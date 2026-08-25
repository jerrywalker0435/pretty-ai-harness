#!/usr/bin/env python3
"""Validate the deterministic structure of a Pretty Design."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Mapping, Sequence


REQUIRED_SECTIONS = (
    "设计结论",
    "方案全景",
    "关键设计与权衡",
    "设计边界",
    "实施影响",
    "验证与风险",
)
FORBIDDEN_HEADINGS = ("覆盖需求", "需求覆盖", "实施计划", "Plan")
PLACEHOLDER_PATTERN = re.compile(
    r"<[^>\n]+>|\b(?:TODO|TBD|FIXME)\b|待定|待确认|未决|待澄清",
    re.IGNORECASE,
)
MERMAID_BLOCK_PATTERN = re.compile(
    r"```mermaid\s*\n(?P<body>.*?)```", re.IGNORECASE | re.DOTALL
)
MERMAID_START_PATTERN = re.compile(
    r"^(?:flowchart|graph|sequenceDiagram|stateDiagram(?:-v2)?|classDiagram|erDiagram)\b",
    re.IGNORECASE,
)
REQ_REF = re.compile(r"\bREQ-\d{3}\b")
AC_REF = re.compile(r"\bAC-\d{3}\b")
TASK_HEADING = re.compile(r"^###\s+(TASK-\d{3})[：:]\s*\S.+$", re.MULTILINE)
RISK_LEVEL = re.compile(r"^-\s*Design 风险级别：\s*(低|高)\s*$", re.MULTILINE)
RISK_TYPES = re.compile(r"^-\s*Design 风险类型：\s*(\S.*)\s*$", re.MULTILINE)
CONTRACT_SOURCES = re.compile(r"^-\s*合同来源：\s*(\S.*)\s*$", re.MULTILINE)
CONTRACT_SOURCE_HASHES = "contract_sources_sha256"


def section_headings(document: str) -> list[str]:
    """Return level-two headings in document order."""
    return [line[3:].strip() for line in document.splitlines() if line.startswith("## ")]


def section_body(document: str, heading: str) -> str:
    lines = document.splitlines()
    marker = f"## {heading}"
    if marker not in lines:
        return ""
    start = lines.index(marker) + 1
    end = next((index for index in range(start, len(lines)) if lines[index].startswith("## ")), len(lines))
    return "\n".join(lines[start:end])


def validate_mermaid_blocks(document: str) -> list[str]:
    """Return errors for empty or unsupported Mermaid blocks."""
    errors: list[str] = []
    for block in MERMAID_BLOCK_PATTERN.finditer(document):
        lines = [line.strip() for line in block.group("body").splitlines() if line.strip()]
        if not lines:
            errors.append("Mermaid 图块不能为空")
        elif not MERMAID_START_PATTERN.match(lines[0]):
            errors.append("Mermaid 图块必须声明 flowchart、sequenceDiagram、stateDiagram、classDiagram 或 erDiagram")
    return errors


def validate_design_document(document: str) -> list[str]:
    """Return deterministic structural errors for a final Design."""
    headings = section_headings(document)
    errors: list[str] = []
    if headings != list(REQUIRED_SECTIONS):
        errors.append(f"Design 二级章节必须依次为：{', '.join(REQUIRED_SECTIONS)}")
    errors.extend(f"禁止章节：{heading}" for heading in FORBIDDEN_HEADINGS if heading in headings)
    if PLACEHOLDER_PATTERN.search(document):
        errors.append("Design 仍包含占位内容或未决项")
    errors.extend(validate_mermaid_blocks(document))
    impact = section_body(document, "实施影响")
    tasks = TASK_HEADING.findall(impact)
    if not tasks:
        errors.append("实施影响至少需要一个 TASK")
    expected = list(range(1, len(tasks) + 1))
    actual = [int(task.split("-")[1]) for task in tasks]
    if actual != expected:
        errors.append("TASK 编号必须从 TASK-001 连续递增")
    if "变更职责链路" not in impact:
        errors.append("实施影响需要变更职责链路")
    for task in tasks:
        start = impact.find(f"### {task}")
        next_task = impact.find("### TASK-", start + 1)
        body = impact[start: next_task if next_task >= 0 else len(impact)]
        missing = [field for field in ("结果", "公共验证入口", "影响锚点", "验证观察面") if not re.search(rf"^-\s*{field}：\s*\S.+$", body, re.MULTILINE)]
        if missing:
            errors.append(f"{task} 缺少字段：{', '.join(missing)}")
        if not REQ_REF.search(body) or not AC_REF.search(body):
            errors.append(f"{task} 必须引用至少一个 REQ-* 和 AC-*")
    if len(set(tasks)) != len(tasks):
        errors.append("TASK ID 必须唯一")
    risk_section = section_body(document, "验证与风险")
    risk_level = RISK_LEVEL.search(risk_section)
    risk_types = RISK_TYPES.search(risk_section)
    if not risk_level:
        errors.append("验证与风险需要声明 Design 风险级别：低或高")
    if not risk_types:
        errors.append("验证与风险需要声明 Design 风险类型")
    elif risk_level and risk_level.group(1) == "高" and risk_types.group(1).strip() == "无":
        errors.append("高风险 Design 必须声明具体风险类型")
    elif risk_level and risk_level.group(1) == "低" and risk_types.group(1).strip() != "无":
        errors.append("低风险 Design 的风险类型必须为无")
    if not CONTRACT_SOURCES.search(risk_section):
        errors.append("验证与风险需要声明合同来源：无或仓库相对路径列表")
    return errors


def design_candidate_hash(design: str, prd: str, sources: Mapping[str, str] | None = None) -> str:
    parts = {"design.md": design, "prd.md": prd, **(sources or {})}
    digest = hashlib.sha256()
    for name, content in sorted(parts.items()):
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _contract_ids(prd: str, prefix: str) -> set[str]:
    return set(re.findall(rf"^###\s+({prefix}-\d{{3}})[：:]", prd, re.MULTILINE))


def _traceability_errors(design: str, prd: str) -> list[str]:
    impact = section_body(design, "实施影响")
    errors = []
    for prefix in ("REQ", "AC"):
        defined = _contract_ids(prd, prefix)
        referenced = set(re.findall(rf"\b{prefix}-\d{{3}}\b", impact))
        for identifier in sorted(referenced - defined):
            errors.append(f"实施影响引用了不存在的 {identifier}")
        for identifier in sorted(defined - referenced):
            errors.append(f"实施影响未覆盖 {identifier}")
    return errors


def _review_errors(
    evidence_path: Path | None,
    candidate: str,
    contract_hashes: Mapping[str, str],
    required: bool,
) -> list[str]:
    if evidence_path is None:
        return ["高风险 Design 需要独立 Reviewer 证据"] if required else []
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"读取 Design Reviewer 证据失败：{error}"]
    if not isinstance(evidence, dict):
        return ["Design Reviewer 证据必须是 JSON object"]
    errors = []
    if evidence.get("candidate_sha256") != candidate:
        errors.append("Design Reviewer 证据与当前候选不匹配")
    if evidence.get(CONTRACT_SOURCE_HASHES) != contract_hashes:
        errors.append("Design Reviewer 证据与当前合同来源不匹配")
    if evidence.get("independent") is not True or not str(evidence.get("reviewer", "")).strip():
        errors.append("Design Reviewer 证据必须标识独立 Reviewer")
    if evidence.get("blocking_findings") != []:
        errors.append("Design Reviewer 仍有 blocking finding")
    return errors


def _repository_relative(repository: Path, path: Path) -> str | None:
    try:
        return path.resolve().relative_to(repository).as_posix()
    except ValueError:
        return None


def _declared_contract_paths(design: str) -> set[str]:
    declaration = CONTRACT_SOURCES.search(section_body(design, "验证与风险"))
    if not declaration or declaration.group(1).strip() == "无":
        return set()
    return {
        source_reference.strip().strip("`")
        for source_reference in re.split(r"[,、]", declaration.group(1))
        if source_reference.strip()
    }


def _contract_source_contents(
    repository: Path,
    declared_paths: set[str],
    errors: list[str],
) -> tuple[dict[str, str], dict[str, str]]:
    source_contents, source_hashes = {}, {}
    for source_name in sorted(declared_paths):
        source_path = (repository / source_name).resolve()
        if _repository_relative(repository, source_path) != source_name:
            errors.append(f"合同证据必须使用仓库内规范路径：{source_name}")
            continue
        try:
            content = source_path.read_text(encoding="utf-8")
        except OSError as error:
            errors.append(f"读取合同证据失败：{error}")
            continue
        source_contents[source_name] = content
        source_hashes[source_name] = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return source_contents, source_hashes


def validate_design(
    design_path: Path,
    review_evidence: Path | None = None,
    contract_sources: Sequence[Path] = (),
) -> list[str]:
    try:
        design = design_path.read_text(encoding="utf-8")
    except OSError as error:
        return [f"读取 Design 失败：{error}"]
    prd_path = design_path.with_name("prd.md")
    try:
        prd = prd_path.read_text(encoding="utf-8")
    except OSError as error:
        return [f"Design 需要同目录 prd.md：{error}"]
    errors = validate_design_document(design)
    errors.extend(_traceability_errors(design, prd))
    repository = design_path.resolve().parents[3]
    declared_paths = _declared_contract_paths(design)
    supplied_paths = {
        relative_path
        for path in contract_sources
        if (relative_path := _repository_relative(repository, path)) is not None
    }
    if contract_sources and declared_paths != supplied_paths:
        errors.append(f"合同来源与校验输入不一致：Design={sorted(declared_paths)}，校验输入={sorted(supplied_paths)}")
    source_contents, source_hashes = _contract_source_contents(repository, declared_paths, errors)
    candidate = design_candidate_hash(design, prd, source_contents)
    risk = RISK_LEVEL.search(section_body(design, "验证与风险"))
    errors.extend(_review_errors(review_evidence, candidate, source_hashes, bool(risk and risk.group(1) == "高")))
    return errors


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("design", type=Path, help="Design 文件路径")
    parser.add_argument("--review-evidence", type=Path)
    parser.add_argument("--contract-source", action="append", type=Path, default=[])
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(arguments)
    try:
        errors = validate_design(args.design, args.review_evidence, args.contract_source)
    except (OSError, ValueError) as error:
        print(f"Design 校验失败：{error}", file=sys.stderr)
        return 2
    if errors:
        for error in errors:
            print(f"错误：{error}", file=sys.stderr)
        return 1
    print("Design 结构校验：通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
