#!/usr/bin/env python3
"""Validate the standalone pretty-writing-plan document contract."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REQUIRED_SECTIONS = (
    "## 实施结论",
    "## 实施任务",
    "## 文件变更总览",
    "## 测试与验证",
    "## 共享约束和代码事实",
)
TASK_PATTERN = re.compile(r"^###\s+.+[（(]TASK-(\d{3})[）)]\s*$", re.MULTILINE)
PERSONAL_ABSOLUTE_PATH = re.compile(
    r"(?:^|[\s`(])/(?:Users|home|private/(?:tmp|var))/|\b[A-Z]:\\"
)
PLACEHOLDER = re.compile(
    r"<(?:主题|module|目的|真实[^>]*|一句[^>]*|2–3 句[^>]*|path|command|test-command|"
    r"repo-root|skill-dir|[^>\n]*\.\.\.[^>\n]*)>"
)
FORBIDDEN_WORDS = re.compile(r"\b(?:TODO|TBD|FIXME)\b", re.IGNORECASE)
TRACE_ID = re.compile(r"\b(?:REQ|AC|DEC)-\d+\b")
EXTERNAL_DEPENDENCY = re.compile(
    r"REQUIRED\s+SUB-SKILL|pretty-java-spring-core|\bsuperpowers:[a-z0-9-]+",
    re.IGNORECASE,
)


def line_number(text: str, index: int) -> int:
    return text.count("\n", 0, max(index, 0)) + 1


def check_standard_path(plan_path: Path, errors: list[str]) -> None:
    parts = plan_path.resolve().parts
    if len(parts) < 4 or parts[-1] != "plan.md" or parts[-3] != "pretty":
        errors.append("path: expected docs/pretty/<topic>/plan.md")
        return

    topic = parts[-2]
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", topic):
        errors.append(
            f"path: topic '{topic}' must use lowercase kebab-case"
        )

    docs_index = None
    for index, part in enumerate(parts[:-3]):
        if part == "docs":
            docs_index = index
    if docs_index is None or tuple(parts[docs_index : docs_index + 2]) != (
        "docs",
        "pretty",
    ):
        errors.append("path: expected a docs/pretty directory")


def check_required_sections(text: str, errors: list[str]) -> None:
    positions = []
    for section in REQUIRED_SECTIONS:
        index = text.find(section)
        if index < 0:
            errors.append(f"structure: missing section '{section[3:]}'")
        else:
            positions.append((index, section))

    if len(positions) == len(REQUIRED_SECTIONS):
        actual = [section for _, section in sorted(positions)]
        if actual != list(REQUIRED_SECTIONS):
            errors.append(
                "structure: fixed sections must appear in the order "
                "实施结论 → 实施任务 → 文件变更总览 → 测试与验证 → 共享约束和代码事实"
            )

    for field in ("**Goal:**", "**Architecture:**", "**Tech Stack:**"):
        if field not in text:
            errors.append(f"header: missing '{field}'")

    conclusion_start = text.find("## 实施结论")
    task_start = text.find("## 实施任务")
    if conclusion_start >= 0 and task_start > conclusion_start:
        conclusion = text[conclusion_start:task_start]
        if "### 链路级分析" not in conclusion:
            errors.append(
                "structure: 实施结论 must contain '链路级分析' "
                "(write 不适用 with a reason for a single-module plan)"
            )


def check_forbidden_content(text: str, errors: list[str]) -> None:
    checks = (
        (FORBIDDEN_WORDS, "placeholder or TODO marker"),
        (TRACE_ID, "REQ/AC/DEC trace identifier"),
        (EXTERNAL_DEPENDENCY, "external skill dependency"),
        (PERSONAL_ABSOLUTE_PATH, "personal absolute path"),
        (PLACEHOLDER, "unresolved placeholder"),
    )
    for pattern, label in checks:
        match = pattern.search(text)
        if match:
            errors.append(
                f"content: {label} at line {line_number(text, match.start())}: "
                f"{match.group(0)!r}"
            )

    # An ellipsis in prose or a code block can hide unplanned implementation.
    # Java varargs are allowed when the line is an actual method signature.
    for index, line in enumerate(text.splitlines(), start=1):
        if "..." not in line:
            continue
        if re.search(r"\b\w+\.\.\.\s+\w+", line) and "```" not in line:
            continue
        errors.append(f"content: ellipsis at line {index}")
        break


def task_ranges(text: str) -> list[tuple[int, int, int]]:
    matches = list(TASK_PATTERN.finditer(text))
    ranges: list[tuple[int, int, int]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        next_section = text.find("\n## ", match.end())
        if next_section >= 0:
            end = min(end, next_section)
        ranges.append((int(match.group(1)), match.start(), end))
    return ranges


def check_tasks(text: str, errors: list[str]) -> int:
    ranges = task_ranges(text)
    if not ranges:
        errors.append("tasks: no TASK heading matching (TASK-001) was found")
        return 0

    expected = list(range(1, len(ranges) + 1))
    actual = [task_id for task_id, _, _ in ranges]
    if actual != expected:
        errors.append(
            f"tasks: TASK ids must be continuous from TASK-001; found {actual}"
        )

    for task_id, start, end in ranges:
        segment = text[start:end]
        prefix = f"TASK-{task_id:03d}"
        if "- [ ]" not in segment:
            errors.append(f"tasks: {prefix} has no checkbox step")

        is_mechanical = "机械任务" in segment or "完整机械变更" in segment
        if is_mechanical:
            if "完整机械变更" not in segment:
                errors.append(f"tasks: {prefix} mechanical task lacks full change content")
            if not re.search(r"验证|不变量|静态检查", segment):
                errors.append(f"tasks: {prefix} mechanical task lacks deterministic verification")
            continue

        required_headings = (
            "#### 核心生产代码",
            "#### 核心测试代码",
            "#### TDD 与验证设计",
            "#### 质量审查",
        )
        for heading in required_headings:
            if heading not in segment:
                errors.append(f"tasks: {prefix} missing '{heading[5:]}'")

        production_start = segment.find("#### 核心生产代码")
        test_start = segment.find("#### 核心测试代码")
        quality_start = segment.find("#### 质量审查")
        if production_start >= 0 and test_start > production_start:
            production = segment[production_start:test_start]
            if "```java" not in production:
                errors.append(f"tasks: {prefix} production section lacks a Java code block")
        if test_start >= 0:
            test_end = quality_start if quality_start > test_start else len(segment)
            tests = segment[test_start:test_end]
            if "```java" not in tests:
                errors.append(f"tasks: {prefix} test section lacks a Java code block")

        if not re.search(r"\bRED\b", segment) or not re.search(r"\bGREEN\b", segment):
            errors.append(f"tasks: {prefix} must describe both RED and GREEN")


def validate_plan(plan_path: Path) -> list[str]:
    errors: list[str] = []
    if not plan_path.exists():
        return [f"file: not found: {plan_path}"]
    if not plan_path.is_file():
        return [f"file: not a regular file: {plan_path}"]

    try:
        text = plan_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return [f"file: expected UTF-8 text: {exc}"]

    check_standard_path(plan_path, errors)
    check_required_sections(text, errors)
    check_forbidden_content(text, errors)
    check_tasks(text, errors)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate docs/pretty/<topic>/plan.md for pretty-writing-plan."
    )
    parser.add_argument("plan", type=Path, help="Plan path to validate")
    args = parser.parse_args()

    errors = validate_plan(args.plan)
    if errors:
        print("Plan validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    task_count = len(task_ranges(args.plan.read_text(encoding="utf-8")))
    print(f"Plan is valid: {args.plan} ({task_count} task(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
