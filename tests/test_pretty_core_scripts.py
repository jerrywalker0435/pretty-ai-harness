from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
CORE_DIR = REPO_ROOT / "skills" / "pretty-java-spring-core"
VALIDATOR = CORE_DIR / "scripts" / "validate-pretty-docs.py"
COVERAGE_CHECKER = CORE_DIR / "scripts" / "check-new-code-coverage.py"
COVERAGE_RUNNER = CORE_DIR / "scripts" / "run-coverage.sh"


class PrettyTemplateContractTest(unittest.TestCase):
    def test_plan_template_makes_test_boundary_reviewable(self) -> None:
        template = (CORE_DIR / "assets" / "templates" / "plan.md").read_text(
            encoding="utf-8"
        )

        for marker in (
            "测试边界",
            "测试层级",
            "独立预期值来源",
            "允许替换的外部边界",
            "RED 命令",
            "GREEN 命令",
            "重构复验",
            "测试提案",
            "拟议生产代码",
        ):
            self.assertIn(marker, template)

    def test_execution_template_requires_an_independent_reviewer(self) -> None:
        template = (CORE_DIR / "assets" / "templates" / "execution.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("环境不支持时标记阻塞", template)
        self.assertNotIn("环境不支持时说明自审", template)

    def test_execution_template_records_tdd_and_refactor_evidence(self) -> None:
        template = (CORE_DIR / "assets" / "templates" / "execution.md").read_text(
            encoding="utf-8"
        )

        for marker in (
            "测试边界",
            "RED",
            "GREEN",
            "`refactor`",
            "重构复验",
        ):
            self.assertIn(marker, template)


class PrettyDocumentValidatorTest(unittest.TestCase):
    def test_accepts_a_complete_cross_stage_document_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            topic_dir = Path(temp_dir) / "checkout"
            self._write_valid_chain(topic_dir)

            result = subprocess.run(
                [sys.executable, str(VALIDATOR), str(topic_dir)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("4 documents valid", result.stdout)

    def test_rejects_an_unknown_cross_stage_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            topic_dir = Path(temp_dir) / "checkout"
            self._write_valid_chain(topic_dir)
            design_file = topic_dir / "design.md"
            design_file.write_text(
                design_file.read_text(encoding="utf-8").replace(
                    "`REQ-001`", "`REQ-999`", 1
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(VALIDATOR), str(topic_dir)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("REQ-999", result.stderr)

    def test_rejects_placeholders(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            topic_dir = Path(temp_dir) / "checkout"
            self._write_valid_chain(topic_dir)
            plan_file = topic_dir / "plan.md"
            plan_file.write_text(
                plan_file.read_text(encoding="utf-8") + "\nTODO: later\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(VALIDATOR), str(topic_dir)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("placeholder", result.stderr.lower())

    @staticmethod
    def _write_valid_chain(topic_dir: Path) -> None:
        topic_dir.mkdir(parents=True)
        documents = {
            "prd.md": """
                # Checkout PRD

                ## 背景与问题
                顾客无法完成结账。

                ## 目标与非目标
                恢复结账；不改造支付平台。

                ## 用户与场景
                顾客提交有效订单。

                ## 需求
                ### REQ-001 支持提交订单
                系统接收有效订单。

                ## 验收标准
                ### AC-001 返回已创建订单
                关联需求：`REQ-001`

                ## 约束与未决问题
                无。
            """,
            "design.md": """
                # Checkout Design

                ## 输入与范围
                输入：`prd.md`。

                ## 现状与约束
                沿用现有 Spring MVC 分层。

                ## 方案与权衡
                选择同步应用服务；当前没有异步需求。

                ## 详细设计
                ### DEC-001 由应用服务编排结账
                覆盖需求：`REQ-001`

                ## 测试策略
                覆盖验收标准：`AC-001`

                ## Java/Spring 质量审查
                Controller 只做协议适配。

                ## 风险与回退
                使用现有事务回滚。
            """,
            "plan.md": """
                # Checkout Plan

                ## 输入与范围
                输入：`prd.md`、`design.md`。

                ## 变更概览
                增加结账应用服务行为。

                ## 实施任务
                ### TASK-001 实现订单提交
                覆盖需求：`REQ-001`
                设计决策：`DEC-001`
                验收标准：`AC-001`
                文件：`src/main/java/com/acme/CheckoutService.java`
                测试：先验证有效订单返回已创建订单。
                验证：`./mvnw -pl checkout test`

                ## 测试与增量覆盖率
                新增代码行覆盖率阈值：90%
                新增代码分支覆盖率阈值：80%

                ## 最终验证
                运行：`./mvnw -pl checkout verify`

                ## 执行交接
                使用 `pretty-executing-plan` 执行。
            """,
            "execution.md": """
                # Checkout Execution

                ## 输入与基线
                输入：`plan.md`；基线为执行开始时 HEAD。

                ## 任务结果
                ### TASK-001 实现订单提交
                已完成，修改 `src/main/java/com/acme/CheckoutService.java`。

                ## 测试与覆盖率结果
                新增代码行覆盖率：95%
                新增代码分支覆盖率：85%

                ## 代码质量 Review
                `clean-code-guard` 与 `java-code-review` 无阻塞问题。

                ## 偏差与遗留问题
                无。

                ## 最终结论
                完成，等待人工 Review。
            """,
        }
        for filename, content in documents.items():
            (topic_dir / filename).write_text(
                textwrap.dedent(content).strip() + "\n", encoding="utf-8"
            )


class NewCodeCoverageCheckerTest(unittest.TestCase):
    def test_checks_only_added_production_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            self._init_git_repo(repo)
            source = repo / "src/main/java/com/acme/PriceService.java"
            source.parent.mkdir(parents=True)
            source.write_text(
                "package com.acme;\n"
                "public class PriceService {\n"
                "  int price(boolean premium) {\n"
                "    return premium ? 2 : 1;\n"
                "  }\n"
                "}\n",
                encoding="utf-8",
            )
            report = repo / "jacoco.xml"
            report.write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
                <report name="test"><package name="com/acme">
                  <sourcefile name="PriceService.java">
                    <line nr="3" mi="0" ci="2" mb="0" cb="0"/>
                    <line nr="4" mi="0" ci="4" mb="0" cb="2"/>
                  </sourcefile>
                </package></report>
                """,
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(COVERAGE_CHECKER),
                    "--repo",
                    str(repo),
                    "--base",
                    "HEAD",
                    "--report",
                    str(report),
                    "--line-threshold",
                    "90",
                    "--branch-threshold",
                    "80",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("line: 100.00%", result.stdout)
            self.assertIn("branch: 100.00%", result.stdout)

    def test_fails_when_added_executable_lines_miss_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            self._init_git_repo(repo)
            source = repo / "src/main/java/com/acme/PriceService.java"
            source.parent.mkdir(parents=True)
            source.write_text(
                "package com.acme;\n"
                "public class PriceService {\n"
                "  int price() { return 1; }\n"
                "  int missed() { return 2; }\n"
                "}\n",
                encoding="utf-8",
            )
            report = repo / "jacoco.xml"
            report.write_text(
                """<report name="test"><package name="com/acme">
                <sourcefile name="PriceService.java">
                  <line nr="3" mi="0" ci="2" mb="0" cb="0"/>
                  <line nr="4" mi="2" ci="0" mb="0" cb="0"/>
                </sourcefile></package></report>""",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(COVERAGE_CHECKER),
                    "--repo",
                    str(repo),
                    "--base",
                    "HEAD",
                    "--report",
                    str(report),
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("line coverage 50.00% is below 90%", result.stderr)

    @staticmethod
    def _init_git_repo(repo: Path) -> None:
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.email", "test@example.com"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.name", "Test User"],
            check=True,
        )
        (repo / "README.md").write_text("baseline\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-qm", "baseline"], check=True
        )


class CoverageRunnerTest(unittest.TestCase):
    def test_runs_maven_without_editing_pom(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            pom = project / "pom.xml"
            pom.write_text("<project/>\n", encoding="utf-8")
            self._write_fake_wrapper(
                project / "mvnw",
                "target/site/jacoco/jacoco.xml",
                "maven.args",
            )

            result = subprocess.run(
                [str(COVERAGE_RUNNER), "--project-dir", str(project)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("<project/>\n", pom.read_text(encoding="utf-8"))
            self.assertIn("jacoco-maven-plugin", (project / "maven.args").read_text())
            self.assertIn("jacoco.xml", result.stdout)

    def test_runs_gradle_with_bundled_init_script(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            build_file = project / "build.gradle"
            build_file.write_text("plugins { id 'java' }\n", encoding="utf-8")
            self._write_fake_wrapper(
                project / "gradlew",
                "build/reports/jacoco/test/jacocoTestReport.xml",
                "gradle.args",
            )

            result = subprocess.run(
                [str(COVERAGE_RUNNER), "--project-dir", str(project)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(
                "plugins { id 'java' }\n", build_file.read_text(encoding="utf-8")
            )
            args = (project / "gradle.args").read_text(encoding="utf-8")
            self.assertIn("-I", args)
            self.assertIn("jacocoTestReport", args)
            self.assertIn("jacocoTestReport.xml", result.stdout)

    @staticmethod
    def _write_fake_wrapper(wrapper: Path, report_path: str, args_file: str) -> None:
        wrapper.write_text(
            "#!/bin/sh\n"
            f"printf '%s\\n' \"$*\" > {args_file}\n"
            f"mkdir -p \"$(dirname '{report_path}')\"\n"
            f"printf '<report/>' > '{report_path}'\n",
            encoding="utf-8",
        )
        wrapper.chmod(wrapper.stat().st_mode | 0o111)


if __name__ == "__main__":
    unittest.main()
