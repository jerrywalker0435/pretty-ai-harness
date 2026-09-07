#!/usr/bin/env python3
"""Validate the structure and completed fields of an execution.md report."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Sequence


REQUIRED_HEADINGS = (
    "## TASK 结果",
    "## 审查与验证",
    "## 未验证范围",
    "## 结论与恢复点",
)
REQUIRED_FIELDS = (
    "- 实际落点：",
    "- 行为证据：",
    "- 审查：",
    "- 质量门禁：",
    "- 限定修复：",
    "- 质量例外：",
    "- 构建验证：",
    "- 覆盖率范围：",
    "- 测试覆盖率：",
)
ALLOWED_STATUS = ("完成", "已满足（无生产差异）", "停止", "返回 PRD", "返回 Design")
COMPLETED_STATUS = ("完成", "已满足（无生产差异）")
QUALITY_GATE = re.compile(
    r"^-\s*质量门禁：`clean-code-guard "
    r"found=(\d+) fixed=(\d+) exception=(\d+) open=(\d+)`\s*$",
    re.MULTILINE,
)
COVERAGE = re.compile(r"^-\s*测试覆盖率：`增量行覆盖率\s+([^%，]+)%.*?分支覆盖率\s+([^%`]+)%", re.MULTILINE)


def _field_value(document: str, field: str) -> str | None:
    match = re.search(rf"^-\s*{re.escape(field)}：`([^`]*)`\s*$", document, re.MULTILINE)
    return match.group(1).strip() if match else None


def _conclusion_status(document: str) -> str | None:
    conclusion = document.partition("## 结论与恢复点")[2]
    match = re.search(r"^-\s*状态：`([^`]+)`", conclusion, re.MULTILINE)
    return match.group(1) if match else None


def _matches_status(status: str, allowed: str) -> bool:
    return status == allowed or status.startswith(allowed + "：")


def _is_completed_status(status: str | None) -> bool:
    return status is not None and any(_matches_status(status, completed) for completed in COMPLETED_STATUS)


def _quality_count_errors(document: str, counts: tuple[int, int, int, int]) -> list[str]:
    found, fixed, exception_count, open_count = counts
    errors: list[str] = []
    if found != fixed + exception_count + open_count:
        errors.append("quality gate counts are inconsistent")
    conclusion_status = _conclusion_status(document)
    if _is_completed_status(conclusion_status) and open_count:
        errors.append("completed execution cannot contain open quality findings")
    return errors


def _quality_evidence_errors(document: str, fixed: int, exception_count: int) -> list[str]:
    errors: list[str] = []
    repair = _field_value(document, "限定修复")
    if repair is None:
        errors.append("bounded repair field must use backtick value format")
    elif fixed and repair in {"", "无"}:
        errors.append("fixed quality findings need bounded repair evidence")
    exception_detail = _field_value(document, "质量例外")
    if exception_detail is None:
        errors.append("quality exception field must use backtick value format")
    elif exception_count and exception_detail in {"", "无"}:
        errors.append("quality exceptions need contract evidence and a revisit trigger")
    elif not exception_count and exception_detail != "无":
        errors.append("quality exception detail must be 无 when exception=0")
    return errors


def _quality_gate_errors(document: str) -> list[str]:
    match = QUALITY_GATE.search(document)
    if not match:
        return ["quality gate result has an unsupported format"]
    counts = tuple(int(count_text) for count_text in match.groups())
    return [
        *_quality_count_errors(document, counts),
        *_quality_evidence_errors(document, counts[1], counts[2]),
    ]


def _coverage_errors(document: str) -> list[str]:
    status = _conclusion_status(document)
    if not _is_completed_status(status):
        return []
    match = COVERAGE.search(document)
    if not match:
        return ["completed execution needs parseable coverage results"]
    try:
        line, branch = float(match.group(1)), float(match.group(2))
    except ValueError:
        return ["completed execution needs numeric coverage results"]
    errors = []
    if line < 90:
        errors.append(f"completed execution has incremental line coverage below 90%: {line:.2f}%")
    if branch < 80:
        errors.append(f"completed execution has incremental branch coverage below 80%: {branch:.2f}%")
    return errors


def validate(document: str) -> list[str]:
    errors = [f"missing heading: {heading}" for heading in REQUIRED_HEADINGS if heading not in document]
    if re.search(r"<[^>]+>", document):
        errors.append("execution report still contains template placeholders")
    for status in re.findall(r"^-\s*状态：`([^`]+)`", document, re.MULTILINE):
        if not any(_matches_status(status, allowed) for allowed in ALLOWED_STATUS):
            errors.append(f"unsupported execution status: {status}")
    if "### TASK-" not in document:
        errors.append("execution report needs at least one TASK result")
    missing_fields = [field for field in REQUIRED_FIELDS if field not in document]
    if missing_fields:
        errors.append("execution report is missing fields: " + ", ".join(missing_fields))
    if _conclusion_status(document) is None:
        errors.append("execution report needs a conclusion status")
    errors.extend(_quality_gate_errors(document))
    errors.extend(_coverage_errors(document))
    return errors


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="execution.md 路径")
    args = parser.parse_args(arguments)
    try:
        errors = validate(args.file.read_text(encoding="utf-8"))
    except OSError as error:
        print(f"Execution report cannot be read: {error}", file=sys.stderr)
        return 2
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    print("Execution report: valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
