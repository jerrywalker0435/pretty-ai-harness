#!/usr/bin/env python3
"""Validate the deterministic structure of a Pretty Execution report."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable, Sequence


REQUIRED_SECTIONS = (
    "执行起点",
    "基线",
    "TASK 结果",
    "最终门禁",
    "未验证范围",
    "结论与恢复点",
)
TASK_PATTERN = re.compile(r"TASK-\d+")
HEAD_PATTERN = re.compile(r"起始 HEAD：\s*`?([0-9a-f]{7,64})`?", re.IGNORECASE)
PLAN_BASIS_PATTERN = re.compile(
    r"^[-*]\s*执行依据：\s*当前工作区最新\s+`?Plan`?\s*$", re.MULTILINE
)
LEGACY_INPUT_PATH_PATTERN = re.compile(
    r"^[-*]\s*(?:PRD|Design|Plan)：\s*`[^`]+`\s*$", re.MULTILINE
)
FINAL_STATUS_PATTERN = re.compile(
    r"^-\s*状态：\s*`?(完成|停止：[^`\n]+|返回(?: PRD| Design| Plan)：[^`\n]+)`?\s*$",
    re.MULTILINE,
)
PLACEHOLDER_PATTERN = re.compile(
    r"<[^>\n]+>|\bTODO\b|\bTBD\b|待验证|待审计|执行中|\.\.\.",
    re.IGNORECASE,
)


def section_headings(document: str) -> list[str]:
    """Return level-two headings in document order."""
    return [line[3:].strip() for line in document.splitlines() if line.startswith("## ")]


def section_body(document: str, heading: str) -> str:
    """Return the content belonging to one level-two heading."""
    lines = document.splitlines()
    marker = f"## {heading}"
    try:
        start = lines.index(marker) + 1
    except ValueError:
        return ""
    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return "\n".join(lines[start:end])


def extract_task_ids(document: str) -> set[str]:
    """Extract stable TASK identities from a Plan or Execution report."""
    return set(TASK_PATTERN.findall(document))


def _missing_sections(headings: Sequence[str]) -> list[str]:
    return [section for section in REQUIRED_SECTIONS if section not in headings]


def _duplicate_sections(headings: Sequence[str]) -> list[str]:
    return sorted({section for section in headings if headings.count(section) > 1})


def _validate_final_status(document: str, allow_in_progress: bool) -> list[str]:
    if allow_in_progress:
        return []
    conclusion = section_body(document, "结论与恢复点")
    if not FINAL_STATUS_PATTERN.search(conclusion):
        return ["结论与恢复点必须包含合法的最终状态"]
    return []


def _validate_task_coverage(document: str, expected: Iterable[str] | None) -> list[str]:
    if expected is None:
        return []
    missing = sorted(set(expected) - extract_task_ids(document))
    if not missing:
        return []
    return [f"Execution 缺少 Plan TASK：{', '.join(missing)}"]


def validate_execution_document(
    document: str,
    expected_task_ids: Iterable[str] | None = None,
    allow_in_progress: bool = False,
) -> list[str]:
    """Return deterministic structural errors for an Execution report."""
    headings = section_headings(document)
    errors: list[str] = []
    errors.extend(f"缺少章节：{name}" for name in _missing_sections(headings))
    errors.extend(f"重复章节：{name}" for name in _duplicate_sections(headings))
    if not allow_in_progress and PLACEHOLDER_PATTERN.search(document):
        errors.append("最终 Execution 报告仍包含占位内容")
    if not HEAD_PATTERN.search(document):
        errors.append("执行起点缺少有效的起始 HEAD")
    if not PLAN_BASIS_PATTERN.search(document):
        errors.append("执行起点必须记录当前工作区最新 Plan 作为执行依据")
    if LEGACY_INPUT_PATH_PATTERN.search(document):
        errors.append("执行起点不应记录 PRD、Design 或 Plan 路径")
    errors.extend(_validate_final_status(document, allow_in_progress))
    errors.extend(_validate_task_coverage(document, expected_task_ids))
    return errors


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("execution", type=Path, help="Execution 报告路径")
    parser.add_argument("--plan", type=Path, help="可选的 Plan 路径，用于核对 TASK")
    parser.add_argument("--allow-in-progress", action="store_true", help="允许执行中的占位内容")
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(arguments)
    try:
        document = args.execution.read_text(encoding="utf-8")
    except OSError as error:
        print(f"读取 Execution 失败：{error}", file=sys.stderr)
        return 2
    expected = None
    if args.plan:
        try:
            expected = extract_task_ids(args.plan.read_text(encoding="utf-8"))
        except OSError as error:
            print(f"读取 Plan 失败：{error}", file=sys.stderr)
            return 2
    errors = validate_execution_document(document, expected, args.allow_in_progress)
    if errors:
        for error in errors:
            print(f"错误：{error}", file=sys.stderr)
        return 1
    print("Execution 报告结构：通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
