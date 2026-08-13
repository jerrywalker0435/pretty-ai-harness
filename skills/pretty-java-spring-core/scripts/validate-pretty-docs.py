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
        "输入与范围",
        "设计摘要",
        "现状与约束",
        "方案与权衡",
        "详细设计",
        "验证策略",
        "风险与回退",
    ),
    "plan": (
        "输入与范围",
        "实施摘要",
        "代码事实与约束",
        "实施任务",
        "测试与验证",
    ),
    "execution": (
        "输入与基线",
        "执行摘要",
        "任务证据",
        "测试与验证结果",
        "偏差与未验证范围",
        "最终审计与结论",
    ),
}
ID_PATTERN = re.compile(r"\b(REQ|AC|DEC|TASK)-(\d{3,})\b")
DEFINITION_PATTERN = re.compile(
    r"^#{3,6}\s+((?:REQ|AC|DEC|TASK)-\d{3,})\b", re.MULTILINE
)
PLACEHOLDER_PATTERN = re.compile(r"\b(?:TODO|TBD|FIXME)\b|待定|占位", re.IGNORECASE)
PERSONAL_PATH_PATTERN = re.compile(
    r"(?:/Users/[^/\s`]+|/home/[^/\s`]+|[A-Za-z]:\\Users\\[^\\\s`]+)"
)
PLAN_REQUIRED_MARKERS = (
    "已核实代码事实",
    "上游约束",
    "拟议实现",
)
PLAN_TASK_REQUIRED_MARKERS = (
    "追溯落点",
    "目标行为或风险闭环",
    "已核实代码事实",
    "继承约束",
    "拟议变更",
    "真实任务依赖",
    "验证入口",
    "完成证据",
)
PLAN_SLICE_MARKERS = (
    "UT 边界",
    "独立预期值",
    "mock/fake/stub 边界",
    "预期 RED 原因",
    "最小 GREEN 条件",
)
EXECUTION_REQUIRED_MARKERS = (
    "工作区归因",
    "Plan 基线",
    "实际声明范围",
    "Pretty 外未验证范围",
    "自动审计",
)
EXECUTION_TASK_REQUIRED_MARKERS = (
    "状态",
    "实际变更",
    "任务级完成证据",
    "实质偏差",
)
BASELINE_STOP_MARKERS = (
    "工作区归因",
    "Plan 基线",
    "停止：基线失败",
    "恢复条件",
    "Pretty 外未验证范围",
)
DESIGN_DEC_REQUIRED_MARKERS = (
    "驱动因素与相关 `REQ`",
    "候选或决定性证据",
    "采用方案及理由",
    "后果",
    "重新评估条件",
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


def definitions(text: str) -> List[str]:
    return DEFINITION_PATTERN.findall(text)


def references(text: str, prefix: str) -> Set[str]:
    return {
        f"{kind}-{number}"
        for kind, number in ID_PATTERN.findall(text)
        if kind == prefix
    }


def definition_blocks(text: str, prefix: str) -> List[Tuple[str, str]]:
    pattern = re.compile(rf"^###\s+({prefix}-\d{{3,}})\b", re.MULTILINE)
    matches = list(pattern.finditer(text))
    blocks = []
    for index, match in enumerate(matches):
        next_definition = (
            matches[index + 1].start() if index + 1 < len(matches) else len(text)
        )
        next_h2 = re.search(r"^##\s+", text[match.end() :], re.MULTILINE)
        end = next_definition
        if next_h2:
            end = min(end, match.end() + next_h2.start())
        blocks.append((match.group(1), text[match.start() : end]))
    return blocks


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


def add_required_marker_errors(
    errors: List[str], stage: str, text: str, required: Iterable[str]
) -> None:
    for marker in required:
        if marker not in text:
            errors.append(f"{stage}.md is missing required field: {marker}")


def add_block_marker_errors(
    errors: List[str],
    stage: str,
    blocks: Iterable[Tuple[str, str]],
    required: Iterable[str],
) -> None:
    for identifier, block in blocks:
        for marker in required:
            if marker not in block:
                errors.append(f"{stage}.md {identifier} is missing required field: {marker}")


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
        if headings != list(REQUIRED_HEADINGS[stage]):
            errors.append(
                f"{stage}.md H2 headings must exactly match the fixed stage order"
            )

        defined_ids = definitions(text)
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
    if decisions:
        add_block_marker_errors(
            errors,
            "design",
            definition_blocks(design, "DEC"),
            DESIGN_DEC_REQUIRED_MARKERS,
        )
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
    add_required_marker_errors(errors, "plan", plan, PLAN_REQUIRED_MARKERS)
    add_block_marker_errors(
        errors,
        "plan",
        definition_blocks(plan, "TASK"),
        PLAN_TASK_REQUIRED_MARKERS,
    )
    if "行为切片" in plan:
        add_required_marker_errors(errors, "plan", plan, PLAN_SLICE_MARKERS)
    for marker in ("行阈值", "分支阈值"):
        if marker not in plan:
            errors.append(f"plan.md is missing coverage policy field: {marker}")
    if NON_UT_TEST_CODE_PATTERN.search(plan):
        errors.append("plan.md proposes non-UT test code")
    return tasks


def validate_execution(
    documents: Dict[str, str],
    definitions_by_stage: Dict[str, Set[str]],
    tasks: Set[str],
    errors: List[str],
) -> None:
    if "execution" not in documents:
        return
    execution = documents["execution"]
    if "停止：基线失败" in execution:
        add_required_marker_errors(errors, "execution", execution, BASELINE_STOP_MARKERS)
    else:
        execution_tasks = {
            item
            for item in definitions_by_stage["execution"]
            if item.startswith("TASK-")
        }
        for unknown in sorted(execution_tasks - tasks):
            errors.append(f"execution.md references unknown {unknown}")
        for missing in sorted(tasks - execution_tasks):
            errors.append(f"execution.md does not report {missing}")
        add_required_marker_errors(errors, "execution", execution, EXECUTION_REQUIRED_MARKERS)
        add_block_marker_errors(
            errors,
            "execution",
            definition_blocks(execution, "TASK"),
            EXECUTION_TASK_REQUIRED_MARKERS,
        )
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
    validate_execution(documents, definitions_by_stage, tasks, errors)

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
