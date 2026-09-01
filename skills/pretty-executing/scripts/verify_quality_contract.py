#!/usr/bin/env python3
"""Create bound mechanical quality evidence for one Apply candidate."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from candidate_contract import (  # type: ignore[import-not-found]
    CandidateRequest,
    file_sha256,
    quality_bundle_sha256,
    run_git,
    snapshot_candidate,
)
from evidence_binding import evidence_sha256  # type: ignore[import-not-found]
from execution_contract import contract_preflight_errors, resolver_binding_errors
from pretty_tmp import (  # type: ignore[import-not-found]
    is_pretty_tmp_path,
    topic_dir_for_document,
    validate_artifact_path,
    validate_run_dir,
)
from quality_contract_gate import (  # type: ignore[import-not-found]
    QualityFinding,
    load_review_evidence,
    parse_touched_java_lines,
    review_evidence_errors,
    scan_java_source,
)


@dataclass(frozen=True)
class QualityVerificationRequest:
    repo: Path
    design: Path
    matrix: Path
    resolver: Path
    base: str
    scope: str
    slice_id: str | None = None
    changed_manifest: Path | None = None
    review_evidence: Path | None = None


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _git_text(repo: Path, arguments: Sequence[str]) -> str:
    return str(run_git(repo, arguments))


def _safe_path(value: str) -> str:
    path = value.replace("\\", "/")
    candidate = PurePosixPath(path)
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        raise ValueError(f"matrix path must be repository-relative: {value}")
    return path


def _is_test_path(path: str) -> bool:
    normalized = f"/{path.lower().lstrip('/')}"
    return "/src/test/" in normalized or normalized.startswith("/test/")


def _is_explanatory_path(path: str) -> bool:
    if is_pretty_tmp_path(path):
        return True
    normalized = path.lower().lstrip("/")
    suffix = PurePosixPath(normalized).suffix
    parts = PurePosixPath(normalized).parts
    if suffix in {".java", ".kt", ".sql", ".xml", ".properties", ".yml", ".yaml", ".json"}:
        return False
    return normalized.startswith(("docs/", ".code-review/")) or "src" not in parts


def _matrix_scopes(matrix: Mapping[str, object]) -> tuple[set[str], dict[str, set[str]]]:
    tasks = matrix.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError("execution matrix tasks must be a list")
    all_paths: set[str] = set()
    slices: dict[str, set[str]] = {}
    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_paths = {
            _safe_path(path)
            for field in ("production_files", "test_files", "supporting_files")
            for path in task.get(field, [])
            if isinstance(path, str)
        }
        all_paths.update(task_paths)
        for behavior_slice in task.get("behavior_slices", []):
            if not isinstance(behavior_slice, dict) or not isinstance(behavior_slice.get("id"), str):
                continue
            paths = behavior_slice.get("paths")
            slice_paths = {
                _safe_path(path) for path in paths if isinstance(path, str)
            } if isinstance(paths, list) else set(task_paths)
            slices[behavior_slice["id"].strip()] = slice_paths
            all_paths.update(slice_paths)
    return all_paths, slices


def _untracked_java(repo: Path, paths: Iterable[str]) -> dict[str, frozenset[int]]:
    result = {}
    for relative_path in paths:
        source = repo / relative_path
        if relative_path.endswith(".java") and source.is_file():
            result[relative_path] = frozenset(range(1, len(source.read_text(encoding="utf-8").splitlines()) + 1))
    return result


def _changed_java(repo: Path, start_head: str, paths: set[str]) -> tuple[dict[str, frozenset[int]], str]:
    diff = _git_text(repo, ["diff", "--no-ext-diff", "--unified=0", start_head, "--"])
    changed = parse_touched_java_lines(diff)
    untracked = set(_git_text(repo, ["ls-files", "--others", "--exclude-standard"]).splitlines())
    changed.update(_untracked_java(repo, untracked))
    return {path: lines for path, lines in changed.items() if path in paths}, diff


def _paths_without_added_nullable(diff: str, paths: Iterable[str]) -> frozenset[str]:
    current = None
    nullable: set[str] = set()
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
        elif current and line.startswith("+") and not line.startswith("+++"):
            if re.search(r"@(?:[A-Za-z_$][\w$]*\.)*(?:Nullable|CheckForNull)\b", line):
                nullable.add(current)
    return frozenset(set(paths) - nullable)


def _scan(
    repo: Path, changed: Mapping[str, frozenset[int]], nullable_contract_paths: frozenset[str],
) -> tuple[list[QualityFinding], bool]:
    findings: list[QualityFinding] = []
    production_java = False
    for relative_path, lines in sorted(changed.items()):
        source_path = repo / relative_path
        if not source_path.is_file() or source_path.is_symlink():
            continue
        production = not _is_test_path(relative_path)
        production_java = production_java or production
        findings.extend(scan_java_source(
            source_path.read_text(encoding="utf-8"),
            source_name=relative_path,
            changed_lines=lines,
            production=production,
            allow_declared_nullable=relative_path in nullable_contract_paths,
        ))
    return findings, production_java


def _scope_errors(
    actual: set[str], matrix_paths: set[str], scope: str,
    slice_id: str | None, slices: Mapping[str, set[str]],
) -> tuple[list[str], set[str]]:
    actual_runtime = {path for path in actual if not _is_explanatory_path(path)}
    declared_runtime = {path for path in matrix_paths if not _is_explanatory_path(path)}
    errors = [
        f"changed path is missing from execution matrix: {path}"
        for path in sorted(actual_runtime - declared_runtime)
    ]
    if scope == "candidate":
        errors.extend(
            f"execution matrix path has no corresponding candidate change: {path}"
            for path in sorted(declared_runtime - actual_runtime)
        )
        return errors, actual_runtime
    if not slice_id or slice_id not in slices:
        return errors + [f"unknown behavior slice: {slice_id}"], set()
    scan_paths = actual_runtime & slices[slice_id]
    if not scan_paths:
        errors.append(f"active behavior slice has no candidate changes: {slice_id}")
    return errors, scan_paths


def _manifest_errors(path: Path | None, actual: set[str]) -> list[str]:
    if path is None:
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return ["changed manifest must be a JSON object"]
    errors = []
    for source_path, lines in payload.items():
        if not isinstance(source_path, str) or not isinstance(lines, list):
            errors.append("changed manifest must map paths to line lists")
        elif any(not isinstance(line, int) or line < 1 for line in lines):
            errors.append(f"changed manifest has invalid line numbers: {source_path}")
    declared = {_safe_path(value) for value in payload if isinstance(value, str)}
    if declared != actual:
        errors.append(
        f"changed manifest scope differs from Git: declared={sorted(declared)}, actual={sorted(actual)}"
        )
    return errors


def verify(request: QualityVerificationRequest) -> dict[str, object]:
    repo, design = request.repo, request.design
    matrix_path, resolver_path = request.matrix, request.resolver
    start_head, scope, slice_id = request.base, request.scope, request.slice_id
    design_text = design.read_text(encoding="utf-8")
    matrix = _load_json(matrix_path)
    resolver = _load_json(resolver_path)
    design_hash = file_sha256(design)
    resolved_head = _git_text(repo, ["rev-parse", "--verify", f"{start_head}^{{commit}}"] ).strip()
    bundle_hash = quality_bundle_sha256()
    snapshot = snapshot_candidate(CandidateRequest(
        repo, design_text, matrix, resolver, resolved_head, bundle_hash,
    ))
    matrix_paths, slices = _matrix_scopes(matrix)
    errors = contract_preflight_errors(design_text, matrix)
    errors.extend(resolver_binding_errors(matrix, resolver, design_hash, resolved_head))
    if matrix.get("design_sha256") != design_hash:
        errors.append("execution matrix does not match the current Design")
    scope_errors, scan_paths = _scope_errors(
        set(snapshot.changed_paths), matrix_paths, scope, slice_id, slices,
    )
    errors.extend(scope_errors)
    errors.extend(_manifest_errors(request.changed_manifest, set(snapshot.changed_paths)))
    changed_java, diff = _changed_java(repo, resolved_head, scan_paths)
    findings, production_java = _scan(
        repo, changed_java, _paths_without_added_nullable(diff, changed_java),
    )
    errors.extend(
        f"{finding.code} at {finding.source}:{finding.line}"
        for finding in findings if finding.severity == "error"
    )
    reviewer = None
    if request.review_evidence is not None:
        reviewer = load_review_evidence(request.review_evidence)
        if reviewer.get("evidence_sha256") != evidence_sha256(reviewer):
            errors.append("review evidence integrity hash does not match")
        errors.extend(review_evidence_errors(
            reviewer,
            snapshot.sha256,
            findings,
            require_clean_guard=production_java,
        ))
    payload: dict[str, object] = {
        "candidate_sha256": snapshot.sha256,
        "start_head": resolved_head,
        "design_sha256": design_hash,
        "execution_matrix_sha256": file_sha256(matrix_path),
        "resolver_sha256": file_sha256(resolver_path),
        "shared_bundle_sha256": bundle_hash,
        "scope": scope,
        "slice_id": slice_id if scope == "slice" else None,
        "changed_files": list(snapshot.changed_paths),
        "scanned_files": sorted(scan_paths),
        "changed_java_files": sorted(changed_java),
        "source_sha256": dict(snapshot.source_sha256),
        "production_java": production_java,
        "findings": [finding.as_dict() for finding in findings],
        "review_pending": any(finding.severity == "review_required" for finding in findings),
        "reviewer": reviewer.get("reviewer") if reviewer else None,
        "passed": not errors,
        "errors": sorted(set(errors)),
        "generated_at": time.time(),
    }
    payload["evidence_sha256"] = evidence_sha256(payload)
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--base", required=True, help="recorded Apply start HEAD")
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--execution-matrix", type=Path, required=True)
    parser.add_argument("--resolver", type=Path, required=True)
    parser.add_argument("--scope", choices=("slice", "candidate"), required=True)
    parser.add_argument("--slice-id")
    parser.add_argument("--changed-manifest", type=Path)
    parser.add_argument("--review-evidence", type=Path)
    parser.add_argument("--json-output", type=Path, required=True)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(arguments)
    try:
        repo = args.repo.resolve()
        design = args.design if args.design.is_absolute() else repo / args.design
        matrix = args.execution_matrix if args.execution_matrix.is_absolute() else repo / args.execution_matrix
        resolver = args.resolver if args.resolver.is_absolute() else repo / args.resolver
        output = args.json_output if args.json_output.is_absolute() else repo / args.json_output
        topic = topic_dir_for_document(design)
        run_dir = validate_run_dir(topic, matrix.parent)
        for artifact in (matrix, resolver, output, args.changed_manifest, args.review_evidence):
            if artifact is not None:
                path = artifact if artifact.is_absolute() else repo / artifact
                validate_artifact_path(run_dir, path)
        if args.scope == "slice" and not args.slice_id:
            raise ValueError("slice scope requires --slice-id")
        if args.scope == "candidate" and args.slice_id:
            raise ValueError("candidate scope does not accept --slice-id")
        manifest = args.changed_manifest if not args.changed_manifest or args.changed_manifest.is_absolute() else repo / args.changed_manifest
        review = args.review_evidence if not args.review_evidence or args.review_evidence.is_absolute() else repo / args.review_evidence
        payload = verify(QualityVerificationRequest(
            repo, design, matrix, resolver, args.base, args.scope, args.slice_id, manifest, review,
        ))
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"quality verification failed: {error}", file=sys.stderr)
        return 2
    for finding in payload["findings"]:
        print(f"{finding['severity']}: {finding['code']} {finding['source']}:{finding['line']}")
    for error in payload["errors"]:
        print(f"error: {error}", file=sys.stderr)
    print("Java quality Gate: passed" if payload["passed"] else "Java quality Gate: failed")
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
