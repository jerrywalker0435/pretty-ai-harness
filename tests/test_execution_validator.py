from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/pretty-executing/scripts"))

from validate_execution import ExecutionEvidence, validate_execution  # noqa: E402

DESIGN = """# Example Design
## 实施影响
### TASK-001：返回订单
"""

EXECUTION = """# Example Execution
## 执行起点
- 执行依据：当前工作区最新 Design
- 起始 HEAD：`1234567`
## 基线
基线通过。
## TASK 结果
### TASK-001：返回订单
- 路由与审查：独立 reviewer 已完成。
## 最终门禁
| 门禁 | 证据 | 结果 |
| --- | --- | --- |
| Design TASK 与真实 Diff | matrix.json | 通过 |
| 机械 Gate 与独立审查 | quality.json | 通过 |
| 编译与相关测试 | build.json | 通过 |
| 新增/修改测试实际执行 | tests.json | 通过 |
| 增量覆盖率 | coverage.json | 通过 |
## 未验证范围
- 无
## 结论与恢复点
- 状态：完成
- 最终 Diff 摘要：`quality`
- 测试覆盖率：增量行覆盖率 100.00%，分支覆盖率 98.91%
"""


class ExecutionValidatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.topic = root / "docs/pretty/example"
        self.topic.mkdir(parents=True)
        self.design = self.topic / "design.md"
        self.design.write_text(DESIGN, encoding="utf-8")
        self.source = root / "src/main/java/example/Service.java"
        self.source.parent.mkdir(parents=True)
        self.source.write_text("final class Service {}\n", encoding="utf-8")
        design_hash = hashlib.sha256(self.design.read_bytes()).hexdigest()
        source_hash = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.quality = {"candidate_sha256": "quality", "design_sha256": design_hash, "source_sha256": {"src/main/java/example/Service.java": source_hash}, "production_java": True, "passed": True}
        self.coverage = {"candidate_sha256": "coverage", "design_sha256": design_hash, "source_sha256": {"src/main/java/example/Service.java": source_hash}, "status": "pass", "line_percentage": 100.0, "branch_percentage": 98.91}
        self.tests = {"candidate_sha256": "tests", "design_sha256": design_hash, "source_sha256": {}, "status": "pass", "passed": True}
        self.build = {"design_sha256": design_hash, "quality_candidate_sha256": "quality", "coverage_candidate_sha256": "coverage", "test_candidate_sha256": "tests", "commands": [{"kind": kind, "exit_code": 0, "finished_at": 101} for kind in ("compile", "new_tests", "regression_tests")]}

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def validate(self, document: str = EXECUTION) -> list[str]:
        return validate_execution(document, DESIGN, self.design, ExecutionEvidence(self.quality, self.coverage, self.build, self.tests))

    def test_accepts_design_bound_execution_and_exact_coverage(self) -> None:
        self.assertEqual([], self.validate())

    def test_rejects_task_set_drift(self) -> None:
        errors = self.validate(EXECUTION.replace("TASK-001：返回订单", "TASK-002：返回订单"))
        self.assertTrue(any("TASK set must match Design" in error for error in errors))

    def test_rejects_tests_that_were_not_actually_executed(self) -> None:
        self.tests["passed"] = False
        self.tests["status"] = "fail"
        self.assertIn("完成状态需要新增/修改测试实际执行通过", self.validate())

    def test_rejects_coverage_numbers_not_backed_by_evidence(self) -> None:
        errors = self.validate(EXECUTION.replace("98.91%", "99.00%"))
        self.assertTrue(any("结论必须包含覆盖率证据" in error for error in errors))

    def test_rejects_evidence_after_source_changes(self) -> None:
        self.source.write_text("final class Service { int changed; }\n", encoding="utf-8")
        errors = self.validate()
        self.assertIn("quality evidence is stale for src/main/java/example/Service.java", errors)
        self.assertIn("coverage evidence is stale for src/main/java/example/Service.java", errors)

    def test_latest_failed_build_command_overrides_earlier_success(self) -> None:
        self.build["commands"].append({"kind": "compile", "exit_code": 1, "finished_at": 102})
        self.assertIn("latest build evidence failed: compile", self.validate())

    def test_latest_successful_build_command_can_close_an_earlier_failure(self) -> None:
        self.build["commands"].insert(0, {"kind": "compile", "exit_code": 1, "finished_at": 100})
        self.assertEqual([], self.validate())

    def test_rejects_stale_candidate_binding(self) -> None:
        self.build["quality_candidate_sha256"] = "older-quality"
        self.assertIn("build evidence has stale quality_candidate_sha256", self.validate())

    def test_stopped_report_does_not_require_successful_commands(self) -> None:
        document = EXECUTION.replace("- 状态：完成", "- 状态：停止：测试环境不可用")
        document = document.replace(
            "- 测试覆盖率：增量行覆盖率 100.00%，分支覆盖率 98.91%",
            "- 测试覆盖率：无法验证",
        )
        document = document.replace("| coverage.json | 通过 |", "| coverage.json | 不通过 |")
        self.coverage["status"] = "unmeasurable"
        self.coverage["line_percentage"] = None
        self.coverage["branch_percentage"] = None
        self.build["commands"] = []
        self.assertEqual([], self.validate(document))

    def test_stopped_report_does_not_require_final_evidence_files(self) -> None:
        document = EXECUTION.replace("- 状态：完成", "- 状态：停止：基线测试失败")
        document = document.replace(
            "- 测试覆盖率：增量行覆盖率 100.00%，分支覆盖率 98.91%",
            "- 测试覆盖率：无法验证",
        )
        evidence = ExecutionEvidence({}, {}, {}, {})
        self.assertEqual([], validate_execution(document, DESIGN, self.design, evidence))

    def test_ddl_only_execution_can_declare_no_build_command_kinds(self) -> None:
        document = EXECUTION.replace(
            "- 测试覆盖率：增量行覆盖率 100.00%，分支覆盖率 98.91%",
            "- 测试覆盖率：不适用",
        )
        document = document.replace("| build.json | 通过 |", "| build.json | 不适用 |")
        document = document.replace("| tests.json | 通过 |", "| tests.json | 不适用 |")
        document = document.replace("| coverage.json | 通过 |", "| coverage.json | 不适用 |")
        self.coverage["status"] = "not_applicable"
        self.coverage["line_percentage"] = None
        self.coverage["branch_percentage"] = None
        self.tests["status"] = "not_applicable"
        self.quality["production_java"] = False
        self.build["required_kinds"] = []
        self.build["commands"] = []
        self.assertEqual([], self.validate(document))

    def test_java_execution_cannot_disable_required_build_kinds(self) -> None:
        self.build["required_kinds"] = []
        self.build["commands"] = []
        self.assertTrue(any("applicable command" in error for error in self.validate()))

    def test_rejects_preview_ready_as_execution_status(self) -> None:
        document = EXECUTION.replace("- 状态：完成", "- 状态：预演就绪")
        self.assertTrue(any("valid final status" in error for error in self.validate(document)))


if __name__ == "__main__":
    unittest.main()
