# Pretty Skills 精简与渐进式代码质量门禁 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 全面排查并精简 Pretty Skills，在不削弱四阶段合同的前提下删除冗余、重复和冲突规则，同时将 Execution 改为逐用例实施、渐进关闭代码质量问题和简洁结果记录。

**Architecture:** 实施前先完整读取 `skills/` 下每个文件，按“共享合同、阶段流程、质量标准、输出模板、机械校验、工具实现、展示元数据”确定唯一权威归属。Plan 在代码提案形成前锁定最终职责形状，Execution 从第一次生产代码编辑起持续应用质量约束，在 TASK 边界关闭局部问题，最终只检查跨 TASK 组合后才出现的问题，然后执行一次最终验证。

**Tech Stack:** Markdown Skill contracts, Python 3 `unittest`, `validate-pretty-docs.py`, Java/Spring quality skills (`clean-code-guard`, `121-java-object-oriented-design`, `solid-principles`, `java-code-review`, `refactor`, `tdd`).

---

## 设计结论

### 单一权威归属

每类规则只能有一个权威位置，其他文件只引用或补充本阶段动作：

| 规则类型 | 唯一权威 | 不再承担 |
| --- | --- | --- |
| 四阶段边界、回退规则、共同术语、共同验证边界、质量路由 | `references/workflow-contract.md` | 逐步复述每个阶段的完整操作算法 |
| 某阶段的输入、动作顺序、停止条件和交付 | 对应阶段 `SKILL.md` | 重复整个共享合同或其他阶段流程 |
| Java/Spring 风险判断 | `references/java-spring-quality.md` | 重复 TDD、覆盖率和文档格式规则 |
| 文档最小结构 | `assets/templates/*.md` | 流程说明、审计清单和 Skill 调用记录 |
| 可确定的结构、编号、引用和禁止项 | `validate-pretty-docs.py` | 判断需求、设计、DRY、SOLID 或 TDD 真实性 |
| 覆盖率采集与计算 | 覆盖率脚本和 JaCoCo asset | 重复阶段流程或文档合同 |
| UI 展示文字 | `agents/openai.yaml` | 新增流程规则 |

精简不是按行数删内容。只有满足以下条件才删除或合并：

- 相同规则已经有更合适的唯一权威位置；
- 两处表述会随演进产生同步成本；
- 当前逻辑已被新流程取代；
- 同一文件同时承担流程、质量判断和结果记录，造成职责混合；
- 删除后仍能从权威文件和阶段引用恢复完整含义。

覆盖率脚本、JaCoCo asset、PRD/Design Skill 等经过排查后若没有与本计划冲突，明确保留，不为“全面排查”制造无意义改动。

### 质量检查改为渐进式而非事后返工

旧顺序是：

```text
全部实现 -> 最终验证 -> 完整只读审查 -> 修改 -> 再验证
```

新顺序是：

```text
Plan：先设计最终职责形状并审查组合代码提案
  -> Execution：首次生产编辑前加载 clean-code-guard live mode
  -> 逐用例 TDD
  -> TASK 完成：只检查并关闭当前 TASK 增量问题
  -> 下一个 TASK
  -> 最终组合检查：只查跨 TASK 后才显现的问题
  -> 一次最终验证
  -> 简洁交付
```

