#!/usr/bin/env python3
"""Shared rule names and defaults for the lightweight Java quality gate."""

from __future__ import annotations

from dataclasses import dataclass


ERROR = "error"

DEFAULT_LINE_COVERAGE = 90.0
DEFAULT_BRANCH_COVERAGE = 80.0


@dataclass(frozen=True)
class RuleSpec:
    code: str
    description: str


RULES = (
    RuleSpec("LABELED-CONTINUE", "labeled continue hides a cross-level control-flow jump"),
    RuleSpec("VOID_TAIL_RETURN", "void methods must not end with an unconditional return statement"),
    RuleSpec("UNREACHABLE_STATEMENT", "a statement after an unconditional control-flow terminator is unreachable"),
    RuleSpec("EMPTY_CATCH", "catch blocks must contain handling statements"),
    RuleSpec("WHOLE-OBJECT-LOGGING", "whole-object JSON serialization can leak or amplify log payloads"),
    RuleSpec("SENSITIVE-LOGGING", "credentials or authentication headers must not be logged"),
    RuleSpec(
        "MANUAL-DURATION-LOGGING",
        "manual wall-clock timing bypasses the repository tracing or metrics abstraction",
    ),
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
        if not rule.description.strip():
            errors.append(f"quality rule {rule.code} needs a description")
    return errors
