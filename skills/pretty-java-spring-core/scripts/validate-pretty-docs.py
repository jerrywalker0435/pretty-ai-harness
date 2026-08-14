#!/usr/bin/env python3
"""Check the small, independent Pretty document formats."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
from typing import Dict, Iterable, List, Sequence


STAGES = ("prd", "design", "plan", "execution")
MINIMUM_HEADINGS = {
    "prd": ("背景与问题", "目标与范围", "用户与场景", "业务规则"),
    "design": ("设计结论", "方案全景", "关键设计与权衡", "设计边界"),
    "plan": ("实施结论", "实施步骤"),
    "execution": ("实施结果",),
}
PLACEHOLDER_PATTERN = re.compile(
    r"\b(?:TODO|TBD|FIXME)\b|待定|占位", re.IGNORECASE
)
PERSONAL_PATH_PATTERN = re.compile(
    r"(?:/Users/[^/\s`]+|/home/[^/\s`]+|~/[^\s`]+|[A-Za-z]:\\Users\\[^\\\s`]+)"
)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check selected docs/pretty/<topic> documents."
    )
    parser.add_argument("topic_dir", type=Path)
    parser.add_argument(
        "--through",
        choices=STAGES,
        help="Check only this stage; without it, check every existing stage file.",
    )
    return parser.parse_args(argv)


def heading_titles(text: str) -> List[str]:
    return [
        match.group(1).strip()
        for match in re.finditer(r"^##\s+(.+?)\s*$", text, re.MULTILINE)
    ]


def selected_stages(topic_dir: Path, through: str | None) -> List[str]:
    if through:
        return [through]
    return [
        stage for stage in STAGES if (topic_dir / f"{stage}.md").is_file()
    ]


def read_documents(
    topic_dir: Path, stages: Iterable[str], errors: List[str]
) -> Dict[str, str]:
    documents: Dict[str, str] = {}
    for stage in stages:
        path = topic_dir / f"{stage}.md"
        if not path.is_file():
            errors.append(f"missing document: {path}")
            continue

        text = path.read_text(encoding="utf-8")
        documents[stage] = text
        if PLACEHOLDER_PATTERN.search(text):
            errors.append(f"{stage}.md contains a placeholder")
        if PERSONAL_PATH_PATTERN.search(text):
            errors.append(f"{stage}.md contains a personal absolute path")

        headings = heading_titles(text)
        missing = [
            heading
            for heading in MINIMUM_HEADINGS[stage]
            if heading not in headings
        ]
        if missing:
            errors.append(
                f"{stage}.md is missing headings: {', '.join(missing)}"
            )
    return documents


def validate(topic_dir: Path, through: str | None = None) -> List[str]:
    errors: List[str] = []
    stages = selected_stages(topic_dir, through)
    if not stages:
        return [f"no Pretty documents found in {topic_dir}"]
    read_documents(topic_dir, stages, errors)
    return errors


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    stages = selected_stages(args.topic_dir, args.through)
    errors = validate(args.topic_dir, args.through)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"OK: {len(stages)} document(s) checked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
