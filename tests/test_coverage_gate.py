from __future__ import annotations

import argparse
import subprocess
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
    _load_changed_sources,
    _coverage_candidate_hash,
    _reject_test_skipping,
    _stale_sources,
    calculate_coverage,
    load_changed_manifest,
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

    def test_diff_ignores_pretty_topic_tmp_java(self) -> None:
        diff = """+++ b/docs/pretty/orders/tmp/run-1/Fake.java
@@ -0,0 +1,1 @@
+class Fake {}
"""
        self.assertEqual({}, parse_changed_diff(diff))

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

    def test_rejects_empty_production_java_manifest_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = Path(temporary) / "changed.json"
            manifest.write_text('{"src/main/java/example/Service.java": []}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must contain changed lines"):
                load_changed_manifest(manifest)

    def test_coverage_manifest_cannot_replace_git_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            source = repo / "src/main/java/example/Service.java"
            source.parent.mkdir(parents=True)
            source.write_text("class Service {}\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=repo, check=True)
            base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
            source.write_text("class Service { int changed; }\n", encoding="utf-8")
            manifest = Path(temporary) / "changed.json"
            manifest.write_text("{}\n", encoding="utf-8")
            args = argparse.Namespace(changed_manifest=manifest)

            with self.assertRaisesRegex(ValueError, "must exactly match the Git diff"):
                _load_changed_sources(args, repo, base)

    def test_slice_manifest_must_be_a_non_empty_subset_of_git_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            source = repo / "src/main/java/example/Service.java"
            source.parent.mkdir(parents=True)
            source.write_text("class Service { int value; }\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=repo, check=True)
            base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
            source.write_text("class Service { int value; int changed; }\n", encoding="utf-8")
            manifest = repo / "slice.json"
            manifest.write_text('{"src/main/java/example/Service.java": [1]}\n', encoding="utf-8")
            args = argparse.Namespace(changed_manifest=None, slice_manifest=manifest)

            sources = _load_changed_sources(args, repo, base)
            self.assertEqual(("src/main/java/example/Service.java",), tuple(s.path for s in sources))

            manifest.write_text('{"src/main/java/example/Service.java": [99]}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "subset of the Git diff"):
                _load_changed_sources(args, repo, base)

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

    def test_coverage_candidate_binds_report_and_thresholds(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            source = repo / "src/main/java/example/Service.java"
            report = repo / "target/jacoco.xml"
            source.parent.mkdir(parents=True)
            report.parent.mkdir(parents=True)
            source.write_text("class Service {}\n", encoding="utf-8")
            report.write_text("<report version='1'/>\n", encoding="utf-8")
            changed = (ChangedSource("src/main/java/example/Service.java", frozenset({1})),)
            first = _coverage_candidate_hash(repo, changed, (report,), 90.0, 80.0)
            report.write_text("<report version='2'/>\n", encoding="utf-8")
            second = _coverage_candidate_hash(repo, changed, (report,), 90.0, 80.0)
            relaxed = _coverage_candidate_hash(repo, changed, (report,), 80.0, 70.0)

        self.assertNotEqual(first, second)
        self.assertNotEqual(second, relaxed)


if __name__ == "__main__":
    unittest.main()
