#!/usr/bin/env python3
"""Validate a Pretty implementation Plan and its Java proposals."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Mapping, Sequence


COMMON_SCRIPTS = Path(__file__).resolve().parents[2] / "pretty-common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

from quality_contract_gate import (  # type: ignore[import-not-found]
    QualityFinding,
    candidate_sha256,
    load_review_evidence,
    mask_java_non_code,
    method_spans,
    review_evidence_errors,
    scan_java_source,
)


TITLE = re.compile(r"^#\s+.+\s+Implementation Plan\s*$")
TASK = re.compile(r"^###\s+TASK-(\d{3})[：:]\s*\S.+$", re.MULTILINE)
FILE_ENTRY = re.compile(
    r"^[-*+]\s+(Create|Modify|Test|Delete):\s+\x60([^\x60\n]+)\x60\s*$",
    re.MULTILINE,
)
PLACEHOLDER = re.compile(r"\b(?:TODO|TBD|FIXME)\b|<[^>\n]*(?:\.\.\.|待|完整|真实|主题|结果|路径)[^>\n]*>", re.IGNORECASE)
PERSONAL_PATH = re.compile(r"(?:^|[\s\x60(])/(?:Users|home|private/(?:tmp|var))/|\b[A-Z]:\\")
EXTERNAL_SKILL = re.compile(
    r"\b(?:codebase-design|121-java-object-oriented-design|122-java-type-design|"
    r"solid-principles|design-patterns|java-code-review|clean-code-guard|tdd)\b",
    re.IGNORECASE,
)
QUALITY_REPORT = re.compile(r"质量(?:审查|评分|报告)|Quality\s+Gate", re.IGNORECASE)
VARARGS = re.compile(r"\b[\w$]+(?:\s*<[^>\n]+>)?(?:\s*\[\])?\s*\.\.\.\s*[\w$]+")
FENCE = re.compile(r"^[ \t]*([\x60~])\1{2,}")
DML_STATEMENT = re.compile(r"(?im)^\s*(?:INSERT|UPDATE|DELETE|REPLACE|MERGE)\b")
CONFIGURATION_DATA_CONTEXT = re.compile(
    r"配置数据|白名单|事件定义|种子数据|reference\s+data|seed\s+data|"
    r"(?:config|setting|define|definition|dictionary|whitelist)[A-Za-z0-9_]*",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FencedBlock:
    start: int
    content_start: int
    content_end: int
    end: int
    language: str


def _line_number(text: str, position: int) -> int:
    return text.count("\n", 0, max(0, position)) + 1


def _fence_marker(line: str) -> tuple[str, int] | None:
    match = FENCE.match(line)
    if not match:
        return None
    character = match.group(1)
    return character, match.group(0).count(character)


def fenced_blocks(text: str) -> tuple[list[FencedBlock], list[int]]:
    blocks, unclosed, active, offset = [], [], None, 0
    for line in text.splitlines(keepends=True):
        marker = _fence_marker(line)
        line_end = offset + len(line)
        if active is None and marker:
            match = FENCE.match(line)
            assert match is not None
            suffix = line[match.end():].strip().split(maxsplit=1)
            active = (marker[0], marker[1], offset, line_end, suffix[0].lower() if suffix else "")
        elif active and marker and marker[0] == active[0] and marker[1] >= active[1]:
            blocks.append(FencedBlock(active[2], active[3], offset, line_end, active[4]))
            active = None
        offset = line_end
    if active:
        unclosed.append(active[2])
    return blocks, unclosed


def mask_fenced_blocks(text: str) -> str:
    blocks, unclosed = fenced_blocks(text)
    spans = [(block.start, block.end) for block in blocks]
    spans.extend((start, len(text)) for start in unclosed)
    masked = list(text)
    for start, end in spans:
        for index in range(start, end):
            if masked[index] not in "\r\n":
                masked[index] = " "
    return "".join(masked)


def _standard_path_errors(plan_path: Path) -> list[str]:
    parts = plan_path.resolve().parts
    if len(parts) < 4 or tuple(parts[-4:-2]) != ("docs", "pretty") or parts[-1] != "plan.md":
        return ["expected docs/pretty/<topic>/plan.md"]
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", parts[-2]):
        return ["Plan topic must use lowercase kebab-case"]
    errors = []
    for required in ("design.md", "prd.md"):
        if not plan_path.with_name(required).is_file():
            errors.append(f"Plan requires sibling {required}")
    return errors


def _structure_errors(text: str) -> list[str]:
    errors = [f"unclosed code fence at line {_line_number(text, start)}" for start in fenced_blocks(text)[1]]
    prose = mask_fenced_blocks(text)
    lines = [line.strip() for line in prose.splitlines() if line.strip()]
    if not lines or not TITLE.fullmatch(lines[0]):
        errors.append("first content line must be '# <topic> Implementation Plan'")
    headings = [line for line in prose.splitlines() if line.startswith("## ")]
    allowed = {"## 变更链路", "## 实施任务"}
    errors.extend(f"unsupported top-level section: {heading}" for heading in headings if heading not in allowed)
    if headings.count("## 实施任务") != 1:
        errors.append("Plan must contain exactly one '实施任务' section")
    if (
        "## 变更链路" in headings
        and "## 实施任务" in headings
        and headings.index("## 变更链路") > headings.index("## 实施任务")
    ):
        errors.append("'变更链路' must precede '实施任务'")
    return errors


def _forbidden_errors(text: str) -> list[str]:
    prose = mask_fenced_blocks(text)
    checks = (
        (PLACEHOLDER, text, "unresolved placeholder"),
        (PERSONAL_PATH, text, "personal absolute path"),
        (EXTERNAL_SKILL, prose, "final Plan must not expose Skill names"),
        (QUALITY_REPORT, prose, "final Plan must not contain a quality report"),
    )
    errors = []
    for pattern, target, message in checks:
        match = pattern.search(target)
        if match:
            errors.append(f"{message} at line {_line_number(text, match.start())}")
    for number, line in enumerate(text.splitlines(), start=1):
        if "..." in line and not VARARGS.search(line):
            errors.append(f"ellipsis hides implementation at line {number}")
            break
    return errors


def _task_ranges(text: str) -> list[tuple[int, int, int]]:
    prose = mask_fenced_blocks(text)
    matches = list(TASK.finditer(prose))
    ranges = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        next_section = prose.find("\n## ", match.end())
        ranges.append((int(match.group(1)), match.start(), min(end, next_section) if next_section >= 0 else end))
    return ranges


def _safe_file_path(path: str) -> bool:
    candidate = PurePosixPath(path)
    return (
        not candidate.is_absolute()
        and "\\" not in path
        and ".." not in candidate.parts
        and all(part not in {"", "."} for part in candidate.parts)
    )


def _project_governance_path(path: str) -> bool:
    parts = tuple(part.lower() for part in PurePosixPath(path).parts)
    if not parts:
        return False
    return (
        parts[0] == ".trellis"
        or parts[-1] in {"agents.md", "business-map.md"}
        or "adr" in parts
        or "adrs" in parts
    )


def _label_position(segment: str, label: str) -> int:
    match = re.search(rf"^{re.escape(label)}：[ \t]*$", mask_fenced_blocks(segment), re.MULTILINE)
    return match.end() if match else -1


def _section_end(segment: str, start: int) -> int:
    match = re.search(
        r"^(?:约束|修改|测试|数据库验证|依赖)：|^\*\*Files:\*\*",
        mask_fenced_blocks(segment)[start:],
        re.MULTILINE,
    )
    return start + match.start() if match else len(segment)


def _blocks_between(segment: str, start: int, end: int, language: str | None = None) -> list[FencedBlock]:
    return [
        block
        for block in fenced_blocks(segment)[0]
        if (
            start <= block.start
            and block.end <= end
            and (language is None or block.language == language)
            and segment[block.content_start:block.content_end].strip()
        )
    ]


def _java_block_has_method(segment: str, block: FencedBlock) -> bool:
    source = segment[block.content_start:block.content_end]
    return bool(method_spans(mask_java_non_code(source), "Plan proposal"))


def _task_errors(
    segment: str,
    task_id: int,
    allow_project_governance: bool,
) -> list[str]:
    prefix = f"TASK-{task_id:03d}"
    entries = FILE_ENTRY.findall(mask_fenced_blocks(segment))
    errors = [] if entries else [f"{prefix} must declare Files"]
    if "**Files:**" not in mask_fenced_blocks(segment):
        errors.append(f"{prefix} must contain **Files:**")
    errors.extend(f"{prefix} has unsafe path: {path}" for _, path in entries if not _safe_file_path(path))
    if not allow_project_governance:
        errors.extend(
            f"{prefix} has out-of-scope project-governance path: {path}"
            for _, path in entries
            if _project_governance_path(path)
        )
    modification = _label_position(segment, "修改")
    if modification < 0:
        return errors + [f"{prefix} must contain 修改"]
    modification_end = _section_end(segment, modification)
    modification_blocks = _blocks_between(segment, modification, modification_end)
    if not modification_blocks:
        errors.append(f"{prefix} 修改 must contain a non-empty code or content block")
    java_methods = any(
        block.language == "java" and _java_block_has_method(segment, block)
        for block in modification_blocks
    )
    sql_change = (
        any(operation in {"Create", "Modify"} and path.lower().endswith(".sql") for operation, path in entries)
        or any(block.language == "sql" for block in modification_blocks)
    )
    if java_methods:
        errors.extend(_logic_task_errors(segment, prefix, entries))
    if sql_change:
        errors.extend(_sql_change_errors(segment, prefix, entries, java_methods))
    return errors


def _logic_task_errors(
    segment: str,
    prefix: str,
    entries: Sequence[tuple[str, str]],
) -> list[str]:
    errors = []
    if not any(operation in {"Create", "Modify"} and path.endswith(".java") for operation, path in entries):
        errors.append(f"{prefix} logic change needs a production Java path")
    if not any(operation == "Test" or "/src/test/" in f"/{path}" for operation, path in entries):
        errors.append(f"{prefix} logic change needs a Test path")
    tests = _label_position(segment, "测试")
    if tests < 0:
        return errors + [f"{prefix} logic change must contain 测试"]
    if not _blocks_between(segment, tests, _section_end(segment, tests), "java"):
        errors.append(f"{prefix} 测试 must contain a non-empty Java code block")
    return errors


def _sql_change_errors(
    segment: str,
    prefix: str,
    entries: Sequence[tuple[str, str]],
    java_methods: bool,
) -> list[str]:
    errors = _sql_test_errors(segment, prefix, entries, java_methods)
    errors.extend(_configuration_data_dml_errors(segment, prefix))
    return errors


def _sql_test_errors(
    segment: str,
    prefix: str,
    entries: Sequence[tuple[str, str]],
    java_methods: bool,
) -> list[str]:
    errors = []
    tests = _label_position(segment, "测试")
    if tests >= 0 and _blocks_between(segment, tests, _section_end(segment, tests), "sql"):
        errors.append(f"{prefix} SQL/DDL change must not contain SQL tests")
    validation = _label_position(segment, "数据库验证")
    if validation >= 0:
        errors.append(f"{prefix} SQL/DDL change must not contain 数据库验证")
    if not java_methods:
        if tests >= 0:
            errors.append(f"{prefix} SQL-only change must not contain 测试")
        if any(operation == "Test" or "/src/test/" in f"/{path}" for operation, path in entries):
            errors.append(f"{prefix} SQL-only change must not declare Test files")
    return errors


def _configuration_data_dml_errors(segment: str, prefix: str) -> list[str]:
    for block in fenced_blocks(segment)[0]:
        if block.language != "sql":
            continue
        source = segment[block.content_start:block.content_end]
        if DML_STATEMENT.search(source) and CONFIGURATION_DATA_CONTEXT.search(segment):
            return [f"{prefix} must not contain data DML; configuration data is handled manually"]
    return []


def _tasks_errors(text: str, allow_project_governance: bool) -> list[str]:
    ranges = _task_ranges(text)
    if not ranges:
        return ["Plan must contain at least TASK-001"]
    identifiers = [task_id for task_id, _, _ in ranges]
    expected = list(range(1, len(ranges) + 1))
    errors = [] if identifiers == expected else [f"TASK ids must be continuous: {identifiers}"]
    for task_id, start, end in ranges:
        errors.extend(_task_errors(text[start:end], task_id, allow_project_governance))
    return errors


def _is_test_block(text: str, block: FencedBlock) -> bool:
    before = text[:block.start]
    positions = {
        label: before.rfind(f"{label}：")
        for label in ("修改", "测试", "数据库验证", "依赖")
    }
    return max(positions, key=positions.get) == "测试"


def plan_findings(text: str) -> list[QualityFinding]:
    findings = []
    for block in fenced_blocks(text)[0]:
        if block.language != "java":
            continue
        source = text[block.content_start:block.content_end]
        findings.extend(
            scan_java_source(
                source,
                source_name=f"plan.md:{_line_number(text, block.content_start)}",
                production=not _is_test_block(text, block),
            )
        )
    return findings


def plan_candidate_hash(text: str) -> str:
    return candidate_sha256({"plan.md": text})


def validate_plan(
    plan_path: Path,
    review_evidence: Mapping[str, object] | None = None,
    *,
    require_review: bool = False,
    allow_project_governance: bool = False,
) -> tuple[list[str], list[QualityFinding]]:
    try:
        text = plan_path.read_text(encoding="utf-8")
    except OSError as error:
        return [f"cannot read Plan: {error}"], []
    findings = plan_findings(text)
    errors = _standard_path_errors(plan_path)
    errors.extend(_structure_errors(text))
    errors.extend(_forbidden_errors(text))
    errors.extend(_tasks_errors(text, allow_project_governance))
    if require_review:
        errors.extend(review_evidence_errors(review_evidence, plan_candidate_hash(text), findings))
    else:
        errors.extend(
            f"{finding.code} at {finding.source}:{finding.line}"
            for finding in findings
            if finding.severity == "error"
        )
    return errors, findings


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--review-evidence", type=Path)
    parser.add_argument("--scan-only", action="store_true")
    parser.add_argument("--allow-project-governance", action="store_true")
    parser.add_argument("--json-output", type=Path)
    return parser


def _write_json(path: Path | None, payload: Mapping[str, object]) -> None:
    if path:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(arguments: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(arguments)
    try:
        plan_text = args.plan.read_text(encoding="utf-8")
        evidence = load_review_evidence(args.review_evidence) if args.review_evidence else None
        errors, findings = validate_plan(
            args.plan,
            evidence,
            require_review=not args.scan_only,
            allow_project_governance=args.allow_project_governance,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Plan validation failed: {error}", file=sys.stderr)
        return 2
    for finding in findings:
        print(f"{finding.severity}: {finding.code} {finding.source}:{finding.line} [{finding.symbol}]")
    _write_json(args.json_output, {
        "candidate_sha256": plan_candidate_hash(plan_text),
        "findings": [finding.as_dict() for finding in findings],
        "passed": not errors,
        "errors": errors,
    })
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if not errors:
        print(f"Plan Gate: passed ({len(_task_ranges(plan_text))} task(s))")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
