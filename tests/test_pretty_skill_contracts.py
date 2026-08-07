from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS = REPO_ROOT / "skills"


class PrettySkillContractTest(unittest.TestCase):
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
        self.assertIn("superpowers:test-driven-development", skill)
        self.assertIn("clean-code-guard", skill)
        self.assertIn("java-code-review", skill)
        self.assertIn("superpowers:verification-before-completion", skill)
        self.assertRegex(skill, re.compile(r"行为.*RED.*GREEN", re.DOTALL))
        self.assertRegex(skill, re.compile(r"非行为.*等价验证", re.DOTALL))
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
