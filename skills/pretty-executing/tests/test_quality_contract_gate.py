#!/usr/bin/env python3
"""Regression tests for the lightweight Java quality gate."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from quality_contract_gate import main, scan_java_source
from quality_registry import ERROR, RULE_BY_CODE, registry_errors


JAVA_PATH = "src/main/java/example/Example.java"
REMOVED_RULE_CODES = {
    "BOOLEAN-FLAG",
    "BROAD-CATCH-FALLBACK",
    "COMPLEX-TERNARY",
    "CONTROL-FLOW-SKIP",
    "DISABLED-TEST",
    "EMPTY-CATCH",
    "FIELD-INJECTION",
    "GENERIC-NORMALIZATION-HELPER",
    "GENERIC-RESULT-SHAPE",
    "IDENTIFIER-NORMALIZATION",
    "IMPLICIT-FIELD-FALLBACK",
    "NORMALIZATION-HELPER",
    "NORMALIZATION-OWNERSHIP",
    "NULL-RETURN",
    "NUMBERED-STEP-COMMENT",
    "OPTIONAL-GET",
    "REPEATED-NORMALIZATION",
    "WILDCARD-IMPORT",
}


def findings_for(source: str, changed_lines: set[int] | None = None):
    return scan_java_source(JAVA_PATH, source, changed_lines)


class QualityContractGateTest(unittest.TestCase):
    def test_registry_is_valid(self):
        self.assertEqual([], registry_errors())

    def test_removed_rules_are_not_registered(self):
        self.assertTrue(REMOVED_RULE_CODES.isdisjoint(RULE_BY_CODE))
        self.assertEqual(
            {
                "LABELED-CONTINUE",
                "WHOLE-OBJECT-LOGGING",
                "SENSITIVE-LOGGING",
                "MANUAL-DURATION-LOGGING",
            },
            set(RULE_BY_CODE),
        )

    def test_plain_continue_is_not_a_mechanical_finding(self):
        findings = findings_for("for (Order order : orders) { continue; }")

        self.assertNotIn("CONTROL-FLOW-SKIP", self.codes(findings))
        self.assertNotIn("LABELED-CONTINUE", self.codes(findings))

    def test_context_dependent_patterns_are_not_mechanical_findings(self):
        source = """
            import java.util.*;

            class Example {
                @Autowired
                private OrderRepository repository;

                String normalizeName(String text) { return text.trim(); }
                String chooseName(String first, String second) {
                    return firstNonBlank(first, second);
                }
                String read(Optional<String> candidate, boolean enabled, Order order) {
                    if (candidate.isPresent()) {
                        return candidate.get();
                    }
                    if (enabled && StringUtils.hasText(order.getOrderId())) {
                        return candidate.orElse("fallback");
                    }
                    return null;
                }
                String load() {
                    try {
                        return repository.load();
                    } catch (Exception ignored) {
                        return null;
                    }
                }
                String classify(boolean cold, boolean large) {
                    return cold ? "cold" : large ? "large" : "ambient";
                }
                void visit(List<Order> orders) {
                    for (Order order : orders) {
                        continue;
                    }
                }
                // Step 1: old scaffolding comment
                @Disabled
                void skippedTest() {}
            }
        """

        findings = scan_java_source("src/test/java/example/Example.java", source)

        self.assertEqual([], self.codes(findings))

    def test_labeled_continue_is_an_error(self):
        findings = findings_for("orders: for (;;) { continue orders; }")

        self.assertFinding(findings, "LABELED-CONTINUE", ERROR)
        self.assertNotIn("CONTROL-FLOW-SKIP", self.codes(findings))

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

    def test_manual_duration_logging_is_an_error(self):
        source = """
            long startedAt = System.nanoTime();
            execute();
            log.info("duration={}", System.nanoTime() - startedAt);
        """

        self.assertEqual(2, self.codes(findings_for(source)).count("MANUAL-DURATION-LOGGING"))

    def test_json_output_contains_only_error_findings(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            source = repo / "Example.java"
            output = repo / "quality.json"
            source.write_text("orders: for (;;) { continue orders; }", encoding="utf-8")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                exit_code = main([
                    "--repo", str(repo),
                    "--source", str(source),
                    "--json-output", str(output),
                ])

            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(1, exit_code)
        self.assertEqual({"scanned_files", "findings", "errors"}, set(payload))
        self.assertEqual(["error"], [finding["severity"] for finding in payload["findings"]])

    def assertFinding(self, findings, code: str, severity: str):
        matching = [finding for finding in findings if finding.code == code]
        self.assertEqual(1, len(matching), findings)
        self.assertEqual(severity, matching[0].severity)

    @staticmethod
    def codes(findings):
        return [finding.code for finding in findings]


if __name__ == "__main__":
    unittest.main()
