from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/pretty-executing/scripts"))

from verify_incremental_coverage import (  # noqa: E402
    ChangedSource,
    LineCoverage,
    SourceCoverage,
    _reject_test_skipping,
    _stale_sources,
    calculate_coverage,
    parse_changed_diff,
)


class CoverageGateTest(unittest.TestCase):
    def test_diff_tracks_only_production_java_additions(self) -> None:
        diff = """+++ b/app/src/main/java/example/Service.java
@@ -2,0 +3,1 @@
+        return value;
+++ b/app/src/test/java/example/ServiceTest.java
@@ -2,0 +3,1 @@
+        assertTrue(true);
"""

        changed = parse_changed_diff(diff)

        self.assertEqual(
            {"app/src/main/java/example/Service.java": frozenset({3})},
            changed,
        )

    def test_multimodule_duplicate_names_match_the_correct_report(self) -> None:
        changed = (
            ChangedSource("orders/src/main/java/example/Service.java", frozenset({10})),
            ChangedSource("users/src/main/java/example/Service.java", frozenset({10})),
        )
        covered = LineCoverage(1, 0, 2, 0)
        sources = {
            "orders/example/Service.java": SourceCoverage("orders/example/Service.java", {10: covered}),
            "users/example/Service.java": SourceCoverage("users/example/Service.java", {10: covered}),
        }

        result = calculate_coverage(changed, sources)

        self.assertEqual("pass", result.status)
        self.assertEqual(100.0, result.line_percentage)
        self.assertEqual(100.0, result.branch_percentage)

    def test_branch_threshold_can_fail_when_lines_pass(self) -> None:
        changed = (ChangedSource("src/main/java/example/Service.java", frozenset({10})),)
        coverage = LineCoverage(1, 0, 1, 1)
        sources = {"example/Service.java": SourceCoverage("example/Service.java", {10: coverage})}

        result = calculate_coverage(changed, sources, line_threshold=90, branch_threshold=80)

        self.assertEqual("fail", result.status)
        self.assertEqual(100.0, result.line_percentage)
        self.assertEqual(50.0, result.branch_percentage)

    def test_no_production_increment_is_not_applicable(self) -> None:
        result = calculate_coverage((), {})

        self.assertEqual("not_applicable", result.status)
        self.assertTrue(result.as_dict()["passed"])

    def test_rejects_coverage_arguments_that_skip_tests(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not skip"):
            _reject_test_skipping(["-DskipTests"])

    def test_detects_report_older_than_matching_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            source = repo / "module/src/main/java/example/Service.java"
            report = repo / "module/target/site/jacoco/jacoco.xml"
            source.parent.mkdir(parents=True)
            report.parent.mkdir(parents=True)
            source.write_text("class Service {}\n", encoding="utf-8")
            report.write_text(
                "<report><package name=\"example\"><sourcefile name=\"Service.java\">"
                "<line nr=\"1\" mi=\"0\" ci=\"1\" mb=\"0\" cb=\"0\"/>"
                "</sourcefile></package></report>",
                encoding="utf-8",
            )
            source.touch()
            report_mtime = source.stat().st_mtime - 10
            report.touch()
            import os

            os.utime(report, (report_mtime, report_mtime))
            changed = (ChangedSource("module/src/main/java/example/Service.java", frozenset({1})),)

            stale = _stale_sources(repo, changed, (report,))

            self.assertEqual(["module/src/main/java/example/Service.java"], stale)


if __name__ == "__main__":
    unittest.main()
