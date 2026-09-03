#!/usr/bin/env python3
"""Tests for the execution report validator."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from validate_execution import validate


VALID_EXECUTION = """# Example Execution

## TASK 结果

### TASK-001：查询未命中

- 状态：`完成`
- 实际落点：`src/main/java/Handler.java#execute`
- 行为证据：`HandlerTest#rejectsMissing`
- 实质偏差：`无`

## 审查与验证

- 审查：`合并 Review、测试守卫和机械门禁通过`
- 构建验证：`mvn test jacoco:report；exit 0`
- 覆盖率范围：`纳入 Handler.java；排除无`
- 测试覆盖率：`增量行覆盖率 100.00%，分支覆盖率 90.00%`

## 未验证范围

- `无`

## 结论与恢复点

- 状态：`完成`
- 交付范围：`查询未命中合同`
- 声明限制：`无`
"""


class ValidateExecutionTest(unittest.TestCase):
    def test_completed_execution_is_valid(self):
        self.assertEqual([], validate(VALID_EXECUTION))

    def test_missing_shared_verification_is_rejected(self):
        document = VALID_EXECUTION.replace("- 构建验证：", "- 其他：")

        self.assertIn("- 构建验证：", " ".join(validate(document)))

    def test_template_placeholders_are_rejected(self):
        document = VALID_EXECUTION.replace("`无`", "`<待填写>`", 1)

        self.assertIn("execution report still contains template placeholders", validate(document))

    def test_unsupported_status_is_rejected(self):
        document = VALID_EXECUTION.replace("- 状态：`完成`", "- 状态：`处理中`", 1)

        self.assertIn("unsupported execution status: 处理中", validate(document))


if __name__ == "__main__":
    unittest.main()
