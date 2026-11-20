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


@dataclass(frozen=True)
class _JavaToken:
    value: str
    start: int
    end: int


@dataclass(frozen=True)
class _ControlFlowScan:
    path: str
    source: str
    changed_lines: set[int] | None
    tokens: Sequence[_JavaToken]
    block_pairs: dict[int, int]


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
_JAVA_TOKEN = re.compile(
    r"[A-Za-z_$][\w$]*|(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?[fFdDlL]?|"
    r"->|==|!=|<=|>=|&&|\|\||\+\+|--|[{}()\[\];,:.]|\S"
)
_CONTROL_FLOW_PREFIXES = {
    "if",
    "else",
    "for",
    "while",
    "do",
    "switch",
    "catch",
    "finally",
    "try",
    "synchronized",
}
_TERMINATORS = {"return", "throw", "break", "continue"}


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


def _java_tokens(masked: str) -> list[_JavaToken]:
    """Tokenize enough Java syntax for block/control-flow checks.

    This is intentionally not a Java parser. Strings and comments have already
    been blanked, so the token stream can safely be used for delimiter matching
    without treating braces or keywords in prose as code.
    """
    return [_JavaToken(match.group(0), match.start(), match.end()) for match in _JAVA_TOKEN.finditer(masked)]


def _matching_token(tokens: Sequence[_JavaToken], opening: int, opening_value: str, closing_value: str) -> int | None:
    depth = 0
    for index in range(opening, len(tokens)):
        token_value = tokens[index].value
        if token_value == opening_value:
            depth += 1
        elif token_value == closing_value:
            depth -= 1
            if depth == 0:
                return index
    return None


def _block_pairs(tokens: Sequence[_JavaToken]) -> dict[int, int]:
    stack: list[int] = []
    pairs: dict[int, int] = {}
    for index, token in enumerate(tokens):
        if token.value == "{":
            stack.append(index)
        elif token.value == "}" and stack:
            pairs[stack.pop()] = index
    return pairs


def _method_bodies(tokens: Sequence[_JavaToken], pairs: dict[int, int]) -> Iterable[tuple[int, int]]:
    """Yield ``{``/``}`` token pairs belonging to void method declarations."""
    for index, token in enumerate(tokens):
        if token.value != "void" or index + 2 >= len(tokens):
            continue
        if not re.fullmatch(r"[A-Za-z_$][\w$]*", tokens[index + 1].value):
            continue
        if tokens[index + 2].value != "(":
            continue
        closing_parenthesis = _matching_token(tokens, index + 2, "(", ")")
        if closing_parenthesis is None:
            continue
        body_opening = closing_parenthesis + 1
        while body_opening < len(tokens) and tokens[body_opening].value not in {"{", ";", "->"}:
            body_opening += 1
        if body_opening >= len(tokens) or tokens[body_opening].value != "{":
            continue
        body_closing = pairs.get(body_opening)
        if body_closing is not None:
            yield body_opening, body_closing


def _direct_token_indexes(
    tokens: Sequence[_JavaToken],
    pairs: dict[int, int],
    opening: int,
    closing: int,
) -> list[int]:
    """Keep one block's tokens while collapsing nested blocks and expressions."""
    indexes: list[int] = []
    cursor = opening + 1
    while cursor < closing:
        indexes.append(cursor)
        token_value = tokens[cursor].value
        if token_value == "{" and (nested_closing := pairs.get(cursor)) is not None:
            indexes.append(nested_closing)
            cursor = nested_closing + 1
            continue
        if token_value in {"(", "["}:
            closing_value = ")" if token_value == "(" else "]"
            expression_closing = _matching_token(tokens, cursor, token_value, closing_value)
            if expression_closing is not None:
                cursor = expression_closing + 1
                continue
        cursor += 1
    return indexes


def _statement_semicolon(tokens: Sequence[_JavaToken], direct: Sequence[int], position: int) -> int | None:
    for cursor in range(position + 1, len(direct)):
        if tokens[direct[cursor]].value == ";":
            return cursor
    return None


def _is_unconditional_terminator(tokens: Sequence[_JavaToken], direct: Sequence[int], position: int) -> bool:
    """Exclude terminators which are the body of a conditional statement."""
    for cursor in range(position - 1, -1, -1):
        value = tokens[direct[cursor]].value
        if value in {";", "{", "}"}:
            break
        if value in _CONTROL_FLOW_PREFIXES:
            return False
    return True


