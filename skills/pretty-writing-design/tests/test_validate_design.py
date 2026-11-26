#!/usr/bin/env python3
"""Regression tests for the Design contract validator."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from validate_design import validate_design_document


VALID_DESIGN = """# Example Design

## 背景与问题

当前申请入口未区分查询未命中与远端失败，调用方无法判断受理结果。

## 目标与非目标

**目标**

REQ-001、AC-001：调用方获得明确的受理结果，并能区分查询未命中与远端失败。

**非目标**

本次不增加自动重试或人工补偿入口。

## 设计结论

采用现有入口扩展结果合同。

## 方案全景

### 业务流程

```mermaid
flowchart LR
    submit[提交申请] --> review{是否符合受理条件}
    review -->|是| accept[受理申请]
    review -->|否| reject[告知不受理原因]
```

### 技术流程

沿用 Handler#execute → Rule#apply → 返回领域结果的主链路，扩展返回结果。

## 关键设计与权衡

没有需要独立记录的技术权衡。

## 设计边界

不改变外部协议所有权。

## 实施影响

### TASK-001：返回结果

- 对应需求：REQ-001、AC-001
- 结果：返回可观察的领域结果
- 输入与不变量：请求标识符必填
- 失败语义：查询未命中与远端失败可区分
- 验证观察面：结果和异常

## 验证与风险

TASK-001 由公共行为测试验证；无额外风险。

## Executing 交付

