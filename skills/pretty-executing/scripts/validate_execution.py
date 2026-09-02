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
    "- 构建验证：",
    "- 覆盖率范围：",
    "- 测试覆盖率：",
)
ALLOWED_STATUS = ("完成", "已满足（无生产差异）", "停止", "返回 PRD", "返回 Design")


def validate(document: str) -> list[str]:
    errors = [f"missing heading: {heading}" for heading in REQUIRED_HEADINGS if heading not in document]
    if re.search(r"<[^>]+>", document):
        errors.append("execution report still contains template placeholders")
    for status in re.findall(r"^-\s*状态：`([^`]+)`", document, re.MULTILINE):
        if "/" not in status and not any(
            status == allowed or status.startswith(allowed + "：") for allowed in ALLOWED_STATUS
        ):
            errors.append(f"unsupported execution status: {status}")
    if "### TASK-" not in document:
        errors.append("execution report needs at least one TASK result")
    missing_fields = [field for field in REQUIRED_FIELDS if field not in document]
    if missing_fields:
        errors.append("execution report is missing fields: " + ", ".join(missing_fields))
    conclusion = document.partition("## 结论与恢复点")[2]
    if not re.search(r"^-\s*状态：`[^`]+`", conclusion, re.MULTILINE):
        errors.append("execution report needs a conclusion status")
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