具体分工：
- 任务代码，包括Plan阶段的代码提案及Execution阶段中真正的代码，优先遵循`121-java-object-oriented-design`、`solid-principles`、`clean-code-guard`等最佳实践，不要优先遵循当前项目代码样例。
- Plan 在分 TASK 前先建立 `生产 symbol -> TASK -> 最终职责` 视图。同一类会被多个 TASK 修改时，先设计其最终形状，不能逐 TASK 向同一类堆功能。
- 所有非机械 Java 代码提案在编写时持续遵守 `clean-code-guard`，全部 TASK 写完后只做一次组合提案审查。
- 对象职责、协作或边界发生变化时使用 `121-java-object-oriented-design`；服务职责、端口或依赖方向变化时使用 `solid-principles`。发现直接修正 Plan 提案，未关闭时不请求用户批准。
- Execution 在第一次生产代码编辑前加载一次 `clean-code-guard` live mode，并在本次执行后续代码变化中持续生效，不在每个用例重新加载或生成报告。
- TASK 完成时只检查当前 TASK 新增差异；能保持行为修正的问题立即使用 `refactor`，然后只复验当前 TASK。
- 最终组合检查只关注跨 TASK 涌现问题：重复知识、累计职责、接口膨胀、依赖方向不一致以及跨任务错误合同，不重复 TASK 已关闭的局部检查。
- `java-code-review` 只在实际 Java diff 命中 null、异常、并发、资源、性能或 API 合同风险时使用，不再作为每次最终交付的固定重复扫描。
- 所有质量修正完成后才执行最终验证。最终验证后没有相关代码变化时不重跑同一命令。

### Execution 只记录结果

TDD 仍按一个用例一个 RED/GREEN 执行，但 `execution.md` 不证明历史过程，不复制 RED/GREEN 命令，不维护逐用例游标。

完成态只保留四章：

1. `执行起点`：Plan 路径和起始 HEAD；
2. `TASK 结果`：每个 TASK 的结果、主要落点、TASK 验证和实质偏差；
3. `最终验证`：紧凑结果表，正常命令引用 Plan，失败或偏离 Plan 时才展开命令；
4. `结论与限制`：状态、组合代码质量结论、交付范围和关键限制。

停止态只写已经发生的事实：

- 没有完成 TASK：`执行起点 -> 恢复点 -> 结论与限制`；
- 已完成 TASK：`执行起点 -> TASK 结果 -> 恢复点 -> 结论与限制`。

Execution 开始只记录 `git rev-parse HEAD`，不执行或记录 Plan 文档校验、工作区归因快照、执行前编译、UT、静态检查或起始 HEAD 对照。最终验证失败时，能从当前 diff、失败测试和调用链可靠归因则返回相应用例；无法可靠归因则停止并写“归因不确定”，不自动扩大修复范围。

### 统一使用“用例”

运行时合同、模板、阶段 Skill、Agent 元数据和用户指南统一使用：

- `用例`；
- `逐用例 TDD`；
- `当前用例最小 GREEN`；
- `返回相应用例修正`。

不新增 `CASE-*` 或 `STEP-*`。`TASK-*` 仍是 Plan 与 Execution 之间唯一执行身份，用例只使用 TASK 内可读短名称。

## 全量排查范围与预期处置

实施者必须在修改任何 Skill 前完整读取以下全部文件；不得只用 `rg` 命中片段代替全文阅读：

| 文件组 | 文件 | 重点排查 | 预期处置 |
| --- | --- | --- | --- |
| 共享入口 | `pretty-java-spring-core/SKILL.md`、`agents/openai.yaml` | 是否重复共享合同和阶段流程 | 保留加载方式、固定路径和工具入口；删除重复流程结论 |
| 阶段流程 | 四个阶段 `SKILL.md` 与各自 `agents/openai.yaml` | 阶段间重复、过期基线、审计顺序和术语冲突 | 保留本阶段动作；统一引用共享合同；精简重复规则 |
| 模板 | `assets/templates/prd.md`、`design.md`、`plan.md`、`execution.md` | 是否混入流程说明、占位审计和重复字段 | 保留最小输出骨架；重写 Plan/Execution 相关部分 |
| 共享参考 | `references/workflow-contract.md`、`java-spring-quality.md` | 是否重复阶段算法、UT/覆盖率或质量路由 | 重建单一权威边界，删除重复段落 |
| 机械校验 | `scripts/validate-pretty-docs.py` | 是否强制无意义 Execution 字段或判断语义 | 简化 Execution 校验，保留确定性规则 |
| 覆盖率工具 | `check-new-code-coverage.py`、`run-coverage.sh`、`jacoco.init.gradle` | 是否依赖被删除的基线文档、存在重复职责 | 若仍以起始 HEAD 和最终验证正常工作则不改 |

