#!/usr/bin/env python3
"""Regression tests for the PRD validator and Design handoff snapshot."""

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


HANDOFF = """\n## Design 交接

- 定位状态：`已核验`

| REQ/AC | 当前公共行为入口 | 当前公共验证入口 |
| --- | --- | --- |
| REQ-001 / AC-001 | `module/src/main/java/example/Handler.java#handle` | `module/src/test/java/example/HandlerTest.java#returnsMissing` |
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
    def test_prd_without_repository_snapshot_remains_valid(self):
        self.assertEqual([], validate_prd_document(BASE_PRD))

    def test_verified_snapshot_is_valid(self):
        self.assertEqual([], validate_prd_document(BASE_PRD + HANDOFF))

    def test_snapshot_can_record_only_the_locator_already_read(self):
        document = (BASE_PRD + HANDOFF).replace(
            "`module/src/test/java/example/HandlerTest.java#returnsMissing`",
            "未获取",
        )

        self.assertEqual([], validate_prd_document(document))

    def test_verified_snapshot_requires_path_and_symbol(self):
        document = BASE_PRD + HANDOFF.replace(
            "module/src/test/java/example/HandlerTest.java#returnsMissing",
            "HandlerTest",
        )

        errors = validate_prd_document(document)

        self.assertIn("Design 交接的公共验证入口必须是仓库 path#symbol 或“未获取”", errors)

    def test_snapshot_cannot_reference_unknown_requirement(self):
        document = BASE_PRD + HANDOFF.replace("REQ-001 / AC-001", "REQ-002 / AC-001")

        errors = validate_prd_document(document)

        self.assertIn("Design 交接引用了不存在的需求或验收编号：REQ-002", errors)

    def test_snapshot_requires_verified_status(self):
        document = (BASE_PRD + HANDOFF).replace("`已核验`", "`未获取`")

        errors = validate_prd_document(document)

        self.assertIn("Design 交接必须声明定位状态：已核验", errors)


if __name__ == "__main__":
    unittest.main()
