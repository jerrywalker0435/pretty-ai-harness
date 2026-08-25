from __future__ import annotations

import json
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/pretty-writing-design/scripts"))

from validate_design import design_candidate_hash, validate_design  # noqa: E402

PRD = """# Example PRD
## 背景与问题
背景。
## 目标与非目标
目标。
## 用户与场景
场景。
## 需求
### REQ-001：返回订单
返回订单。
## 验收标准
### AC-001：订单可见
返回订单。
"""

DESIGN = """# Example Design
## 设计结论
复用订单用例。
## 方案全景
从入口查询订单。
## 关键设计与权衡
保持现有职责。
## 设计边界
不改变外部合同。
## 实施影响
### 变更职责链路
订单入口到订单规则所有者。
### TASK-001：返回订单
- 覆盖需求：REQ-001、AC-001
- 结果：返回目标订单。
- 公共验证入口：OrderService#load
- 影响锚点：OrderService、OrderRepository
- 验证观察面：订单结果或缺失异常。
## 验证与风险
验证存在和缺失结果。
- Design 风险级别：低
- Design 风险类型：无
- 合同来源：无
"""


class DesignValidatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.topic = Path(self.temporary.name) / "docs/pretty/example"
        self.topic.mkdir(parents=True)
        self.prd = self.topic / "prd.md"
        self.design = self.topic / "design.md"
        self.prd.write_text(PRD, encoding="utf-8")
        self.design.write_text(DESIGN, encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_accepts_complete_low_risk_design(self) -> None:
        self.assertEqual([], validate_design(self.design))

    def test_requires_task_traceability_fields(self) -> None:
        self.design.write_text(DESIGN.replace("- 公共验证入口：OrderService#load\n", ""), encoding="utf-8")
        self.assertIn("TASK-001 缺少字段：公共验证入口", validate_design(self.design))

    def test_rejects_missing_prd_contract_coverage(self) -> None:
        self.design.write_text(DESIGN.replace("REQ-001、", ""), encoding="utf-8")
        self.assertIn("实施影响未覆盖 REQ-001", validate_design(self.design))

    def test_high_risk_design_requires_matching_independent_review(self) -> None:
        high_risk = DESIGN.replace(
            "- Design 风险级别：低\n- Design 风险类型：无\n- 合同来源：无",
            "- Design 风险级别：高\n- Design 风险类型：事务与幂等\n- 合同来源：无",
        )
        self.design.write_text(high_risk, encoding="utf-8")
        self.assertIn("高风险 Design 需要独立 Reviewer 证据", validate_design(self.design))
        evidence = self.topic / "review.json"
        evidence.write_text(json.dumps({
            "candidate_sha256": design_candidate_hash(high_risk, PRD),
            "reviewer": "reviewer-1",
            "independent": True,
            "contract_sources_sha256": {},
            "blocking_findings": [],
        }), encoding="utf-8")
        self.assertEqual([], validate_design(self.design, evidence))

    def test_review_candidate_binds_contract_source_content(self) -> None:
        high_risk = DESIGN.replace(
            "- Design 风险级别：低\n- Design 风险类型：无\n- 合同来源：无",
            "- Design 风险级别：高\n- Design 风险类型：公共合同\n- 合同来源：src/main/resources/schema.json",
        )
        self.design.write_text(high_risk, encoding="utf-8")
        contract = self.topic.parents[2] / "src/main/resources/schema.json"
        contract.parent.mkdir(parents=True)
        contract.write_text('{"type":"object"}\n', encoding="utf-8")
        source_name = "src/main/resources/schema.json"
        source_content = contract.read_text(encoding="utf-8")
        source_hash = hashlib.sha256(source_content.encode("utf-8")).hexdigest()
        evidence = self.topic / "review.json"
        evidence.write_text(json.dumps({
            "candidate_sha256": design_candidate_hash(high_risk, PRD, {source_name: source_content}),
            "contract_sources_sha256": {source_name: source_hash},
            "reviewer": "reviewer-1",
            "independent": True,
            "blocking_findings": [],
        }), encoding="utf-8")
        self.assertEqual([], validate_design(self.design, evidence, (contract,)))
        contract.write_text('{"type":"string"}\n', encoding="utf-8")
        self.assertTrue(any("候选不匹配" in error for error in validate_design(self.design, evidence, (contract,))))


if __name__ == "__main__":
    unittest.main()
