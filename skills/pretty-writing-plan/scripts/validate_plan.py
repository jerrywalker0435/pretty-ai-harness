#!/usr/bin/env python3
"""Validate the current, read-only pretty-writing-plan document contract."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import NamedTuple


TASKS_SECTION = "## 实施任务"
CHAIN_SECTION = "## 变更链路"
TOP_LEVEL_SECTIONS = {CHAIN_SECTION, TASKS_SECTION}
TASK_PATTERN = re.compile(r"^###\s+TASK-(\d{3})[：:][ \t]*.+$", re.MULTILINE)
TOP_LEVEL_PATTERN = re.compile(r"^##\s+.+$", re.MULTILINE)
TITLE_PATTERN = re.compile(r"^#\s+.+\s+Implementation Plan\s*$", re.MULTILINE)
MERMAID_START_PATTERN = re.compile(
    r"^(?:flowchart|sequenceDiagram|stateDiagram-v2)\b", re.IGNORECASE
)
FILES_HEADING = re.compile(r"^\*\*Files:\*\*[ \t]*$", re.MULTILINE)
FILE_ENTRY = re.compile(
    r"^\s*[-*+]\s+(Create|Modify|Test|Delete):\s+`([^`\n]+)`\s*$",
    re.MULTILINE,
)
LABEL_PATTERN = re.compile(r"^(约束|修改|测试|依赖)：[ \t]*$", re.MULTILINE)
DEPRECATED_METADATA = re.compile(
    r"^(?:编排级别|判定依据)：", re.MULTILINE
)
DEPRECATED_PATH_TABLE = re.compile(
    r"^\|\s*仓库相对路径\s*\|\s*(?:symbol|目标)\s*\|\s*修改目的\s*\|\s*$",
    re.MULTILINE,
)
DEPRECATED_CHAIN_TABLE = re.compile(
    r"^\|\s*顺序/分支\s*\|", re.MULTILINE
)
PERSONAL_ABSOLUTE_PATH = re.compile(
    r"(?:^|[\s`(])/(?:Users|home|private/(?:tmp|var))/|\b[A-Z]:\\"
)
PLACEHOLDER = re.compile(
    r"<(?:主题|单模块[^>]*|领域结果[^>]*|声明或结构变更结果[^>]*|目的|仓库相对路径|"
    r"可观察[^>]*|展示[^>]*|仅在依赖[^>]*|"
    r"完整[^>]*|真实[^>]*|一句[^>]*|2–3 句[^>]*|"
    r"module|path|command|"
    r"test-command|repo-root|skill-dir|[^>\n]*\.\.\.[^>\n]*)>",
    re.IGNORECASE,
)
FORBIDDEN_WORDS = re.compile(r"\b(?:TODO|TBD|FIXME)\b", re.IGNORECASE)
TRACE_ID = re.compile(r"\b(?:REQ|AC|DEC)-\d+\b")
EXTERNAL_DEPENDENCY = re.compile(
    r"REQUIRED\s+SUB-SKILL|\$?(?:codebase-design|121-java-object-oriented-design|"
    r"122-java-type-design|solid-principles|design-patterns|clean-code|"
    r"superpowers:writing-plans|clean-code-guard|java-code-review|springboot-tdd)",
    re.IGNORECASE,
)
GENERIC_EXTERNAL_SKILL = re.compile(
    r"(?<![\w$])\$[a-z][a-z0-9-]*(?::[a-z0-9-]+)?\b",
    re.IGNORECASE,
)
DEPRECATED_PLAN_PROSE = re.compile(
    r"(?:\bTDD\b|\bRED\b\s*(?:→|->)|\bGREEN\b\s*(?:→|->)|"
    r"\bREFACTOR\b\s*(?:→|->)|覆盖率(?:目标)?|验证(?:命令|目标)|"
    r"完成证据|执行结果|执行交接|(?:交给|移交给)\s*Execution|"
    r"Execution\s*(?:阶段|负责|执行)|(?:\./)?mvnw?\s+[^`\n]{0,80}\b(?:test|verify)\b|"
    r"(?:\./)?gradlew?\s+[^`\n]{0,80}\b(?:test|check)\b|"
    r"\b(?:pytest|npm\s+test|pnpm\s+test|yarn\s+test)\b)",
    re.IGNORECASE,
)
H1_PATTERN = re.compile(r"^#(?!#)\s+.+$", re.MULTILINE)
DEPRECATED_HEADER_FIELD = re.compile(
    r"^\s*\*\*(?:Goal|Architecture|Tech Stack):\*\*",
    re.IGNORECASE | re.MULTILINE,
)
DEPRECATED_PLAN_STRUCTURE = re.compile(
    r"^(?:"
    r"\s*#{2,6}\s+(?:实施结论|文件变更总览|测试与验证|共享约束和代码事实|"
    r"质量审查|TDD\s*与验证设计|完成证据|验证命令|执行结果|"
    r"核心生产代码|核心测试代码|完整变更内容)\s*"
    r"|\s*\*\*(?:完成证据|验证命令|覆盖率(?:目标)?|执行结果|状态)[：:]\*\*"
    r"|\s*[-*+]\s+\[[ xX]\]"
    r"|\s*(?:\*\*)?(?:RED|GREEN|REFACTOR)(?:\*\*)?\s*(?:[：:]|→|->)"
    r")",
    re.IGNORECASE | re.MULTILINE,
)
SILENT_NULL_TERNARY = re.compile(r"==\s*null\s*\?\s*null\s*:")
OR_ELSE_NULL = re.compile(r"\.orElse\s*\(\s*null\s*\)")
BROAD_CATCH_FALLBACK = re.compile(
    r"catch\s*\(\s*(?:Exception|RuntimeException|Throwable)\b[^)]*\)\s*\{"
    r"(?:(?!\}).){0,800}\breturn\s+(?:null|"
    r"Collections\.empty(?:List|Set|Map)\s*\(\)|"
    r"(?:List|Set|Map)\.of\s*\(\))\s*;",
    re.IGNORECASE | re.DOTALL,
)
JAVA_CONTINUE = re.compile(r"\bcontinue\s*;")
JAVA_VARARGS = re.compile(
    r"\b[\w$]+(?:\s*<[^>\n]+>)?(?:\s*\[\])?\s*\.\.\.\s*[\w$]+"
)
FENCE_PATTERN = re.compile(r"^[ \t]*([`~])\1{2,}")


class FencedBlock(NamedTuple):
    start: int
    content_start: int
    content_end: int
    end: int
    language: str


def line_number(text: str, index: int) -> int:
    return text.count("\n", 0, max(index, 0)) + 1


def match_error(
    text: str, pattern: re.Pattern[str], message: str
) -> str | None:
    match = pattern.search(text)
    if not match:
        return None
    return (
        f"content: {message} at line {line_number(text, match.start())}: "
        f"{match.group(0)!r}"
    )


def fence_marker(line: str) -> tuple[str, int] | None:
    match = FENCE_PATTERN.match(line)
    if not match:
        return None
    marker_character = match.group(1)
    return marker_character, match.group(0).count(marker_character)


def fenced_blocks(text: str) -> tuple[list[FencedBlock], list[int]]:
    blocks: list[FencedBlock] = []
    unclosed_starts: list[int] = []
    active: tuple[str, int, int, int, str] | None = None
    offset = 0

    for line in text.splitlines(keepends=True):
        marker = fence_marker(line)
        line_start = offset
        line_end = offset + len(line)
        if active is None and marker:
            marker_match = FENCE_PATTERN.match(line)
            assert marker_match is not None
            language = line[marker_match.end() :].strip().split(maxsplit=1)
            active = (
                marker[0],
                marker[1],
                line_start,
                line_end,
                language[0].lower() if language else "",
            )
        elif (
            active is not None
            and marker
            and marker[0] == active[0]
            and marker[1] >= active[1]
        ):
            blocks.append(
                FencedBlock(
                    start=active[2],
                    content_start=active[3],
                    content_end=line_start,
                    end=line_end,
                    language=active[4],
                )
            )
            active = None
        offset = line_end

    if active is not None:
        unclosed_starts.append(active[2])
    return blocks, unclosed_starts


def blank_non_newline_characters(line: str) -> str:
    return re.sub(r"[^\r\n]", " ", line)


def mask_fenced_blocks(text: str) -> str:
    blocks, unclosed_starts = fenced_blocks(text)
    spans = [(block.start, block.end) for block in blocks]
    spans.extend((start, len(text)) for start in unclosed_starts)
    masked = list(text)
    for start, end in spans:
        for index in range(start, end):
            if masked[index] not in "\r\n":
                masked[index] = " "
    return "".join(masked)


def fence_errors(text: str) -> list[str]:
    _, unclosed_starts = fenced_blocks(text)
    return [
        f"structure: unclosed fenced code block at line {line_number(text, start)}"
        for start in unclosed_starts
    ]


def top_level_matches(text: str) -> list[re.Match[str]]:
    return list(TOP_LEVEL_PATTERN.finditer(mask_fenced_blocks(text)))


def java_continue_errors(text: str) -> list[str]:
    """Reject continue statements in Java code proposed by a Plan."""
    for block in fenced_blocks(text)[0]:
        if block.language == "java":
            block_text = text[block.content_start : block.content_end]
            match = JAVA_CONTINUE.search(block_text)
            if match is not None:
                position = block.content_start + match.start()
                return [
                    f"content: Java code must not use continue at line {line_number(text, position)}"
                ]
    return []


def standard_path_errors(plan_path: Path) -> list[str]:
    parts = plan_path.resolve().parts
    if len(parts) < 4 or tuple(parts[-4:-2]) != ("docs", "pretty") or parts[-1] != "plan.md":
        return ["path: expected docs/pretty/<topic>/plan.md"]

    topic = parts[-2]
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", topic):
        return [f"path: topic '{topic}' must use lowercase kebab-case"]
    return []


def section_ranges(text: str) -> dict[str, tuple[int, int]]:
    matches = top_level_matches(text)
    ranges: dict[str, tuple[int, int]] = {}
    for index, match in enumerate(matches):
        heading = match.group(0).strip()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        ranges.setdefault(heading, (match.start(), end))
    return ranges


def top_level_section_counts(text: str) -> dict[str, int]:
    section_counts: dict[str, int] = {}
    for match in top_level_matches(text):
        heading = match.group(0).strip()
        section_counts[heading] = section_counts.get(heading, 0) + 1
    return section_counts


def top_level_section_errors(text: str) -> list[str]:
    errors: list[str] = []
    for heading, count in top_level_section_counts(text).items():
        if heading not in TOP_LEVEL_SECTIONS:
            errors.append(f"structure: unsupported top-level section '{heading[3:]}'")
        if count > 1:
            errors.append(f"structure: duplicate top-level section '{heading[3:]}'")
    return errors


def chain_errors(text: str, sections: dict[str, tuple[int, int]]) -> list[str]:
    if CHAIN_SECTION not in sections:
        return []

    errors: list[str] = []
    if TASKS_SECTION in sections and sections[CHAIN_SECTION][0] > sections[TASKS_SECTION][0]:
        errors.append("structure: 变更链路 must precede 实施任务")
    chain_start, chain_end = sections[CHAIN_SECTION]
    mermaid_blocks = [
        block
        for block in fenced_blocks(text)[0]
        if block.start >= chain_start
        and block.end <= chain_end
        and block.language == "mermaid"
    ]
    if not mermaid_blocks:
        errors.append("structure: 变更链路 must contain a Mermaid diagram")
    for block in mermaid_blocks:
        lines = [
            line.strip()
            for line in text[block.content_start : block.content_end].splitlines()
            if line.strip()
        ]
        if not lines or MERMAID_START_PATTERN.match(lines[0]) is None:
            errors.append(
                "structure: 变更链路 Mermaid diagram must start with flowchart, "
                "sequenceDiagram, or stateDiagram-v2"
            )
    return errors


def structure_errors(text: str) -> list[str]:
    errors = fence_errors(text)
    errors.extend(top_level_section_errors(text))
    structural_text = mask_fenced_blocks(text)
    title_matches = list(TITLE_PATTERN.finditer(structural_text))
    if not title_matches:
        errors.append("header: expected '# <topic> Implementation Plan'")
    else:
        first_content_line = next(
            (line.strip() for line in structural_text.splitlines() if line.strip()),
            "",
        )
        if not TITLE_PATTERN.fullmatch(first_content_line):
            errors.append("header: title must be the first non-empty line")
        if len(title_matches) != 1:
            errors.append(
                "header: expected exactly one Implementation Plan title"
            )
    for heading in H1_PATTERN.finditer(structural_text):
        if not TITLE_PATTERN.fullmatch(heading.group(0).strip()):
            errors.append(
                "structure: unsupported level-one heading "
                f"at line {line_number(text, heading.start())}: "
                f"{heading.group(0)!r}"
            )
            break
    sections = section_ranges(text)
    if TASKS_SECTION not in sections:
        errors.append("structure: missing section '实施任务'")
    else:
        task_start, task_end = sections[TASKS_SECTION]
        for match in TASK_PATTERN.finditer(structural_text):
            if not task_start <= match.start() < task_end:
                errors.append(
                    "structure: TASK heading outside '实施任务' at line "
                    f"{line_number(text, match.start())}"
                )
                break
    errors.extend(chain_errors(text, sections))
    return errors


def forbidden_content_errors(text: str) -> list[str]:
    structural_text = mask_fenced_blocks(text)
    prose_checks = (
        (EXTERNAL_DEPENDENCY, "external skill dependency"),
        (GENERIC_EXTERNAL_SKILL, "external skill dependency"),
        (DEPRECATED_HEADER_FIELD, "deprecated header field"),
        (DEPRECATED_METADATA, "deprecated orchestration metadata"),
        (DEPRECATED_PATH_TABLE, "deprecated path/symbol table"),
        (DEPRECATED_CHAIN_TABLE, "deprecated chain relation table"),
        (DEPRECATED_PLAN_STRUCTURE, "deprecated plan structure"),
        (DEPRECATED_PLAN_PROSE, "deprecated plan prose"),
    )
    whole_document_checks = (
        (FORBIDDEN_WORDS, "placeholder or TODO marker"),
        (TRACE_ID, "REQ/AC/DEC trace identifier"),
        (PERSONAL_ABSOLUTE_PATH, "personal absolute path"),
        (PLACEHOLDER, "unresolved placeholder"),
        (SILENT_NULL_TERNARY, "silent null propagation"),
        (OR_ELSE_NULL, "orElse(null) fallback"),
        (
            BROAD_CATCH_FALLBACK,
            "broad catch returns an empty/success fallback",
        ),
    )
    errors = [
        error
        for pattern, label in prose_checks
        if (error := match_error(structural_text, pattern, label)) is not None
    ]
    errors.extend(
        error
        for pattern, label in whole_document_checks
        if (error := match_error(text, pattern, label)) is not None
    )
    errors.extend(java_continue_errors(text))

    # An ellipsis in prose or a code block can hide unplanned implementation.
    # Java varargs are allowed when the line is an actual method signature.
    for index, line in enumerate(text.splitlines(), start=1):
        if "..." not in line:
            continue
        if JAVA_VARARGS.search(line) and "```" not in line:
            continue
        errors.append(f"content: ellipsis at line {index}")
        break
    return errors


def task_ranges(text: str) -> list[tuple[int, int, int]]:
    structural_text = mask_fenced_blocks(text)
    matches = list(TASK_PATTERN.finditer(structural_text))
    ranges: list[tuple[int, int, int]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        next_section = structural_text.find("\n## ", match.end())
        if next_section >= 0:
            end = min(end, next_section)
        ranges.append((int(match.group(1)), match.start(), end))
    return ranges


def task_section(text: str) -> str | None:
    sections = section_ranges(text)
    task_bounds = sections.get(TASKS_SECTION)
    if task_bounds is None:
        return None
    start, end = task_bounds
    return text[start:end]


def task_identity_errors(task_ranges_found: list[tuple[int, int, int]]) -> list[str]:
    actual = [task_id for task_id, _, _ in task_ranges_found]
    expected = list(range(1, len(task_ranges_found) + 1))
    if actual == expected:
        return []
    return [f"tasks: TASK ids must be continuous from TASK-001; found {actual}"]


def has_nonempty_fenced_block(
    text: str, start: int, end: int, language: str | None = None
) -> bool:
    blocks, _ = fenced_blocks(text)
    return any(
        block.start >= start
        and block.end <= end
        and (language is None or block.language == language)
        and bool(text[block.content_start : block.content_end].strip())
        for block in blocks
    )


def file_entries(segment: str) -> list[tuple[str, str]]:
    structural_segment = mask_fenced_blocks(segment)
    return FILE_ENTRY.findall(structural_segment)


def label_match(segment: str, label: str) -> re.Match[str] | None:
    return re.search(rf"^{re.escape(label)}：[ \t]*$", mask_fenced_blocks(segment), re.MULTILINE)


def next_label_position(segment: str, start: int) -> int:
    match = LABEL_PATTERN.search(mask_fenced_blocks(segment)[start:])
    return start + match.start() if match else len(segment)


def files_errors(segment: str, prefix: str) -> tuple[list[str], list[tuple[str, str]]]:
    errors: list[str] = []
    structural_segment = mask_fenced_blocks(segment)
    files_heading = FILES_HEADING.search(structural_segment)
    if files_heading is None:
        return [f"tasks: {prefix} missing '**Files:**'"], []
    entries = file_entries(segment)
    if not entries:
        errors.append(f"tasks: {prefix} has no Create/Modify/Test/Delete file entry")
    files_end = next_label_position(segment, files_heading.end())
    if not any(
        match.start() >= files_heading.end() and match.start() < files_end
        for match in FILE_ENTRY.finditer(structural_segment)
    ):
        errors.append(f"tasks: {prefix} '**Files:**' has no file entry")
    return errors, entries


def constraint_order_error(segment: str, prefix: str) -> list[str]:
    structural_segment = mask_fenced_blocks(segment)
    constraint = label_match(segment, "约束")
    files = FILES_HEADING.search(structural_segment)
    if constraint is not None and files is not None and constraint.start() > files.start():
        return [f"tasks: {prefix} 约束 must precede **Files:**"]
    return []


def logic_task_errors(segment: str, prefix: str) -> list[str]:
    errors, entries = files_errors(segment, prefix)
    errors.extend(constraint_order_error(segment, prefix))
    has_production_file = any(
        operation in {"Create", "Modify"}
        and not re.search(r"(?:^|[/._-])tests?(?:[/._-]|$)", path, re.IGNORECASE)
        for operation, path in entries
    )
    has_test_file = any(
        operation == "Test"
        or re.search(r"(?:^|[/._-])tests?(?:[/._-]|$)", path, re.IGNORECASE)
        for operation, path in entries
    )
    if not has_production_file:
        errors.append(f"tasks: {prefix} Files lacks a production Create/Modify path")
    if not has_test_file:
        errors.append(f"tasks: {prefix} Files lacks a Test path")

    modification = label_match(segment, "修改")
    tests = label_match(segment, "测试")
    if modification is None:
        errors.append(f"tasks: {prefix} missing '修改：'")
    if tests is None:
        errors.append(f"tasks: {prefix} missing '测试：'")
    if modification is not None:
        modification_end = next_label_position(segment, modification.end())
        if not has_nonempty_fenced_block(
            segment, modification.end(), modification_end, language="java"
        ):
            errors.append(f"tasks: {prefix} 修改 lacks a nonempty Java code block")
    if tests is not None:
        tests_end = next_label_position(segment, tests.end())
        if not has_nonempty_fenced_block(segment, tests.end(), tests_end, language="java"):
            errors.append(f"tasks: {prefix} 测试 lacks a nonempty Java code block")
    return errors


def structural_task_errors(segment: str, prefix: str) -> list[str]:
    errors, entries = files_errors(segment, prefix)
    errors.extend(constraint_order_error(segment, prefix))
    if not any(operation in {"Create", "Modify", "Delete"} for operation, _ in entries):
        errors.append(f"tasks: {prefix} Files lacks a Create/Modify/Delete path")
    modification = label_match(segment, "修改")
    if modification is None:
        errors.append(f"tasks: {prefix} missing '修改：'")
    elif not has_nonempty_fenced_block(segment, modification.end(), len(segment)):
        errors.append(f"tasks: {prefix} 修改 lacks a nonempty code/content block")
    return errors


def task_errors(segment: str, task_id: int) -> list[str]:
    prefix = f"TASK-{task_id:03d}"
    structural_segment = mask_fenced_blocks(segment)
    if "测试：" in structural_segment:
        return logic_task_errors(segment, prefix)
    return structural_task_errors(segment, prefix)


def task_errors_for_plan(text: str) -> tuple[list[str], int]:
    tasks_text = task_section(text)
    if tasks_text is None:
        return [], 0
    ranges = task_ranges(tasks_text)
    if not ranges:
        return [
            "tasks: no TASK heading inside '实施任务' matching '### TASK-001：...' was found"
        ], 0
    errors = task_identity_errors(ranges)
    for task_id, start, end in ranges:
        errors.extend(task_errors(tasks_text[start:end], task_id))
    return errors, len(ranges)


def read_plan_text(plan_path: Path) -> tuple[str | None, list[str]]:
    try:
        if not plan_path.exists():
            return None, [f"file: not found: {plan_path}"]
        if not plan_path.is_file():
            return None, [f"file: not a regular file: {plan_path}"]
        return plan_path.read_text(encoding="utf-8"), []
    except UnicodeDecodeError as exc:
        return None, [f"file: expected UTF-8 text: {exc}"]
    except OSError as exc:
        return None, [f"file: could not read {plan_path}: {exc}"]


def validation_result(plan_path: Path) -> tuple[list[str], int]:
    text, file_errors = read_plan_text(plan_path)
    if text is None:
        return file_errors, 0

    errors: list[str] = []
    errors.extend(standard_path_errors(plan_path))
    errors.extend(structure_errors(text))
    errors.extend(forbidden_content_errors(text))
    task_validation_errors, task_count = task_errors_for_plan(text)
    errors.extend(task_validation_errors)
    return errors, task_count


def validate_plan(plan_path: Path) -> list[str]:
    errors, _ = validation_result(plan_path)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate docs/pretty/<topic>/plan.md for pretty-writing-plan."
    )
    parser.add_argument("plan", type=Path, help="Plan path to validate")
    args = parser.parse_args()

    errors, task_count = validation_result(args.plan)
    if errors:
        print("Plan validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"Plan is valid: {args.plan} ({task_count} task(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
