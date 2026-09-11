from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from execution_batch import next_execution_path


class ExecutionBatchTest(unittest.TestCase):
    def test_first_execution_uses_base_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(Path(directory) / "execution.md", next_execution_path(Path(directory)))

    def test_existing_reports_get_next_immutable_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            topic = Path(directory)
            (topic / "execution.md").touch()
            (topic / "execution-002.md").touch()
            (topic / "execution-004.md").touch()
            self.assertEqual(topic / "execution-005.md", next_execution_path(topic))

    def test_missing_base_report_does_not_reuse_history(self):
        with tempfile.TemporaryDirectory() as directory:
            topic = Path(directory)
            (topic / "execution-002.md").touch()
            self.assertEqual(topic / "execution-003.md", next_execution_path(topic))


if __name__ == "__main__":
    unittest.main()
