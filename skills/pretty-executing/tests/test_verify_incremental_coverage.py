#!/usr/bin/env python3
"""Tests for incremental JaCoCo calculation and threshold selection."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from verify_incremental_coverage import (
    ChangedSource,
    CoverageBuild,
    LineCoverage,
    SourceCoverage,
    _maven_coverage_command,
    calculate,
    changed_sources,
    project_thresholds,
)


class VerifyIncrementalCoverageTest(unittest.TestCase):
    @patch("verify_incremental_coverage._run_git")
    def test_changed_sources_limits_git_queries_to_requested_paths(self, run_git):
        path = "orders/src/main/java/example/Handler.java"
        run_git.side_effect = [
            f"+++ b/{path}\n@@ -0,0 +10,1 @@\n+return result;\n",
            "",
        ]

        changed = changed_sources(Path("/repo"), "base", (path,))

        self.assertEqual((ChangedSource(path, frozenset({10})),), changed)
        self.assertEqual(
            [
                call(Path("/repo"), ["diff", "--no-ext-diff", "--unified=0", "base", "--", path]),
                call(Path("/repo"), ["ls-files", "--others", "--exclude-standard", "--", path]),
            ],
            run_git.call_args_list,
        )

    def test_calculate_reports_missed_lines_and_partial_branches(self):
        changed = (ChangedSource("module/src/main/java/example/Handler.java", frozenset({10, 11})),)
        sources = {
            "example/Handler.java": SourceCoverage(
                "example/Handler.java",
                {
                    10: LineCoverage(0, 2, 0, 0),
                    11: LineCoverage(3, 0, 1, 1),
                },
            )
        }

        result = calculate(changed, sources, line_threshold=90.0, branch_threshold=80.0)

        self.assertEqual("fail", result.status)
        self.assertEqual(("module/src/main/java/example/Handler.java:10",), result.missed_lines)
        self.assertEqual(
            ("module/src/main/java/example/Handler.java:11 (1/2)",),
            result.partial_branch_lines,
        )

    def test_thresholds_only_use_affected_module_and_its_parents(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.write_pom(repo / "pom.xml", line="0.70", branch="0.60")
            self.write_pom(repo / "orders" / "pom.xml", line="0.91", branch="0.81")
            self.write_pom(repo / "unrelated" / "pom.xml", line="0.99", branch="0.95")
            source = repo / "orders" / "src" / "main" / "java" / "Order.java"
            source.parent.mkdir(parents=True)
            source.touch()

            thresholds = project_thresholds(repo, ("orders/src/main/java/Order.java",))
            repository_thresholds = project_thresholds(repo)

        self.assertEqual((91.0, 81.0), thresholds)
        self.assertEqual((99.0, 95.0), repository_thresholds)

    @patch("verify_incremental_coverage._executable", return_value=["mvn"])
    def test_maven_command_uses_writable_temp_repository_by_default(self, _executable):
        with tempfile.TemporaryDirectory() as directory:
            command = _maven_coverage_command(
                Path(directory),
                CoverageBuild((), ("test",), ("org.jacoco:jacoco-maven-plugin:report",)),
            )

        repository_argument = next(
            argument for argument in command if argument.startswith("-Dmaven.repo.local=")
        )
        repository = Path(repository_argument.split("=", 1)[1])
        self.assertTrue(repository.is_relative_to(Path(tempfile.gettempdir()).resolve()))
        self.assertNotIn("/.m2/", repository.as_posix())

    @patch("verify_incremental_coverage._executable", return_value=["mvn"])
    def test_maven_command_preserves_explicit_repository(self, _executable):
        explicit_repository = "/private/tmp/project-maven-repository"
        command = _maven_coverage_command(
            Path("/repo"),
            CoverageBuild(
                (f"-Dmaven.repo.local={explicit_repository}",),
                ("test",),
                ("report",),
            ),
        )

        self.assertEqual(
            1,
            sum(argument.startswith("-Dmaven.repo.local=") for argument in command),
        )
        self.assertIn(f"-Dmaven.repo.local={explicit_repository}", command)

    @patch("verify_incremental_coverage._executable", return_value=["mvn"])
    def test_maven_command_preserves_split_define_repository(self, _executable):
        explicit_repository = "maven.repo.local=/private/tmp/project-maven-repository"
        command = _maven_coverage_command(
            Path("/repo"),
            CoverageBuild(("--define", explicit_repository), (), ()),
        )

        self.assertEqual(0, sum(argument.startswith("-Dmaven.repo.local=") for argument in command))
        self.assertEqual(("--define", explicit_repository), tuple(command[1:3]))

    @staticmethod
    def write_pom(path: Path, line: str, branch: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            """<project><build><plugins><plugin><configuration><rules><rule><limits>
            <limit><counter>LINE</counter><minimum>{line}</minimum></limit>
            <limit><counter>BRANCH</counter><minimum>{branch}</minimum></limit>
            </limits></rule></rules></configuration></plugin></plugins></build></project>
            """.format(line=line, branch=branch),
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