排查时在临时工作笔记中为每个文件记录：`权威职责 / 重复 / 冲突 / 过期 / 保留或修改理由`。该矩阵只服务本次实施，不写入仓库；最终有意义的结论直接落实到 Skill 和测试。

当前工作区已有用户改动。实施不得恢复 staged 删除的 `tests/test_pretty_grilling_interaction_contract.py`、`tests/test_pretty_install_prompt.py`，也不得覆盖与本计划无关的 Design/PRD 改动。Git commit、push、MR、合并和发布不属于本计划。

---

### Task 1: 全量审计 Skills 并锁定单一权威

**Files:**

- Read: every file returned by `rg --files skills | sort`
- Modify only after audit: files classified as duplicate, conflicting, or stale

- [ ] **Step 1: 固定全量文件清单**

Run:

```bash
rg --files skills | sort
```

Expected: 输出当前 `skills/` 下全部文件，包括 5 个 Skill 包、4 个模板、2 个参考、3 个脚本、1 个 JaCoCo asset 和所有 Agent 元数据。后续新增文件也必须进入清单。

- [ ] **Step 2: 完整读取每个文件并完成职责分类**

对清单中的每个文件全文读取，并回答：

```text
1. 该文件唯一负责什么？
2. 哪些规则与其他文件重复？
3. 哪些规则与“渐进质量检查、简洁 Execution、用例术语”冲突？
4. 哪些内容已经过期？
5. 应保留、移动、引用、重写还是删除？
```

不得在本步骤修改文件。覆盖率脚本和 asset 也必须阅读；确认无冲突是有效结论。

- [ ] **Step 3: 按权威归属做修改前审计结论**

在临时工作笔记中按以下格式覆盖全部文件：

```text
<path> | <权威职责> | <重复/冲突/无> | <保留/修改> | <理由>
```

进入 Task 2 前必须确认：每条待保留规则只有一个权威位置；若两个位置都需要出现，其中一个只能是简短引用或阶段动作，不能复制完整定义。

---

### Task 2: 用合同测试锁定精简边界和执行顺序

**Files:**

- Create: `tests/test_pretty_execution_quality_contract.py`
- Test: `skills/pretty-java-spring-core/scripts/validate-pretty-docs.py`

- [ ] **Step 1: 创建运行时合同测试**

```python
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAN_SKILL = ROOT / "skills/pretty-writing-plan/SKILL.md"
EXECUTION_SKILL = ROOT / "skills/pretty-executing-plan/SKILL.md"
WORKFLOW = ROOT / "skills/pretty-java-spring-core/references/workflow-contract.md"
EXECUTION_TEMPLATE = ROOT / "skills/pretty-java-spring-core/assets/templates/execution.md"
VALIDATOR = ROOT / "skills/pretty-java-spring-core/scripts/validate-pretty-docs.py"


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_pretty_docs", VALIDATOR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PrettyRuntimeContractTest(unittest.TestCase):
    def test_plan_designs_composed_shape_before_requesting_review(self) -> None:
        plan = PLAN_SKILL.read_text(encoding="utf-8")

        self.assertLess(plan.index("生产 symbol -> TASK -> 最终职责"), plan.index("请求 Review"))
        for marker in (
            "clean-code-guard",
            "最终组合形状",
            "121-java-object-oriented-design",
            "solid-principles",
            "未关闭的代码质量发现阻塞请求 Review",
        ):
            self.assertIn(marker, plan)

    def test_execution_applies_quality_before_final_verification(self) -> None:
        execution = EXECUTION_SKILL.read_text(encoding="utf-8")

        self.assertLess(execution.index("live mode"), execution.index("逐用例 TDD"))
        self.assertLess(execution.index("最终组合检查"), execution.index("最终验证"))
        for marker in (
            "不重复 TASK 已关闭的局部检查",
            "java-code-review",
            "实际 Java 风险",
            "未关闭的代码质量发现阻塞最终验证",
        ):
            self.assertIn(marker, execution)

    def test_execution_template_only_records_results(self) -> None:
        template = EXECUTION_TEMPLATE.read_text(encoding="utf-8")

        headings = [
            line.removeprefix("## ")
            for line in template.splitlines()
            if line.startswith("## ")
        ]
        self.assertEqual(["执行起点", "TASK 结果", "最终验证", "结论与限制"], headings)
        for removed in (
            "工作区归因",
            "Plan 基线",
            "UT 边界",
            "RED：",
            "GREEN：",
            "自动审计",
            "新鲜证据核对",
            "Execution 机械校验",
        ):
            self.assertNotIn(removed, template)

    def test_runtime_skills_use_case_terminology_and_remove_old_execution_flow(self) -> None:
        runtime_files = list((ROOT / "skills").rglob("*.md"))
        runtime_files.extend((ROOT / "skills").rglob("*.yaml"))

        for path in runtime_files:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("行为切片", text, path.as_posix())
            self.assertNotIn("逐切片", text, path.as_posix())
            self.assertNotIn("Execution 基线", text, path.as_posix())
            self.assertNotIn("自动审计", text, path.as_posix())


class PrettyExecutionValidatorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.validator = load_validator()

    def test_completed_execution_accepts_compact_results(self) -> None:
        execution = """# Topic Execution

## 执行起点
- Plan：`docs/pretty/topic/plan.md`
- 起始 HEAD：`0123456789abcdef`

## TASK 结果
### 完成目标行为（TASK-001）
- 状态：完成
- 结果：目标行为已实现。
- 主要落点：`ExampleService#execute`
- 验证：相关 UT 通过。

