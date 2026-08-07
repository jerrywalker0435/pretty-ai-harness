#!/usr/bin/env python3
"""Validate the lightweight Pretty PRD -> Design -> Plan -> Execution chain."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import re
import sys
from typing import Dict, Iterable, List, Sequence, Set


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
        "现状与约束",
        "方案与权衡",
        "详细设计",
        "测试策略",
        "Java/Spring 质量审查",
        "风险与回退",
    ),
    "plan": (
        "输入与范围",
        "变更概览",
        "实施任务",
        "测试与增量覆盖率",
        "最终验证",
        "执行交接",
    ),
    "execution": (
        "输入与基线",
        "任务结果",
        "测试与覆盖率结果",
        "代码质量 Review",
        "偏差与遗留问题",
        "最终结论",
    ),
}
ID_PATTERN = re.compile(r"\b(REQ|AC|DEC|TASK)-(\d{3,})\b")
DEFINITION_PATTERN = re.compile(
    r"^#{3,6}\s+((?:REQ|AC|DEC|TASK)-\d{3,})\b", re.MULTILINE
)
PLACEHOLDER_PATTERN = re.compile(r"\b(?:TODO|TBD|FIXME)\b|待定|占位", re.IGNORECASE)


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


def heading_titles(text: str) -> Set[str]:
    return {
        match.group(1).strip()
        for match in re.finditer(r"^##\s+(.+?)\s*$", text, re.MULTILINE)
    }


def definitions(text: str) -> List[str]:
    return DEFINITION_PATTERN.findall(text)


def references(text: str, prefix: str) -> Set[str]:
    return {
        f"{kind}-{number}"
        for kind, number in ID_PATTERN.findall(text)
        if kind == prefix
    }


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


def validate(topic_dir: Path, through: str = None) -> List[str]:
    errors: List[str] = []
    stages = selected_stages(topic_dir, through)
    if not stages:
        return [f"no Pretty documents found in {topic_dir}"]

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

        headings = heading_titles(text)
        for heading in REQUIRED_HEADINGS[stage]:
            if heading not in headings:
                errors.append(f"{stage}.md is missing heading: {heading}")

        defined_ids = definitions(text)
        for duplicate, count in Counter(defined_ids).items():
            if count > 1:
                errors.append(f"{stage}.md defines {duplicate} more than once")
        stage_definitions[stage] = set(defined_ids)

    if "prd" in documents:
        reqs = {item for item in stage_definitions["prd"] if item.startswith("REQ-")}
        acceptance = {item for item in stage_definitions["prd"] if item.startswith("AC-")}
        if not reqs:
            errors.append("prd.md must define at least one REQ ID")
        if not acceptance:
            errors.append("prd.md must define at least one AC ID")
        add_unknown_reference_errors(errors, "prd", documents["prd"], "REQ", reqs)
    else:
        reqs = set()
        acceptance = set()

    if "design" in documents:
        decisions = {
            item for item in stage_definitions["design"] if item.startswith("DEC-")
        }
        if not decisions:
            errors.append("design.md must define at least one DEC ID")
        add_unknown_reference_errors(errors, "design", documents["design"], "REQ", reqs)
        add_unknown_reference_errors(errors, "design", documents["design"], "AC", acceptance)
        add_missing_reference_errors(errors, "design", documents["design"], reqs)
        add_missing_reference_errors(errors, "design", documents["design"], acceptance)
    else:
        decisions = set()

    if "plan" in documents:
        tasks = {item for item in stage_definitions["plan"] if item.startswith("TASK-")}
        if not tasks:
            errors.append("plan.md must define at least one TASK ID")
        for prefix, known in (("REQ", reqs), ("AC", acceptance), ("DEC", decisions)):
            add_unknown_reference_errors(errors, "plan", documents["plan"], prefix, known)
            add_missing_reference_errors(errors, "plan", documents["plan"], known)
        if not re.search(r"新增代码行覆盖率阈值[：:]\s*90%", documents["plan"]):
            errors.append("plan.md must set new-code line coverage threshold to 90%")
        if not re.search(r"新增代码分支覆盖率阈值[：:]\s*80%", documents["plan"]):
            errors.append("plan.md must set new-code branch coverage threshold to 80%")
    else:
        tasks = set()

    if "execution" in documents:
        execution_tasks = {
            item
            for item in stage_definitions["execution"]
            if item.startswith("TASK-")
        }
        for unknown in sorted(execution_tasks - tasks):
            errors.append(f"execution.md references unknown {unknown}")
        for missing in sorted(tasks - execution_tasks):
            errors.append(f"execution.md does not report {missing}")

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
