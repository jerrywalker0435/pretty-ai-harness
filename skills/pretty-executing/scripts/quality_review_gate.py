#!/usr/bin/env python3
"""Validate the bounded quality-review closure produced by pretty-executing."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Sequence


MAX_REPAIR_ATTEMPTS = 2
FINDING_ID = re.compile(r"QF-\d{3,}")
REPAIR_GROUP_ID = re.compile(r"QG-\d{3,}")
CONTROL_FLOW_REVIEW_RULE = "21"
ALLOWED_STATUS = {"fixed", "exception", "open"}
CQS_STATUS = {"clear", "finding", "exception"}
CQS_PLACEHOLDERS = {"unknown", "n/a", "not checked", "todo"}


def _non_empty_string(candidate_text: object) -> bool:
    return isinstance(candidate_text, str) and bool(candidate_text.strip())


def _specific_cqs_text(candidate_text: object) -> bool:
    return _non_empty_string(candidate_text) and candidate_text.strip().lower() not in CQS_PLACEHOLDERS


def _repository_relative_path(candidate_path: object) -> bool:
    if not _non_empty_string(candidate_path):
        return False
    path = PurePosixPath(candidate_path)
    return (
        path != PurePosixPath(".")
        and not path.is_absolute()
        and ".." not in path.parts
        and path.as_posix() == candidate_path
    )


def _validate_scope(scope: object, label: str) -> list[str]:
    if not isinstance(scope, list) or not scope:
        return [f"{label} must be a non-empty list"]
    return [
        f"{label} entries must use repository-relative path#symbol: {entry!r}"
        for entry in scope
        if not _valid_symbol_location(entry)
    ]


def _valid_symbol_location(candidate_location: object) -> bool:
    return _symbol_path(candidate_location) is not None


def _symbol_path(candidate_location: object) -> str | None:
    if not _non_empty_string(candidate_location):
        return None
    path, separator, symbol = candidate_location.partition("#")
    source_path = re.sub(r":\d+$", "", path)
    if not separator or not symbol.strip() or not _repository_relative_path(source_path):
        return None
    return source_path


def _symbol_location_key(candidate_location: object) -> str | None:
    """Return a stable path#symbol key while ignoring an optional line number."""
    if not _non_empty_string(candidate_location):
        return None
    path, separator, symbol = candidate_location.partition("#")
    source_path = re.sub(r":\d+$", "", path)
    if not separator or not symbol.strip() or not _repository_relative_path(source_path):
        return None
    return f"{source_path}#{symbol.strip()}"


def _validate_cqs_locations(
    locations: object,
    label: str,
    reviewed_paths: set[str] | None,
) -> list[str]:
    if not isinstance(locations, list) or not locations:
        return [f"{label} must be a non-empty list"]
    errors: list[str] = []
    for index, location in enumerate(locations):
        location_label = f"{label}[{index}]"
        if not _valid_symbol_location(location):
            errors.append(f"{location_label} must use path:line#symbol or path#symbol")
            continue
        if reviewed_paths is not None and (path := _symbol_path(location)) not in reviewed_paths:
            errors.append(f"{location_label} path must be included in reviewed_paths: {path}")
    return errors


def _validate_cqs_entry(
    entry: object,
    label: str,
    required_fields: tuple[str, ...],
    reviewed_paths: set[str] | None,
) -> list[str]:
    if not isinstance(entry, dict):
        return [f"{label} must be an object"]
    errors = [
        f"{label}.{field} must be a non-empty string"
        for field in required_fields
        if not _specific_cqs_text(entry.get(field))
    ]
    location = entry.get("location")
    if not _valid_symbol_location(location):
        errors.append(f"{label}.location must use path:line#symbol or path#symbol")
    elif reviewed_paths is not None and (path := _symbol_path(location)) not in reviewed_paths:
        errors.append(f"{label}.location path must be included in reviewed_paths: {path}")
    return errors