## 最终验证
| 范围 | 结果 |
| --- | --- |
| 编译与 UT | 通过 |

## 结论与限制
- 状态：完成
- 代码质量：最终组合检查通过。
- 限制：未执行真实外部服务联调。
"""

        self.assertEqual(
            [],
            self.validator.validate_execution_document(execution, {"TASK-001"}),
        )

    def test_stopped_execution_accepts_recovery_point(self) -> None:
        execution = """# Topic Execution

## 执行起点
- Plan：`docs/pretty/topic/plan.md`
- 起始 HEAD：`0123456789abcdef`

## 恢复点
- 当前 TASK：`TASK-001`
- 原因：最终验证失败且归因不确定。
- 下一步：确认失败归属后恢复。

## 结论与限制
- 状态：停止：最终验证失败且归因不确定
- 限制：不得声明交付完成。
"""

        self.assertEqual(
            [],
            self.validator.validate_execution_document(execution, {"TASK-001"}),
        )

    def test_execution_rejects_placeholders_and_missing_task_results(self) -> None:
        execution = """# Topic Execution

## 执行起点
- 起始 HEAD：`0123456789abcdef`

## TASK 结果
### 完成目标行为（TASK-001）
- 状态：完成
- 结果：待验证

## 最终验证
- 结果：通过

