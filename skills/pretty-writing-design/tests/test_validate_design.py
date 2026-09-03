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

### TASK-001：返回结果

- 对应需求：REQ-001、AC-001
- 结果：返回可观察的领域结果
- 输入与不变量：请求标识符必填
- 失败语义：查询未命中与远端失败可区分
- 验证观察面：结果和异常

## 验证与风险

TASK-001 由公共行为测试验证；无额外风险。

## Executing 定位与交付

### 变更职责链路

入口 Handler#execute 到规则所有者 Rule#apply。

### TASK-001

- 公共验证入口：现有；module/src/test/java/example/HandlerTest.java#returnsResult
- 影响锚点：现有 module/src/main/java/example/Handler.java#execute；新增 module/src/main/java/example/Rule.java#apply
- Execution 交付：构建模块 module；Modify `module/src/main/java/example/Handler.java`；Add `module/src/main/java/example/Rule.java`；Test `module/src/test/java/example/HandlerTest.java`
- 人工运维产物：无
"""


class ValidateDesignHandoffTest(unittest.TestCase):
    def test_separated_execution_handoff_is_valid(self):
        self.assertEqual([], validate_design_document(VALID_DESIGN))

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

        self.assertIn("Executing 定位与交付的 TASK ID 必须与实施影响一致且顺序相同", errors)

    def test_execution_content_cannot_remain_in_impact(self):
        document = VALID_DESIGN.replace(
            "## 实施影响\n",
            "## 实施影响\n\n### 变更职责链路\n\n入口到规则所有者。\n",
        ).replace(
            "- 验证观察面：结果和异常",
            "- 验证观察面：结果和异常\n- 公共验证入口：现有；HandlerTest.java#returnsResult",
        )

        errors = validate_design_document(document)

        self.assertIn("实施影响不得包含变更职责链路或 Executing 定位与交付字段", errors)


if __name__ == "__main__":
    unittest.main()
