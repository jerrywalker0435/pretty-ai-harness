#!/usr/bin/env python3
"""Validate the deterministic structure of a Pretty PRD."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Sequence


REQUIRED_SECTIONS = (
    "背景与问题",
    "目标与非目标",
    "用户与场景",
    "需求",
    "验收标准",
)
REQ_HEADING = re.compile(r"^REQ-\d{3}：\S.+$")
AC_HEADING = re.compile(r"^AC-\d{3}：\S.+$")
FORBIDDEN_HEADINGS = ("约束与未决问题", "未决问题")
PLACEHOLDER_PATTERN = re.compile(
    r"<[^>\n]+>|\b(?:TODO|TBD|FIXME)\b|待用户选择|待确认|未澄清",
    re.IGNORECASE,
)
FLOW_PATTERN = re.compile(r"```mermaid\s+(?:flowchart|graph|stateDiagram(?:-v2)?)\b", re.IGNORECASE)


def section_headings(document: str) -> list[str]:
    """Return level-two headings in document order."""
    return [line[3:].strip() for line in document.splitlines() if line.startswith("## ")]


def section_body(document: str, heading: str) -> str:
    """Return the body of one level-two heading."""
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


def validate_prd_document(document: str) -> list[str]:
    """Return deterministic structural errors for a final PRD."""
    headings = section_headings(document)
    errors: list[str] = []
    errors.extend(f"缺少章节：{section}" for section in REQUIRED_SECTIONS if section not in headings)
    errors.extend(f"禁止章节：{heading}" for heading in FORBIDDEN_HEADINGS if heading in headings)
    if PLACEHOLDER_PATTERN.search(document):
        errors.append("PRD 仍包含占位内容或未澄清项")
    requirement_headings = [line[4:].strip() for line in document.splitlines() if line.startswith("### REQ-")]
    acceptance_headings = [line[4:].strip() for line in document.splitlines() if line.startswith("### AC-")]
    if not requirement_headings:
        errors.append("PRD 至少需要一个 REQ-* 需求")
    if not acceptance_headings:
        errors.append("PRD 至少需要一个 AC-* 验收标准")
    if any(not REQ_HEADING.fullmatch(heading) for heading in requirement_headings):
        errors.append("REQ-* 必须使用连续三位编号和非空标题")
    if any(not AC_HEADING.fullmatch(heading) for heading in acceptance_headings):
        errors.append("AC-* 必须使用连续三位编号和非空标题")
    if _numbers(requirement_headings, "REQ") != list(range(1, len(requirement_headings) + 1)):
        errors.append("REQ-* 编号必须从 001 连续递增")
    if _numbers(acceptance_headings, "AC") != list(range(1, len(acceptance_headings) + 1)):
        errors.append("AC-* 编号必须从 001 连续递增")
    flow = section_body(document, "核心用例流程（可选）")
    if flow and not FLOW_PATTERN.search(flow):
        errors.append("核心用例流程必须使用业务流程图格式")
    return errors


def _numbers(headings: list[str], prefix: str) -> list[int]:
    numbers = []
    for heading in headings:
        match = re.match(rf"{prefix}-(\d{{3}})：", heading)
        if match:
            numbers.append(int(match.group(1)))
    return numbers


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prd", type=Path, help="PRD 文件路径")
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(arguments)
    try:
        document = args.prd.read_text(encoding="utf-8")
    except OSError as error:
        print(f"读取 PRD 失败：{error}", file=sys.stderr)
        return 2
    errors = validate_prd_document(document)
    if errors:
        for error in errors:
            print(f"错误：{error}", file=sys.stderr)
        return 1
    print("PRD 结构校验：通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
