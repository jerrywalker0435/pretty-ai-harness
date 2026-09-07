#!/usr/bin/env python3
"""Regression tests for the bounded quality-review gate."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from quality_review_gate import main, validate, validate_closed


PRODUCTION_PATH = "src/main/java/example/OrderService.java"


def review_document(findings=None):
    return {
        "review_type": "full-discovery",
        "full_review_count": 1,
        "reviewed_paths": [PRODUCTION_PATH],
        "findings": [] if findings is None else findings,
    }


def fixed_finding():
    return {
        "id": "QF-001",
        "source": "clean-code-guard",
        "rule": "15",
        "severity": "blocking",
        "location": f"{PRODUCTION_PATH}:42#loadOrder",
        "evidence": "broad catch returns null",
        "allowed_scope": [f"{PRODUCTION_PATH}#loadOrder"],
        "repair_group": "QG-001",
        "status": "fixed",
        "attempts": 1,
        "resolution": "propagate the repository failure",
        "verification": "targeted test passed",
    }


class QualityReviewGateTest(unittest.TestCase):
    def test_closed_review_with_no_findings_is_valid(self):
        self.assertEqual([], validate_closed(review_document(), [PRODUCTION_PATH]))

    def test_open_finding_blocks_closed_review(self):
        finding = fixed_finding()
        finding.update(status="open", attempts=2)

        errors = validate_closed(review_document([finding]), [PRODUCTION_PATH])

        self.assertIn("blocking findings remain open", " ".join(errors))

    def test_fixed_finding_requires_resolution_and_verification(self):
        finding = fixed_finding()
        finding.pop("resolution")
        finding.pop("verification")

        errors = validate(review_document([finding]))

        self.assertIn("QF-001.resolution", " ".join(errors))
        self.assertIn("QF-001.verification", " ".join(errors))

    def test_exception_requires_contract_evidence(self):
        finding = fixed_finding()
        finding.update(status="exception", attempts=0, exception={"reason": "legacy"})

        errors = validate(review_document([finding]))

        self.assertIn("exception.facts", " ".join(errors))
        self.assertIn("exception.revisit_trigger", " ".join(errors))

    def test_contract_backed_exception_closes_review(self):
        finding = fixed_finding()
        finding.update(
            status="exception",
            attempts=0,
            exception={
                "reason": "external signature cannot change",
                "facts": "published interface and compatibility test",
                "revisit_trigger": "next major API version",
            },
        )

        self.assertEqual([], validate_closed(review_document([finding]), [PRODUCTION_PATH]))

    def test_repair_attempts_are_bounded(self):
        finding = fixed_finding()
        finding["attempts"] = 3

        self.assertIn("integer from 0 to 2", " ".join(validate(review_document([finding]))))

    def test_reviewed_paths_must_match_requested_scope(self):
        errors = validate_closed(review_document(), ["src/main/java/example/Other.java"])

        self.assertIn("reviewed_paths do not match", " ".join(errors))

    def test_reviewed_paths_reject_repository_root(self):
        document = review_document()
        document["reviewed_paths"] = ["."]

        self.assertIn("repository-relative paths", " ".join(validate(document)))

    def test_finding_and_repair_scope_must_stay_in_reviewed_paths(self):
        finding = fixed_finding()
        finding["location"] = "src/main/java/example/Other.java:10#loadOrder"
        finding["allowed_scope"] = ["src/main/java/example/Other.java#loadOrder"]

        errors = validate(review_document([finding]))

        self.assertIn("location path must be included in reviewed_paths", " ".join(errors))
        self.assertIn("allowed_scope path must be included in reviewed_paths", " ".join(errors))

    def test_repair_group_uses_one_shared_attempt_count(self):
        first = fixed_finding()
        second = fixed_finding()
        second.update(id="QF-002", attempts=2)

        errors = validate(review_document([first, second]))

        self.assertIn("QG-001 must use one shared repair-attempt count", errors)

    def test_duplicate_finding_ids_are_rejected(self):
        errors = validate(review_document([fixed_finding(), fixed_finding()]))

        self.assertIn("duplicate finding IDs", " ".join(errors))

    def test_full_review_must_be_recorded_once(self):
        document = review_document()
        document["full_review_count"] = 2

        self.assertIn("full_review_count must be exactly 1", validate(document))

    def test_cli_emits_execution_summary_for_closed_review(self):
        with tempfile.TemporaryDirectory() as directory:
            review_file = Path(directory) / "quality-review.json"
            review_file.write_text(json.dumps(review_document([fixed_finding()])), encoding="utf-8")
            standard_output = StringIO()
            with redirect_stdout(standard_output), redirect_stderr(StringIO()):
                exit_code = main([
                    str(review_file),
                    "--path", PRODUCTION_PATH,
                    "--require-closed",
                ])

        self.assertEqual(0, exit_code)
        self.assertEqual(
            "clean-code-guard found=1 fixed=1 exception=0 open=0",
            standard_output.getvalue().strip(),
        )

    def test_cli_blocks_open_review(self):
        finding = fixed_finding()
        finding.update(status="open", attempts=2)
        with tempfile.TemporaryDirectory() as directory:
            review_file = Path(directory) / "quality-review.json"
            review_file.write_text(json.dumps(review_document([finding])), encoding="utf-8")
            standard_error = StringIO()
            with redirect_stdout(StringIO()), redirect_stderr(standard_error):
                exit_code = main([
                    str(review_file),
                    "--path", PRODUCTION_PATH,
                    "--require-closed",
                ])

        self.assertEqual(1, exit_code)
        self.assertIn("blocking findings remain open", standard_error.getvalue())


if __name__ == "__main__":
    unittest.main()
