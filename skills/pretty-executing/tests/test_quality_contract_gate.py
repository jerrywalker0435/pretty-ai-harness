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
                "VOID_TAIL_RETURN",
                "UNREACHABLE_STATEMENT",
                "EMPTY_CATCH",
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

    def test_void_tail_return_is_an_error(self):
        source = """
            class Example {
                void execute() {
                    doWork();
                    return;
                }
            }
        """

        self.assertFinding(findings_for(source), "VOID_TAIL_RETURN", ERROR)

    def test_early_void_return_is_allowed(self):
        source = """
            class Example {
                void execute(boolean skip) {
                    if (skip) {
                        return;
                    }
                    doWork();
                }
            }
        """

        self.assertNotIn("VOID_TAIL_RETURN", self.codes(findings_for(source)))

    def test_unreachable_statement_after_return_is_an_error(self):
        source = """
            class Example {
                void execute() {
                    return;
                    doWork();
                }
            }
        """

        findings = findings_for(source)

        self.assertFinding(findings, "UNREACHABLE_STATEMENT", ERROR)
        self.assertNotIn("VOID_TAIL_RETURN", self.codes(findings))

    def test_unreachable_statement_after_throw_break_and_continue_is_an_error(self):
        source = """
            class Example {
                void fail() {
                    throw new IllegalStateException();
                    recover();
                }
                void stop() {
                    while (active()) {
                        break;
                        recover();
                    }
                }
                void skip() {
                    while (active()) {
                        continue;
                        recover();
                    }
                }
            }
        """

        self.assertEqual(3, self.codes(findings_for(source)).count("UNREACHABLE_STATEMENT"))

    def test_conditional_return_before_a_statement_is_allowed(self):
        source = """
            class Example {
                void execute(boolean skip) {
                    if (skip) return;
                    doWork();
                }
            }
        """

        self.assertNotIn("UNREACHABLE_STATEMENT", self.codes(findings_for(source)))

    def test_empty_catch_is_an_error_even_when_it_contains_only_a_comment(self):
        source = """
            class Example {
                void execute() {
                    try {
                        doWork();
                    } catch (RuntimeException ignored) {
                        // intentionally ignored
                    }
                }
            }
        """

        self.assertFinding(findings_for(source), "EMPTY_CATCH", ERROR)

    def test_catch_with_a_handling_statement_is_allowed(self):
        source = """
            class Example {
                void execute() {
                    try {
                        doWork();
                    } catch (RuntimeException error) {
                        throw translate(error);
                    }
                }
            }
        """

        self.assertNotIn("EMPTY_CATCH", self.codes(findings_for(source)))

    def test_control_flow_findings_respect_changed_lines(self):
        source = """class Example {
    void oldMethod() {
        return;
    }
    void changedMethod() {
        doWork();
    }
}
"""

        findings = findings_for(source, {6})

        self.assertNotIn("VOID_TAIL_RETURN", self.codes(findings))

    def test_tail_return_is_checked_when_an_earlier_line_in_the_method_changes(self):
        source = """class Example {
    void changedMethod() {
        doWork();
        return;
    }
}
"""

        findings = findings_for(source, {3})

        self.assertFinding(findings, "VOID_TAIL_RETURN", ERROR)

    def test_whole_object_serialization_in_a_log_is_an_error(self):
        source = 'log.info("request={}", objectMapper.writeValueAsString(request));'

        self.assertFinding(findings_for(source), "WHOLE-OBJECT-LOGGING", ERROR)

    def test_control_flow_boundaries_do_not_report_valid_code(self):
        sources = [
            'class X { void f() { Runnable r = () -> { return; }; work(); } }',
            'class X { void f(int x) { switch(x) { case 1: return; default: work(); } } }',
            'class X { void f(boolean x) { if (x) work(); else return; work(); } }',
            'class X { String f() { return "return; work(); catch (E e) {}"; } }',
            'class X { void f() { /* return; work(); */ work(); } }',
        ]
        for source in sources:
            with self.subTest(source=source):
                self.assertEqual([], findings_for(source))

    def test_unreachable_statement_changed_without_changing_terminator(self):
        source = 'class X { void f() {\nreturn;\nwork();\n} }'
        findings = findings_for(source, {3})
        self.assertFinding(findings, "UNREACHABLE_STATEMENT", ERROR)
        self.assertEqual(3, findings[0].line)

    def test_empty_catch_with_empty_statements_is_rejected(self):
        source = 'class X { void f() { try { work(); } catch (E e) { {}; } } }'
        self.assertFinding(findings_for(source), "EMPTY_CATCH", ERROR)

    def test_anonymous_exception_does_not_hide_unreachable_statement(self):
        source = 'class X { void f() { throw new E() {}; work(); } }'
        self.assertFinding(findings_for(source), "UNREACHABLE_STATEMENT", ERROR)

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
