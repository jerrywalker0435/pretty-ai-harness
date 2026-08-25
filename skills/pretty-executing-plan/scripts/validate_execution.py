#!/usr/bin/env python3
"""Validate a final Pretty Execution report against fresh evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Mapping, Sequence


SECTIONS = (
    "执行起点",
    "基线",
    "TASK 结果",
    "最终门禁",
    "未验证范围",
    "结论与恢复点",
)
TASK_HEADING = re.compile(r"^###\s+(TASK-\d{3})[：:]\s*\S.+$", re.MULTILINE)
PLAN_TASK = re.compile(r"^###\s+(TASK-\d{3})[：:]", re.MULTILINE)
PLAN_SQL_FILE = re.compile(
    r"^[-*+]\s+(?:Create|Modify):\s+\x60[^\x60\n]+\.sql\x60\s*$",
    re.IGNORECASE | re.MULTILINE,
)
HEAD = re.compile(r"^-\s*起始 HEAD：\s*\x60[0-9a-f]{7,64}\x60\s*$", re.MULTILINE)
PLAN_BASIS = re.compile(r"^-\s*执行依据：\s*当前工作区最新 Plan\s*$", re.MULTILINE)
FINAL_STATUS = re.compile(
    r"^-\s*状态：\s*(完成|停止：\S.+|返回 PRD：\S.+|返回 Design：\S.+|返回 Plan：\S.+)\s*$",
    re.MULTILINE,
)
PLACEHOLDER = re.compile(r"<[^>\n]+>|\b(?:TODO|TBD|FIXME)\b|待验证|待审查|执行中|\.\.\.", re.IGNORECASE)
TASK_REVIEW = re.compile(r"^-\s*路由与审查：\s*\S.+$", re.MULTILINE)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _section_headings(document: str) -> list[str]:
    return [line[3:].strip() for line in document.splitlines() if line.startswith("## ")]


def _section_body(document: str, heading: str) -> str:
    lines = document.splitlines()
    marker = f"## {heading}"
    if marker not in lines:
        return ""
    start = lines.index(marker) + 1
    end = next(
        (index for index in range(start, len(lines)) if lines[index].startswith("## ")),
        len(lines),
    )
    return "\n".join(lines[start:end])


def _structure_errors(document: str) -> list[str]:
    headings = _section_headings(document)
    errors = []
    if headings != list(SECTIONS):
        errors.append(f"sections must be exactly: {', '.join(SECTIONS)}")
    if PLACEHOLDER.search(document):
        errors.append("final Execution report contains unfinished content")
    if not HEAD.search(_section_body(document, "执行起点")):
        errors.append("执行起点 needs a valid starting HEAD")
    if not PLAN_BASIS.search(_section_body(document, "执行起点")):
        errors.append("执行起点 must use the current Plan")
    if not FINAL_STATUS.search(_section_body(document, "结论与恢复点")):
        errors.append("结论与恢复点 needs a valid final status")
    return errors


def _task_errors(document: str, plan_text: str) -> list[str]:
    plan_tasks = PLAN_TASK.findall(plan_text)
    execution_tasks = TASK_HEADING.findall(_section_body(document, "TASK 结果"))
    errors = []
    if execution_tasks != plan_tasks:
        errors.append(f"Execution TASK order must match Plan: {plan_tasks}")
    task_body = _section_body(document, "TASK 结果")
    if len(TASK_REVIEW.findall(task_body)) != len(execution_tasks):
        errors.append("every TASK must record routing and independent review")
    return errors


def _complete_status(document: str) -> bool:
    conclusion = _section_body(document, "结论与恢复点")
    return re.search(r"^-\s*状态：\s*完成\s*$", conclusion, re.MULTILINE) is not None


def _plan_has_sql(plan_text: str) -> bool:
    return PLAN_SQL_FILE.search(plan_text) is not None


def _coverage_summary(coverage: Mapping[str, object]) -> str:
    if coverage.get("status") == "not_applicable":
        return "不适用"
    if coverage.get("status") == "unmeasurable":
        return "无法验证"
    line_percentage = coverage.get("line_percentage")
    branch_percentage = coverage.get("branch_percentage")
    if not isinstance(line_percentage, (int, float)):
        return "无法验证"
    line_text = f"增量行覆盖率 {line_percentage:.2f}%"
    branch_text = (
        f"分支覆盖率 {branch_percentage:.2f}%"
        if isinstance(branch_percentage, (int, float))
        else "分支覆盖率不适用"
    )
    return f"{line_text}，{branch_text}"


def _coverage_errors(document: str, coverage: Mapping[str, object]) -> list[str]:
    conclusion = _section_body(document, "结论与恢复点")
    expected = f"- 测试覆盖率：{_coverage_summary(coverage)}"
    errors = [] if expected in conclusion else [f"结论必须包含覆盖率证据：{expected}"]
    if _complete_status(document) and coverage.get("status") not in {"pass", "not_applicable"}:
        errors.append("完成状态需要通过或不适用的增量覆盖率")
    return errors


def _quality_errors(
    document: str,
    quality: Mapping[str, object],
    require_database_validation: bool,
) -> list[str]:
    errors = []
    if _complete_status(document) and quality.get("passed") is not True:
        errors.append("完成状态需要通过 Java quality Gate")
    final_gate = _section_body(document, "最终门禁")
    required_rows = (
        "Plan 与真实 Diff",
        "机械 Gate 与独立审查",
        "编译与相关测试",
        "数据库验证",
        "增量覆盖率",
    )
    for row in required_rows:
        match = re.search(
            rf"^\|\s*{re.escape(row)}\s*\|[^\n]*\|\s*([^|\n]+)\s*\|$",
            final_gate,
            re.MULTILINE,
        )
        if not match:
            errors.append(f"最终门禁缺少：{row}")
        elif _complete_status(document):
            accepted_results = {"通过"} if row == "数据库验证" and require_database_validation else {"通过", "不适用"}
            if match.group(1).strip() not in accepted_results:
                errors.append(f"完成状态的最终门禁未通过：{row}")
    return errors


def _repo_root(plan_path: Path) -> Path:
    resolved = plan_path.resolve()
    return next((parent for parent in resolved.parents if (parent / ".git").exists()), resolved.parent)


def _source_binding_errors(
    evidence: Mapping[str, object],
    plan_path: Path,
    label: str,
) -> list[str]:
    source_hashes = evidence.get("source_sha256")
    if not isinstance(source_hashes, dict):
        return [f"{label} evidence needs source_sha256"]
    repo = _repo_root(plan_path)
    errors = []
    for relative_path, expected_hash in source_hashes.items():
        if not isinstance(relative_path, str) or not isinstance(expected_hash, str):
            errors.append(f"{label} evidence has an invalid source hash entry")
            continue
        source_path = repo / relative_path
        if not source_path.is_file() or _sha256(source_path) != expected_hash:
            errors.append(f"{label} evidence is stale for {relative_path}")
    return errors


def _build_errors(
    build: Mapping[str, object],
    plan_path: Path,
    quality: Mapping[str, object],
    coverage: Mapping[str, object],
    require_passes: bool,
    require_database_validation: bool,
) -> list[str]:
    errors = []
    if build.get("plan_sha256") != _sha256(plan_path):
        errors.append("build evidence does not match the current Plan")
    quality_candidate = quality.get("candidate_sha256")
    coverage_candidate = coverage.get("candidate_sha256")
    if not isinstance(quality_candidate, str) or not quality_candidate:
        errors.append("quality evidence needs a candidate_sha256")
    if not isinstance(coverage_candidate, str) or not coverage_candidate:
        errors.append("coverage evidence needs a candidate_sha256")
    if build.get("quality_candidate_sha256") != quality_candidate:
        errors.append("build evidence does not match quality evidence")
    if build.get("coverage_candidate_sha256") != coverage_candidate:
        errors.append("build evidence does not match coverage evidence")
    started_at = build.get("started_at")
    if isinstance(started_at, bool) or not isinstance(started_at, (int, float)):
        errors.append("build evidence needs a numeric started_at")
    commands = build.get("commands")
    if not isinstance(commands, list):
        return errors + ["build evidence commands must be a list"]
    valid_commands = []
    for index, entry in enumerate(commands):
        if not isinstance(entry, dict):
            errors.append(f"build command {index} must be an object")
            continue
        if not isinstance(entry.get("command"), str) or not entry["command"].strip():
            errors.append(f"build command {index} needs the executed command")
        exit_code = entry.get("exit_code")
        if isinstance(exit_code, bool) or not isinstance(exit_code, int):
            errors.append(f"build command {index} needs an integer exit_code")
        finished_at = entry.get("finished_at")
        if (
            isinstance(started_at, (int, float))
            and not isinstance(started_at, bool)
            and (
                isinstance(finished_at, bool)
                or not isinstance(finished_at, (int, float))
                or finished_at < started_at
            )
        ):
            errors.append(f"build command {index} is not fresh")
        if (
            isinstance(finished_at, (int, float))
            and not isinstance(finished_at, bool)
            and isinstance(exit_code, int)
            and not isinstance(exit_code, bool)
        ):
            valid_commands.append((index, entry, float(finished_at)))
    if not require_passes:
        return errors
    required_commands = {"compile", "new_tests", "regression_tests"}
    if require_database_validation:
        required_commands.add("database_validation")
    errors.extend(_latest_required_command_errors(valid_commands, required_commands))
    return errors


def _latest_required_command_errors(
    valid_commands: Sequence[tuple[int, Mapping[str, object], float]],
    required: set[str],
) -> list[str]:
    latest_by_kind = {}
    for index, entry, finished_at in valid_commands:
        kind = entry.get("kind")
        if kind not in required:
            continue
        previous = latest_by_kind.get(kind)
        if previous is None or (finished_at, index) > (previous[0], previous[1]):
            latest_by_kind[kind] = (finished_at, index, entry)
    missing = sorted(required - set(latest_by_kind))
    errors = []
    if missing:
        errors.append(f"missing build evidence: {', '.join(missing)}")
    for kind in sorted(required & set(latest_by_kind)):
        if latest_by_kind[kind][2].get("exit_code") != 0:
            errors.append(f"latest build evidence failed: {kind}")
    return errors


def validate_execution(
    document: str,
    plan_text: str,
    plan_path: Path,
    quality: Mapping[str, object],
    coverage: Mapping[str, object],
    build: Mapping[str, object],
) -> list[str]:
    errors = _structure_errors(document)
    errors.extend(_task_errors(document, plan_text))
    errors.extend(_quality_errors(document, quality, _plan_has_sql(plan_text)))
    errors.extend(_coverage_errors(document, coverage))
    if quality.get("plan_sha256") != _sha256(plan_path):
        errors.append("quality evidence does not match the current Plan")
    errors.extend(_source_binding_errors(quality, plan_path, "quality"))
    errors.extend(_source_binding_errors(coverage, plan_path, "coverage"))
    errors.extend(
        _build_errors(
            build,
            plan_path,
            quality,
            coverage,
            require_passes=_complete_status(document),
            require_database_validation=_plan_has_sql(plan_text),
        )
    )
    return errors


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("execution", type=Path)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--quality-evidence", type=Path, required=True)
    parser.add_argument("--coverage-evidence", type=Path, required=True)
    parser.add_argument("--build-evidence", type=Path, required=True)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(arguments)
    try:
        document = args.execution.read_text(encoding="utf-8")
        plan_text = args.plan.read_text(encoding="utf-8")
        quality = _load_json(args.quality_evidence)
        coverage = _load_json(args.coverage_evidence)
        build = _load_json(args.build_evidence)
        errors = validate_execution(document, plan_text, args.plan, quality, coverage, build)
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
