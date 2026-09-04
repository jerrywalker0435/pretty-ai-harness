#!/usr/bin/env python3
"""Run a stateless mechanical quality scan over changed Java files.

The command deliberately emits findings only. It does not create execution state
or modify the project. Every finding is a deterministic gate error.
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
    from quality_registry import ERROR, RULE_BY_CODE, registry_errors
except ImportError:  # pragma: no cover - supports package execution
    from .quality_registry import ERROR, RULE_BY_CODE, registry_errors


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    path: str
    line: int
    message: str


STRING_OR_COMMENT = re.compile(
    r'"""(?:\\.|(?!""").)*"""|'
    r'"(?:\\.|[^"\\\n])*"|'
    r"'(?:\\.|[^'\\\n])*'|"
    r"//[^\n]*|/\*.*?\*/",
    re.DOTALL,
)
_LOG_CALL = re.compile(r"\b(?:log|logger)\s*\.\s*(?:trace|debug|info|warn|error)\s*\(", re.IGNORECASE)
_HEADER_ACCESS = re.compile(r"\b(?:getHeader|header|getFirst|get)\s*\(", re.IGNORECASE)
_SENSITIVE_HEADER_ARGUMENT = re.compile(
    r"\s*(?:"
    r'"(?:Authorization|Cookie|Set-Cookie)"|'
    r"(?:HttpHeaders\s*\.\s*)?(?:AUTHORIZATION|COOKIE|SET_COOKIE)"
    r")\s*",
    re.IGNORECASE,
)
_JAVA_IDENTIFIER = re.compile(r"\b[A-Za-z_$][\w$]*\b")
_SENSITIVE_LOG_TERMS = ("password", "secret", "accesstoken", "refreshtoken")
_REDACTED_LOG_PREFIXES = ("mask", "redact", "getmask", "getredact", "ismask", "isredact")


def _mask(match: re.Match[str]) -> str:
    return "".join("\n" if char == "\n" else " " for char in match.group(0))


def _mask_non_code(source: str) -> str:
    return STRING_OR_COMMENT.sub(_mask, source)


def _mask_comments(source: str) -> str:
    return STRING_OR_COMMENT.sub(
        lambda match: _mask(match) if match.group(0).startswith(("//", "/*")) else match.group(0),
        source,
    )


def _line_number(source: str, position: int) -> int:
    return source.count("\n", 0, position) + 1


def _span_changed(source: str, start: int, end: int, changed_lines: set[int] | None) -> bool:
    if changed_lines is None:
        return True
    first_line = _line_number(source, start)
    last_line = _line_number(source, max(start, end - 1))
    return any(first_line <= line <= last_line for line in changed_lines)


def _finding(code: str, path: str, source: str, position: int) -> Finding:
    rule = RULE_BY_CODE[code]
    return Finding(code, ERROR, path, _line_number(source, position), rule.description)


def _matches(
    code: str,
    pattern: re.Pattern[str],
    path: str,
    source: str,
    masked: str,
    changed_lines: set[int] | None,
) -> list[Finding]:
    findings: list[Finding] = []
    for match in pattern.finditer(masked):
        if _span_changed(source, match.start(), match.end(), changed_lines):
            findings.append(_finding(code, path, source, match.start()))
    return findings


def _matching_delimiter(masked: str, opening: int, opening_char: str, closing_char: str) -> int | None:
    depth = 0
    for position in range(opening, len(masked)):
        char = masked[position]
        if char == opening_char:
            depth += 1
        elif char == closing_char:
            depth -= 1
            if depth == 0:
                return position
    return None


def _changed_position(source: str, position: int, changed_lines: set[int] | None) -> bool:
    return changed_lines is None or _line_number(source, position) in changed_lines


def _log_call_spans(masked: str) -> Iterable[tuple[int, int]]:
    for match in _LOG_CALL.finditer(masked):
        opening = masked.find("(", match.start(), match.end())
        closing = _matching_delimiter(masked, opening, "(", ")")
        if opening >= 0 and closing is not None:
            yield match.start(), closing + 1


def _sensitive_identifier_position(masked_log_call: str) -> int | None:
    for identifier in _JAVA_IDENTIFIER.finditer(masked_log_call):
        normalized = identifier.group(0).replace("_", "").lower()
        if normalized.startswith(_REDACTED_LOG_PREFIXES):
            continue
        if any(term in normalized for term in _SENSITIVE_LOG_TERMS):
            return identifier.start()
    return None


def _sensitive_header_position(masked_log_call: str, visible_log_call: str) -> int | None:
    for access in _HEADER_ACCESS.finditer(masked_log_call):
        opening = masked_log_call.find("(", access.start(), access.end())
        closing = _matching_delimiter(masked_log_call, opening, "(", ")")
        if closing is None:
            continue
        argument = visible_log_call[opening + 1:closing]
        if _SENSITIVE_HEADER_ARGUMENT.fullmatch(argument):
            return access.start()
    return None


def _unsafe_log_positions(masked_log_call: str, visible_log_call: str) -> list[tuple[str, int]]:
    rule_positions: list[tuple[str, int]] = []
    serialized = re.search(r"\bwriteValueAsString\s*\(", masked_log_call)
    if serialized:
        rule_positions.append(("WHOLE-OBJECT-LOGGING", serialized.start()))

    sensitive_header = _sensitive_header_position(masked_log_call, visible_log_call)
    sensitive_identifier = _sensitive_identifier_position(masked_log_call)
    if sensitive_header is not None:
        rule_positions.append(("SENSITIVE-LOGGING", sensitive_header))
    elif sensitive_identifier is not None:
        rule_positions.append(("SENSITIVE-LOGGING", sensitive_identifier))
    return rule_positions


def _log_findings(
    path: str,
    source: str,
    masked: str,
    changed_lines: set[int] | None,
) -> list[Finding]:
    comments_masked = _mask_comments(source)
    findings: list[Finding] = []
    for start, end in _log_call_spans(masked):
        masked_call = masked[start:end]
        visible_call = comments_masked[start:end]
        for code, relative_position in _unsafe_log_positions(masked_call, visible_call):
            position = start + relative_position
            if _changed_position(source, position, changed_lines):
                findings.append(_finding(code, path, source, position))
    return findings


def scan_java_source(path: str, source: str, changed_lines: set[int] | None = None) -> list[Finding]:
    masked = _mask_non_code(source)
    findings: list[Finding] = []
    findings.extend(_matches(
        "LABELED-CONTINUE", re.compile(r"\bcontinue\s+[A-Za-z_$][\w$]*\s*;"),
        path, source, masked, changed_lines,
    ))
    if _LOG_CALL.search(masked):
        findings.extend(_log_findings(path, source, masked, changed_lines))
        for match in re.finditer(r"System\.(?:currentTimeMillis|nanoTime)\s*\(", masked):
            if changed_lines is None or _line_number(source, match.start()) in changed_lines:
                findings.append(_finding("MANUAL-DURATION-LOGGING", path, source, match.start()))
    return findings


def _run_git(repo: Path, args: Sequence[str]) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def _changed_lines(repo: Path, base: str, requested: Sequence[str] = ()) -> dict[str, set[int]]:
    diff = _run_git(repo, ["diff", "--no-ext-diff", "--unified=0", base, "--", *requested])
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
    for untracked in _run_git(
        repo,
        ["ls-files", "--others", "--exclude-standard", "--", *requested],
    ).splitlines():
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
        paths = sorted({_safe_path(repo, raw) for raw in requested})
        if not base:
            return {path: None for path in paths if path.endswith(".java")}
        changed = _changed_lines(repo, base, paths)
        return {path: changed.get(path, set()) for path in paths if path.endswith(".java")}
    if not base:
        raise ValueError("provide --base or at least one --path")
    return _changed_lines(repo, base)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."), help="目标仓库根目录")
    parser.add_argument("--base", help="Git diff 的基线；与 --path 同用时只扫描指定文件的增量")
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
        print(f"Quality Gate: passed ({len(scanned)} Java file(s))")
        return 0
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Quality Gate: unable to run: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