def _validate_cqs_entries(
    entries: object,
    label: str,
    required_fields: tuple[str, ...],
    reviewed_paths: set[str] | None,
) -> list[str]:
    if not isinstance(entries, list):
        return [f"{label} must be a list"]
    return [
        error
        for index, entry in enumerate(entries)
        for error in _validate_cqs_entry(entry, f"{label}[{index}]", required_fields, reviewed_paths)
    ]


def _validate_cqs_finding_evidence(
    finding: dict[str, object],
    finding_id: str,
    reviewed_paths: set[str] | None,
) -> list[str]:
    if finding.get("source") != "clean-code-guard" or str(finding.get("rule")) != "4":
        return []
    errors: list[str] = []
    for field in ("side_effect_locations", "caller_consumption_locations"):
        errors.extend(_validate_cqs_locations(finding.get(field), f"{finding_id}.{field}", reviewed_paths))
    return errors


def _cqs_location_keys(locations: object) -> set[str]:
    if not isinstance(locations, list):
        return set()
    keys = {_symbol_location_key(location) for location in locations}
    keys.discard(None)
    return {str(key) for key in keys}


def _cqs_entry_location_keys(entries: object) -> set[str]:
    entries = entries if isinstance(entries, list) else []
    locations = [entry.get("location") for entry in entries if isinstance(entry, dict)]
    return _cqs_location_keys(locations)


def _validate_cqs_not_applicable(value: object) -> list[str]:
    if not isinstance(value, dict):
        return ["cqs_not_applicable must include reason and facts when cqs_checks is empty"]
    return [
        f"cqs_not_applicable.{field} must be a non-empty string"
        for field in ("reason", "facts")
        if not _specific_cqs_text(value.get(field))
    ]


def _cqs_method_errors(
    check: dict[str, object],
    label: str,
    reviewed_paths: set[str] | None,
    seen_methods: set[str],
) -> tuple[list[str], str | None]:
    method = check.get("method")
    method_key = _symbol_location_key(method)
    if method_key is None:
        return [f"{label}.method must use path:line#symbol or path#symbol"], None
    errors: list[str] = []
    if reviewed_paths is not None and (path := _symbol_path(method)) not in reviewed_paths:
        errors.append(f"{label}.method path must be included in reviewed_paths: {path}")
    if method_key in seen_methods:
        errors.append(f"duplicate CQS method: {method_key}")
    seen_methods.add(method_key)
    return errors, method_key


def _cqs_chain_errors(
    check: dict[str, object],
    label: str,
    method_key: str | None,
    reviewed_paths: set[str] | None,
) -> tuple[list[str], set[str]]:
    call_chain = check.get("call_chain")
    errors = _validate_cqs_locations(call_chain, f"{label}.call_chain", reviewed_paths)
    locations = call_chain if isinstance(call_chain, list) else []
    chain_keys = {_symbol_location_key(location) for location in locations}
    chain_keys.discard(None)
    if method_key is not None and locations and _symbol_location_key(locations[0]) != method_key:
        errors.append(f"{label}.call_chain must start with method")
    return errors, {str(key) for key in chain_keys}


def _cqs_evidence_errors(
    check: dict[str, object],
    label: str,
    reviewed_paths: set[str] | None,
    call_chain_keys: set[str],
) -> tuple[list[str], bool, bool]:
    side_effects = check.get("side_effects")
    callers = check.get("caller_consumption")
    errors = _validate_cqs_entries(
        side_effects, f"{label}.side_effects", ("kind",), reviewed_paths
    )
    errors.extend(
        _validate_cqs_entries(
            callers, f"{label}.caller_consumption", ("use", "evidence"), reviewed_paths
        )
    )
    if not _specific_cqs_text(check.get("return_use")):
        errors.append(f"{label}.return_use must be a non-empty string")
    if isinstance(side_effects, list):
        for effect in side_effects:
            if not isinstance(effect, dict):
                continue
            effect_key = _symbol_location_key(effect.get("location"))
            if effect_key is not None and effect_key not in call_chain_keys:
                errors.append(f"{label}.call_chain must include side-effect location: {effect_key}")
    return errors, isinstance(side_effects, list) and bool(side_effects), isinstance(callers, list) and bool(callers)


