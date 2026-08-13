from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_CONTRACT = (
    ROOT
    / "skills"
    / "pretty-java-spring-core"
    / "references"
    / "workflow-contract.md"
)
PRD_SKILL = ROOT / "skills" / "pretty-writing-prd" / "SKILL.md"


class PrettyGrillingInteractionContractTest(unittest.TestCase):
    def test_grilling_questions_hide_internal_workflow_classification(self) -> None:
        workflow = WORKFLOW_CONTRACT.read_text(encoding="utf-8")
        prd_skill = PRD_SKILL.read_text(encoding="utf-8")

        for marker in (
            "直接提出业务或技术决策",
            "不要向用户复述触发判定或 Skill 编排状态",
            "需要确认一个外部合同",
            "唯一阻塞决策",
            "这是 `grilling` 要求关闭的",
        ):
            self.assertIn(marker, workflow)

        self.assertIn("直接使用共享合同的面向用户句式", prd_skill)
        self.assertIn("不暴露触发判定或 Skill 编排状态", prd_skill)

    def test_grilling_contract_contains_a_business_facing_example(self) -> None:
        workflow = WORKFLOW_CONTRACT.read_text(encoding="utf-8")

        for marker in (
            "受理成功但不生成工单",
            "ACCEPTED_NO_WORK_ORDER",
            "复用现有成功结果码",
            "是否采用推荐方案",
        ):
            self.assertIn(marker, workflow)


if __name__ == "__main__":
    unittest.main()
