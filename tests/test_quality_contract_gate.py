from __future__ import annotations

import re
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/pretty-common/scripts"))
sys.path.insert(0, str(ROOT / "skills/pretty-executing/scripts"))

from quality_contract_gate import RULES, RISK_OWNERS, candidate_sha256, parse_touched_java_lines, review_evidence_errors, scan_java_source  # noqa: E402
from verify_quality_contract import (  # noqa: E402
    _candidate_file_parts,
    _changed_scope,
    _manifest_scope_errors,
    _matrix_paths,
    _read_manifest,
    _scan_sources,
    _scope_errors,
)
from verify_test_execution import TestExecutionRequest, scan_disabled_annotations, verify, verify_expected_tests  # noqa: E402


class QualityContractGateTest(unittest.TestCase):
    def test_risk_owner_registry_matches_shared_routing_table(self) -> None:
        routing = (ROOT / "skills/pretty-common/references/quality-routing.md").read_text(encoding="utf-8")
        documented = dict(re.findall(r"^\| `([^`]+)` \|.*\| `([^`]+)` \|$", routing, re.MULTILINE))
        self.assertEqual(RISK_OWNERS, documented)

    def test_detects_high_confidence_production_errors(self) -> None:
        codes = {finding.code for finding in scan_java_source("class Service { String load() { return null; } }")}
        self.assertIn("NULL-RETURN", codes)

    def test_continue_is_a_non_waivable_error(self) -> None:
        findings = [
            finding for finding in scan_java_source("class Service { void run() { continue; } }")
            if finding.code == "CONTROL-FLOW-SKIP"
        ]
        self.assertEqual(["error"], [finding.severity for finding in findings])

    def test_nullable_annotation_cannot_self_authorize_null_return(self) -> None:
        source = "class Service { @Nullable String load() { return null; } }"
        self.assertIn("NULL-RETURN", {finding.code for finding in scan_java_source(source)})

    def test_rejects_repeated_nullable_builder_mapping(self) -> None:
        source = """
class Service {
    Criteria build(Query query) {
        return Criteria.builder()
            .storeCode(query == null ? null : query.getStoreCode())
            .pointCode(query == null ? null : query.getPointCode())
            .build();
    }
}
"""
        findings = scan_java_source(source)
        severities = {finding.code: finding.severity for finding in findings}
        self.assertEqual("error", severities["NULL-TERNARY"])
        self.assertEqual("review_required", severities["REPEATED-NULL-GUARD"])

    def test_nullable_return_contract_does_not_allow_internal_null_propagation(self) -> None:
        source = """
class Service {
    @Nullable
    Criteria build(Query query) {
        return Criteria.builder()
            .storeCode(query == null ? null : query.getStoreCode())
            .build();
    }
}
"""
        self.assertIn("NULL-TERNARY", {finding.code for finding in scan_java_source(source)})

    def test_comment_content_is_not_scanned_as_code_but_comment_needs_review(self) -> None:
        source = """
class Service {
    String load() {
        // return null;
        return "catch (Exception ignored) {}";
    }
}
"""
        self.assertEqual({"COMMENT-JUSTIFICATION"}, {finding.code for finding in scan_java_source(source)})

    def test_all_comment_languages_use_one_justification_rule(self) -> None:
        comment = """
class Service {
    String load() {
        // 查询订单后返回结果。
        return "ORDER";
    }
}
"""
        string = 'class Service { String load() { return "https://example.test/中文"; } }'
        self.assertEqual({"COMMENT-JUSTIFICATION"}, {finding.code for finding in scan_java_source(comment)})
        self.assertNotIn("COMMENT-JUSTIFICATION", {finding.code for finding in scan_java_source(string)})

    def test_rejects_manual_duration_logging(self) -> None:
        source = """
class Service {
    void dispatch() {
        long start = System.currentTimeMillis();
        send();
        log.info("durationMs={}", System.currentTimeMillis() - start);
    }
}
"""
        self.assertIn("MANUAL-DURATION-LOGGING", {finding.code for finding in scan_java_source(source)})

    def test_trim_requires_boundary_contract_review(self) -> None:
        source = """
class Service {
    String route(String eventDefineCode) {
        return eventDefineCode.trim();
    }
}
"""
        self.assertIn("NORMALIZATION-OWNERSHIP", {finding.code for finding in scan_java_source(source)})

    def test_generic_normalization_helper_declaration_is_a_non_waivable_error(self) -> None:
        source = """
class TextSupport {
    private String normalizeText(String value) {
        return value == null ? null : value.trim();
    }
}
"""
        findings = [finding for finding in scan_java_source(source) if finding.code == "GENERIC-NORMALIZATION-HELPER"]
        self.assertEqual(["error"], [finding.severity for finding in findings])

    def test_generic_normalization_helper_aliases_are_blocked(self) -> None:
        names = ("normalizeString", "cleanText", "trimText", "trimToNull")
        for name in names:
            with self.subTest(name=name):
                source = f"""
class TextSupport {{
    String {name}(String value) {{
        return value.trim();
    }}
}}
"""
                codes = {finding.code for finding in scan_java_source(source)}
                self.assertIn("GENERIC-NORMALIZATION-HELPER", codes)

    def test_generic_normalization_helper_call_is_blocked(self) -> None:
        source = """
class EventService {
    String duplicateKey(String value) {
        return normalizeText(value);
    }
}
"""
        findings = [finding for finding in scan_java_source(source) if finding.code == "GENERIC-NORMALIZATION-HELPER"]
        self.assertEqual(["error"], [finding.severity for finding in findings])

    def test_generic_normalization_support_call_is_blocked(self) -> None:
        source = """
class EventService {
    String duplicateKey(String value) {
        return textSupport.normalize(value);
    }
}
"""
        self.assertIn(
            "GENERIC-NORMALIZATION-HELPER",
            {finding.code for finding in scan_java_source(source)},
        )

    def test_generic_normalization_method_reference_is_blocked(self) -> None:
        source = """
class EventService {
    Function<String, String> normalizer() {
        return this::normalizeText;
    }
}
"""
        self.assertIn(
            "GENERIC-NORMALIZATION-HELPER",
            {finding.code for finding in scan_java_source(source)},
        )

    def test_domain_specific_normalizer_method_is_not_name_only_error(self) -> None:
        source = """
class LegacyEventIdAdapter {
    String normalize(String rawEventId) {
        return rawEventId.trim();
    }
}

class EventService {
    String eventId(String rawEventId) {
        return legacyEventIdAdapter.normalize(rawEventId);
    }
}
"""
        findings = scan_java_source(source)
        self.assertNotIn("GENERIC-NORMALIZATION-HELPER", {finding.code for finding in findings})
        self.assertIn("NORMALIZATION-OWNERSHIP", {finding.code for finding in findings})

    def test_required_query_input_cannot_fall_back_to_empty(self) -> None:
        source = """
class QueryService {
    List<Order> find(String eventCode) {
        if (eventCode == null) {
            return Collections.emptyList();
        }
        return repository.find(eventCode);
    }
}
"""
        self.assertIn("REQUIRED-INPUT-EMPTY-FALLBACK", {finding.code for finding in scan_java_source(source)})

    def test_boundary_any_without_captor_requires_review(self) -> None:
        source = """
class AdapterTest {
    @Test
    void sendsRequest() {
        when(gateway.send(any())).thenReturn(SUCCESS);
        assertThat(adapter.send(command)).isEqualTo(SUCCESS);
    }
}
"""
        self.assertIn(
            "BOUNDARY-ANY-WITHOUT-CAPTOR",
            {finding.code for finding in scan_java_source(source, production=False)},
        )

    def test_changed_line_expands_to_the_whole_method(self) -> None:
        body = "\n".join(f"        value += {number};" for number in range(22))
        source = f"""
class Service {{
    int calculate() {{
        int value = 0;
{body}
        return value;
    }}
}}
"""
        self.assertIn("METHOD-LOC", {finding.code for finding in scan_java_source(source, changed_lines=frozenset({12}))})

    def test_deletion_only_hunk_touches_the_surviving_anchor(self) -> None:
        diff = "--- a/src/main/java/example/Service.java\n+++ b/src/main/java/example/Service.java\n@@ -8,1 +8,0 @@\n-        obsolete();\n"
        self.assertEqual(frozenset({8}), parse_touched_java_lines(diff)["src/main/java/example/Service.java"])

    def test_deleted_production_source_still_requires_production_review(self) -> None:
        findings, source_parts, has_production = _scan_sources(ROOT, {"src/main/java/example/Deleted.java": frozenset({1})})
        self.assertEqual([], findings)
        self.assertEqual({}, source_parts)
        self.assertTrue(has_production)

    def test_disabled_test_is_a_hard_finding(self) -> None:
        findings = scan_java_source("@Disabled\n@Test\nvoid behavior() {}", production=False)
        disabled = [finding for finding in findings if finding.code == "DISABLED-TEST"]
        self.assertTrue(disabled)
        self.assertEqual({"error"}, {finding.severity for finding in disabled})

    def test_review_evidence_requires_independent_reviewer(self) -> None:
        candidate = candidate_sha256({"source": "class Service {}"})
        evidence = {"candidate_sha256": candidate, "reviewer": "reviewer-1", "independent": True, "risks": [], "accepted_findings": [], "blocking_findings": [], "guards": ["clean-code-guard"]}
        self.assertEqual([], review_evidence_errors(evidence, candidate, [], require_clean_guard=True))

    def test_review_rejects_duplicate_risk_ownership_entries(self) -> None:
        candidate = candidate_sha256({"source": "class Service {}"})
        risk = {"id": "JAVA_OOD", "owner": "121-java-object-oriented-design", "evidence": ["Service"]}
        evidence = {"candidate_sha256": candidate, "reviewer": "reviewer-1", "independent": True, "risks": [risk, risk], "accepted_findings": [], "blocking_findings": []}
        self.assertIn("review risk id must be unique: JAVA_OOD", review_evidence_errors(evidence, candidate, []))

    def test_review_rejects_wrong_risk_owner(self) -> None:
        candidate = candidate_sha256({"source": "class Service {}"})
        evidence = {"candidate_sha256": candidate, "reviewer": "reviewer-1", "independent": True, "risks": [{"id": "TYPE_DESIGN", "owner": "java-code-review", "evidence": ["Score"]}], "accepted_findings": [], "blocking_findings": []}
        self.assertIn("review risk TYPE_DESIGN must be owned by 122-java-type-design", review_evidence_errors(evidence, candidate, []))

    def test_review_rejects_invalid_accepted_finding_collection(self) -> None:
        candidate = candidate_sha256({"source": "class Service {}"})
        evidence = {"candidate_sha256": candidate, "reviewer": "reviewer-1", "independent": True, "risks": [], "accepted_findings": "none", "blocking_findings": []}
        self.assertIn("review evidence accepted_findings must be a list", review_evidence_errors(evidence, candidate, []))

    def test_review_must_bind_objective_gate_completed_before_review(self) -> None:
        candidate = candidate_sha256({"source": "class Service {}"})
        evidence = {
            "candidate_sha256": candidate,
            "reviewer": "reviewer-1",
            "independent": True,
            "risks": [],
            "accepted_findings": [],
            "blocking_findings": [],
            "pre_review_gate": {
                "quality_candidate_sha256": candidate,
                "build_candidate_sha256": "old-build",
                "test_evidence_sha256": "tests",
                "coverage_evidence_sha256": "coverage",
            },
        }
        expected = {
            "quality_candidate_sha256": candidate,
            "build_candidate_sha256": "build",
            "test_evidence_sha256": "tests",
            "coverage_evidence_sha256": "coverage",
        }
        self.assertIn(
            "review evidence does not match the objective pre-review Gate",
            review_evidence_errors(evidence, candidate, [], pre_review_gate=expected),
        )

    def test_review_rejects_reusing_one_generic_acceptance_reason(self) -> None:
        body = "\n".join(f"        int value{number} = {number};" for number in range(22))
        source = f"""
class Service {{
    void first() {{
{body}
    }}
    void second() {{
{body}
    }}
}}
"""
        findings = [finding for finding in scan_java_source(source) if finding.code == "METHOD-LOC"]
        candidate = candidate_sha256({"source": source})
        evidence = {
            "candidate_sha256": candidate,
            "reviewer": "reviewer-1",
            "independent": True,
            "risks": [],
            "accepted_findings": [
                {
                    "fingerprint": finding.fingerprint,
                    "reason": "existing repository method is accepted",
                    "evidence": ["stable repository contract"],
                }
                for finding in findings
            ],
            "blocking_findings": [],
        }
        errors = review_evidence_errors(evidence, candidate, findings)
        self.assertTrue(any("generic reason" in error for error in errors))

    def test_changed_scope_ignores_explanatory_documents(self) -> None:
        self.assertEqual([], _scope_errors({"docs/pretty/example/design.md"}, set()))

    def test_runtime_paths_are_never_treated_as_explanatory(self) -> None:
        changed = {
            "context-service/src/main/java/example/Service.java",
            "src/main/resources/help.md",
            "module/src/main/java/adr/Policy.java",
        }
        errors = _scope_errors(changed, set())
        self.assertEqual(3, len(errors))

    def test_quality_candidate_binds_sql_file_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            sql_path = repo / "db/migration/V2__event_index.sql"
            sql_path.parent.mkdir(parents=True)
            sql_path.write_text("CREATE INDEX idx_event_code ON service_event(event_code);\n", encoding="utf-8")
            parts, source_hashes = _candidate_file_parts(repo, {"db/migration/V2__event_index.sql"})
        self.assertIn("CREATE INDEX", parts["file:db/migration/V2__event_index.sql"])
        self.assertEqual(64, len(source_hashes["db/migration/V2__event_index.sql"]))

    def test_changed_manifest_rejects_parent_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = Path(temporary) / "changed.json"
            manifest.write_text('{"../outside.java": [1]}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "repository-relative"):
                _read_manifest(manifest)

    def test_changed_manifest_rejects_empty_java_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = Path(temporary) / "changed.json"
            manifest.write_text('{"src/main/java/example/Service.java": []}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must contain changed lines"):
                _read_manifest(manifest)

    def test_manifest_cannot_omit_real_java_diff(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            source = repo / "src/main/java/example/Service.java"
            source.parent.mkdir(parents=True)
            source.write_text('class Service { String build(Query query) { return "ok"; } }\n', encoding="utf-8")
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=repo, check=True)
            base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
            source.write_text(
                "class Service { String build(Query query) { "
                "return query == null ? null : query.value(); } }\n",
                encoding="utf-8",
            )
            manifest = repo / "changed.json"
            manifest.write_text("{}\n", encoding="utf-8")

            changed_java, changed_paths, _ = _changed_scope(repo, base)
            findings, _, _ = _scan_sources(repo, changed_java)
            errors = _manifest_scope_errors(manifest, changed_java, changed_paths)

            self.assertIn("NULL-TERNARY", {finding.code for finding in findings})
            self.assertTrue(any("omits Java paths" in error for error in errors))

    def test_java_execution_matrix_requires_generation_preflight(self) -> None:
        design = "## 实施影响\n### TASK-001：行为\n"
        matrix = {
            "tasks": [{
                "id": "TASK-001",
                "production_files": ["src/main/java/example/Service.java"],
                "test_files": ["src/test/java/example/ServiceTest.java"],
                "supporting_files": [],
                "behavior_slices": [],
            }]
        }

        _, errors = _matrix_paths(matrix, design)

        self.assertTrue(any("without behavior_slices needs non_behavior_reason" in error for error in errors))

    def test_accepts_complete_generation_preflight(self) -> None:
        design = "## 实施影响\n### TASK-001：行为\n"
        matrix = {
            "tasks": [{
                "id": "TASK-001",
                "production_files": ["src/main/java/example/Service.java"],
                "test_files": ["src/test/java/example/ServiceTest.java"],
                "supporting_files": [],
                "behavior_slices": [{
                    "id": "SLICE-001",
                    "paths": [
                        "src/main/java/example/Service.java",
                        "src/test/java/example/ServiceTest.java",
                    ],
                    "production_symbols": ["Service#execute"],
                    "test_entry": "ServiceTest#returnsResult",
                    "input_invariants": ["query is required"],
                    "boundary_substitutes": [],
                    "result_assertions": ["returns the mapped result"],
                    "nearest_neighbors": ["NeighborService#execute"],
                    "coverage_obligations": ["normal result -> ServiceTest#returnsResult"],
                    "resolver_rules": [rule.code for rule in RULES],
                    "resolver_risks": [{
                        "id": "JAVA_RUNTIME_RISK",
                        "owner": "java-code-review",
                        "evidence": ["Service#execute"],
                    }],
                    "depends_on": [],
                }],
            }]
        }

        _, errors = _matrix_paths(matrix, design)

        self.assertEqual([], errors)

    def test_non_behavior_java_task_can_record_not_applicable_reason(self) -> None:
        design = "## 实施影响\n### TASK-001：声明类型\n"
        matrix = {
            "tasks": [{
                "id": "TASK-001",
                "production_files": ["src/main/java/example/Status.java"],
                "test_files": [],
                "supporting_files": [],
                "behavior_slices": [],
                "non_behavior_reason": "declaration-only enum with no runtime branch",
            }]
        }

        _, errors = _matrix_paths(matrix, design)

        self.assertEqual([], errors)

    def test_disabled_scope_is_reported_before_apply(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            source = repo / "src/test/java/example/ServiceTest.java"
            source.parent.mkdir(parents=True)
            source.write_text("@Disabled\nclass ServiceTest {}\n", encoding="utf-8")
            findings = scan_disabled_annotations(repo, ["src/test/java/example/ServiceTest.java"])
        self.assertEqual("disabled", findings[0]["kind"])

    def test_expected_test_must_appear_in_fresh_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "TEST-example.ServiceTest.xml"
            report.write_text("<testsuite><testcase classname='example.ServiceTest' name='works'/></testsuite>", encoding="utf-8")
            executed, errors = verify_expected_tests((report,), ("example.ServiceTest#works",))
        self.assertEqual([], errors)
        self.assertEqual(1, len(executed))

    def test_new_test_source_cannot_use_a_disabled_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            source = repo / "src/test/java/example/ServiceTest.java"
            source.parent.mkdir(parents=True)
            source.write_text("@Disabled\nclass ServiceTest {\n@Test void works() {}\n}\n", encoding="utf-8")
            payload = verify(TestExecutionRequest(
                repo=repo,
                test_sources=("src/test/java/example/ServiceTest.java",),
                expected_tests=("ServiceTest#works",),
                reports=(),
                report_not_before=0,
                new_test_sources=("src/test/java/example/ServiceTest.java",),
                design_sha256="design-sha",
            ))

        self.assertFalse(payload["passed"])
        self.assertTrue(any("disabled" in error for error in payload["errors"]))

    def test_new_test_source_is_bound_into_test_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            source = repo / "src/test/java/example/NewTest.java"
            source.parent.mkdir(parents=True)
            source.write_text("class NewTest {}\n", encoding="utf-8")
            payload = verify(TestExecutionRequest(
                repo=repo,
                test_sources=(),
                expected_tests=(),
                reports=(),
                report_not_before=0,
                new_test_sources=("src/test/java/example/NewTest.java",),
                design_sha256="design-sha",
            ))

        self.assertIn("src/test/java/example/NewTest.java", payload["source_sha256"])

    def test_new_test_can_use_enabled_class_beside_historical_disabled_class(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            source = repo / "src/test/java/example/NewTest.java"
            source.parent.mkdir(parents=True)
            source.write_text(
                "@Disabled\nclass OldTest {}\nclass NewTest {\n@Test void works() {}\n}\n",
                encoding="utf-8",
            )
            report = repo / "target/TEST-NewTest.xml"
            report.parent.mkdir(parents=True)
            report.write_text(
                "<testsuite><testcase classname='NewTest' name='works'/></testsuite>",
                encoding="utf-8",
            )
            os.utime(source, (100, 100))
            os.utime(report, (200, 200))
            payload = verify(TestExecutionRequest(
                repo=repo,
                test_sources=("src/test/java/example/NewTest.java",),
                expected_tests=("NewTest#works",),
                reports=(report,),
                report_not_before=0,
                new_test_sources=("src/test/java/example/NewTest.java",),
                design_sha256="design-sha",
            ))
        self.assertTrue(payload["passed"])

    def test_report_must_be_newer_than_target_test_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            source = repo / "src/test/java/example/ServiceTest.java"
            report = repo / "target/TEST-ServiceTest.xml"
            source.parent.mkdir(parents=True)
            report.parent.mkdir(parents=True)
            source.write_text("class ServiceTest { @Test void works() {} }", encoding="utf-8")
            report.write_text("<testsuite><testcase classname='ServiceTest' name='works'/></testsuite>", encoding="utf-8")
            os.utime(report, (100, 100))
            os.utime(source, (200, 200))
            payload = verify(TestExecutionRequest(
                repo=repo,
                test_sources=("src/test/java/example/ServiceTest.java",),
                expected_tests=("ServiceTest#works",),
                reports=(report,),
                report_not_before=0,
            ))
        self.assertTrue(any("stale" in error for error in payload["errors"]))

    def test_one_skipped_parameterized_invocation_fails_expected_test(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "TEST-example.ServiceTest.xml"
            report.write_text(
                "<testsuite><testcase classname='example.ServiceTest' name='works[1]'/><testcase classname='example.ServiceTest' name='works[2]'><skipped/></testcase></testsuite>",
                encoding="utf-8",
            )
            _, errors = verify_expected_tests((report,), ("example.ServiceTest#works",))
        self.assertTrue(any("skipped or failed invocation" in error for error in errors))

    def test_target_test_source_must_exist(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            request = TestExecutionRequest(
                repo=Path(temporary),
                test_sources=("src/test/java/example/MissingTest.java",),
                expected_tests=(),
                reports=(),
                report_not_before=0,
                design_sha256="design-sha",
            )
            payload = verify(request)
        self.assertIn(
            "target test source does not exist: src/test/java/example/MissingTest.java",
            payload["errors"],
        )

    def test_meta_disabled_annotation_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            source = repo / "src/test/java/example/ServiceTest.java"
            source.parent.mkdir(parents=True)
            source.write_text(
                "@Disabled\n@interface DisabledByPolicy {}\n@DisabledByPolicy\nclass ServiceTest {}\n",
                encoding="utf-8",
            )
            findings = scan_disabled_annotations(repo, ("src/test/java/example/ServiceTest.java",))
        self.assertTrue(any(finding["kind"] == "meta-disabled" for finding in findings))


if __name__ == "__main__":
    unittest.main()