def _cqs_finding_errors(
    check: dict[str, object],
    label: str,
    findings_by_id: dict[str, dict[str, object]],
    side_effects: object,
    caller_consumption: object,
) -> tuple[list[str], list[str]]:
    linked_findings = check.get("finding_ids")
    if not isinstance(linked_findings, list):
        return [f"{label}.finding_ids must be a list"], []
    errors: list[str] = []
    valid_ids: list[str] = []
    for finding_id in linked_findings:
        errors.extend(
            _cqs_finding_link_errors(
                finding_id, label, findings_by_id, side_effects, caller_consumption
            )
        )
        if isinstance(finding_id, str) and FINDING_ID.fullmatch(finding_id) and finding_id in findings_by_id:
            valid_ids.append(finding_id)
    return errors, valid_ids


def _cqs_finding_evidence_match_errors(
    finding_id: str,
    finding: dict[str, object],
    label: str,
    side_effects: object,
    caller_consumption: object,
) -> list[str]:
    finding_effects = _cqs_location_keys(finding.get("side_effect_locations"))
    finding_callers = _cqs_location_keys(finding.get("caller_consumption_locations"))
    expected_effects = _cqs_entry_location_keys(side_effects)
    expected_callers = _cqs_entry_location_keys(caller_consumption)
    errors: list[str] = []
    if not expected_effects.issubset(finding_effects):
        errors.append(f"{label}.finding {finding_id} must cite every side-effect location")
    if not expected_callers.issubset(finding_callers):
        errors.append(f"{label}.finding {finding_id} must cite every caller-consumption location")
    return errors


def _cqs_finding_link_errors(
    finding_id: object,
    label: str,
    findings_by_id: dict[str, dict[str, object]],
    side_effects: object,
    caller_consumption: object,
) -> list[str]:
    if not isinstance(finding_id, str) or not FINDING_ID.fullmatch(finding_id):
        return [f"{label}.finding_ids entries must match QF-<three or more digits>"]
    finding = findings_by_id.get(finding_id)
    if finding is None:
        return [f"{label}.finding_ids references unknown finding: {finding_id}"]
    if finding.get("source") != "clean-code-guard" or str(finding.get("rule")) != "4":
        return [f"{label}.finding_ids must reference clean-code-guard rule 4: {finding_id}"]
    return _cqs_finding_evidence_match_errors(
        finding_id, finding, label, side_effects, caller_consumption
    )


def _cqs_status_errors(
    check: dict[str, object],
    label: str,
    has_side_effects: bool,
    has_callers: bool,
    linked_findings: list[str],
    findings_by_id: dict[str, dict[str, object]],
) -> list[str]:
    status = check.get("status")
    if not isinstance(status, str) or status not in CQS_STATUS:
        return [f"{label}.status must be one of {sorted(CQS_STATUS)}"]
    if status == "clear":
        errors = []
        if has_side_effects:
            errors.append(f"{label}.status clear cannot contain side_effects")
        if linked_findings:
            errors.append(f"{label}.status clear cannot link findings")
        return errors
    required = []
    if not has_side_effects:
        required.append(f"{label}.status {status} requires side_effects")
    if not has_callers:
        required.append(f"{label}.status {status} requires caller_consumption evidence")
    if not linked_findings:
        required.append(f"{label}.status {status} requires finding_ids")
    if status == "finding":
        required.extend(
            f"{label}.status finding cannot link exception finding: {finding_id}"
            for finding_id in linked_findings
            if finding_id in findings_by_id and findings_by_id[finding_id].get("status") == "exception"
        )
    if status == "exception":
        required.extend(_cqs_exception_errors(label, linked_findings, findings_by_id))
    return required


def _cqs_exception_errors(
    label: str,
    linked_findings: list[str],
    findings_by_id: dict[str, dict[str, object]],
) -> list[str]:
    return [
        f"{label}.status exception requires exception findings: {finding_id}"
        for finding_id in linked_findings
        if finding_id in findings_by_id and findings_by_id[finding_id].get("status") != "exception"
    ]


