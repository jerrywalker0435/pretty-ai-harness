#!/usr/bin/env python3
"""Regression tests for the Design contract validator."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from validate_design import validate_design_document


VALID_DESIGN = """# Example Design

## 设计结论

采用现有入口扩展结果合同。

## 方案全景

职责关系保持不变。

## 关键设计与权衡

没有需要独立记录的技术权衡。

## 设计边界

不改变外部协议所有权。

## 实施影响

### 变更职责链路

入口 Handler#execute 到规则所有者 Rule#apply。

### TASK-001：返回结果

- 对应需求：REQ-001、AC-001
- 结果：返回可观察的领域结果
- 输入与不变量：请求标识符必填
- 失败语义：查询未命中与远端失败可区分
- 验证观察面：结果和异常

## 验证与风险

TASK-001 由公共行为测试验证；无额外风险。

## Executing交付

### TASK-001

- 公共验证入口：现有；module/src/test/java/example/HandlerTest.java#returnsResult
- 影响锚点：现有 module/src/main/java/example/Handler.java#execute；新增 module/src/main/java/example/Rule.java#apply
- Execution 交付：构建模块 module；Modify `module/src/main/java/example/Handler.java`；Add `module/src/main/java/example/Rule.java`；Test `module/src/test/java/example/HandlerTest.java`
- 人工运维产物：无
"""


class ValidateDesignHandoffTest(unittest.TestCase):
    def test_separated_execution_handoff_is_valid(self):
        self.assertEqual([], validate_design_document(VALID_DESIGN))

    def test_responsibility_chain_belongs_to_human_review(self):
        chain = "### 变更职责链路\n\n入口 Handler#execute 到规则所有者 Rule#apply。\n\n"
        document = VALID_DESIGN.replace(chain, "").replace(
            "## Executing交付\n\n", "## Executing交付\n\n" + chain
        )

        errors = validate_design_document(document)

        self.assertIn("实施影响需要供人工评审的变更职责链路", errors)
        self.assertIn("变更职责链路应位于实施影响，不得放入 Executing交付", errors)

    def test_responsibility_chain_cannot_be_duplicated_in_handoff(self):
        document = VALID_DESIGN.replace(
            "## Executing交付\n\n",
            "## Executing交付\n\n### 变更职责链路\n\n入口到规则所有者。\n\n",
        )

        errors = validate_design_document(document)

        self.assertIn("变更职责链路应位于实施影响，不得放入 Executing交付", errors)

    def test_root_level_file_is_a_valid_repository_relative_path(self):
        document = VALID_DESIGN.replace(
            "module/src/test/java/example/HandlerTest.java#returnsResult",
            "HandlerTest.java#returnsResult",
        )

        self.assertEqual([], validate_design_document(document))

    def test_public_entry_requires_existing_or_new_path_symbol(self):
        document = VALID_DESIGN.replace(
            "现有；module/src/test/java/example/HandlerTest.java#returnsResult",
            "HandlerTest#returnsResult",
        )

        errors = validate_design_document(document)

        self.assertIn("TASK-001 的公共验证入口必须标记现有或新增", errors)
        self.assertIn("TASK-001 的公共验证入口必须包含仓库相对路径#symbol", errors)

    def test_execution_delivery_requires_build_owner_and_file_action(self):
        document = VALID_DESIGN.replace(
            "构建模块 module；Modify `module/src/main/java/example/Handler.java`；Add `module/src/main/java/example/Rule.java`；Test `module/src/test/java/example/HandlerTest.java`",
            "module/src/main/java/example/Handler.java",
        )

        errors = validate_design_document(document)

        self.assertIn("TASK-001 的 Execution 交付必须声明构建根或模块", errors)
        self.assertIn("TASK-001 的 Execution 交付必须标记 Add/Modify/Test/DDL", errors)

    def test_handoff_task_ids_must_match_impact(self):
        document = VALID_DESIGN.replace("### TASK-001\n\n- 公共验证入口", "### TASK-002\n\n- 公共验证入口")

        errors = validate_design_document(document)

        self.assertIn("Executing交付的 TASK ID 必须与实施影响一致且顺序相同", errors)

    def test_execution_content_cannot_remain_in_impact(self):
        document = VALID_DESIGN.replace(
            "- 验证观察面：结果和异常",
            "- 验证观察面：结果和异常\n- 公共验证入口：现有；HandlerTest.java#returnsResult",
        )

        errors = validate_design_document(document)

        self.assertIn("实施影响不得包含 Executing交付字段", errors)


class ValidateExternalVerificationTest(unittest.TestCase):
    def with_risk(self, risk):
        return VALID_DESIGN.replace("TASK-001 由公共行为测试验证；无额外风险。", risk)

    def test_external_requirements_without_manual_owner_are_rejected(self):
        for risk in (
            "TASK-001 需要应用单元测试及真实事务/唯一约束集成测试。",
            "TASK-001 需要 repository 查询集成测试。",
            "执行阶段以同店同桌单日数据验证执行计划。",
            "TASK-001 必须通过 Testcontainers 验证提交失败。",
        ):
            with self.subTest(risk=risk):
                self.assertTrue(validate_design_document(self.with_risk(risk)))

    def test_manual_external_verification_preserves_local_completion(self):
        risk = (
            "TASK-001 使用本地行为测试验证提交异常分支。\n"
            "- 人工外部验证：TASK-001 需要真实事务/唯一约束集成测试及 SQL 执行计划验证；"
            "mock 不能证明数据库语义，列为未验证范围；不作为 Plan/Execution 门禁。"
        )
        self.assertEqual([], validate_design_document(self.with_risk(risk)))

    def test_manual_owner_alone_does_not_remove_gate(self):
        risk = "- 人工外部验证：TASK-001 需要真实事务集成测试，通过后 Execution 才能完成。"
        self.assertTrue(validate_design_document(self.with_risk(risk)))

    def test_manual_verification_does_not_authorize_external_handoff(self):
        document = self.with_risk(
            "- 人工外部验证：TASK-001 的集成测试；不作为 Plan/Execution 门禁。"
        )
        document += "\n- 依赖：集成测试通过\n"
        self.assertTrue(validate_design_document(document))

    def test_local_protocol_tests_and_database_limitations_are_allowed(self):
        risk = (
            "TASK-001 需要本地 HTTP/Dubbo 契约测试及 adapter 协议映射测试。\n"
            "mock 不能证明真实数据库事务与唯一约束，数据库语义未验证。"
        )
        self.assertEqual([], validate_design_document(self.with_risk(risk)))


if __name__ == "__main__":
    unittest.main()
