#!/usr/bin/env python3
"""Coordinate an Apply run and prevent stale worktree or evidence reuse."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping, Sequence

COMMON_SCRIPTS = Path(__file__).resolve().parents[2] / "pretty-common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

from evidence_binding import evidence_sha256  # type: ignore[import-not-found]
from execution_contract import contract_preflight_errors, contract_preflight_summary
from pretty_tmp import (  # type: ignore[import-not-found]
    assert_cleanup_scope,
    cleanup_registered_run,
    is_pretty_tmp_path,
    registered_artifact_names,
    topic_dir_for_document,
    topic_dir_for_run,
    validate_artifact_path,
    validate_run_dir,
)


SCHEMA_VERSION = 3
MISSING = "<missing>"
MATRIX_NAME = "execution-matrix.json"
STATE_NAME = "execution-state.json"
LEGACY_STATE_NAME = ".execution-state.json"
STATE_NAMES = {STATE_NAME, LEGACY_STATE_NAME}
DEFAULT_LINE_THRESHOLD = 90.0
DEFAULT_BRANCH_THRESHOLD = 80.0


@dataclass(frozen=True)
class ApplyStartRequest:
    repo: Path
    topic: str
    design: Path
    execution_matrix: Path
    state_path: Path
    runtime_paths: Sequence[str]


@dataclass(frozen=True)
class ApplyFreezeRequest:
    state_path: Path
    repo: Path
    design: Path
    execution_matrix: Path
    candidate_sha256: str


@dataclass(frozen=True)
class ObjectiveGatePaths:
    quality: Path
    build: Path
    tests: Path
    coverage: Path


@dataclass(frozen=True)
class SliceCoverageRequest:
    state_path: Path
    repo: Path
    design: Path
    slice_id: str
    coverage_path: Path


def _coverage_threshold(value: object, name: str, default: float) -> float:
    threshold = default if value is None else value
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise ValueError(f"coverage_policy {name} must be between 0 and 100")
    if not 0 <= float(threshold) <= 100:
        raise ValueError(f"coverage_policy {name} must be between 0 and 100")
    return float(threshold)


def _coverage_policy(matrix: Mapping[str, object]) -> dict[str, object]:
    """Return the immutable per-slice coverage policy for an Apply run."""
    configured = matrix.get("coverage_policy") or {}
    if not isinstance(configured, dict):
        raise ValueError("execution matrix coverage_policy must be an object")
    line = _coverage_threshold(configured.get("line_threshold"), "line_threshold", DEFAULT_LINE_THRESHOLD)
    branch = _coverage_threshold(configured.get("branch_threshold"), "branch_threshold", DEFAULT_BRANCH_THRESHOLD)
    if line < DEFAULT_LINE_THRESHOLD or branch < DEFAULT_BRANCH_THRESHOLD:
        raise ValueError("coverage_policy cannot lower the 90%/80% minimum thresholds")
    gate_each = configured.get("gate_each_slice", True)
    gate_before_next = configured.get("gate_before_next_slice", True)
    if gate_each is not True or gate_before_next is not True:
        raise ValueError("per-slice coverage gates cannot be disabled")
    return {
        "line_threshold": float(line),
        "branch_threshold": float(branch),
        "gate_each_slice": True,
        "gate_before_next_slice": True,
    }


def _task_slice_ids(task: Mapping[str, object]) -> tuple[str, ...]:
    slices = task.get("behavior_slices", [])
    if not isinstance(slices, list):
        raise ValueError(f"execution matrix task {task.get('id', '<unknown>')} behavior_slices must be a list")
    identifiers: list[str] = []
    for behavior_slice in slices:
        if not isinstance(behavior_slice, dict) or not isinstance(behavior_slice.get("id"), str):
            raise ValueError("execution matrix behavior slice needs an id")
        identifier = behavior_slice["id"].strip()
        if not identifier:
            raise ValueError("execution matrix behavior slice id cannot be empty")
        identifiers.append(identifier)
    return tuple(identifiers)


def _matrix_slice_ids(matrix: Mapping[str, object]) -> tuple[str, ...]:
    tasks = matrix.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError("execution matrix tasks must be a list")
    identifiers: list[str] = []
    seen: set[str] = set()
    for task in tasks:
        if not isinstance(task, dict):
            continue
        for identifier in _task_slice_ids(task):
            if identifier in seen:
                raise ValueError(f"execution matrix behavior slice id is duplicated: {identifier}")
            seen.add(identifier)
            identifiers.append(identifier)
    return tuple(identifiers)


def _matrix_slice_paths(matrix: Mapping[str, object]) -> dict[str, tuple[str, ...]]:
    paths: dict[str, tuple[str, ...]] = {}
    tasks = matrix.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError("execution matrix tasks must be a list")
    for task in tasks:
        if not isinstance(task, dict):
            continue
        for behavior_slice in task.get("behavior_slices", []):
            if not isinstance(behavior_slice, dict) or not isinstance(behavior_slice.get("id"), str):
                continue
            declared = behavior_slice.get("paths", [])
            if not isinstance(declared, list):
                raise ValueError(f"behavior slice {behavior_slice['id']} paths must be a list")
            if not declared:
                raise ValueError(f"behavior slice {behavior_slice['id']} paths cannot be empty")
            safe_paths = _safe_paths(
                path for path in declared if isinstance(path, str)
            )
            if not any(
                path.endswith(".java")
                and not any(marker in f"/{path}" for marker in ("/src/test/", "/test/"))
                for path in safe_paths
            ):
                raise ValueError(f"behavior slice {behavior_slice['id']} needs a production Java path")
            paths[behavior_slice["id"].strip()] = safe_paths
    return paths


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _git(repo: Path, arguments: Sequence[str]) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *arguments], capture_output=True, text=True, check=False
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or "git command failed")
    return completed.stdout.strip()


def _safe_paths(paths: Iterable[str]) -> tuple[str, ...]:
    normalized = []
    for path in paths:
        candidate = PurePosixPath(path.replace("\\", "/"))
        if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
            raise ValueError(f"runtime path must be repository-relative: {path}")
        if is_pretty_tmp_path(candidate.as_posix()):
            raise ValueError(f"runtime path cannot be Pretty temporary evidence: {path}")
        normalized.append(candidate.as_posix())
    return tuple(sorted(set(normalized)))


def _path_digest(repo: Path, relative_path: str) -> str:
    path = repo / relative_path
    if not path.exists():
        return MISSING
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"runtime path must be a regular file: {relative_path}")
    return _sha256_file(path)


def _dirty_runtime_paths(repo: Path, paths: Sequence[str]) -> list[str]:
    dirty = []
    for path in paths:
        status = _git(repo, ["status", "--porcelain", "--untracked-files=all", "--", path])
        if status:
            dirty.append(path)
    return dirty


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_bytes(_canonical(payload) + b"\n")
    os.replace(temporary, path)


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"state must contain a JSON object: {path}")
    return payload


def _validate_state_location(state_path: Path, state: Mapping[str, object]) -> Path:
    run_dir = state_path.resolve().parent
    topic_dir = topic_dir_for_run(run_dir)
    if state_path.name not in STATE_NAMES or state.get("topic") != topic_dir.name:
        raise ValueError(f"Apply state must be {run_dir / STATE_NAME}")
    stored_name = state.get("state_file")
    if stored_name is not None and stored_name != state_path.name:
        raise ValueError("Apply state file name does not match its file location")
    stored_run = str(state.get("run_dir", ""))
    if Path(stored_run).name != run_dir.name:
        raise ValueError("Apply state run directory does not match its file location")
    return topic_dir


def _validate_gate_locations(paths: ObjectiveGatePaths) -> Path:
    candidates = (paths.quality, paths.build, paths.tests, paths.coverage)
    run_dirs = {path.resolve().parent for path in candidates}
    if len(run_dirs) != 1:
        raise ValueError("objective Gate evidence must share one topic tmp run directory")
    run_dir = next(iter(run_dirs))
    for path in candidates:
        validate_artifact_path(run_dir, path)
    return topic_dir_for_run(run_dir)


def _register_artifact(state_path: Path, state: dict[str, object], artifact_path: Path) -> dict[str, object]:
    run_dir = state_path.resolve().parent
    validate_artifact_path(run_dir, artifact_path)
    artifacts = registered_artifact_names(state.get("temporary_artifacts", []))
    if artifact_path.name not in artifacts:
        if artifact_path.exists() or artifact_path.is_symlink():
            raise ValueError(f"拒绝登记已存在的非本次运行产物：{artifact_path.name}")
        artifacts.add(artifact_path.name)
        state["temporary_artifacts"] = sorted(artifacts)
        return _save_state(state_path, state)
    return state


def register_apply_artifact(state_path: Path, artifact_path: Path) -> dict[str, object]:
    state = _load_json(state_path)
    _validate_state_location(state_path, state)
    errors = _state_integrity_errors(state)
    if state.get("status") != "in_progress":
        errors.append("Apply state is not in progress")
    if errors:
        raise ValueError("; ".join(errors))
    return _register_artifact(state_path, state, artifact_path)


def _assert_apply_cleanup(state_path: Path, state: Mapping[str, object]) -> None:
    _validate_state_location(state_path, state)
    artifacts = registered_artifact_names(state.get("temporary_artifacts", []))
    assert_cleanup_scope(state_path.resolve().parent, state_path.name, artifacts)


def _cleanup_apply_state(state_path: Path, state: Mapping[str, object]) -> tuple[str, ...]:
    topic_dir = _validate_state_location(state_path, state)
    artifacts = registered_artifact_names(state.get("temporary_artifacts", []))
    return cleanup_registered_run(topic_dir, state_path.parent, state_path.name, artifacts)


def cleanup_apply(state_path: Path) -> tuple[str, ...]:
    state = _load_json(state_path)
    _validate_state_location(state_path, state)
    integrity_errors = _state_integrity_errors(state)
    if integrity_errors:
        raise ValueError("; ".join(integrity_errors))
    _assert_apply_cleanup(state_path, state)
    return _cleanup_apply_state(state_path, state)


def _state_hash(state: Mapping[str, object]) -> str:
    payload = {key: value for key, value in state.items() if key not in {"updated_at", "state_sha256"}}
    return _sha256_bytes(_canonical(payload))


def _state_errors(state: Mapping[str, object]) -> list[str]:
    required = (
        "schema_version", "mode", "topic", "start_head", "design_sha256",
        "execution_matrix_sha256", "contract_preflight", "registered_runtime_paths",
        "coverage_policy", "slice_order", "active_slice", "slice_coverage",
        "slice_runtime_paths",
        "temporary_artifacts", "run_dir", "status",
    )
    errors = [f"state missing {field}" for field in required if field not in state]
    if state.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"state schema_version must be {SCHEMA_VERSION}")
    return errors


def _state_integrity_errors(state: Mapping[str, object]) -> list[str]:
    errors = _state_errors(state)
    if state.get("state_sha256") != _state_hash(state):
        errors.append("Apply state integrity hash does not match")
    return errors


def start_apply(request: ApplyStartRequest) -> dict[str, object]:
    repo = request.repo.resolve()
    design = request.design.resolve()
    matrix = request.execution_matrix.resolve()
    topic_dir = topic_dir_for_document(design)
    run_dir = validate_run_dir(topic_dir, matrix.parent)
    if request.topic != topic_dir.name:
        raise ValueError(f"topic does not match Design directory: {request.topic}")
    if request.state_path.resolve().parent != run_dir or request.state_path.name not in STATE_NAMES:
        raise ValueError(f"Apply state must be {run_dir / STATE_NAME}")
    if matrix.name != MATRIX_NAME:
        raise ValueError(f"execution matrix must be {run_dir / MATRIX_NAME}")
    assert_cleanup_scope(run_dir, request.state_path.name, [MATRIX_NAME])
    paths = _safe_paths(request.runtime_paths)
    if request.state_path.exists():
        raise ValueError(f"Apply state already exists: {request.state_path}")
    if not design.is_file() or not matrix.is_file():
        raise ValueError("Apply requires readable Design and execution matrix")
    design_text = design.read_text(encoding="utf-8")
    matrix_payload = _load_json(matrix)
    preflight_errors = contract_preflight_errors(design_text, matrix_payload)
    if preflight_errors:
        raise ValueError(f"Design contract is not executable: {'; '.join(preflight_errors)}")
    coverage_policy = _coverage_policy(matrix_payload)
    slice_order = _matrix_slice_ids(matrix_payload)
    slice_runtime_paths = _matrix_slice_paths(matrix_payload)
    dirty = _dirty_runtime_paths(repo, paths)
    if dirty:
        raise ValueError(f"runtime paths must be clean: {', '.join(dirty)}")
    state: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "mode": "apply",
        "topic": request.topic,
        "run_id": run_dir.name,
        "run_dir": str(run_dir.relative_to(repo)),
        "state_file": request.state_path.name,
        "start_head": _git(repo, ["rev-parse", "HEAD"]),
        "design_sha256": _sha256_file(design),
        "execution_matrix_sha256": _sha256_file(matrix),
        "contract_preflight": contract_preflight_summary(),
        "coverage_policy": coverage_policy,
        "slice_order": list(slice_order),
        "active_slice": slice_order[0] if slice_order else None,
        "slice_coverage": {},
        "slice_runtime_paths": {
            slice_id: list(slice_runtime_paths.get(slice_id, ()))
            for slice_id in slice_order
        },
        "registered_runtime_paths": {path: _path_digest(repo, path) for path in paths},
        "temporary_artifacts": [MATRIX_NAME],
        "phase": "writing",
        "status": "in_progress",
        "created_at": _now(),
        "updated_at": _now(),
    }
    state["state_sha256"] = _state_hash(state)
    _write_json(request.state_path, state)
    return state


def checkpoint_apply(state_path: Path, repo: Path) -> dict[str, object]:
    state = _load_json(state_path)
    _validate_state_location(state_path, state)
    errors = _state_integrity_errors(state)
    if state.get("status") != "in_progress" or state.get("phase") != "writing":
        errors.append("Apply state is not writable")
    if errors:
        raise ValueError("; ".join(errors))
    registered = state["registered_runtime_paths"]
    if not isinstance(registered, dict):
        raise ValueError("registered_runtime_paths must be an object")
    active_slice = state.get("active_slice")
    slice_paths = state.get("slice_runtime_paths", {})
    if active_slice is not None:
        if not isinstance(slice_paths, dict) or not isinstance(slice_paths.get(active_slice), list):
            raise ValueError(f"Apply state has no runtime path scope for active slice {active_slice}")
        changed_paths = [
            path for path, expected in registered.items()
            if _path_digest(repo, str(path)) != expected
        ]
        allowed_paths = set(slice_paths[active_slice])
        outside_paths = sorted(set(changed_paths) - allowed_paths)
        if outside_paths:
            raise ValueError(
                "runtime paths changed outside active behavior slice "
                f"{active_slice}: {', '.join(outside_paths)}"
            )
    elif state.get("slice_order"):
        changed_paths = [
            path for path, expected in registered.items()
            if _path_digest(repo, str(path)) != expected
        ]
        if changed_paths:
            raise ValueError("all behavior slices are closed; runtime paths are frozen")
    state["registered_runtime_paths"] = {
        path: _path_digest(repo, path) for path in sorted(registered)
    }
    state["updated_at"] = _now()
    state["state_sha256"] = _state_hash(state)
    _write_json(state_path, state)
    return state


def _save_state(state_path: Path, state: dict[str, object]) -> dict[str, object]:
    state["updated_at"] = _now()
    state["state_sha256"] = _state_hash(state)
    _write_json(state_path, state)
    return state


def _slice_gate_errors(state: Mapping[str, object]) -> list[str]:
    """Ensure every declared behavior slice has a passing, bound coverage receipt."""
    order = state.get("slice_order", [])
    coverage = state.get("slice_coverage", {})
    if not isinstance(order, list) or any(not isinstance(item, str) for item in order):
        return ["Apply state slice_order must be a string list"]
    if not isinstance(coverage, dict):
        return ["Apply state slice_coverage must be an object"]
    errors: list[str] = []
    for slice_id in order:
        receipt = coverage.get(slice_id)
        if not isinstance(receipt, dict):
            errors.append(f"behavior slice {slice_id} has no coverage evidence")
            continue
        if receipt.get("status") not in {"pass"} or receipt.get("passed") is not True:
            errors.append(f"behavior slice {slice_id} coverage Gate did not pass")
    active = state.get("active_slice")
    if active is not None:
        errors.append(f"behavior slice {active} is not coverage-closed")
    return errors


def _slice_identity_errors(
    state: Mapping[str, object], design: Path, coverage: Mapping[str, object], slice_id: str
) -> list[str]:
    errors: list[str] = []
    if coverage.get("scope") != "slice":
        errors.append("slice coverage evidence must declare scope=slice")
    if coverage.get("slice_id") != slice_id:
        errors.append("slice coverage evidence has the wrong slice_id")
    if coverage.get("start_head") != state.get("start_head"):
        errors.append("slice coverage evidence does not match Apply starting HEAD")
    if coverage.get("design_sha256") != _sha256_file(design):
        errors.append("slice coverage evidence does not match the current Design")
    return errors


def _slice_threshold_errors(state: Mapping[str, object], coverage: Mapping[str, object]) -> list[str]:
    policy = state.get("coverage_policy")
    if not isinstance(policy, dict):
        return ["Apply state is missing coverage_policy"]
    errors = []
    for field in ("line_threshold", "branch_threshold"):
        if coverage.get(field) != policy.get(field):
            errors.append(f"slice coverage {field} does not match Apply policy")
    line = coverage.get("line_percentage")
    branch = coverage.get("branch_percentage")
    line_threshold = float(policy.get("line_threshold", DEFAULT_LINE_THRESHOLD))
    branch_threshold = float(policy.get("branch_threshold", DEFAULT_BRANCH_THRESHOLD))
    if not isinstance(line, (int, float)) or float(line) < line_threshold:
        errors.append(f"slice coverage line percentage is below {line_threshold:g}%")
    if branch is not None and (not isinstance(branch, (int, float)) or float(branch) < branch_threshold):
        errors.append(f"slice coverage branch percentage is below {branch_threshold:g}%")
    return errors


def _slice_coverage_errors(
    state: Mapping[str, object], design: Path, coverage_path: Path, slice_id: str
) -> list[str]:
    order = state.get("slice_order")
    if not isinstance(order, list) or slice_id not in order:
        return [f"unknown behavior slice: {slice_id}"]
    errors = []
    active = state.get("active_slice")
    if active != slice_id:
        errors.append(f"behavior slice {slice_id} cannot close before active slice {active}")
    coverage = _load_json(coverage_path)
    if coverage.get("evidence_sha256") != evidence_sha256(coverage):
        errors.append("slice coverage evidence integrity hash does not match")
    errors.extend(_slice_identity_errors(state, design, coverage, slice_id))
    if coverage.get("status") != "pass" or coverage.get("passed") is not True:
        errors.append("slice coverage Gate did not pass")
    if not isinstance(coverage.get("changed_files"), int) or coverage["changed_files"] < 1:
        errors.append("slice coverage must include changed production files")
    if not isinstance(coverage.get("changed_lines"), int) or coverage["changed_lines"] < 1:
        errors.append("slice coverage must include changed production lines")
    if coverage.get("missing_sources") not in ([], ()):
        errors.append("slice coverage has missing JaCoCo sources")
    errors.extend(_slice_threshold_errors(state, coverage))
    if coverage_path.name not in registered_artifact_names(state.get("temporary_artifacts", [])):
        errors.append(f"slice coverage artifact is not registered: {coverage_path.name}")
    return errors


def _slice_source_binding_errors(repo: Path, coverage_path: Path) -> list[str]:
    coverage = _load_json(coverage_path)
    hashes = coverage.get("source_sha256")
    if not isinstance(hashes, dict):
        return ["slice coverage evidence needs source_sha256"]
    errors = []
    for relative_path, expected in hashes.items():
        if not isinstance(relative_path, str) or not isinstance(expected, str):
            errors.append("slice coverage source_sha256 must map paths to hashes")
            continue
        try:
            _safe_paths((relative_path,))
            actual = _path_digest(repo, relative_path)
        except ValueError as error:
            errors.append(str(error))
            continue
        if actual != expected:
            errors.append(f"slice coverage source changed after report: {relative_path}")
    return errors


def _validated_slice_request(
    request: SliceCoverageRequest,
) -> tuple[dict[str, object], Path]:
    state_path = request.state_path
    coverage_path = request.coverage_path.resolve()
    design = request.design.resolve()
    state = _load_json(state_path)
    _validate_state_location(state_path, state)
    errors = _state_integrity_errors(state)
    if state.get("status") != "in_progress" or state.get("phase") != "writing":
        errors.append("Apply state is not writable")
    errors.extend(_registered_path_errors(state, request.repo))
    validate_artifact_path(state_path.resolve().parent, coverage_path)
    if not coverage_path.is_file():
        errors.append(f"slice coverage evidence does not exist: {coverage_path}")
    if not errors:
        errors.extend(_slice_coverage_errors(state, design, coverage_path, request.slice_id))
        errors.extend(_slice_source_binding_errors(request.repo, coverage_path))
    if errors:
        raise ValueError("; ".join(sorted(set(errors))))
    return state, coverage_path


def record_slice_coverage(request: SliceCoverageRequest) -> dict[str, object]:
    """Close the active behavior slice only after a fresh passing coverage receipt."""
    state, coverage_path = _validated_slice_request(request)
    coverage = _load_json(coverage_path)
    order = state["slice_order"]
    index = order.index(request.slice_id)
    receipts = dict(state.get("slice_coverage", {}))
    receipts[request.slice_id] = {
        "status": coverage["status"],
        "passed": True,
        "line_percentage": coverage.get("line_percentage"),
        "branch_percentage": coverage.get("branch_percentage"),
        "coverage_evidence": coverage_path.name,
        "evidence_sha256": coverage["evidence_sha256"],
        "candidate_sha256": coverage.get("candidate_sha256"),
    }
    state["slice_coverage"] = receipts
    state["active_slice"] = order[index + 1] if index + 1 < len(order) else None
    return _save_state(request.state_path, state)


def freeze_apply(request: ApplyFreezeRequest) -> dict[str, object]:
    errors = resume_apply(
        request.state_path,
        request.repo,
        request.design,
        request.execution_matrix,
    )
    if errors:
        raise ValueError("; ".join(errors))
    state = _load_json(request.state_path)
    if state.get("phase") != "writing":
        raise ValueError("Apply candidate is already frozen")
    slice_errors = _slice_gate_errors(state)
    if slice_errors:
        raise ValueError("; ".join(slice_errors))
    if not request.candidate_sha256:
        raise ValueError("frozen Apply candidate needs candidate_sha256")
    state["candidate_sha256"] = request.candidate_sha256
    state["phase"] = "frozen"
    state["frozen_at"] = _now()
    return _save_state(request.state_path, state)


def start_review(state_path: Path) -> dict[str, object]:
    state = _load_json(state_path)
    _validate_state_location(state_path, state)
    errors = _state_integrity_errors(state)
    if state.get("status") != "in_progress":
        errors.append("Apply state is not in progress")
    if state.get("phase") != "frozen":
        errors.append("Apply candidate must be frozen before Review starts")
    if errors:
        raise ValueError("; ".join(errors))
    if not isinstance(state.get("objective_gate"), dict):
        raise ValueError("objective Gate must complete before final Review starts")
    request = {
        "run_id": state["run_id"],
        "candidate_sha256": state["candidate_sha256"],
        "pre_review_gate": state["objective_gate"],
        "review_session_id": uuid.uuid4().hex,
        "reviewer_context_id": uuid.uuid4().hex,
        "history": "none",
    }
    state["active_review"] = request
    state["phase"] = "reviewing"
    _save_state(state_path, state)
    return request


def _objective_gate_errors(gate: Mapping[str, object]) -> list[str]:
    required = (
        "quality_candidate_sha256",
        "build_candidate_sha256",
        "test_evidence_sha256",
        "coverage_evidence_sha256",
    )
    return [
        f"objective Gate needs {field}"
        for field in required
        if not isinstance(gate.get(field), str) or not str(gate[field]).strip()
    ]


def _build_candidate_sha256(build: Mapping[str, object]) -> str:
    payload = {key: value for key, value in build.items() if key != "candidate_sha256"}
    return _sha256_bytes(_canonical(payload))


def objective_gate_from_files(
    paths: ObjectiveGatePaths,
    candidate_sha256: str,
) -> dict[str, str]:
    _validate_gate_locations(paths)
    quality = _load_json(paths.quality)
    build = _load_json(paths.build)
    tests = _load_json(paths.tests)
    coverage = _load_json(paths.coverage)
    errors = _objective_evidence_errors(quality, build, tests, coverage, candidate_sha256)
    if errors:
        raise ValueError("; ".join(errors))
    return {
        "quality_candidate_sha256": str(quality["candidate_sha256"]),
        "build_candidate_sha256": str(build["candidate_sha256"]),
        "test_evidence_sha256": str(tests["evidence_sha256"]),
        "coverage_evidence_sha256": str(coverage["evidence_sha256"]),
    }


def _objective_evidence_errors(
    quality: Mapping[str, object],
    build: Mapping[str, object],
    tests: Mapping[str, object],
    coverage: Mapping[str, object],
    candidate_sha256: str,
) -> list[str]:
    errors = []
    if quality.get("mode") != "scan_only" or quality.get("passed") is not True:
        errors.append("objective quality scan must pass in scan_only mode")
    if quality.get("candidate_sha256") != candidate_sha256:
        errors.append("objective quality scan does not match the frozen candidate")
    for label, payload in (("quality", quality), ("test", tests), ("coverage", coverage)):
        if payload.get("evidence_sha256") != evidence_sha256(payload):
            errors.append(f"{label} evidence integrity hash does not match")
    if build.get("candidate_sha256") != _build_candidate_sha256(build):
        errors.append("build candidate hash does not match")
    if tests.get("quality_candidate_sha256") != candidate_sha256:
        errors.append("test evidence does not match the frozen candidate")
    if coverage.get("quality_candidate_sha256") != candidate_sha256:
        errors.append("coverage evidence does not match the frozen candidate")
    if coverage.get("scope") == "slice":
        errors.append("final objective Gate cannot use slice coverage evidence")
    if tests.get("passed") is not True:
        errors.append("test execution Gate did not pass")
    if coverage.get("status") not in {"pass", "not_applicable"}:
        errors.append("coverage Gate did not pass")
    return errors


def _registered_path_errors(state: Mapping[str, object], repo: Path) -> list[str]:
    registered = state.get("registered_runtime_paths")
    if not isinstance(registered, dict):
        return ["registered_runtime_paths must be an object"]
    return [
        f"frozen runtime path changed: {path}"
        for path, expected in registered.items()
        if _path_digest(repo, str(path)) != expected
    ]


def record_objective_gate(
    state_path: Path,
    repo: Path,
    candidate_sha256: str,
    gate: Mapping[str, object],
) -> dict[str, object]:
    state = _load_json(state_path)
    _validate_state_location(state_path, state)
    errors = _state_integrity_errors(state)
    errors.extend(_objective_gate_errors(gate))
    errors.extend(_registered_path_errors(state, repo))
    if state.get("phase") != "frozen":
        errors.append("Apply candidate is not frozen")
    if state.get("candidate_sha256") != candidate_sha256:
        errors.append("objective Gate does not match the frozen candidate")
    if errors:
        raise ValueError("; ".join(errors))
    state["objective_gate"] = dict(gate)
    state["gate_completed_at"] = _now()
    return _save_state(state_path, state)


def _review_receipt_errors(state: Mapping[str, object], review: Mapping[str, object]) -> list[str]:
    active = state.get("active_review")
    if not isinstance(active, dict):
        return ["Apply Review was not started"]
    binding_fields = ("run_id", "review_session_id", "candidate_sha256")
    errors = [
        "review receipt does not match the Apply run"
        for field in binding_fields
        if review.get(field) != active.get(field)
    ]
    if review.get("independent") is not True or not review.get("reviewer"):
        errors.append("review receipt must identify an independent reviewer")
    if review.get("blocking_findings") != []:
        errors.append("review receipt contains unresolved blocking findings")
    if review.get("pre_review_gate") != state.get("objective_gate"):
        errors.append("review receipt does not match the objective Gate")
    return sorted(set(errors))


def complete_apply(
    state_path: Path,
    repo: Path,
    review: Mapping[str, object],
    completion_path: Path,
) -> dict[str, object]:
    state = _load_json(state_path)
    _validate_state_location(state_path, state)
    errors = _completion_errors(state, repo, review)
    if errors:
        raise ValueError("; ".join(errors))
    completion = _completion_payload(state, review)
    _prepare_completion_artifact(state_path, state, completion_path)
    _write_json(completion_path, completion)
    _cleanup_apply_state(state_path, state)
    return completion


def _completion_errors(
    state: Mapping[str, object],
    repo: Path,
    review: Mapping[str, object],
) -> list[str]:
    errors = _state_integrity_errors(state)
    errors.extend(_registered_path_errors(state, repo))
    errors.extend(_review_receipt_errors(state, review))
    if not isinstance(state.get("objective_gate"), dict):
        errors.append("objective Gate has not completed")
    if state.get("status") != "in_progress" or state.get("phase") != "reviewing":
        errors.append("Apply state is not in final Review phase")
    return errors


def _completion_payload(state: Mapping[str, object], review: Mapping[str, object]) -> dict[str, object]:
    return {
        "status": "completed",
        "run_id": state["run_id"],
        "candidate_sha256": state["candidate_sha256"],
        "review_session_id": review["review_session_id"],
        "reviewer": review["reviewer"],
        "objective_gate": state["objective_gate"],
        "completed_at": _now(),
    }


def _prepare_completion_artifact(
    state_path: Path,
    state: dict[str, object],
    completion_path: Path,
) -> None:
    validate_artifact_path(state_path.parent, completion_path)
    artifacts = registered_artifact_names(state.get("temporary_artifacts", []))
    if completion_path.name not in artifacts and completion_path.exists():
        raise ValueError(f"拒绝覆盖已存在的完成产物：{completion_path.name}")
    assert_cleanup_scope(state_path.resolve().parent, state_path.name, [*artifacts, completion_path.name])
    _register_artifact(state_path, state, completion_path)


def resume_apply(state_path: Path, repo: Path, design: Path, execution_matrix: Path) -> list[str]:
    try:
        state = _load_json(state_path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return [str(error)]
    errors = _state_errors(state)
    try:
        _validate_state_location(state_path, state)
        topic_dir = topic_dir_for_document(design)
        run_dir = validate_run_dir(topic_dir, execution_matrix.parent)
        if run_dir != state_path.resolve().parent:
            errors.append("execution matrix and Apply state must share one topic tmp run directory")
        if execution_matrix.name != MATRIX_NAME:
            errors.append(f"execution matrix must be named {MATRIX_NAME}")
    except ValueError as error:
        errors.append(str(error))
    if state.get("state_sha256") != _state_hash(state):
        errors.append("Apply state integrity hash does not match")
    if state.get("status") != "in_progress":
        errors.append("Apply state is not resumable")
    try:
        if state.get("start_head") != _git(repo, ["rev-parse", "HEAD"]):
            errors.append("Apply starting HEAD changed")
        if state.get("design_sha256") != _sha256_file(design):
            errors.append("Design changed since Apply started")
        if state.get("execution_matrix_sha256") != _sha256_file(execution_matrix):
            errors.append("execution matrix changed since Apply started")
        registered = state.get("registered_runtime_paths", {})
        if isinstance(registered, dict):
            for path, expected in registered.items():
                if _path_digest(repo, str(path)) != expected:
                    errors.append(f"registered runtime path changed: {path}")
        else:
            errors.append("registered_runtime_paths must be an object")
    except (OSError, RuntimeError, ValueError) as error:
        errors.append(str(error))
    return sorted(set(errors))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    start = subparsers.add_parser("start")
    start.add_argument("--repo", type=Path, default=Path("."))
    start.add_argument("--topic", required=True)
    start.add_argument("--design", type=Path, required=True)
    start.add_argument("--execution-matrix", type=Path, required=True)
    start.add_argument("--state", type=Path, required=True)
    start.add_argument("--runtime-path", action="append", default=[])
    checkpoint = subparsers.add_parser("checkpoint")
    checkpoint.add_argument("--state", type=Path, required=True)
    checkpoint.add_argument("--repo", type=Path, default=Path("."))
    resume = subparsers.add_parser("resume")
    resume.add_argument("--state", type=Path, required=True)
    resume.add_argument("--repo", type=Path, default=Path("."))
    resume.add_argument("--design", type=Path, required=True)
    resume.add_argument("--execution-matrix", type=Path, required=True)
    register = subparsers.add_parser("register", help="register one run artifact before creating it")
    register.add_argument("--state", type=Path, required=True)
    register.add_argument("--artifact", type=Path, required=True)
    slice_coverage = subparsers.add_parser(
        "slice-coverage", help="close the active behavior slice with passing coverage evidence"
    )
    slice_coverage.add_argument("--state", type=Path, required=True)
    slice_coverage.add_argument("--repo", type=Path, default=Path("."))
    slice_coverage.add_argument("--design", type=Path, required=True)
    slice_coverage.add_argument("--slice-id", required=True)
    slice_coverage.add_argument("--coverage", type=Path, required=True)
    cleanup = subparsers.add_parser("cleanup", help="remove only artifacts registered by this Apply run")
    cleanup.add_argument("--state", type=Path, required=True)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(arguments)
    try:
        if args.command == "start":
            print(json.dumps(start_apply(ApplyStartRequest(
                args.repo, args.topic, args.design, args.execution_matrix, args.state, args.runtime_path,
            )), ensure_ascii=False, indent=2))
        elif args.command == "checkpoint":
            print(json.dumps(checkpoint_apply(args.state, args.repo), ensure_ascii=False, indent=2))
        elif args.command == "resume":
            errors = resume_apply(args.state, args.repo, args.design, args.execution_matrix)
            for error in errors:
                print(f"error: {error}", file=sys.stderr)
            return 0 if not errors else 1
        elif args.command == "register":
            state = register_apply_artifact(args.state, args.artifact)
            print(json.dumps(state, ensure_ascii=False, indent=2))
        elif args.command == "slice-coverage":
            state = record_slice_coverage(
                SliceCoverageRequest(
                    args.state,
                    args.repo,
                    args.design,
                    args.slice_id,
                    args.coverage,
                )
            )
            print(json.dumps(state, ensure_ascii=False, indent=2))
        else:
            removed = cleanup_apply(args.state)
            print(json.dumps({"status": "cleaned", "removed": removed}, ensure_ascii=False, indent=2))
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"Apply run failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
