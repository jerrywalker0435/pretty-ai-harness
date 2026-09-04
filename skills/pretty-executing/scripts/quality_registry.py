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
    RuleSpec("LABELED-CONTINUE", ERROR, "labeled continue hides a cross-level control-flow jump"),
    RuleSpec("NUMBERED-STEP-COMMENT", ERROR, "numbered step comment narrates code instead of explaining why"),
    RuleSpec("WHOLE-OBJECT-LOGGING", ERROR, "whole-object JSON serialization can leak or amplify log payloads"),
    RuleSpec("SENSITIVE-LOGGING", ERROR, "credentials or authentication headers must not be logged"),
    RuleSpec("MANUAL-DURATION-LOGGING", ERROR, "manual wall-clock timing is used for logging"),
    RuleSpec("DISABLED-TEST", ERROR, "a changed test is disabled or conditionally skipped"),
    RuleSpec("WILDCARD-IMPORT", REVIEW, "wildcard import requires review"),
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
