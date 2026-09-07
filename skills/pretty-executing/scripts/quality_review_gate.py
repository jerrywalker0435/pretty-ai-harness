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
ALLOWED_STATUS = {"fixed", "exception", "open"}


def _non_empty_string(candidate_text: object) -> bool:
    return isinstance(candidate_text, str) and bool(candidate_text.strip())


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
    if status not in ALLOWED_STATUS:
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
    errors.extend(_repair_group_errors(finding, finding_id))
    errors.extend(_review_scope_errors(finding, finding_id, reviewed_paths))
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
    return [*errors, *_findings_errors(findings, reviewed_path_set)]


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
