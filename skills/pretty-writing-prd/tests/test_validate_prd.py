#!/usr/bin/env python3
"""Regression tests for the PRD validator and Design handoff index."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from validate_prd import validate_prd_document


BASE_PRD = """# Example PRD

## 背景与问题

当前查询结果无法区分缺失与失败。

## 目标与非目标

**目标**

- 返回可区分的查询结果。

**非目标**

- 不改变其他接口。

## 用户与场景

用户发起查询并需要明确结果。

## 需求

### REQ-001：查询结果

查询结果必须可区分。

## 验收标准

### AC-001：区分结果

- Given 数据缺失，When 发起查询，Then 返回缺失结果。
"""


HANDOFF = """\n## Design 交付

| 关联项 | 关键内容 | 定位 |
| --- | --- | --- |
| REQ-001 / AC-001 | 公共行为入口 | `module/src/main/java/example/Handler.java#handle` |
| REQ-001 / AC-001 | 公共验证入口 | `module/src/test/java/example/HandlerTest.java#returnsMissing` |
"""


class ValidatePrdScenariosTest(unittest.TestCase):
    def test_scenarios_reject_requirement_and_acceptance_references(self):
        for scenario in (
            "用户按 REQ-001 查询结果。",
            "用户按 AC-001 核对结果。",
            "### 查询结果（REQ-001）\n\n用户发起查询。",
            "- 用户发起查询。（AC-001）",
            "| 角色 | 结果 |\n| --- | --- |\n| 用户 | REQ-001 |",
            "用户发起查询，查看[查询规则](#req-001)。",
            "用户发起查询，查看[验收结果](#ac-001)。",
        ):
            with self.subTest(scenario=scenario):
                document = BASE_PRD.replace("用户发起查询并需要明确结果。", scenario)

                self.assertIn(
                    "用户与场景禁止引用需求编号或验收编号，请直接描述业务触发和可观察结果",
                    validate_prd_document(document),
                )

    def test_natural_language_scenarios_and_contract_traceability_remain_valid(self):
        document = (BASE_PRD + HANDOFF).replace(
            "用户发起查询并需要明确结果。",
            "用户查询不存在的数据时，看到明确的缺失结果，能够与查询失败区分。",
        ).replace("### AC-001：区分结果", "### AC-001：区分结果\n\n关联 REQ-001。")

        self.assertEqual([], validate_prd_document(document))


class ValidatePrdHandoffTest(unittest.TestCase):
    def test_prd_without_repository_locators_remains_valid(self):
        self.assertEqual([], validate_prd_document(BASE_PRD))

    def test_index_needs_no_status_or_file_actions(self):
        self.assertEqual([], validate_prd_document(BASE_PRD + HANDOFF))

    def test_index_can_record_only_the_entry_or_test_already_read(self):
        for label in ("公共行为入口", "公共验证入口"):
            with self.subTest(label=label):
                handoff = "\n".join(line for line in HANDOFF.splitlines() if label not in line)
                self.assertEqual([], validate_prd_document(BASE_PRD + handoff))

    def test_missing_locators_cannot_be_filled_with_empty_markers(self):
        for locator in ("无", "未获取", ""):
            with self.subTest(locator=locator):
                document = (BASE_PRD + HANDOFF).replace(
                    "module/src/test/java/example/HandlerTest.java#returnsMissing", locator
                )
                self.assertTrue(validate_prd_document(document))

    def test_locator_requires_repository_relative_path_and_symbol(self):
        for locator in (
            "HandlerTest",
            "/tmp/HandlerTest.java#returnsMissing",
            "../HandlerTest.java#returnsMissing",
            "新增 module/src/test/java/example/HandlerTest.java#returnsMissing",
        ):
            with self.subTest(locator=locator):
                document = BASE_PRD + HANDOFF.replace(
                    "module/src/test/java/example/HandlerTest.java#returnsMissing", locator
                )
                self.assertIn(
                    "Design 交付的定位必须是仓库相对路径#symbol；未获得的定位请省略",
                    validate_prd_document(document),
                )

    def test_index_cannot_reference_unknown_contracts(self):
        for known, unknown in (("REQ-001", "REQ-002"), ("AC-001", "AC-002")):
            with self.subTest(unknown=unknown):
                document = BASE_PRD + HANDOFF.replace(known, unknown)
                self.assertIn(
                    f"Design 交付引用了不存在的需求或验收编号：{unknown}",
                    validate_prd_document(document),
                )

    def test_index_does_not_accept_implementation_decisions(self):
        document = BASE_PRD + HANDOFF.replace("公共行为入口", "新增文件")
        self.assertIn(
            "Design 交付只索引当前公共行为入口或公共验证入口",
            validate_prd_document(document),
        )

    def test_empty_or_malformed_index_is_rejected(self):
        for handoff in (
            "\n".join(line for line in HANDOFF.splitlines() if "REQ-001" not in line),
            HANDOFF.replace("| --- | --- | --- |\n", ""),
            HANDOFF.replace("| --- | --- | --- |", "| --- | --- |"),
        ):
            with self.subTest(handoff=handoff):
                self.assertTrue(validate_prd_document(BASE_PRD + handoff))


if __name__ == "__main__":
    unittest.main()
