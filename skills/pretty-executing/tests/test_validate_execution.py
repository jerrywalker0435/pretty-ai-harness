#!/usr/bin/env python3
"""Tests for the execution report validator."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from validate_execution import FinalGateInput, _final_gate_errors, main, validate


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
- 构建验证：`最终验收：mvn test jacoco:report；执行次数=1；exit 0`
- 覆盖率范围：`纳入 Handler.java；排除无`
- 测试覆盖率：`增量行覆盖率 100.00%，分支覆盖率 90.00%`

## 未验证范围

- `无`

## 结论与恢复点

- TASK 完成情况：`TASK-001：完成`
- 实际生产代码变更：`src/main/java/Handler.java#execute`
- 停止代码：`无`
- 停止证据：`无`
- 状态：`完成`
- 交付范围：`查询未命中合同`
- 声明限制：`无`
"""


class ValidateExecutionTest(unittest.TestCase):
    def test_final_cli_accepts_a_complete_no_diff_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            (repo / "README.md").write_text("fixture\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "base"],
                cwd=repo,
                check=True,
            )
            contract = repo / "design.md"
            contract.write_text("## 实施影响\n\n### TASK-001：查询未命中\n", encoding="utf-8")
            execution = repo / "execution.md"
            execution.write_text(
                VALID_EXECUTION.replace(
                    "- 状态：`完成`\n- 交付范围：",
                    "- 状态：`已满足（无生产差异）`\n- 交付范围：",
                ).replace(
                    "- 实际生产代码变更：`src/main/java/Handler.java#execute`",
                    "- 实际生产代码变更：`无；本次没有生产代码差异`",
                ).replace(
                    "`增量行覆盖率 100.00%，分支覆盖率 90.00%`",
                    "`不适用：无可执行生产增量`",
                ),
                encoding="utf-8",
            )
            coverage = repo / "coverage.json"
            coverage.write_text('{"status":"not_applicable"}\n', encoding="utf-8")

            with redirect_stdout(StringIO()):
                exit_code = main([
                    str(execution), "--final", "--contract", str(contract), "--coverage-json", str(coverage),
                    "--repo", str(repo), "--base", "HEAD",
                ])

            self.assertEqual(0, exit_code)

    def test_completed_execution_is_valid(self):
        self.assertEqual([], validate(VALID_EXECUTION))

    def test_historical_execution_without_new_final_fields_remains_readable(self):
        historical = VALID_EXECUTION
        for line in (
            "- TASK 完成情况：`TASK-001：完成`\n",
            "- 实际生产代码变更：`src/main/java/Handler.java#execute`\n",
            "- 停止代码：`无`\n",
            "- 停止证据：`无`\n",
        ):
            historical = historical.replace(line, "")
        self.assertEqual([], validate(historical))

    def test_completed_execution_rejects_insufficient_coverage(self):
        document = VALID_EXECUTION.replace(
            "增量行覆盖率 100.00%，分支覆盖率 90.00%",
            "增量行覆盖率 41.18%，分支覆盖率 35.14%",
        )
        errors = validate(document)
        self.assertTrue(any("line coverage below 90%" in error for error in errors))
        self.assertTrue(any("branch coverage below 80%" in error for error in errors))

    def test_final_gate_requires_all_contract_tasks(self):
        contract = "## 实施影响\n\n### TASK-001：查询未命中\n\n### TASK-002：回复兼容\n"
        errors = _final_gate_errors(FinalGateInput(
            VALID_EXECUTION, contract,
            {"status": "pass", "line_percentage": 100.0, "branch_percentage": 90.0},
            None, None, None, None, (),
        ))
        self.assertIn("execution report is missing TASK results: TASK-002", errors)
        self.assertIn("completed execution has incomplete TASKs: TASK-002", errors)

    def test_final_gate_accepts_complete_contract_and_coverage(self):
        contract = "## 实施影响\n\n### TASK-001：查询未命中\n"
        errors = _final_gate_errors(FinalGateInput(
            VALID_EXECUTION, contract,
            {"status": "pass", "line_percentage": 100.0, "branch_percentage": 90.0},
            None, None, None, None, (),
        ))
        self.assertEqual([], errors)

    def test_final_gate_accepts_no_branch_measurements(self):
        contract = "## 实施影响\n\n### TASK-001：查询未命中\n"
        document = VALID_EXECUTION.replace(
            "分支覆盖率 90.00%", "分支覆盖率 不适用"
        )
        errors = _final_gate_errors(FinalGateInput(
            document, contract,
            {"status": "pass", "line_percentage": 100.0, "branch_percentage": None, "branch_total": 0},
            None, None, None, None, (),
        ))
        self.assertEqual([], errors)

    def test_final_gate_accepts_not_applicable_coverage_receipt(self):
        contract = "## 实施影响\n\n### TASK-001：查询未命中\n"
        document = VALID_EXECUTION.replace(
            "`增量行覆盖率 100.00%，分支覆盖率 90.00%`",
            "`不适用：无可执行生产增量`",
        )
        errors = _final_gate_errors(FinalGateInput(
            document, contract, {"status": "not_applicable"},
            None, None, None, None, (),
        ))
        self.assertEqual([], errors)

    def test_not_applicable_coverage_allows_build_without_jacoco(self):
        contract = "## 实施影响\n\n### TASK-001：查询未命中\n"
        document = VALID_EXECUTION.replace(
            "最终验收：mvn test jacoco:report", "最终验收：mvn test"
        ).replace(
            "`增量行覆盖率 100.00%，分支覆盖率 90.00%`",
            "`不适用：无可执行生产增量`",
        )
        errors = _final_gate_errors(FinalGateInput(
            document, contract, {"status": "not_applicable"},
            None, None, None, None, (),
        ))
        self.assertEqual([], errors)

    def test_final_gate_rejects_coverage_text_mismatch(self):
        contract = "## 实施影响\n\n### TASK-001：查询未命中\n"
        errors = _final_gate_errors(FinalGateInput(
            VALID_EXECUTION, contract,
            {"status": "pass", "line_percentage": 99.0, "branch_percentage": 90.0},
            None, None, None, None, (),
        ))
        self.assertIn("execution report line coverage does not match coverage JSON", errors)

    def test_final_gate_rejects_compile_only_verification(self):
        contract = "## 实施影响\n\n### TASK-001：查询未命中\n"
        document = VALID_EXECUTION.replace(
            "最终验收：mvn test jacoco:report", "最终验收：mvn compile"
        )
        errors = _final_gate_errors(FinalGateInput(
            document, contract,
            {"status": "pass", "line_percentage": 100.0, "branch_percentage": 90.0},
            None, None, None, None, (),
        ))
        self.assertIn("completed execution build verification must include a test task", errors)
        self.assertIn("completed execution build verification must include JaCoCo or coverage reporting", errors)

    def test_final_gate_rejects_zero_build_invocation_count(self):
        contract = "## 实施影响\n\n### TASK-001：查询未命中\n"
        document = VALID_EXECUTION.replace("执行次数=1", "执行次数=0")
        errors = _final_gate_errors(FinalGateInput(
            document, contract,
            {"status": "pass", "line_percentage": 100.0, "branch_percentage": 90.0},
            None, None, None, None, (),
        ))
        self.assertIn("completed execution build verification invocation count must be positive", errors)

    def test_final_gate_rejects_completion_without_coverage_artifact(self):
        contract = "## 实施影响\n\n### TASK-001：查询未命中\n"
        errors = _final_gate_errors(FinalGateInput(
            VALID_EXECUTION, contract, None, None, None, None, None, (),
        ))
        self.assertIn("final completion requires the verify_incremental_coverage JSON result", errors)

    def test_final_gate_rejects_extra_task_without_status(self):
        contract = "## 实施影响\n\n### TASK-001：查询未命中\n"
        document = VALID_EXECUTION.replace(
            "## 审查与验证",
            "### TASK-999：未声明任务\n\n## 审查与验证",
        )
        errors = _final_gate_errors(FinalGateInput(
            document, contract,
            {"status": "pass", "line_percentage": 100.0, "branch_percentage": 90.0},
            None, None, None, None, (),
        ))
        self.assertIn("execution report contains TASKs absent from contract: TASK-999", errors)
        self.assertIn("execution report TASKs need a final status: TASK-999", errors)

    def test_final_gate_requires_task_summary_to_match_task_results(self):
        contract = "## 实施影响\n\n### TASK-001：查询未命中\n"
        document = VALID_EXECUTION.replace(
            "TASK-001：完成", "TASK-001：停止：未完成"
        )
        errors = _final_gate_errors(FinalGateInput(
            document, contract,
            {"status": "pass", "line_percentage": 100.0, "branch_percentage": 90.0},
            None, None, None, None, (),
        ))
        self.assertIn("TASK 完成情况 disagrees with TASK 结果 for TASK-001", errors)

    def test_task_summary_preserves_semicolons_in_stop_reason(self):
        contract = "## 实施影响\n\n### TASK-001：查询未命中\n"
        document = VALID_EXECUTION.replace(
            "- TASK 完成情况：`TASK-001：完成`",
            "- TASK 完成情况：`TASK-001：停止：构建失败；无新诊断证据`",
        ).replace(
            "- 状态：`完成`\n- 实际落点：",
            "- 状态：`停止：构建失败；无新诊断证据`\n- 实际落点：",
        ).replace(
            "- 状态：`完成`\n- 交付范围：",
            "- 状态：`停止：构建失败；无新诊断证据`\n- 交付范围：",
        ).replace("- 停止代码：`无`", "- 停止代码：`VALIDATION_FAILED`").replace(
            "- 停止证据：`无`",
            "- 停止证据：`构建失败；无新诊断证据；exit 1`",
        )
        errors = _final_gate_errors(FinalGateInput(
            document, contract, None, None, None, None, None, (),
        ))
        self.assertNotIn("TASK 完成情况 disagrees with TASK 结果", " ".join(errors))

    @patch("validate_execution._git_paths", return_value={"target/generated-sources/Foo.java"})
    def test_generated_java_does_not_count_as_production_diff(self, _git_paths):
        contract = "## 实施影响\n\n### TASK-001：查询未命中\n"
        document = VALID_EXECUTION.replace(
            "- 状态：`完成`\n- 交付范围：",
            "- 状态：`已满足（无生产差异）`\n- 交付范围：",
        )
        errors = _final_gate_errors(FinalGateInput(
            document, contract,
            {"status": "pass", "line_percentage": 100.0, "branch_percentage": 90.0},
            None, None, Path("."), "HEAD", (),
        ))
        self.assertEqual([], errors)

    @patch(
        "validate_execution._git_paths",
        return_value={"src/main/java/Handler.java", "other/src/main/java/Unrelated.java"},
    )
    def test_final_gate_ignores_java_changes_outside_execution_scope(self, _git_paths):
        contract = "## 实施影响\n\n### TASK-001：查询未命中\n"
        document = VALID_EXECUTION
        errors = _final_gate_errors(FinalGateInput(
            document, contract,
            {"status": "pass", "line_percentage": 100.0, "branch_percentage": 90.0},
            None, None, Path("."), "HEAD", ("src/main/java/Handler.java",),
        ))
        self.assertIn("final completion requires the quality Review JSON result", errors)
        self.assertNotIn("Unrelated.java", " ".join(errors))

    @patch("validate_execution._git_paths", return_value={"src/main/java/Handler.java"})
    def test_stopped_execution_does_not_require_closed_review(self, _git_paths):
        contract = "## 实施影响\n\n### TASK-001：查询未命中\n"
        document = VALID_EXECUTION.replace(
            "- 状态：`完成`\n- 交付范围：",
            "- 状态：`停止：质量问题在两次修复后仍未关闭`\n- 交付范围：",
        ).replace("- 停止代码：`无`", "- 停止代码：`QUALITY_OPEN`").replace(
            "- 停止证据：`无`",
            "- 停止证据：`QF-001 两次限定修复后仍为 open；"
            "quality_review_gate --require-closed 退出 1`",
        )
        errors = _final_gate_errors(FinalGateInput(
            document, contract, None, None, None, Path("."), "HEAD", (),
        ))
        self.assertNotIn("final completion requires the quality Review JSON result", errors)

    @patch("validate_execution._git_paths", return_value={"src/main/java/Handler.java"})
    def test_final_gate_requires_review_artifacts_for_production_diff(self, _git_paths):
        contract = "## 实施影响\n\n### TASK-001：查询未命中\n"
        errors = _final_gate_errors(FinalGateInput(
            VALID_EXECUTION, contract,
            {"status": "pass", "line_percentage": 100.0, "branch_percentage": 90.0},
            None, None, Path("."), "HEAD", (),
        ))
        self.assertIn("final completion requires the quality Review JSON result", errors)
        self.assertIn("final completion with production changes requires --path for every reviewed file", errors)

    @patch("validate_execution._git_paths", return_value={"src/main/java/Handler.java"})
    def test_final_gate_accepts_closed_review_and_routes_for_production_diff(self, _git_paths):
        from quality_review_gate import validate_closed

        contract = "## 实施影响\n\n### TASK-001：查询未命中\n"
        review = {
            "review_type": "full-discovery",
            "full_review_count": 1,
            "routes_applied": ["clean-code-guard"],
            "reviewed_paths": ["src/main/java/Handler.java"],
            "type_necessity_checks": [],
            "type_necessity_not_applicable": "only method bodies changed; no new types",
            "cqs_checks": [],
            "cqs_not_applicable": {"reason": "no non-void methods", "facts": "only a data carrier changed"},
            "findings": [],
        }
        self.assertEqual([], validate_closed(review, ["src/main/java/Handler.java"]))
        errors = _final_gate_errors(FinalGateInput(
            VALID_EXECUTION, contract,
            {"status": "pass", "line_percentage": 100.0, "branch_percentage": 90.0},
            review, {"production_java": ["src/main/java/Handler.java"], "routes": []},
            Path("."), "HEAD", ("src/main/java/Handler.java",),
        ))
        self.assertEqual([], errors)

    @patch(
        "validate_execution._git_paths",
        return_value={"src/main/java/Handler.java", "src/main/java/Outbox.java"},
    )
    def test_final_gate_requires_every_production_diff_path_in_receipts(self, _git_paths):
        contract = "## 实施影响\n\n### TASK-001：查询未命中\n"
        review = {
            "review_type": "full-discovery",
            "full_review_count": 1,
            "routes_applied": ["clean-code-guard"],
            "reviewed_paths": ["src/main/java/Handler.java", "src/main/java/Outbox.java"],
            "type_necessity_checks": [],
            "type_necessity_not_applicable": "only method bodies changed; no new types",
            "cqs_checks": [],
            "cqs_not_applicable": {"reason": "no non-void methods", "facts": "only void methods changed"},
            "findings": [],
        }
        errors = _final_gate_errors(FinalGateInput(
            VALID_EXECUTION, contract,
            {"status": "pass", "line_percentage": 100.0, "branch_percentage": 90.0},
            review, {"production_java": ["src/main/java/Handler.java"], "routes": []},
            Path("."), "HEAD", ("src/main/java/Handler.java", "src/main/java/Outbox.java"),
        ))
        self.assertIn("quality route JSON production_java does not match the Java production diff", errors)
        self.assertIn("actual production code changes are missing Git diff files: src/main/java/Outbox.java", errors)

    def test_coverage_json_uses_project_thresholds(self):
        document = VALID_EXECUTION.replace(
            "增量行覆盖率 100.00%，分支覆盖率 90.00%",
            "增量行覆盖率 85.00%，分支覆盖率 75.00%",
        )
        errors = validate(
            document,
            {"status": "pass", "line_percentage": 85.0, "branch_percentage": 75.0,
             "line_threshold": 80.0, "branch_threshold": 70.0},
        )
        self.assertEqual([], errors)

    def test_final_gate_rejects_invalid_coverage_ranges(self):
        contract = "## 实施影响\n\n### TASK-001：查询未命中\n"
        errors = _final_gate_errors(FinalGateInput(
            VALID_EXECUTION, contract,
            {"status": "pass", "line_percentage": 101.0, "branch_percentage": 90.0,
             "line_threshold": 90.0, "branch_threshold": 80.0},
            None, None, None, None, (),
        ))
        self.assertIn("completed execution coverage percentages must be between 0 and 100", errors)

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
        ).replace("- 停止代码：`无`", "- 停止代码：`QUALITY_OPEN`").replace(
            "- 停止证据：`无`",
            "- 停止证据：`QF-001 两次限定修复后仍为 open；"
            "quality_review_gate --require-closed 退出 1`",
        )

        self.assertEqual([], validate(document))

    def test_stopped_execution_requires_blocking_evidence(self):
        document = VALID_EXECUTION.replace(
            "- 状态：`完成`\n- 交付范围：",
            "- 状态：`停止：构建失败且无法修复`\n- 交付范围：",
        )
        errors = _final_gate_errors(FinalGateInput(
            document, "## 实施影响\n\n### TASK-001：查询未命中\n", None, None, None, None, None, (),
        ))
        self.assertIn("stopped execution needs concrete blocking evidence", errors)
        self.assertIn("stopped execution needs a supported stop code", errors)

    def test_returned_execution_requires_contract_reason(self):
        contract = "## 实施影响\n\n### TASK-001：查询未命中\n"
        document = VALID_EXECUTION.replace(
            "- 状态：`完成`\n- 交付范围：",
            "- 状态：`返回 Design：需求边界仍不明确`\n- 交付范围：",
        ).replace("- 停止代码：`无`", "- 停止代码：`CONTRACT_CONFLICT`").replace(
            "- 停止证据：`无`", "- 停止证据：`需求与 Design 不一致，无法安全实现`"
        )
        errors = _final_gate_errors(FinalGateInput(
            document, contract, None, None, None, None, None, (),
        ))
        self.assertEqual([], errors)


if __name__ == "__main__":
    unittest.main()
