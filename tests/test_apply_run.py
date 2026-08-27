from __future__ import annotations

import json
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/pretty-executing/scripts"))

from apply_run import (  # noqa: E402
    ApplyStartRequest,
    ApplyFreezeRequest,
    checkpoint_apply,
    complete_apply,
    cleanup_apply,
    freeze_apply,
    record_objective_gate,
    resume_apply,
    register_apply_artifact,
    record_slice_coverage,
    SliceCoverageRequest,
    start_apply,
    start_review,
)
from evidence_binding import evidence_sha256  # noqa: E402


DESIGN = """# Example Design
## 实施影响
### TASK-001：返回订单
- 结果：返回订单。
- 输入与不变量：订单编号必填。
- 失败语义：非法输入、合法缺失和依赖故障可区分。
- 公共验证入口：OrderService#load
- 影响锚点：OrderService
- 验证观察面：返回值或异常。
- Execution 交付：Java、测试
- 人工运维产物：无
"""

CONTRACT_PREFLIGHT = {
    area: {"status": "clear", "evidence": [f"design.md#{area}"]}
    for area in (
        "module_boundaries",
        "runtime_semantics",
        "verification_surface",
        "delivery_ownership",
    )
}


class ApplyRunTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.topic = self.root / "docs/pretty/example"
        self.topic.mkdir(parents=True)
        self.design = self.topic / "design.md"
        self.design.write_text(DESIGN, encoding="utf-8")
        self.source = self.root / "src/main/java/example/Service.java"
        self.source.parent.mkdir(parents=True)
        self.source.write_text("class Service {}\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=self.root, check=True)
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=self.root, check=True)
        self.run_dir = self.topic / "tmp/apply-run"
        self.run_dir.mkdir(parents=True)
        self.matrix = self.run_dir / "execution-matrix.json"
        self.matrix.write_text(json.dumps({
            "contract_preflight": CONTRACT_PREFLIGHT,
            "tasks": [{"id": "TASK-001"}],
        }) + "\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def request(self) -> ApplyStartRequest:
        return ApplyStartRequest(
            repo=self.root,
            topic="example",
            design=self.design,
            execution_matrix=self.matrix,
            state_path=self.run_dir / "execution-state.json",
            runtime_paths=("src/main/java/example/Service.java",),
        )

    def test_start_checkpoint_and_resume_reject_external_drift(self) -> None:
        request = self.request()
        manifest = start_apply(request)
        self.assertEqual("in_progress", manifest["status"])

        self.source.write_text("class Service { int changed; }\n", encoding="utf-8")
        checkpoint_apply(request.state_path, self.root)
        self.assertEqual([], resume_apply(request.state_path, self.root, self.design, self.matrix))

        self.source.write_text("class Service { int external; }\n", encoding="utf-8")
        errors = resume_apply(request.state_path, self.root, self.design, self.matrix)
        self.assertTrue(any("registered runtime path changed" in error for error in errors))

    def test_start_rejects_dirty_runtime_path(self) -> None:
        self.source.write_text("class Service { int dirty; }\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "runtime paths must be clean"):
            start_apply(self.request())

    def test_start_rejects_missing_contract_executability_preflight(self) -> None:
        self.matrix.write_text(json.dumps({"tasks": [{"id": "TASK-001"}]}) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "contract_preflight"):
            start_apply(self.request())

    def test_start_rejects_lowered_slice_coverage_thresholds(self) -> None:
        self.matrix.write_text(json.dumps({
            "contract_preflight": CONTRACT_PREFLIGHT,
            "coverage_policy": {"line_threshold": 80, "branch_threshold": 70},
            "tasks": [{"id": "TASK-001"}],
        }) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "cannot lower"):
            start_apply(self.request())

    def test_start_rejects_external_matrix_or_state_path(self) -> None:
        request = self.request()
        request = ApplyStartRequest(
            request.repo,
            request.topic,
            request.design,
            self.root / "external" / "execution-matrix.json",
            self.root / "external" / "execution-state.json",
            request.runtime_paths,
        )
        request.execution_matrix.parent.mkdir(parents=True)
        request.execution_matrix.write_text(self.matrix.read_text(encoding="utf-8"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "temporary run"):
            start_apply(request)

    def test_frozen_candidate_converges_parallel_gate_and_review_once(self) -> None:
        request = self.request()
        start_apply(request)
        frozen = freeze_apply(ApplyFreezeRequest(
            request.state_path, self.root, self.design, self.matrix, "candidate-1"
        ))
        objective_gate = {
            "quality_candidate_sha256": "candidate-1",
            "build_candidate_sha256": "build-candidate",
            "test_evidence_sha256": "test-evidence",
            "coverage_evidence_sha256": "coverage-evidence",
        }
        record_objective_gate(request.state_path, self.root, "candidate-1", objective_gate)
        review_request = start_review(request.state_path)
        self.assertEqual("candidate-1", review_request["candidate_sha256"])
        review = {
            "run_id": frozen["run_id"],
            "review_session_id": review_request["review_session_id"],
            "candidate_sha256": "candidate-1",
            "reviewer": "reviewer-1",
            "independent": True,
            "pre_review_gate": objective_gate,
            "blocking_findings": [],
        }
        completion_path = self.run_dir / "completion.json"
        completion = complete_apply(request.state_path, self.root, review, completion_path)

        self.assertEqual("completed", completion["status"])
        self.assertEqual(objective_gate, completion["objective_gate"])
        self.assertFalse(request.state_path.exists())
        self.assertFalse(self.run_dir.exists())

    def test_freeze_requires_each_behavior_slice_to_close_with_coverage(self) -> None:
        self.matrix.write_text(json.dumps({
            "contract_preflight": CONTRACT_PREFLIGHT,
            "coverage_policy": {
                "line_threshold": 90,
                "branch_threshold": 80,
                "gate_each_slice": True,
                "gate_before_next_slice": True,
            },
            "tasks": [{
                "id": "TASK-001",
                "behavior_slices": [
                    {"id": "SLICE-001", "paths": ["src/main/java/example/Service.java"]},
                    {"id": "SLICE-002", "paths": ["src/main/java/example/Service.java"]},
                ],
            }],
        }) + "\n", encoding="utf-8")
        request = self.request()
        state = start_apply(request)
        self.assertEqual("SLICE-001", state["active_slice"])
        with self.assertRaisesRegex(ValueError, "has no coverage evidence"):
            freeze_apply(ApplyFreezeRequest(
                request.state_path, self.root, self.design, self.matrix, "candidate-1"
            ))

        def close_slice(slice_id: str) -> None:
            path = self.run_dir / f"coverage-{slice_id}.json"
            register_apply_artifact(request.state_path, path)
            payload = {
                "scope": "slice",
                "slice_id": slice_id,
                "status": "pass",
                "passed": True,
                "changed_files": 1,
                "changed_lines": 1,
                "missing_sources": [],
                "line_threshold": 90.0,
                "branch_threshold": 80.0,
                "line_percentage": 100.0,
                "branch_percentage": 100.0,
                "start_head": state["start_head"],
                "design_sha256": state["design_sha256"],
                "source_sha256": {
                    "src/main/java/example/Service.java": hashlib.sha256(
                        self.source.read_bytes()
                    ).hexdigest()
                },
                "candidate_sha256": f"candidate-{slice_id}",
            }
            payload["evidence_sha256"] = evidence_sha256(payload)
            path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            record_slice_coverage(SliceCoverageRequest(
                request.state_path, self.root, self.design, slice_id, path
            ))

        close_slice("SLICE-001")
        self.assertEqual("SLICE-002", json.loads(request.state_path.read_text())["active_slice"])
        with self.assertRaisesRegex(ValueError, "is not coverage-closed"):
            freeze_apply(ApplyFreezeRequest(
                request.state_path, self.root, self.design, self.matrix, "candidate-1"
            ))
        close_slice("SLICE-002")
        frozen = freeze_apply(ApplyFreezeRequest(
            request.state_path, self.root, self.design, self.matrix, "candidate-1"
        ))
        self.assertEqual("frozen", frozen["phase"])

    def test_checkpoint_rejects_changes_outside_active_behavior_slice(self) -> None:
        other = self.root / "src/main/java/example/Adapter.java"
        other.write_text("class Adapter {}\n", encoding="utf-8")
        subprocess.run(["git", "add", str(other.relative_to(self.root))], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "baseline-adapter"], cwd=self.root, check=True)
        self.matrix.write_text(json.dumps({
            "contract_preflight": CONTRACT_PREFLIGHT,
            "tasks": [{
                "id": "TASK-001",
                "behavior_slices": [{"id": "SLICE-001", "paths": [
                    "src/main/java/example/Service.java",
                ]}],
            }],
        }) + "\n", encoding="utf-8")
        request = ApplyStartRequest(
            self.root,
            "example",
            self.design,
            self.matrix,
            self.run_dir / "execution-state.json",
            (
                "src/main/java/example/Service.java",
                "src/main/java/example/Adapter.java",
            ),
        )
        start_apply(request)
        self.source.write_text("class Service { int changed; }\n", encoding="utf-8")
        other.write_text("class Adapter { int changed; }\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "outside active behavior slice"):
            checkpoint_apply(request.state_path, self.root)

    def test_cleanup_refuses_unregistered_files(self) -> None:
        request = self.request()
        start_apply(request)
        rogue = self.run_dir / "rogue.json"
        rogue.write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unregistered"):
            cleanup_apply(request.state_path)
        self.assertTrue(rogue.exists())

    def test_registered_evidence_is_removed_with_run(self) -> None:
        request = self.request()
        start_apply(request)
        evidence = self.run_dir / "quality.json"
        register_apply_artifact(request.state_path, evidence)
        evidence.write_text("{}\n", encoding="utf-8")
        cleanup_apply(request.state_path)
        self.assertFalse(self.run_dir.exists())

    def test_completion_rejects_receipt_from_another_run(self) -> None:
        request = self.request()
        start_apply(request)
        freeze_apply(ApplyFreezeRequest(
            request.state_path, self.root, self.design, self.matrix, "candidate-1"
        ))
        objective_gate = {
            "quality_candidate_sha256": "candidate-1",
            "build_candidate_sha256": "build-candidate",
            "test_evidence_sha256": "test-evidence",
            "coverage_evidence_sha256": "coverage-evidence",
        }
        record_objective_gate(request.state_path, self.root, "candidate-1", objective_gate)
        review_request = start_review(request.state_path)
        review = {
            "run_id": "another-run",
            "review_session_id": review_request["review_session_id"],
            "candidate_sha256": "candidate-1",
            "reviewer": "reviewer-1",
            "independent": True,
            "pre_review_gate": objective_gate,
            "blocking_findings": [],
        }
        with self.assertRaisesRegex(ValueError, "review receipt does not match the Apply run"):
            complete_apply(request.state_path, self.root, review, self.topic / "completion.json")


if __name__ == "__main__":
    unittest.main()