| 关联项 | 关键内容 | 定位 |
| --- | --- | --- |
| TASK-001 | 结果合同 | `实施影响 → TASK-001：返回结果` |
| TASK-001 | 影响锚点 | `module/src/main/java/example/Handler.java#execute` |
| TASK-001 | 公共验证入口 | `module/src/test/java/example/HandlerTest.java#returnsResult` |
"""


class ValidateDesignHandoffTest(unittest.TestCase):
    def test_index_needs_no_file_actions_modules_or_implementation_order(self):
        self.assertEqual([], validate_design_document(VALID_DESIGN))

    def test_new_capability_can_handoff_contract_without_future_symbols(self):
        document = "\n".join(
            line for line in VALID_DESIGN.splitlines()
            if "| 影响锚点 |" not in line and "| 公共验证入口 |" not in line
        )
        self.assertEqual([], validate_design_document(document))

    def test_index_can_locate_a_specific_design_decision(self):
        for label in ("技术合同", "新增状态与删除规则"):
            with self.subTest(label=label):
                document = VALID_DESIGN.replace(
                    "没有需要独立记录的技术权衡。",
                    "### 查询边界\n\n查询失败不得作为查询未命中处理。",
                ) + f"| TASK-001 | {label} | `关键设计与权衡 → 查询边界` |\n"
                self.assertEqual([], validate_design_document(document))

    def test_index_rejects_missing_or_wrongly_nested_document_locations(self):
        for locator in (
            "实施影响 → TASK-001：不存在的结果",
            "方案全景 → TASK-001：返回结果",
            "关键设计与权衡 → 未定义的决定",
        ):
            with self.subTest(locator=locator):
                document = VALID_DESIGN.replace("实施影响 → TASK-001：返回结果", locator)
                self.assertIn(
                    "Executing 交付的定位必须是仓库相对路径#symbol 或文档内存在的章节路径",
                    validate_design_document(document),
                )

    def test_every_task_must_locate_its_own_result_contract(self):
        document = VALID_DESIGN.replace("实施影响 → TASK-001：返回结果", "关键设计与权衡")
        self.assertIn(
            "Executing 交付必须定位 TASK-001 在实施影响中的结果合同",
            validate_design_document(document),
        )

    def test_root_level_file_is_a_valid_repository_relative_path(self):
        document = VALID_DESIGN.replace(
            "module/src/test/java/example/HandlerTest.java#returnsResult",
            "HandlerTest.java#returnsResult",
        )
        self.assertEqual([], validate_design_document(document))

    def test_repository_locators_reject_missing_symbols_absolute_paths_and_statuses(self):
        for locator in (
            "HandlerTest#returnsResult",
            "/tmp/HandlerTest.java#returnsResult",
            "../HandlerTest.java#returnsResult",
            "现有 HandlerTest.java#returnsResult",
            "新增 HandlerTest.java#returnsResult",
            "无",
        ):
            with self.subTest(locator=locator):
                document = VALID_DESIGN.replace(
                    "module/src/test/java/example/HandlerTest.java#returnsResult", locator
                )
                self.assertIn(
                    "Executing 交付的定位必须是仓库相对路径#symbol 或文档内存在的章节路径",
                    validate_design_document(document),
                )

    def test_index_cannot_prescribe_file_actions(self):
        for label in ("Add", "Modify", "Test", "新增文件", "修改文件", "删除文件", "构建模块", "依赖"):
            with self.subTest(label=label):
                document = VALID_DESIGN.replace("| 影响锚点 |", f"| {label} |")
                self.assertIn(
                    "Executing 交付的关键内容只说明定位用途，不指定文件动作或实施安排",
                    validate_design_document(document),
                )

    def test_legacy_file_checklist_is_not_a_handoff_index(self):
        document = VALID_DESIGN + "\n- Execution 交付：构建模块 module；Add Rule.java\n"
        self.assertIn(
            "Executing 交付只保留定位索引，不列文件清单、人工运维产物或实施依赖",
            validate_design_document(document),
        )

    def test_index_must_cover_the_impact_tasks(self):
        document = VALID_DESIGN.replace("| TASK-001 |", "| TASK-002 |")
        self.assertIn(
            "Executing 交付的关联 TASK 必须与实施影响一致且顺序相同",
            validate_design_document(document),
        )

    def test_multiple_tasks_retain_contract_order(self):
        impact = VALID_DESIGN.split("### TASK-001：返回结果")[1].split("## 验证与风险")[0]
        document = VALID_DESIGN.replace(
            "## 验证与风险", f"### TASK-002：拒绝缺失标识\n{impact}\n## 验证与风险"
        ) + "| TASK-002 | 结果合同 | `实施影响 → TASK-002：拒绝缺失标识` |\n"
        self.assertEqual([], validate_design_document(document))

        row = "| TASK-002 | 结果合同 | `实施影响 → TASK-002：拒绝缺失标识` |"
        reversed_document = document.replace(row, "").replace(
            "| TASK-001 | 结果合同 |", row + "| TASK-001 | 结果合同 |"
        )
        self.assertTrue(validate_design_document(reversed_document))

    def test_table_spacing_does_not_change_validity(self):
        document = VALID_DESIGN.replace("| ", "|").replace(" |", "|")
        self.assertEqual([], validate_design_document(document))

    def test_empty_or_malformed_index_is_rejected(self):
        for handoff in (
            "| 关联项 | 关键内容 | 定位 |\n| --- | --- | --- |",
            "| TASK-001 | 结果合同 | `实施影响 → TASK-001：返回结果` |",
            "| 关联项 | 关键内容 | 定位 |\n| --- | --- | --- |\n| TASK-001 |",
            "| 关联项 | 关键内容 | 定位 |\n| TASK-001 | 结果合同 | `实施影响 → TASK-001：返回结果` |",
            "| 关联项 | 关键内容 | 定位 |\n| --- | --- |\n| TASK-001 | 结果合同 | `实施影响 → TASK-001：返回结果` |",
        ):
            with self.subTest(handoff=handoff):
                document = VALID_DESIGN.split("## Executing 交付")[0] + "## Executing 交付\n\n" + handoff
                self.assertTrue(validate_design_document(document))

    def test_locators_do_not_duplicate_impact_fields(self):
        document = VALID_DESIGN.replace(
            "- 验证观察面：结果和异常",
            "- 验证观察面：结果和异常\n- 公共验证入口：HandlerTest.java#returnsResult",
        )
        self.assertIn("实施影响不得包含交付定位或文件清单字段", validate_design_document(document))

    def test_result_contract_supports_ascii_colon(self):
        document = VALID_DESIGN.replace("TASK-001：返回结果", "TASK-001: 返回结果")
        self.assertEqual([], validate_design_document(document))


class ValidateManualOperationsTest(unittest.TestCase):
    def test_config_responsibility_lives_in_design_boundaries(self):
        document = VALID_DESIGN.replace(
            "不改变外部协议所有权。",
            "新增事件定义配置数据。\n- 人工运维：配置数据 DML 及配置激活由人工处理。",
        )
        self.assertEqual([], validate_design_document(document))

    def test_config_changes_still_require_manual_owner(self):
        document = VALID_DESIGN.replace("不改变外部协议所有权。", "新增事件定义配置数据。")
        self.assertIn(
            "Design 提及配置数据变更时必须在设计边界说明人工运维责任",
            validate_design_document(document),
        )

    def test_handoff_cannot_substitute_for_manual_responsibility(self):
        document = VALID_DESIGN.replace("不改变外部协议所有权。", "新增事件定义配置数据。")
        document += "\n- 人工运维产物：配置数据 DML db/event-config.sql\n"
        self.assertIn(
            "Design 提及配置数据变更时必须在设计边界说明人工运维责任",
            validate_design_document(document),
        )

    def test_execution_cannot_own_config_dml_or_database_actions(self):
        for directive, error in (
            ("Execution 交付配置数据 DML。", "Execution 不得生成、交付或执行配置数据 DML"),
            ("Execution 执行 DDL。", "Execution 只能交付 DDL 文件，不得执行或间接执行 DDL"),
        ):
            with self.subTest(directive=directive):
                document = VALID_DESIGN.replace("不改变外部协议所有权。", directive)
                self.assertIn(error, validate_design_document(document))


class ValidateBusinessFlowTest(unittest.TestCase):
    def business_section(self):
        return VALID_DESIGN.split("### 业务流程")[1].split("### 技术流程")[0]

    def test_business_flow_is_required(self):
        document = VALID_DESIGN.replace("### 业务流程" + self.business_section(), "")

        self.assertIn("方案全景必须包含业务流程小节", validate_design_document(document))

    def test_business_flow_must_precede_technical_flow(self):
        business = "### 业务流程" + self.business_section()
        document = VALID_DESIGN.replace(business, "").replace(
            "## 关键设计与权衡", business + "## 关键设计与权衡"
        )

        self.assertIn("业务流程必须位于技术流程之前", validate_design_document(document))

    def test_business_flow_requires_its_own_flowchart(self):
        for replacement in (
            "\n提交申请后受理或告知不受理原因。\n\n",
            "\n```mermaid\nsequenceDiagram\n用户->>业务系统: 提交申请\n```\n\n",
            "\n<!--" + self.business_section() + "-->\n\n",
        ):
            with self.subTest(replacement=replacement):
                document = VALID_DESIGN.replace(self.business_section(), replacement).replace(
                    "沿用 Handler#execute", "```mermaid\nflowchart LR\nA --> B\n```\n\n沿用 Handler#execute"
                )

                self.assertIn(
                    "业务流程必须包含 Mermaid flowchart 流程图",
                    validate_design_document(document),
                )

    def test_cross_system_swimlanes_are_valid(self):
        business = """