def _cqs_linked_ids(checks: list[object]) -> set[str]:
    linked_ids: set[str] = set()
    for check in checks:
        if not isinstance(check, dict) or not isinstance(check.get("finding_ids"), list):
            continue
        linked_ids.update(
            finding_id for finding_id in check["finding_ids"] if isinstance(finding_id, str)
        )
    return linked_ids


def _cqs_check_errors(
    check: object,
    index: int,
    reviewed_paths: set[str] | None,
    seen_methods: set[str],
    findings_by_id: dict[str, dict[str, object]],
) -> list[str]:
    label = f"cqs_checks[{index}]"
    if not isinstance(check, dict):
        return [f"{label} must be an object"]
    errors, method_key = _cqs_method_errors(check, label, reviewed_paths, seen_methods)
    chain_errors, chain_keys = _cqs_chain_errors(check, label, method_key, reviewed_paths)
    evidence_errors, has_effects, has_callers = _cqs_evidence_errors(
        check, label, reviewed_paths, chain_keys
    )
    finding_errors, linked_findings = _cqs_finding_errors(
        check, label, findings_by_id, check.get("side_effects"), check.get("caller_consumption")
    )
    return [
        *errors,
        *chain_errors,
        *evidence_errors,
        *finding_errors,
        *_cqs_status_errors(check, label, has_effects, has_callers, linked_findings, findings_by_id),
    ]


def _cqs_errors(
    checks: object,
    not_applicable: object,
    reviewed_paths: set[str] | None,
    findings_by_id: dict[str, dict[str, object]],
) -> list[str]:
    if not isinstance(checks, list):
        return ["cqs_checks must be a list"]
    if not checks:
        errors = _validate_cqs_not_applicable(not_applicable)
        if any(
            finding.get("source") == "clean-code-guard" and str(finding.get("rule")) == "4"
            for finding in findings_by_id.values()
        ):
            errors.append("cqs_checks cannot be empty when a clean-code-guard rule 4 finding exists")
        return errors
    if not_applicable is not None:
        return ["cqs_not_applicable is only allowed when cqs_checks is empty"]
    seen_methods: set[str] = set()
    errors = [
        error
        for index, check in enumerate(checks)
        for error in _cqs_check_errors(check, index, reviewed_paths, seen_methods, findings_by_id)
    ]
    linked_ids = _cqs_linked_ids(checks)
    errors.extend(
        f"clean-code-guard rule 4 finding is not linked from cqs_checks: {finding_id}"
        for finding_id, finding in findings_by_id.items()
        if finding.get("source") == "clean-code-guard"
        and str(finding.get("rule")) == "4"
        and finding_id not in linked_ids
    )
    return errors


def _validate_exception(finding_id: str, exception: object) -> list[str]:
    if not isinstance(exception, dict):
        return [f"{finding_id} exception status needs an exception object"]
    required = ("reason", "facts", "revisit_trigger")
    return [
        f"{finding_id} exception.{field} must be a non-empty string"
        for field in required
        if not _non_empty_string(exception.get(field))
    ]


def _finding_identity(finding: dict[str, object], label: str) -> tuple[str, list[str]]:
    finding_id = finding.get("id")
    if _non_empty_string(finding_id) and FINDING_ID.fullmatch(finding_id):
        return str(finding_id), []
    return label, [f"{label}.id must match QF-<three or more digits>"]


def _common_finding_errors(finding: dict[str, object], finding_id: str) -> list[str]:
    errors: list[str] = []
    for field in ("source", "rule", "location", "evidence"):
        if not _non_empty_string(finding.get(field)):
            errors.append(f"{finding_id}.{field} must be a non-empty string")
    location = finding.get("location")
    if _non_empty_string(location) and not _valid_symbol_location(location):
        errors.append(f"{finding_id}.location must use path:line#symbol or path#symbol")
    errors.extend(_validate_scope(finding.get("allowed_scope"), f"{finding_id}.allowed_scope"))
    return errors


