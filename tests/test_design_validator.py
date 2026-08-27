from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/pretty-writing-design/scripts"))

from validate_design import validate_design  # noqa: E402


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
- 输入与不变量：订单编号必填，入口完成合法性校验。
- 失败语义：非法编号抛出参数异常，合法未命中返回缺失结果，仓储故障继续传播。
- 公共验证入口：OrderService#load
- 影响锚点：OrderService、OrderRepository
- 验证观察面：订单结果或缺失异常。
- Execution 交付：Java、测试
- 人工运维产物：无
## 验证与风险
验证存在和缺失结果。
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

    def test_accepts_complete_design_without_self_declared_risk_fields(self) -> None:
        self.assertEqual([], validate_design(self.design))

    def test_requires_task_traceability_fields(self) -> None:
        self.design.write_text(DESIGN.replace("- 公共验证入口：OrderService#load\n", ""), encoding="utf-8")
        self.assertIn("TASK-001 缺少字段：公共验证入口", validate_design(self.design))

    def test_requires_input_invariant_and_failure_contract(self) -> None:
        invalid = DESIGN.replace("- 输入与不变量：订单编号必填，入口完成合法性校验。\n", "")
        invalid = invalid.replace(
            "- 失败语义：非法编号抛出参数异常，合法未命中返回缺失结果，仓储故障继续传播。\n",
            "",
        )
        self.design.write_text(invalid, encoding="utf-8")
        self.assertIn("TASK-001 缺少字段：输入与不变量, 失败语义", validate_design(self.design))

    def test_rejects_low_quality_implementation_directive(self) -> None:
        invalid = DESIGN.replace(
            "保持现有职责。",
            "保持现有职责；实现时允许使用 continue 跳过非目标订单。",
        )
        self.design.write_text(invalid, encoding="utf-8")
        self.assertTrue(any("不得用普通实现指令降级" in error for error in validate_design(self.design)))

    def test_rejects_required_input_empty_fallback_contract(self) -> None:
        invalid = DESIGN.replace(
            "订单编号必填，入口完成合法性校验。",
            "订单编号必填，订单编号为空时返回空集合。",
        )
        self.design.write_text(invalid, encoding="utf-8")
        self.assertTrue(any("不得用普通实现指令降级" in error for error in validate_design(self.design)))

    def test_rejects_generic_normalization_helper_directive(self) -> None:
        invalid = DESIGN.replace(
            "保持现有职责。",
            "保持现有职责；新增 normalizeText 通用方法处理所有文本。",
        )
        self.design.write_text(invalid, encoding="utf-8")
        self.assertTrue(any("不得要求通用文本规范化 Helper" in error for error in validate_design(self.design)))

    def test_requires_task_delivery_ownership_fields(self) -> None:
        self.design.write_text(DESIGN.replace("- 人工运维产物：无\n", ""), encoding="utf-8")
        self.assertIn("TASK-001 缺少字段：人工运维产物", validate_design(self.design))

    def test_rejects_configuration_dml_as_execution_delivery(self) -> None:
        invalid = DESIGN.replace(
            "- Execution 交付：Java、测试",
            "- Execution 交付：Java、测试、事件定义配置 DML 脚本",
        )
        self.design.write_text(invalid, encoding="utf-8")
        self.assertTrue(any("不得把配置数据 DML" in error for error in validate_design(self.design)))

    def test_rejects_reverse_configuration_dml_assignment_to_execution(self) -> None:
        invalid = DESIGN.replace(
            "保持现有职责。",
            "事件定义配置 DML 由 Execution 生成。",
        )
        self.design.write_text(invalid, encoding="utf-8")
        self.assertIn("Execution 不得生成、交付或执行配置数据 DML", validate_design(self.design))

    def test_accepts_configuration_dml_as_manual_operations_artifact(self) -> None:
        valid = DESIGN.replace(
            "- 人工运维产物：无",
            "- 人工运维产物：事件定义、模板关系失效和激活配置 DML",
        )
        self.design.write_text(valid, encoding="utf-8")
        self.assertEqual([], validate_design(self.design))

    def test_accepts_structural_ddl_as_file_delivery(self) -> None:
        valid = DESIGN.replace(
            "- Execution 交付：Java、测试",
            "- Execution 交付：Java、测试、联合索引 DDL 文件",
        )
        self.design.write_text(valid, encoding="utf-8")
        self.assertEqual([], validate_design(self.design))

    def test_rejects_execution_of_structural_ddl(self) -> None:
        invalid = DESIGN.replace(
            "保持现有职责。",
            "保持现有职责；Execution 执行联合索引 DDL。",
        )
        self.design.write_text(invalid, encoding="utf-8")
        self.assertIn("Execution 只能交付 DDL 文件，不得执行或间接执行 DDL", validate_design(self.design))

    def test_requires_manual_owner_when_task_mentions_configuration_dml(self) -> None:
        invalid = DESIGN.replace(
            "- 结果：返回目标订单。",
            "- 结果：返回目标订单，并准备事件定义配置 DML。",
        )
        self.design.write_text(invalid, encoding="utf-8")
        self.assertTrue(any("必须声明人工运维产物" in error for error in validate_design(self.design)))

    def test_allows_explicit_configuration_dml_exclusion_without_manual_artifact(self) -> None:
        valid = DESIGN.replace(
            "保持现有职责。",
            "保持现有职责；Execution 不生成或执行配置数据 DML。",
        )
        self.design.write_text(valid, encoding="utf-8")
        self.assertEqual([], validate_design(self.design))

    def test_does_not_treat_java_event_definition_symbol_as_configuration_dml(self) -> None:
        valid = DESIGN.replace(
            "OrderService、OrderRepository",
            "EventDefinitionCode、OrderService、OrderRepository",
        )
        self.design.write_text(valid, encoding="utf-8")
        self.assertEqual([], validate_design(self.design))

    def test_requires_task_owner_for_configuration_dml_outside_impact_section(self) -> None:
        invalid = DESIGN.replace(
            "保持现有职责。",
            "准备事件定义配置 DML 后保持现有职责。",
        )
        self.design.write_text(invalid, encoding="utf-8")
        self.assertIn(
            "Design 提及配置数据变更时必须由 TASK 声明人工运维产物",
            validate_design(self.design),
        )

    def test_rejects_missing_prd_contract_coverage(self) -> None:
        self.design.write_text(DESIGN.replace("REQ-001、", ""), encoding="utf-8")
        self.assertIn("实施影响未覆盖 REQ-001", validate_design(self.design))

if __name__ == "__main__":
    unittest.main()
