from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/pretty-writing-design/scripts"
sys.path.insert(0, str(SCRIPTS))

from design_run import (  # noqa: E402
    build_evidence_summary,
    bind_evidence_candidate,
    design_candidate_hash,
    evidence_staleness_errors,
    freeze_inputs,
    frozen_input_errors,
    _claim_artifact,
    _cleanup_design_run,
)


PRD = """# PRD
## 背景与问题
问题。
## 目标与非目标
目标。
## 用户与场景
场景。
## 需求
### REQ-001：查询订单
查询订单。
## 验收标准
### AC-001：返回订单
返回订单。
"""

DESIGN = """# Design
## 设计结论
复用查询入口。
## 方案全景
查询。
## 关键设计与权衡
保持边界。
## 设计边界
不扩展合同。
## 实施影响
### 变更职责链路
入口到规则所有者。
### TASK-001：返回订单
- 覆盖需求：REQ-001、AC-001
- 结果：返回订单。
- 输入与不变量：订单编号必填。
- 失败语义：非法输入失败，合法缺失可区分，依赖故障传播。
- 公共验证入口：OrderService#load
- 影响锚点：OrderService
- 验证观察面：返回值或异常。
- Execution 交付：Java、测试
- 人工运维产物：无
## 验证与风险
覆盖成功与失败。
"""


class DesignRunTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.topic = self.root / "docs/pretty/example"
        self.topic.mkdir(parents=True)
        (self.root / "src/main/java/example").mkdir(parents=True)
        (self.root / "src/main/resources").mkdir(parents=True)
        self.prd = self.topic / "prd.md"
        self.design = self.topic / "design.md"
        self.prd.write_text(PRD, encoding="utf-8")
        self.design.write_text(DESIGN, encoding="utf-8")
        (self.root / "src/main/java/example/Orders.java").write_text(
            "@RestController\n@GetMapping(\"/orders\")\nclass Orders {}\n", encoding="utf-8"
        )
        (self.root / "src/main/resources/application.yml").write_text(
            "server.port: 8081\n", encoding="utf-8"
        )
        (self.root / "schema.sql").write_text("CREATE TABLE orders (id bigint);\n", encoding="utf-8")
        (self.topic / "tmp/existing").mkdir(parents=True)
        (self.topic / "tmp/existing/fake.java").write_text("@RestController class Fake {}\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_freeze_and_evidence_summary_bind_one_run(self) -> None:
        run_dir = self.topic / "tmp/run-1"
        manifest = freeze_inputs(self.prd, self.design, run_dir, run_id="run-1")
        self.assertEqual(manifest, freeze_inputs(self.prd, self.design, run_dir, run_id="run-1"))
        self.assertEqual([], frozen_input_errors(manifest))
        summary = build_evidence_summary(self.prd, self.design, manifest)
        self.assertEqual("run-1", summary["run_id"])
        self.assertEqual([], summary["traceability"]["unmapped"])
        self.assertTrue(summary["repository"]["entry_points"])
        self.assertTrue(summary["repository"]["ports"])
        self.assertTrue(summary["repository"]["schemas"])

    def test_design_edits_do_not_invalidate_input_freeze_but_candidate_does(self) -> None:
        manifest = freeze_inputs(self.prd, self.design, self.topic / "tmp/run-2", run_id="run-2")
        summary = build_evidence_summary(self.prd, self.design, manifest)
        self.design.write_text(DESIGN + "\n补充取舍。\n", encoding="utf-8")
        self.assertEqual([], frozen_input_errors(manifest))
        self.assertTrue(evidence_staleness_errors(summary, manifest, self.prd, self.design))

    def test_candidate_binding_updates_hash_without_rescanning_sources(self) -> None:
        run_dir = self.topic / "tmp/run-bind"
        manifest = freeze_inputs(self.prd, self.design, run_dir, run_id="run-bind")
        evidence_path = run_dir / "evidence-summary.json"
        evidence_path.write_text(json.dumps(build_evidence_summary(self.prd, None, manifest)), encoding="utf-8")
        bound = bind_evidence_candidate(evidence_path, self.prd, self.design)
        self.assertEqual([], evidence_staleness_errors(bound, manifest, self.prd, self.design))
        self.assertEqual([], bound["traceability"]["unmapped"])
        self.assertEqual(design_candidate_hash(DESIGN, PRD), bound["candidate_sha256"])

    def test_tampered_manifest_cannot_be_reused(self) -> None:
        run_dir = self.topic / "tmp/run-tamper"
        manifest = freeze_inputs(self.prd, self.design, run_dir, run_id="run-tamper")
        manifest["run_id"] = "other-run"
        (run_dir / "design-run.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.assertTrue(frozen_input_errors(manifest))

    def test_external_run_directory_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "temporary run"):
            freeze_inputs(self.prd, self.design, self.root / "external", run_id="run-external")

    def test_default_run_directory_is_topic_local(self) -> None:
        manifest = freeze_inputs(self.prd, self.design, run_id="run-default")
        self.assertEqual("docs/pretty/example/tmp/run-default", manifest["run_dir"])

    def test_cleanup_removes_only_registered_design_artifacts(self) -> None:
        run_dir = self.topic / "tmp/run-cleanup"
        manifest = freeze_inputs(self.prd, self.design, run_dir, run_id="run-cleanup")
        evidence = run_dir / "evidence-summary.json"
        _claim_artifact(run_dir / "design-run.json", evidence)
        evidence.write_text(json.dumps(build_evidence_summary(self.prd, self.design, manifest)), encoding="utf-8")
        _cleanup_design_run(run_dir / "design-run.json")
        self.assertFalse(run_dir.exists())

if __name__ == "__main__":
    unittest.main()