def _control_flow_review_errors(finding: dict[str, object], finding_id: str) -> list[str]:
    """Validate the dedicated clean-code review rule for control-flow endpoints.

    Rule 21 is intentionally a Review finding rather than a regex finding: the
    reviewer must explain the concrete method and control-flow endpoint. Keep
    the source and location contract strict so a differently sourced or vague
    finding cannot silently satisfy the required review.
    """
    if str(finding.get("rule")) != CONTROL_FLOW_REVIEW_RULE:
        return []
    errors: list[str] = []
    if finding.get("source") != "clean-code-guard":
        errors.append(f"{finding_id}.source must be clean-code-guard for rule {CONTROL_FLOW_REVIEW_RULE}")
    location = finding.get("location")
    if not isinstance(location, str) or re.search(r":[1-9]\d*#\S+$", location) is None:
        errors.append(
            f"{finding_id}.location must include a concrete path:line#symbol for rule {CONTROL_FLOW_REVIEW_RULE}"
        )
    if not _specific_cqs_text(finding.get("evidence")):
        errors.append(f"{finding_id}.evidence must describe the concrete control-flow issue")
    return errors


def _repair_group_errors(finding: dict[str, object], finding_id: str) -> list[str]:
    repair_group = finding.get("repair_group")
    if _non_empty_string(repair_group) and REPAIR_GROUP_ID.fullmatch(repair_group):
        return []
    return [f"{finding_id}.repair_group must match QG-<three or more digits>"]


def _review_scope_errors(
    finding: dict[str, object],
    finding_id: str,
    reviewed_paths: set[str] | None,
) -> list[str]:
    if reviewed_paths is None:
        return []
    locations = [("location", finding.get("location"))]
    allowed_scope = finding.get("allowed_scope")
    if isinstance(allowed_scope, list):
        locations.extend(("allowed_scope", entry) for entry in allowed_scope)
    return [
        f"{finding_id}.{field} path must be included in reviewed_paths: {path}"
        for field, location in locations
        if (path := _symbol_path(location)) is not None and path not in reviewed_paths
    ]


def _status_errors(finding: dict[str, object], finding_id: str) -> list[str]:
    errors: list[str] = []
    if finding.get("severity") != "blocking":
        errors.append(f"{finding_id}.severity must be blocking")
    status = finding.get("status")
    if not isinstance(status, str) or status not in ALLOWED_STATUS:
        errors.append(f"{finding_id}.status must be one of {sorted(ALLOWED_STATUS)}")
    return errors


def _attempt_errors(finding: dict[str, object], finding_id: str) -> list[str]:
    attempts = finding.get("attempts")
    if isinstance(attempts, bool) or not isinstance(attempts, int) or not 0 <= attempts <= MAX_REPAIR_ATTEMPTS:
        return [f"{finding_id}.attempts must be an integer from 0 to {MAX_REPAIR_ATTEMPTS}"]
    if finding.get("status") == "fixed" and attempts == 0:
        return [f"{finding_id}.attempts must be at least 1 when fixed"]
    return []


def _resolution_errors(finding: dict[str, object], finding_id: str) -> list[str]:
    if finding.get("status") == "exception":
        return _validate_exception(finding_id, finding.get("exception"))
    if finding.get("status") != "fixed":
        return []
    return [
        f"{finding_id}.{field} must be a non-empty string when fixed"
        for field in ("resolution", "verification")
        if not _non_empty_string(finding.get(field))
    ]


def _validate_finding(
    finding: object,
    index: int,
    reviewed_paths: set[str] | None,
) -> list[str]:
    label = f"finding[{index}]"
    if not isinstance(finding, dict):
        return [f"{label} must be an object"]
    finding_id, errors = _finding_identity(finding, label)
    errors.extend(_common_finding_errors(finding, finding_id))
    errors.extend(_control_flow_review_errors(finding, finding_id))
    errors.extend(_repair_group_errors(finding, finding_id))
    errors.extend(_review_scope_errors(finding, finding_id, reviewed_paths))
    errors.extend(_validate_cqs_finding_evidence(finding, finding_id, reviewed_paths))
    errors.extend(_status_errors(finding, finding_id))
    errors.extend(_attempt_errors(finding, finding_id))
    errors.extend(_resolution_errors(finding, finding_id))
    return errors


