#!/usr/bin/env python3
"""Select quality routes from concrete Java repository facts.

The resolver is intentionally stateless: it prints the route decision and does not
write execution state or modify the project. With --base, only requested files and
their added or modified lines participate in route matching.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Iterable, Sequence

try:
    from quality_registry import DEFAULT_BRANCH_COVERAGE, DEFAULT_LINE_COVERAGE
except ImportError:  # pragma: no cover
    from .quality_registry import DEFAULT_BRANCH_COVERAGE, DEFAULT_LINE_COVERAGE


ROUTES = {
    "MODULE_BOUNDARY": ("codebase-design", "interface, seam, depth, locality, and module ownership"),
    "TYPE_DESIGN": ("122-java-type-design", "domain types, precision, hierarchies, and signature contrast"),
    "JAVA_RUNTIME_RISK": (
        "java-code-review",
        "Java/Spring concurrency, transaction, resource, reactive, and external API risks",
    ),
    "BEHAVIOR_TEST": ("tdd", "observable behavior, assertions, and boundary substitutes"),
}
MODULE_BOUNDARY_RISK = re.compile(
    r"\bpublic\s+interface\b|"
    r"\b[A-Z][A-Za-z0-9_$]*(?:Gateway|Adapter|Repository|Client|Remote|Controller)\b"
)
TYPE_DESIGN_RISK = re.compile(
    r"\b(?:record|enum|BigDecimal|Optional|Comparable)\b|"
    r"\b[A-Z][A-Za-z0-9_$]*(?:Value|Id|Code|Type|Status)\b"
)
JAVA_RUNTIME_RISK = re.compile(
    r"\b(?:synchronized|volatile|CompletableFuture|Executor(?:Service)?|ThreadLocal|"
    r"InputStream|OutputStream|Reader|Writer|Connection|ResultSet)\b|"
    r"@(?:Transactional|Async)\b|\b(?:Mono|Flux)\s*<|"
    r"\b[A-Z][A-Za-z0-9_$]*(?:Gateway|Adapter|Repository|Client|Remote)\b"
)
BEHAVIOR_TEST_RISK = re.compile(
    r"\b(?:MockMvc|WebTestClient|WireMock|Testcontainers|Mockito|Awaitility)\b|"
    r"@(?:MockBean|SpyBean)\b|\bassertThrows\s*\("
)


def _run_git(repo: Path, args: Sequence[str]) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def _safe_path(repo: Path, raw: str) -> str:
    requested = Path(raw)
    resolved = requested.resolve() if requested.is_absolute() else (repo / requested).resolve()
    try:
        relative = resolved.relative_to(repo.resolve())
    except ValueError as error:
        raise ValueError(f"path is outside repository: {raw}") from error
    if ".." in PurePosixPath(relative.as_posix()).parts:
        raise ValueError(f"invalid repository path: {raw}")
    return relative.as_posix()


def _paths(repo: Path, base: str | None, requested: Iterable[str]) -> list[str]:
    if requested:
        paths = sorted({_safe_path(repo, path) for path in requested})
        if not base:
            return paths
        tracked = _run_git(
            repo, ["diff", "--name-only", base, "--", *paths]
        ).splitlines()
        untracked = _run_git(
            repo, ["ls-files", "--others", "--exclude-standard", "--", *paths]
        ).splitlines()
        return sorted(set(tracked + untracked))
    if not base:
        raise ValueError("provide --base or at least one --path")
    tracked = _run_git(repo, ["diff", "--name-only", base, "--"]).splitlines()
    untracked = _run_git(repo, ["ls-files", "--others", "--exclude-standard"]).splitlines()
    return sorted(set(tracked + untracked))


def _route_source(repo: Path, paths: Sequence[str], base: str | None) -> str:
    if not paths:
        return ""
    if not base:
        return "\n".join(
            (repo / path).read_text(encoding="utf-8", errors="replace")
            for path in paths
            if (repo / path).is_file()
        )

    diff = _run_git(repo, ["diff", "--no-ext-diff", "--unified=0", base, "--", *paths])
    added_lines = [
        line[1:]
        for line in diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    untracked = set(
        _run_git(
            repo, ["ls-files", "--others", "--exclude-standard", "--", *paths]
        ).splitlines()
    )
    for path in paths:
        if path in untracked and (repo / path).is_file():
            added_lines.append((repo / path).read_text(encoding="utf-8", errors="replace"))
    return "\n".join(added_lines)


def _matched_routes(production_content: str, test_content: str) -> set[str]:
    checks = (
        ("MODULE_BOUNDARY", MODULE_BOUNDARY_RISK),
        ("TYPE_DESIGN", TYPE_DESIGN_RISK),
        ("JAVA_RUNTIME_RISK", JAVA_RUNTIME_RISK),
    )
    routes = {route for route, pattern in checks if pattern.search(production_content)}
    if BEHAVIOR_TEST_RISK.search(test_content):
        routes.add("BEHAVIOR_TEST")
    return routes


def resolve(repo: Path, paths: Sequence[str], base: str | None = None) -> dict[str, object]:
    production_java = [
        path
        for path in paths
        if path.endswith(".java")
        and "/src/test/" not in f"/{path}"
        and "/test/" not in f"/{path}"
    ]
    test_java = [path for path in paths if path.endswith(".java") and path not in production_java]
    production_content = "\n".join([*production_java, _route_source(repo, production_java, base)])
    test_content = "\n".join([*test_java, _route_source(repo, test_java, base)])
    routes = _matched_routes(production_content, test_content)
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
    parser.add_argument("--repo", type=Path, default=Path("."), help="目标 Git 仓库根目录")
    parser.add_argument("--base", help="Git 基线；提供后只匹配相对该基线的 Java 增量")
    parser.add_argument(
        "--path",
        action="append",
        default=[],
        help="本次实际影响的 Java 文件；可重复，配合 --base 时忽略未变化文件",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON；默认输出简短路由列表")
    parser.add_argument("--json-output", type=Path, help="可选 JSON 结果文件，供最终执行门禁读取")
    return parser


def _write_json_output(payload: dict[str, object], output_path: Path | None, repo: Path) -> None:
    if output_path is None:
        return
    output = output_path if output_path.is_absolute() else repo / output_path
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _print_payload(payload: dict[str, object], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    routes = payload["routes"]
    labels = "、".join(item["id"] for item in routes) if routes else "无专项路由；使用 clean-code-guard 与执行质量补充"
    print("质量路由：" + labels)


def main(arguments: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(arguments)
    try:
        repo = args.repo.resolve()
        payload = resolve(repo, _paths(repo, args.base, args.path), args.base)
        _write_json_output(payload, args.json_output, repo)
        _print_payload(payload, args.json)
        return 0
    except (OSError, RuntimeError, ValueError) as error:
        print(f"质量路由无法解析：{error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
