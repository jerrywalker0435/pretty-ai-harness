#!/usr/bin/env python3
"""Validate the required structure of an E2E result report."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


SCENARIO = re.compile(r"^\|\s*S\d+\b.*\|", re.MULTILINE)
DETAIL_SCENARIO = re.compile(r"^###\s+(S\d+)\b.*$", re.MULTILINE)
STATUS = re.compile(r"通过|失败|跳过|未执行|暂不执行")
REQUIRED_SECTIONS = ("## 场景总览", "## 场景详情", "## 未验证范围", "## 测试总结")
DETAIL_FIELDS = ("前置条件：", "数据副作用：", "结果：", "关键断言：", "清理结果：")
COMMAND_FIELD = re.compile(r"命令或脚本(?:（[^）]*）)?：\s*```(?:bash|sh|shell)?\s*[\s\S]*?```", re.MULTILINE)
FORMATTED_JSON = re.compile(r"返回值 JSON：\s*```json\s*\{[\s\S]*?\}\s*```", re.MULTILINE)


def validate(report: Path) -> list[str]:
    if not report.is_file():
        return [f"报告不存在：{report}"]
    content = report.read_text(encoding="utf-8")
    errors = [f"缺少章节：{section}" for section in REQUIRED_SECTIONS if section not in content]
    scenario_rows = SCENARIO.findall(content)
    if not scenario_rows:
        errors.append("场景总览至少需要一行 S<数字> 场景")
    elif not any(STATUS.search(row) for row in scenario_rows):
        errors.append("场景总览必须包含通过、失败、跳过或未执行状态")
    if "## 场景详情" in content and not any(field in content for field in DETAIL_FIELDS):
        errors.append("场景详情必须包含前置条件、数据副作用、结果、关键断言或清理结果")
    details = list(DETAIL_SCENARIO.finditer(content))
    if scenario_rows and not details:
        errors.append("每个场景必须在场景详情中有对应的 ### S<数字> 小节")
    for index, detail in enumerate(details):
        end = details[index + 1].start() if index + 1 < len(details) else len(content)
        block = content[detail.start():end]
        scenario_id = detail.group(1)
        if not COMMAND_FIELD.search(block):
            errors.append(f"场景 {scenario_id} 必须包含可单独执行的命令或脚本")
        if not FORMATTED_JSON.search(block):
            errors.append(f"场景 {scenario_id} 必须包含格式化的返回值 JSON")
    if "## 未验证范围" in content:
        section = content.split("## 未验证范围", 1)[1].split("## 测试总结", 1)[0]
        if not section.strip():
            errors.append("未验证范围不能是空章节")
    return errors


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args(arguments)
    errors = validate(args.report)
    if errors:
        for error in errors:
            print(f"E2E 报告校验失败：{error}", file=sys.stderr)
        return 1
    print(f"E2E 报告校验通过：{args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
