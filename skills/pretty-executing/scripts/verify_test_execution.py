#!/usr/bin/env python3
"""Verify target tests are enabled and actually executed in fresh JUnit XML reports."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Mapping, Sequence
from xml.etree import ElementTree

COMMON_SCRIPTS = Path(__file__).resolve().parents[2] / "pretty-common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

from disabled_test_scope import repository_meta_disabled_names, scan_paths, targeted_findings  # type: ignore[import-not-found]
from candidate_contract import quality_bundle_sha256, run_git  # type: ignore[import-not-found]
from evidence_binding import evidence_sha256, file_sha256, self_bound_sha256  # type: ignore[import-not-found]
from pretty_tmp import topic_dir_for_document, validate_artifact_path, validate_run_dir  # type: ignore[import-not-found]


@dataclass(frozen=True)
class TestExecutionRequest:
    repo: Path
    test_sources: Sequence[str]
    expected_tests: Sequence[str]
    reports: Sequence[Path]
    report_not_before: float
    new_test_sources: Sequence[str] = ()
    design_sha256: str | None = None
    quality_candidate_sha256: str | None = None
    start_head: str | None = None
    execution_matrix_sha256: str | None = None
    resolver_sha256: str | None = None
    shared_bundle_sha256: str | None = None
    scope: str = "final"
    slice_id: str | None = None


def _safe_relative_path(relative_path: str) -> bool:
    path = PurePosixPath(relative_path)
    return not path.is_absolute() and ".." not in path.parts and "\\" not in relative_path


def scan_disabled_annotations(repo: Path, paths: Sequence[str]) -> list[dict[str, object]]:
    for relative_path in sorted(set(paths)):
        if not _safe_relative_path(relative_path):
            raise ValueError(f"test source path must be repository-relative: {relative_path}")
    return scan_paths(repo, paths)


def _testcases(report: Path) -> tuple[list[dict[str, object]], list[str]]:
    root = ElementTree.parse(report).getroot()
    cases, errors = [], []
    suites = [root] if root.tag.endswith("testsuite") else list(root.iter("testsuite"))
    for suite in suites:
        failures = int(suite.attrib.get("failures", "0") or 0)
        suite_errors = int(suite.attrib.get("errors", "0") or 0)
        if failures or suite_errors:
            errors.append(
                f"JUnit suite reports failures/errors in {report}: "
                f"{suite.attrib.get('name', '<unnamed>')} ({failures}/{suite_errors})"
            )
    for testcase in root.iter("testcase"):
        classname = testcase.attrib.get("classname", "")
        name = testcase.attrib.get("name", "")
        skipped = testcase.find("skipped") is not None
        failed = testcase.find("failure") is not None or testcase.find("error") is not None
        cases.append({"classname": classname, "name": name, "skipped": skipped, "failed": failed})
    return cases, errors


def _matches(case: Mapping[str, object], expected: str) -> bool:
    classname, separator, method = expected.partition("#")
    actual_class = str(case.get("classname", ""))
    if actual_class != classname and not actual_class.endswith(f".{classname}"):
        return False
    if not separator:
        return True
    actual_method = str(case.get("name", ""))
    return actual_method == method or actual_method.startswith(f"{method}(") or actual_method.startswith(f"{method}[")


def verify_expected_tests(
    reports: Sequence[Path], expected_tests: Sequence[str]
) -> tuple[list[dict[str, object]], list[str]]:
    cases, errors = [], []
    for report in reports:
        report_cases, report_errors = _testcases(report)
        cases.extend(report_cases)
        errors.extend(report_errors)
    executed = []
    for expected in expected_tests:
        matches = [case for case in cases if _matches(case, expected)]
        if not matches:
            errors.append(f"expected test did not execute: {expected}")
        elif any(case["skipped"] or case["failed"] for case in matches):
            errors.append(f"expected test has a skipped or failed invocation: {expected}")
        else:
            executed.extend({"expected": expected, **case} for case in matches)
    return executed, errors


def verify(request: TestExecutionRequest) -> dict[str, object]:
    executable_reports, errors = _fresh_reports(request)
    errors.extend(_missing_test_source_errors(request))
    disabled = scan_disabled_annotations(request.repo, request.test_sources)
    new_disabled = []
    meta_names = repository_meta_disabled_names(request.repo)
    for relative_path in sorted(set(request.new_test_sources)):
        source_path = request.repo / relative_path
        if not source_path.is_file():
            continue
        for finding in targeted_findings(
            source_path.read_text(encoding="utf-8"),
            request.expected_tests,
            meta_names,
        ):
            new_disabled.append({"path": relative_path, **finding})
    errors.extend(
        "new test source is inside a disabled or conditionally disabled scope: "
        f"{finding['path']}:{finding['line']}"
        for finding in new_disabled
    )
    executed, execution_errors = _verify_execution(request.expected_tests, executable_reports)
    errors.extend(execution_errors)
    source_hashes = _test_source_hashes(request)
    status = "fail" if errors else "not_applicable" if not request.expected_tests else "pass"
    payload = {
        "quality_candidate_sha256": request.quality_candidate_sha256,
        "design_sha256": request.design_sha256,
        "start_head": request.start_head,
        "execution_matrix_sha256": request.execution_matrix_sha256,
        "resolver_sha256": request.resolver_sha256,
        "shared_bundle_sha256": request.shared_bundle_sha256,
        "scope": request.scope,
        "slice_id": request.slice_id if request.scope == "slice" else None,
        "source_sha256": source_hashes,
        "reports": [str(path) for path in executable_reports],
        "expected_tests": list(request.expected_tests),
        "executed_tests": executed,
        "disabled_annotations": disabled,
        "status": status,
        "passed": status in {"pass", "not_applicable"},
        "errors": errors,
        "generated_at": time.time(),
    }
    payload["candidate_sha256"] = self_bound_sha256(payload)
    payload["evidence_sha256"] = evidence_sha256(payload)
    return payload


def _missing_test_source_errors(request: TestExecutionRequest) -> list[str]:
    paths = set(request.test_sources) | set(request.new_test_sources)
    return [
        f"target test source does not exist: {path}"
        for path in sorted(paths)
        if not (request.repo / path).is_file()
    ]


def _fresh_reports(request: TestExecutionRequest) -> tuple[list[Path], list[str]]:
    reports = [path if path.is_absolute() else request.repo / path for path in request.reports]
    source_paths = [
        request.repo / path
        for path in set(request.test_sources) | set(request.new_test_sources)
        if (request.repo / path).is_file()
    ]
    source_mtime = max((path.stat().st_mtime for path in source_paths), default=None)
    errors = []
    for report in reports:
        if not report.is_file():
            errors.append(f"test report does not exist: {report}")
        elif report.stat().st_mtime < request.report_not_before:
            errors.append(f"test report is stale: {report}")
        elif source_mtime is not None and report.stat().st_mtime <= source_mtime:
            errors.append(f"test report is stale: {report}")
    fresh = [
        report for report in reports
        if report.is_file()
        and report.stat().st_mtime >= request.report_not_before
        and (source_mtime is None or report.stat().st_mtime > source_mtime)
    ]
    return fresh, errors


def _verify_execution(
    expected_tests: Sequence[str], reports: Sequence[Path]
) -> tuple[list[dict[str, object]], list[str]]:
    if not expected_tests:
        return [], []
    if not reports:
        return [], ["fresh JUnit XML report is required for changed tests"]
    try:
        return verify_expected_tests(reports, expected_tests)
    except ElementTree.ParseError as error:
        return [], [f"invalid JUnit XML report: {error}"]


def _test_source_hashes(request: TestExecutionRequest) -> dict[str, str]:
    return {
        path: file_sha256(request.repo / path)
        for path in sorted(set(request.test_sources) | set(request.new_test_sources))
        if (request.repo / path).is_file()
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--test-source", action="append", default=[])
    parser.add_argument("--new-test-source", action="append", default=[])
    parser.add_argument("--expected-test", action="append", default=[])
    parser.add_argument("--report", action="append", type=Path, default=[])
    parser.add_argument("--report-not-before", type=float, required=True)
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--execution-matrix", type=Path, required=True)
    parser.add_argument("--resolver", type=Path, required=True)
    parser.add_argument("--scope", choices=("slice", "final"), required=True)
    parser.add_argument("--slice-id")
    parser.add_argument("--quality-candidate-sha256", required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(arguments)
    try:
        repo = args.repo.resolve()
        design = args.design if args.design.is_absolute() else repo / args.design
        matrix = args.execution_matrix if args.execution_matrix.is_absolute() else repo / args.execution_matrix
        resolver = args.resolver if args.resolver.is_absolute() else repo / args.resolver
        output = args.json_output if args.json_output.is_absolute() else repo / args.json_output
        topic_dir = topic_dir_for_document(design)
        run_dir = validate_run_dir(topic_dir, output.parent)
        output = validate_artifact_path(run_dir, output)
        validate_artifact_path(run_dir, matrix)
        validate_artifact_path(run_dir, resolver)
        if args.scope == "slice" and not args.slice_id:
            raise ValueError("slice scope requires --slice-id")
        if args.scope == "final" and args.slice_id:
            raise ValueError("final scope does not accept --slice-id")
        start_head = str(run_git(repo, ["rev-parse", "--verify", f"{args.base}^{{commit}}"])).strip()
        payload = verify(TestExecutionRequest(
            repo=repo,
            test_sources=args.test_source,
            expected_tests=args.expected_test,
            reports=args.report,
            report_not_before=args.report_not_before,
            new_test_sources=args.new_test_source,
            design_sha256=file_sha256(design),
            quality_candidate_sha256=args.quality_candidate_sha256,
            start_head=start_head,
            execution_matrix_sha256=file_sha256(matrix),
            resolver_sha256=file_sha256(resolver),
            shared_bundle_sha256=quality_bundle_sha256(),
            scope=args.scope,
            slice_id=args.slice_id,
        ))
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError) as error:
        print(f"test execution verification failed: {error}", file=sys.stderr)
        return 2
    for error in payload["errors"]:
        print(f"error: {error}", file=sys.stderr)
    print(f"Test execution Gate: {payload['status']}")
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
