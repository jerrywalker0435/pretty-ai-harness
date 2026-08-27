from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMMON = ROOT / "skills/pretty-common"
sys.path.insert(0, str(COMMON / "scripts"))

from quality_registry import RISK_OWNERS, RULES  # noqa: E402
from quality_resolver import _matrix_slice_paths, resolve_slice  # noqa: E402
from validate_pretty_consistency import consistency_errors  # noqa: E402


class QualityResolverTest(unittest.TestCase):
    def test_java_production_slice_receives_all_shared_rules_and_conservative_risks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            source = repo / "src/main/java/example/OrderGatewayAdapter.java"
            source.parent.mkdir(parents=True)
            source.write_text(
                "final class OrderGatewayAdapter implements Gateway { String load() { return null; } }\n",
                encoding="utf-8",
            )
            result = resolve_slice(repo, "SLICE-001", ["src/main/java/example/OrderGatewayAdapter.java"])

        self.assertEqual({rule.code for rule in RULES}, set(result["rules"]))
        risks = {entry["id"]: entry["owner"] for entry in result["risks"]}
        self.assertEqual(RISK_OWNERS["JAVA_OOD"], risks["JAVA_OOD"])
        self.assertEqual(RISK_OWNERS["JAVA_RUNTIME_RISK"], risks["JAVA_RUNTIME_RISK"])
        self.assertEqual(RISK_OWNERS["BEHAVIOR_TEST"], risks["BEHAVIOR_TEST"])
        self.assertEqual(RISK_OWNERS["MODULE_BOUNDARY"], risks["MODULE_BOUNDARY"])
        self.assertEqual(["clean-code-guard"], result["guards"])

    def test_matrix_paths_default_to_task_scope(self) -> None:
        matrix = {
            "tasks": [{
                "id": "TASK-001",
                "production_files": ["src/main/java/example/Service.java"],
                "test_files": ["src/test/java/example/ServiceTest.java"],
                "behavior_slices": [{"id": "SLICE-001"}],
            }]
        }
        self.assertEqual(
            {
                "src/main/java/example/Service.java",
                "src/test/java/example/ServiceTest.java",
            },
            _matrix_slice_paths(matrix)["SLICE-001"],
        )

    def test_pretty_bundle_has_no_duplicate_or_conflicting_registry(self) -> None:
        errors = consistency_errors(
            COMMON,
            design_skill=ROOT / "skills/pretty-writing-design/SKILL.md",
            executing_skill=ROOT / "skills/pretty-executing/SKILL.md",
        )
        self.assertEqual([], errors)

    def test_pretty_bundle_requires_non_waivable_normalization_helper_rule(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            common = Path(temporary) / "pretty-common"
            shutil.copytree(COMMON, common)
            principles = common / "references/quality-principles.md"
            principles.write_text(
                principles.read_text(encoding="utf-8").replace(
                    "GENERIC-NORMALIZATION-HELPER", "REMOVED-RULE"
                ),
                encoding="utf-8",
            )
            errors = consistency_errors(common)
        self.assertIn("shared principles must define GENERIC-NORMALIZATION-HELPER as non-waivable", errors)


if __name__ == "__main__":
    unittest.main()