## 结论与限制
- 状态：完成
"""

        errors = self.validator.validate_execution_document(
            execution, {"TASK-001", "TASK-002"}
        )
        self.assertTrue(any("placeholder" in error for error in errors))
        self.assertTrue(any("TASK-002" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试并确认旧合同为 RED**

Run:

```bash
python3 -m unittest tests/test_pretty_execution_quality_contract.py
```

Expected: FAIL。失败来自缺少新合同、旧 Execution 模板/流程仍存在或 `validate_execution_document` 尚未实现；不得接受语法、import 或夹具错误。

---

### Task 3: 精简共享核心和阶段合同

**Files:**

- Modify: `skills/pretty-java-spring-core/SKILL.md`
- Modify: `skills/pretty-java-spring-core/references/workflow-contract.md`
- Modify: `skills/pretty-java-spring-core/references/java-spring-quality.md`
- Modify if audit found duplication: `skills/pretty-writing-prd/SKILL.md`
- Modify if audit found duplication: `skills/pretty-writing-design/SKILL.md`
- Modify: `skills/pretty-writing-plan/SKILL.md`
- Modify: `skills/pretty-executing-plan/SKILL.md`
- Test: `tests/test_pretty_execution_quality_contract.py`

- [ ] **Step 1: 将共享核心缩减为加载与工具入口**

`pretty-java-spring-core/SKILL.md` 只保留：共享合同和当前模板的读取顺序、中文输出约定、标准目录/文件、校验与覆盖率工具入口、工具红线。阶段审批、Execution 顺序和质量路由只引用 `workflow-contract.md`，不再复制定义。

- [ ] **Step 2: 将共享合同收敛为跨阶段规则**

`workflow-contract.md` 保留：

```text
四阶段边界与回退
澄清和领域文档归属
共同文档/追溯规则
UT-only 与 Pretty 内外验证边界
质量 Skill 路由
最终状态与 Git 授权边界
```

删除已经在阶段 Skill 或模板中完整定义的 Plan 写作顺序、Execution RED/GREEN 操作步骤、逐字段 Execution 记录方式、最终审计算法和重复 Java 清单。共享合同只规定跨阶段不变量，阶段 Skill 决定如何执行。

- [ ] **Step 3: 将 Java/Spring 参考收敛为风险标准**

`java-spring-quality.md` 只保留 Java/Spring 专项判断：职责与依赖、事务、边界 DTO、输入信任边界、Repository/SQL、异常/日志、安全和组合代码质量。删除与共享合同重复的 UT-only 和覆盖率章节。

加入组合标准：

```markdown
## 组合代码质量

- 在 Plan 编码前按最终生产 symbol 检查累计职责和依赖，不按 TASK 局部堆叠。
- 一个业务规则只有一个权威实现位置；相同知识不得分散到 Service、Policy、Adapter 或 fixture。
- 同一类跨 TASK 修改、同时包含业务编排与基础设施 DTO、或服务多个独立 actor 时，先重新划分职责。
- 业务层依赖由业务侧定义的窄端口；Adapter/Infra 实现端口，不泄漏远端 DTO、Mapper 或框架类型。
- 不为没有当前第二个使用者的变化轴引入接口、工厂、策略、模式开关或通用命令。
```

- [ ] **Step 4: 精简 PRD/Design Skill 中已被共享合同定义的重复内容**

根据 Task 1 审计，只删除逐字或等义重复的共同规则；保留 PRD 的不同结果测试、需求澄清和 `REQ/AC` 写作，以及 Design 的技术未知关闭、表达视图和 `DEC` 写作。不得为了精简改变阶段行为。

- [ ] **Step 5: 运行合同测试观察剩余 RED**

Run:

```bash
python3 -m unittest tests/test_pretty_execution_quality_contract.py
```

Expected: 旧术语和共享流程相关失败减少；Plan、Execution、模板和校验器相关测试仍可失败。

---

### Task 4: 在 Plan 中前置最终结构与质量判断

**Files:**

- Modify: `skills/pretty-writing-plan/SKILL.md`
- Modify: `skills/pretty-java-spring-core/assets/templates/plan.md`
- Test: `tests/test_pretty_execution_quality_contract.py`

- [ ] **Step 1: 在写 TASK 前建立最终 symbol 形状**

Plan Skill 必须在编写代码提案前建立：

```text
生产 symbol -> 所属 TASK -> 最终职责 -> 直接依赖 -> 规则所有权
```

同一生产类被两个以上 TASK 修改时，先合并阅读所有拟议变化并确定最终职责；若累计变化产生多个 actor、混合抽象层级或跨层依赖，先调整 TASK/职责，不能留给 Execution 事后重构。

- [ ] **Step 2: 将质量能力用于写作过程和一次组合审查**

在写第一段非机械 Java 提案前使用 `clean-code-guard` live mode，并在后续提案中持续应用，不按 TASK 重复加载。全部 TASK 完成后，只审一次最终组合形状。

触发规则：

```markdown
- 对象职责、协作、封装或聚合变化：使用 `121-java-object-oriented-design`。
- 服务职责、端口或依赖方向变化：使用 `solid-principles`。
- 质量发现直接修正代码提案；未关闭的代码质量发现阻塞请求 Review。
- 改变 Design 合同返回 Design；改变外部结果返回 PRD。
```

- [ ] **Step 3: 统一用例术语并删除 Execution 基线**

Plan 仍用 `TASK-*` 组织垂直行为，每个 TASK 内使用无编号的“用例”。删除 `Execution 基线`，只保留一次最终验证命令：编译、新/改 UT、直接相关回归、静态检查和适用覆盖率。

模板中的可选用例块为：

```markdown
#### 用例：<可读短名称>

- 测试入口：`<TestClass#method>`
- 目标行为：<独立业务预期与关键边界>
```

模板不增加 OOD 检查清单或 Skill 调用记录；质量体现在最终代码提案。

- [ ] **Step 4: 运行合同测试**

Run:

```bash
python3 -m unittest tests/test_pretty_execution_quality_contract.py
```

Expected: Plan 顺序和组合审查测试 PASS；Execution 与校验器测试仍可失败。

---

### Task 5: 将 Execution 改为持续质量约束和一次最终验证

**Files:**

- Modify: `skills/pretty-executing-plan/SKILL.md`
- Modify: `skills/pretty-executing-plan/agents/openai.yaml`
- Rewrite: `skills/pretty-java-spring-core/assets/templates/execution.md`
- Test: `tests/test_pretty_execution_quality_contract.py`

- [ ] **Step 1: 将启动动作缩减为记录起始 HEAD**

Execution 开始只运行并记录：

```bash
git rev-parse HEAD
```

不运行 Plan 校验、工作区归因采集、编译/UT/静态基线或起始 HEAD 失败对照。恢复时读取真实 diff、测试和已完成 TASK 结果，不依赖逐用例日志。

- [ ] **Step 2: 在第一次生产编辑前启用持续质量约束**

进入逐用例 TDD 前，若计划存在非机械生产代码修改，使用一次 `clean-code-guard` live mode；后续所有生产修改持续遵守该 Skill，不重复加载或输出逐 TASK 报告。

逐用例流程只保留：

```text
[一个 UT] -> [确认因目标行为缺失而正确 RED]
  -> [当前用例最小 GREEN]
  -> [下一个用例]
```

- [ ] **Step 3: 在 TASK 边界立即关闭局部问题**

TASK 的全部用例 GREEN 后，仅检查该 TASK 新增生产差异是否违反已经启用的 guard。发现行为保持结构问题时使用 `refactor` 修正，只复验当前 TASK；行为错误返回相应用例；超出合同返回 Plan、Design 或 PRD。未关闭的局部质量问题阻塞进入下一 TASK。

- [ ] **Step 4: 最终只检查跨 TASK 涌现问题**

全部 TASK 完成后，在最终验证前执行“最终组合检查”，只检查：

```text
跨 TASK 重复知识
同一类累计职责和混合抽象层级
接口因多个 TASK 叠加而膨胀
依赖方向或对象转换在边界间不一致
跨 TASK 异常、事务、并发或兼容合同冲突
```

不重复 TASK 已关闭的局部检查。组合问题命中对象职责或依赖方向时才使用相应 OOD/SOLID Skill；实际 Java 风险命中 null、异常、并发、资源、性能或 API 合同时才使用 `java-code-review`。发现立即修正并复验受影响 TASK；未关闭的代码质量发现阻塞最终验证。

- [ ] **Step 5: 质量关闭后只执行一次最终验证**

运行 Plan 定义的编译、新/改 UT、相关回归、静态检查和适用覆盖率。失败能可靠归因到本次变更则返回相应用例；无法可靠归因则停止并声明“归因不确定”。最终验证后只有相关代码变化才重跑受影响范围。

- [ ] **Step 6: 重写四章 Execution 模板**

```markdown
# <主题> Execution

## 执行起点

- Plan：`docs/pretty/<topic>/plan.md`
- 起始 HEAD：`<sha>`

## TASK 结果

### <任务名>（TASK-001）

- 状态：<完成/已满足（无生产差异）>
- 结果：<可观察结果>
- 主要落点：`<module / Class#method>`
- 验证：<TASK 级结果摘要>
- 实质偏差：<只在存在时保留>

## 最终验证

| 范围 | 结果 |
| --- | --- |
| 受影响模块编译 | <通过/失败> |
| 本次全部新/改 UT | <通过/失败与关键数字> |
| 直接相关回归 UT | <通过/失败与关键数字> |
| 快速静态检查 | <通过/失败/不适用> |
| 覆盖率 | <结果/不适用> |

## 结论与限制

- 状态：完成
- 代码质量：<最终组合检查结论；有发现时只写实质处置>
- 交付范围：<代码结果和验证范围>
- 限制：<限制声明的关键未验证项>
```

模板不包含基线、工作区归因、RED/GREEN、自动审计、新鲜证据、机械校验、通用 Git 授权或未来状态占位。

- [ ] **Step 7: 更新展示元数据并运行合同测试**

`short_description` 改为：

```yaml
short_description: "执行 Java/Spring Plan，逐用例 TDD 并渐进关闭代码质量问题"
```

Run:

```bash
python3 -m unittest tests/test_pretty_execution_quality_contract.py
```

Expected: Skill 顺序、术语和模板测试 PASS；校验器测试仍可失败。

---

### Task 6: 简化 Execution 机械校验

**Files:**

- Modify: `skills/pretty-java-spring-core/scripts/validate-pretty-docs.py`
- Test: `tests/test_pretty_execution_quality_contract.py`

- [ ] **Step 1: 删除旧过程字段校验**

删除 `EXECUTION_REQUIRED_MARKERS`、`EXECUTION_TASK_REQUIRED_MARKERS`、`BASELINE_STOP_MARKERS` 及其调用。Execution 不再要求工作区归因、Plan 基线、自动审计等过程字段。

- [ ] **Step 2: 实现独立的简洁 Execution 校验函数**

```python
EXECUTION_COMPLETE_HEADINGS = (
    "执行起点",
    "TASK 结果",
    "最终验证",
    "结论与限制",
)
EXECUTION_STOP_HEADINGS = (
    ("执行起点", "恢复点", "结论与限制"),
    ("执行起点", "TASK 结果", "恢复点", "结论与限制"),
)
EXECUTION_PLACEHOLDER_PATTERN = re.compile(
    r"待执行|待验证|待审计|待逐[^\n]*记录|执行中"
)


def validate_execution_document(text: str, tasks: Set[str]) -> List[str]:
    errors: List[str] = []
    headings = tuple(heading_titles(text))
    conclusion = subsection(text, "## 结论与限制")
    completed = bool(re.search(r"^- 状态：完成\s*$", conclusion, re.MULTILINE))
    stopped = bool(
        re.search(
            r"^- 状态：(停止：.+|返回 (?:Plan|Design|PRD)：.+)\s*$",
            conclusion,
            re.MULTILINE,
        )
    )

    if EXECUTION_PLACEHOLDER_PATTERN.search(text):
        errors.append("execution.md contains a placeholder")

    if completed:
        if headings != EXECUTION_COMPLETE_HEADINGS:
            errors.append("execution.md completed headings are invalid")
        reported = set(PLAN_TASK_HEADING_PATTERN.findall(text))
        for unknown in sorted(reported - tasks):
            errors.append(f"execution.md references unknown {unknown}")
        for missing in sorted(tasks - reported):
            errors.append(f"execution.md does not report {missing}")
        return errors

    if stopped:
        if headings not in EXECUTION_STOP_HEADINGS:
            errors.append("execution.md stopped headings are invalid")
        return errors

    errors.append("execution.md must contain a final completed or stopped status")
    return errors
```

从通用固定 H2 校验中排除 Execution，由 `validate_execution_document` 判断完成态和停止态。现有 `validate_execution` 只把该函数返回的错误合入总错误列表，并保留禁止新增非 UT 的确定性检查。

- [ ] **Step 3: 运行测试和 Python 编译**

Run:

```bash
python3 -m unittest tests/test_pretty_execution_quality_contract.py
python3 -m py_compile skills/pretty-java-spring-core/scripts/validate-pretty-docs.py
```

Expected: 全部 PASS，编译命令 exit code 0。

---

### Task 7: 同步指南、样本术语并验证全仓一致性

**Files:**

- Modify: `ai-harness-skill-orchestration-guide.md`
- Modify: `docs/plan.md`
- Modify: `docs/execution.md`
- Read only: `docs/superpowers/specs/2026-08-12-pretty-skill-design.md`
- Test: `tests/test_pretty_execution_quality_contract.py`

- [ ] **Step 1: 定向同步现行用户指南**

只修改与新合同冲突的段落：统一“用例”术语；删除执行前基线和逐用例证据；说明 Plan 前置最终职责形状、Execution 持续 guard、TASK 局部关闭、最终组合检查和一次最终验证。不扩写新的审计章节或质量报告。

- [ ] **Step 2: 只同步当前诊断样本术语**

在 `docs/plan.md`、`docs/execution.md` 把旧术语改为“用例”。样本来自另一个仓库的中途执行，不能为了展示新模板而虚构完成态或验证结果。

日期化历史设计保留历史语义。若需要消除误导，只在旧设计开头增加一行指向本计划，不批量重写历史决定。

- [ ] **Step 3: 重新执行全量 Skills 排查**

再次完整核对 Task 1 清单，确认：

```text
每类规则只有一个权威位置
阶段 Skill 没有复制共享合同长段落
质量参考没有重复 UT/覆盖率规则
模板没有流程与审计说明
校验器没有语义判断
Agent 元数据与实际流程一致
覆盖率工具仍与起始 HEAD 和最终验证兼容
```

发现冗余、重复或冲突时直接精简相应 Skill，再重跑后续验证。

- [ ] **Step 4: 搜索过期运行时逻辑**

Run:

```bash
rg -n '行为切片|逐切片|切片级|切片内|返回切片|Execution 基线|自动审计|Plan 基线|工作区归因' \
  skills ai-harness-skill-orchestration-guide.md docs/plan.md docs/execution.md
```

Expected: 无匹配。日期化历史设计不属于运行时合同，不纳入该搜索。

- [ ] **Step 5: 运行全部当前可用测试与静态检查**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m py_compile \
  skills/pretty-java-spring-core/scripts/validate-pretty-docs.py \
  skills/pretty-java-spring-core/scripts/check-new-code-coverage.py
git diff --check
```

Expected: 全部 exit code 0。不得恢复用户已删除的测试来制造通过结果。

- [ ] **Step 6: 最终检查本次 Skill 重构本身**

使用 `clean-code-guard` 检查 Python diff 和 Skill 合同，重点确认：

- 校验器函数职责单一、命名明确、没有重复状态解析；
- 新流程没有把删除的审计换成另一套检查清单；
- Plan、Execution、共享路由和模板之间没有顺序冲突；
- 全量排查没有演变成永久报告或无意义文件改动；
- 最终组合检查不重复 TASK 局部检查。

若发生修改，重新运行 Step 3–5。

## 完成标准

- 实施前后都完整核对 `skills/` 下全部文件，每个文件有清晰单一职责；
- 共享合同、阶段 Skill、质量参考、模板和校验器之间不存在已知冗余、重复或冲突规则；
- Plan 在写代码提案前确定最终 symbol 职责，组合质量问题在请求 Review 前关闭；
- Execution 从首次生产编辑起持续应用质量规则，TASK 边界关闭局部问题，最终只检查跨 TASK 涌现问题；
- `java-code-review` 按实际 Java 风险触发，不再固定重复扫描；
- 所有质量修正完成后只运行一次最终验证；
- `execution.md` 完成态只有四章，不记录基线、工作区归因、逐用例 RED/GREEN 或自动审计流水；
- 校验器只检查确定性结构、状态、TASK 覆盖和占位符，不判断代码质量；
- 所有现行运行时材料统一使用“用例”；
- 新合同测试、全部当前可用测试、Python 编译和 `git diff --check` 通过；
- 不覆盖无关用户改动，不自动执行 Git 或发布动作。
