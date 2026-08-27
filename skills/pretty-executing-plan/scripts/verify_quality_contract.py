#!/usr/bin/env python3
"""Verify the current Execution Java increment and independent review evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath
from typing import Mapping, Sequence


COMMON_SCRIPTS = Path(__file__).resolve().parents[2] / "pretty-common" / "scripts"
PLAN_SCRIPTS = Path(__file__).resolve().parents[2] / "pretty-writing-plan" / "scripts"
for scripts_dir in (COMMON_SCRIPTS, PLAN_SCRIPTS):
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

from quality_contract_gate import (  # type: ignore[import-not-found]
    QualityFinding,
    candidate_sha256,
    load_review_evidence,
    parse_touched_java_lines,
    review_evidence_errors,
    scan_java_source,
)
from validate_plan import FILE_ENTRY, validate_plan  # type: ignore[import-not-found]


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
    base: str | None,
    manifest: Path | None,
) -> tuple[dict[str, frozenset[int]], set[str], str]:
    if manifest:
        manifest_content = manifest.read_text(encoding="utf-8")
        all_changed = _read_manifest(manifest)
        java_changed = {path: lines for path, lines in all_changed.items() if path.endswith(".java")}
        return java_changed, set(all_changed), manifest_content
    assert base is not None
    diff = _run_git(repo, ["diff", "--no-ext-diff", "--unified=0", base, "--"])
    changed_paths = set(_run_git(repo, ["diff", "--name-only", base, "--"]).splitlines())
    untracked_paths = _untracked_paths(repo)
    changed_paths.update(untracked_paths)
    java_changed = parse_touched_java_lines(diff)
    java_changed.update(_untracked_java(repo, untracked_paths))
    return java_changed, changed_paths, diff


def _plan_paths(plan_text: str) -> set[str]:
    return {path for _, path in FILE_ENTRY.findall(plan_text)}


def _scope_extensions(evidence: Mapping[str, object] | None) -> dict[str, str]:
    extensions = {}
    if not evidence:
        return extensions
    for entry in evidence.get("scope_extensions", []):
        if isinstance(entry, dict) and isinstance(entry.get("path"), str):
            extensions[entry["path"]] = str(entry.get("reason", "")).strip()
    return extensions


def _scope_errors(
    changed_paths: set[str],
    planned_paths: set[str],
    evidence: Mapping[str, object] | None,
) -> list[str]:
    extensions = _scope_extensions(evidence)
    errors = []
    for path in sorted(changed_paths - planned_paths):
        if len(extensions.get(path, "")) < 12:
            errors.append(f"unplanned path without a justified scope extension: {path}")
    for path in sorted(planned_paths - changed_paths):
        errors.append(f"planned path has no corresponding change: {path}")
    return errors


def _candidate_file_parts(
    repo: Path,
    changed_paths: set[str],
) -> tuple[dict[str, str], dict[str, str]]:
    parts, source_hashes = {}, {}
    for relative_path in sorted(changed_paths):
        source_path = repo / relative_path
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
            )
        )
    return findings, source_parts, has_production


def _write_json(path: Path | None, payload: Mapping[str, object]) -> None:
    if path:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--base")
    source.add_argument("--changed-manifest", type=Path)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-review-evidence", type=Path)
    parser.add_argument("--review-evidence", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(arguments)
    repo = args.repo.resolve()
    plan_path = args.plan if args.plan.is_absolute() else repo / args.plan
    try:
        plan_text = plan_path.read_text(encoding="utf-8")
        plan_evidence = load_review_evidence(args.plan_review_evidence) if args.plan_review_evidence else None
        plan_errors, plan_findings = validate_plan(
            plan_path,
            plan_evidence,
            require_review=plan_evidence is not None,
        )
        if plan_evidence is None and any(finding.severity == "review_required" for finding in plan_findings):
            plan_errors.append("Plan has review findings and needs matching --plan-review-evidence")
        changed_java, changed_paths, diff_or_manifest = _changed_scope(repo, args.base, args.changed_manifest)
        findings, _, has_production = _scan_sources(repo, changed_java)
        candidate_files, changed_source_hashes = _candidate_file_parts(repo, changed_paths)
        candidate_parts = {
            "plan.md": plan_text,
            "changes": diff_or_manifest,
            **candidate_files,
        }
        candidate_hash = candidate_sha256(candidate_parts)
        evidence = load_review_evidence(args.review_evidence)
        errors = list(plan_errors)
        errors.extend(_scope_errors(changed_paths, _plan_paths(plan_text), evidence))
        errors.extend(
            review_evidence_errors(
                evidence,
                candidate_hash,
                findings,
                require_clean_guard=has_production,
            )
        )
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"quality verification failed: {error}", file=sys.stderr)
        return 2
    payload = {
        "candidate_sha256": candidate_hash,
        "plan_sha256": hashlib.sha256(plan_text.encode("utf-8")).hexdigest(),
        "changed_files": sorted(changed_paths),
        "changed_java_files": sorted(changed_java),
        "source_sha256": changed_source_hashes,
        "production_java": has_production,
        "findings": [finding.as_dict() for finding in findings],
        "reviewer": evidence.get("reviewer"),
        "passed": not errors,
        "errors": errors,
        "generated_at": time.time(),
    }
    _write_json(args.json_output, payload)
    for finding in findings:
        print(f"{finding.severity}: {finding.code} {finding.source}:{finding.line} [{finding.symbol}]")
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    print("Java quality Gate: passed" if not errors else "Java quality Gate: failed")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