def _next_statement(direct: Sequence[int], tokens: Sequence[_JavaToken], semicolon: int) -> int | None:
    cursor = semicolon + 1
    if cursor >= len(direct):
        return None
    if tokens[direct[cursor]].value in {"}", "else", "catch", "finally", "case", "default"}:
        return None
    return cursor


def _statement_end(tokens: Sequence[_JavaToken], direct: Sequence[int], position: int) -> int:
    for cursor in range(position, len(direct)):
        if tokens[direct[cursor]].value in {";", "}"}:
            return tokens[direct[cursor]].end
    return tokens[direct[position]].end


def _unreachable_findings(scan: _ControlFlowScan) -> list[Finding]:
    findings: list[Finding] = []
    for opening, closing in scan.block_pairs.items():
        direct = _direct_token_indexes(scan.tokens, scan.block_pairs, opening, closing)
        for position, token_index in enumerate(direct):
            token = scan.tokens[token_index]
            if token.value not in _TERMINATORS or not _is_unconditional_terminator(scan.tokens, direct, position):
                continue
            semicolon = _statement_semicolon(scan.tokens, direct, position)
            if semicolon is None:
                continue
            next_position = _next_statement(direct, scan.tokens, semicolon)
            if next_position is None:
                continue
            next_token = scan.tokens[direct[next_position]]
            statement_end = _statement_end(scan.tokens, direct, next_position)
            if _span_changed(scan.source, token.start, statement_end, scan.changed_lines):
                findings.append(_finding("UNREACHABLE_STATEMENT", scan.path, scan.source, next_token.start))
    return findings


def _void_tail_return_findings(scan: _ControlFlowScan) -> list[Finding]:
    findings: list[Finding] = []
    for body_opening, body_closing in _method_bodies(scan.tokens, scan.block_pairs):
        direct = _direct_token_indexes(scan.tokens, scan.block_pairs, body_opening, body_closing)
        for position, token_index in enumerate(direct):
            if scan.tokens[token_index].value != "return":
                continue
            if not _is_unconditional_terminator(scan.tokens, direct, position):
                continue
            semicolon = _statement_semicolon(scan.tokens, direct, position)
            if semicolon != position + 1 or semicolon != len(direct) - 1:
                continue
            return_position = scan.tokens[token_index].start
            return_end = scan.tokens[direct[semicolon]].end
            if _span_changed(scan.source, return_position, return_end, scan.changed_lines):
                findings.append(_finding("VOID_TAIL_RETURN", scan.path, scan.source, return_position))
    return findings


def _empty_catch_findings(scan: _ControlFlowScan) -> list[Finding]:
    findings: list[Finding] = []
    for index, token in enumerate(scan.tokens):
        if token.value != "catch" or index + 1 >= len(scan.tokens) or scan.tokens[index + 1].value != "(":
            continue
        closing_parenthesis = _matching_token(scan.tokens, index + 1, "(", ")")
        if closing_parenthesis is None or closing_parenthesis + 1 >= len(scan.tokens):
            continue
        body_opening = closing_parenthesis + 1
        if scan.tokens[body_opening].value != "{":
            continue
        body_closing = scan.block_pairs.get(body_opening)
        if body_closing is None:
            continue
        body_values = {scan.tokens[cursor].value for cursor in range(body_opening + 1, body_closing)}
        if body_values - {"{", "}", ";"}:
            continue
        if _span_changed(scan.source, token.start, scan.tokens[body_closing].end, scan.changed_lines):
            findings.append(_finding("EMPTY_CATCH", scan.path, scan.source, token.start))
    return findings


def _control_flow_findings(
    path: str,
    source: str,
    masked: str,
    changed_lines: set[int] | None,
) -> list[Finding]:
    tokens = _java_tokens(masked)
    scan = _ControlFlowScan(path, source, changed_lines, tokens, _block_pairs(tokens))
    return [
        *_unreachable_findings(scan),
        *_void_tail_return_findings(scan),
        *_empty_catch_findings(scan),
    ]


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
    findings.extend(_control_flow_findings(path, source, masked, changed_lines))
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
