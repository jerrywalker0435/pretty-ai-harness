#!/usr/bin/env python3
"""Shared rule names and defaults for the lightweight Java quality gate."""

from __future__ import annotations

from dataclasses import dataclass


ERROR = "error"
REVIEW = "review_required"

DEFAULT_LINE_COVERAGE = 90.0
DEFAULT_BRANCH_COVERAGE = 80.0


@dataclass(frozen=True)
class RuleSpec:
    code: str
    severity: str
    description: str


RULES = (
    RuleSpec("EMPTY-CATCH", ERROR, "empty catch silently ignores a failure"),
    RuleSpec("BROAD-CATCH-FALLBACK", ERROR, "broad catch hides a failure behind null, empty, or success"),
    RuleSpec("FIELD-INJECTION", ERROR, "production dependency uses field injection"),
    RuleSpec("CONTROL-FLOW-SKIP", ERROR, "continue obscures the business control flow"),
    RuleSpec("MANUAL-DURATION-LOGGING", ERROR, "manual wall-clock timing is used for logging"),
    RuleSpec("NORMALIZATION-HELPER", ERROR, "a normalization helper hides the first trust boundary and invites repeated defense"),
    RuleSpec("GENERIC-NORMALIZATION-HELPER", ERROR, "generic text normalization hides boundary ownership"),
    RuleSpec("IMPLICIT-FIELD-FALLBACK", ERROR, "an undocumented alternate field hides missing or corrupt data"),
    RuleSpec("DISABLED-TEST", ERROR, "a changed test is disabled or conditionally skipped"),
    RuleSpec("NULL-RETURN", REVIEW, "return null requires an explicit nullable contract"),
    RuleSpec("REPEATED-NORMALIZATION", REVIEW, "the same method or boundary performs redundant text normalization"),
    RuleSpec("IDENTIFIER-NORMALIZATION", REVIEW, "an ID or Code is normalized without a proven boundary contract"),
    RuleSpec("NORMALIZATION-OWNERSHIP", REVIEW, "normalization ownership must be justified by the first trust boundary"),
    RuleSpec("WILDCARD-IMPORT", REVIEW, "wildcard import requires review"),
    RuleSpec("OPTIONAL-GET", REVIEW, "Optional get/isPresent usage requires contract review"),
    RuleSpec("BOOLEAN-FLAG", REVIEW, "boolean parameter may hide two commands"),
    RuleSpec("GENERIC-RESULT-SHAPE", REVIEW, "generic success/code/message/data result shape"),
    RuleSpec("COMPLEX-TERNARY", REVIEW, "nested or repeated ternary makes control flow harder to read"),
)

RULE_BY_CODE = {rule.code: rule for rule in RULES}


def registry_errors() -> list[str]:
    """Return deterministic registry errors for the gate's self-check."""
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
