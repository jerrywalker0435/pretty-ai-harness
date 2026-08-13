#!/usr/bin/env python3
"""Validate the lightweight Pretty PRD -> Design -> Plan -> Execution chain."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import re
import sys
from typing import Dict, Iterable, List, Sequence, Set, Tuple


STAGES = ("prd", "design", "plan", "execution")
REQUIRED_HEADINGS = {
    "prd": (
        "背景与问题",
        "目标与非目标",
        "用户与场景",
        "需求",
        "验收标准",
        "约束与未决问题",
    ),
    "design": (
        "设计结论",
        "方案全景",
        "关键设计与权衡",
        "设计边界",
        "验证与风险",
    ),
    "plan": (
        "实施结论",
        "实施任务",
        "文件变更总览",
        "测试与验证",
        "共享约束和代码事实",
    ),
}
ID_PATTERN = re.compile(r"\b(REQ|AC|DEC|TASK)-(\d{3,})\b")
HEADING_DEFINITION_PATTERN = re.compile(
    r"^#{3,6}\s+((?:REQ|AC|DEC|TASK)-\d{3,})\b", re.MULTILINE
)
DESIGN_DECISION_PATTERN = re.compile(
    r"(?:^|[；;])\s*决策：\s*`?(DEC-\d{3,})`?", re.MULTILINE
)
PLAN_TASK_HEADING_PATTERN = re.compile(
    r"^###\s+.+?[（(](TASK-\d{3,})[)）]\s*$", re.MULTILINE
)
PLACEHOLDER_PATTERN = re.compile(r"\b(?:TODO|TBD|FIXME)\b|待定|占位", re.IGNORECASE)
PERSONAL_PATH_PATTERN = re.compile(
    r"(?:/Users/[^/\s`]+|/home/[^/\s`]+|~/[^\s`]+|[A-Za-z]:\\Users\\[^\\\s`]+)"
)
PLAN_PRODUCTION_CODE_HEADING = "#### 核心生产代码"
PLAN_TEST_CODE_HEADING = "#### 核心测试代码"
PLAN_MECHANICAL_CHANGE_HEADING = "#### 完整机械变更"
JAVA_FENCE_PATTERN = re.compile(r"```java\s*\n.+?\n```", re.DOTALL)
EXECUTION_COMPLETE_HEADINGS = (
    "执行起点",
    "TASK 结果",
    "最终验证",
    "结论与限制",
)
EXECUTION_STOP_HEADINGS = (
    ("执行起点", "恢复点", "结论与限制"),
    ("执行起点", "TASK 结果", "恢复点", "结论与限制"),
)
EXECUTION_PLACEHOLDER_PATTERN = re.compile(
    r"待执行|待验证|待审计|待逐[^\n]*记录|执行中"
)
NON_UT_TEST_CODE_PATTERN = re.compile(
    r"^\s*(?:@(SpringBootTest|WebMvcTest|DataJpaTest)\b|"
    r"import\s+org\.testcontainers\.|"
    r"(?:new\s+)?(?:PostgreSQLContainer|MySQLContainer|GenericContainer)\s*[<(])",
    re.MULTILINE,
)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a docs/pretty/<topic> document chain."
    )
    parser.add_argument("topic_dir", type=Path)
    parser.add_argument(
        "--through",
        choices=STAGES,
        help="Validate through this stage; default is the highest contiguous file.",
    )
    return parser.parse_args(argv)


def heading_titles(text: str) -> List[str]:
    return [
        match.group(1).strip()
        for match in re.finditer(r"^##\s+(.+?)\s*$", text, re.MULTILINE)
    ]


def definitions(stage: str, text: str) -> List[str]:
    if stage == "design":
        return DESIGN_DECISION_PATTERN.findall(text)
    if stage == "plan":
        return PLAN_TASK_HEADING_PATTERN.findall(text)
    return HEADING_DEFINITION_PATTERN.findall(text)


def references(text: str, prefix: str) -> Set[str]:
    return {
        f"{kind}-{number}"
        for kind, number in ID_PATTERN.findall(text)
        if kind == prefix
    }


def plan_task_blocks(text: str) -> List[Tuple[str, str]]:
    matches = list(PLAN_TASK_HEADING_PATTERN.finditer(text))
    blocks: List[Tuple[str, str]] = []
    for index, match in enumerate(matches):
        next_task = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        next_h2 = re.search(r"^##\s+", text[match.end() :], re.MULTILINE)
        end = next_task
        if next_h2:
            end = min(end, match.end() + next_h2.start())
        blocks.append((match.group(1), text[match.start() : end]))
    return blocks


def subsection(text: str, heading: str) -> str:
    start_match = re.search(rf"^{re.escape(heading)}\s*$", text, re.MULTILINE)
    if not start_match:
        return ""
    remainder = text[start_match.end() :]
    next_heading = re.search(r"^#{2,4}\s+", remainder, re.MULTILINE)
    return remainder[: next_heading.start()] if next_heading else remainder


def add_sequence_errors(errors: List[str], stage: str, defined_ids: List[str]) -> None:
    by_prefix: Dict[str, List[str]] = {}
    for item in defined_ids:
        by_prefix.setdefault(item.split("-", 1)[0], []).append(item)
    for prefix, items in by_prefix.items():
        expected = [f"{prefix}-{index:03d}" for index in range(1, len(items) + 1)]
        if items != expected:
            errors.append(
                f"{stage}.md {prefix} definitions must be continuous from {prefix}-001"
            )


def add_unknown_reference_errors(
    errors: List[str],
    stage: str,
    text: str,
    prefix: str,
    known: Set[str],
) -> None:
    for unknown in sorted(references(text, prefix) - known):
        errors.append(f"{stage}.md references unknown {unknown}")


def add_missing_reference_errors(
    errors: List[str], stage: str, text: str, required: Iterable[str]
) -> None:
    all_references = {f"{kind}-{number}" for kind, number in ID_PATTERN.findall(text)}
    for missing in sorted(set(required) - all_references):
        errors.append(f"{stage}.md does not reference {missing}")


def selected_stages(topic_dir: Path, through: str) -> List[str]:
    if through:
        return list(STAGES[: STAGES.index(through) + 1])

    selected: List[str] = []
    for stage in STAGES:
        if (topic_dir / f"{stage}.md").is_file():
            selected.append(stage)
        else:
            break
    return selected


def read_documents(
    topic_dir: Path, stages: Iterable[str], errors: List[str]
) -> Tuple[Dict[str, str], Dict[str, Set[str]]]:
    documents: Dict[str, str] = {}
    stage_definitions: Dict[str, Set[str]] = {}
    for stage in stages:
        path = topic_dir / f"{stage}.md"
        if not path.is_file():
            errors.append(f"missing required file: {path}")
            continue
        text = path.read_text(encoding="utf-8")
        documents[stage] = text
        if PLACEHOLDER_PATTERN.search(text):
            errors.append(f"{stage}.md contains a placeholder")

        if PERSONAL_PATH_PATTERN.search(text):
            errors.append(f"{stage}.md contains a personal absolute path")

        headings = heading_titles(text)
        if stage != "execution" and headings != list(REQUIRED_HEADINGS[stage]):
            errors.append(
                f"{stage}.md H2 headings must exactly match the fixed stage order"
            )

        defined_ids = definitions(stage, text)
        for duplicate, count in Counter(defined_ids).items():
            if count > 1:
                errors.append(f"{stage}.md defines {duplicate} more than once")
        add_sequence_errors(errors, stage, defined_ids)
        stage_definitions[stage] = set(defined_ids)
    return documents, stage_definitions


def validate_prd(
    documents: Dict[str, str],
    definitions_by_stage: Dict[str, Set[str]],
    errors: List[str],
) -> Tuple[Set[str], Set[str]]:
    if "prd" not in documents:
        return set(), set()
    reqs = {item for item in definitions_by_stage["prd"] if item.startswith("REQ-")}
    acceptance = {
        item for item in definitions_by_stage["prd"] if item.startswith("AC-")
    }
    if not reqs:
        errors.append("prd.md must define at least one REQ ID")
    if not acceptance:
        errors.append("prd.md must define at least one AC ID")
    add_unknown_reference_errors(errors, "prd", documents["prd"], "REQ", reqs)
    return reqs, acceptance


def validate_design(
    documents: Dict[str, str],
    definitions_by_stage: Dict[str, Set[str]],
    reqs: Set[str],
    acceptance: Set[str],
    errors: List[str],
) -> Set[str]:
    if "design" not in documents:
        return set()
    decisions = {
        item for item in definitions_by_stage["design"] if item.startswith("DEC-")
    }
    design = documents["design"]
    add_unknown_reference_errors(errors, "design", design, "REQ", reqs)
    add_unknown_reference_errors(errors, "design", design, "AC", acceptance)
    add_missing_reference_errors(errors, "design", design, reqs)
    add_missing_reference_errors(errors, "design", design, acceptance)
    if re.search(r"^\s*[-*]\s*覆盖需求\s*[：:]", design, re.MULTILINE):
        errors.append("design.md must not contain a 覆盖需求 list")
    if re.search(r"^#{2,6}\s+(?:REQ|AC|DEC)-\d{3,}\b", design, re.MULTILINE):
        errors.append("design.md must keep REQ/AC/DEC IDs out of headings")
    return decisions


def validate_plan(
    documents: Dict[str, str],
    definitions_by_stage: Dict[str, Set[str]],
    upstream_ids: Iterable[Tuple[str, Set[str]]],
    errors: List[str],
) -> Set[str]:
    if "plan" not in documents:
        return set()
    plan = documents["plan"]
    tasks = {item for item in definitions_by_stage["plan"] if item.startswith("TASK-")}
    if not tasks:
        errors.append("plan.md must define at least one TASK ID")
    for prefix, known in upstream_ids:
        add_unknown_reference_errors(errors, "plan", plan, prefix, known)
        add_missing_reference_errors(errors, "plan", plan, known)
    for task, block in plan_task_blocks(plan):
        if "| 完整仓库相对路径 | symbol | 修改目的 |" not in block:
            errors.append(f"plan.md {task} is missing a file change table")
        production = subsection(block, PLAN_PRODUCTION_CODE_HEADING)
        tests = subsection(block, PLAN_TEST_CODE_HEADING)
        mechanical = subsection(block, PLAN_MECHANICAL_CHANGE_HEADING)
        has_pair = bool(production and tests)
        has_mechanical = bool(mechanical)
        if not has_pair and not has_mechanical:
            errors.append(
                f"plan.md {task} must contain both 核心生产代码 and 核心测试代码, "
                "or a 完整机械变更"
            )
        if bool(production) != bool(tests):
            missing = "核心测试代码" if production else "核心生产代码"
            errors.append(f"plan.md {task} is missing required paired section: {missing}")
        if has_pair:
            if not JAVA_FENCE_PATTERN.search(production):
                errors.append(f"plan.md {task} 核心生产代码 must contain Java code")
            if not JAVA_FENCE_PATTERN.search(tests):
                errors.append(f"plan.md {task} 核心测试代码 must contain Java code")
        if "> 追溯：" not in block:
            errors.append(f"plan.md {task} is missing a tail traceability note")
    if re.search(r"^###\s+TASK-\d{3,}\b", plan, re.MULTILINE):
        errors.append("plan.md TASK IDs must appear after readable task titles")
    for marker in ("行阈值", "分支阈值"):
        if marker not in plan:
            errors.append(f"plan.md is missing coverage policy field: {marker}")
    if NON_UT_TEST_CODE_PATTERN.search(plan):
        errors.append("plan.md proposes non-UT test code")
    return tasks


def execution_status(text: str) -> str:
    conclusion = subsection(text, "## 结论与限制")
    if re.search(r"^- 状态：完成\s*$", conclusion, re.MULTILINE):
        return "completed"
    if re.search(
        r"^- 状态：(停止：.+|返回 (?:Plan|Design|PRD)：.+)\s*$",
        conclusion,
        re.MULTILINE,
    ):
        return "stopped"
    return ""


def add_execution_task_errors(
    errors: List[str], text: str, tasks: Set[str]
) -> None:
    reported = set(PLAN_TASK_HEADING_PATTERN.findall(text))
    for unknown in sorted(reported - tasks):
        errors.append(f"execution.md references unknown {unknown}")
    for missing in sorted(tasks - reported):
        errors.append(f"execution.md does not report {missing}")


def validate_execution_document(text: str, tasks: Set[str]) -> List[str]:
    errors: List[str] = []
    headings = tuple(heading_titles(text))
    status = execution_status(text)

    if EXECUTION_PLACEHOLDER_PATTERN.search(text):
        errors.append("execution.md contains a placeholder")

    if status == "completed":
        if headings != EXECUTION_COMPLETE_HEADINGS:
            errors.append("execution.md completed headings are invalid")
        add_execution_task_errors(errors, text, tasks)
        return errors

    if status == "stopped":
        if headings not in EXECUTION_STOP_HEADINGS:
            errors.append("execution.md stopped headings are invalid")
        return errors

    errors.append("execution.md must contain a final completed or stopped status")
    return errors


def validate_execution(
    documents: Dict[str, str], tasks: Set[str], errors: List[str]
) -> None:
    if "execution" not in documents:
        return
    execution = documents["execution"]
    errors.extend(validate_execution_document(execution, tasks))
    if NON_UT_TEST_CODE_PATTERN.search(execution):
        errors.append("execution.md records non-UT test code creation")


def validate(topic_dir: Path, through: str = None) -> List[str]:
    errors: List[str] = []
    stages = selected_stages(topic_dir, through)
    if not stages:
        return [f"no Pretty documents found in {topic_dir}"]

    documents, definitions_by_stage = read_documents(topic_dir, stages, errors)
    reqs, acceptance = validate_prd(documents, definitions_by_stage, errors)
    decisions = validate_design(
        documents, definitions_by_stage, reqs, acceptance, errors
    )
    tasks = validate_plan(
        documents,
        definitions_by_stage,
        (("REQ", reqs), ("AC", acceptance), ("DEC", decisions)),
        errors,
    )
    validate_execution(documents, tasks, errors)

    return errors


def main(argv: Sequence[str] = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    stages = selected_stages(args.topic_dir, args.through)
    errors = validate(args.topic_dir, args.through)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"OK: {len(stages)} documents valid through {stages[-1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
