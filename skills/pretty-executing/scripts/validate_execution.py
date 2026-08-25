#!/usr/bin/env python3
"""Validate a final Pretty Execution report against Design and fresh evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


SECTIONS = ("执行起点", "基线", "TASK 结果", "最终门禁", "未验证范围", "结论与恢复点")
TASK_HEADING = re.compile(r"^###\s+(TASK-\d{3})[：:]\s*\S.+$", re.MULTILINE)
DESIGN_TASK = re.compile(r"^###\s+(TASK-\d{3})[：:]", re.MULTILINE)
HEAD = re.compile(r"^-\s*起始 HEAD：\s*`[0-9a-f]{7,64}`\s*$", re.MULTILINE)
DESIGN_BASIS = re.compile(r"^-\s*执行依据：\s*当前工作区最新 Design\s*$", re.MULTILINE)
FINAL_STATUS = re.compile(
    r"^-\s*状态：\s*(完成|停止：\S.+|返回 PRD：\S.+|返回 Design：\S.+)\s*$",
    re.MULTILINE,
)
PLACEHOLDER = re.compile(r"<[^>\n]+>|\b(?:TODO|TBD|FIXME)\b|待验证|待审查|执行中|\.\.\.", re.IGNORECASE)


@dataclass(frozen=True)
class ExecutionEvidence:
    quality: Mapping[str, object]
    coverage: Mapping[str, object]
    build: Mapping[str, object]
    tests: Mapping[str, object]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _section_body(document: str, heading: str) -> str:
    lines = document.splitlines()
    marker = f"## {heading}"
    if marker not in lines:
        return ""
    start = lines.index(marker) + 1
    end = next((index for index in range(start, len(lines)) if lines[index].startswith("## ")), len(lines))
    return "\n".join(lines[start:end])


def _structure_errors(document: str) -> list[str]:
    headings = [line[3:].strip() for line in document.splitlines() if line.startswith("## ")]
    errors = []
    if headings != list(SECTIONS):
        errors.append(f"sections must be exactly: {', '.join(SECTIONS)}")
    if PLACEHOLDER.search(document):
        errors.append("final Execution report contains unfinished content")
    start = _section_body(document, "执行起点")
    if not HEAD.search(start):
        errors.append("执行起点 needs a valid starting HEAD")
    if not DESIGN_BASIS.search(start):
        errors.append("执行起点 must use the current Design")
    if not FINAL_STATUS.search(_section_body(document, "结论与恢复点")):
        errors.append("结论与恢复点 needs a valid final status")
    return errors


def _task_errors(document: str, design_text: str) -> list[str]:
    design_tasks = DESIGN_TASK.findall(design_text)
    execution_tasks = TASK_HEADING.findall(_section_body(document, "TASK 结果"))
    if set(execution_tasks) != set(design_tasks):
        return [f"Execution TASK set must match Design: {design_tasks}"]
    return []


def _complete_status(document: str) -> bool:
    return re.search(r"^-\s*状态：\s*完成\s*$", _section_body(document, "结论与恢复点"), re.MULTILINE) is not None


def _coverage_summary(coverage: Mapping[str, object]) -> str:
    status = coverage.get("status")
    if status == "not_applicable":
        return "不适用"
    if status == "unmeasurable":
        return "无法验证"
    line = coverage.get("line_percentage")
    branch = coverage.get("branch_percentage")
    if not isinstance(line, (int, float)):
        return "无法验证"
    branch_text = f"分支覆盖率 {branch:.2f}%" if isinstance(branch, (int, float)) else "分支覆盖率不适用"
    return f"增量行覆盖率 {line:.2f}%，{branch_text}"


def _coverage_errors(document: str, coverage: Mapping[str, object]) -> list[str]:
    expected = f"- 测试覆盖率：{_coverage_summary(coverage)}"
    errors = [] if expected in _section_body(document, "结论与恢复点") else [f"结论必须包含覆盖率证据：{expected}"]
    if _complete_status(document) and coverage.get("status") not in {"pass", "not_applicable"}:
        errors.append("完成状态需要通过或不适用的增量覆盖率")
    return errors


def _gate_errors(document: str, quality: Mapping[str, object], tests: Mapping[str, object]) -> list[str]:
    gate = _section_body(document, "最终门禁")
    required = ("Design TASK 与真实 Diff", "机械 Gate 与独立审查", "编译与相关测试", "新增/修改测试实际执行", "增量覆盖率")
    errors = []
    for row in required:
        match = re.search(rf"^\|\s*{re.escape(row)}\s*\|[^|]*\|\s*([^|\n]+)\s*\|$", gate, re.MULTILINE)
        if not match:
            errors.append(f"最终门禁缺少：{row}")
        elif _complete_status(document) and match.group(1).strip() not in {"通过", "不适用"}:
            errors.append(f"完成状态的最终门禁未通过：{row}")
    if _complete_status(document) and quality.get("passed") is not True:
        errors.append("完成状态需要通过 quality Gate")
    if _complete_status(document) and tests.get("passed") is not True:
        errors.append("完成状态需要新增/修改测试实际执行通过")
    return errors


def _source_binding_errors(evidence: Mapping[str, object], repo: Path, label: str) -> list[str]:
    source_hashes = evidence.get("source_sha256")
    if not isinstance(source_hashes, dict):
        return [f"{label} evidence needs source_sha256"]
    errors = []
    for relative_path, expected_hash in source_hashes.items():
        source_path = repo / str(relative_path)
        if not source_path.is_file() or _sha256(source_path) != expected_hash:
            errors.append(f"{label} evidence is stale for {relative_path}")
    return errors


def _build_errors(build: Mapping[str, object], design_path: Path, evidence: ExecutionEvidence, require_passes: bool) -> list[str]:
    errors = _evidence_binding_errors(build, design_path, evidence)
    if not isinstance(build.get("commands"), list):
        return errors + ["build evidence commands must be a list"]
    if not require_passes:
        return errors
    return errors + _required_command_errors(build, evidence)


def _evidence_binding_errors(
    build: Mapping[str, object], design_path: Path, evidence: ExecutionEvidence
) -> list[str]:
    design_hash = _sha256(design_path)
    quality, coverage, tests = evidence.quality, evidence.coverage, evidence.tests
    errors = []
    if build.get("design_sha256") != design_hash:
        errors.append("build evidence does not match the current Design")
    if quality.get("design_sha256") != design_hash:
        errors.append("quality evidence does not match the current Design")
    if coverage.get("design_sha256") != design_hash:
        errors.append("coverage evidence does not match the current Design")
    if tests.get("design_sha256") != design_hash:
        errors.append("test evidence does not match the current Design")
    candidate_bindings = {
        "quality_candidate_sha256": quality.get("candidate_sha256"),
        "coverage_candidate_sha256": coverage.get("candidate_sha256"),
        "test_candidate_sha256": tests.get("candidate_sha256"),
    }
    for field, expected in candidate_bindings.items():
        if not isinstance(expected, str) or not expected:
            errors.append(f"{field.removesuffix('_candidate_sha256')} evidence needs candidate_sha256")
        elif build.get(field) != expected:
            errors.append(f"build evidence has stale {field}")
    return errors


def _required_command_errors(build: Mapping[str, object], evidence: ExecutionEvidence) -> list[str]:
    commands = build.get("commands")
    if not isinstance(commands, list):
        return ["build evidence commands must be a list"]
    errors = []
    latest = {}
    for index, entry in enumerate(commands):
        if not isinstance(entry, dict) or not isinstance(entry.get("kind"), str):
            continue
        finished = entry.get("finished_at", 0)
        previous = latest.get(entry["kind"])
        if previous is None or (finished, index) > (previous[0], previous[1]):
            latest[entry["kind"]] = (finished, index, entry)
    required = build.get("required_kinds", ["compile", "new_tests", "regression_tests"])
    allowed = {"compile", "new_tests", "regression_tests"}
    if not isinstance(required, list) or any(kind not in allowed for kind in required):
        return errors + ["build evidence required_kinds must contain only known command kinds"]
    mandatory = set()
    if evidence.quality.get("production_java") is True:
        mandatory.update({"compile", "regression_tests"})
    if evidence.tests.get("expected_tests"):
        mandatory.add("new_tests")
    for missing_kind in sorted(mandatory - set(required)):
        errors.append(f"build evidence cannot mark applicable command as not required: {missing_kind}")
    for kind in required:
        if kind not in latest:
            errors.append(f"missing build evidence: {kind}")
        elif latest[kind][2].get("exit_code") != 0:
            errors.append(f"latest build evidence failed: {kind}")
    return errors


def validate_execution(document: str, design_text: str, design_path: Path, evidence: ExecutionEvidence) -> list[str]:
    quality, coverage, build, tests = evidence.quality, evidence.coverage, evidence.build, evidence.tests
    errors = _structure_errors(document)
    errors.extend(_task_errors(document, design_text))
    errors.extend(_gate_errors(document, quality, tests))
    errors.extend(_coverage_errors(document, coverage))
    repo = design_path.resolve().parents[3] if len(design_path.resolve().parents) >= 4 else design_path.parent
    complete = _complete_status(document)
    if complete:
        errors.extend(_source_binding_errors(quality, repo, "quality"))
        errors.extend(_source_binding_errors(coverage, repo, "coverage"))
        errors.extend(_source_binding_errors(tests, repo, "test"))
        errors.extend(_build_errors(build, design_path, evidence, True))
    final_digest = re.search(r"^-\s*最终 Diff 摘要：\s*`([^`]+)`\s*$", _section_body(document, "结论与恢复点"), re.MULTILINE)
    if complete and (not final_digest or final_digest.group(1) != quality.get("candidate_sha256")):
        errors.append("最终 Diff 摘要必须匹配 quality candidate_sha256")
    return errors


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("execution", type=Path)
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--quality-evidence", type=Path)
    parser.add_argument("--coverage-evidence", type=Path)
    parser.add_argument("--build-evidence", type=Path)
    parser.add_argument("--test-evidence", type=Path)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(arguments)
    try:
        document = args.execution.read_text(encoding="utf-8")
        design_text = args.design.read_text(encoding="utf-8")
        quality = _load_json(args.quality_evidence) if args.quality_evidence else {}
        coverage = _load_json(args.coverage_evidence) if args.coverage_evidence else {}
        build = _load_json(args.build_evidence) if args.build_evidence else {}
        tests = _load_json(args.test_evidence) if args.test_evidence else {}
        errors = validate_execution(
            document,
            design_text,
            args.design,
            ExecutionEvidence(quality, coverage, build, tests),
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Execution validation failed: {error}", file=sys.stderr)
        return 2
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if not errors:
        print("Execution Gate: passed")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
