#!/usr/bin/env python3
"""Single source of truth for Pretty quality rules and risk ownership."""

from __future__ import annotations

from dataclasses import dataclass


ERROR = "error"
REVIEW = "review_required"


@dataclass(frozen=True)
class RuleSpec:
    code: str
    severity: str
    description: str
    threshold: int | None = None


# Every mechanical rule is registered exactly once.  Prose references use these IDs.
RULES = (
    RuleSpec("EMPTY-CATCH", ERROR, "empty catch silently ignores a failure"),
    RuleSpec("BROAD-CATCH-FALLBACK", ERROR, "broad catch returns null, empty, or success"),
    RuleSpec("FIELD-INJECTION", ERROR, "production dependency uses field injection"),
    RuleSpec("NULL-RETURN", ERROR, "method returns null without an explicit nullable contract"),
    RuleSpec("NULL-OR-ELSE", ERROR, "Optional is converted to an undeclared null"),
    RuleSpec("NULL-TERNARY", ERROR, "ternary expression propagates undeclared null"),
    RuleSpec("CONTROL-FLOW-SKIP", ERROR, "continue obscures the business control flow"),
    RuleSpec("WILDCARD-IMPORT", REVIEW, "wildcard import requires repository-style review"),
    RuleSpec("GENERIC-RESULT-SHAPE", REVIEW, "generic success/code/message/data result shape"),
    RuleSpec("COMPLEX-TERNARY", REVIEW, "statement contains nested or multiple ternaries"),
    RuleSpec("METHOD-LOC", REVIEW, "method exceeds the effective-line target", 20),
    RuleSpec("METHOD-PARAMETERS", REVIEW, "method exceeds the parameter target", 4),
    RuleSpec("METHOD-COMPLEXITY", REVIEW, "method exceeds the complexity target", 10),
    RuleSpec("METHOD-NESTING", REVIEW, "method exceeds the nesting target", 5),
    RuleSpec("BOOLEAN-FLAG", REVIEW, "boolean parameter may hide two commands"),
    RuleSpec("OPTIONAL-GET", REVIEW, "Optional isPresent/get pair requires contract review"),
    RuleSpec("EXCESSIVE-LOGGING", REVIEW, "method has many log calls", 2),
    RuleSpec("BRANCH-LOGGING", REVIEW, "multiple branches log independently"),
    RuleSpec("MANUAL-DURATION-LOGGING", ERROR, "manual wall-clock timing must not be used for logs"),
    RuleSpec("COMMENT-JUSTIFICATION", REVIEW, "production comment must explain a non-obvious reason"),
    RuleSpec("GENERIC-NORMALIZATION-HELPER", ERROR, "generic text normalization helper hides boundary ownership"),
    RuleSpec("NORMALIZATION-OWNERSHIP", REVIEW, "input normalization needs an explicit boundary contract"),
    RuleSpec("AMBIGUOUS-BUCKET-NAME", REVIEW, "relative bucket name needs a defined opposite and partition rule"),
    RuleSpec("REPEATED-NULL-GUARD", REVIEW, "one input is guarded repeatedly inside a method"),
    RuleSpec("DISABLED-TEST", ERROR, "new or changed test is disabled or conditionally skipped"),
    RuleSpec("REQUIRED-INPUT-EMPTY-FALLBACK", REVIEW, "missing input may be disguised as an empty query result"),
    RuleSpec("BOUNDARY-ANY-WITHOUT-CAPTOR", REVIEW, "boundary stub uses any() without request capture"),
    RuleSpec("MULTI-CODE-NO-OUTPUT-ASSERTION", REVIEW, "multiple event or status codes need matching output assertions"),
)
RULE_BY_CODE = {rule.code: rule for rule in RULES}

RISK_OWNERS = {
    "MODULE_BOUNDARY": "codebase-design",
    "JAVA_OOD": "121-java-object-oriented-design",
    "FOCUSED_SOLID": "solid-principles",
    "TYPE_DESIGN": "122-java-type-design",
    "CHANGE_AXIS": "design-patterns",
    "JAVA_RUNTIME_RISK": "java-code-review",
    "BEHAVIOR_TEST": "tdd",
}


PRECEDENCE = (
    "已批准 PRD / Design",
    "Pretty 共享质量规则",
    "专项 Skill 的非强制建议",
    "真实仓库既有惯例",
    "AGENTS",
    "Trellis",
)


def registry_errors() -> list[str]:
    """Return deterministic errors for duplicate or malformed registry entries."""
    errors: list[str] = []
    codes = [rule.code for rule in RULES]
    duplicates = sorted({code for code in codes if codes.count(code) > 1})
    if duplicates:
        errors.append(f"duplicate quality rule IDs: {duplicates}")
    for rule in RULES:
        if rule.severity not in {ERROR, REVIEW}:
            errors.append(f"unknown severity for {rule.code}: {rule.severity}")
        if not rule.description.strip():
            errors.append(f"quality rule {rule.code} needs a description")
    return errors
