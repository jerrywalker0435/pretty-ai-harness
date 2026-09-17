#!/usr/bin/env python3
"""Choose the next immutable execution report path for a Pretty topic."""

from __future__ import annotations

import argparse
from pathlib import Path


def next_execution_path(topic_dir: Path) -> Path:
    """Return execution.md for the first run, or the next numbered batch."""
    initial = topic_dir / "execution.md"
    batches = [
        int(path.stem.removeprefix("execution-"))
        for path in topic_dir.glob("execution-*.md")
        if path.stem.removeprefix("execution-").isdigit()
    ]
    if not initial.exists() and not batches:
        return initial
    next_batch = max([1 if initial.exists() else 0, *batches]) + 1
    return topic_dir / f"execution-{next_batch:03d}.md"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("topic_dir", type=Path)
    args = parser.parse_args()
    print(next_execution_path(args.topic_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
