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
CONTRACT_REFERENCE_PATTERN = re.compile(r"(?:REQ|AC)-\d+", re.IGNORECASE)
FORBIDDEN_HEADINGS = ("约束与未决问题", "未决问题")
PLACEHOLDER_PATTERN = re.compile(
    r"<[^>\n]+>|\b(?:TODO|TBD|FIXME)\b|待用户选择|待确认|未澄清",
    re.IGNORECASE,
)
FLOW_PATTERN = re.compile(r"```mermaid\s+(?:flowchart|graph|stateDiagram(?:-v2)?)\b", re.IGNORECASE)
HANDOFF_STATUS_PATTERN = re.compile(
    r"^-\s*定位状态：\s*`?已核验`?\s*$", re.MULTILINE
)
HANDOFF_LOCATOR_PATTERN = re.compile(
    r"(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.$-]+\.[A-Za-z0-9_-]+#"
    r"[A-Za-z_$][A-Za-z0-9_.$]*(?:\([^`\n]*\))?"
)
HANDOFF_TABLE_HEADER = ("REQ/AC", "当前公共行为入口", "当前公共验证入口")


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


def _table_cells(line: str) -> list[str] | None:
    stripped = line.strip()
    if not (stripped.startswith("|") and stripped.endswith("|")):
        return None
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def _handoff_rows(body: str) -> tuple[list[list[str]], bool]:
    lines = body.splitlines()
    for index, line in enumerate(lines):
        cells = _table_cells(line)
        if cells != list(HANDOFF_TABLE_HEADER):
            continue
        if index + 1 >= len(lines) or _table_cells(lines[index + 1]) is None:
            return [], True
        rows: list[list[str]] = []
        for candidate in lines[index + 2 :]:
            cells = _table_cells(candidate)
            if cells is None:
                break
            if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                continue
            rows.append(cells)
        return rows, True
    return [], False


def _handoff_locator_valid(value: str) -> bool:
    normalized = value.strip().strip("`")
    if normalized == "未获取":
        return True
    path = normalized.split("#", 1)[0]
    if any(part == ".." for part in path.split("/")):
        return False
    return bool(HANDOFF_LOCATOR_PATTERN.fullmatch(normalized))


def _design_handoff_errors(document: str) -> list[str]:
    if "## Design 交接" not in document.splitlines():
        return []
    body = section_body(document, "Design 交接")
    errors: list[str] = []
    status_match = HANDOFF_STATUS_PATTERN.search(body)
    if status_match is None:
        return ["Design 交接必须声明定位状态：已核验"]

    rows, has_table = _handoff_rows(body)
    if not has_table or not rows:
        return ["Design 交接为已核验时必须提供至少一条定位表记录"]

    defined_req = set(re.findall(r"^###\s+(REQ-\d{3})：", document, re.MULTILINE))
    defined_ac = set(re.findall(r"^###\s+(AC-\d{3})：", document, re.MULTILINE))
    has_locator = False
    for row in rows:
        if len(row) != 3:
            errors.append("Design 交接定位表每行必须有 REQ/AC、行为入口、验证入口三列")
            continue
        req_refs = set(re.findall(r"\bREQ-\d{3}\b", row[0]))
        ac_refs = set(re.findall(r"\bAC-\d{3}\b", row[0]))
        if not req_refs or not ac_refs:
            errors.append("Design 交接定位表每行必须关联至少一个 REQ-* 和 AC-*")
        unknown = (req_refs - defined_req) | (ac_refs - defined_ac)
        if unknown:
            errors.append("Design 交接引用了不存在的需求或验收编号：" + ", ".join(sorted(unknown)))
        for label, value in zip(("公共行为入口", "公共验证入口"), row[1:]):
            if not _handoff_locator_valid(value):
                errors.append(f"Design 交接的{label}必须是仓库 path#symbol 或“未获取”")
            elif value.strip().strip("`") != "未获取":
                has_locator = True
    if not has_locator:
        errors.append("Design 交接为已核验时至少需要一个 path#symbol")
    return sorted(set(errors))


def validate_prd_document(document: str) -> list[str]:
    """Return deterministic structural errors for a final PRD."""
    headings = section_headings(document)
    errors: list[str] = []
    errors.extend(f"缺少章节：{section}" for section in REQUIRED_SECTIONS if section not in headings)
    errors.extend(f"禁止章节：{heading}" for heading in FORBIDDEN_HEADINGS if heading in headings)
    if PLACEHOLDER_PATTERN.search(document):
        errors.append("PRD 仍包含占位内容或未澄清项")
    if CONTRACT_REFERENCE_PATTERN.search(section_body(document, "用户与场景")):
        errors.append("用户与场景禁止引用需求编号或验收编号，请直接描述业务触发和可观察结果")
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
    errors.extend(_design_handoff_errors(document))
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
