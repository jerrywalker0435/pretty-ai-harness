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

- 审查：`一次全量发现 Review、限定复核、测试守卫和机械门禁通过`
- 质量门禁：`clean-code-guard found=0 fixed=0 exception=0 open=0`
- 限定修复：`无`
- 质量例外：`无`
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

    def test_completed_execution_rejects_insufficient_coverage(self):
        document = VALID_EXECUTION.replace(
            "增量行覆盖率 100.00%，分支覆盖率 90.00%",
            "增量行覆盖率 41.18%，分支覆盖率 35.14%",
        )
        errors = validate(document)
        self.assertTrue(any("line coverage below 90%" in error for error in errors))
        self.assertTrue(any("branch coverage below 80%" in error for error in errors))

    def test_missing_shared_verification_is_rejected(self):
        document = VALID_EXECUTION.replace("- 构建验证：", "- 其他：")

        self.assertIn("- 构建验证：", " ".join(validate(document)))

    def test_template_placeholders_are_rejected(self):
        document = VALID_EXECUTION.replace("`无`", "`<待填写>`", 1)

        self.assertIn("execution report still contains template placeholders", validate(document))

    def test_unsupported_status_is_rejected(self):
        document = VALID_EXECUTION.replace("- 状态：`完成`", "- 状态：`处理中`", 1)

        self.assertIn("unsupported execution status: 处理中", validate(document))

    def test_completed_execution_rejects_open_quality_findings(self):
        document = VALID_EXECUTION.replace(
            "found=0 fixed=0 exception=0 open=0",
            "found=1 fixed=0 exception=0 open=1",
        )

        self.assertIn("completed execution cannot contain open quality findings", validate(document))

    def test_completed_execution_with_reason_rejects_open_quality_findings(self):
        document = VALID_EXECUTION.replace(
            "found=0 fixed=0 exception=0 open=0",
            "found=1 fixed=0 exception=0 open=1",
        ).replace(
            "- 状态：`完成`\n- 交付范围：",
            "- 状态：`完成：附带说明`\n- 交付范围：",
        )

        self.assertIn("completed execution cannot contain open quality findings", validate(document))

    def test_status_choice_list_is_rejected(self):
        document = VALID_EXECUTION.replace(
            "- 状态：`完成`\n- 交付范围：",
            "- 状态：`完成 / 停止`\n- 交付范围：",
        )

        self.assertIn("unsupported execution status: 完成 / 停止", validate(document))

    def test_inconsistent_quality_counts_are_rejected(self):
        document = VALID_EXECUTION.replace(
            "found=0 fixed=0 exception=0 open=0",
            "found=2 fixed=1 exception=0 open=0",
        ).replace("- 限定修复：`无`", "- 限定修复：`QF-001@1 Handler#execute`")

        self.assertIn("quality gate counts are inconsistent", validate(document))

    def test_fixed_finding_requires_repair_evidence(self):
        document = VALID_EXECUTION.replace(
            "found=0 fixed=0 exception=0 open=0",
            "found=1 fixed=1 exception=0 open=0",
        )

        self.assertIn("fixed quality findings need bounded repair evidence", validate(document))

    def test_quality_fields_require_backtick_values(self):
        document = VALID_EXECUTION.replace("- 限定修复：`无`", "- 限定修复：无")

        self.assertIn("bounded repair field must use backtick value format", validate(document))

    def test_quality_exception_requires_details(self):
        document = VALID_EXECUTION.replace(
            "found=0 fixed=0 exception=0 open=0",
            "found=1 fixed=0 exception=1 open=0",
        )

        self.assertIn("quality exceptions need contract evidence", " ".join(validate(document)))

    def test_fixed_quality_finding_with_repair_evidence_is_valid(self):
        document = VALID_EXECUTION.replace(
            "found=0 fixed=0 exception=0 open=0",
            "found=1 fixed=1 exception=0 open=0",
        ).replace(
            "- 限定修复：`无`",
            "- 限定修复：`QF-001@1 src/main/java/Handler.java#execute`",
        )

        self.assertEqual([], validate(document))

    def test_quality_exception_with_contract_evidence_is_valid(self):
        document = VALID_EXECUTION.replace(
            "found=0 fixed=0 exception=0 open=0",
            "found=1 fixed=0 exception=1 open=0",
        ).replace(
            "- 质量例外：`无`",
            "- 质量例外：`QF-001 Handler#execute；外部签名固定；下个主版本复查`",
        )

        self.assertEqual([], validate(document))

    def test_stopped_execution_can_record_open_quality_findings(self):
        document = VALID_EXECUTION.replace(
            "found=0 fixed=0 exception=0 open=0",
            "found=1 fixed=0 exception=0 open=1",
        ).replace(
            "- 状态：`完成`\n- 交付范围：",
            "- 状态：`停止：QF-001 两次修复后仍未关闭`\n- 交付范围：",
        )

        self.assertEqual([], validate(document))


if __name__ == "__main__":
    unittest.main()
