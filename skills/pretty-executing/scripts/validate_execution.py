#!/usr/bin/env python3
"""Validate the structure and completed fields of an execution.md report."""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


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
COVERAGE = re.compile(
    r"^-\s*测试覆盖率：`增量行覆盖率\s+([^%，`]+)%.*?分支覆盖率\s+([^%`]+%|不适用)",
    re.MULTILINE,
)
COVERAGE_NOT_APPLICABLE = re.compile(r"^-\s*测试覆盖率：`不适用(?:：[^`]*)?`\s*$", re.MULTILINE)
TASK_HEADING = re.compile(r"^###\s+(TASK-\d{3})[：:]\s*\S.*$", re.MULTILINE)
STOP_CODES = {
    "CONTRACT_CONFLICT",
    "USER_CHANGES",
    "BOUNDARY_CHANGE",
    "QUALITY_OPEN",
    "VALIDATION_FAILED",
    "AUTHORIZATION_REQUIRED",
}


@dataclass(frozen=True)
class FinalGateInput:
    document: str
    contract: str
    coverage_payload: object
    review_payload: object
    routes_payload: object
    repo: Path | None
    base: str | None
    expected_paths: Sequence[str]


@dataclass(frozen=True)
class ReviewGateInput:
    document: str
    review_payload: object
    routes_payload: object
    expected_paths: Sequence[str]
    production: set[str]


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


def _coverage_payload_errors(payload: object, line_threshold: float, branch_threshold: float) -> list[str]:
    if not isinstance(payload, dict):
        return ["completed execution coverage result must be a JSON object"]
    if payload.get("status") not in {"pass", "not_applicable"}:
        return ["completed execution requires a passing incremental coverage result"]
    if payload.get("status") == "not_applicable":
        return []
    line_value, branch_value = payload.get("line_percentage"), payload.get("branch_percentage")
    if isinstance(line_value, bool) or not isinstance(line_value, (int, float)):
        return ["completed execution coverage result must include numeric percentages"]
    branch_total = payload.get("branch_total")
    if branch_total is not None and (
        isinstance(branch_total, bool) or not isinstance(branch_total, int) or branch_total < 0
    ):
        return ["completed execution coverage result must include a numeric branch_total"]
    branch_without_measurements = branch_total == 0 and branch_value is None
    if not branch_without_measurements and (
        isinstance(branch_value, bool) or not isinstance(branch_value, (int, float))
    ):
        return ["completed execution coverage result must include numeric percentages"]
    try:
        line_limit = float(payload.get("line_threshold", line_threshold))
        branch_limit = float(payload.get("branch_threshold", branch_threshold))
    except (TypeError, ValueError):
        return ["completed execution coverage result must include numeric thresholds"]
    if any(not math.isfinite(value) or value < 0 or value > 100 for value in (line_limit, branch_limit)):
        return ["completed execution coverage result thresholds must be between 0 and 100"]
    if not math.isfinite(float(line_value)) or (
        not branch_without_measurements and not math.isfinite(float(branch_value))
    ):
        return ["completed execution coverage result must include finite percentages"]
    if line_value < 0 or line_value > 100 or (
        not branch_without_measurements and (branch_value < 0 or branch_value > 100)
    ):
        return ["completed execution coverage percentages must be between 0 and 100"]
    errors = []
    if line_value < line_limit:
        errors.append(f"completed execution has incremental line coverage below threshold: {line_value:.2f}%")
    if not branch_without_measurements and branch_value < branch_limit:
        errors.append(f"completed execution has incremental branch coverage below threshold: {branch_value:.2f}%")
    return errors


