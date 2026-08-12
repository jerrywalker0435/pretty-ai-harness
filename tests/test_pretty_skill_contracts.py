from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS = REPO_ROOT / "skills"
INSTALLER_DESIGN = (
    REPO_ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-08-12-pretty-skills-prompt-only-installer-design.md"
)
ORCHESTRATION_GUIDE = REPO_ROOT / "ai-harness-skill-orchestration-guide.md"


class PrettySkillContractTest(unittest.TestCase):
    def test_installer_routes_tdd_from_mattpocock_and_keeps_superpowers_verifier(
        self,
    ) -> None:
        design = INSTALLER_DESIGN.read_text(encoding="utf-8")

        self.assertRegex(
            design,
            re.compile(
                r"mattpocock/skills\.git.*domain-modeling.*grilling.*design-an-interface.*`tdd`",
                re.DOTALL,
            ),
        )
        self.assertRegex(
            design,
            re.compile(
                r"obra/superpowers\.git.*`verification-before-completion`",
                re.DOTALL,
            ),
        )
        self.assertNotIn("`test-driven-development`", design)
        self.assertRegex(
            design,
            re.compile(
                r"five Pretty\s+Skills and their thirteen required external Skills"
            ),
        )

    def test_orchestration_guide_describes_pretty_tdd_contract(self) -> None:
        guide = ORCHESTRATION_GUIDE.read_text(encoding="utf-8")

        self.assertNotIn("superpowers:test-driven-development", guide)
        for marker in (
            "`tdd`",
            "测试边界",
            "独立预期值",
            "垂直切片",
            "`refactor`",
            "90%",
            "80%",
        ):
            self.assertIn(marker, guide)

    def test_repository_markdown_uses_chinese_test_boundary_term(self) -> None:
        violations = []
        for path in REPO_ROOT.rglob("*.md"):
            if ".git" in path.parts:
                continue
            content = path.read_text(encoding="utf-8")
            if re.search(r"\bseams?\b", content, re.IGNORECASE):
                violations.append(str(path.relative_to(REPO_ROOT)))

        self.assertEqual([], violations)

    def test_shared_core_does_not_route_removed_quality_skill(self) -> None:
        core = (SKILLS / "pretty-java-spring-core" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        workflow = (
            SKILLS
            / "pretty-java-spring-core"
            / "references"
            / "workflow-contract.md"
        ).read_text(encoding="utf-8")

        self.assertNotIn("code-smell-detector", core + workflow)

    def test_shared_core_centralizes_domain_modeling_policy(self) -> None:
        workflow = (
            SKILLS
            / "pretty-java-spring-core"
            / "references"
            / "workflow-contract.md"
        ).read_text(encoding="utf-8")

        for marker in (
            "domain-modeling",
            "CONTEXT.md",
            "CONTEXT-MAP.md",
            "PRD 与 Design",
            "Plan 与 Executing",
            "触发后强制",
            "grilling",
        ):
            self.assertIn(marker, workflow)
        self.assertRegex(
            workflow,
            re.compile(
                r"实体.*值对象.*状态.*不变量.*聚合.*所有权.*领域事件",
                re.DOTALL,
            ),
        )
        self.assertRegex(workflow, re.compile(r"难以撤销.*真实权衡.*ADR", re.DOTALL))
        self.assertRegex(workflow, re.compile(r"Plan 与 Executing.*不得.*更新", re.DOTALL))

    def test_shared_core_routes_behavior_through_tdd_and_refactoring_separately(
        self,
    ) -> None:
        workflow = (
            SKILLS
            / "pretty-java-spring-core"
            / "references"
            / "workflow-contract.md"
        ).read_text(encoding="utf-8")

        self.assertIn("| 任意生产行为变更 | `tdd` |", workflow)
        self.assertNotIn("superpowers:test-driven-development", workflow)
        self.assertRegex(
            workflow,
            re.compile(r"测试边界.*Plan.*Review.*确认", re.DOTALL),
        )
        self.assertRegex(
            workflow,
            re.compile(r"springboot-tdd.*测试技术.*tdd.*测试质量", re.DOTALL),
        )
        self.assertRegex(
            workflow,
            re.compile(r"重构.*触发.*refactor.*缺失.*阻塞", re.DOTALL),
        )

    def test_prd_review_mode_does_not_mutate_domain_documents(self) -> None:
        workflow = (
            SKILLS
            / "pretty-java-spring-core"
            / "references"
            / "workflow-contract.md"
        ).read_text(encoding="utf-8")

        self.assertRegex(
            workflow,
            re.compile(
                r"评审模式.*不修改文件.*只报告.*domain-modeling.*创建或修订",
                re.DOTALL,
            ),
        )
        self.assertRegex(
            workflow,
            re.compile(r"除 PRD 评审模式外.*每个阶段", re.DOTALL),
        )

    def test_design_and_core_share_java_type_trigger_vocabulary(self) -> None:
        design = (SKILLS / "pretty-writing-design" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        workflow = (
            SKILLS
            / "pretty-java-spring-core"
            / "references"
            / "workflow-contract.md"
        ).read_text(encoding="utf-8")
        trigger = "值对象、泛型、类型层次、金额类型或 primitive obsession"

        self.assertIn(trigger, design)
        self.assertIn(trigger, workflow)

    def test_prd_skill_is_a_thin_stage_wrapper(self) -> None:
        skill = (SKILLS / "pretty-writing-prd" / "SKILL.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("pretty-java-spring-core", skill)
        self.assertIn("docs/pretty/<topic>/prd.md", skill)
        self.assertIn("--through prd", skill)
        self.assertIn("domain-modeling", skill)
        self.assertIn("CONTEXT.md", skill)
        self.assertIn("CONTEXT-MAP.md", skill)
        self.assertRegex(skill, re.compile(r"术语.*身份.*生命周期.*不变量", re.DOTALL))
        self.assertRegex(skill, re.compile(r"PRD.*不.*ADR", re.DOTALL))
        self.assertLess(len(skill.split()), 700)
        for legacy_marker in (
            "批准记录",
            "跨层增量修订包",
            "superpowers:brainstorming",
            "validate-prd.sh",
            "references/quality-gates.md",
        ):
            self.assertNotIn(legacy_marker, skill)
        self.assertRegex(skill, re.compile(r"一次.*Review", re.DOTALL))

    def test_prd_skill_supports_non_mutating_review_mode(self) -> None:
        skill = (SKILLS / "pretty-writing-prd" / "SKILL.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("评审模式（不修改文件）", skill)
        self.assertRegex(skill, re.compile(r"评审模式.*任意路径", re.DOTALL))
        self.assertRegex(
            skill,
            re.compile(r"阻塞问题.*建议改进.*下游影响.*可进入 Design", re.DOTALL),
        )
        self.assertRegex(
            skill,
            re.compile(r"评审模式.*不.*修改.*PRD.*CONTEXT\.md", re.DOTALL),
        )
        self.assertRegex(
            skill,
            re.compile(r"标准.*目录.*完整.*校验.*非标准.*不.*移动", re.DOTALL),
        )
        self.assertIn("非标准路径不运行标准链路校验", skill)
        self.assertRegex(
            skill,
            re.compile(r"评审模式.*不创建评审文档.*不移动或复制", re.DOTALL),
        )
        self.assertRegex(
            skill,
            re.compile(r"用户要求解决或修订后才使用 `grilling`", re.DOTALL),
        )

    def test_prd_skill_conditionally_uses_concrete_business_stories(self) -> None:
        skill = (SKILLS / "pretty-writing-prd" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        template = (
            SKILLS
            / "pretty-java-spring-core"
            / "assets"
            / "templates"
            / "prd.md"
        ).read_text(encoding="utf-8")

        for marker in (
            "3–6",
            "多个真实角色",
            "状态分支",
            "失败隔离",
            "幂等",
            "并发",
            "作为……我希望……以便……",
            "真实角色",
            "不强制",
            "解释视图",
            "唯一需求合同",
            "关联需求",
            "关联验收",
        ):
            self.assertIn(marker, skill)
        self.assertRegex(skill, re.compile(r"代表性.*AC.*详细.*边界", re.DOTALL))
        self.assertRegex(skill, re.compile(r"不.*新增.*US", re.DOTALL))
        for marker in (
            "简单需求",
            "复杂需求",
            "### <业务故事名称>",
            "作为<真实角色>，我希望<业务目标>，以便<业务价值>",
            "关联需求：`REQ-001`",
            "关联验收：`AC-001`",
        ):
            self.assertIn(marker, template)

    def test_design_skill_is_a_thin_stage_wrapper(self) -> None:
        skill = (SKILLS / "pretty-writing-design" / "SKILL.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("pretty-java-spring-core", skill)
        self.assertIn("docs/pretty/<topic>/design.md", skill)
        self.assertIn("--through design", skill)
        self.assertIn("domain-modeling", skill)
        self.assertIn("CONTEXT.md", skill)
        self.assertIn("CONTEXT-MAP.md", skill)
        self.assertRegex(skill, re.compile(r"共享合同.*Design.*domain-modeling", re.DOTALL))
        self.assertRegex(skill, re.compile(r"REQ.*AC.*返回 PRD", re.DOTALL))
        self.assertIn("ADR", skill)
        self.assertLess(len(skill.split()), 900)
        for required_skill in (
            "121-java-object-oriented-design",
            "122-java-type-design",
            "solid-principles",
            "refactor",
            "design-an-interface",
            "design-patterns",
            "springboot-tdd",
        ):
            self.assertIn(required_skill, skill)
        for legacy_marker in (
            "superpowers:brainstorming",
            "code-smell-detector",
            "批准记录",
            "跨层增量修订",
            "validate-design.sh",
            "references/quality-gates.md",
        ):
            self.assertNotIn(legacy_marker, skill)
        self.assertRegex(skill, re.compile(r"一次.*Review", re.DOTALL))

    def test_plan_skill_is_a_preimplementation_cr_wrapper(self) -> None:
        skill = (SKILLS / "pretty-writing-plan" / "SKILL.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("pretty-java-spring-core", skill)
        self.assertIn("docs/pretty/<topic>/plan.md", skill)
        self.assertIn("--through plan", skill)
        self.assertIn("CONTEXT.md", skill)
        self.assertIn("CONTEXT-MAP.md", skill)
        self.assertIn("domain-modeling", skill)
        self.assertRegex(skill, re.compile(r"不.*调用.*domain-modeling", re.DOTALL))
        self.assertRegex(skill, re.compile(r"不得.*更新.*CONTEXT", re.DOTALL))
        self.assertRegex(skill, re.compile(r"需求.*返回 PRD.*领域设计.*返回 Design", re.DOTALL))
        self.assertIn("CR", skill)
        self.assertRegex(skill, re.compile(r"完整.*关键.*生产.*测试代码", re.DOTALL))
        self.assertRegex(skill, re.compile(r"机械.*变更表", re.DOTALL))
        self.assertIn("**REQUIRED SUB-SKILL：** 使用 `tdd`", skill)
        self.assertNotIn("superpowers:test-driven-development", skill)
        for marker in (
            "测试边界",
            "独立预期值",
            "垂直切片",
            "测试提案",
            "拟议生产代码",
        ):
            self.assertIn(marker, skill)
        self.assertRegex(
            skill,
            re.compile(r"先.*测试提案.*再.*拟议生产代码", re.DOTALL),
        )
        self.assertRegex(
            skill,
            re.compile(r"用户.*Review.*确认.*测试边界", re.DOTALL),
        )
        self.assertRegex(
            skill,
            re.compile(r"springboot-tdd.*技术.*tdd.*质量", re.DOTALL),
        )
        self.assertIn("90%", skill)
        self.assertIn("80%", skill)
        self.assertIn("新增生产代码", skill)
        self.assertIn("未触碰历史代码", skill)
        self.assertIn("run-coverage.sh", skill)
        self.assertIn("check-new-code-coverage.py", skill)
        self.assertIn("--file", skill)
        self.assertLess(len(skill.split()), 1100)
        for legacy_marker in (
            "superpowers:writing-plans",
            "superpowers:subagent-driven-development",
            "superpowers:executing-plans",
            "批准记录",
            "候选提交",
            "当前分支本地提交",
            "validate-plan.sh",
            "references/quality-gates.md",
        ):
            self.assertNotIn(legacy_marker, skill)
        self.assertRegex(skill, re.compile(r"一次.*Review", re.DOTALL))

    def test_design_and_plan_consume_business_stories_without_new_ids(self) -> None:
        design = (SKILLS / "pretty-writing-design" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        plan = (SKILLS / "pretty-writing-plan" / "SKILL.md").read_text(
            encoding="utf-8"
        )

        self.assertRegex(
            design,
            re.compile(r"业务故事.*端到端.*状态分支.*失败", re.DOTALL),
        )
        self.assertRegex(
            plan,
            re.compile(r"业务故事.*测试.*多对多.*不.*E2E", re.DOTALL),
        )
        for downstream_skill in (design, plan):
            self.assertRegex(
                downstream_skill,
                re.compile(r"不.*新增.*US", re.DOTALL),
            )
            self.assertIn("`REQ/AC` 仍是唯一需求合同", downstream_skill)

    def test_executing_skill_uses_classified_gates_without_git_orchestration(
        self,
    ) -> None:
        skill = (SKILLS / "pretty-executing-plan" / "SKILL.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("pretty-java-spring-core", skill)
        self.assertIn("docs/pretty/<topic>/plan.md", skill)
        self.assertIn("docs/pretty/<topic>/execution.md", skill)
        self.assertIn("--through execution", skill)
        self.assertIn("CONTEXT.md", skill)
        self.assertIn("CONTEXT-MAP.md", skill)
        self.assertIn("domain-modeling", skill)
        self.assertRegex(skill, re.compile(r"不.*调用.*domain-modeling", re.DOTALL))
        self.assertRegex(skill, re.compile(r"不得.*更新.*CONTEXT", re.DOTALL))
        self.assertRegex(
            skill,
            re.compile(r"需求.*PRD.*领域设计.*Design.*实施计划.*Plan", re.DOTALL),
        )
        self.assertIn("**REQUIRED SUB-SKILL：** 使用 `tdd`", skill)
        self.assertNotIn("superpowers:test-driven-development", skill)
        self.assertIn("clean-code-guard", skill)
        self.assertIn("java-code-review", skill)
        self.assertIn("superpowers:verification-before-completion", skill)
        self.assertRegex(skill, re.compile(r"行为.*RED.*GREEN", re.DOTALL))
        self.assertRegex(skill, re.compile(r"非行为.*等价验证", re.DOTALL))
        self.assertRegex(skill, re.compile(r"每次只.*一个.*测试", re.DOTALL))
        self.assertRegex(skill, re.compile(r"垂直切片", re.DOTALL))
        self.assertRegex(
            skill,
            re.compile(r"Plan.*Review.*确认.*测试边界.*不再.*询问", re.DOTALL),
        )
        self.assertRegex(
            skill,
            re.compile(r"编译.*RED.*行为 RED", re.DOTALL),
        )
        self.assertRegex(
            skill,
            re.compile(r"首次通过.*不.*伪造.*RED", re.DOTALL),
        )
        self.assertRegex(
            skill,
            re.compile(r"重构.*REQUIRED SUB-SKILL.*refactor.*复验", re.DOTALL),
        )
        self.assertRegex(
            skill,
            re.compile(r"独立预期值.*实现", re.DOTALL),
        )
        self.assertRegex(
            skill,
            re.compile(r"mock.*外部边界.*业务结果", re.DOTALL),
        )
        self.assertRegex(
            skill,
            re.compile(r"紧急.*期限.*已投入.*负责人.*不.*豁免", re.DOTALL),
        )
        self.assertRegex(
            skill,
            re.compile(r"首次通过.*诊断证据", re.DOTALL),
        )
        self.assertRegex(
            skill,
            re.compile(r"当前.*行为切片.*无关遗留.*返回 Plan", re.DOTALL),
        )
        self.assertRegex(skill, re.compile(r"一次.*最终.*独立.*Review", re.DOTALL))
        self.assertIn("90%", skill)
        self.assertIn("80%", skill)
        self.assertIn("新增生产代码", skill)
        self.assertIn("未触碰历史代码", skill)
        self.assertIn("run-coverage.sh", skill)
        self.assertIn("check-new-code-coverage.py", skill)
        self.assertIn("--file", skill)
        self.assertLess(len(skill.split()), 1300)
        for legacy_marker in (
            "superpowers:using-git-worktrees",
            "superpowers:subagent-driven-development",
            "superpowers:executing-plans",
            "Plan 批次基线哈希",
            "证据指纹",
            "候选提交",
            "批准记录",
            "validate-execution.sh",
            "references/quality-gates.md",
        ):
            self.assertNotIn(legacy_marker, skill)
        self.assertRegex(skill, re.compile(r"不.*自动.*commit", re.IGNORECASE | re.DOTALL))


if __name__ == "__main__":
    unittest.main()
