#!/usr/bin/env python3
"""Check that Pretty rules, routes and phase contracts have one interpretation."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Iterable

from quality_registry import PRECEDENCE, RISK_OWNERS, registry_errors


def _bundle_files(root: Path) -> list[Path]:
    names = (
        root / "references/quality-principles.md",
        root / "references/quality-routing.md",
        root / "references/quality-review-protocol.md",
        root / "references/runtime-authorization.md",
        root / "scripts/quality_registry.py",
        root / "scripts/quality_contract_gate.py",
        root / "scripts/quality_resolver.py",
        root / "scripts/pretty_tmp.py",
        root / "scripts/validate_pretty_consistency.py",
    )
    return [path for path in names if path.is_file()]


def bundle_sha256(root: Path, extra_files: Iterable[Path] = ()) -> str:
    digest = hashlib.sha256()
    for path in sorted([*_bundle_files(root), *[item for item in extra_files if item.is_file()]]):
        try:
            label = str(path.relative_to(root))
        except ValueError:
            label = str(path)
        digest.update(label.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _routing_rows(text: str) -> dict[str, str]:
    return dict(re.findall(r"^\| `([^`]+)` \|.*\| `([^`]+)` \|$", text, re.MULTILINE))


def consistency_errors(
    common_root: Path,
    *,
    design_skill: Path | None = None,
    executing_skill: Path | None = None,
) -> list[str]:
    errors = list(registry_errors())
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
    if "只有 Apply 的真实可执行产物强制独立 Reviewer" not in review_protocol:
        errors.append("only Apply must require an independent Reviewer")
    if "Design 不生成 Reviewer receipt" not in review_protocol:
        errors.append("Design must not require a Reviewer receipt")
    if executing_skill and executing_skill.is_file():
        text = executing_skill.read_text(encoding="utf-8")
        if "validate_design.py" in text:
            errors.append("Execution must not call validate_design.py")
        if re.search(r"并行运行[^\n]*Reviewer[^\n]*(?:覆盖率|编译|回归)", text):
            errors.append("final Reviewer must start after objective coverage/build/test gates")
    if design_skill and design_skill.is_file():
        text = design_skill.read_text(encoding="utf-8")
        if "生成完整 Java" in text and "不生成完整 Java" not in text:
            errors.append("Design must not require complete Java generation")
        if re.search(r"review-start|review-evidence(?:\.json)?|validate_design_review\.py", text):
            errors.append("Design must not orchestrate an independent Reviewer")
        if "等待用户 Review" not in text or "证据" not in text:
            errors.append("Design must end at evidence checks and user Review")
    if executing_skill and executing_skill.is_file():
        text = executing_skill.read_text(encoding="utf-8")
        if "合同可执行性预检" not in text:
            errors.append("Execution must perform a contract executability preflight")
        if "唯一最终独立 Reviewer" not in text:
            errors.append("Apply must retain one final independent Reviewer")
    return sorted(set(errors))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--common-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--design-skill", type=Path)
    parser.add_argument("--executing-skill", type=Path)
    parser.add_argument("--output", type=Path)
    return parser


def main(arguments: Iterable[str] | None = None) -> int:
    args = _build_parser().parse_args(list(arguments) if arguments is not None else None)
    errors = consistency_errors(
        args.common_root,
        design_skill=args.design_skill,
        executing_skill=args.executing_skill,
    )
    payload = {
        "schema_version": 1,
        "pretty_bundle_sha256": bundle_sha256(
            args.common_root,
            [path for path in (args.design_skill, args.executing_skill) if path],
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
