#!/usr/bin/env python3
"""Regression tests for the lightweight Java quality gate."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from quality_contract_gate import scan_java_source
from quality_registry import ERROR, REVIEW, registry_errors


JAVA_PATH = "src/main/java/example/Example.java"


def findings_for(source: str, changed_lines: set[int] | None = None):
    return scan_java_source(JAVA_PATH, source, changed_lines)


class QualityContractGateTest(unittest.TestCase):
    def test_registry_is_valid(self):
        self.assertEqual([], registry_errors())

    def test_plain_continue_requires_review(self):
        findings = findings_for("for (Order order : orders) { continue; }")

        self.assertFinding(findings, "CONTROL-FLOW-SKIP", REVIEW)
        self.assertNotIn("LABELED-CONTINUE", self.codes(findings))

    def test_labeled_continue_is_an_error(self):
        findings = findings_for("orders: for (;;) { continue orders; }")

        self.assertFinding(findings, "LABELED-CONTINUE", ERROR)
        self.assertNotIn("CONTROL-FLOW-SKIP", self.codes(findings))

    def test_nested_ternary_requires_review(self):
        findings = findings_for("return cold ? COLD : large ? OVERSIZED : AMBIENT;")

        self.assertFinding(findings, "COMPLEX-TERNARY", REVIEW)

    def test_numbered_step_comments_are_errors(self):
        source = """
            // Step 1: validate
            validate(command);
            // 2. persist
            persist(order);
            /* 第三步：发布事件 */
            publish(event);
            String example = "// Step 4: not a comment";
        """

        findings = findings_for(source)

        self.assertEqual(3, self.codes(findings).count("NUMBERED-STEP-COMMENT"))

    def test_java_text_block_content_is_not_treated_as_a_comment(self):
        source = '''
            String instructions = """
                One "quoted" word
                // Step 1: rendered instructions
                """;
            // Step 2: actual comment
        '''

        findings = findings_for(source)

        numbered_comments = [finding for finding in findings if finding.code == "NUMBERED-STEP-COMMENT"]
        self.assertEqual([6], [finding.line for finding in numbered_comments])

    def test_given_when_then_comments_are_not_numbered_steps(self):
        source = "// Given\n// When\n// Then\nvoid verifiesOrderPlacement() {}"

        self.assertNotIn("NUMBERED-STEP-COMMENT", self.codes(findings_for(source)))

    def test_numbered_step_comments_respect_changed_lines(self):
        source = "// Step 1: validate\nvalidate();\n// Step 2: persist\npersist();"

        findings = findings_for(source, changed_lines={3})

        numbered_comments = [finding for finding in findings if finding.code == "NUMBERED-STEP-COMMENT"]
        self.assertEqual([3], [finding.line for finding in numbered_comments])

    def test_whole_object_serialization_in_a_log_is_an_error(self):
        source = 'log.info("request={}", objectMapper.writeValueAsString(request));'

        self.assertFinding(findings_for(source), "WHOLE-OBJECT-LOGGING", ERROR)

    def test_sensitive_header_and_credentials_are_errors(self):
        source = """
            log.info("authorization={}", request.getHeader("Authorization"));
            log.info("password={}", command.password());
            log.info("token={}", response.accessToken());
        """

        findings = findings_for(source)

        self.assertEqual(3, self.codes(findings).count("SENSITIVE-LOGGING"))

    def test_redacted_credentials_and_safe_summary_are_allowed(self):
        source = '''
            log.info("password={}", maskedPassword);
            log.info("token={}", response.getRedactedAccessToken());
            log.info("requestId={}, itemCount={}", requestId, itemCount);
            log.info("Authorization authentication failed");
            log.info("""
                Example: request.getHeader("Authorization")
                """);
        '''

        self.assertNotIn("SENSITIVE-LOGGING", self.codes(findings_for(source)))

    def assertFinding(self, findings, code: str, severity: str):
        matching = [finding for finding in findings if finding.code == code]
        self.assertEqual(1, len(matching), findings)
        self.assertEqual(severity, matching[0].severity)

    @staticmethod
    def codes(findings):
        return [finding.code for finding in findings]


if __name__ == "__main__":
    unittest.main()
