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
        "routes_applied": ["clean-code-guard"],
        "reviewed_paths": [PRODUCTION_PATH],
        "type_necessity_checks": [],
        "type_necessity_not_applicable": "only method bodies changed; no new types or changed type responsibilities",
        "cqs_checks": [],
        "cqs_not_applicable": {
            "reason": "no changed non-void production methods",
            "facts": "the affected file contains only a data carrier",
        },
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
    def type_review(self, conclusion="necessary", findings=None):
        document = review_document(findings)
        document.pop("type_necessity_not_applicable")
        document["type_necessity_checks"] = [{
            "type": f"{PRODUCTION_PATH}:10#OrderRequest",
            "caller_locations": [f"{PRODUCTION_PATH}:20#submit"],
            "responsibility": "two-field request DTO for the published API",
            "necessity_evidence": "the serializer binds this DTO to the published request schema",
            "caller_usage": "one controller reads both fields to invoke the service",
            "deletion_impact": "removing the DTO breaks the published request schema binding",
            "wrapper_assessment": "data carrier with a required protocol contract",
            "contract_constraints": "published API schema requires this request shape",
            "conclusion": conclusion,
            "finding_ids": [] if findings is None else [finding["id"] for finding in findings],
        }]
        return document

    def test_type_review_requires_records_or_explicit_non_applicability(self):
        document = review_document()
        document.pop("type_necessity_checks")
        self.assertIn("type_necessity_checks must be a list", validate(document))
        document["type_necessity_checks"] = []
        document.pop("type_necessity_not_applicable")
        self.assertTrue(validate(document))

    def test_two_field_dto_with_one_caller_can_pass(self):
        self.assertEqual([], validate_closed(self.type_review()))

    def test_value_object_and_single_implementation_port_can_pass(self):
        for responsibility, evidence, impact in (
            ("two-field Money value object", "constructor enforces amount and currency consistency",
             "removal duplicates currency validation in consumers"),
            ("single implementation query port", "domain owns the query contract consumed by application",
             "removal introduces a domain dependency on infrastructure"),
        ):
            with self.subTest(responsibility=responsibility):
                document = self.type_review()
                document["type_necessity_checks"][0].update(
                    responsibility=responsibility, necessity_evidence=evidence, deletion_impact=impact)
                self.assertEqual([], validate_closed(document))

    def test_type_review_rejects_placeholders_and_conflicting_declarations(self):
        document = self.type_review()
        document["type_necessity_checks"][0]["deletion_impact"] = "todo"
        self.assertTrue(validate(document))
        document = self.type_review()
        document["type_necessity_not_applicable"] = "no types apply"
        self.assertTrue(validate(document))
        self.assertTrue(validate(self.type_review(findings=[fixed_finding()])))

    def test_malformed_type_records_return_errors(self):
        for value in (None, "unchecked", [], 42):
            with self.subTest(value=value):
                document = self.type_review()
                document["type_necessity_checks"] = [value]
                self.assertTrue(validate(document))
        document = self.type_review()
        document["type_necessity_checks"][0]["finding_ids"] = [{}]
        self.assertTrue(validate(document))

    def test_type_review_requires_each_evidence_field(self):
        for field in ("type", "caller_locations", "responsibility", "necessity_evidence", "caller_usage",
                      "deletion_impact", "wrapper_assessment", "contract_constraints", "conclusion", "finding_ids"):
            with self.subTest(field=field):
                document = self.type_review()
                document["type_necessity_checks"][0].pop(field)
                self.assertTrue(validate(document))

    def test_type_and_caller_locations_must_stay_in_review_scope(self):
        for field, value in (("type", "other.java#Other"), ("caller_locations", ["other.java#call"])):
            with self.subTest(field=field):
                document = self.type_review()
                document["type_necessity_checks"][0][field] = value
                self.assertIn("included in reviewed_paths", " ".join(validate(document)))

    def test_duplicate_types_ignore_line_numbers(self):
        document = self.type_review()
        duplicate = dict(document["type_necessity_checks"][0], type=f"{PRODUCTION_PATH}:99#OrderRequest")
        document["type_necessity_checks"].append(duplicate)
        self.assertIn("duplicate type necessity check", " ".join(validate(document)))

    def test_no_callers_requires_search_or_framework_evidence(self):
        document = self.type_review()
        check = document["type_necessity_checks"][0]
        check["caller_locations"] = []
        self.assertTrue(validate(document))
        check["no_callers_evidence"] = "framework binds the DTO through the registered endpoint schema"
        self.assertEqual([], validate(document))

    def test_unnecessary_type_requires_real_finding_and_open_blocks_delivery(self):
        document = self.type_review("unnecessary")
        self.assertIn("requires finding_ids", " ".join(validate(document)))
        finding = fixed_finding()
        finding.update(status="open", attempts=0, source="122-java-type-design", rule="unnecessary-wrapper")
        document = self.type_review("unnecessary", [finding])
        document["type_necessity_checks"][0]["contract_constraints"] = "Design explicitly specifies this type; deletion awaits user authorization"
        self.assertEqual([], validate(document))
        self.assertIn("blocking findings remain open", " ".join(validate_closed(document)))
        document["type_necessity_checks"][0]["finding_ids"] = ["QF-999"]
        self.assertIn("unknown finding", " ".join(validate(document)))

    def test_repaired_type_retains_original_review_and_closed_finding(self):
        finding = fixed_finding()
        finding.update(source="122-java-type-design", rule="unnecessary-wrapper",
                       resolution="user explicitly authorized deletion; inlined fields into caller")
        self.assertEqual([], validate_closed(self.type_review("unnecessary", [finding])))

    def test_closed_review_with_no_findings_is_valid(self):
        self.assertEqual([], validate_closed(review_document(), [PRODUCTION_PATH]))

    def test_review_requires_routes_applied_receipt(self):
        document = review_document()
        document.pop("routes_applied")
        self.assertIn("routes_applied must be a non-empty list", validate(document))

    def test_review_rejects_duplicate_routes(self):
        document = review_document()
        document["routes_applied"] = ["clean-code-guard", "clean-code-guard"]
        self.assertIn("routes_applied must not contain duplicates", validate(document))

    def test_cqs_checks_are_required(self):
        document = review_document()
        document.pop("cqs_checks")

        self.assertIn("cqs_checks must be a list", validate(document))

    def test_empty_cqs_checks_require_non_applicable_evidence(self):
        document = review_document()
        document.pop("cqs_not_applicable")

        self.assertIn("cqs_not_applicable must include reason and facts", " ".join(validate(document)))

    def test_clear_cqs_check_requires_no_side_effects(self):
        document = review_document()
        document["cqs_checks"] = [{
            "method": f"{PRODUCTION_PATH}:12#loadOrder",
            "call_chain": [f"{PRODUCTION_PATH}:12#loadOrder"],
            "side_effects": [{"kind": "persistence", "location": f"{PRODUCTION_PATH}:18#save"}],
            "caller_consumption": [],
            "return_use": "logged",
            "finding_ids": [],
            "status": "clear",
        }]
        document.pop("cqs_not_applicable")

        errors = validate(document)

        self.assertIn("status clear cannot contain side_effects", " ".join(errors))

    def test_cqs_finding_requires_callers_and_rule_four_finding(self):
        document = review_document([fixed_finding()])
        document["cqs_checks"] = [{
            "method": f"{PRODUCTION_PATH}:12#save",
            "call_chain": [f"{PRODUCTION_PATH}:12#save", f"{PRODUCTION_PATH}:18#insert"],
            "side_effects": [{"kind": "persistence", "location": f"{PRODUCTION_PATH}:18#insert"}],
            "caller_consumption": [],
            "return_use": "discarded",
            "finding_ids": ["QF-001"],
            "status": "finding",
        }]
        document.pop("cqs_not_applicable")

        errors = validate(document)

        self.assertIn("requires caller_consumption evidence", " ".join(errors))
        self.assertIn("must reference clean-code-guard rule 4", " ".join(errors))

    def test_valid_cqs_finding_links_rule_four_finding(self):
        finding = fixed_finding()
        finding.update(
            rule="4",
            location=f"{PRODUCTION_PATH}:12#save",
            side_effect_locations=[f"{PRODUCTION_PATH}:18#insert"],
            caller_consumption_locations=[f"{PRODUCTION_PATH}:30#create"],
        )
        document = review_document([finding])
        document["cqs_checks"] = [{
            "method": f"{PRODUCTION_PATH}:12#save",
            "call_chain": [f"{PRODUCTION_PATH}:12#save", f"{PRODUCTION_PATH}:18#insert"],
            "side_effects": [{"kind": "persistence", "location": f"{PRODUCTION_PATH}:18#insert"}],
            "caller_consumption": [{
                "location": f"{PRODUCTION_PATH}:30#create",
                "use": "discarded",
                "evidence": "caller ignores the returned execution result",
            }],
            "return_use": "discarded",
            "finding_ids": ["QF-001"],
            "status": "finding",
        }]
        document.pop("cqs_not_applicable")

        self.assertEqual([], validate_closed(document, [PRODUCTION_PATH]))

    def test_cqs_exception_requires_exception_finding(self):
        finding = fixed_finding()
        finding.update(
            rule="4",
            location=f"{PRODUCTION_PATH}:12#save",
            side_effect_locations=[f"{PRODUCTION_PATH}:18#insert"],
            caller_consumption_locations=[f"{PRODUCTION_PATH}:30#create"],
        )
        document = review_document([finding])
        document["cqs_checks"] = [{
            "method": f"{PRODUCTION_PATH}:12#save",
            "call_chain": [f"{PRODUCTION_PATH}:12#save", f"{PRODUCTION_PATH}:18#insert"],
            "side_effects": [{"kind": "persistence", "location": f"{PRODUCTION_PATH}:18#insert"}],
            "caller_consumption": [{
                "location": f"{PRODUCTION_PATH}:30#create",
                "use": "discarded",
                "evidence": "caller ignores the returned execution result",
            }],
            "return_use": "discarded",
            "finding_ids": ["QF-001"],
            "status": "exception",
        }]
        document.pop("cqs_not_applicable")

        self.assertIn("requires exception findings", " ".join(validate(document)))

    def test_rule_four_finding_requires_both_evidence_location_lists(self):
        finding = fixed_finding()
        finding.update(rule="4")
        document = review_document([finding])

        errors = validate(document)

        joined_errors = " ".join(errors)
        self.assertIn("side_effect_locations", joined_errors)
        self.assertIn("caller_consumption_locations", joined_errors)

    def test_open_finding_blocks_closed_review(self):
        finding = fixed_finding()
        finding.update(status="open", attempts=2)

        errors = validate_closed(review_document([finding]), [PRODUCTION_PATH])

        self.assertIn("blocking findings remain open", " ".join(errors))

    def test_control_flow_rule_requires_clean_code_guard_source_and_line(self):
        finding = fixed_finding()
        finding.update(
            source="pretty-executing",
            rule="21",
            location=f"{PRODUCTION_PATH}#execute",
            evidence="tail return",
        )

        errors = validate(review_document([finding]))

        joined_errors = " ".join(errors)
        self.assertIn("source must be clean-code-guard for rule 21", joined_errors)
        self.assertIn("path:line#symbol for rule 21", joined_errors)

    def test_valid_closed_control_flow_finding_is_accepted(self):
        finding = fixed_finding()
        finding.update(
            rule="21",
            location=f"{PRODUCTION_PATH}:42#execute",
            evidence="void execute ends with an unconditional return statement",
        )

        self.assertEqual([], validate_closed(review_document([finding]), [PRODUCTION_PATH]))

    def test_open_control_flow_finding_blocks_closed_review(self):
        finding = fixed_finding()
        finding.update(
            rule="21",
            location=f"{PRODUCTION_PATH}:42#execute",
            evidence="void execute ends with an unconditional return statement",
            status="open",
            attempts=0,
        )

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
