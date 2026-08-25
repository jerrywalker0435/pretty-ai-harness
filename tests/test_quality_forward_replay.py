from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "benchmarks/quality-forward/run_replay.py"
SPEC = importlib.util.spec_from_file_location("quality_forward_replay", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
REPLAY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = REPLAY
SPEC.loader.exec_module(REPLAY)


class QualityForwardReplayTest(unittest.TestCase):
    def test_classifies_revoked_oauth_token_as_infrastructure_error(self) -> None:
        messages = (
            "HTTP 401: token_revoked",
            "error code: refresh_token_invalidated",
            "Please log out and sign in again.",
        )
        for message in messages:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as temporary_directory:
                log = Path(temporary_directory) / "agent.log"
                log.write_text(message, encoding="utf-8")

                self.assertEqual("Codex authentication expired", REPLAY._infrastructure_error(log))

    def test_ignores_ordinary_agent_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            log = Path(temporary_directory) / "agent.log"
            log.write_text("Design validation failed", encoding="utf-8")

            self.assertIsNone(REPLAY._infrastructure_error(log))

    def test_missing_command_is_reported_as_infrastructure_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            log = workspace / "missing.log"

            exit_code = REPLAY._run(
                ["pretty-command-that-does-not-exist"],
                workspace,
                log,
                timeout=1,
            )

            self.assertEqual(127, exit_code)
            self.assertEqual("Command failed to start", REPLAY._infrastructure_error(log))

    def test_timeout_is_reported_as_infrastructure_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            log = workspace / "timeout.log"

            exit_code = REPLAY._run(
                [sys.executable, "-c", "import time; time.sleep(1)"],
                workspace,
                log,
                timeout=0.01,
            )

            self.assertEqual(124, exit_code)
            self.assertEqual("Command timed out", REPLAY._infrastructure_error(log))

    def test_behavior_oracle_failure_prevents_a_replay_pass(self) -> None:
        result = REPLAY.ReplayResult(
            scenario="branch-contract",
            repetition=1,
            workspace="/tmp/replay",
            design_agent_exit=0,
            design_gate_exit=0,
            execution_agent_exit=0,
            execution_gate_exit=0,
            oracle_exit=1,
            infrastructure_error=None,
            semantic_errors=(),
        )

        self.assertFalse(result.passed)

    def test_every_scenario_has_an_evaluator_owned_oracle(self) -> None:
        scenarios = REPLAY._load_scenarios(set())

        self.assertEqual(
            {str(scenario["id"]) for scenario in scenarios},
            set(REPLAY.ORACLE_SOURCES),
        )
        for scenario_id, source in REPLAY.ORACLE_SOURCES.items():
            with self.subTest(scenario=scenario_id):
                self.assertIn("class EvaluatorAcceptanceTest", source)
                self.assertIn("@Test", source)

    def test_behavior_oracle_forces_test_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo = Path(temporary_directory)
            log = repo / "oracle.log"
            scenario = {"id": "branch-contract"}
            environment = REPLAY.ReplayEnvironment(repo, repo / "evidence", "branch-contract", 10.0)

            with mock.patch.object(REPLAY, "_run", return_value=0) as run:
                exit_code = REPLAY._run_behavior_oracle(environment, scenario, log)

            self.assertEqual(0, exit_code)
            command = run.call_args.args[0]
            self.assertIn("-DskipTests=false", command)
            self.assertIn("-Dmaven.test.failure.ignore=false", command)
            self.assertIn("-DfailIfNoTests=true", command)
            self.assertTrue(
                (repo / "src/test/java/benchmark/EvaluatorAcceptanceTest.java").is_file()
            )

    def test_worker_exception_is_isolated_as_infrastructure_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_root = Path(temporary_directory)
            scenario = {"id": "branch-contract"}

            with mock.patch.object(REPLAY, "run_one", side_effect=RuntimeError("boom")):
                result = REPLAY._run_job((output_root, scenario, 1, 1.0))

            self.assertEqual("Benchmark worker failed: RuntimeError", result.infrastructure_error)
            self.assertFalse(result.passed)
            self.assertTrue(
                (output_root / "branch-contract-1/infrastructure-error.log").is_file()
            )


if __name__ == "__main__":
    unittest.main()
