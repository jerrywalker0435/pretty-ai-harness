"""Shared Java test disabled-scope detection for execution gates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


DISABLED_NAMES = frozenset({
    "Disabled", "Ignore", "DisabledIf", "DisabledIfEnvironmentVariable",
    "DisabledIfSystemProperty", "DisabledOn", "DisabledOnOs", "DisabledOnJre",
    "DisabledInNativeImage", "DisabledForJreRange", "EnabledIf",
    "EnabledIfEnvironmentVariable", "EnabledIfSystemProperty", "EnabledOn",
    "EnabledOnOs", "EnabledOnJre", "EnabledInNativeImage", "EnabledForJreRange",
})
ANNOTATION = re.compile(r"(?m)^\s*@(?P<name>(?:[A-Za-z_$][\w$]*\.)*[A-Za-z_$][\w$]*)\b")
ANNOTATION_DECLARATION = re.compile(
    r"(?s)(?P<prefix>(?:\s*@[^\n]+\n){1,8})\s*@interface\s+(?P<name>[A-Za-z_$][\w$]*)"
)
JAVA_NON_CODE = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*.*?\*/', re.DOTALL)
CLASS_DECLARATION = re.compile(
    r"(?ms)(?P<prefix>(?:(?:\s*@[^\n]+\n){0,8}))\s*"
    r"(?:public\s+|protected\s+|private\s+|static\s+|final\s+)*"
    r"(?:class|interface|enum)\s+(?P<name>[A-Za-z_$][\w$]*)[^\{]*\{"
)
METHOD_DECLARATION = re.compile(
    r"(?ms)(?P<prefix>(?:(?:\s*@[^\n]+\n){0,8}))\s*"
    r"(?:public\s+|protected\s+|private\s+|static\s+|final\s+|synchronized\s+)*"
    r"(?:[A-Za-z_$][\w$<>.,\[\] ?]*\s+)?(?P<name>[A-Za-z_$][\w$]*)\s*\([^;{}]*\)\s*\{"
)


@dataclass(frozen=True)
class DisabledScope:
    kind: str
    name: str
    start: int
    end: int
    disabled: bool
    annotation: str


def _matching_brace(source: str, opening: int) -> int:
    depth = 0
    for index in range(opening, len(source)):
        depth += int(source[index] == "{")
        depth -= int(source[index] == "}")
        if depth == 0:
            return index + 1
    return len(source)


def _mask_non_code(source: str) -> str:
    return JAVA_NON_CODE.sub(
        lambda match: "".join("\n" if character == "\n" else " " for character in match.group(0)),
        source,
    )


def _simple_name(name: str) -> str:
    return name.rsplit(".", 1)[-1]


def _is_disabled_annotation(name: str, meta_names: set[str]) -> bool:
    simple = _simple_name(name)
    return simple in DISABLED_NAMES or simple in meta_names


def meta_disabled_names(source: str) -> set[str]:
    names = set()
    for declaration in ANNOTATION_DECLARATION.finditer(_mask_non_code(source)):
        annotations = ANNOTATION.finditer(declaration.group("prefix"))
        if any(_is_disabled_annotation(match.group("name"), set()) for match in annotations):
            names.add(declaration.group("name"))
    return names


def annotation_findings(source: str, meta_names: set[str] | None = None) -> list[dict[str, object]]:
    meta_names = meta_names or meta_disabled_names(source)
    findings = []
    for match in ANNOTATION.finditer(_mask_non_code(source)):
        name = match.group("name")
        if not _is_disabled_annotation(name, meta_names):
            continue
        findings.append({
            "line": source.count("\n", 0, match.start()) + 1,
            "kind": "meta-disabled" if _simple_name(name) in meta_names else "disabled",
            "annotation": f"@{name}",
        })
    return findings


def _annotation_prefix_disabled(prefix: str, meta_names: set[str]) -> tuple[bool, str]:
    for match in ANNOTATION.finditer(prefix):
        if _is_disabled_annotation(match.group("name"), meta_names):
            return True, f"@{match.group('name')}"
    return False, ""


def discover_scopes(source: str, meta_names: set[str] | None = None) -> tuple[DisabledScope, ...]:
    meta_names = meta_names or meta_disabled_names(source)
    masked_source = _mask_non_code(source)
    scopes = []
    for kind, pattern in (("class", CLASS_DECLARATION), ("method", METHOD_DECLARATION)):
        for match in pattern.finditer(masked_source):
            disabled, annotation = _annotation_prefix_disabled(match.group("prefix"), meta_names)
            scopes.append(DisabledScope(
                kind,
                match.group("name"),
                match.start(),
                _matching_brace(masked_source, match.end() - 1),
                disabled,
                annotation,
            ))
    return tuple(scopes)


def targeted_findings(
    source: str,
    expected_tests: Sequence[str],
    meta_names: set[str] | None = None,
) -> list[dict[str, object]]:
    meta_names = meta_names or meta_disabled_names(source)
    scopes = discover_scopes(source, meta_names)
    findings = []
    for expected in expected_tests:
        class_name, separator, method_name = expected.partition("#")
        simple_class = re.split(r"[.$]", class_name)[-1]
        disabled = _target_disabled_scope(scopes, simple_class, method_name if separator else None)
        if disabled:
            findings.append({
                "expected": expected,
                "line": source.count("\n", 0, disabled.start) + 1,
                "kind": "disabled-scope",
                "annotation": disabled.annotation,
            })
    return findings


def _target_disabled_scope(
    scopes: Sequence[DisabledScope],
    class_name: str,
    method_name: str | None,
) -> DisabledScope | None:
    classes = [scope for scope in scopes if scope.kind == "class" and scope.name == class_name]
    for class_scope in classes:
        methods = [
            scope for scope in scopes
            if scope.kind == "method"
            and scope.name == method_name
            and class_scope.start <= scope.start < class_scope.end
        ]
        if method_name and not methods:
            continue
        target = methods[0] if method_name else class_scope
        ancestors = [
            scope for scope in scopes
            if scope.kind == "class" and scope.start <= target.start < scope.end and scope.disabled
        ]
        return target if target.disabled else ancestors[-1] if ancestors else None
    return None


def scan_paths(repo: Path, paths: Iterable[str]) -> list[dict[str, object]]:
    meta_names = repository_meta_disabled_names(repo)
    findings = []
    for relative_path in sorted(set(paths)):
        source_path = repo / relative_path
        if not source_path.is_file():
            continue
        source = source_path.read_text(encoding="utf-8")
        for finding in annotation_findings(source, meta_names):
            findings.append({"path": relative_path, **finding})
    return findings


def repository_meta_disabled_names(repo: Path) -> set[str]:
    meta_names: set[str] = set()
    for source_path in repo.rglob("*.java"):
        if ".git" in source_path.parts or "target" in source_path.parts:
            continue
        meta_names.update(meta_disabled_names(source_path.read_text(encoding="utf-8")))
    return meta_names
