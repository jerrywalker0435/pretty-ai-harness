#!/usr/bin/env python3
"""Verify an Apply increment against Design, its execution matrix, and review evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping, Sequence


COMMON_SCRIPTS = Path(__file__).resolve().parents[2] / "pretty-common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

from quality_contract_gate import (  # type: ignore[import-not-found]
    QualityFinding,
    candidate_sha256,
    load_review_evidence,
    parse_touched_java_lines,
    review_evidence_errors,
    scan_java_source,
)
from quality_registry import RISK_OWNERS, RULES  # type: ignore[import-not-found]
from evidence_binding import evidence_sha256  # type: ignore[import-not-found]
from execution_contract import contract_preflight_errors


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _run_git(repo: Path, arguments: Sequence[str]) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode:
        detail = completed.stderr.strip() or "git command failed"
        raise RuntimeError(f"git {' '.join(arguments)}: {detail}")
    return completed.stdout


def _is_test_path(path: str) -> bool:
    normalized = f"/{path.replace(chr(92), '/').lower().lstrip('/')}"
    return "/src/test/" in normalized or normalized.startswith("/test/")


def _is_explanatory_path(path: str) -> bool:
    normalized = path.replace(chr(92), "/").lower().lstrip("/")
    parts = PurePosixPath(normalized).parts
    name = parts[-1] if parts else ""
    runtime_names = {
        "pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle",
        "settings.gradle.kts", "gradle.properties", "mvnw", "mvnw.cmd",
    }
    runtime_suffixes = {
        ".java", ".kt", ".kts", ".groovy", ".scala", ".xml", ".sql",
        ".properties", ".yml", ".yaml", ".json", ".conf", ".toml",
    }
    runtime_parts = {"src", "test", "tests", "resources", "migration", "migrations"}
    if name in runtime_names or runtime_parts.intersection(parts):
        return False
    if PurePosixPath(name).suffix in runtime_suffixes:
        return False
    return (
        normalized.startswith(("docs/", ".code-review/"))
        or (parts and parts[0] in {"context", "contexts", "adr", "adrs"})
        or name in {"agents.md", "business-map.md", ".execution-state.json"}
        or PurePosixPath(name).suffix in {".md", ".adoc", ".rst"}
    )


def _read_manifest(path: Path) -> dict[str, frozenset[int]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("changed manifest must be a JSON object")
    changed = {}
    for source_path, line_numbers in payload.items():
        if not isinstance(source_path, str) or not isinstance(line_numbers, list):
            raise ValueError("changed manifest entries must map paths to line lists")
        candidate = PurePosixPath(source_path)
        if candidate.is_absolute() or ".." in candidate.parts or "\\" in source_path:
            raise ValueError(f"changed manifest path must be repository-relative: {source_path}")
        if any(not isinstance(line, int) or line < 1 for line in line_numbers):
            raise ValueError(f"invalid changed line for {source_path}")
        if source_path.endswith(".java") and not line_numbers:
            raise ValueError(f"changed manifest Java entry must contain changed lines: {source_path}")
        changed[source_path] = frozenset(line_numbers)
    return changed


def _untracked_paths(repo: Path) -> set[str]:
    output = _run_git(repo, ["ls-files", "--others", "--exclude-standard"])
    return {path for path in output.splitlines() if path}


def _untracked_java(repo: Path, paths: set[str] | None = None) -> dict[str, frozenset[int]]:
    changed = {}
    for relative_path in paths if paths is not None else _untracked_paths(repo):
        if not relative_path.endswith(".java"):
            continue
        line_count = len((repo / relative_path).read_text(encoding="utf-8").splitlines())
        changed[relative_path] = frozenset(range(1, line_count + 1))
    return changed


def _changed_scope(
    repo: Path,
    base: str,
) -> tuple[dict[str, frozenset[int]], set[str], str]:
    diff = _run_git(repo, ["diff", "--no-ext-diff", "--unified=0", base, "--"])
    changed_paths = set(_run_git(repo, ["diff", "--name-only", base, "--"]).splitlines())
    untracked_paths = _untracked_paths(repo)
    changed_paths.update(untracked_paths)
    changed_paths = {path for path in changed_paths if not _is_explanatory_path(path)}
    java_changed = parse_touched_java_lines(diff)
    java_changed.update(_untracked_java(repo, untracked_paths))
    java_changed = {path: lines for path, lines in java_changed.items() if path in changed_paths}
    return java_changed, changed_paths, diff


def _manifest_scope_errors(
    manifest: Path | None,
    actual_java: Mapping[str, frozenset[int]],
    actual_paths: set[str],
) -> list[str]:
    if manifest is None:
        return []
    declared = _read_manifest(manifest)
    declared_paths = {path for path in declared if not _is_explanatory_path(path)}
    errors = _manifest_path_errors(declared_paths, actual_java, actual_paths)
    errors.extend(_manifest_line_errors(declared, actual_java))
    return errors


def _manifest_path_errors(
    declared_paths: set[str],
    actual_java: Mapping[str, frozenset[int]],
    actual_paths: set[str],
) -> list[str]:
    missing_java = sorted(set(actual_java) - declared_paths)
    extra = sorted(declared_paths - actual_paths)
    errors = []
    if missing_java:
        errors.append(f"changed manifest omits Java paths from Git diff: {missing_java}")
    if extra:
        errors.append(f"changed manifest contains paths outside Git diff: {extra}")
    return errors


def _manifest_line_errors(
    declared: Mapping[str, frozenset[int]],
    actual_java: Mapping[str, frozenset[int]],
) -> list[str]:
    errors = []
    for path, actual_lines in sorted(actual_java.items()):
        declared_lines = declared.get(path)
        if declared_lines is not None and declared_lines != actual_lines:
            errors.append(
                f"changed manifest lines do not match Git diff for {path}: "
                f"{sorted(declared_lines)} != {sorted(actual_lines)}"
            )
    return errors


def _matrix_paths(matrix: Mapping[str, object], design_text: str) -> tuple[set[str], list[str]]:
    tasks = matrix.get("tasks")
    if not isinstance(tasks, list):
        return set(), ["execution matrix tasks must be a list"]
    expected_tasks = set(re.findall(r"^###\s+(TASK-\d{3})[：:]", design_text, re.MULTILINE))
    actual_tasks, paths, errors = set(), set(), []
    for index, task in enumerate(tasks):
        if not isinstance(task, dict) or not isinstance(task.get("id"), str):
            errors.append(f"execution matrix task {index} needs an id")
            continue
        actual_tasks.add(task["id"])
        for field in ("production_files", "test_files", "supporting_files"):
            declared_paths = task.get(field, [])
            if not isinstance(declared_paths, list) or any(not isinstance(path, str) for path in declared_paths):
                errors.append(f"execution matrix {task['id']} {field} must be a string list")
                continue
            for declared_path in declared_paths:
                candidate = PurePosixPath(declared_path)
                if candidate.is_absolute() or ".." in candidate.parts or "\\" in declared_path:
                    errors.append(f"execution matrix path must be repository-relative: {declared_path}")
                else:
                    paths.add(declared_path)
        errors.extend(_matrix_behavior_errors(task, index))
    if actual_tasks != expected_tasks:
        errors.append(f"execution matrix TASK set must match Design: {sorted(expected_tasks)}")
    return paths, errors


def _matrix_behavior_errors(task: Mapping[str, object], index: int) -> list[str]:
    java_paths = _matrix_java_paths(task)
    slices = task.get("behavior_slices")
    if not isinstance(slices, list):
        return [f"execution matrix task {index} behavior_slices must be a list"]
    if not slices:
        reason = task.get("non_behavior_reason")
        return [] if isinstance(reason, str) and reason.strip() else [
            f"execution matrix task {index} without behavior_slices needs non_behavior_reason"
        ]
    if not java_paths:
        return [f"execution matrix task {index} has behavior_slices without Java files"]
    errors = []
    for slice_index, behavior_slice in enumerate(slices):
        errors.extend(_behavior_slice_errors(behavior_slice, index, slice_index))
    return errors


def _behavior_slice_errors(
    behavior_slice: object,
    task_index: int,
    slice_index: int,
) -> list[str]:
    prefix = f"execution matrix task {task_index} behavior slice {slice_index}"
    if not isinstance(behavior_slice, dict):
        return [f"{prefix} must be an object"]
    errors = []
    if not isinstance(behavior_slice.get("id"), str) or not behavior_slice["id"].strip():
        errors.append(f"{prefix} needs an id")
    if not isinstance(behavior_slice.get("test_entry"), str) or not behavior_slice["test_entry"].strip():
        errors.append(f"{prefix} needs a test_entry")
    list_fields = (
        "paths", "production_symbols", "input_invariants", "boundary_substitutes",
        "result_assertions", "nearest_neighbors", "coverage_obligations",
        "resolver_rules", "depends_on",
    )
    for field in list_fields:
        values = behavior_slice.get(field)
        if not isinstance(values, list) or any(not isinstance(value, str) or not value.strip() for value in values):
            errors.append(f"{prefix} {field} must be a string list")
    for field in ("paths", "production_symbols", "result_assertions", "coverage_obligations", "resolver_rules"):
        if behavior_slice.get(field) == []:
            errors.append(f"{prefix} {field} must not be empty")
    expected_rules = {rule.code for rule in RULES}
    actual_rules = behavior_slice.get("resolver_rules")
    if isinstance(actual_rules, list) and set(actual_rules) != expected_rules:
        errors.append(f"{prefix} resolver_rules must contain the complete shared registry")
    errors.extend(_resolver_risk_errors(behavior_slice.get("resolver_risks"), prefix))
    return errors


def _resolver_risk_errors(risks: object, prefix: str) -> list[str]:
    if not isinstance(risks, list):
        return [f"{prefix} resolver_risks must be a list"]
    errors = []
    seen = set()
    for index, risk in enumerate(risks):
        if not isinstance(risk, dict):
            errors.append(f"{prefix} resolver risk {index} must be an object")
            continue
        risk_id = risk.get("id")
        owner = risk.get("owner")
        evidence = risk.get("evidence")
        if risk_id not in RISK_OWNERS:
            errors.append(f"{prefix} resolver risk {index} has unknown id")
        elif risk_id in seen:
            errors.append(f"{prefix} resolver risk id must be unique: {risk_id}")
        else:
            seen.add(risk_id)
            if owner != RISK_OWNERS[risk_id]:
                errors.append(f"{prefix} resolver risk {risk_id} has the wrong owner")
        if not isinstance(evidence, list) or not evidence or any(
            not isinstance(item, str) or not item.strip() for item in evidence
        ):
            errors.append(f"{prefix} resolver risk {index} needs concrete evidence")
    return errors


def _matrix_java_paths(task: Mapping[str, object]) -> list[str]:
    paths = []
    for field in ("production_files", "test_files"):
        declared = task.get(field)
        if isinstance(declared, list):
            paths.extend(path for path in declared if isinstance(path, str) and path.endswith(".java"))
    return paths


def _scope_errors(
    changed_paths: set[str],
    matrix_paths: set[str],
) -> list[str]:
    changed_paths = {path for path in changed_paths if not _is_explanatory_path(path)}
    matrix_paths = {path for path in matrix_paths if not _is_explanatory_path(path)}
    errors = []
    for path in sorted(changed_paths - matrix_paths):
        errors.append(f"changed path is missing from execution matrix: {path}")
    for path in sorted(matrix_paths - changed_paths):
        errors.append(f"execution matrix path has no corresponding change: {path}")
    return errors


def _candidate_file_parts(
    repo: Path,
    changed_paths: set[str],
) -> tuple[dict[str, str], dict[str, str]]:
    parts, source_hashes = {}, {}
    for relative_path in sorted(changed_paths):
        source_path = repo / relative_path
        if not source_path.exists():
            parts[f"file:{relative_path}"] = "<deleted>"
            continue
        if not source_path.is_file() or source_path.is_symlink():
            continue
        source_bytes = source_path.read_bytes()
        source_hashes[relative_path] = hashlib.sha256(source_bytes).hexdigest()
        try:
            parts[f"file:{relative_path}"] = source_bytes.decode("utf-8")
        except UnicodeDecodeError:
            parts[f"file:{relative_path}"] = source_hashes[relative_path]
    return parts, source_hashes


def _scan_sources(
    repo: Path,
    changed: Mapping[str, frozenset[int]],
    declared_nullable_paths: frozenset[str] = frozenset(),
) -> tuple[list[QualityFinding], dict[str, str], bool]:
    findings, source_parts, has_production = [], {}, False
    for relative_path, line_numbers in sorted(changed.items()):
        if not relative_path.endswith(".java"):
            continue
        production = not _is_test_path(relative_path)
        has_production = has_production or production
        source_path = repo / relative_path
        if not source_path.is_file() or source_path.is_symlink():
            continue
        source = source_path.read_text(encoding="utf-8")
        source_parts[relative_path] = source
        findings.extend(
            scan_java_source(
                source,
                source_name=relative_path,
                changed_lines=line_numbers,
                production=production,
                allow_declared_nullable=relative_path in declared_nullable_paths,
            )
        )
    return findings, source_parts, has_production


def _paths_without_new_nullable_annotations(diff: str, changed_paths: Iterable[str]) -> frozenset[str]:
    current_path = None
    added_nullable: set[str] = set()
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current_path = line[6:]
        elif current_path and line.startswith("+") and not line.startswith("+++"):
            if re.search(r"@(?:[A-Za-z_$][\w$]*\.)*(?:Nullable|CheckForNull)\b", line):
                added_nullable.add(current_path)
    return frozenset(set(changed_paths) - added_nullable)


def _write_json(path: Path | None, payload: Mapping[str, object]) -> None:
    if path:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--base", required=True, help="recorded Apply start HEAD")
    parser.add_argument(
        "--changed-manifest",
        type=Path,
        help="optional TASK attribution that must cover the Git-derived Java scope exactly",
    )
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--execution-matrix", type=Path, required=True)
    parser.add_argument("--review-evidence", type=Path)
    parser.add_argument("--build-evidence", type=Path)
    parser.add_argument("--test-evidence", type=Path)
    parser.add_argument("--coverage-evidence", type=Path)
    parser.add_argument("--scan-only", action="store_true", help="form the objective pre-review candidate")
    parser.add_argument("--json-output", type=Path, required=True)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(arguments)
    repo = args.repo.resolve()
    design_path = args.design if args.design.is_absolute() else repo / args.design
    try:
        design_text = design_path.read_text(encoding="utf-8")
        matrix = _load_json(args.execution_matrix)
        matrix_paths, matrix_errors = _matrix_paths(matrix, design_text)
        for error in contract_preflight_errors(design_text, matrix):
            if error not in matrix_errors:
                matrix_errors.append(error)
        design_hash = hashlib.sha256(design_text.encode("utf-8")).hexdigest()
        if matrix.get("design_sha256") != design_hash:
            matrix_errors.append("execution matrix does not match the current Design")
        start_head = _run_git(repo, ["rev-parse", "--verify", f"{args.base}^{{commit}}"]).strip()
        changed_java, changed_paths, diff = _changed_scope(repo, start_head)
        scope_errors = _manifest_scope_errors(args.changed_manifest, changed_java, changed_paths)
        findings, _, has_production = _scan_sources(
            repo,
            changed_java,
            _paths_without_new_nullable_annotations(diff, changed_java),
        )
        candidate_files, changed_source_hashes = _candidate_file_parts(repo, changed_paths)
        candidate_parts = {
            "design.md": design_text,
            "execution-matrix.json": json.dumps(matrix, ensure_ascii=False, sort_keys=True),
            "start-head": start_head,
            "runtime-change-scope.json": json.dumps(sorted(changed_paths), ensure_ascii=False),
            **candidate_files,
        }
        candidate_hash = candidate_sha256(candidate_parts)
        errors = list(matrix_errors)
        errors.extend(scope_errors)
        errors.extend(_scope_errors(changed_paths, matrix_paths))
        evidence: Mapping[str, object] = {}
        pre_review_gate: Mapping[str, object] | None = None
        if args.scan_only:
            errors.extend(
                f"{finding.code} at {finding.source}:{finding.line}"
                for finding in findings
                if finding.severity == "error"
            )
        else:
            evidence_paths = (
                args.review_evidence, args.build_evidence,
                args.test_evidence, args.coverage_evidence,
            )
            if any(path is None for path in evidence_paths):
                raise ValueError(
                    "final quality verification needs review, build, test, and coverage evidence"
                )
            evidence = load_review_evidence(args.review_evidence)
            build_evidence = _load_json(args.build_evidence)
            test_evidence = _load_json(args.test_evidence)
            coverage_evidence = _load_json(args.coverage_evidence)
            pre_review_gate = {
                "quality_candidate_sha256": candidate_hash,
                "build_candidate_sha256": build_evidence.get("candidate_sha256"),
                "test_evidence_sha256": test_evidence.get("evidence_sha256"),
                "coverage_evidence_sha256": coverage_evidence.get("evidence_sha256"),
            }
            errors.extend(
                review_evidence_errors(
                    evidence,
                    candidate_hash,
                    findings,
                    require_clean_guard=has_production,
                    pre_review_gate=pre_review_gate,
                )
            )
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"quality verification failed: {error}", file=sys.stderr)
        return 2
    payload = {
        "candidate_sha256": candidate_hash,
        "start_head": start_head,
        "design_sha256": design_hash,
        "changed_files": sorted(changed_paths),
        "changed_java_files": sorted(changed_java),
        "source_sha256": changed_source_hashes,
        "production_java": has_production,
        "findings": [finding.as_dict() for finding in findings],
        "mode": "scan_only" if args.scan_only else "final",
        "reviewer": evidence.get("reviewer"),
        "pre_review_gate": pre_review_gate,
        "passed": not errors,
        "errors": errors,
        "generated_at": time.time(),
    }
    payload["evidence_sha256"] = evidence_sha256(payload)
    _write_json(args.json_output, payload)
    for finding in findings:
        print(f"{finding.severity}: {finding.code} {finding.source}:{finding.line} [{finding.symbol}]")
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    print("Java quality Gate: passed" if not errors else "Java quality Gate: failed")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
