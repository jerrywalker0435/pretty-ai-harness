"""Validate the Writer-owned contract preflight before an Apply run starts."""

from __future__ import annotations

import re
from typing import Mapping


TASK_HEADING = re.compile(r"^###\s+(TASK-\d{3})[：:]\s*\S.+$", re.MULTILINE)
UNRESOLVED = re.compile(r"\b(?:TODO|TBD|FIXME)\b|待定|待确认|待澄清|未决", re.IGNORECASE)
TASK_FIELDS = (
    "结果",
    "输入与不变量",
    "失败语义",
    "公共验证入口",
    "影响锚点",
    "验证观察面",
    "Execution 交付",
    "人工运维产物",
)
PREFLIGHT_AREAS = (
    "module_boundaries",
    "runtime_semantics",
    "verification_surface",
    "delivery_ownership",
)


def _task_bodies(design: str) -> dict[str, str]:
    matches = list(TASK_HEADING.finditer(design))
    return {
        match.group(1): design[
            match.start(): matches[index + 1].start() if index + 1 < len(matches) else len(design)
        ]
        for index, match in enumerate(matches)
    }


def _matrix_task_ids(matrix: Mapping[str, object]) -> tuple[set[str], list[str]]:
    tasks = matrix.get("tasks")
    if not isinstance(tasks, list):
        return set(), ["execution matrix tasks must be a list"]
    identifiers: set[str] = set()
    errors: list[str] = []
    for index, task in enumerate(tasks):
        identifier = task.get("id") if isinstance(task, dict) else None
        if not isinstance(identifier, str) or not identifier.strip():
            errors.append(f"execution matrix task {index} needs an id")
        elif identifier in identifiers:
            errors.append(f"execution matrix TASK id is duplicated: {identifier}")
        else:
            identifiers.add(identifier)
    return identifiers, errors


def _area_errors(area: str, check: object) -> list[str]:
    if not isinstance(check, dict):
        return [f"contract_preflight needs {area}"]
    errors: list[str] = []
    status = check.get("status")
    if status not in {"clear", "not_applicable"}:
        errors.append(f"contract_preflight {area} status must be clear or not_applicable")
    evidence = check.get("evidence")
    if not isinstance(evidence, list) or not evidence or any(
        not isinstance(item, str) or not item.strip() for item in evidence
    ):
        errors.append(f"contract_preflight {area} needs concrete evidence")
    reason = check.get("reason")
    if status == "not_applicable" and (not isinstance(reason, str) or not reason.strip()):
        errors.append(f"contract_preflight {area} not_applicable needs a reason")
    return errors


def _preflight_area_errors(preflight: object) -> list[str]:
    if not isinstance(preflight, dict):
        return ["execution matrix needs contract_preflight before code changes"]
    return [error for area in PREFLIGHT_AREAS for error in _area_errors(area, preflight.get(area))]


def contract_preflight_errors(design: str, matrix: Mapping[str, object]) -> list[str]:
    """Return blocking errors for an Execution Writer's contract preflight."""
    bodies = _task_bodies(design)
    matrix_tasks, errors = _matrix_task_ids(matrix)
    if not bodies:
        errors.append("Design needs at least one executable TASK")
    if UNRESOLVED.search(design):
        errors.append("Design contains unresolved contract language")
    if matrix_tasks != set(bodies):
        errors.append(f"execution matrix TASK set must match Design: {sorted(bodies)}")
    for task, body in bodies.items():
        missing = [
            field for field in TASK_FIELDS
            if not re.search(rf"^-\s*{re.escape(field)}：\s*\S.*$", body, re.MULTILINE)
        ]
        if missing:
            errors.append(f"{task} is not executable; missing fields: {', '.join(missing)}")
    errors.extend(_preflight_area_errors(matrix.get("contract_preflight")))
    return sorted(set(errors))


def contract_preflight_summary() -> dict[str, object]:
    return {"status": "passed", "areas": list(PREFLIGHT_AREAS)}
