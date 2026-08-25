from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/pretty-executing-plan/scripts"))

from validate_execution import validate_execution  # noqa: E402


PLAN = """# example Implementation Plan

## 实施任务

### TASK-001：返回订单
"""

COMPLETE_EXECUTION = """# example Execution

## 执行起点

- 执行依据：当前工作区最新 Plan
- 起始 HEAD：`1234567`

## 基线

基线通过。

## TASK 结果

### TASK-001：返回订单

- 路由与审查：JAVA_OOD 由独立 reviewer 完成审查。

## 最终门禁

| 门禁 | 证据 | 结果 |
| --- | --- | --- |
| Plan 与真实 Diff | scope.json | 通过 |
| 机械 Gate 与独立审查 | quality.json | 通过 |
| 编译与相关测试 | build.json | 通过 |
| 数据库验证 | 不适用 | 不适用 |
| 增量覆盖率 | coverage.json | 通过 |

## 未验证范围

- 无

## 结论与恢复点

- 状态：完成
- 测试覆盖率：增量行覆盖率 100.00%，分支覆盖率 98.91%
"""


class ExecutionValidatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.plan_path = Path(self.temporary.name) / "plan.md"
        self.plan_path.write_text(PLAN, encoding="utf-8")
        self.source_path = Path(self.temporary.name) / "Service.java"
        self.source_path.write_text("final class Service {}\n", encoding="utf-8")
        plan_hash = hashlib.sha256(self.plan_path.read_bytes()).hexdigest()
        source_hash = hashlib.sha256(self.source_path.read_bytes()).hexdigest()
        self.quality = {
            "candidate_sha256": "quality",
            "plan_sha256": plan_hash,
            "source_sha256": {"Service.java": source_hash},
            "passed": True,
        }
        self.coverage = {
            "candidate_sha256": "coverage",
            "source_sha256": {"Service.java": source_hash},
            "status": "pass",
            "line_percentage": 100.0,
            "branch_percentage": 98.91,
        }
        self.build = {
            "plan_sha256": plan_hash,
            "quality_candidate_sha256": "quality",
            "coverage_candidate_sha256": "coverage",
            "started_at": 100,
            "commands": [
                {"kind": kind, "command": f"run {kind}", "exit_code": 0, "finished_at": 101}
                for kind in ("compile", "new_tests", "regression_tests")
            ],
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_accepts_exact_coverage_conclusion(self) -> None:
        errors = validate_execution(
            COMPLETE_EXECUTION,
            PLAN,
            self.plan_path,
            self.quality,
            self.coverage,
            self.build,
        )

        self.assertEqual([], errors)

    def test_rejects_coverage_numbers_not_backed_by_evidence(self) -> None:
        document = COMPLETE_EXECUTION.replace("98.91%", "99.00%")

        errors = validate_execution(
            document,
            PLAN,
            self.plan_path,
            self.quality,
            self.coverage,
            self.build,
        )

        self.assertTrue(any("结论必须包含覆盖率证据" in error for error in errors))

    def test_stopped_report_does_not_require_successful_builds(self) -> None:
        document = COMPLETE_EXECUTION.replace("- 状态：完成", "- 状态：停止：测试环境不可用")
        document = document.replace(
            "- 测试覆盖率：增量行覆盖率 100.00%，分支覆盖率 98.91%",
            "- 测试覆盖率：无法验证",
        )
        document = document.replace("| coverage.json | 通过 |", "| coverage.json | 未通过 |")
        quality = {**self.quality, "passed": False}
        coverage = {**self.coverage, "status": "unmeasurable"}
        self.build["commands"] = []

        errors = validate_execution(
            document,
            PLAN,
            self.plan_path,
            quality,
            coverage,
            self.build,
        )

        self.assertEqual([], errors)

    def test_extra_passing_row_cannot_hide_a_failed_required_gate(self) -> None:
        document = COMPLETE_EXECUTION.replace(
            "| Plan 与真实 Diff | scope.json | 通过 |",
            "| Plan 与真实 Diff | scope.json | 未通过 |\n| 额外检查 | extra.json | 通过 |",
        )

        errors = validate_execution(
            document,
            PLAN,
            self.plan_path,
            self.quality,
            self.coverage,
            self.build,
        )

        self.assertIn("完成状态的最终门禁未通过：Plan 与真实 Diff", errors)

    def test_rejects_evidence_after_source_changes(self) -> None:
        self.source_path.write_text("final class Service { int changed; }\n", encoding="utf-8")

        errors = validate_execution(
            COMPLETE_EXECUTION,
            PLAN,
            self.plan_path,
            self.quality,
            self.coverage,
            self.build,
        )

        self.assertIn("quality evidence is stale for Service.java", errors)
        self.assertIn("coverage evidence is stale for Service.java", errors)

    def test_latest_failed_build_command_overrides_earlier_success(self) -> None:
        self.build["commands"].append(
            {
                "kind": "compile",
                "command": "run compile again",
                "exit_code": 1,
                "finished_at": 102,
            }
        )

        errors = validate_execution(
            COMPLETE_EXECUTION,
            PLAN,
            self.plan_path,
            self.quality,
            self.coverage,
            self.build,
        )

        self.assertIn("latest build evidence failed: compile", errors)

    def test_latest_successful_build_command_can_close_an_earlier_failure(self) -> None:
        self.build["commands"].insert(
            0,
            {
                "kind": "compile",
                "command": "initial compile",
                "exit_code": 1,
                "finished_at": 100,
            },
        )

        errors = validate_execution(
            COMPLETE_EXECUTION,
            PLAN,
            self.plan_path,
            self.quality,
            self.coverage,
            self.build,
        )

        self.assertEqual([], errors)

    def test_sql_plan_requires_fresh_database_validation(self) -> None:
        sql_plan = PLAN + "\n- Modify: `db/migration/V2__event_index.sql`\n"
        self.plan_path.write_text(sql_plan, encoding="utf-8")
        plan_hash = hashlib.sha256(self.plan_path.read_bytes()).hexdigest()
        self.quality["plan_sha256"] = plan_hash
        self.build["plan_sha256"] = plan_hash
        document = COMPLETE_EXECUTION.replace(
            "| 数据库验证 | 不适用 | 不适用 |",
            "| 数据库验证 | database.json | 通过 |",
        )

        errors = validate_execution(
            document,
            sql_plan,
            self.plan_path,
            self.quality,
            self.coverage,
            self.build,
        )

        self.assertIn("missing build evidence: database_validation", errors)
        self.build["commands"].append(
            {
                "kind": "database_validation",
                "command": "mysql --execute SHOW INDEX FROM service_event",
                "exit_code": 0,
                "finished_at": 102,
            }
        )
        self.assertEqual(
            [],
            validate_execution(
                document,
                sql_plan,
                self.plan_path,
                self.quality,
                self.coverage,
                self.build,
            ),
        )


if __name__ == "__main__":
    unittest.main()
