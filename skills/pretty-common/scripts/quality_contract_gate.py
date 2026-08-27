#!/usr/bin/env python3
"""Run a diagnostic Java scan with the shared Pretty quality rule registry.

Formal Apply evidence is produced only by ``verify_quality_contract.py``.  This
module remains the reusable scanner and reviewer-finding validator; its CLI is
intentionally source-scoped diagnostics and never emits formal evidence.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from itertools import chain
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from disabled_test_scope import annotation_findings
from evidence_binding import bytes_sha256, candidate_sha256

from quality_registry import (  # type: ignore[import-not-found]
    ERROR,
    REVIEW,
    RULES,
    RULE_BY_CODE,
    RISK_OWNERS,
)
from pretty_tmp import validate_artifact_path, validate_run_dir


@dataclass(frozen=True)
class QualityFinding:
    code: str
    message: str
    line: int
    source: str
    symbol: str

    @property
    def severity(self) -> str:
        return RULE_BY_CODE[self.code].severity

    @property
    def fingerprint(self) -> str:
        payload = f"{self.code}|{self.source}|{self.symbol}|{self.line}|{self.message}"
        return bytes_sha256(payload.encode("utf-8"))

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["severity"] = self.severity
        payload["fingerprint"] = self.fingerprint
        return payload


@dataclass(frozen=True)
class MethodSpan:
    name: str
    owner: str
    symbol: str
    start: int
    body_start: int
    end: int
    parameters: str
    nullable: bool


@dataclass(frozen=True)
class JavaScanContext:
    source: str
    masked_source: str
    source_name: str
    methods: tuple[MethodSpan, ...]
    eligible_lines: frozenset[int] | None


JAVA_TOKEN = re.compile(
    r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*.*?\*/',
    re.DOTALL,
)
COMMENT_TOKEN = re.compile(r"//[^\n]*|/\*.*?\*/", re.DOTALL)
ANNOTATION = r"@(?:[A-Za-z_$][\w$]*\.)*[A-Za-z_$][\w$]*(?:\([^\n)]*\))?"
METHOD_PATTERN = re.compile(
    rf"(?m)^[ \t]*(?P<prefix>(?:(?:{ANNOTATION}|public|protected|private|static|"
    rf"final|synchronized|native|abstract|default)\s+)*)"
    r"(?:<[^>\n]+>\s+)?"
    r"(?P<return>[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*"
    r"(?:\s*<[^{}\n]+>)?(?:\s*\[\])?)\s+"
    r"(?P<name>[A-Za-z_$][\w$]*)\s*\((?P<parameters>[^;{}]*)\)\s*"
    r"(?:throws[^\n{]+)?\{"
)
CONSTRUCTOR_PATTERN = re.compile(
    rf"(?m)^[ \t]*(?P<prefix>(?:(?:{ANNOTATION}|public|protected|private)\s+)*)"
    r"(?P<name>[A-Z][A-Za-z0-9_$]*)\s*\((?P<parameters>[^;{}]*)\)\s*"
    r"(?:throws[^\n{]+)?\{"
)
CLASS_PATTERN = re.compile(r"\b(?:class|interface|enum|record)\s+([A-Za-z_$][\w$]*)[^;{]*\{")
WILDCARD_IMPORT = re.compile(r"(?m)^\s*import\s+(?:static\s+)?[\w$.]+\.\*\s*;")
FIELD_INJECTION = re.compile(
    r"(?m)^\s*@(Autowired|Resource|Inject)\b[^\n]*\n"
    r"(?:\s*@[^\n]+\n)*\s*(?:(?:public|protected|private|static|final)\s+)*"
    r"[A-Za-z_$][\w$]*(?:\s*<[^;{}\n]+>)?(?:\s*\[\])?\s+[A-Za-z_$][\w$]*\s*;"
)
EMPTY_CATCH = re.compile(r"catch\s*\([^)]*\)\s*\{\s*\}", re.DOTALL)
BROAD_CATCH = re.compile(
    r"catch\s*\(\s*(?:Exception|RuntimeException|Throwable)\b[^)]*\)\s*\{"
)
FALLBACK_RETURN = re.compile(
    r"\breturn\s+(?:null|true|false|0|1|"
    r"Collections\.empty(?:List|Set|Map)\s*\(\)|(?:List|Set|Map)\.of\s*\(\))\s*;"
)
LOGGER_CALL = re.compile(
    r"\b(?:log|logger|LOG|LOGGER|[A-Za-z_$][\w$]*(?:Logger|Log))"
    r"\s*\.\s*(?:trace|debug|info|warn|error|fatal)\s*\("
)
MANUAL_DURATION_TIMER = re.compile(
    r"\b(?:final\s+)?(?:long|Long|var)\s+"
    r"(?P<variable>(?:start|started|begin)(?:Time)?(?:At|Timestamp|Millis|Nanos)?)\s*=\s*"
    r"System\s*\.\s*(?:currentTimeMillis|nanoTime)\s*\(",
    re.IGNORECASE,
)
REQUIRED_INPUT_EMPTY_FALLBACK = re.compile(
    r"if\s*\([^)]*(?:==\s*null|\.isBlank\s*\(|\.isEmpty\s*\()[^)]*\)"
    r"\s*\{?\s*return\s+(?:Collections\.(?:emptyList|emptySet|emptyMap)|Optional\.empty)\s*\(",
    re.DOTALL,
)
BOUNDARY_ANY = re.compile(
    r"(?:when|verify)\s*\([^;\n]*(?:gateway|repository|client|adapter)\.[^;\n]*\bany\w*\s*\(",
    re.IGNORECASE,
)
CAPTOR_USAGE = re.compile(r"\b(?:ArgumentCaptor|Captor|capture)\b")
CONTRACT_CODE = re.compile(r"\b[A-Z][A-Z0-9]+(?:_[A-Z0-9]+)+\b")
ASSERTION = re.compile(r"\b(?:assert\w*|then|expect)\s*\([^;]*", re.IGNORECASE)
GENERIC_RESULT = re.compile(
    r"\b(?:class|record)\s+[A-Za-z_$][\w$]*(?:Result|Response)\b"
    r"(?:(?!\b(?:class|record)\b).){0,1500}\b(?:success|ok)\b"
    r"(?:(?!\b(?:class|record)\b).){0,1500}\b(?:code|status)\b"
    r"(?:(?!\b(?:class|record)\b).){0,1500}\b(?:message|error)\b"
    r"(?:(?!\b(?:class|record)\b).){0,1500}\b(?:data|payload)\b",
    re.IGNORECASE | re.DOTALL,
)
COMPLEXITY_TOKEN = re.compile(r"\b(?:if|for|while|case|catch)\b|&&|\|\||\?")
NULLABLE = re.compile(r"@(?:[A-Za-z_$][\w$]*\.)*(?:Nullable|CheckForNull)\b")
HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
NORMALIZATION_CALL = re.compile(
    r"\.\s*(?:trim|strip|stripLeading|stripTrailing|toLowerCase|toUpperCase)\s*\("
)
METHOD_INVOCATION = re.compile(
    r"(?:(?P<owner>[A-Za-z_$][\w$]*)\s*\.\s*)?"
    r"(?P<name>[A-Za-z_$][\w$]*)\s*\("
)
METHOD_REFERENCE = re.compile(
    r"(?P<owner>[A-Za-z_$][\w$]*)\s*::\s*"
    r"(?P<name>[A-Za-z_$][\w$]*)\b"
)
JAVA_IDENTIFIER = re.compile(r"\b[A-Za-z_$][A-Za-z0-9_$]*\b")
RELATIVE_BUCKET_TOKENS = frozenset({"normal", "special"})
GENERIC_NORMALIZATION_VERBS = frozenset({
    "canonicalise", "canonicalize", "clean", "normalise", "normalize", "sanitize", "strip", "trim",
})
GENERIC_TEXT_TOKENS = frozenset({
    "blank", "data", "empty", "field", "input", "null", "space", "string", "text", "to", "value", "whitespace",
})
GENERIC_NORMALIZATION_OWNERS = frozenset({
    "canonicalizer", "cleaner", "common", "helper", "input", "normalization", "normalizer",
    "sanitizer", "string", "support", "text", "trimmer", "util", "utils", "value",
})
GENERIC_NULL_FALLBACK_NAMES = frozenset({
    ("blank", "to", "null"),
    ("empty", "to", "null"),
    ("null", "to", "empty"),
})


def _blank_token(match: re.Match[str]) -> str:
    return "".join("\n" if character == "\n" else " " for character in match.group(0))


def mask_java_non_code(source: str) -> str:
    return JAVA_TOKEN.sub(_blank_token, source)


def _matching_brace(masked_source: str, opening: int) -> int:
    depth = 0
    for index in range(opening, len(masked_source)):
        depth += int(masked_source[index] == "{")
        depth -= int(masked_source[index] == "}")
        if depth == 0:
            return index + 1
    return len(masked_source)


def _line_number(source: str, position: int) -> int:
    return source.count("\n", 0, max(position, 0)) + 1


def _top_level_parameters(parameters: str) -> tuple[str, ...]:
    if not parameters.strip():
        return ()
    segments, start, depths = [], 0, [0, 0, 0]
    for index, character in enumerate(parameters):
        if character in "<([{":
            depths[0 if character == "<" else 1 if character == "(" else 2] += 1
        elif character in ">)]}":
            slot = 0 if character == ">" else 1 if character == ")" else 2
            depths[slot] = max(0, depths[slot] - 1)
        elif character == "," and not any(depths):
            segments.append(parameters[start:index].strip())
            start = index + 1
    segments.append(parameters[start:].strip())
    return tuple(segment for segment in segments if segment)


def _class_spans(masked_source: str) -> tuple[tuple[str, int, int], ...]:
    spans = []
    for match in CLASS_PATTERN.finditer(masked_source):
        spans.append((match.group(1), match.start(), _matching_brace(masked_source, match.end() - 1)))
    return tuple(spans)


def _class_name(spans: Sequence[tuple[str, int, int]], position: int) -> str:
    owners = [span for span in spans if span[1] <= position < span[2]]
    return max(owners, key=lambda span: span[1])[0] if owners else "<top-level>"


def _method_from_match(
    match: re.Match[str],
    masked_source: str,
    source_name: str,
    class_spans: Sequence[tuple[str, int, int]],
) -> MethodSpan:
    body_start = match.end() - 1
    parameters = match.group("parameters")
    owner = _class_name(class_spans, match.start())
    arity = len(_top_level_parameters(parameters))
    symbol = f"{source_name}#{owner}#{match.group('name')}/{arity}"
    return MethodSpan(
        match.group("name"),
        owner,
        symbol,
        match.start(),
        body_start,
        _matching_brace(masked_source, body_start),
        parameters,
        bool(NULLABLE.search(match.group("prefix") or "")),
    )


def method_spans(masked_source: str, source_name: str) -> tuple[MethodSpan, ...]:
    classes = _class_spans(masked_source)
    matches = list(METHOD_PATTERN.finditer(masked_source))
    matches.extend(CONSTRUCTOR_PATTERN.finditer(masked_source))
    unique = {match.start(): match for match in matches}
    return tuple(
        _method_from_match(unique[start], masked_source, source_name, classes)
        for start in sorted(unique)
    )


def _method_for_position(methods: Sequence[MethodSpan], position: int) -> MethodSpan | None:
    owners = [method for method in methods if method.start <= position < method.end]
    return max(owners, key=lambda method: method.start) if owners else None


def _eligible_lines(
    source: str,
    methods: Sequence[MethodSpan],
    changed_lines: frozenset[int] | None,
) -> frozenset[int] | None:
    if changed_lines is None:
        return None
    eligible = set(changed_lines)
    for method in methods:
        first, last = _line_number(source, method.start), _line_number(source, method.end - 1)
        if any(first <= line <= last for line in changed_lines):
            eligible.update(range(first, last + 1))
    return frozenset(eligible)


def _position_is_eligible(
    source: str,
    position: int,
    eligible_lines: frozenset[int] | None,
) -> bool:
    return eligible_lines is None or _line_number(source, position) in eligible_lines


def _span_is_eligible(
    source: str,
    start: int,
    end: int,
    eligible_lines: frozenset[int] | None,
) -> bool:
    if eligible_lines is None:
        return True
    first = _line_number(source, start)
    last = _line_number(source, max(start, end - 1))
    return any(first <= line <= last for line in eligible_lines)


def _finding(
    code: str,
    message: str,
    source: str,
    source_name: str,
    position: int,
    methods: Sequence[MethodSpan],
) -> QualityFinding:
    method = _method_for_position(methods, position)
    return QualityFinding(
        code,
        message,
        _line_number(source, position),
        source_name,
        method.symbol if method else source_name,
    )


def _pattern_findings(
    pattern: re.Pattern[str],
    code: str,
    message: str,
    source: str,
    masked_source: str,
    source_name: str,
    methods: Sequence[MethodSpan],
    eligible_lines: frozenset[int] | None,
) -> list[QualityFinding]:
    findings = []
    for match in pattern.finditer(masked_source):
        if _span_is_eligible(source, match.start(), match.end(), eligible_lines):
            findings.append(_finding(code, message, source, source_name, match.start(), methods))
    return findings


def _broad_catch_findings(context: JavaScanContext) -> list[QualityFinding]:
    findings = []
    for catch in BROAD_CATCH.finditer(context.masked_source):
        catch_end = _matching_brace(context.masked_source, catch.end() - 1)
        fallback = FALLBACK_RETURN.search(
            context.masked_source,
            catch.end(),
            catch_end - 1,
        )
        if fallback and _span_is_eligible(
            context.source,
            catch.start(),
            fallback.end(),
            context.eligible_lines,
        ):
            findings.append(
                _finding(
                    "BROAD-CATCH-FALLBACK",
                    "broad catch returns fallback success",
                    context.source,
                    context.source_name,
                    catch.start(),
                    context.methods,
                )
            )
    return findings


def _nullable_contract(methods: Sequence[MethodSpan], position: int) -> bool:
    method = _method_for_position(methods, position)
    return bool(method and method.nullable)


def _null_findings(
    source: str,
    masked_source: str,
    source_name: str,
    methods: Sequence[MethodSpan],
    eligible_lines: frozenset[int] | None,
    allow_declared_nullable: bool,
) -> list[QualityFinding]:
    checks = (
        (re.compile(r"\breturn\s+null\s*;"), "NULL-RETURN", "return null needs an independently proven external contract"),
        (re.compile(r"\.orElse\s*\(\s*null\s*\)"), "NULL-OR-ELSE", "orElse(null) hides absence"),
        (re.compile(r"\?[^:;]*\bnull\b[^;]*:|\?[^:;]*:[^;]*\bnull\b"), "NULL-TERNARY", "ternary propagates null"),
    )
    findings = []
    for pattern, code, message in checks:
        for match in pattern.finditer(masked_source):
            if code == "NULL-RETURN" and allow_declared_nullable and _nullable_contract(methods, match.start()):
                continue
            if _position_is_eligible(source, match.start(), eligible_lines):
                findings.append(_finding(code, message, source, source_name, match.start(), methods))
    return findings


def _repeated_null_guard_findings(context: JavaScanContext) -> list[QualityFinding]:
    findings = []
    for method in context.methods:
        if not _position_is_eligible(context.source, method.start, context.eligible_lines):
            continue
        body = context.masked_source[method.body_start:method.end]
        guards: dict[str, list[int]] = {}
        for match in re.finditer(r"\b([A-Za-z_$][\w$]*)\s*(?:==|!=)\s*null\b", body):
            guards.setdefault(match.group(1), []).append(method.body_start + match.start())
        for identifier, positions in guards.items():
            if len(positions) < 2:
                continue
            findings.append(_finding(
                "REPEATED-NULL-GUARD",
                f"'{identifier}' is checked against null {len(positions)} times; establish its invariant once",
                context.source,
                context.source_name,
                positions[0],
                (method,),
            ))
    return findings


def _effective_lines(masked_body: str) -> int:
    return sum(
        bool(line.strip().strip("{}"))
        for line in masked_body.splitlines()
    )


def _max_nesting(masked_body: str) -> int:
    depth = maximum = 0
    for character in masked_body:
        depth += int(character == "{")
        maximum = max(maximum, depth)
        depth = max(0, depth - int(character == "}"))
    return max(0, maximum - 1)


def _method_metric_findings(
    source: str,
    masked_source: str,
    source_name: str,
    methods: Sequence[MethodSpan],
    eligible_lines: frozenset[int] | None,
) -> list[QualityFinding]:
    findings = []
    for method in methods:
        if not _position_is_eligible(source, method.start, eligible_lines):
            continue
        body = masked_source[method.body_start:method.end]
        findings.extend(_one_method_metrics(source, source_name, method, body))
    return findings


def _metric_finding(
    code: str,
    measured: int,
    source: str,
    source_name: str,
    method: MethodSpan,
) -> QualityFinding | None:
    threshold = RULE_BY_CODE[code].threshold
    if threshold is None or measured <= threshold:
        return None
    message = f"{RULE_BY_CODE[code].description}: {measured} > {threshold}"
    return _finding(code, message, source, source_name, method.start, (method,))


def _one_method_metrics(
    source: str,
    source_name: str,
    method: MethodSpan,
    masked_body: str,
) -> list[QualityFinding]:
    parameters = _top_level_parameters(method.parameters)
    measurements = (
        ("METHOD-LOC", _effective_lines(masked_body)),
        ("METHOD-PARAMETERS", len(parameters)),
        ("METHOD-COMPLEXITY", 1 + len(COMPLEXITY_TOKEN.findall(masked_body))),
        ("METHOD-NESTING", _max_nesting(masked_body)),
    )
    findings = [
        finding
        for code, measured in measurements
        if (finding := _metric_finding(code, measured, source, source_name, method))
    ]
    if any(re.search(r"\b(?:boolean|Boolean)\b", parameter) for parameter in parameters):
        findings.append(_finding("BOOLEAN-FLAG", "boolean parameter needs two-command review", source, source_name, method.start, (method,)))
    return findings


def _method_structure_findings(
    source: str,
    masked_source: str,
    source_name: str,
    methods: Sequence[MethodSpan],
    eligible_lines: frozenset[int] | None,
) -> list[QualityFinding]:
    findings = []
    for method in methods:
        if not _position_is_eligible(source, method.start, eligible_lines):
            continue
        body = masked_source[method.body_start:method.end]
        findings.extend(_method_body_findings(source, source_name, method, body))
    return findings


def _method_body_findings(
    source: str,
    source_name: str,
    method: MethodSpan,
    masked_body: str,
) -> list[QualityFinding]:
    findings = []
    log_count = len(LOGGER_CALL.findall(masked_body))
    if log_count > (RULE_BY_CODE["EXCESSIVE-LOGGING"].threshold or 0):
        findings.append(_finding("EXCESSIVE-LOGGING", f"method has {log_count} log calls", source, source_name, method.start, (method,)))
    if len(re.findall(r"\b(?:if|else|case)\b[^{};]{0,300}\blog(?:ger)?\s*\.", masked_body, re.DOTALL)) > 1:
        findings.append(_finding("BRANCH-LOGGING", "several branches log independently", source, source_name, method.start, (method,)))
    if "isPresent(" in masked_body and re.search(r"\.get\s*\(", masked_body):
        findings.append(_finding("OPTIONAL-GET", "isPresent/get pair needs absence review", source, source_name, method.start, (method,)))
    for statement in masked_body.split(";"):
        if statement.count("?") > 1:
            findings.append(_finding("COMPLEX-TERNARY", "statement has multiple ternaries", source, source_name, method.start, (method,)))
            break
    return findings


def _comment_justification_findings(
    source: str,
    source_name: str,
    methods: Sequence[MethodSpan],
    eligible_lines: frozenset[int] | None,
) -> list[QualityFinding]:
    findings = []
    for method in methods:
        if not _position_is_eligible(source, method.start, eligible_lines):
            continue
        comment = COMMENT_TOKEN.search(source, method.body_start, method.end)
        if comment:
            findings.append(
                _finding(
                    "COMMENT-JUSTIFICATION",
                    "production method comment needs reason or external-constraint evidence",
                    source,
                    source_name,
                    comment.start(),
                    (method,),
                )
            )
    return findings


def _manual_duration_logging_findings(context: JavaScanContext) -> list[QualityFinding]:
    findings = []
    for method in context.methods:
        if not _position_is_eligible(context.source, method.start, context.eligible_lines):
            continue
        timer = MANUAL_DURATION_TIMER.search(
            context.masked_source,
            method.body_start,
            method.end,
        )
        logger = LOGGER_CALL.search(
            context.masked_source,
            method.body_start,
            method.end,
        )
        duration = None
        if timer:
            duration = re.search(
                rf"System\s*\.\s*(?:currentTimeMillis|nanoTime)\s*\(\s*\)\s*-\s*{re.escape(timer.group('variable'))}\b",
                context.masked_source[timer.end():method.end],
            )
        if timer and duration and logger:
            findings.append(
                _finding(
                    "MANUAL-DURATION-LOGGING",
                    "manual wall-clock timer is coupled to method logging; use existing tracing or metrics",
                    context.source,
                    context.source_name,
                    timer.start(),
                    (method,),
                )
            )
    return findings


def _normalization_findings(
    context: JavaScanContext,
) -> list[QualityFinding]:
    findings = []
    for method in context.methods:
        if not _position_is_eligible(context.source, method.start, context.eligible_lines):
            continue
        normalization = NORMALIZATION_CALL.search(
            context.masked_source,
            method.body_start,
            method.end,
        )
        if normalization:
            findings.append(
                _finding(
                    "NORMALIZATION-OWNERSHIP",
                    "normalization must belong to the first trust boundary and preserve the declared value semantics",
                    context.source,
                    context.source_name,
                    normalization.start(),
                    (method,),
                )
            )
    return findings


def _identifier_parts(identifier: str) -> tuple[str, ...]:
    snake_case = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", identifier)
    snake_case = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", snake_case)
    return tuple(part.lower() for part in re.split(r"[_$]+", snake_case) if part)


def _is_generic_normalization_name(name: str) -> bool:
    parts = _identifier_parts(name)
    if parts in GENERIC_NULL_FALLBACK_NAMES:
        return True
    return bool(
        parts
        and parts[0] in GENERIC_NORMALIZATION_VERBS
        and (len(parts) == 1 or all(part in GENERIC_TEXT_TOKENS for part in parts[1:]))
    )


def _is_generic_normalization_owner(owner: str) -> bool:
    parts = _identifier_parts(owner)
    return bool(parts) and all(part in GENERIC_NORMALIZATION_OWNERS for part in parts)


def _generic_normalization_declaration(method: MethodSpan) -> bool:
    parts = _identifier_parts(method.name)
    return _is_generic_normalization_name(method.name) and (
        len(parts) > 1 or _is_generic_normalization_owner(method.owner)
    )


def _generic_normalization_usage(usage: re.Match[str]) -> bool:
    name = usage.group("name")
    if not _is_generic_normalization_name(name):
        return False
    parts = _identifier_parts(name)
    owner = usage.group("owner")
    if len(parts) > 1:
        return True
    if owner is None or not _is_generic_normalization_owner(owner):
        return False
    owner_parts = _identifier_parts(owner)
    return owner[0].isupper() or len(owner_parts) > 1


def _generic_normalization_declaration_finding(
    context: JavaScanContext,
    method: MethodSpan,
) -> QualityFinding | None:
    if not _generic_normalization_declaration(method):
        return None
    return _finding(
        "GENERIC-NORMALIZATION-HELPER",
        f"'{method.name}' is a generic normalization helper; establish the invariant at a named trust boundary",
        context.source,
        context.source_name,
        method.start,
        (method,),
    )


def _generic_normalization_usage_findings(
    context: JavaScanContext,
    method: MethodSpan,
) -> list[QualityFinding]:
    findings = []
    body = context.masked_source[method.body_start:method.end]
    for usage in chain(METHOD_INVOCATION.finditer(body), METHOD_REFERENCE.finditer(body)):
        if _generic_normalization_usage(usage):
            findings.append(_finding(
                "GENERIC-NORMALIZATION-HELPER",
                f"'{usage.group('name')}' delegates normalization to a generic helper",
                context.source,
                context.source_name,
                method.body_start + usage.start(),
                (method,),
            ))
    return findings


def _generic_normalization_helper_findings(context: JavaScanContext) -> list[QualityFinding]:
    findings = []
    for method in context.methods:
        if not _position_is_eligible(context.source, method.start, context.eligible_lines):
            continue
        declaration = _generic_normalization_declaration_finding(context, method)
        if declaration:
            findings.append(declaration)
        findings.extend(_generic_normalization_usage_findings(context, method))
    return findings


def _identifier_tokens(identifier: str) -> frozenset[str]:
    return frozenset(_identifier_parts(identifier))


def _ambiguous_bucket_finding(
    context: JavaScanContext,
    identifier: re.Match[str],
    bucket_tokens: frozenset[str],
) -> QualityFinding:
    identifier_name = identifier.group(0)
    return _finding(
        "AMBIGUOUS-BUCKET-NAME",
        f"'{identifier_name}' uses relative bucket '{sorted(bucket_tokens)[0]}' without naming the domain distinction",
        context.source,
        context.source_name,
        identifier.start(),
        context.methods,
    )


def _ambiguous_bucket_name_findings(context: JavaScanContext) -> list[QualityFinding]:
    findings = []
    seen = set()
    for identifier in JAVA_IDENTIFIER.finditer(context.masked_source):
        bucket_tokens = _identifier_tokens(identifier.group(0)) & RELATIVE_BUCKET_TOKENS
        if not bucket_tokens or not _position_is_eligible(
            context.source,
            identifier.start(),
            context.eligible_lines,
        ):
            continue
        method = _method_for_position(context.methods, identifier.start())
        symbol = method.symbol if method else context.source_name
        key = (identifier.group(0), symbol)
        if key in seen:
            continue
        seen.add(key)
        findings.append(_ambiguous_bucket_finding(context, identifier, bucket_tokens))
    return findings


def scan_java_source(
    source: str,
    *,
    source_name: str = "<java>",
    changed_lines: frozenset[int] | None = None,
    production: bool = True,
    allow_declared_nullable: bool = False,
) -> list[QualityFinding]:
    masked_source = mask_java_non_code(source)
    methods = method_spans(masked_source, source_name)
    eligible = _eligible_lines(source, methods, changed_lines)
    context = JavaScanContext(source, masked_source, source_name, methods, eligible)
    findings = _base_findings(context)
    findings.extend(
        _production_findings(context, allow_declared_nullable)
        if production
        else _test_contract_findings(context)
    )
    findings.extend(_method_metric_findings(source, masked_source, source_name, methods, eligible))
    findings.extend(_method_structure_findings(source, masked_source, source_name, methods, eligible))
    findings.extend(_ambiguous_bucket_name_findings(context))
    return sorted(findings, key=lambda finding: (finding.source, finding.line, finding.code))


def _base_findings(context: JavaScanContext) -> list[QualityFinding]:
    checks = (
        (EMPTY_CATCH, "EMPTY-CATCH", "empty catch ignores a failure"),
        (WILDCARD_IMPORT, "WILDCARD-IMPORT", "wildcard import needs style review"),
        (re.compile(r"\bcontinue\s*;"), "CONTROL-FLOW-SKIP", "continue is prohibited in delivered code"),
        (GENERIC_RESULT, "GENERIC-RESULT-SHAPE", "generic result shape needs boundary review"),
    )
    findings = []
    for pattern, code, message in checks:
        findings.extend(_pattern_findings(
            pattern, code, message, context.source, context.masked_source,
            context.source_name, context.methods, context.eligible_lines,
        ))
    return findings + _broad_catch_findings(context)


def _production_findings(context: JavaScanContext, allow_declared_nullable: bool) -> list[QualityFinding]:
    scan_arguments = (context.source, context.masked_source, context.source_name, context.methods, context.eligible_lines)
    findings = _pattern_findings(FIELD_INJECTION, "FIELD-INJECTION", "use constructor injection", *scan_arguments)
    findings.extend(_null_findings(*scan_arguments, allow_declared_nullable))
    findings.extend(_comment_justification_findings(context.source, context.source_name, context.methods, context.eligible_lines))
    findings.extend(_manual_duration_logging_findings(context))
    findings.extend(_generic_normalization_helper_findings(context))
    findings.extend(_normalization_findings(context))
    findings.extend(_repeated_null_guard_findings(context))
    findings.extend(_pattern_findings(
        REQUIRED_INPUT_EMPTY_FALLBACK,
        "REQUIRED-INPUT-EMPTY-FALLBACK",
        "missing required input may return an empty result instead of failing fast",
        *scan_arguments,
    ))
    return findings


def _test_contract_findings(context: JavaScanContext) -> list[QualityFinding]:
    findings = [
        _finding(
            "DISABLED-TEST",
            "disabled or conditional test scope needs explicit review",
            context.source,
            context.source_name,
            _position_for_line(context.source, int(finding["line"])),
            context.methods,
        )
        for finding in annotation_findings(context.source)
        if context.eligible_lines is None or int(finding["line"]) in context.eligible_lines
    ]
    findings.extend(_boundary_any_findings(context))
    findings.extend(_multi_code_assertion_findings(context))
    return findings


def _position_for_line(source: str, line: int) -> int:
    if line <= 1:
        return 0
    position = 0
    for _ in range(line - 1):
        position = source.find("\n", position) + 1
        if position == 0:
            return len(source)
    return position


def _boundary_any_findings(context: JavaScanContext) -> list[QualityFinding]:
    if BOUNDARY_ANY.search(context.masked_source) and not CAPTOR_USAGE.search(context.masked_source):
        match = BOUNDARY_ANY.search(context.masked_source)
        assert match is not None
        return [_finding(
            "BOUNDARY-ANY-WITHOUT-CAPTOR",
            "critical boundary request uses any() without captor or exact matching",
            context.source,
            context.source_name,
            match.start(),
            context.methods,
        )]
    return []


def _multi_code_assertion_findings(context: JavaScanContext) -> list[QualityFinding]:
    codes = set(CONTRACT_CODE.findall(context.masked_source))
    asserted_codes = {
        code
        for assertion in ASSERTION.finditer(context.masked_source)
        for code in CONTRACT_CODE.findall(assertion.group(0))
    }
    if len(codes) > 1 and len(asserted_codes) < len(codes):
        match = CONTRACT_CODE.search(context.masked_source)
        assert match is not None
        return [_finding(
            "MULTI-CODE-NO-OUTPUT-ASSERTION",
            "multiple event or status codes appear without corresponding output mapping assertions",
            context.source,
            context.source_name,
            match.start(),
            context.methods,
        )]
    return []


def load_review_evidence(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("review evidence must be a JSON object")
    return payload


def review_evidence_errors(
    evidence: Mapping[str, object] | None,
    candidate_hash: str,
    findings: Iterable[QualityFinding],
    *,
    require_clean_guard: bool = False,
    pre_review_gate: Mapping[str, object] | None = None,
) -> list[str]:
    if evidence is None:
        return ["independent review evidence is required"]
    errors = _review_header_errors(evidence, candidate_hash, require_clean_guard, pre_review_gate)
    errors.extend(_review_finding_errors(evidence, findings))
    return errors


def _review_header_errors(
    evidence: Mapping[str, object],
    candidate_hash: str,
    require_clean_guard: bool,
    pre_review_gate: Mapping[str, object] | None,
) -> list[str]:
    errors = []
    if evidence.get("candidate_sha256") != candidate_hash:
        errors.append("review evidence does not match the current candidate")
    reviewer = evidence.get("reviewer")
    if evidence.get("independent") is not True or not isinstance(reviewer, str) or not reviewer.strip():
        errors.append("review evidence must identify an independent reviewer")
    if evidence.get("blocking_findings") != []:
        errors.append("review evidence contains unresolved blocking findings")
    if require_clean_guard:
        guards = evidence.get("guards")
        if not isinstance(guards, list) or "clean-code-guard" not in guards:
            errors.append("production diff requires clean-code-guard evidence")
    if pre_review_gate is not None:
        actual_gate = evidence.get("pre_review_gate")
        if actual_gate != dict(pre_review_gate):
            errors.append("review evidence does not match the objective pre-review Gate")
        if any(not isinstance(value, str) or not value for value in pre_review_gate.values()):
            errors.append("objective pre-review Gate needs quality/build candidate and test/coverage evidence hashes")
    errors.extend(_risk_errors(evidence.get("risks")))
    return errors


def _risk_errors(risks: object) -> list[str]:
    if not isinstance(risks, list):
        return ["review evidence risks must be a list"]
    errors = []
    seen = set()
    for index, risk in enumerate(risks):
        if not isinstance(risk, dict):
            errors.append(f"review risk {index} must be an object")
            continue
        risk_id = risk.get("id")
        owner = risk.get("owner")
        evidence = risk.get("evidence")
        if not isinstance(risk_id, str) or not risk_id.strip():
            errors.append(f"review risk {index} needs an id")
        elif risk_id in seen:
            errors.append(f"review risk id must be unique: {risk_id}")
        elif risk_id not in RISK_OWNERS:
            errors.append(f"review risk {index} has unknown id: {risk_id}")
        else:
            seen.add(risk_id)
        if not isinstance(owner, str) or not owner.strip():
            errors.append(f"review risk {index} needs one owner")
        elif isinstance(risk_id, str) and risk_id in RISK_OWNERS and owner != RISK_OWNERS[risk_id]:
            errors.append(f"review risk {risk_id} must be owned by {RISK_OWNERS[risk_id]}")
        if (
            not isinstance(evidence, list)
            or not evidence
            or any(not isinstance(item, str) or not item.strip() for item in evidence)
        ):
            errors.append(f"review risk {index} needs concrete evidence")
    return errors


def _accepted_fingerprints(
    evidence: Mapping[str, object],
    known_fingerprints: frozenset[str],
) -> tuple[dict[str, str], list[str]]:
    entries = evidence.get("accepted_findings")
    if not isinstance(entries, list):
        return {}, ["review evidence accepted_findings must be a list"]
    accepted = {}
    reasons: dict[str, str] = {}
    errors = []
    for index, entry in enumerate(entries):
        fingerprint, reason, entry_errors = _accepted_finding_entry(
            index, entry, known_fingerprints, frozenset(accepted)
        )
        errors.extend(entry_errors)
        if fingerprint:
            if reason and reason in reasons:
                errors.append(
                    f"accepted finding reason must be specific; generic reason reused by "
                    f"{reasons[reason]} and {fingerprint}"
                )
            elif reason:
                reasons[reason] = fingerprint
            accepted[fingerprint] = reason
    return accepted, errors


def _accepted_finding_entry(
    index: int,
    entry: object,
    known_fingerprints: frozenset[str],
    accepted_fingerprints: frozenset[str],
) -> tuple[str | None, str, list[str]]:
    if not isinstance(entry, dict):
        return None, "", [f"accepted finding {index} must be an object"]
    fingerprint = entry.get("fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint.strip():
        return None, "", [f"accepted finding {index} needs a fingerprint"]
    if fingerprint in accepted_fingerprints:
        return None, "", [f"accepted finding fingerprint must be unique: {fingerprint}"]
    errors = []
    if fingerprint not in known_fingerprints:
        errors.append(f"accepted finding does not match the current candidate: {fingerprint}")
    reason = entry.get("reason")
    normalized_reason = reason.strip() if isinstance(reason, str) else ""
    if len(normalized_reason) < 12:
        errors.append(f"accepted finding {fingerprint} needs a concrete reason")
    finding_evidence = entry.get("evidence")
    if (
        not isinstance(finding_evidence, list)
        or not finding_evidence
        or any(not isinstance(item, str) or not item.strip() for item in finding_evidence)
    ):
        errors.append(f"accepted finding {fingerprint} needs concrete evidence")
    return fingerprint, normalized_reason, errors


def _review_finding_errors(
    evidence: Mapping[str, object],
    findings: Iterable[QualityFinding],
) -> list[str]:
    current_findings = tuple(findings)
    review_fingerprints = frozenset(
        finding.fingerprint
        for finding in current_findings
        if finding.severity == REVIEW
    )
    accepted, errors = _accepted_fingerprints(evidence, review_fingerprints)
    for finding in current_findings:
        if finding.severity == ERROR:
            errors.append(f"{finding.code} at {finding.source}:{finding.line}")
        elif len(accepted.get(finding.fingerprint, "")) < 12:
            errors.append(f"unresolved {finding.code} at {finding.source}:{finding.line}")
    return errors


def parse_touched_java_lines(diff: str) -> dict[str, frozenset[int]]:
    touched: dict[str, set[int]] = {}
    path = None
    old_path = None
    new_line = 0
    anchor = 0
    saw_addition = saw_deletion = in_hunk = False

    def close_hunk() -> None:
        if path and saw_deletion and not saw_addition:
            touched.setdefault(path, set()).add(max(1, anchor))

    for line in diff.splitlines():
        if line.startswith("--- a/"):
            close_hunk()
            old_path = line[6:]
            path = None
            new_line = 0
            saw_addition = saw_deletion = in_hunk = False
            continue
        if line.startswith("+++ b/"):
            close_hunk()
            path = line[6:]
            saw_addition = saw_deletion = in_hunk = False
            continue
        if line == "+++ /dev/null":
            path = old_path
            saw_addition = saw_deletion = in_hunk = False
            continue
        header = HUNK_HEADER.match(line)
        if header:
            close_hunk()
            new_line = anchor = int(header.group(1))
            saw_addition = saw_deletion = False
            in_hunk = True
            continue
        if not path or not path.endswith(".java") or not in_hunk:
            continue
        if line.startswith("+"):
            touched.setdefault(path, set()).add(new_line)
            new_line += 1
            saw_addition = True
        elif line.startswith("-"):
            saw_deletion = True
        elif not line.startswith("\\"):
            new_line += 1
    close_hunk()
    return {path: frozenset(lines) for path, lines in touched.items()}


def _write_json(path: Path | None, payload: Mapping[str, object]) -> None:
    if path:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _render_finding(finding: QualityFinding) -> str:
    return (
        f"{finding.severity}: {finding.code} {finding.source}:{finding.line} "
        f"[{finding.symbol}] {finding.message}"
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path)
    parser.add_argument("--changed-line", type=int, action="append", default=[])
    parser.add_argument("--test-source", action="store_true")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--run-dir", type=Path, help="Pretty topic tmp run directory for evidence output")
    parser.add_argument("--list-rules", action="store_true")
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(arguments)
    if args.list_rules:
        print(json.dumps([asdict(rule) for rule in RULES], ensure_ascii=False, indent=2))
        return 0
    if args.source is None:
        print("source is required unless --list-rules is used", file=sys.stderr)
        return 2
    try:
        if args.run_dir is None and args.json_output:
            raise ValueError("Pretty evidence paths require --run-dir under docs/pretty/<topic>/tmp/<run-id>")
        if args.run_dir is not None:
            run_dir = validate_run_dir(args.run_dir.parent.parent, args.run_dir)
            args.run_dir = run_dir
            for attribute in ("json_output",):
                artifact = getattr(args, attribute)
                if artifact is not None:
                    normalized = artifact.resolve()
                    validate_artifact_path(run_dir, normalized)
                    setattr(args, attribute, normalized)
        source = args.source.read_text(encoding="utf-8")
        findings = scan_java_source(
            source,
            source_name=str(args.source),
            changed_lines=frozenset(args.changed_line) if args.changed_line else None,
            production=not args.test_source,
        )
        scan_hash = candidate_sha256({str(args.source): source})
        errors = [
            f"{finding.code} at {finding.source}:{finding.line}"
            for finding in findings
            if finding.severity == ERROR
        ]
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"quality scan failed: {error}", file=sys.stderr)
        return 2
    for finding in findings:
        print(_render_finding(finding))
    _write_json(args.json_output, {
        "scan_sha256": scan_hash,
        "scope": "diagnostic-source",
        "formal_evidence": False,
        "findings": [finding.as_dict() for finding in findings],
        "review_pending": any(finding.severity == REVIEW for finding in findings),
        "passed": not errors,
        "errors": errors,
    })
    for error in errors:
        print(f"gate: {error}", file=sys.stderr)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
