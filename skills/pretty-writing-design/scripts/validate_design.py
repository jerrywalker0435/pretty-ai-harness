#!/usr/bin/env python3
"""Validate the deterministic structure of a Pretty Design."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Sequence


REQUIRED_SECTIONS = (
    "设计结论",
    "方案全景",
    "关键设计与权衡",
    "设计边界",
    "验证与风险",
)
FORBIDDEN_HEADINGS = ("覆盖需求", "需求覆盖")
PLACEHOLDER_PATTERN = re.compile(
    r"<[^>\n]+>|\b(?:TODO|TBD|FIXME)\b|待定|待确认|未决|待澄清",
    re.IGNORECASE,
)
MERMAID_BLOCK_PATTERN = re.compile(
    r"```mermaid\s*\n(?P<body>.*?)```", re.IGNORECASE | re.DOTALL
)
MERMAID_START_PATTERN = re.compile(
    r"^(?:flowchart|graph|sequenceDiagram|stateDiagram(?:-v2)?|classDiagram|erDiagram)\b",
    re.IGNORECASE,
)


def section_headings(document: str) -> list[str]:
    """Return level-two headings in document order."""
    return [line[3:].strip() for line in document.splitlines() if line.startswith("## ")]


def validate_mermaid_blocks(document: str) -> list[str]:
    """Return errors for empty or unsupported Mermaid blocks."""
    errors: list[str] = []
    for block in MERMAID_BLOCK_PATTERN.finditer(document):
        lines = [line.strip() for line in block.group("body").splitlines() if line.strip()]
        if not lines:
            errors.append("Mermaid 图块不能为空")
        elif not MERMAID_START_PATTERN.match(lines[0]):
            errors.append("Mermaid 图块必须声明 flowchart、sequenceDiagram、stateDiagram、classDiagram 或 erDiagram")
    return errors


def validate_design_document(document: str) -> list[str]:
    """Return deterministic structural errors for a final Design."""
    headings = section_headings(document)
    errors: list[str] = []
    errors.extend(f"缺少章节：{section}" for section in REQUIRED_SECTIONS if section not in headings)
    errors.extend(f"禁止章节：{heading}" for heading in FORBIDDEN_HEADINGS if heading in headings)
    if PLACEHOLDER_PATTERN.search(document):
        errors.append("Design 仍包含占位内容或未决项")
    errors.extend(validate_mermaid_blocks(document))
    return errors


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("design", type=Path, help="Design 文件路径")
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(arguments)
    try:
        document = args.design.read_text(encoding="utf-8")
    except OSError as error:
        print(f"读取 Design 失败：{error}", file=sys.stderr)
        return 2
    errors = validate_design_document(document)
    if errors:
        for error in errors:
            print(f"错误：{error}", file=sys.stderr)
        return 1
    print("Design 结构校验：通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
