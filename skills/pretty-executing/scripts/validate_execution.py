#!/usr/bin/env python3
"""Validate a final Pretty Execution report against Design and fresh evidence."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

COMMON_SCRIPTS = Path(__file__).resolve().parents[2] / "pretty-common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

from evidence_binding import evidence_sha256, file_sha256, payload_sha256, self_bound_sha256  # type: ignore[import-not-found]
from pretty_tmp import topic_dir_for_document, validate_artifact_path, validate_run_dir  # type: ignore[import-not-found]


SECTIONS = ("执行起点", "基线", "TASK 结果", "最终门禁", "未验证范围", "结论与恢复点")
TASK_HEADING = re.compile(r"^###\s+(TASK-\d{3})[：:]\s*\S.+$", re.MULTILINE)
DESIGN_TASK = re.compile(r"^###\s+(TASK-\d{3})[：:]", re.MULTILINE)
HEAD = re.compile(r"^-\s*起始 HEAD：\s*`[0-9a-f]{7,64}`\s*$", re.MULTILINE)
DESIGN_BASIS = re.compile(r"^-\s*执行依据：\s*当前工作区最新 Design\s*$", re.MULTILINE)
FINAL_STATUS = re.compile(
    r"^-\s*状态：\s*(完成|停止：\S.+|返回 PRD：\S.+|返回 Design：\S.+)\s*$",
    re.MULTILINE,
)
PLACEHOLDER = re.compile(r"<[^>\n]+>|\b(?:TODO|TBD|FIXME)\b|待验证|待审查|执行中|\.\.\.", re.IGNORECASE)
EXECUTION_DELIVERY = re.compile(r"^-\s*Execution 交付：\s*(\S.+)$", re.MULTILINE)
DDL_DELIVERY = re.compile(
    r"\bDDL\b|ALTER\s+TABLE|CREATE\s+(?:TABLE|INDEX)|DROP\s+(?:TABLE|INDEX)",
    re.IGNORECASE,
)
DDL_REPORT = "- DDL：已交付、未执行、未进行数据库验证"


@dataclass(frozen=True)
class ExecutionEvidence:
    quality: Mapping[str, object]
    coverage: Mapping[str, object]
    build: Mapping[str, object]
    tests: Mapping[str, object]
    review: Mapping[str, object] | None = None
    state: Mapping[str, object] | None = None


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _section_body(document: str, heading: str) -> str:
    lines = document.splitlines()
    marker = f"## {heading}"
    if marker not in lines:
        return ""
    start = lines.index(marker) + 1
    end = next((index for index in range(start, len(lines)) if lines[index].startswith("## ")), len(lines))
    return "\n".join(lines[start:end])


def _structure_errors(document: str, state: Mapping[str, object] | None = None) -> list[str]:
    headings = [line[3:].strip() for line in document.splitlines() if line.startswith("## ")]
    errors = []
    if state is not None and state.get("state_sha256") != payload_sha256(state, {"updated_at", "state_sha256"}):
        errors.append("execution state integrity hash does not match")
    if headings != list(SECTIONS):
        errors.append(f"sections must be exactly: {', '.join(SECTIONS)}")
    if PLACEHOLDER.search(document):
        errors.append("final Execution report contains unfinished content")
    start = _section_body(document, "执行起点")
    if not HEAD.search(start):
        errors.append("执行起点 needs a valid starting HEAD")
    if not DESIGN_BASIS.search(start):
        errors.append("执行起点 must use the current Design")
    if not FINAL_STATUS.search(_section_body(document, "结论与恢复点")):
        errors.append("结论与恢复点 needs a valid final status")
    return errors


def _task_errors(document: str, design_text: str) -> list[str]:
    design_tasks = DESIGN_TASK.findall(design_text)
    execution_tasks = TASK_HEADING.findall(_section_body(document, "TASK 结果"))
    if set(execution_tasks) != set(design_tasks):
        return [f"Execution TASK set must match Design: {design_tasks}"]
    return []


def _task_body(document: str, section: str, task: str) -> str:
    section_text = _section_body(document, section)
    start = section_text.find(f"### {task}")
    if start < 0:
        return ""
    next_task = section_text.find("### TASK-", start + 1)
    return section_text[start: next_task if next_task >= 0 else len(section_text)]


def _ddl_report_errors(document: str, design_text: str) -> list[str]:
    if not _complete_status(document):
        return []
    errors = []
    for task in DESIGN_TASK.findall(design_text):
        delivery = EXECUTION_DELIVERY.search(_task_body(design_text, "实施影响", task))
        if delivery and DDL_DELIVERY.search(delivery.group(1)):
            execution_task = _task_body(document, "TASK 结果", task)
            if DDL_REPORT not in execution_task:
                errors.append(f"{task} 的 DDL 必须报告为已交付、未执行、未进行数据库验证")
    return errors


def _complete_status(document: str) -> bool:
    return re.search(r"^-\s*状态：\s*完成\s*$", _section_body(document, "结论与恢复点"), re.MULTILINE) is not None


def _coverage_summary(coverage: Mapping[str, object]) -> str:
    status = coverage.get("status")
    if status == "not_applicable":
        return "不适用"
    if status == "unmeasurable":
        return "无法验证"
    line = coverage.get("line_percentage")
    branch = coverage.get("branch_percentage")
    if not isinstance(line, (int, float)):
        return "无法验证"
    branch_text = f"分支覆盖率 {branch:.2f}%" if isinstance(branch, (int, float)) else "分支覆盖率不适用"
    return f"增量行覆盖率 {line:.2f}%，{branch_text}"


def _coverage_errors(document: str, coverage: Mapping[str, object]) -> list[str]:
    expected = f"- 测试覆盖率：{_coverage_summary(coverage)}"
    errors = [] if expected in _section_body(document, "结论与恢复点") else [f"结论必须包含覆盖率证据：{expected}"]
    if coverage.get("scope") == "slice":
        errors.append("Execution 最终结论不能引用切片覆盖率作为最终覆盖率")
    if _complete_status(document) and coverage.get("status") not in {"pass", "not_applicable"}:
        errors.append("完成状态需要通过或不适用的增量覆盖率")
    return errors


def _gate_errors(document: str, quality: Mapping[str, object], tests: Mapping[str, object]) -> list[str]:
    gate = _section_body(document, "最终门禁")
    required = ("Design TASK 与真实 Diff", "机械 Gate", "编译与相关测试", "新增/修改测试实际执行", "增量覆盖率", "最终独立审查")
    errors = []
    for row in required:
        match = re.search(rf"^\|\s*{re.escape(row)}\s*\|[^|]*\|\s*([^|\n]+)\s*\|$", gate, re.MULTILINE)
        if not match:
            errors.append(f"最终门禁缺少：{row}")
        elif _complete_status(document) and match.group(1).strip() not in {"通过", "不适用"}:
            errors.append(f"完成状态的最终门禁未通过：{row}")
    if _complete_status(document) and quality.get("passed") is not True:
        errors.append("完成状态需要通过 quality Gate")
    if _complete_status(document) and tests.get("passed") is not True:
        errors.append("完成状态需要新增/修改测试实际执行通过")
    return errors


def _source_binding_errors(evidence: Mapping[str, object], repo: Path, label: str) -> list[str]:
    source_hashes = evidence.get("source_sha256")
    if not isinstance(source_hashes, dict):
        return [f"{label} evidence needs source_sha256"]
    errors = []
    for relative_path, expected_hash in source_hashes.items():
        source_path = repo / str(relative_path)
        if not source_path.is_file() or file_sha256(source_path) != expected_hash:
            errors.append(f"{label} evidence is stale for {relative_path}")
    return errors


def _build_errors(build: Mapping[str, object], design_path: Path, evidence: ExecutionEvidence, require_passes: bool) -> list[str]:
    errors = _evidence_binding_errors(build, design_path, evidence)
    if build.get("candidate_sha256") != self_bound_sha256(build):
        errors.append("build evidence candidate_sha256 does not match its content")
    if not isinstance(build.get("commands"), list):
        return errors + ["build evidence commands must be a list"]
    if not require_passes:
        return errors
    return errors + _required_command_errors(build, evidence)


def _evidence_integrity_errors(evidence: ExecutionEvidence) -> list[str]:
    errors = []
    for label, payload in (
        ("quality", evidence.quality),
        ("build", evidence.build),
        ("coverage", evidence.coverage),
        ("test", evidence.tests),
    ):
        expected = payload.get("evidence_sha256")
        if not isinstance(expected, str) or not expected:
            errors.append(f"{label} evidence needs evidence_sha256")
        elif expected != evidence_sha256(payload):
            errors.append(f"{label} evidence evidence_sha256 does not match its content")
    if evidence.review is not None:
        expected = evidence.review.get("evidence_sha256")
        if not isinstance(expected, str) or expected != evidence_sha256(evidence.review):
            errors.append("review evidence evidence_sha256 does not match its content")
    return errors


def _state_errors(evidence: ExecutionEvidence) -> list[str]:
    state = evidence.state
    if state is None:
        return ["completed Execution report needs execution-state.json"]
    errors = []
    if state.get("schema_version") != 4 or state.get("phase") != "promoted" or state.get("status") != "completed":
        errors.append("completed Execution report needs a promoted Apply state")
    if state.get("candidate_sha256") != evidence.quality.get("candidate_sha256"):
        errors.append("execution state does not match quality candidate")
    gate = state.get("objective_gate")
    if gate != {
        "quality_candidate_sha256": evidence.quality.get("candidate_sha256"),
        "build_candidate_sha256": evidence.build.get("candidate_sha256"),
        "test_evidence_sha256": evidence.tests.get("evidence_sha256"),
        "coverage_evidence_sha256": evidence.coverage.get("evidence_sha256"),
    }:
        errors.append("execution state objective Gate does not match evidence")
    if evidence.review is not None and state.get("review_receipt_sha256") != evidence.review.get("evidence_sha256"):
        errors.append("execution state Reviewer receipt is stale")
    return errors


def _start_head_errors(document: str, evidence: ExecutionEvidence) -> list[str]:
    match = HEAD.search(_section_body(document, "执行起点"))
    if not match:
        return []
    report_head = re.search(r"`([0-9a-f]{7,64})`", match.group(0))
    if not report_head:
        return []
    expected_prefix = report_head.group(1)
    heads = _evidence_start_heads(evidence)
    errors = [
        f"{label} evidence does not use the Execution starting HEAD"
        for label, actual in heads.items()
        if not isinstance(actual, str) or not actual.startswith(expected_prefix)
    ]
    concrete = {head for head in heads.values() if isinstance(head, str)}
    if len(concrete) > 1:
        errors.append("quality, coverage, and build evidence use different starting HEADs")
    return errors


def _evidence_start_heads(evidence: ExecutionEvidence) -> dict[str, object]:
    return {
        "quality": evidence.quality.get("start_head"),
        "coverage": evidence.coverage.get("start_head"),
        "build": evidence.build.get("start_head"),
        "test": evidence.tests.get("start_head"),
    }


def _evidence_binding_errors(
    build: Mapping[str, object], design_path: Path, evidence: ExecutionEvidence
) -> list[str]:
    design_hash = file_sha256(design_path)
    quality, coverage, tests = evidence.quality, evidence.coverage, evidence.tests
    errors = []
    if build.get("design_sha256") != design_hash:
        errors.append("build evidence does not match the current Design")
    if quality.get("design_sha256") != design_hash:
        errors.append("quality evidence does not match the current Design")
    if coverage.get("design_sha256") != design_hash:
        errors.append("coverage evidence does not match the current Design")
    if tests.get("design_sha256") != design_hash:
        errors.append("test evidence does not match the current Design")
    for label, payload in (("coverage", coverage), ("test", tests)):
        if payload.get("quality_candidate_sha256") != quality.get("candidate_sha256"):
            errors.append(f"{label} evidence does not match the frozen quality candidate")
    candidate_bindings = {
        "quality_candidate_sha256": quality.get("candidate_sha256"),
    }
    for field, expected in candidate_bindings.items():
        if not isinstance(expected, str) or not expected:
            errors.append(f"{field.removesuffix('_candidate_sha256')} evidence needs candidate_sha256")
        elif build.get(field) != expected:
            errors.append(f"build evidence has stale {field}")
    for label, payload in (("quality", quality), ("build", build), ("test", tests), ("coverage", coverage)):
        if payload.get("execution_matrix_sha256") != quality.get("execution_matrix_sha256"):
            errors.append(f"{label} evidence has stale execution matrix binding")
        if payload.get("resolver_sha256") != quality.get("resolver_sha256"):
            errors.append(f"{label} evidence has stale resolver binding")
        if payload.get("shared_bundle_sha256") != quality.get("shared_bundle_sha256"):
            errors.append(f"{label} evidence has stale shared bundle binding")
    return errors


def _pre_review_gate_errors(evidence: ExecutionEvidence) -> list[str]:
    if evidence.review is None:
        return ["completed Apply needs an independent Reviewer receipt"]
    gate = evidence.review.get("pre_review_gate")
    if not isinstance(gate, dict):
        return ["Reviewer receipt must bind the objective Gate"]
    expected = {
        "quality_candidate_sha256": evidence.quality.get("candidate_sha256"),
        "build_candidate_sha256": evidence.build.get("candidate_sha256"),
        "test_evidence_sha256": evidence.tests.get("evidence_sha256"),
        "coverage_evidence_sha256": evidence.coverage.get("evidence_sha256"),
    }
    errors = []
    for field, value in expected.items():
        if not isinstance(value, str) or not value:
            errors.append(f"pre-review {field.removesuffix('_candidate_sha256')} evidence needs candidate_sha256")
        elif gate.get(field) != value:
            errors.append(f"final Reviewer started before stable {field}")
    if evidence.review.get("candidate_sha256") != evidence.quality.get("candidate_sha256"):
        errors.append("Reviewer receipt does not match the frozen candidate")
    if evidence.review.get("independent") is not True:
        errors.append("Reviewer receipt must identify an independent Reviewer")
    if evidence.review.get("blocking_findings") != []:
        errors.append("Reviewer receipt contains blocking findings")
    return errors


def _required_command_errors(build: Mapping[str, object], evidence: ExecutionEvidence) -> list[str]:
    commands = build.get("commands")
    if not isinstance(commands, list):
        return ["build evidence commands must be a list"]
    errors = []
    satisfied = set()
    seen_commands = set()
    for index, entry in enumerate(commands):
        if not isinstance(entry, dict):
            continue
        command_key = json.dumps(entry.get("command"), ensure_ascii=False, sort_keys=True)
        if command_key in seen_commands:
            errors.append(f"equivalent build command is duplicated: {entry.get('command')}")
        seen_commands.add(command_key)
        kinds = entry.get("satisfies")
        allowed = {"compile", "new_tests", "regression_tests", "coverage"}
        if not isinstance(kinds, list) or not kinds or any(kind not in allowed for kind in kinds):
            errors.append(f"build command {index} has invalid satisfies")
            continue
        if entry.get("exit_code") != 0:
            errors.append(f"build command {index} failed")
        satisfied.update(kinds)
    mandatory = set()
    if evidence.quality.get("production_java") is True:
        mandatory.update({"compile", "regression_tests"})
    if evidence.tests.get("expected_tests"):
        mandatory.add("new_tests")
    if evidence.coverage.get("status") == "pass":
        mandatory.add("coverage")
    for kind in sorted(mandatory - satisfied):
        errors.append(f"build evidence does not satisfy required command: {kind}")
    return errors


def validate_execution(document: str, design_text: str, design_path: Path, evidence: ExecutionEvidence) -> list[str]:
    quality, coverage, build, tests = evidence.quality, evidence.coverage, evidence.build, evidence.tests
    errors = _structure_errors(document, evidence.state)
    errors.extend(_task_errors(document, design_text))
    errors.extend(_ddl_report_errors(document, design_text))
    errors.extend(_gate_errors(document, quality, tests))
    errors.extend(_coverage_errors(document, coverage))
    repo = design_path.resolve().parents[3] if len(design_path.resolve().parents) >= 4 else design_path.parent
    complete = _complete_status(document)
    if complete:
        errors.extend(_evidence_integrity_errors(evidence))
        errors.extend(_start_head_errors(document, evidence))
        errors.extend(_source_binding_errors(quality, repo, "quality"))
        errors.extend(_source_binding_errors(coverage, repo, "coverage"))
        errors.extend(_source_binding_errors(tests, repo, "test"))
        errors.extend(_build_errors(build, design_path, evidence, True))
        errors.extend(_pre_review_gate_errors(evidence))
        errors.extend(_state_errors(evidence))
    final_digest = re.search(r"^-\s*最终 Diff 摘要：\s*`([^`]+)`\s*$", _section_body(document, "结论与恢复点"), re.MULTILINE)
    if complete and (not final_digest or final_digest.group(1) != quality.get("candidate_sha256")):
        errors.append("最终 Diff 摘要必须匹配 quality candidate_sha256")
    return errors


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("execution", type=Path)
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--quality-evidence", type=Path)
    parser.add_argument("--coverage-evidence", type=Path)
    parser.add_argument("--build-evidence", type=Path)
    parser.add_argument("--test-evidence", type=Path)
    parser.add_argument("--review-evidence", type=Path)
    parser.add_argument("--state", type=Path)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(arguments)
    try:
        execution_path = args.execution.resolve()
        design_path = args.design.resolve()
        document = execution_path.read_text(encoding="utf-8")
        design_text = design_path.read_text(encoding="utf-8")
        evidence_paths = (
            args.quality_evidence, args.coverage_evidence,
            args.build_evidence, args.test_evidence,
            args.review_evidence, args.state,
        )
        run_dirs = {
            path.resolve().parent
            for path in evidence_paths
            if path is not None
        }
        if run_dirs:
            if len(run_dirs) != 1:
                raise ValueError("Execution evidence must share one topic tmp run directory")
            run_dir = validate_run_dir(topic_dir_for_document(design_path), next(iter(run_dirs)))
            for evidence_path in evidence_paths:
                if evidence_path is not None:
                    validate_artifact_path(run_dir, evidence_path.resolve())
        quality = _load_json(args.quality_evidence) if args.quality_evidence else {}
        coverage = _load_json(args.coverage_evidence) if args.coverage_evidence else {}
        build = _load_json(args.build_evidence) if args.build_evidence else {}
        tests = _load_json(args.test_evidence) if args.test_evidence else {}
        review = _load_json(args.review_evidence) if args.review_evidence else None
        state = _load_json(args.state) if args.state else None
        errors = validate_execution(
            document,
            design_text,
            design_path,
            ExecutionEvidence(quality, coverage, build, tests, review, state),
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Execution validation failed: {error}", file=sys.stderr)
        return 2
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if not errors:
        print("Execution Gate: passed")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