def _coverage_text_errors(document: str, line_threshold: float, branch_threshold: float) -> list[str]:
    match = COVERAGE.search(document)
    if not match:
        if re.search(r"^-\s*测试覆盖率：`[^`]*不适用", document, re.MULTILINE):
            return []
        return ["completed execution needs parseable coverage results"]
    try:
        line = float(match.group(1))
        branch = None if match.group(2) == "不适用" else float(match.group(2).removesuffix("%"))
    except ValueError:
        return ["completed execution needs numeric coverage results"]
    errors = []
    if line < line_threshold:
        errors.append(f"completed execution has incremental line coverage below {line_threshold:g}%: {line:.2f}%")
    if branch is not None and branch < branch_threshold:
        errors.append(f"completed execution has incremental branch coverage below {branch_threshold:g}%: {branch:.2f}%")
    return errors


def _coverage_consistency_errors(document: str, payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return []
    match = COVERAGE.search(document)
    if payload.get("status") == "not_applicable":
        if not COVERAGE_NOT_APPLICABLE.search(document):
            return ["not_applicable coverage JSON must be recorded as 不适用 in execution report"]
        return []
    if not match:
        return ["final execution coverage text must match the coverage JSON result"]
    try:
        text_line = float(match.group(1))
        text_branch = None if match.group(2) == "不适用" else float(match.group(2).removesuffix("%"))
    except ValueError:
        return ["final execution coverage text must match the coverage JSON result"]
    payload_line = payload.get("line_percentage")
    payload_branch = payload.get("branch_percentage")
    if isinstance(payload_line, bool) or not isinstance(payload_line, (int, float)):
        return ["final execution coverage text must match the coverage JSON result"]
    if abs(float(payload_line) - text_line) > 0.01:
        return ["execution report line coverage does not match coverage JSON"]
    if payload_branch is None and text_branch is None:
        return []
    if isinstance(payload_branch, bool) or not isinstance(payload_branch, (int, float)) or text_branch is None:
        return ["execution report branch coverage does not match coverage JSON"]
    if abs(float(payload_branch) - text_branch) > 0.01:
        return ["execution report branch coverage does not match coverage JSON"]
    return []


def _coverage_errors(
    document: str,
    line_threshold: float = 90.0,
    branch_threshold: float = 80.0,
    coverage_payload: dict[str, Any] | None = None,
) -> list[str]:
    if not _is_completed_status(_conclusion_status(document)):
        return []
    if coverage_payload is not None:
        return [
            *_coverage_payload_errors(coverage_payload, line_threshold, branch_threshold),
            *_coverage_consistency_errors(document, coverage_payload),
        ]
    return _coverage_text_errors(document, line_threshold, branch_threshold)


def _section_body(document: str, heading: str) -> str:
    lines = document.splitlines()
    marker = f"## {heading}"
    if marker not in lines:
        return ""
    start = lines.index(marker) + 1
    end = next((index for index in range(start, len(lines)) if lines[index].startswith("## ")), len(lines))
    return "\n".join(lines[start:end])


def _contract_tasks(contract: str) -> list[str]:
    for heading in ("实施影响", "实施任务"):
        body = _section_body(contract, heading)
        tasks = TASK_HEADING.findall(body)
        if tasks:
            return list(dict.fromkeys(tasks))
    return []


def _execution_tasks(document: str) -> dict[str, str]:
    task_section = _section_body(document, "TASK 结果")
    matches = list(TASK_HEADING.finditer(task_section))
    result: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(task_section)
        block = task_section[match.start():end]
        status = re.search(r"^-\s*状态：`([^`]+)`", block, re.MULTILINE)
        if status:
            result[match.group(1)] = status.group(1)
    return result


def _git_paths(repo: Path, base: str) -> set[str]:
    def run(args: list[str]) -> str:
        result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
        if result.returncode:
            raise ValueError(result.stderr.strip() or "git query failed")
        return result.stdout

    changed = set(run(["diff", "--name-only", base, "--"]).splitlines())
    changed.update(run(["ls-files", "--others", "--exclude-standard"]).splitlines())
    return changed


def _task_contract_errors(document: str, contract: str) -> tuple[list[str], list[str], dict[str, str]]:
    errors: list[str] = []
    expected_tasks = _contract_tasks(contract)
    actual_tasks = _execution_tasks(document)
    task_section = _section_body(document, "TASK 结果")
    task_ids = TASK_HEADING.findall(task_section)
    heading_set = set(task_ids)
    duplicates = sorted({task for task in task_ids if task_ids.count(task) > 1})
    if duplicates:
        errors.append("execution report contains duplicate TASKs: " + ", ".join(duplicates))
    if not expected_tasks:
        errors.append("contract must declare at least one TASK")
    missing = [task for task in expected_tasks if task not in actual_tasks]
    if missing:
        errors.append("execution report is missing TASK results: " + ", ".join(missing))
    extra = sorted(heading_set - set(expected_tasks))
    if extra:
        errors.append("execution report contains TASKs absent from contract: " + ", ".join(extra))
    missing_status = sorted(heading_set - set(actual_tasks))
    if missing_status:
        errors.append("execution report TASKs need a final status: " + ", ".join(missing_status))
    return errors, expected_tasks, actual_tasks


def _final_field_errors(document: str) -> list[str]:
    return [
        f"final execution report is missing field: {field}"
        for field in ("TASK 完成情况", "实际生产代码变更", "停止代码", "停止证据")
        if _field_value(document, field) is None
    ]


def _task_summary_errors(document: str, expected_tasks: list[str], actual_tasks: dict[str, str]) -> list[str]:
    summary = _field_value(document, "TASK 完成情况")
    if summary is None:
        return []
    errors: list[str] = []
    for task in expected_tasks:
        match = re.search(rf"{re.escape(task)}\s*[：:]\s*", summary)
        if not match:
            errors.append(f"TASK 完成情况 must include final status for {task}")
            continue
        remainder = summary[match.end():]
        next_task = re.search(r"TASK-\d{3}\s*[：:]", remainder)
        reported = remainder[:next_task.start() if next_task else None].strip(" 、,;；`")
        actual = actual_tasks.get(task)
        if actual is not None and reported != actual:
            errors.append(f"TASK 完成情况 disagrees with TASK 结果 for {task}")
    return errors


def _completed_status_errors(document: str, expected_tasks: list[str], actual_tasks: dict[str, str]) -> list[str]:
    incomplete = [task for task in expected_tasks if actual_tasks.get(task) is None or not any(
        _matches_status(actual_tasks[task], completed) for completed in COMPLETED_STATUS
    )]
    errors = ["completed execution has incomplete TASKs: " + ", ".join(incomplete)] if incomplete else []
    if _field_value(document, "停止代码") != "无" or _field_value(document, "停止证据") != "无":
        errors.append("completed execution must set stop code and evidence to 无")
    return errors


def _stopped_status_errors(document: str, status: str) -> list[str]:
    errors: list[str] = []
    if "停止：" not in status or len(status.split("：", 1)[1].strip()) < 8:
        errors.append("stopped execution needs a concrete blocking reason")
    evidence = _field_value(document, "停止证据")
    stop_code = _field_value(document, "停止代码")
    if stop_code not in STOP_CODES:
        errors.append("stopped execution needs a supported stop code")
    if evidence in {None, "", "无"}:
        errors.append("stopped execution needs concrete blocking evidence")
    errors.extend(_stop_evidence_errors(stop_code, evidence or ""))
    external_markers = (
        "人工外部验证", "数据库联调", "远程掌中宝", "远程服务",
        "真实数据库", "真实 Dubbo", "SQL 执行计划",
    )
    if any(marker in status for marker in external_markers):
        errors.append("external validation cannot be the stopping reason")
    return errors


def _returned_status_errors(document: str, status: str) -> list[str]:
    errors: list[str] = []
    if "：" not in status or len(status.split("：", 1)[1].strip()) < 8:
        errors.append("returned execution needs a concrete reason")
    if _field_value(document, "停止代码") != "CONTRACT_CONFLICT":
        errors.append("returned execution must use stop code CONTRACT_CONFLICT")
    evidence = _field_value(document, "停止证据")
    if evidence in {None, "", "无"}:
        errors.append("returned execution needs contract evidence")
    else:
        errors.extend(_stop_evidence_errors("CONTRACT_CONFLICT", evidence))
    return errors


def _stop_evidence_errors(stop_code: str | None, evidence: str) -> list[str]:
    required_terms = {
        "CONTRACT_CONFLICT": ("冲突", "不一致", "需求", "contract", "Design", "Plan"),
        "USER_CHANGES": ("未提交", "modified", "dirty", "working tree", "用户修改"),
        "BOUNDARY_CHANGE": ("边界", "接口", "所有权", "事务", "并发", "幂等", "安全", "scope"),
        "QUALITY_OPEN": ("open", "finding", "质量", "Review"),
        "VALIDATION_FAILED": ("失败", "failed", "退出码", "exit", "exited", "error"),
        "AUTHORIZATION_REQUIRED": (
            "授权", "权限", "permission", "forbidden", "not permitted", "access denied", "denied", "sandbox",
        ),
    }
    if stop_code not in required_terms:
        return []
    if any(term.lower() in evidence.lower() for term in required_terms[stop_code]):
        return []
    return [f"stop evidence does not support stop code: {stop_code}"]


def _status_errors(document: str, expected_tasks: list[str], actual_tasks: dict[str, str]) -> list[str]:
    status = _conclusion_status(document)
    errors = [*_final_field_errors(document), *_task_summary_errors(document, expected_tasks, actual_tasks)]
    if _is_completed_status(status):
        return [*errors, *_completed_status_errors(document, expected_tasks, actual_tasks)]
    if status and status.startswith("停止"):
        return [*errors, *_stopped_status_errors(document, status)]
    if status and (status.startswith("返回 PRD") or status.startswith("返回 Design")):
        return [*errors, *_returned_status_errors(document, status)]
    return errors


def _build_verification_errors(document: str, require_coverage: bool = True) -> list[str]:
    value = _field_value(document, "构建验证") or ""
    normalized = value.lower()
    compact = normalized.replace(" ", "")
    errors: list[str] = []
    if not re.search(r"\b(?:mvnw?|gradlew?|gradle)\b", normalized):
        errors.append("completed execution build verification must record a Maven or Gradle command")
    if not re.search(r"\b(?:test|check|verify)\b", normalized):
        errors.append("completed execution build verification must include a test task")
    if require_coverage and "jacoco" not in normalized and "coverage" not in normalized:
        errors.append("completed execution build verification must include JaCoCo or coverage reporting")
    if not re.search(r"(?:exit(?:code)?|退出码)[=:：]?0(?:\D|$)", compact):
        errors.append("completed execution build verification must record a successful final exit code")
    if "执行次数" not in value and not re.search(r"执行\s*[一二三四五六七八九十0-9]+\s*次", value):
        errors.append("completed execution build verification must record the final invocation count")
    count_match = re.search(r"执行次数\s*[=:：]\s*(-?\d+)", value)
    if count_match and int(count_match.group(1)) < 1:
        errors.append("completed execution build verification invocation count must be positive")
    return errors


def _production_paths(
    repo: Path | None,
    base: str | None,
    scope: Sequence[str] = (),
) -> set[str]:
    if repo is None or not base:
        return set()
    changed = _git_paths(repo, base)
    if scope:
        changed &= set(scope)
    return {
        path for path in changed
        if _is_production_java_path(path)
    }


def _is_production_java_path(path: str) -> bool:
    normalized = "/" + path.replace("\\", "/").lower().strip("/")
    excluded = ("/src/test/", "/test/", "/target/", "/build/", "/generated/", "/generated-sources/")
    return normalized.endswith(".java") and not any(item in normalized for item in excluded)


def _review_route_errors(review_payload: dict[str, Any], routes_payload: object, production: set[str]) -> list[str]:
    if not production:
        return []
    routes = review_payload.get("routes_applied")
    errors = []
    applied_routes = routes if isinstance(routes, list) and all(isinstance(route, str) for route in routes) else []
    if "clean-code-guard" not in applied_routes:
        errors.append("production completion requires routes_applied including clean-code-guard")
    if not isinstance(routes_payload, dict):
        errors.append("production completion requires the quality route JSON result")
        return errors
    java_production = set(production)
    routed_production = routes_payload.get("production_java")
    if not isinstance(routed_production, list) or any(not isinstance(path, str) for path in routed_production):
        errors.append("quality route JSON must contain a production_java path list")
    elif len(routed_production) != len(set(routed_production)):
        errors.append("quality route JSON production_java must not contain duplicates")
    elif set(routed_production) != java_production:
        errors.append("quality route JSON production_java does not match the Java production diff")
    route_records = routes_payload.get("routes")
    if not isinstance(route_records, list):
        errors.append("quality route JSON must contain a routes list")
        return errors
    required = {
        str(route.get("skill"))
        for route in route_records
        if isinstance(route, dict) and isinstance(route.get("skill"), str) and route["skill"].strip()
    }
    if len(required) != len(route_records):
        errors.append("quality route JSON routes must contain unique, non-empty skills")
    if not required.issubset(set(applied_routes)):
        errors.append("Review routes_applied do not cover every route selected by quality_resolver")
    return errors


def _review_errors(gate_input: ReviewGateInput) -> list[str]:
    review_payload = gate_input.review_payload
    completed = _is_completed_status(_conclusion_status(gate_input.document))
    if review_payload is None:
        if completed and gate_input.production:
            return ["final completion requires the quality Review JSON result"]
        return []
    if not isinstance(review_payload, dict):
        return ["quality Review JSON must be an object"]
    try:
        from quality_review_gate import validate_closed, summary
    except ImportError as error:
        return [f"quality review gate unavailable: {error}"]
    review_validator = validate_closed if completed else validate
    errors = review_validator(review_payload, gate_input.expected_paths)
    errors.extend(_review_route_errors(review_payload, gate_input.routes_payload, gate_input.production))
    return [*errors, *_review_quality_errors(gate_input.document, review_payload, summary)]


def _quality_summary(match: re.Match[str]) -> str:
    return "clean-code-guard " + match.group(0).split("clean-code-guard ", 1)[1].rstrip("`")


def _review_quality_errors(document: str, review_payload: dict[str, Any], summary: Any) -> list[str]:
    quality_match = QUALITY_GATE.search(document)
    if quality_match and summary(review_payload) != _quality_summary(quality_match):
        return ["execution report quality counts do not match Review JSON"]
    return []


def _production_completion_errors(
    document: str,
    status: str | None,
    production: set[str],
    expected_paths: Sequence[str],
) -> list[str]:
    if not _is_completed_status(status):
        return []
    errors: list[str] = []
    if _matches_status(status or "", "完成") and not production:
        errors.append(
            "completed execution requires a production code diff; use "
            "已满足（无生产差异） when none is required"
        )
    if _matches_status(status or "", "已满足（无生产差异）") and production:
        errors.append("已满足（无生产差异） cannot be used when the Git diff contains production changes")
    return [*errors, *_production_diff_errors(document, production, expected_paths)]


def _production_diff_errors(document: str, production: set[str], expected_paths: Sequence[str]) -> list[str]:
    if not production:
        return []
    errors: list[str] = []
    declared_changes = _field_value(document, "实际生产代码变更") or ""
    missing_declared = sorted(path for path in production if path not in declared_changes)
    if missing_declared:
        errors.append("actual production code changes are missing Git diff files: " + ", ".join(missing_declared))
    if expected_paths:
        missing = sorted(production - set(expected_paths))
        if missing:
            errors.append("Review --path is missing production diff files: " + ", ".join(missing))
    else:
        errors.append("final completion with production changes requires --path for every reviewed file")
    return errors


def _final_gate_errors(gate_input: FinalGateInput) -> list[str]:
    errors, expected_tasks, actual_tasks = _task_contract_errors(gate_input.document, gate_input.contract)
    errors.extend(_status_errors(gate_input.document, expected_tasks, actual_tasks))
    if _is_completed_status(_conclusion_status(gate_input.document)):
        coverage_is_not_applicable = (
            isinstance(gate_input.coverage_payload, dict)
            and gate_input.coverage_payload.get("status") == "not_applicable"
        )
        errors.extend(_build_verification_errors(gate_input.document, not coverage_is_not_applicable))
    errors.extend(_coverage_errors(gate_input.document, coverage_payload=gate_input.coverage_payload))
    if _is_completed_status(_conclusion_status(gate_input.document)) and gate_input.coverage_payload is None:
        errors.append("final completion requires the verify_incremental_coverage JSON result")
    production = _production_paths(gate_input.repo, gate_input.base, gate_input.expected_paths)
    errors.extend(_review_errors(ReviewGateInput(
        gate_input.document, gate_input.review_payload, gate_input.routes_payload,
        gate_input.expected_paths, production,
    )))
    if gate_input.repo is not None and gate_input.base:
        status = _conclusion_status(gate_input.document)
        errors.extend(_production_completion_errors(
            gate_input.document, status, production, gate_input.expected_paths,
        ))
    return errors


def validate(
    document: str,
    coverage_payload: dict[str, Any] | None = None,
    include_coverage: bool = True,
) -> list[str]:
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
    if include_coverage:
        errors.extend(_coverage_errors(document, coverage_payload=coverage_payload))
    return errors


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="execution.md 路径")
    parser.add_argument(
        "--final", action="store_true", help="执行最终合同、TASK、Review、覆盖率和 diff 门禁"
    )
    parser.add_argument("--contract", type=Path, help="Design 或 execution-plan 文件；--final 必填")
    parser.add_argument("--coverage-json", type=Path, help="verify_incremental_coverage.py 的 JSON 输出")
    parser.add_argument("--review-json", type=Path, help="quality_review_gate.py 的 Review JSON")
    parser.add_argument("--routes-json", type=Path, help="quality_resolver.py 的 JSON 输出")
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--base", help="Git 基线；--final 时用于检查生产 diff")
    parser.add_argument("--path", action="append", default=[], help="Review JSON 应覆盖的文件；可重复")
    return parser


def _json_payload(path: Path | None) -> object:
    return json.loads(path.read_text(encoding="utf-8")) if path else None


def _final_cli_errors(args: argparse.Namespace, document: str, coverage_payload: object) -> list[str]:
    errors = []
    if not args.contract:
        errors.append("--final requires --contract")
    if not args.base:
        errors.append("--final requires --base")
    contract = args.contract.read_text(encoding="utf-8") if args.contract else ""
    return [*errors, *_final_gate_errors(FinalGateInput(
        document, contract, coverage_payload, _json_payload(args.review_json),
        _json_payload(args.routes_json), args.repo.resolve(), args.base, args.path,
    ))]


def _print_errors(errors: Sequence[str]) -> None:
    for error in errors:
        print(f"error: {error}", file=sys.stderr)


def main(arguments: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(arguments)
    try:
        document = args.file.read_text(encoding="utf-8")
        coverage_payload = _json_payload(args.coverage_json)
        errors = validate(document, include_coverage=not args.final)
        if args.final:
            errors.extend(_final_cli_errors(args, document, coverage_payload))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Execution report cannot be read: {error}", file=sys.stderr)
        return 2
    if errors:
        _print_errors(errors)
        return 1
    print("Execution report: valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
