from __future__ import annotations

import importlib.util
import sys
from tempfile import TemporaryDirectory
import unittest
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
EXECUTION_SKILL = ROOT / "skills/pretty-executing-plan/SKILL.md"
QUALITY_GATES = ROOT / "skills/pretty-executing-plan/references/quality-contract-gates.md"
QUALITY_PRINCIPLES = ROOT / "skills/pretty-executing-plan/references/quality-principles.md"
VALIDATOR_PATH = ROOT / "skills/pretty-executing-plan/scripts/validate_execution.py"
COVERAGE_PATH = ROOT / "skills/pretty-executing-plan/scripts/verify_incremental_coverage.py"


def load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


validator = load_module("validate_execution", VALIDATOR_PATH)
coverage = load_module("verify_incremental_coverage", COVERAGE_PATH)


def valid_execution_report(status: str = "完成") -> str:
    return f"""# 订单去重 Execution

## 执行起点
- 执行依据：当前工作区最新 `Plan`
- 起始 HEAD：`0123456789abcdef`
- 工作区归因：执行前无与目标重叠的用户改动。

## 基线
| 检查 | 命令 | 退出码 | 结果 |
| --- | --- | ---: | --- |
| 编译 | `mvn test` | `0` | 通过 |

## TASK 结果
### 防止重复订单（TASK-001）
- 状态：`{status}`
- 结果：同一业务身份只创建一笔订单。
- 实际落点：`OrderService#create`
- 验证摘要：定向 UT 通过，退出码 `0`。

## 最终门禁
| 门禁 | 命令或证据 | 退出码 | 结果 |
| --- | --- | ---: | --- |
| 编译 | `mvn test` | `0` | 通过 |
| 增量覆盖率 | `coverage.py` | `0` | 通过 |

## 未验证范围
- 真实数据库压力未执行。

## 结论与恢复点
- 状态：`{status}`
- 交付范围：本地代码与 UT。
- 恢复点：`无`
"""


def jacoco_source(lines: str) -> dict[str, coverage.SourceCoverage]:
    source = coverage.SourceCoverage(
        "com/example/OrderService.java",
        {
            int(number): coverage.LineCoverage(*map(int, values.split(",")))
            for number, values in (line.split(":") for line in lines.split(";"))
        },
    )
    return {source.source_key: source}


