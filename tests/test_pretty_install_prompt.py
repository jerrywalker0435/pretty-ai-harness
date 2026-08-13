from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = ROOT / "install" / "CODEX_INSTALL_PROMPT.template.md"
WORKFLOW_CONTRACT_PATH = (
    ROOT / "skills" / "pretty-java-spring-core" / "references" / "workflow-contract.md"
)

PRETTY_SKILLS = {
    "pretty-java-spring-core",
    "pretty-writing-prd",
    "pretty-writing-design",
    "pretty-writing-plan",
    "pretty-executing-plan",
}
EXTERNAL_SKILLS = {
    "domain-modeling",
    "grilling",
    "codebase-design",
    "tdd",
    "121-java-object-oriented-design",
    "122-java-type-design",
    "solid-principles",
    "refactor",
    "clean-code-guard",
    "design-patterns",
    "java-code-review",
    "verification-before-completion",
}
EXPECTED_SKILLS = PRETTY_SKILLS | EXTERNAL_SKILLS

EXPECTED_SOURCES = {
    "git@gitlab-inner.haidilao.com:zhangy114/pretty-ai-harness.git",
    "https://github.com/mattpocock/skills.git",
    "https://github.com/jabrena/cursor-rules-java.git",
    "https://github.com/florianbuetow/claude-code.git",
    "https://github.com/github/awesome-copilot.git",
    "https://github.com/amelnagdy/guard-skills.git",
    "https://github.com/decebals/claude-code-java.git",
    "https://github.com/obra/superpowers.git",
}


class PrettyInstallPromptContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.prompt = PROMPT_PATH.read_text(encoding="utf-8")

    def test_contains_exact_source_and_skill_closure(self) -> None:
        catalog = self._section("<!-- SOURCE_CATALOG_START -->", "<!-- SOURCE_CATALOG_END -->")
        sources = set(re.findall(r"(?:git@|https://)[^`\s|]+\.git", catalog))
        skills = set(re.findall(r"`([a-z0-9]+(?:-[a-z0-9]+)*)`", catalog))

        self.assertEqual(EXPECTED_SOURCES, sources)
        self.assertEqual(EXPECTED_SKILLS, skills)
        self.assertEqual(5, len(PRETTY_SKILLS))
        self.assertEqual(12, len(EXTERNAL_SKILLS))
        self.assertNotIn("springboot-tdd", self.prompt)
        self.assertNotIn("design-an-interface", self.prompt)

    def test_external_catalog_matches_current_pretty_workflow_routes(self) -> None:
        workflow = WORKFLOW_CONTRACT_PATH.read_text(encoding="utf-8")
        routed = self._backtick_skill_names(
            workflow.split("## 质量 Skill 路由", 1)[1].split("## 依赖缺失", 1)[0]
        )
        clarification = self._backtick_skill_names(
            workflow.split("## 澄清与阶段回退", 1)[1].split(
                "## 领域模型一致性", 1
            )[0]
        )
        workflow_dependencies = {
            name.removeprefix("superpowers:")
            for name in routed | clarification
        }

        self.assertEqual(EXTERNAL_SKILLS, workflow_dependencies)

    def test_requires_explicit_scope_confirmation_before_fetch_or_write(self) -> None:
        self.assertIn("当前目录：<original-CWD>/.agents/skills（默认，推荐）", self.prompt)
        self.assertIn("全局用户目录：$HOME/.agents/skills", self.prompt)
        self.assertRegex(self.prompt, r"3\.\s*取消")
        self.assertIn("展示默认值不等于获得同意", self.prompt)
        self.assertIn("空回复、含糊回复、取消或未回复", self.prompt)
        self.assertIn("不得获取任何仓库，也不得写入任何文件", self.prompt)

    def test_uses_pinned_cli_but_unpinned_latest_repository_sources(self) -> None:
        self.assertIn("npx skills@1.5.22 add <repository-url>", self.prompt)
        self.assertIn("默认分支 HEAD", self.prompt)
        self.assertIn("不得指定 commit、tag、branch 或其他 Git ref", self.prompt)
        self.assertNotRegex(self.prompt, r"(?i)\b[0-9a-f]{40}\b")
        self.assertNotRegex(self.prompt, r"https://github\.com/[^\s`]+/(?:tree|commit)/")
        self.assertNotRegex(self.prompt, r"\.git(?:#|\?ref=|@(?:main|master|v?\d))")

    def test_commands_preserve_project_and_global_scope_semantics(self) -> None:
        project_command = (
            "npx skills@1.5.22 add <repository-url> --agent universal --copy "
            "--full-depth --yes --skill <name...>"
        )
        global_command = (
            "npx skills@1.5.22 add <repository-url> --global --agent universal "
            "--copy --full-depth --yes --skill <name...>"
        )
        self.assertIn(project_command, self.prompt)
        self.assertIn(global_command, self.prompt)
        self.assertIn("npx skills@1.5.22 list --agent universal --json", self.prompt)
        self.assertIn("npx skills@1.5.22 list --global --agent universal --json", self.prompt)

    def test_existing_targets_require_one_update_confirmation(self) -> None:
        self.assertIn("文件、目录或符号链接都算已存在", self.prompt)
        self.assertIn("是否更新全部 17 个 Skill 到最新版本", self.prompt)
        self.assertIn("明确同意", self.prompt)
        self.assertIn("否则停止且不修改", self.prompt)
        self.assertNotIn("skipped-existing", self.prompt)
        self.assertNotIn("pretty-backups", self.prompt)

    def test_verifies_all_targets_directly_and_reports_every_outcome(self) -> None:
        self.assertIn("Selected 和 Installed", self.prompt)
        self.assertIn("Failed to install", self.prompt)
        self.assertIn("不得只凭退出码或旧目录仍存在", self.prompt)
        self.assertIn("检查全部 17 个目录", self.prompt)
        self.assertIn("frontmatter 的 `name`", self.prompt)
        self.assertIn("成功和失败名称", self.prompt)
        self.assertIn("重启 Codex 一次", self.prompt)

    def test_prompt_stays_focused_and_concise(self) -> None:
        self.assertLessEqual(len(self.prompt.splitlines()), 80)
        for unnecessary in (
            "run-id",
            "事务日志",
            "恢复 CLI",
            "lease",
            "journal",
            "transaction engine",
            "source lock",
            "hash checker",
        ):
            self.assertNotIn(unnecessary, self.prompt)

    def test_deliverable_has_no_custom_installer_runtime(self) -> None:
        install_files = {
            path.relative_to(ROOT).as_posix()
            for path in (ROOT / "install").rglob("*")
            if path.is_file()
        }
        self.assertEqual({"install/CODEX_INSTALL_PROMPT.template.md"}, install_files)
        for suffix in ("*.js", "*.mjs", "*.ts", "*.py", "*.sh", "*.json"):
            self.assertEqual([], list((ROOT / "install").rglob(suffix)))

    def _section(self, start: str, end: str) -> str:
        self.assertIn(start, self.prompt)
        self.assertIn(end, self.prompt)
        return self.prompt.split(start, 1)[1].split(end, 1)[0]

    @staticmethod
    def _backtick_skill_names(text: str) -> set[str]:
        return set(
            re.findall(r"`((?:superpowers:)?[a-z0-9]+(?:-[a-z0-9]+)*)`", text)
        )


if __name__ == "__main__":
    unittest.main()
