#!/usr/bin/env python3
"""Select quality routes from concrete Java repository facts.

The resolver is intentionally stateless: it prints the route decision and does not
write execution state or modify the project.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Sequence

try:
    from quality_registry import DEFAULT_BRANCH_COVERAGE, DEFAULT_LINE_COVERAGE
except ImportError:  # pragma: no cover
    from .quality_registry import DEFAULT_BRANCH_COVERAGE, DEFAULT_LINE_COVERAGE


ROUTES = {
    "MODULE_BOUNDARY": ("codebase-design", "interface, seam, depth, locality, and module ownership"),
    "JAVA_OOD": ("121-java-object-oriented-design", "Java responsibility, encapsulation, and object contracts"),
    "FOCUSED_SOLID": ("solid-principles", "one specifically confirmed SOLID principle"),
    "TYPE_DESIGN": ("122-java-type-design", "domain types, precision, hierarchies, and signature contrast"),
    "CHANGE_AXIS": ("design-patterns", "an existing second implementation or approved variation axis"),
    "JAVA_RUNTIME_RISK": ("java-code-review", "null, exception, concurrency, resource, performance, and API risks"),
    "BEHAVIOR_TEST": ("tdd", "observable behavior, assertions, and boundary substitutes"),
}


def _run_git(repo: Path, args: Sequence[str]) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def _paths(repo: Path, base: str | None, requested: Iterable[str]) -> list[str]:
    if requested:
        return sorted(set(requested))
    if not base:
        raise ValueError("provide --base or at least one --path")
    tracked = _run_git(repo, ["diff", "--name-only", base, "--"]).splitlines()
    untracked = _run_git(repo, ["ls-files", "--others", "--exclude-standard"]).splitlines()
    return sorted(set(tracked + untracked))


def resolve(repo: Path, paths: Sequence[str]) -> dict[str, object]:
    production_java = [path for path in paths if path.endswith(".java") and "/src/test/" not in f"/{path}" and "/test/" not in f"/{path}"]
    test_java = [path for path in paths if path.endswith(".java") and path not in production_java]
    content = "\n".join(
        (repo / path).read_text(encoding="utf-8", errors="replace")
        for path in paths
        if (repo / path).is_file() and path.endswith(".java")
    )
    routes: set[str] = set()
    if production_java:
        routes.update({"JAVA_OOD", "JAVA_RUNTIME_RISK", "BEHAVIOR_TEST"})
    elif test_java:
        routes.add("BEHAVIOR_TEST")
    if re.search(r"\b(?:public\s+interface|implements|extends)\b|\b\w*(?:Gateway|Adapter|Repository|Client|Remote|Controller)\b", content):
        routes.add("MODULE_BOUNDARY")
    if re.search(r"\b(?:record|enum|BigDecimal|Optional|Comparable)\b|\b\w*(?:Value|Id|Code|Type|Status)\b", content):
        routes.add("TYPE_DESIGN")
    if re.search(r"\b(?:Strategy|Factory|Registry|Provider)\b", content):
        routes.add("CHANGE_AXIS")
    if re.search(r"\b(?:null|throw|catch|synchronized|volatile|CompletableFuture|Executor|ThreadLocal|Transactional)\b|\b\w*(?:Gateway|Adapter|Repository|Client|Remote)\b", content):
        routes.add("JAVA_RUNTIME_RISK")
    return {
        "production_java": sorted(production_java),
        "test_java": sorted(test_java),
        "routes": [
            {"id": route, "skill": ROUTES[route][0], "reason": ROUTES[route][1]}
            for route in sorted(routes)
        ],
        "common_quality_principles": "always_apply",
        "unmatched_route_behavior": "continue_with_common_principles",
        "coverage_defaults": {
            "incremental_line_percent": DEFAULT_LINE_COVERAGE,
            "incremental_branch_percent": DEFAULT_BRANCH_COVERAGE,
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--base")
    parser.add_argument("--path", action="append", default=[])
    parser.add_argument("--json", action="store_true", help="输出 JSON；默认输出简短路由列表")
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(arguments)
    try:
        payload = resolve(args.repo.resolve(), _paths(args.repo.resolve(), args.base, args.path))
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            routes = payload["routes"]
            print("质量路由：" + ("、".join(item["id"] for item in routes) if routes else "无专项路由；使用通用质量原则"))
        return 0
    except (OSError, RuntimeError, ValueError) as error:
        print(f"质量路由无法解析：{error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