def _reviewed_paths(payload: dict[str, object]) -> tuple[list[str], list[str]]:
    paths = payload.get("reviewed_paths")
    if not isinstance(paths, list) or not paths or any(not _repository_relative_path(path) for path in paths):
        return [], ["reviewed_paths must be a non-empty list of repository-relative paths"]
    if len(paths) != len(set(paths)):
        return paths, ["reviewed_paths must not contain duplicates"]
    return paths, []


def _finding_id_errors(finding_ids: list[str]) -> list[str]:
    duplicates = sorted({finding_id for finding_id in finding_ids if finding_ids.count(finding_id) > 1})
    if duplicates:
        return [f"duplicate finding IDs: {duplicates}"]
    expected_ids = [f"QF-{index:03d}" for index in range(1, len(finding_ids) + 1)]
    return [] if finding_ids == expected_ids else ["finding IDs must be consecutive in QF-001 order"]


def _repair_group_consistency_errors(findings: list[object]) -> list[str]:
    attempts_by_group: dict[str, set[int]] = {}
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        repair_group = finding.get("repair_group")
        attempts = finding.get("attempts")
        if _non_empty_string(repair_group) and isinstance(attempts, int) and not isinstance(attempts, bool):
            attempts_by_group.setdefault(str(repair_group), set()).add(attempts)
    return [
        f"{repair_group} must use one shared repair-attempt count"
        for repair_group, attempts in attempts_by_group.items()
        if len(attempts) > 1
    ]


def _findings_errors(findings: list[object], reviewed_paths: set[str] | None) -> list[str]:
    errors = [
        error
        for index, finding in enumerate(findings)
        for error in _validate_finding(finding, index, reviewed_paths)
    ]
    finding_ids = [
        finding["id"]
        for finding in findings
        if isinstance(finding, dict) and _non_empty_string(finding.get("id"))
    ]
    return [*errors, *_finding_id_errors(finding_ids), *_repair_group_consistency_errors(findings)]


def _open_finding_errors(findings: list[object]) -> list[str]:
    open_ids = [
        finding.get("id", f"finding[{index}]")
        for index, finding in enumerate(findings)
        if isinstance(finding, dict) and finding.get("status") == "open"
    ]
    return [f"blocking findings remain open: {open_ids}"] if open_ids else []


def _type_check_links(check: dict[str, object], label: str, findings: dict[str, dict[str, object]]) -> list[str]:
    links = check.get("finding_ids")
    if not isinstance(links, list):
        return [f"{label}.finding_ids must be a list"]
    errors = []
    for link in links:
        if not isinstance(link, str) or link not in findings:
            errors.append(f"{label}.finding_ids references unknown finding: {link!r}")
    conclusion = check.get("conclusion")
    if conclusion not in ("necessary", "unnecessary"):
        errors.append(f"{label}.conclusion must be necessary or unnecessary")
    if conclusion == "necessary" and links:
        errors.append(f"{label}.necessary cannot link findings")
    if conclusion == "unnecessary" and not links:
        errors.append(f"{label}.unnecessary requires finding_ids")
    return errors


def _type_check_errors(check: object, label: str, paths: set[str] | None) -> list[str]:
    if not isinstance(check, dict):
        return [f"{label} must be an object"]
    errors = _validate_cqs_locations([check.get("type")], f"{label}.type", paths)
    for field in ("responsibility", "necessity_evidence", "caller_usage", "deletion_impact", "wrapper_assessment", "contract_constraints"):
        if not _specific_cqs_text(check.get(field)):
            errors.append(f"{label}.{field} must contain specific evidence")
    callers = check.get("caller_locations")
    if callers == []:
        if not _specific_cqs_text(check.get("no_callers_evidence")):
            errors.append(f"{label}.no_callers_evidence is required when caller_locations is empty")
    else:
        errors.extend(_validate_cqs_locations(callers, f"{label}.caller_locations", paths))
    return errors


