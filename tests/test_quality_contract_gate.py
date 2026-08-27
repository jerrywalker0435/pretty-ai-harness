from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/pretty-common/scripts"))
sys.path.insert(0, str(ROOT / "skills/pretty-writing-plan/scripts"))
sys.path.insert(0, str(ROOT / "skills/pretty-executing-plan/scripts"))

from quality_contract_gate import (  # noqa: E402
    RISK_OWNERS,
    candidate_sha256,
    parse_touched_java_lines,
    review_evidence_errors,
    scan_java_source,
)
from verify_quality_contract import (  # noqa: E402
    _candidate_file_parts,
    _plan_paths,
    _read_manifest,
    _scan_sources,
    _scope_errors,
)


class QualityContractGateTest(unittest.TestCase):
    def test_risk_owner_registry_matches_shared_routing_table(self) -> None:
        routing = (
            ROOT / "skills/pretty-common/references/quality-routing.md"
        ).read_text(encoding="utf-8")
        documented = dict(
            re.findall(r"^\| `([^`]+)` \|.*\| `([^`]+)` \|$", routing, re.MULTILINE)
        )

        self.assertEqual(RISK_OWNERS, documented)

    def test_detects_high_confidence_production_errors(self) -> None:
        source = """
class Service {
    @Autowired
    private Dependency dependency;

    String load() {
        return null;
    }
}
"""

        codes = {finding.code for finding in scan_java_source(source)}

        self.assertEqual({"FIELD-INJECTION", "NULL-RETURN"}, codes)

    def test_comment_content_is_not_scanned_as_code_but_comment_needs_review(self) -> None:
        source = """
class Service {
    String load() {
        // return null;
        return "catch (Exception ignored) {}";
    }
}
"""

        codes = {finding.code for finding in scan_java_source(source)}

        self.assertEqual({"COMMENT-JUSTIFICATION"}, codes)

    def test_single_production_comment_requires_justification(self) -> None:
        source = """
class Service {
    String load() {
        // Preserve the provider's legacy sentinel.
        return "UNKNOWN";
    }
}
"""

        codes = {finding.code for finding in scan_java_source(source)}

        self.assertIn("COMMENT-JUSTIFICATION", codes)
        self.assertNotIn("COMMENT-JUSTIFICATION", {finding.code for finding in scan_java_source(source, production=False)})

    def test_rejects_cjk_production_comment(self) -> None:
        source = """
class Service {
    String load() {
        // 查询订单后返回结果。
        return "ORDER";
    }
}
"""

        codes = {finding.code for finding in scan_java_source(source)}

        self.assertIn("CJK-COMMENT", codes)

    def test_cjk_text_inside_string_is_not_a_comment(self) -> None:
        source = """
class Service {
    String endpoint() {
        return "https://example.test/中文";
    }
}
"""

        codes = {finding.code for finding in scan_java_source(source)}

        self.assertNotIn("CJK-COMMENT", codes)

    def test_rejects_manual_duration_logging(self) -> None:
        source = """
class Service {
    void dispatch() {
        long start = System.currentTimeMillis();
        send();
        log.info("dispatch durationMs={}", System.currentTimeMillis() - start);
    }
}
"""

        codes = {finding.code for finding in scan_java_source(source)}

        self.assertIn("MANUAL-DURATION-LOGGING", codes)

    def test_business_timestamp_without_logging_is_not_duration_logging(self) -> None:
        source = """
class Service {
    long currentTimestamp() {
        long startedAt = System.currentTimeMillis();
        return startedAt;
    }
}
"""

        codes = {finding.code for finding in scan_java_source(source)}

        self.assertNotIn("MANUAL-DURATION-LOGGING", codes)

    def test_business_timestamp_with_unrelated_logging_is_not_duration_logging(self) -> None:
        source = """
class Service {
    long currentTimestamp() {
        long startedAt = System.currentTimeMillis();
        log.info("timestamp captured");
        return startedAt;
    }
}
"""

        codes = {finding.code for finding in scan_java_source(source)}

        self.assertNotIn("MANUAL-DURATION-LOGGING", codes)

    def test_trim_requires_boundary_contract_review(self) -> None:
        source = """
class Service {
    String route(String eventDefineCode) {
        String normalizedCode = eventDefineCode.trim();
        return normalizedCode;
    }
}
"""

        codes = {finding.code for finding in scan_java_source(source)}

        self.assertIn("NORMALIZATION-OWNERSHIP", codes)

    def test_relative_bucket_token_is_generic_and_does_not_match_normalized(self) -> None:
        source = """
class Dispatcher {
    void dispatchNormalEvent(Command normalCommand, String normalText) {
        String normalizedText = normalText;
    }
}
"""

        ambiguous_symbols = {
            finding.message
            for finding in scan_java_source(source)
            if finding.code == "AMBIGUOUS-BUCKET-NAME"
        }

        self.assertTrue(any("dispatchNormalEvent" in message for message in ambiguous_symbols))
        self.assertTrue(any("normalCommand" in message for message in ambiguous_symbols))
        self.assertTrue(any("normalText" in message for message in ambiguous_symbols))
        self.assertFalse(any("normalizedText" in message for message in ambiguous_symbols))

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

        findings = scan_java_source(source, changed_lines=frozenset({12}))

        self.assertIn("METHOD-LOC", {finding.code for finding in findings})

    def test_heuristic_smells_require_review_instead_of_hard_failure(self) -> None:
        source = """
import java.util.*;
class Service {
    String choose(int first, int second, int third, int fourth, boolean strict) {
        continuePoint: for (;;) {
            if (strict) {
                continue continuePoint;
            }
            return "STANDARD";
        }
    }
}
"""

        findings = scan_java_source(source)

        self.assertTrue(findings)
        self.assertEqual({"review_required"}, {finding.severity for finding in findings})

    def test_deletion_only_hunk_touches_the_surviving_anchor(self) -> None:
        diff = """--- a/src/main/java/example/Service.java
+++ b/src/main/java/example/Service.java
@@ -8,1 +8,0 @@
-        obsolete();
"""

        touched = parse_touched_java_lines(diff)

        self.assertEqual(frozenset({8}), touched["src/main/java/example/Service.java"])

    def test_whole_file_deletion_remains_in_changed_java_scope(self) -> None:
        diff = """--- a/src/main/java/example/Service.java
+++ /dev/null
@@ -1,3 +0,0 @@
-package example;
-class Service {
-}
"""

        touched = parse_touched_java_lines(diff)

        self.assertEqual(
            frozenset({1}),
            touched["src/main/java/example/Service.java"],
        )

    def test_deleted_production_source_still_requires_production_review(self) -> None:
        with self.subTest("deleted source"):
            findings, source_parts, has_production = _scan_sources(
                ROOT,
                {"src/main/java/example/Deleted.java": frozenset({1})},
            )

        self.assertEqual([], findings)
        self.assertEqual({}, source_parts)
        self.assertTrue(has_production)

    def test_detects_broad_catch_fallback_after_nested_block(self) -> None:
        source = """
class Service {
    boolean load() {
        try {
            return false;
        } catch (Exception error) {
            if (error != null) {
                audit();
            }
            return true;
        }
    }

    void audit() {}
}
"""

        codes = {finding.code for finding in scan_java_source(source)}

        self.assertIn("BROAD-CATCH-FALLBACK", codes)

    def test_accepts_fully_qualified_nullable_annotation(self) -> None:
        source = """
class Service {
    public @org.springframework.lang.Nullable String load() {
        return null;
    }
}
"""

        codes = {finding.code for finding in scan_java_source(source)}

        self.assertNotIn("NULL-RETURN", codes)

    def test_scope_rejects_planned_path_without_a_change(self) -> None:
        errors = _scope_errors(
            {"src/main/java/example/A.java"},
            {
                "src/main/java/example/A.java",
                "src/main/java/example/B.java",
            },
            None,
        )

        self.assertIn(
            "planned path has no corresponding change: src/main/java/example/B.java",
            errors,
        )

    def test_plan_scope_includes_sql_files(self) -> None:
        plan = """
- Modify: `src/main/java/example/A.java`
- Create: `db/migration/V2__event_index.sql`
"""

        self.assertEqual(
            {
                "src/main/java/example/A.java",
                "db/migration/V2__event_index.sql",
            },
            _plan_paths(plan),
        )

    def test_quality_candidate_binds_sql_file_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            sql_path = repo / "db/migration/V2__event_index.sql"
            sql_path.parent.mkdir(parents=True)
            sql_path.write_text("CREATE INDEX idx_event_code ON service_event(event_code);\n")

            parts, source_hashes = _candidate_file_parts(
                repo,
                {"db/migration/V2__event_index.sql"},
            )

        self.assertIn("CREATE INDEX", parts["file:db/migration/V2__event_index.sql"])
        self.assertEqual(64, len(source_hashes["db/migration/V2__event_index.sql"]))

    def test_changed_manifest_rejects_parent_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "changed.json"
            manifest.write_text('{"../outside.java": [1]}', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "repository-relative"):
                _read_manifest(manifest)

    def test_review_requires_structured_independent_evidence(self) -> None:
        candidate = candidate_sha256({"source": "class Service {}"})
        evidence = {
            "candidate_sha256": candidate,
            "reviewer": "reviewer-1",
            "independent": True,
            "risks": [],
            "accepted_findings": [],
            "blocking_findings": [],
            "guards": ["clean-code-guard"],
        }

        self.assertEqual(
            [],
            review_evidence_errors(evidence, candidate, [], require_clean_guard=True),
        )

    def test_review_rejects_duplicate_risk_ownership_entries(self) -> None:
        candidate = candidate_sha256({"source": "class Service {}"})
        risk = {
            "id": "JAVA_OOD",
            "owner": "121-java-object-oriented-design",
            "evidence": ["Service"],
        }
        evidence = {
            "candidate_sha256": candidate,
            "reviewer": "reviewer-1",
            "independent": True,
            "risks": [risk, risk],
            "accepted_findings": [],
            "blocking_findings": [],
        }

        errors = review_evidence_errors(evidence, candidate, [])

        self.assertIn("review risk id must be unique: JAVA_OOD", errors)

    def test_review_rejects_wrong_risk_owner(self) -> None:
        candidate = candidate_sha256({"source": "class Service {}"})
        evidence = {
            "candidate_sha256": candidate,
            "reviewer": "reviewer-1",
            "independent": True,
            "risks": [
                {"id": "TYPE_DESIGN", "owner": "java-code-review", "evidence": ["Score"]}
            ],
            "accepted_findings": [],
            "blocking_findings": [],
        }

        errors = review_evidence_errors(evidence, candidate, [])

        self.assertIn(
            "review risk TYPE_DESIGN must be owned by 122-java-type-design",
            errors,
        )

    def test_review_rejects_unmatched_accepted_finding(self) -> None:
        candidate = candidate_sha256({"source": "class Service {}"})
        evidence = {
            "candidate_sha256": candidate,
            "reviewer": "reviewer-1",
            "independent": True,
            "risks": [],
            "accepted_findings": [
                {"fingerprint": "stale-finding", "reason": "A detailed but stale explanation"}
            ],
            "blocking_findings": [],
        }

        errors = review_evidence_errors(evidence, candidate, [])

        self.assertIn(
            "accepted finding does not match the current candidate: stale-finding",
            errors,
        )

    def test_accepted_finding_requires_concrete_evidence(self) -> None:
        finding = next(
            finding
            for finding in scan_java_source(
                """
class Service {
    String route(String code) {
        return code.trim();
    }
}
"""
            )
            if finding.code == "NORMALIZATION-OWNERSHIP"
        )
        candidate = candidate_sha256({"source": "trim"})
        evidence = {
            "candidate_sha256": candidate,
            "reviewer": "reviewer-1",
            "independent": True,
            "risks": [],
            "accepted_findings": [
                {
                    "fingerprint": finding.fingerprint,
                    "reason": "The HTTP contract explicitly defines surrounding whitespace as insignificant.",
                }
            ],
            "blocking_findings": [],
        }

        errors = review_evidence_errors(evidence, candidate, [finding])

        self.assertIn(
            f"accepted finding {finding.fingerprint} needs concrete evidence",
            errors,
        )
        evidence["accepted_findings"][0]["evidence"] = ["api.yaml#/eventDefineCode"]
        self.assertEqual([], review_evidence_errors(evidence, candidate, [finding]))

    def test_review_rejects_invalid_accepted_finding_collection(self) -> None:
        candidate = candidate_sha256({"source": "class Service {}"})
        evidence = {
            "candidate_sha256": candidate,
            "reviewer": "reviewer-1",
            "independent": True,
            "risks": [],
            "accepted_findings": "none",
            "blocking_findings": [],
        }

        errors = review_evidence_errors(evidence, candidate, [])

        self.assertIn("review evidence accepted_findings must be a list", errors)


if __name__ == "__main__":
    unittest.main()
