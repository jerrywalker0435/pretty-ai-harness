#!/usr/bin/env python3
"""Manage one isolated Pretty Apply run from preflight through Promotion."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
COMMON_SCRIPTS = SCRIPT_DIR.parents[1] / "pretty-common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

from candidate_contract import (  # type: ignore[import-not-found]
    CandidateSnapshot,
    CandidateRequest,
    changed_paths,
    file_sha256,
    quality_bundle_sha256,
    run_git,
    snapshot_candidate,
    stage_candidate_patch,
)
from evidence_binding import (  # type: ignore[import-not-found]
    canonical_json_bytes,
    evidence_sha256,
    payload_sha256,
    self_bound_sha256,
)
from execution_contract import (  # type: ignore[import-not-found]
    contract_preflight_errors,
    contract_preflight_summary,
    resolver_binding_errors,
)
from pretty_tmp import (  # type: ignore[import-not-found]
    CANDIDATE_NAME,
    assert_cleanup_scope,
    candidate_lane_path,
    cleanup_registered_run,
    is_pretty_tmp_path,
    registered_artifact_names,
    topic_dir_for_document,
    topic_dir_for_run,
    validate_artifact_path,
    validate_candidate_lane,
    validate_run_dir,
)
from quality_registry import MIN_BRANCH_COVERAGE, MIN_LINE_COVERAGE  # type: ignore[import-not-found]
from quality_registry import RISK_BY_CODE  # type: ignore[import-not-found]
from quality_resolver import freshness_errors  # type: ignore[import-not-found]


SCHEMA_VERSION = 4
MATRIX_NAME = "execution-matrix.json"
RESOLVER_NAME = "quality-resolver.json"
STATE_NAME = "execution-state.json"
PATCH_NAME = "candidate.patch"
MANIFEST_NAME = "candidate-manifest.json"
MISSING = "<missing>"


@dataclass(frozen=True)
class StartRequest:
    repo: Path
    topic: str
    design: Path
    matrix: Path
    resolver: Path
    state: Path
    runtime_paths: Sequence[str]


@dataclass(frozen=True)
class EvidencePaths:
    quality: Path
    build: Path
    tests: Path
    coverage: Path


@dataclass(frozen=True)
class ContractFiles:
    design: Path
    matrix: Path
    resolver: Path


@dataclass(frozen=True)
class SliceGateRequest:
    state: Path
    repo: Path
    slice_id: str
    quality: Path
    tests: Path
    build: Path | None = None


@dataclass(frozen=True)
class AttemptEvidence:
    candidate: str
    quality: Mapping[str, object]
    tests: Mapping[str, object]
    passed: bool


@dataclass(frozen=True)
class RebindRequest:
    state: Path
    repo: Path
    design: Path
    matrix: Path
    resolver: Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    _write_bytes(path, canonical_json_bytes(payload) + b"\n")


def _write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_bytes(content)
    os.replace(temporary, path)


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def _git_text(repo: Path, arguments: Sequence[str]) -> str:
    return str(run_git(repo, arguments)).strip()


def _state_hash(state: Mapping[str, object]) -> str:
    return payload_sha256(state, {"updated_at", "state_sha256"})


def _save_state(path: Path, state: dict[str, object]) -> dict[str, object]:
    state["updated_at"] = _now()
    state["state_sha256"] = _state_hash(state)
    _write_json(path, state)
    return state


def _load_state(path: Path) -> dict[str, object]:
    state = _load_json(path)
    if state.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Apply state schema_version must be {SCHEMA_VERSION}")
    if state.get("state_sha256") != _state_hash(state):
        raise ValueError("Apply state integrity hash does not match")
    if state.get("state_file") != STATE_NAME or path.name != STATE_NAME:
        raise ValueError(f"Apply state must be named {STATE_NAME}")
    run_dir = path.resolve().parent
    topic = topic_dir_for_run(run_dir)
    if state.get("topic") != topic.name or state.get("run_dir") != str(run_dir):
        raise ValueError("Apply state location does not match its topic run")
    validate_candidate_lane(run_dir, Path(str(state.get("candidate_lane", ""))))
    return state


def _safe_paths(paths: Iterable[str]) -> tuple[str, ...]:
    normalized = []
    for value in paths:
        path = value.replace("\\", "/")
        candidate = Path(path)
        if candidate.is_absolute() or ".." in candidate.parts or not path:
            raise ValueError(f"runtime path must be repository-relative: {value}")
        normalized.append(candidate.as_posix())
    return tuple(sorted(set(normalized)))


def _path_digest(repo: Path, relative_path: str) -> str:
    path = repo / relative_path
    if path.is_symlink():
        return f"<symlink:{os.readlink(path)}>"
    if not path.exists():
        return MISSING
    if not path.is_file():
        raise ValueError(f"runtime path must be a regular file: {relative_path}")
    return file_sha256(path)


def _dirty_paths(repo: Path, paths: Iterable[str]) -> list[str]:
    return [
        path for path in paths
        if _git_text(repo, ["status", "--porcelain", "--untracked-files=all", "--", path])
    ]


def _target_status(repo: Path) -> tuple[str, ...]:
    lines = _git_text(repo, ["status", "--porcelain=v1", "--untracked-files=all"]).splitlines()
    return tuple(sorted(
        line for line in lines
        if line and not is_pretty_tmp_path(line[3:].split(" -> ")[-1])
    ))


def _matrix_paths(matrix: Mapping[str, object]) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    tasks = matrix.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError("execution matrix tasks must be a list")
    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_paths = _safe_paths(
            path
            for field in ("production_files", "test_files", "supporting_files")
            for path in task.get(field, [])
            if isinstance(path, str)
        )
        slices = task.get("behavior_slices", [])
        if not isinstance(slices, list):
            raise ValueError(f"task {task.get('id')} behavior_slices must be a list")
        for behavior_slice in slices:
            if not isinstance(behavior_slice, dict) or not isinstance(behavior_slice.get("id"), str):
                raise ValueError("behavior slice needs an id")
            identifier = behavior_slice["id"].strip()
            if identifier in result:
                raise ValueError(f"duplicate behavior slice: {identifier}")
            result[identifier] = _safe_paths(
                path for path in behavior_slice.get("paths", task_paths) if isinstance(path, str)
            )
    return result


def _matrix_symbols(matrix: Mapping[str, object]) -> tuple[str, ...]:
    symbols = []
    for task in matrix.get("tasks", []):
        if not isinstance(task, dict):
            continue
        for behavior_slice in task.get("behavior_slices", []):
            if isinstance(behavior_slice, dict):
                symbols.extend(
                    value for value in behavior_slice.get("production_symbols", [])
                    if isinstance(value, str)
                )
    return tuple(sorted(set(symbols)))


def _coverage_policy(matrix: Mapping[str, object]) -> dict[str, float]:
    configured = matrix.get("coverage_policy") or {}
    if not isinstance(configured, dict):
        raise ValueError("coverage_policy must be an object")
    retired_keys = {"gate_" + "each_slice", "gate_before_" + "next_slice"}
    if retired_keys & configured.keys():
        raise ValueError("per-slice coverage switches are no longer supported")
    line = float(configured.get("line_threshold", MIN_LINE_COVERAGE))
    branch = float(configured.get("branch_threshold", MIN_BRANCH_COVERAGE))
    if not MIN_LINE_COVERAGE <= line <= 100 or not MIN_BRANCH_COVERAGE <= branch <= 100:
        raise ValueError("coverage thresholds cannot be lower than the registry minimum")
    return {"line_threshold": line, "branch_threshold": branch}


def _registered_artifact(state: Mapping[str, object], path: Path) -> Path:
    artifact = validate_artifact_path(Path(str(state["run_dir"])), path.resolve())
    if artifact.name not in registered_artifact_names(state.get("temporary_artifacts", [])):
        raise ValueError(f"artifact is not registered: {artifact.name}")
    return artifact


def _repo_for(state: Mapping[str, object], repo: Path | None = None) -> Path:
    expected = Path(str(state["target_repo"])).resolve()
    actual = expected if repo is None else repo.resolve()
    if actual != expected:
        raise ValueError(f"Apply target repository changed: {actual}")
    return expected


def _contract_files(state: Mapping[str, object]) -> ContractFiles:
    return ContractFiles(
        Path(str(state["design_path"])),
        Path(str(state["execution_matrix_path"])),
        Path(str(state["resolver_path"])),
    )


def _assert_target_unchanged(state: Mapping[str, object], repo: Path | None = None) -> Path:
    target = _repo_for(state, repo)
    if _git_text(target, ["rev-parse", "HEAD"]) != state.get("start_head"):
        raise ValueError("Apply target HEAD changed")
    if tuple(state.get("start_target_status", ())) != _target_status(target):
        raise ValueError("Apply target Git working tree changed")
    registered = state.get("registered_runtime_paths", {})
    if not isinstance(registered, dict):
        raise ValueError("registered_runtime_paths must be an object")
    changed = [
        str(path) for path, expected in registered.items()
        if _path_digest(target, str(path)) != expected
    ]
    if changed:
        raise ValueError(f"Apply target runtime path changed: {', '.join(sorted(changed))}")
    return target


def _load_contract(files: ContractFiles) -> tuple[str, dict[str, object], dict[str, object]]:
    return (
        files.design.read_text(encoding="utf-8"),
        _load_json(files.matrix),
        _load_json(files.resolver),
    )


def _preflight(
    files: ContractFiles, start_head: str | None = None, repo: Path | None = None,
) -> tuple[str, dict[str, object], dict[str, object], str]:
    design, matrix, resolver = _load_contract(files)
    design_hash = file_sha256(files.design)
    errors = contract_preflight_errors(design, matrix)
    errors.extend(resolver_binding_errors(matrix, resolver, design_hash, start_head))
    if repo is not None:
        errors.extend(freshness_errors(repo, resolver))
    if errors:
        raise ValueError("Apply preflight failed: " + "; ".join(sorted(set(errors))))
    return design, matrix, resolver, design_hash


def _assert_contract_current(
    state: Mapping[str, object], *, validate_resolver_freshness: bool = False,
) -> ContractFiles:
    files = _contract_files(state)
    expected = {
        files.design: state.get("design_sha256"),
        files.matrix: state.get("execution_matrix_sha256"),
        files.resolver: state.get("resolver_sha256"),
    }
    stale = [str(path) for path, digest in expected.items() if file_sha256(path) != digest]
    if stale:
        raise ValueError(f"Apply contract changed without rebind: {', '.join(stale)}")
    if quality_bundle_sha256() != state.get("shared_bundle_sha256"):
        raise ValueError("shared quality bundle changed during Apply")
    repo = Path(str(state["target_repo"])) if validate_resolver_freshness else None
    _preflight(files, str(state.get("start_head")), repo)
    return files


def _snapshot(
    state: Mapping[str, object], repo: Path, paths: Iterable[str] | None = None,
    *, validate_resolver_freshness: bool = False,
) -> CandidateSnapshot:
    files = _assert_contract_current(state, validate_resolver_freshness=validate_resolver_freshness)
    design, matrix, resolver = _load_contract(files)
    return snapshot_candidate(CandidateRequest(
        repo, design, matrix, resolver, str(state["start_head"]),
        str(state["shared_bundle_sha256"]), paths,
    ))


def _lane(state: Mapping[str, object]) -> Path:
    lane = validate_candidate_lane(Path(str(state["run_dir"])), Path(str(state["candidate_lane"])))
    if not lane.exists():
        raise ValueError("Apply Candidate Lane is missing")
    return lane


def _binding_errors(payload: Mapping[str, object], state: Mapping[str, object]) -> list[str]:
    expected = {
        "start_head": state.get("start_head"),
        "design_sha256": state.get("design_sha256"),
        "execution_matrix_sha256": state.get("execution_matrix_sha256"),
        "resolver_sha256": state.get("resolver_sha256"),
        "shared_bundle_sha256": state.get("shared_bundle_sha256"),
    }
    return [f"evidence has stale {field}" for field, value in expected.items() if payload.get(field) != value]


def _load_evidence(state: Mapping[str, object], path: Path, label: str) -> dict[str, object]:
    artifact = _registered_artifact(state, path)
    payload = _load_json(artifact)
    if payload.get("evidence_sha256") != evidence_sha256(payload):
        raise ValueError(f"{label} evidence integrity hash does not match")
    errors = _binding_errors(payload, state)
    if errors:
        raise ValueError(f"{label}: " + "; ".join(errors))
    return payload


def _review_finding_errors(state: Mapping[str, object], review: Mapping[str, object]) -> list[str]:
    accepted = review.get("accepted_findings")
    extensions = review.get("scope_extensions")
    if not isinstance(accepted, list) or not isinstance(extensions, list):
        return ["review receipt needs accepted_findings and scope_extensions lists"]
    objective = state.get("objective_evidence")
    if not isinstance(objective, dict) or not isinstance(objective.get("quality"), str):
        return []
    quality = _load_evidence(state, Path(str(state["run_dir"])) / str(objective["quality"]), "quality")
    required = {
        str(finding.get("fingerprint"))
        for finding in quality.get("findings", [])
        if isinstance(finding, dict) and finding.get("severity") == "review_required"
    }
    provided = {
        str(item.get("fingerprint"))
        for item in accepted if isinstance(item, dict) and item.get("fingerprint")
    }
    return ["review receipt does not account for every review_required finding"] if required != provided else []


def start_apply(request: StartRequest) -> dict[str, object]:
    repo = request.repo.resolve()
    files = ContractFiles(request.design.resolve(), request.matrix.resolve(), request.resolver.resolve())
    state_path = request.state.resolve()
    topic_dir = topic_dir_for_document(files.design)
    run_dir = validate_run_dir(topic_dir, files.matrix.parent)
    if request.topic != topic_dir.name or state_path.parent != run_dir:
        raise ValueError("Apply topic, matrix, and state must share one run directory")
    if files.matrix.name != MATRIX_NAME or files.resolver.name != RESOLVER_NAME or state_path.name != STATE_NAME:
        raise ValueError("Apply artifacts have invalid names")
    validate_artifact_path(run_dir, files.matrix)
    validate_artifact_path(run_dir, files.resolver)
    if state_path.exists() or candidate_lane_path(run_dir).exists():
        raise ValueError("Apply state or Candidate Lane already exists")
    assert_cleanup_scope(run_dir, STATE_NAME, [MATRIX_NAME, RESOLVER_NAME])
    start_head = _git_text(repo, ["rev-parse", "HEAD"])
    _, matrix, _, design_hash = _preflight(files, start_head, repo)
    slice_paths = _matrix_paths(matrix)
    runtime_paths = _safe_paths((*request.runtime_paths, *(p for paths in slice_paths.values() for p in paths)))
    dirty = _dirty_paths(repo, runtime_paths)
    if dirty:
        raise ValueError(f"runtime paths must be clean: {', '.join(dirty)}")
    lane = candidate_lane_path(run_dir)
    try:
        run_git(repo, ["worktree", "add", "--detach", str(lane), start_head])
        order = list(slice_paths)
        created_at = _now()
        state: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "mode": "apply",
            "topic": request.topic,
            "run_id": run_dir.name,
            "run_dir": str(run_dir),
            "state_file": STATE_NAME,
            "target_repo": str(repo),
            "candidate_lane": str(lane),
            "design_path": str(files.design),
            "execution_matrix_path": str(files.matrix),
            "resolver_path": str(files.resolver),
            "start_head": start_head,
            "start_target_status": list(_target_status(repo)),
            "design_sha256": design_hash,
            "execution_matrix_sha256": file_sha256(files.matrix),
            "resolver_sha256": file_sha256(files.resolver),
            "shared_bundle_sha256": quality_bundle_sha256(),
            "contract_preflight": contract_preflight_summary(),
            "coverage_policy": _coverage_policy(matrix),
            "slice_order": order,
            "active_slice": order[0] if order else None,
            "slice_runtime_paths": {key: list(value) for key, value in slice_paths.items()},
            "approved_symbols": list(_matrix_symbols(matrix)),
            "registered_runtime_paths": {path: _path_digest(repo, path) for path in runtime_paths},
            "first_attempts": {},
            "slice_results": {},
            "candidate_sha256": None,
            "objective_gate": None,
            "active_review": None,
            "frozen_patch_sha256": None,
            "temporary_artifacts": [MATRIX_NAME, RESOLVER_NAME, CANDIDATE_NAME],
            "phase": "writing",
            "status": "in_progress",
            "created_at": created_at,
            "updated_at": created_at,
        }
        return _save_state(state_path, state)
    except Exception:
        if lane.exists():
            run_git(repo, ["worktree", "remove", "--force", str(lane)])
        raise


def _assert_writable(state: Mapping[str, object]) -> None:
    if state.get("status") != "in_progress" or state.get("phase") != "writing":
        raise ValueError("Apply is not in a writable phase")


def register_apply(state_path: Path, names: Sequence[str]) -> dict[str, object]:
    state = _load_state(state_path)
    if state.get("status") != "in_progress":
        raise ValueError("completed Apply cannot register evidence")
    artifacts = registered_artifact_names(state.get("temporary_artifacts", []))
    requested = registered_artifact_names(names)
    reserved = {STATE_NAME, CANDIDATE_NAME, MATRIX_NAME, RESOLVER_NAME, PATCH_NAME, MANIFEST_NAME}
    invalid = sorted(requested & reserved)
    if invalid:
        raise ValueError(f"reserved Apply artifacts cannot be registered manually: {', '.join(invalid)}")
    for name in requested - artifacts:
        path = validate_artifact_path(state_path.parent, state_path.parent / name)
        if path.exists() or path.is_symlink():
            raise ValueError(f"refusing to register a pre-existing artifact: {name}")
    state["temporary_artifacts"] = sorted(artifacts | requested)
    return _save_state(state_path, state)


def checkpoint_apply(state_path: Path, repo: Path) -> dict[str, object]:
    state = _load_state(state_path)
    _assert_writable(state)
    _assert_target_unchanged(state, repo)
    lane = _lane(state)
    allowed: set[str] = set()
    active = state.get("active_slice")
    closed = set(state.get("slice_results", {}))
    for slice_id in state.get("slice_order", []):
        if slice_id in closed or slice_id == active:
            allowed.update(state.get("slice_runtime_paths", {}).get(slice_id, []))
        if slice_id == active:
            break
    outside = sorted(set(changed_paths(lane, str(state["start_head"]))) - allowed)
    if outside:
        raise ValueError(f"runtime paths changed outside the active slice: {', '.join(outside)}")
    state["last_checkpoint_sha256"] = _snapshot(state, lane).sha256
    return _save_state(state_path, state)


def resume_apply(state_path: Path, repo: Path) -> dict[str, object]:
    state = _load_state(state_path)
    _assert_target_unchanged(state, repo)
    _assert_contract_current(state, validate_resolver_freshness=True)
    _lane(state)
    if state.get("phase") in {"frozen", "objective_gated", "reviewing", "review_passed"}:
        _assert_frozen(state)
    return state


def _record_attempt(state: dict[str, object], request: SliceGateRequest, evidence: AttemptEvidence) -> None:
    attempts = dict(state.get("first_attempts", {}))
    previous = attempts.get(request.slice_id)
    findings = evidence.quality.get("findings", [])
    mechanical_count = len(findings) if isinstance(findings, list) else 0
    if not isinstance(previous, dict):
        attempts[request.slice_id] = {
            "candidate_sha256": evidence.candidate,
            "mechanical_findings": mechanical_count,
            "tests_passed": evidence.tests.get("passed") is True,
            "passed": evidence.passed,
            "repair_count": 0,
            "last_attempt_sha256": evidence.candidate,
        }
    else:
        updated = dict(previous)
        if updated.get("last_attempt_sha256") != evidence.candidate:
            updated["repair_count"] = int(updated.get("repair_count", 0)) + 1
            updated["last_attempt_sha256"] = evidence.candidate
        attempts[request.slice_id] = updated
    state["first_attempts"] = attempts


def slice_gate(request: SliceGateRequest) -> dict[str, object]:
    state = _load_state(request.state)
    _assert_writable(state)
    if state.get("active_slice") != request.slice_id:
        raise ValueError(f"slice is not active: {request.slice_id}")
    _assert_target_unchanged(state, request.repo)
    lane = _lane(state)
    snapshot = _snapshot(state, lane)
    quality = _load_evidence(state, request.quality, "quality")
    tests = _load_evidence(state, request.tests, "test")
    build = _load_evidence(state, request.build, "build") if request.build else None
    errors = []
    if quality.get("scope") != "slice" or quality.get("slice_id") != request.slice_id:
        errors.append("quality evidence must identify the active slice")
    if quality.get("candidate_sha256") != snapshot.sha256:
        errors.append("slice quality evidence does not match the current candidate")
    if quality.get("passed") is not True:
        errors.append("slice quality Gate did not pass")
    if tests.get("scope") != "slice" or tests.get("slice_id") != request.slice_id:
        errors.append("test evidence must identify the active slice")
    if tests.get("quality_candidate_sha256") != snapshot.sha256 or tests.get("passed") is not True:
        errors.append("slice test evidence did not pass for the current candidate")
    if build is not None and (
        build.get("quality_candidate_sha256") != snapshot.sha256 or build.get("passed") is not True
    ):
        errors.append("slice build evidence did not pass for the current candidate")
    _record_attempt(state, request, AttemptEvidence(snapshot.sha256, quality, tests, not errors))
    if errors:
        _save_state(request.state, state)
        raise ValueError("; ".join(errors))
    results = dict(state.get("slice_results", {}))
    results[request.slice_id] = {
        "candidate_sha256": snapshot.sha256,
        "quality_evidence_sha256": quality["evidence_sha256"],
        "test_evidence_sha256": tests["evidence_sha256"],
        "build_evidence_sha256": build.get("evidence_sha256") if build else None,
        "passed": True,
    }
    order = list(state.get("slice_order", []))
    index = order.index(request.slice_id)
    state["slice_results"] = results
    state["active_slice"] = order[index + 1] if index + 1 < len(order) else None
    state["phase"] = "writing" if state["active_slice"] else "slice_gated"
    return _save_state(request.state, state)


def rebind_apply(request: RebindRequest) -> dict[str, object]:
    state = _load_state(request.state)
    _assert_writable(state)
    target = _assert_target_unchanged(state, request.repo)
    current = _contract_files(state)
    replacement = ContractFiles(request.design.resolve(), request.matrix.resolve(), request.resolver.resolve())
    if replacement != current:
        raise ValueError("rebind must update the registered Design, matrix, and Resolver paths in place")
    _, matrix_payload, _, design_hash = _preflight(
        replacement, str(state["start_head"]), request.repo.resolve()
    )
    if design_hash != state.get("design_sha256"):
        raise ValueError("rebind cannot change the approved Design")
    slice_paths = _matrix_paths(matrix_payload)
    new_runtime = _safe_paths(path for paths in slice_paths.values() for path in paths)
    registered = dict(state.get("registered_runtime_paths", {}))
    new_paths = sorted(set(new_runtime) - set(registered))
    dirty = _dirty_paths(target, new_paths)
    if dirty:
        raise ValueError(f"new runtime paths must be clean in the target: {', '.join(dirty)}")
    registered.update({path: _path_digest(target, path) for path in new_paths})
    order = list(slice_paths)
    state.update({
        "execution_matrix_sha256": file_sha256(replacement.matrix),
        "resolver_sha256": file_sha256(replacement.resolver),
        "shared_bundle_sha256": quality_bundle_sha256(),
        "coverage_policy": _coverage_policy(matrix_payload),
        "slice_order": order,
        "active_slice": order[0] if order else None,
        "slice_runtime_paths": {key: list(value) for key, value in slice_paths.items()},
        "approved_symbols": list(_matrix_symbols(matrix_payload)),
        "registered_runtime_paths": registered,
        "slice_results": {},
        "first_attempts": {},
        "objective_gate": None,
        "active_review": None,
        "candidate_sha256": None,
        "frozen_patch_sha256": None,
        "phase": "writing",
    })
    return _save_state(request.state, state)


def _register_internal(state_path: Path, state: dict[str, object], names: Iterable[str]) -> None:
    artifacts = registered_artifact_names(state.get("temporary_artifacts", []))
    for name in names:
        path = validate_artifact_path(state_path.parent, state_path.parent / name)
        if path.exists() and name not in artifacts:
            raise ValueError(f"refusing to overwrite unregistered artifact: {name}")
        artifacts.add(name)
    state["temporary_artifacts"] = sorted(artifacts)


def freeze_apply(state_path: Path, repo: Path, quality_path: Path) -> dict[str, object]:
    state = _load_state(state_path)
    _assert_target_unchanged(state, repo)
    if state.get("phase") not in {"writing", "slice_gated"} or state.get("active_slice") is not None:
        raise ValueError("all behavior slices must pass before freezing")
    quality = _load_evidence(state, quality_path, "quality")
    lane = _lane(state)
    snapshot = _snapshot(state, lane)
    if quality.get("scope") != "candidate" or quality.get("candidate_sha256") != snapshot.sha256:
        raise ValueError("candidate quality evidence does not match the Lane")
    if quality.get("passed") is not True:
        raise ValueError("candidate quality Gate did not pass")
    if not snapshot.changed_paths:
        raise ValueError("cannot freeze an empty candidate")
    patch = stage_candidate_patch(lane, str(state["start_head"]), snapshot.changed_paths)
    if not patch:
        raise ValueError("candidate patch is empty")
    _register_internal(state_path, state, (PATCH_NAME, MANIFEST_NAME))
    _save_state(state_path, state)
    patch_path = state_path.parent / PATCH_NAME
    _write_bytes(patch_path, patch)
    manifest = {
        "candidate_sha256": snapshot.sha256,
        "start_head": state["start_head"],
        "shared_bundle_sha256": state["shared_bundle_sha256"],
        "paths": list(snapshot.changed_paths),
        "source_sha256": dict(snapshot.source_sha256),
        "source_states": dict(snapshot.source_states),
        "patch_sha256": file_sha256(patch_path),
    }
    _write_json(state_path.parent / MANIFEST_NAME, manifest)
    state["candidate_sha256"] = snapshot.sha256
    state["frozen_patch_sha256"] = manifest["patch_sha256"]
    state["phase"] = "frozen"
    return _save_state(state_path, state)


def _assert_frozen(state: Mapping[str, object]) -> tuple[dict[str, object], CandidateSnapshot]:
    if not state.get("candidate_sha256") or not state.get("frozen_patch_sha256"):
        raise ValueError("Apply has no frozen candidate")
    patch_path = _registered_artifact(state, Path(str(state["run_dir"])) / PATCH_NAME)
    manifest_path = _registered_artifact(state, Path(str(state["run_dir"])) / MANIFEST_NAME)
    if file_sha256(patch_path) != state.get("frozen_patch_sha256"):
        raise ValueError("frozen candidate patch changed")
    manifest = _load_json(manifest_path)
    paths = manifest.get("paths")
    if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths):
        raise ValueError("candidate manifest paths are invalid")
    snapshot = _snapshot(state, _lane(state), paths)
    expected = {
        "candidate_sha256": snapshot.sha256,
        "start_head": state.get("start_head"),
        "shared_bundle_sha256": state.get("shared_bundle_sha256"),
        "paths": list(snapshot.changed_paths),
        "source_sha256": dict(snapshot.source_sha256),
        "source_states": dict(snapshot.source_states),
        "patch_sha256": state.get("frozen_patch_sha256"),
    }
    if manifest != expected or snapshot.sha256 != state.get("candidate_sha256"):
        raise ValueError("frozen candidate or manifest changed")
    if changed_paths(_lane(state), str(state["start_head"])) != snapshot.changed_paths:
        raise ValueError("frozen Candidate Lane path scope changed")
    return manifest, snapshot


def _build_command_errors(
    build: Mapping[str, object], quality: Mapping[str, object],
    tests: Mapping[str, object], coverage: Mapping[str, object],
) -> list[str]:
    commands = build.get("commands")
    if not isinstance(commands, list):
        return ["build evidence commands must be a list"]
    errors = []
    satisfied: set[str] = set()
    seen_commands: set[str] = set()
    allowed = {"compile", "new_tests", "regression_tests", "coverage"}
    for index, entry in enumerate(commands):
        if not isinstance(entry, dict):
            errors.append(f"build command {index} must be an object")
            continue
        command = entry.get("command")
        command_key = json.dumps(command, ensure_ascii=False, sort_keys=True)
        if command_key in seen_commands:
            errors.append(f"equivalent build command is duplicated: {command}")
        seen_commands.add(command_key)
        kinds = entry.get("satisfies")
        if not isinstance(kinds, list) or not kinds or any(kind not in allowed for kind in kinds):
            errors.append(f"build command {index} has invalid satisfies")
            continue
        if entry.get("exit_code") != 0:
            errors.append(f"build command {index} failed")
        satisfied.update(kinds)
    required = set()
    if quality.get("production_java") is True:
        required.update({"compile", "regression_tests"})
    if tests.get("expected_tests"):
        required.add("new_tests")
    if coverage.get("status") == "pass":
        required.add("coverage")
    for kind in sorted(required - satisfied):
        errors.append(f"build command graph does not satisfy {kind}")
    return errors


def _objective_errors(
    state: Mapping[str, object], paths: EvidencePaths, candidate: str,
) -> tuple[list[str], tuple[dict[str, object], ...]]:
    quality = _load_evidence(state, paths.quality, "quality")
    build = _load_evidence(state, paths.build, "build")
    tests = _load_evidence(state, paths.tests, "test")
    coverage = _load_evidence(state, paths.coverage, "coverage")
    errors = []
    if quality.get("scope") != "candidate" or quality.get("candidate_sha256") != candidate or quality.get("passed") is not True:
        errors.append("objective quality evidence did not pass for the frozen candidate")
    if build.get("candidate_sha256") != self_bound_sha256(build):
        errors.append("build evidence self digest does not match")
    if build.get("quality_candidate_sha256") != candidate or build.get("passed") is not True:
        errors.append("objective build evidence did not pass for the frozen candidate")
    if tests.get("quality_candidate_sha256") != candidate or tests.get("scope") != "final" or tests.get("passed") is not True:
        errors.append("objective test evidence did not pass for the frozen candidate")
    if coverage.get("quality_candidate_sha256") != candidate or coverage.get("scope") != "final":
        errors.append("objective coverage evidence is stale or not final")
    policy = state.get("coverage_policy", {})
    if coverage.get("status") not in {"pass", "not_applicable"}:
        errors.append("objective coverage Gate did not pass")
    if coverage.get("status") == "pass":
        if float(coverage.get("line_percentage", 0)) < float(policy.get("line_threshold", MIN_LINE_COVERAGE)):
            errors.append("objective line coverage is below policy")
        branch = coverage.get("branch_percentage")
        if branch is not None and float(branch) < float(policy.get("branch_threshold", MIN_BRANCH_COVERAGE)):
            errors.append("objective branch coverage is below policy")
    errors.extend(_build_command_errors(build, quality, tests, coverage))
    return errors, (quality, build, tests, coverage)


def record_objective_gate(state_path: Path, repo: Path, paths: EvidencePaths) -> dict[str, object]:
    state = _load_state(state_path)
    _assert_target_unchanged(state, repo)
    if state.get("phase") != "frozen" or not state.get("candidate_sha256"):
        raise ValueError("candidate must be frozen before objective Gate")
    _assert_frozen(state)
    errors, evidence = _objective_errors(state, paths, str(state["candidate_sha256"]))
    if errors:
        raise ValueError("; ".join(errors))
    quality, build, tests, coverage = evidence
    state["objective_gate"] = {
        "quality_candidate_sha256": quality["candidate_sha256"],
        "build_candidate_sha256": build["candidate_sha256"],
        "test_evidence_sha256": tests["evidence_sha256"],
        "coverage_evidence_sha256": coverage["evidence_sha256"],
    }
    state["objective_evidence"] = {
        "quality": paths.quality.name,
        "build": paths.build.name,
        "tests": paths.tests.name,
        "coverage": paths.coverage.name,
    }
    state["phase"] = "objective_gated"
    return _save_state(state_path, state)


def start_review(state_path: Path) -> dict[str, object]:
    state = _load_state(state_path)
    _assert_target_unchanged(state)
    _assert_frozen(state)
    if state.get("phase") != "objective_gated" or not isinstance(state.get("objective_gate"), dict):
        raise ValueError("objective Gate must pass before Review")
    request = {
        "run_id": state["run_id"],
        "candidate_sha256": state["candidate_sha256"],
        "pre_review_gate": state["objective_gate"],
        "review_session_id": uuid.uuid4().hex,
        "reviewer_context_id": uuid.uuid4().hex,
    }
    state["active_review"] = request
    state["phase"] = "reviewing"
    _save_state(state_path, state)
    return request


def record_review(state_path: Path, review_path: Path) -> dict[str, object]:
    state = _load_state(state_path)
    _assert_target_unchanged(state)
    _assert_frozen(state)
    if state.get("phase") != "reviewing":
        raise ValueError("Apply Review is not active")
    review = _load_evidence(state, review_path, "review")
    active = state.get("active_review")
    if not isinstance(active, dict):
        raise ValueError("Apply Review was not started")
    errors = []
    for field in ("run_id", "review_session_id", "reviewer_context_id", "candidate_sha256"):
        if review.get(field) != active.get(field):
            errors.append(f"review receipt does not match {field}")
    if review.get("independent") is not True or not review.get("reviewer"):
        errors.append("review receipt must identify an independent reviewer")
    risks = review.get("risks")
    if not isinstance(risks, list):
        errors.append("review receipt must include Resolver risks")
    else:
        actual_risk_ids = set()
        for risk in risks:
            if not isinstance(risk, dict) or risk.get("id") not in RISK_BY_CODE:
                errors.append("review receipt contains an unknown Resolver risk")
            elif risk.get("owner") != RISK_BY_CODE[str(risk["id"])].owner:
                errors.append(f"review receipt has the wrong owner for risk {risk['id']}")
            else:
                actual_risk_ids.add(str(risk["id"]))
        resolver = _load_json(_contract_files(state).resolver)
        expected_risk_ids = {
            str(risk.get("id"))
            for item in resolver.get("slices", []) if isinstance(item, dict)
            for risk in item.get("risks", []) if isinstance(risk, dict)
        }
        if actual_risk_ids != expected_risk_ids:
            errors.append("review receipt risks do not match the current Resolver")
        expected_guards = {
            str(guard)
            for item in resolver.get("slices", []) if isinstance(item, dict)
            for guard in item.get("guards", []) if isinstance(guard, str)
        }
        actual_guards = set(review.get("guards", [])) if isinstance(review.get("guards"), list) else set()
        if not expected_guards.issubset(actual_guards):
            errors.append("review receipt is missing a Resolver-required Guard")
    if review.get("blocking_findings") != []:
        errors.append("review receipt contains unresolved blocking findings")
    if review.get("pre_review_gate") != state.get("objective_gate"):
        errors.append("review receipt does not match objective Gate")
    errors.extend(_review_finding_errors(state, review))
    if errors:
        raise ValueError("; ".join(errors))
    state["review_receipt_sha256"] = review["evidence_sha256"]
    state["review_evidence"] = review_path.name
    state["phase"] = "review_passed"
    return _save_state(state_path, state)


def reopen_apply(state_path: Path, repo: Path, slice_id: str, reason: str) -> dict[str, object]:
    state = _load_state(state_path)
    _assert_target_unchanged(state, repo)
    if state.get("phase") not in {"frozen", "objective_gated", "reviewing", "review_passed"}:
        raise ValueError("Apply cannot be reopened from the current phase")
    if not reason.strip():
        raise ValueError("reopen requires a concrete finding")
    order = list(state.get("slice_order", []))
    if slice_id not in order:
        raise ValueError(f"unknown behavior slice: {slice_id}")
    cutoff = order.index(slice_id)
    state["slice_results"] = {
        key: value for key, value in dict(state.get("slice_results", {})).items()
        if key in order and order.index(key) < cutoff
    }
    state.update({
        "active_slice": slice_id,
        "phase": "writing",
        "candidate_sha256": None,
        "objective_gate": None,
        "objective_evidence": None,
        "active_review": None,
        "review_receipt_sha256": None,
        "review_evidence": None,
        "frozen_patch_sha256": None,
        "reopen_reason": reason.strip(),
    })
    artifacts = registered_artifact_names(state.get("temporary_artifacts", []))
    for name in (PATCH_NAME, MANIFEST_NAME):
        path = validate_artifact_path(state_path.parent, state_path.parent / name)
        if path.exists() or path.is_symlink():
            path.unlink()
        artifacts.discard(name)
    state["temporary_artifacts"] = sorted(artifacts)
    return _save_state(state_path, state)


def promote_apply(state_path: Path, repo: Path) -> dict[str, object]:
    state = _load_state(state_path)
    if state.get("phase") != "review_passed":
        raise ValueError("Apply is not ready for Promotion")
    target = _assert_target_unchanged(state, repo)
    manifest, frozen = _assert_frozen(state)
    patch_path = _registered_artifact(state, state_path.parent / PATCH_NAME)
    run_git(target, ["apply", "--check", "--binary", str(patch_path)])
    run_git(target, ["apply", "--binary", str(patch_path)])
    promoted = _snapshot(state, target, manifest["paths"], validate_resolver_freshness=False)
    if promoted.sha256 != frozen.sha256 or promoted.source_states != frozen.source_states:
        raise ValueError("Promotion result does not match the frozen candidate; Lane retained")
    state["phase"] = "promoted"
    state["status"] = "completed"
    state["promoted_candidate_sha256"] = promoted.sha256
    return _save_state(state_path, state)


def cleanup_apply(state_path: Path, repo: Path) -> tuple[str, ...]:
    state = _load_state(state_path)
    target = _repo_for(state, repo)
    lane = validate_candidate_lane(state_path.parent, Path(str(state["candidate_lane"])))
    if lane.exists():
        run_git(target, ["worktree", "remove", "--force", str(lane)])
    artifacts = registered_artifact_names(state.get("temporary_artifacts", []))
    return cleanup_registered_run(topic_dir_for_run(state_path.parent), state_path.parent, STATE_NAME, artifacts)


def _contract_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("--state", type=Path, required=True)
    command.add_argument("--repo", type=Path, default=Path("."))
    command.add_argument("--design", type=Path, required=True)
    command.add_argument("--execution-matrix", type=Path, required=True)
    command.add_argument("--resolver", type=Path, required=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start")
    start.add_argument("--repo", type=Path, default=Path("."))
    start.add_argument("--topic", required=True)
    start.add_argument("--design", type=Path, required=True)
    start.add_argument("--execution-matrix", type=Path, required=True)
    start.add_argument("--resolver", type=Path, required=True)
    start.add_argument("--state", type=Path, required=True)
    start.add_argument("--runtime-path", action="append", default=[])
    register = commands.add_parser("register")
    register.add_argument("--state", type=Path, required=True)
    register.add_argument("--artifact", action="append", required=True)
    for name in ("checkpoint", "resume"):
        command = commands.add_parser(name)
        command.add_argument("--state", type=Path, required=True)
        command.add_argument("--repo", type=Path, default=Path("."))
    rebind = commands.add_parser("rebind")
    _contract_arguments(rebind)
    slice_command = commands.add_parser("slice-gate")
    slice_command.add_argument("--state", type=Path, required=True)
    slice_command.add_argument("--repo", type=Path, default=Path("."))
    slice_command.add_argument("--slice-id", required=True)
    slice_command.add_argument("--quality", type=Path, required=True)
    slice_command.add_argument("--tests", type=Path, required=True)
    slice_command.add_argument("--build", type=Path)
    freeze = commands.add_parser("freeze")
    freeze.add_argument("--state", type=Path, required=True)
    freeze.add_argument("--repo", type=Path, default=Path("."))
    freeze.add_argument("--quality", type=Path, required=True)
    objective = commands.add_parser("objective-gate")
    objective.add_argument("--state", type=Path, required=True)
    objective.add_argument("--repo", type=Path, default=Path("."))
    for label in ("quality", "build", "tests", "coverage"):
        objective.add_argument(f"--{label}", type=Path, required=True)
    commands.add_parser("start-review").add_argument("--state", type=Path, required=True)
    review = commands.add_parser("record-review")
    review.add_argument("--state", type=Path, required=True)
    review.add_argument("--review", type=Path, required=True)
    reopen = commands.add_parser("reopen")
    reopen.add_argument("--state", type=Path, required=True)
    reopen.add_argument("--repo", type=Path, default=Path("."))
    reopen.add_argument("--slice-id", required=True)
    reopen.add_argument("--reason", required=True)
    for name in ("promote", "cleanup"):
        command = commands.add_parser(name)
        command.add_argument("--state", type=Path, required=True)
        command.add_argument("--repo", type=Path, default=Path("."))
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(arguments)
    try:
        if args.command == "start":
            result = start_apply(StartRequest(
                args.repo, args.topic, args.design, args.execution_matrix,
                args.resolver, args.state, args.runtime_path,
            ))
        elif args.command == "register":
            result = register_apply(args.state, args.artifact)
        elif args.command == "checkpoint":
            result = checkpoint_apply(args.state, args.repo)
        elif args.command == "resume":
            result = resume_apply(args.state, args.repo)
        elif args.command == "rebind":
            result = rebind_apply(RebindRequest(
                args.state, args.repo, args.design, args.execution_matrix, args.resolver,
            ))
        elif args.command == "slice-gate":
            result = slice_gate(SliceGateRequest(
                args.state, args.repo, args.slice_id, args.quality, args.tests, args.build,
            ))
        elif args.command == "freeze":
            result = freeze_apply(args.state, args.repo, args.quality)
        elif args.command == "objective-gate":
            result = record_objective_gate(
                args.state, args.repo,
                EvidencePaths(args.quality, args.build, args.tests, args.coverage),
            )
        elif args.command == "start-review":
            result = start_review(args.state)
        elif args.command == "record-review":
            result = record_review(args.state, args.review)
        elif args.command == "reopen":
            result = reopen_apply(args.state, args.repo, args.slice_id, args.reason)
        elif args.command == "promote":
            result = promote_apply(args.state, args.repo)
        else:
            result = {"status": "cleaned", "removed": cleanup_apply(args.state, args.repo)}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"Apply run failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