def _type_necessity_errors(payload: dict[str, object], paths: set[str] | None,
                           findings: dict[str, dict[str, object]]) -> list[str]:
    checks = payload.get("type_necessity_checks")
    if not isinstance(checks, list):
        return ["type_necessity_checks must be a list"]
    if not checks:
        reason = payload.get("type_necessity_not_applicable")
        if not _specific_cqs_text(reason):
            return ["type_necessity_not_applicable must explain why no types apply"]
        return []
    errors = []
    if "type_necessity_not_applicable" in payload:
        errors.append("type_necessity_not_applicable is only allowed when type_necessity_checks is empty")
    seen = set()
    for index, check in enumerate(checks):
        label = f"type_necessity_checks[{index}]"
        errors.extend(_type_check_errors(check, label, paths))
        if not isinstance(check, dict):
            continue
        key = _symbol_location_key(check.get("type"))
        if key is not None and key in seen:
            errors.append(f"duplicate type necessity check: {key}")
        seen.add(key)
        errors.extend(_type_check_links(check, label, findings))
    return errors


def validate(
    payload: object,
    expected_paths: Sequence[str] = (),
) -> list[str]:
    if not isinstance(payload, dict):
        return ["review document must be a JSON object"]

    errors = [] if payload.get("review_type") == "full-discovery" else ["review_type must be full-discovery"]
    if payload.get("full_review_count") != 1:
        errors.append("full_review_count must be exactly 1")
    reviewed_paths, path_errors = _reviewed_paths(payload)
    errors.extend(path_errors)
    if expected_paths and set(reviewed_paths) != set(expected_paths):
        errors.append("reviewed_paths do not match the requested affected paths")
    findings = payload.get("findings")
    if not isinstance(findings, list):
        return [*errors, "findings must be a list"]
    reviewed_path_set = None if path_errors else set(reviewed_paths)
    findings_by_id = {
        str(finding.get("id")): finding
        for finding in findings
        if isinstance(finding, dict) and _non_empty_string(finding.get("id"))
    }
    return [
        *errors,
        *_findings_errors(findings, reviewed_path_set),
        *_type_necessity_errors(payload, reviewed_path_set, findings_by_id),
        *_cqs_errors(
            payload.get("cqs_checks"),
            payload.get("cqs_not_applicable"),
            reviewed_path_set,
            findings_by_id,
        ),
    ]


def validate_closed(payload: object, expected_paths: Sequence[str] = ()) -> list[str]:
    errors = validate(payload, expected_paths)
    if not isinstance(payload, dict) or not isinstance(payload.get("findings"), list):
        return errors
    return [*errors, *_open_finding_errors(payload["findings"])]


def summary(payload: dict[str, Any]) -> str:
    findings = payload.get("findings", [])
    statuses = [finding.get("status") for finding in findings if isinstance(finding, dict)]
    return (
        f"clean-code-guard found={len(findings)} "
        f"fixed={statuses.count('fixed')} "
        f"exception={statuses.count('exception')} "
        f"open={statuses.count('open')}"
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="临时质量 Review JSON 文件")
    parser.add_argument(
        "--path",
        action="append",
        required=True,
        help="全量发现 Review 应覆盖的受影响或明确授权文件；每个文件重复传入",
    )
    parser.add_argument("--require-closed", action="store_true", help="存在 open finding 时失败")
    return parser


def _read_review(review_file: Path) -> dict[str, Any]:
    payload = json.loads(review_file.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("review document must be a JSON object")
    return payload


def _print_errors(errors: Sequence[str]) -> None:
    for error in errors:
        print(f"error: {error}", file=sys.stderr)


def main(arguments: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(arguments)
    try:
        payload = _read_review(args.file)
    except (OSError, ValueError) as error:
        print(f"Quality Review Gate: unable to read review: {error}", file=sys.stderr)
        return 2
    review_validator = validate_closed if args.require_closed else validate
    errors = review_validator(payload, args.path)
    if errors:
        _print_errors(errors)
        return 1
    print(summary(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
