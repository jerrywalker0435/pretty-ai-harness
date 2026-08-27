"""Validate the Writer-owned contract preflight before an Apply run starts."""

from __future__ import annotations

import re
from typing import Mapping

from evidence_binding import payload_sha256
from quality_registry import RISK_BY_CODE, RULES


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
SLICE_LIST_FIELDS = (
    "paths",
    "production_symbols",
    "input_invariants",
    "boundary_substitutes",
    "result_assertions",
    "nearest_neighbors",
    "coverage_obligations",
    "resolver_rules",
    "depends_on",
    "non_goals",
)
SLICE_REQUIRED_NON_EMPTY = (
    "paths",
    "production_symbols",
    "result_assertions",
    "coverage_obligations",
    "resolver_rules",
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


def _risk_errors(risks: object, prefix: str) -> list[str]:
    if not isinstance(risks, list):
        return [f"{prefix} resolver_risks must be a list"]
    errors: list[str] = []
    seen: set[str] = set()
    for index, risk in enumerate(risks):
        if not isinstance(risk, dict):
            errors.append(f"{prefix} resolver risk {index} must be an object")
            continue
        risk_id = risk.get("id")
        if not isinstance(risk_id, str) or risk_id not in RISK_BY_CODE:
            errors.append(f"{prefix} resolver risk {index} has unknown id")
            continue
        if risk_id in seen:
            errors.append(f"{prefix} resolver risk id must be unique: {risk_id}")
        seen.add(risk_id)
        if risk.get("owner") != RISK_BY_CODE[risk_id].owner:
            errors.append(f"{prefix} resolver risk {risk_id} has the wrong owner")
        evidence = risk.get("evidence")
        if not isinstance(evidence, list) or not evidence or any(
            not isinstance(item, str) or not item.strip() for item in evidence
        ):
            errors.append(f"{prefix} resolver risk {risk_id} needs concrete evidence")
    return errors


def _slice_errors(behavior_slice: object, task_index: int, slice_index: int) -> list[str]:
    prefix = f"execution matrix task {task_index} behavior slice {slice_index}"
    if not isinstance(behavior_slice, dict):
        return [f"{prefix} must be an object"]
    errors: list[str] = []
    if not isinstance(behavior_slice.get("id"), str) or not behavior_slice["id"].strip():
        errors.append(f"{prefix} needs an id")
    if not isinstance(behavior_slice.get("test_entry"), str) or not behavior_slice["test_entry"].strip():
        errors.append(f"{prefix} needs a test_entry")
    for field in SLICE_LIST_FIELDS:
        values = behavior_slice.get(field)
        if not isinstance(values, list) or any(
            not isinstance(value, str) or not value.strip() for value in values
        ):
            errors.append(f"{prefix} {field} must be a string list")
    for field in SLICE_REQUIRED_NON_EMPTY:
        if behavior_slice.get(field) == []:
            errors.append(f"{prefix} {field} must not be empty")
    if behavior_slice.get("resolver_rules") != [rule.code for rule in RULES]:
        errors.append(f"{prefix} resolver_rules must contain the complete shared registry in order")
    errors.extend(_risk_errors(behavior_slice.get("resolver_risks"), prefix))
    return errors


def _slice_contract_errors(matrix: Mapping[str, object]) -> list[str]:
    tasks = matrix.get("tasks")
    if not isinstance(tasks, list):
        return []
    errors: list[str] = []
    identifiers: set[str] = set()
    for task_index, task in enumerate(tasks):
        if not isinstance(task, dict):
            continue
        java_paths = [
            path
            for field in ("production_files", "test_files")
            for path in task.get(field, [])
            if isinstance(path, str) and path.endswith(".java")
        ]
        slices = task.get("behavior_slices")
        if not isinstance(slices, list):
            errors.append(f"execution matrix task {task_index} behavior_slices must be a list")
            continue
        if not slices:
            reason = task.get("non_behavior_reason")
            if not isinstance(reason, str) or not reason.strip():
                errors.append(
                    f"execution matrix task {task_index} without behavior_slices needs non_behavior_reason"
                )
            continue
        if not java_paths:
            errors.append(f"execution matrix task {task_index} has behavior_slices without Java files")
        for slice_index, behavior_slice in enumerate(slices):
            errors.extend(_slice_errors(behavior_slice, task_index, slice_index))
            identifier = behavior_slice.get("id") if isinstance(behavior_slice, dict) else None
            if isinstance(identifier, str):
                if identifier in identifiers:
                    errors.append(f"behavior slice id is duplicated: {identifier}")
                identifiers.add(identifier)
    return errors


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
    errors.extend(_slice_contract_errors(matrix))
    return sorted(set(errors))


def contract_preflight_summary() -> dict[str, object]:
    return {"status": "passed", "areas": list(PREFLIGHT_AREAS)}


def resolver_binding_errors(
    matrix: Mapping[str, object], resolver: Mapping[str, object], design_sha256: str,
    start_head: str | None = None,
) -> list[str]:
    """Ensure the machine-derived Resolver output is the one bound to the matrix."""
    errors: list[str] = []
    if resolver.get("design_sha256") != design_sha256:
        errors.append("quality resolver does not match the current Design")
    if resolver.get("resolver_sha256") != payload_sha256(resolver, {"resolver_sha256"}):
        errors.append("quality resolver integrity hash does not match")
    if start_head is not None and resolver.get("start_head") != start_head:
        errors.append("quality resolver does not match the Apply starting HEAD")
    expected_rules = [rule.code for rule in RULES]
    if resolver.get("shared_rules") != expected_rules:
        errors.append("quality resolver shared_rules differ from the registry")
    resolver_slices = {
        item.get("id"): item
        for item in resolver.get("slices", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    tasks = matrix.get("tasks", [])
    if not isinstance(tasks, list):
        return errors + ["execution matrix tasks must be a list"]
    matrix_slice_ids: set[str] = set()
    for task in tasks:
        if not isinstance(task, dict):
            continue
        for behavior_slice in task.get("behavior_slices", []):
            if not isinstance(behavior_slice, dict) or not isinstance(behavior_slice.get("id"), str):
                continue
            identifier = behavior_slice["id"].strip()
            matrix_slice_ids.add(identifier)
            resolved = resolver_slices.get(identifier)
            if not isinstance(resolved, dict):
                errors.append(f"resolver is missing behavior slice {identifier}")
                continue
            matrix_paths = sorted(path for path in behavior_slice.get("paths", []) if isinstance(path, str))
            if resolved.get("paths") != matrix_paths:
                errors.append(f"resolver paths do not match behavior slice {identifier}")
            if behavior_slice.get("resolver_rules") != resolved.get("rules"):
                errors.append(f"resolver rules do not match behavior slice {identifier}")
            matrix_risks = sorted(
                (str(risk.get("id", "")), str(risk.get("owner", "")))
                for risk in behavior_slice.get("resolver_risks", [])
                if isinstance(risk, dict)
            )
            resolver_risks = sorted(
                (str(risk.get("id", "")), str(risk.get("owner", "")))
                for risk in resolved.get("risks", [])
                if isinstance(risk, dict)
            )
            if matrix_risks != resolver_risks:
                errors.append(f"resolver risks do not match behavior slice {identifier}")
    extra = sorted(set(resolver_slices) - matrix_slice_ids)
    if extra:
        errors.append(f"resolver contains behavior slices outside the matrix: {extra}")
    return sorted(set(errors))