```mermaid
flowchart LR
    subgraph orders[订单系统]
        submit[提交订单]
        confirm[确认订单]
    end
    subgraph payments[支付系统]
        pay[完成支付]
    end
    submit -->|发起支付| pay
    pay -->|支付成功| confirm
```

"""
        document = VALID_DESIGN.replace(self.business_section(), business)

        self.assertEqual([], validate_design_document(document))


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

    def test_index_cannot_include_external_verification(self):
        document = VALID_DESIGN + "| TASK-001 | 公共验证入口 | 集成测试通过 |\n"

        self.assertIn(
            "外部验证不得作为 Execution 交付或门禁；请在验证与风险使用独立的"
            "人工外部验证条目，并声明不作为 Plan/Execution 门禁",
            validate_design_document(document),
        )

    def test_local_protocol_tests_and_database_limitations_are_allowed(self):
        risk = (
            "TASK-001 需要本地 HTTP/Dubbo 契约测试及 adapter 协议映射测试。\n"
            "mock 不能证明真实数据库事务与唯一约束，数据库语义未验证。"
        )
        self.assertEqual([], validate_design_document(self.with_risk(risk)))


class ValidateDesignDDLTest(unittest.TestCase):
    def with_schema_change(self, sql_content):
        return VALID_DESIGN.replace(
            "## 关键设计与权衡",
            "### 持久化实体\n\n"
            "#### 表结构变更 DDL\n\n"
            "数据库：MySQL 8.0。为 work_order 增加 version 列，历史记录初始化为 0。\n\n"
            f"{sql_content}\n\n"
            "## 关键设计与权衡",
        )

    def test_ddl_index_requires_inline_sql(self):
        document = VALID_DESIGN + "| TASK-001 | DDL | `关键设计与权衡` |\n"
        self.assertIn(
            "声明表结构变更 DDL 或 DDL 索引时，方案全景必须直接包含提供 DDL 语句的 sql 代码块",
            validate_design_document(document),
        )

    def test_ddl_index_locates_the_contract_without_prescribing_a_file(self):
        document = self.with_schema_change(
            "```sql\nALTER TABLE work_order ADD COLUMN version BIGINT NOT NULL DEFAULT 0;\n```"
        ) + "| TASK-001 | DDL | `方案全景 → 持久化实体 → 表结构变更 DDL` |\n"
        self.assertEqual([], validate_design_document(document))

    def test_schema_section_requires_ddl_even_without_index_entry(self):
        document = self.with_schema_change("DDL 见 `db/schema.sql`。")
        self.assertTrue(validate_design_document(document))

    def test_empty_comments_and_dml_cannot_replace_ddl(self):
        for content in (
            "```sql\n\n```",
            "```sql\n-- ALTER TABLE work_order ADD COLUMN version BIGINT;\n```",
            "```sql\n/*\nALTER TABLE work_order ADD COLUMN version BIGINT;\n*/\n```",
            "```sql\nUPDATE work_order SET version = 0;\n```",
            "ALTER TABLE work_order ADD COLUMN version BIGINT NOT NULL DEFAULT 0;",
        ):
            with self.subTest(content=content):
                self.assertTrue(validate_design_document(self.with_schema_change(content)))

    def test_inline_ddl_does_not_require_a_delivery_file_checklist(self):
        for statement in (
            "CREATE TABLE work_order (id BIGINT PRIMARY KEY);",
            "ALTER TABLE work_order ADD COLUMN version BIGINT NOT NULL DEFAULT 0;",
            "CREATE UNIQUE INDEX uk_work_order_id ON work_order (id);",
            "ALTER TABLE work_order ADD CONSTRAINT chk_version CHECK (version >= 0);",
            "DROP INDEX idx_work_order_status ON work_order;",
            "RENAME TABLE work_order TO work_order_archive;",
        ):
            with self.subTest(statement=statement):
                document = self.with_schema_change(f"```sql\n{statement}\n```")
                self.assertEqual([], validate_design_document(document))

    def test_unchanged_schema_does_not_require_sql_or_empty_ddl_field(self):
        self.assertEqual([], validate_design_document(VALID_DESIGN))


if __name__ == "__main__":
    unittest.main()