class PrettyExecutingPlanTest(unittest.TestCase):
    def test_execution_contract_uses_own_assets_and_scripts(self) -> None:
        skill = EXECUTION_SKILL.read_text(encoding="utf-8")

        self.assertIn("assets/execution.md", skill)
        self.assertIn("references/quality-contract-gates.md", skill)
        self.assertIn("references/quality-principles.md", skill)
        self.assertNotIn("assets/design.md", skill)
        self.assertIn("verify_incremental_coverage.py", skill)
        self.assertIn("validate_execution.py", skill)
        self.assertIn("外部 `tdd` Skill", skill)
        self.assertIn("质量路由", skill)
        self.assertIn("契约 Gate", skill)
        self.assertNotIn("codebase-design", skill)
        self.assertNotIn("121-java-object-oriented-design", skill)
        self.assertNotIn("pretty-java-spring-core", skill)
        self.assertNotIn("ai-harness-skill-orchestration-guide.md", skill)

    def test_quality_rules_have_one_execution_reference_and_include_new_principles(self) -> None:
        gates = QUALITY_GATES.read_text(encoding="utf-8")
        principles = QUALITY_PRINCIPLES.read_text(encoding="utf-8")

        self.assertIn("quality-principles.md", gates)
        self.assertIn("查询与命令分离", principles)
        self.assertIn("参数只作为输入", principles)
        self.assertIn("查询方法只读取", principles)
        self.assertIn("方法参数不能充当返回参数", principles)
        self.assertIn("codebase-design", gates)
        self.assertNotIn("查询与命令分离", gates)

    def test_execution_report_records_only_plan_as_execution_basis(self) -> None:
        report = valid_execution_report()

        self.assertEqual([], validator.validate_execution_document(report, {"TASK-001"}))
        self.assertNotIn("- PRD：", report)
        self.assertNotIn("- Design：", report)
        self.assertIn("执行依据：当前工作区最新 `Plan`", report)

    def test_execution_report_rejects_legacy_upstream_paths(self) -> None:
        report = valid_execution_report().replace(
            "- 执行依据：当前工作区最新 `Plan`",
            "- PRD：`docs/prd.md`\n- Design：`docs/design.md`\n- Plan：`docs/plan.md`",
        )

        errors = validator.validate_execution_document(report, {"TASK-001"})

        self.assertTrue(any("不应记录" in error for error in errors))
        self.assertTrue(any("执行依据" in error for error in errors))

    def test_execution_report_validator_accepts_complete_report(self) -> None:
        errors = validator.validate_execution_document(valid_execution_report(), {"TASK-001"})

        self.assertEqual([], errors)

    def test_execution_report_validator_accepts_stopped_report(self) -> None:
        report = valid_execution_report("停止：增量覆盖率未达标")

        self.assertEqual([], validator.validate_execution_document(report, {"TASK-001"}))

    def test_execution_report_validator_rejects_placeholders_and_missing_tasks(self) -> None:
        report = valid_execution_report().replace("TASK-001", "TASK-002").replace("完成", "待验证", 1)

        errors = validator.validate_execution_document(report, {"TASK-001", "TASK-002"})

        self.assertTrue(any("占位" in error for error in errors))
        self.assertTrue(any("TASK-001" in error for error in errors))

    def test_parse_changed_diff_returns_new_line_numbers(self) -> None:
        diff = """diff --git a/src/main/java/com/example/OrderService.java b/src/main/java/com/example/OrderService.java
--- a/src/main/java/com/example/OrderService.java
+++ b/src/main/java/com/example/OrderService.java
@@ -10,0 +11,2 @@
+        return existing;
+    }
"""

        changed = coverage.parse_changed_diff(diff)

        self.assertEqual(
            {"src/main/java/com/example/OrderService.java": frozenset({11, 12})},
            changed,
        )

    def test_incremental_coverage_fails_when_changed_line_is_missed(self) -> None:
        changed = (
            coverage.ChangedSource(
                "module/src/main/java/com/example/OrderService.java", frozenset({11, 12})
            ),
        )
        sources = jacoco_source("11:3,0,2,0;12:0,2,0,0")

        result = coverage.calculate_coverage(changed, sources)

        self.assertEqual("fail", result.status)
        self.assertEqual(50.0, result.line_percentage)
        self.assertEqual(100.0, result.branch_percentage)

    def test_incremental_coverage_passes_with_required_line_and_branch_results(self) -> None:
        changed = (
            coverage.ChangedSource(
                "module/src/main/java/com/example/OrderService.java", frozenset({11, 12})
            ),
        )
        sources = jacoco_source("11:3,0,2,0;12:2,0,0,0")

        result = coverage.calculate_coverage(changed, sources)

        self.assertEqual("pass", result.status)
        self.assertEqual(100.0, result.line_percentage)
        self.assertEqual(100.0, result.branch_percentage)

    def test_incremental_coverage_reports_missing_source_as_unmeasurable(self) -> None:
        changed = (coverage.ChangedSource("src/main/java/com/example/Missing.java", frozenset({1})),)

        result = coverage.calculate_coverage(changed, {})

        self.assertEqual("unmeasurable", result.status)
        self.assertEqual(("src/main/java/com/example/Missing.java",), result.missing_sources)

    def test_changed_manifest_preserves_execution_attribution(self) -> None:
        with TemporaryDirectory() as directory:
            manifest = Path(directory) / "changed-lines.json"
            manifest.write_text(
                '{"module/src/main/java/com/example/OrderService.java": [11, 12], '
                '"module/src/test/java/com/example/OrderServiceTest.java": [1]}',
                encoding="utf-8",
            )

            changed = coverage.load_changed_manifest(manifest)

        self.assertEqual(
            ("module/src/main/java/com/example/OrderService.java",),
            tuple(source.path for source in changed),
        )

    def test_parse_jacoco_report_reads_package_source_lines(self) -> None:
        report_xml = """<report name="sample">
  <package name="com/example">
    <sourcefile name="OrderService.java">
      <line nr="11" mi="0" ci="3" mb="0" cb="2" />
    </sourcefile>
  </package>
</report>"""
        with TemporaryDirectory() as directory:
            report = Path(directory) / "jacoco.xml"
            report.write_text(report_xml, encoding="utf-8")

            sources = coverage.parse_jacoco_report(report)

        line = sources["com/example/OrderService.java"].lines[11]
        self.assertEqual(3, line.instruction_covered)
        self.assertEqual(2, line.branch_covered)

    def test_no_changed_production_java_returns_not_applicable_without_report(self) -> None:
        result = coverage.calculate_coverage((), {})

        self.assertEqual("not_applicable", result.status)
        self.assertEqual("不适用", result.as_dict()["status_label"])

    def test_coverage_text_uses_chinese_status_labels(self) -> None:
        result = coverage.calculate_coverage((), {})

        self.assertIn("增量覆盖率：不适用", coverage._render_text(result))

    def test_incremental_coverage_ignores_non_executable_changed_lines(self) -> None:
        changed = (coverage.ChangedSource("src/main/java/com/example/OrderService.java", frozenset({1})),)
        sources = jacoco_source("1:0,0,0,0")

        result = coverage.calculate_coverage(changed, sources)

        self.assertEqual("not_applicable", result.status)


if __name__ == "__main__":
    unittest.main()
