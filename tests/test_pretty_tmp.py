from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "skills/pretty-common/scripts"))

from pretty_tmp import (  # noqa: E402
    cleanup_registered_run,
    is_pretty_tmp_path,
    run_dir_for,
    topic_dir_for_document,
    validate_artifact_path,
    validate_run_dir,
)


class PrettyTmpTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.topic = self.root / "docs/pretty/orders"
        self.topic.mkdir(parents=True)
        self.design = self.topic / "design.md"
        self.design.write_text("# Design\n", encoding="utf-8")
        self.run_dir = run_dir_for(self.topic, "run-1")
        self.run_dir.mkdir(parents=True)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_topic_run_and_artifact_are_strictly_scoped(self) -> None:
        self.assertEqual(self.topic.resolve(), topic_dir_for_document(self.design))
        self.assertEqual(self.run_dir, validate_run_dir(self.topic, self.run_dir))
        artifact = self.run_dir / "quality.json"
        self.assertEqual(artifact, validate_artifact_path(self.run_dir, artifact))
        with self.assertRaises(ValueError):
            validate_run_dir(self.topic, self.root / "external/run-1")
        with self.assertRaises(ValueError):
            validate_run_dir(self.topic, self.topic / "tmp/../tmp/run-1")
        with self.assertRaises(ValueError):
            validate_artifact_path(self.run_dir, self.root / "other.json")

    def test_pretty_tmp_paths_are_excluded_from_git_scope(self) -> None:
        self.assertTrue(is_pretty_tmp_path("docs/pretty/orders/tmp/run-1/quality.json"))
        self.assertFalse(is_pretty_tmp_path("src/main/java/example/Service.java"))

    def test_cleanup_only_removes_registered_direct_files(self) -> None:
        manifest = self.run_dir / "design-run.json"
        evidence = self.run_dir / "evidence-summary.json"
        manifest.write_text("{}\n", encoding="utf-8")
        evidence.write_text("{}\n", encoding="utf-8")
        removed = cleanup_registered_run(
            self.topic,
            self.run_dir,
            "design-run.json",
            ["evidence-summary.json"],
        )
        self.assertEqual(("evidence-summary.json", "design-run.json"), removed)
        self.assertFalse(self.run_dir.exists())

    def test_cleanup_refuses_unregistered_file_without_deleting(self) -> None:
        manifest = self.run_dir / "design-run.json"
        manifest.write_text("{}\n", encoding="utf-8")
        rogue = self.run_dir / "rogue.json"
        rogue.write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unregistered"):
            cleanup_registered_run(self.topic, self.run_dir, "design-run.json", [])
        self.assertTrue(manifest.exists())
        self.assertTrue(rogue.exists())


if __name__ == "__main__":
    unittest.main()
