#!/usr/bin/env python3
"""Derive Pretty quality rules and review risks from repository facts."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping, Sequence

from evidence_binding import bytes_sha256, payload_sha256  # type: ignore[import-not-found]
from quality_registry import RISK_BY_CODE, RULES
from pretty_tmp import is_pretty_tmp_path, topic_dir_for_document, validate_artifact_path, validate_run_dir


JAVA_TYPE = re.compile(r"\b(?:class|interface|enum|record)\s+([A-Za-z_$][\w$]*)")
MODULE_SIGNAL = re.compile(
    r"\b(?:public\s+interface|implements|extends)\b|"
    r"\b(?:[A-Za-z_$][\w$]*)?(?:Gateway|Adapter|Repository|Client|Remote|Controller)\b"
)
TYPE_SIGNAL = re.compile(
    r"\b(?:record|enum)\b|\b(?:BigDecimal|Optional|Comparable)\b|"
    r"\b(?:Value|Id|Code|Type|Status)\b"
)
RUNTIME_SIGNAL = re.compile(
    r"\b(?:null|throw|catch|synchronized|volatile|CompletableFuture|Executor|ThreadLocal|Transactional)\b|"
    r"\b(?:[A-Za-z_$][\w$]*)?(?:Gateway|Adapter|Repository|Client|Remote)\b"
)
CHANGE_AXIS_SIGNAL = re.compile(r"\b(?:Strategy|Factory|Registry|Provider)\b")


def _run_git(repo: Path, arguments: Sequence[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(arguments)} failed")
    return result.stdout


def _safe_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    candidate = PurePosixPath(normalized)
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        raise ValueError(f"quality resolver path must be repository-relative: {path}")
    return normalized


def _git_paths(repo: Path, base: str) -> set[str]:
    tracked = set(_run_git(repo, ["diff", "--name-only", base, "--"]).splitlines())
    untracked = set(_run_git(repo, ["ls-files", "--others", "--exclude-standard"]).splitlines())
    return {_safe_path(path) for path in tracked | untracked if path and not is_pretty_tmp_path(path)}


def _matrix_slice_paths(matrix: Mapping[str, object]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    tasks = matrix.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError("execution matrix tasks must be a list")
    for task in tasks:
        if not isinstance(task, dict) or not isinstance(task.get("id"), str):
            raise ValueError("execution matrix task needs an id")
        task_paths = {
            _safe_path(path)
            for field in ("production_files", "test_files", "supporting_files")
            for path in task.get(field, [])
            if isinstance(path, str)
        }
        slices = task.get("behavior_slices", [])
        if not isinstance(slices, list):
            raise ValueError(f"execution matrix {task['id']} behavior_slices must be a list")
        if not slices:
            result[task["id"]] = task_paths
            continue
        for behavior_slice in slices:
            if not isinstance(behavior_slice, dict) or not isinstance(behavior_slice.get("id"), str):
                raise ValueError(f"execution matrix {task['id']} behavior slice needs an id")
            slice_paths = behavior_slice.get("paths")
            result[behavior_slice["id"]] = (
                {_safe_path(path) for path in slice_paths if isinstance(path, str)}
                if isinstance(slice_paths, list) and slice_paths
                else set(task_paths)
            )
    return result


def _path_evidence(repo: Path, paths: Iterable[str]) -> tuple[list[str], str, bool, bool]:
    evidence: list[str] = []
    content_parts: list[str] = []
    has_production_java = False
    has_test_java = False
    for relative_path in sorted(set(paths)):
        path = repo / relative_path
        is_java = relative_path.endswith(".java")
        is_test = "/src/test/" in f"/{relative_path}" or relative_path.startswith("test/")
        has_production_java = has_production_java or (is_java and not is_test)
        has_test_java = has_test_java or (is_java and is_test)
        if not path.is_file() or path.is_symlink():
            evidence.append(relative_path)
            continue
        raw = path.read_bytes()
        content_parts.append(f"{relative_path}\0{bytes_sha256(raw)}")
        text = raw.decode("utf-8", errors="replace")
        symbols = JAVA_TYPE.findall(text) if is_java else []
        evidence.extend(f"{relative_path}#{symbol}" for symbol in symbols[:8])
        if not symbols:
            evidence.append(relative_path)
        content_parts.append(text)
    return evidence, "\n".join(content_parts), has_production_java, has_test_java


def resolve_slice(repo: Path, slice_id: str, paths: Iterable[str]) -> dict[str, object]:
    safe_paths = sorted({_safe_path(path) for path in paths})
    evidence, content, has_production_java, has_test_java = _path_evidence(repo, safe_paths)
    risks: set[str] = set()
    if has_production_java:
        # Conservative defaults prevent semantic under-routing for generated Java.
        risks.update({"JAVA_OOD", "JAVA_RUNTIME_RISK", "BEHAVIOR_TEST"})
    elif has_test_java:
        risks.add("BEHAVIOR_TEST")
    if MODULE_SIGNAL.search(content):
        risks.add("MODULE_BOUNDARY")
    if TYPE_SIGNAL.search(content):
        risks.add("TYPE_DESIGN")
    if RUNTIME_SIGNAL.search(content):
        risks.add("JAVA_RUNTIME_RISK")
    if CHANGE_AXIS_SIGNAL.search(content):
        risks.add("CHANGE_AXIS")
    return {
        "id": slice_id,
        "paths": safe_paths,
        "rules": [rule.code for rule in RULES],
        "risks": [
            {
                "id": risk,
                "owner": RISK_BY_CODE[risk].owner,
                "description": RISK_BY_CODE[risk].description,
                "evidence": evidence or safe_paths,
            }
            for risk in sorted(risks)
        ],
        "guards": ["clean-code-guard"] if has_production_java else [],
        "scope_sha256": bytes_sha256(("\n".join(safe_paths) + "\0" + content).encode("utf-8")),
    }


def freshness_errors(repo: Path, resolver: Mapping[str, object]) -> list[str]:
    """Detect route output that no longer matches the current repository files."""
    slices = resolver.get("slices")
    if not isinstance(slices, list):
        return ["quality resolver slices must be a list"]
    errors: list[str] = []
    for item in slices:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            errors.append("quality resolver contains an invalid slice")
            continue
        paths = item.get("paths")
        if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths):
            errors.append(f"quality resolver slice {item['id']} has invalid paths")
            continue
        expected = resolve_slice(repo, item["id"], paths)
        for field in ("paths", "rules", "risks", "guards", "scope_sha256"):
            if item.get(field) != expected[field]:
                errors.append(f"quality resolver slice {item['id']} is stale for {field}")
    return sorted(set(errors))


def resolve(
    repo: Path,
    design: Path,
    slices: Mapping[str, Iterable[str]],
    base: str | None = None,
) -> dict[str, object]:
    design_bytes = design.read_bytes()
    resolved = [resolve_slice(repo, slice_id, paths) for slice_id, paths in sorted(slices.items())]
    payload: dict[str, object] = {
        "schema_version": 1,
        "design_sha256": bytes_sha256(design_bytes),
        "shared_rules": [rule.code for rule in RULES],
        "slices": resolved,
    }
    if base:
        payload["start_head"] = _run_git(repo, ["rev-parse", "--verify", f"{base}^{{commit}}"]).strip()
    payload["resolver_sha256"] = payload_sha256(payload, {"resolver_sha256"})
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--base", help="execution starting HEAD; derives current Git scope when no matrix is supplied")
    parser.add_argument("--execution-matrix", type=Path)
    parser.add_argument("--path", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(arguments)
    repo = args.repo.resolve()
    design = args.design if args.design.is_absolute() else repo / args.design
    try:
        topic_dir = topic_dir_for_document(design)
        output = args.output if args.output.is_absolute() else repo / args.output
        run_dir = validate_run_dir(topic_dir, output.parent)
        output = validate_artifact_path(run_dir, output)
        if args.execution_matrix:
            matrix_path = args.execution_matrix if args.execution_matrix.is_absolute() else repo / args.execution_matrix
            validate_artifact_path(run_dir, matrix_path)
            matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
            if not isinstance(matrix, dict):
                raise ValueError("execution matrix must be a JSON object")
            slices = _matrix_slice_paths(matrix)
        else:
            paths = {_safe_path(path) for path in args.path}
            if args.base:
                paths.update(_git_paths(repo, args.base))
            if not paths:
                raise ValueError("quality resolver needs an execution matrix, --path, or --base")
            slices = {"candidate": paths}
        payload = resolve(repo, design, slices, args.base)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"quality resolver failed: {error}", file=sys.stderr)
        return 2
    print(f"Quality Resolver: {len(payload['slices'])} slice(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
