#!/usr/bin/env python3
"""Run a stateless mechanical quality scan over changed Java files.

The command deliberately emits findings only. It does not create execution state
or modify the project. Review-level findings are reported for the independent
reviewer; error-level findings make the gate fail.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Sequence

try:
    from quality_registry import ERROR, REVIEW, RULE_BY_CODE, registry_errors
except ImportError:  # pragma: no cover - supports package execution
    from .quality_registry import ERROR, REVIEW, RULE_BY_CODE, registry_errors


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    path: str
    line: int
    message: str


STRING_OR_COMMENT = re.compile(
    r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*.*?\*/',
    re.DOTALL,
)


def _mask(match: re.Match[str]) -> str:
    return "".join("\n" if char == "\n" else " " for char in match.group(0))


def _mask_non_code(source: str) -> str:
    return STRING_OR_COMMENT.sub(_mask, source)


def _line_number(source: str, position: int) -> int:
    return source.count("\n", 0, position) + 1


def _finding(code: str, path: str, source: str, position: int, detail: str | None = None) -> Finding:
    rule = RULE_BY_CODE[code]
    return Finding(code, rule.severity, path, _line_number(source, position), detail or rule.description)


def _is_test_file(path: str) -> bool:
    normalized = "/" + path.replace("\\", "/").lower().strip("/") + "/"
    return "/src/test/" in normalized or "/test/" in normalized


def _matches(
    code: str,
    pattern: re.Pattern[str],
    path: str,
    source: str,
    masked: str,
    changed_lines: set[int] | None,
    detail: str | None = None,
) -> list[Finding]:
    findings: list[Finding] = []
    for match in pattern.finditer(masked):
        line = _line_number(source, match.start())
        if changed_lines is None or line in changed_lines:
            findings.append(_finding(code, path, source, match.start(), detail))
    return findings


def scan_java_source(path: str, source: str, changed_lines: set[int] | None = None) -> list[Finding]:
    masked = _mask_non_code(source)
    findings: list[Finding] = []
    findings.extend(_matches(
        "EMPTY-CATCH", re.compile(r"catch\s*\([^)]*\)\s*\{\s*\}"), path, source, masked, changed_lines,
        "catch block must not silently discard a failure",
    ))
    broad_catch = re.compile(
        r"catch\s*\(\s*(?:Exception|RuntimeException|Throwable)\b[^)]*\)\s*\{(?P<body>.*?)\}", re.DOTALL
    )
    for match in broad_catch.finditer(masked):
        if re.search(r"\breturn\s+(?:null|Optional\.empty\(\)|Collections\.empty\w*\(\)|false)\s*;", match.group("body")):
            if changed_lines is None or _line_number(source, match.start()) in changed_lines:
                findings.append(_finding(
                    "BROAD-CATCH-FALLBACK", path, source, match.start(),
                    "catch a specific recoverable exception or propagate the original failure",
                ))
    findings.extend(_matches(
        "FIELD-INJECTION",
        re.compile(
            r"@(?:Autowired|Resource|Inject)\b[^\n]*(?:\n\s*@[A-Za-z_$][\w$]*(?:\([^\n]*\))?)*\n"
            r"\s*(?:(?:public|protected|private|static|final)\s+)*[A-Za-z_$][\w$]*(?:\s*<[^;{}\n]+>)?(?:\s*\[\])?\s+[A-Za-z_$][\w$]*\s*;"
        ), path, source, masked, changed_lines, "inject production dependencies through a constructor",
    ))
    findings.extend(_matches(
        "CONTROL-FLOW-SKIP", re.compile(r"\bcontinue\s*;"), path, source, masked, changed_lines,
        "replace continue with an explicit, readable control flow",
    ))
    findings.extend(_matches(
        "NULL-RETURN", re.compile(r"\breturn\s+null\s*;"), path, source, masked, changed_lines,
    ))
    findings.extend(_matches(
        "GENERIC-NORMALIZATION-HELPER",
        re.compile(r"\b(?:normalizeText|normalizeString|cleanText|trimText|trimToNull)\s*\("),
        path, source, masked, changed_lines, "give normalization a domain or protocol boundary name",
    ))
    if re.search(r"\b(?:log|logger)\.(?:trace|debug|info|warn|error)\s*\(", masked):
        for match in re.finditer(r"System\.(?:currentTimeMillis|nanoTime)\s*\(", masked):
            if changed_lines is None or _line_number(source, match.start()) in changed_lines:
                findings.append(_finding(
                    "MANUAL-DURATION-LOGGING", path, source, match.start(),
                    "use the repository tracing or metrics abstraction for elapsed-time logging",
                ))
    findings.extend(_matches(
        "WILDCARD-IMPORT", re.compile(r"^\s*import\s+(?:static\s+)?[\w$.]+\.\*\s*;", re.MULTILINE),
        path, source, masked, changed_lines,
    ))
    findings.extend(_matches(
        "OPTIONAL-GET", re.compile(r"\b(?:isPresent|isEmpty)\s*\(\s*\).*?\bget\s*\(\s*\)", re.DOTALL),
        path, source, masked, changed_lines,
    ))
    findings.extend(_matches(
        "BOOLEAN-FLAG",
        re.compile(r"\b(?:public|protected|private)?\s*(?:static\s+)?[\w<>?,.\[\]]+\s+\w+\s*\([^)]*\bboolean\s+\w+\b[^)]*\)\s*\{"),
        path, source, masked, changed_lines,
    ))
    findings.extend(_matches(
        "GENERIC-RESULT-SHAPE", re.compile(r"\b(?:success|code|message|data)\b\s*[:=]"),
        path, source, masked, changed_lines,
    ))
    for match in re.finditer(r"\?[^:\n]+:[^;\n]+", masked):
        if (changed_lines is None or _line_number(source, match.start()) in changed_lines) and match.group(0).count("?") > 1:
            findings.append(_finding("COMPLEX-TERNARY", path, source, match.start()))
    if _is_test_file(path):
        findings.extend(_matches(
            "DISABLED-TEST", re.compile(r"@(Disabled|Ignore|EnabledIf|DisabledIf|EnableIf)\b"),
            path, source, masked, changed_lines, "do not add or expand disabled/conditional test scope",
        ))
    return findings


def _run_git(repo: Path, args: Sequence[str]) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def _changed_lines(repo: Path, base: str) -> dict[str, set[int]]:
    diff = _run_git(repo, ["diff", "--no-ext-diff", "--unified=0", base, "--"])
    hunk = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
    result: dict[str, set[int]] = {}
    path: str | None = None
    line_number = 0
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:]
            continue
        match = hunk.match(line)
        if match:
            line_number = int(match.group(1))
            continue
        if not path or not line_number or line.startswith("\\"):
            continue
        if line.startswith("+"):
            if path.endswith(".java"):
                result.setdefault(path, set()).add(line_number)
            line_number += 1
        elif not line.startswith("-"):
            line_number += 1
    for untracked in _run_git(repo, ["ls-files", "--others", "--exclude-standard"]).splitlines():
        if untracked.endswith(".java") and (repo / untracked).is_file():
            lines = len((repo / untracked).read_text(encoding="utf-8").splitlines())
            result[untracked] = set(range(1, lines + 1))
    return result


def _safe_path(repo: Path, raw: str) -> str:
    requested_path = Path(raw)
    resolved = requested_path.resolve() if requested_path.is_absolute() else (repo / requested_path).resolve()
    try:
        relative = resolved.relative_to(repo.resolve())
    except ValueError as error:
        raise ValueError(f"path is outside repository: {raw}") from error
    if ".." in PurePosixPath(relative.as_posix()).parts:
        raise ValueError(f"invalid repository path: {raw}")
    return relative.as_posix()


def _paths(repo: Path, base: str | None, requested: Iterable[str]) -> dict[str, set[int] | None]:
    if requested:
        return {path: None for path in sorted({_safe_path(repo, raw) for raw in requested}) if path.endswith(".java")}
    if not base:
        raise ValueError("provide --base or at least one --path")
    return _changed_lines(repo, base)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."), help="目标仓库根目录")
    parser.add_argument("--base", help="Git diff 的基线；未提供时必须显式传入 --path")
    parser.add_argument("--path", action="append", default=[], help="要扫描的仓库相对 Java 文件；可重复")
    parser.add_argument("--source", action="append", type=Path, default=[], help="要扫描的任意 Java 源文件；可重复，适合 Plan 临时文件")
    parser.add_argument("--json-output", type=Path, help="可选普通扫描结果 JSON 文件")
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(arguments)
    repo = args.repo.resolve()
    try:
        errors = registry_errors()
        if errors:
            raise RuntimeError("quality registry invalid: " + "; ".join(errors))
        paths = _paths(repo, args.base, args.path) if args.base or args.path else {}
        findings: list[Finding] = []
        scanned: list[str] = []
        for path, changed in sorted(paths.items()):
            source_path = repo / path
            if not source_path.is_file() or not path.endswith(".java"):
                continue
            scanned.append(path)
            findings.extend(scan_java_source(path, source_path.read_text(encoding="utf-8"), changed))
        for source_path in args.source:
            resolved = source_path.resolve()
            if not resolved.is_file() or resolved.suffix != ".java":
                raise ValueError(f"source is not a Java file: {source_path}")
            label = str(resolved)
            scanned.append(label)
            findings.extend(scan_java_source(label, resolved.read_text(encoding="utf-8"), None))
        payload = {
            "scanned_files": scanned,
            "findings": [asdict(item) for item in findings],
            "errors": [asdict(item) for item in findings if item.severity == ERROR],
            "review_required": [asdict(item) for item in findings if item.severity == REVIEW],
        }
        if args.json_output:
            output = args.json_output if args.json_output.is_absolute() else repo / args.json_output
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for finding in findings:
            print(f"{finding.severity}: {finding.code} {finding.path}:{finding.line} - {finding.message}")
        if payload["errors"]:
            print(f"Quality Gate: failed ({len(payload['errors'])} error(s))", file=sys.stderr)
            return 1
        print(f"Quality Gate: passed ({len(scanned)} Java file(s), {len(payload['review_required'])} review finding(s))")
        return 0
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Quality Gate: unable to run: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
