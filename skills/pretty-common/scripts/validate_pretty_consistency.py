#!/usr/bin/env python3
"""Check that Pretty rules, routes and phase contracts have one interpretation."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable

from evidence_binding import COMMON_BUNDLE_FILES, bundle_sha256

from quality_registry import (
    MIN_BRANCH_COVERAGE,
    MIN_LINE_COVERAGE,
    PRECEDENCE,
    RISK_OWNERS,
    registry_errors,
)


REMOVED_MODE_TERMS = (
    "dry" + " run",
    "dry" + "-run",
    "pre" + "view",
    "execution-" + "preview",
    "test-" + "preview",
)
RETIRED_SLICE_TERMS = (
    "slice-" + "coverage",
    "Slice" + "CoverageRequest",
    "gate_" + "each_slice",
    "gate_before_" + "next_slice",
)
HASH_DEFINITIONS = (
    "bytes_sha256",
    "file_sha256",
    "bundle_sha256",
    "candidate_sha256",
    "evidence_sha256",
    "canonical_json_bytes",
    "payload_sha256",
    "self_bound_sha256",
)


def _skill_files(skill: Path | None) -> list[Path]:
    if skill is None:
        return []
    if skill.is_file():
        return [skill]
    if skill.is_dir():
        return sorted(path for path in skill.rglob("*") if path.is_file())
    return []


def _skill_document(skill: Path | None) -> Path | None:
    if skill is None:
        return None
    document = skill / "SKILL.md" if skill.is_dir() else skill
    return document if document.is_file() else None


def _routing_rows(text: str) -> dict[str, str]:
    return dict(re.findall(r"^\| `([^`]+)` \|.*\| `([^`]+)` \|$", text, re.MULTILINE))


def _runtime_files(skills_root: Path) -> list[Path]:
    return [
        path for path in skills_root.rglob("*")
        if path.is_file() and path.name != Path(__file__).name
    ]


def _retired_surface_errors(common_root: Path) -> list[str]:
    skills_root = common_root.parent
    errors: list[str] = []
    for path in _runtime_files(skills_root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        lowered = text.lower()
        for term in REMOVED_MODE_TERMS:
            if term.lower() in lowered:
                errors.append(f"removed execution mode remains in {path.relative_to(skills_root)}")
        for term in RETIRED_SLICE_TERMS:
            if term in text:
                errors.append(f"retired per-slice coverage branch remains in {path.relative_to(skills_root)}")
    obsolete = (
        skills_root / "pretty-executing/assets" / ("execution-" + "preview.md"),
        skills_root / "pretty-executing/references" / ("test-" + "preview.md"),
        skills_root / "pretty-executing/scripts" / ("validate_" + "preview.py"),
    )
    errors.extend(
        f"removed execution mode file still exists: {path.relative_to(skills_root)}"
        for path in obsolete if path.exists()
    )
    return errors


def _hash_ownership_errors(common_root: Path) -> list[str]:
    skills_root = common_root.parent
    owner = common_root / "scripts/evidence_binding.py"
    errors: list[str] = []
    for path in skills_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if path.resolve() != owner.resolve() and re.search(r"hashlib\.sha256\s*\(", text):
            errors.append(f"direct hashlib.sha256 use remains outside shared evidence binding: {path.relative_to(skills_root)}")
        for name in HASH_DEFINITIONS:
            if re.search(rf"^def\s+{name}\s*\(", text, re.MULTILINE) and path.resolve() != owner.resolve():
                errors.append(f"shared hash {name} is redefined in {path.relative_to(skills_root)}")
    return errors


def _threshold_errors(common_root: Path) -> list[str]:
    registry = common_root / "scripts/quality_registry.py"
    errors = []
    for path in common_root.parent.rglob("*.py"):
        if path.resolve() == registry.resolve():
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r"^\s*MIN_(?:LINE|BRANCH)_COVERAGE\s*=", text, re.MULTILINE):
            errors.append(f"coverage minimum is redefined outside registry: {path}")
    if MIN_LINE_COVERAGE < MIN_BRANCH_COVERAGE:
        errors.append("line coverage minimum must not be lower than branch coverage minimum")
    return errors


def consistency_errors(
    common_root: Path,
    *,
    executing_skill: Path | None = None,
) -> list[str]:
    errors = list(registry_errors())
    errors.extend(_retired_surface_errors(common_root))
    errors.extend(_hash_ownership_errors(common_root))
    errors.extend(_threshold_errors(common_root))
    errors.extend(
        f"shared quality bundle file is missing: {relative}"
        for relative in COMMON_BUNDLE_FILES
        if not (common_root / relative).is_file()
    )
    routing_path = common_root / "references/quality-routing.md"
    routing = routing_path.read_text(encoding="utf-8") if routing_path.is_file() else ""
    if _routing_rows(routing) != RISK_OWNERS:
        errors.append("quality-routing.md risk ownership differs from the shared registry")
    principles = (common_root / "references/quality-principles.md").read_text(encoding="utf-8")
    review_protocol = (common_root / "references/quality-review-protocol.md").read_text(encoding="utf-8")
    if (
        "GENERIC-NORMALIZATION-HELPER" not in principles
        or "不可豁免的机械错误" not in principles
    ):
        errors.append("shared principles must define GENERIC-NORMALIZATION-HELPER as non-waivable")
    for index, item in enumerate(PRECEDENCE):
        if item not in principles:
            errors.append(f"QP-03 precedence is missing: {item}")
        if index and principles.find(PRECEDENCE[index - 1]) > principles.find(item):
            errors.append("QP-03 precedence order is inconsistent")
    if "风险路由" not in principles or "不定义风险路由" not in routing:
        errors.append("precedence and risk routing must be explicitly separated")
    if "只有执行阶段的真实可执行产物强制独立 Reviewer" not in review_protocol:
        errors.append("execution must require an independent Reviewer")
    if executing_skill is not None and _skill_document(executing_skill) is None:
        errors.append(f"Executing Skill path is missing SKILL.md: {executing_skill}")
    executing_document = _skill_document(executing_skill)
    if executing_document:
        text = executing_document.read_text(encoding="utf-8")
        if re.search(r"并行运行[^\n]*Reviewer[^\n]*(?:覆盖率|编译|回归)", text):
            errors.append("final Reviewer must start after objective coverage/build/test gates")
        if "合同可执行性预检" not in text:
            errors.append("Execution must perform a contract executability preflight")
        if "唯一最终 Reviewer" not in text and "唯一最终独立 Reviewer" not in text:
            errors.append("execution must retain one final independent Reviewer")
        for required in ("Candidate Lane", "Promotion", "register", "resume", "rebind", "reopen"):
            if required not in text:
                errors.append(f"execution workflow is missing {required}")
        if "Slice Fast Gate" not in text:
            errors.append("execution workflow must retain Slice Fast Gate")
    return sorted(set(errors))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--common-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--executing-skill", type=Path)
    parser.add_argument("--output", type=Path)
    return parser


def main(arguments: Iterable[str] | None = None) -> int:
    args = _build_parser().parse_args(list(arguments) if arguments is not None else None)
    errors = consistency_errors(
        args.common_root,
        executing_skill=args.executing_skill,
    )
    payload = {
        "schema_version": 1,
        "pretty_bundle_sha256": bundle_sha256(
            args.common_root,
            _skill_files(args.executing_skill),
        ),
        "passed": not errors,
        "errors": errors,
    }
    if args.output:
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if not errors:
        print(f"Pretty consistency: passed ({payload['pretty_bundle_sha256']})")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
