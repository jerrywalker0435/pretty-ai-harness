---
name: pretty-writing-plan
description: Use when creating, revising, or reviewing a Java/Spring implementation plan under the standard docs/pretty topic path after the user has explicitly approved the corresponding PRD and Design, especially when the plan must address cross-module duplication, design quality, and test-first unit-test proposals.
---

# 编写 Java/Spring Implementation Plan

这是一个独立 skill。它不依赖其他 skill；本目录中的引用资料、模板和校验器是唯一的流程依据。

**硬规则：先读原则，后看源码；先看链路，后切 TASK；先设计测试，后提生产代码。只让一个类变干净、却让整条链路继续重复，不算完成。**

## 目标与边界

把用户明确批准的 PRD、Design 和真实 Java/Spring 仓库事实，转化为可审查、可执行的 `plan.md`。Plan 是实施合同和代码提案，不是实现动作。

- 只处理 Java/Spring 的新功能、Bug 修复和行为保持型重构。
- 只读真实仓库；不修改生产代码、测试代码、PRD、Design 或 Git 状态。
- 不运行项目编译、测试、覆盖率或 TDD；只在 Plan 中定义精确的 Execution 命令。
- 不调用、要求或引用其他 skill；把本 skill 需要的规则放在 `references/` 中。
- 不保留 `REQ/AC/DEC` 追溯。连续的 `TASK-001` 等编号只用于实施任务身份和 checkbox。

## 模式与输入门禁

先根据用户意图进入一个模式：

- **创建**：新建标准路径下的 `plan.md`。
- **修订**：原地更新已有标准 `plan.md`，保留用户无关改动。
- **只读评审**：只读取并报告问题，不修改任何文件、不生成下游制品。

只接受 `docs/pretty/<topic>/plan.md`，其中 `<topic>` 必须匹配 `^[a-z0-9]+(?:-[a-z0-9]+)*$`。不迁移、复制或修复非标准路径的文档。

创建或修订前必须同时满足：

1. 同一目录存在 `prd.md` 和 `design.md`。
2. 用户在当前对话中明确说 PRD 与 Design 已批准、通过或进入 Plan。
3. 文档内容没有会改变业务结果、模块 Interface、所有权、依赖方向、一致性或长期扩展点的未决问题。

文件存在、内容完整或评审结论“可进入 Plan”都不能代替用户批准。门禁不满足时停止，不创建空 Plan，不猜测，不在 Plan 内调用 `grilling`：业务结果未知返回 PRD，技术合同未知返回 Design。

## 强制执行顺序

严格按以下顺序工作；不得因为赶时间跳步：

1. **确认合同**：读取用户请求、已批准 PRD/Design，确认目标、非目标、外部结果和不可改变的边界。
2. **先读原则**：完整读取 `references/quality-principles.md`、`references/effective-java.md` 和 `references/tdd-plan.md`。
3. **形成原则基线**：先决定应采用的模块形状、Interface、Seam、职责、依赖方向、测试边界和模式适用性；不要先把仓库现状当成设计答案。
4. **调查仓库事实**：再读取 Java/Spring 版本、构建配置、入口、调用方、被调用方、Adapter、持久化/外部边界、现有测试和验证脚本。仓库代码只用于事实、兼容性和可落地路径。
5. **分析整条链路**：沿 caller → callee → Adapter → persistence/外部边界检查语义重复、职责分裂、重复校验/映射/默认值/异常映射、数据所有权、事务、并发、幂等、性能和安全。
6. **选择方案**：若存在多个会改变 Interface、Seam、Adapter、依赖方向或长期扩展性的现实方案，比较至少两个；若只有一个现实变化轴，不为形式制造候选。
7. **编写 Plan**：按可验证行为或独立风险垂直切分 TASK，展示近完整核心生产代码和测试代码。
8. **自审和校验**：做链路级质量审查、TDD 测试审查、需求内部覆盖检查和占位扫描，运行本目录的 `scripts/validate_plan.py`。
9. **停止交付**：报告路径、任务数量、质量结论、测试边界和校验结果，请求用户 Review；不得自动实现或执行 Git 动作。

## 质量优先与全局优化

以受影响业务链路的整体最优为目标，不追求无边界的全仓重构。完整规则见 `references/quality-principles.md`。

### 优先级

发生冲突时按以下顺序裁决：

1. 已批准的业务结果、外部合同和兼容性。
2. 正确性、安全性、异常、数据一致性、事务和并发。
3. 可测试性，以及小而深的模块 Interface。
4. SOLID、OOD、Clean Code、Effective Java、类型安全和可维护性。
5. YAGNI、DRY、KISS、最小变更和可逆性。
6. 只有存在真实变化轴时才使用设计模式。
7. 仓库既有风格只作事实和兼容参考，不能压过上述规则。

若更好的设计会改变已批准的业务结果或技术合同，返回 PRD/Design；不要在 Plan 中静默降级原则。

### 链路级检查

不能只检查单个类是否没有重复。必须判断多个位置是否维护同一语义规则，即使代码写法不同；文本相似只能作为线索。优先把规则归属于一个职责清晰的 Deep Module，减少调用方需要理解的 Interface，同时保持真实边界的 Locality 和可测试性。

允许修改直接相关的多个类或模块，但不得借机重构无关区域。若收敛逻辑会改变所有权、依赖方向、跨模块合同或长期扩展点，返回 Design。

跨两个以上模块或多个协作者时，在“实施结论”中增加“链路级分析”，说明：调用关系、规则唯一归属、重复收敛点、数据所有权、事务/异常/并发边界和 UT 边界。单模块 Plan 也要明确写出“不适用”的理由。

## Plan 文档合同

Plan 只写入 `docs/pretty/<topic>/plan.md`。开头使用以下独立格式，不写外部 skill 依赖：

```markdown
# <主题> Implementation Plan

**Goal:** <一句话目标>

**Architecture:** <2–3 句实现全景和链路边界>

**Tech Stack:** <真实 Java/Spring/测试技术栈>

---
```

正文必须保留五章，简单变更也不能删除章节：

1. `## 实施结论`
2. `## 实施任务`
3. `## 文件变更总览`
4. `## 测试与验证`
5. `## 共享约束和代码事实`

“共享约束和代码事实”只记录影响多个 TASK 的决定性规则和已核实事实，例如 Java 版本、模块依赖方向、公共异常合同、测试边界和真实验证入口；任务专属事实放在所属 TASK。不要重复堆砌仓库风格。

### 行为 TASK

按行为或独立风险切分，不按 Controller/Service/Repository 技术层切分，也不按 commit 大小切分。任务标题使用可读名称，编号放在末尾：

```markdown
### 重复提交不产生第二次副作用（TASK-001）
```

每个行为 TASK 必须就地包含：

1. 可观察结果、不可改变的合同和实现限制。
2. 完整仓库相对路径、symbol 和目的的文件变更表；同一任务的长路径集中出现一次。
3. 接近可编译的核心生产代码：完整签名、依赖、返回值、异常和高风险分支。
4. 核心测试代码：public 行为入口、fixture、边界 fake/stub/mock、独立预期和业务结果/状态/完整边界请求断言。
5. 测试先行的 RED → 最小 GREEN → 必要 REFACTOR 设计，以及精确命令和预期证据；Plan 阶段不执行它们。
6. `#### 质量审查`：说明链路归属、Interface/Seam/Depth、命中的原则、模式选择或不引入模式的理由、异常/并发/可测试性和仓库兼容权衡。
7. 任务依赖和完成证据。保留 `- [ ]` checkbox；不添加 `REQ/AC/DEC` 追溯。

代码任务不得使用 `TODO`、`TBD`、`FIXME`、`...`、伪码、未解析的路径/命令或“类似上一个任务”。不要只写“补测试”“处理边界”“添加适当异常”。

### 机械 TASK

纯配置、DDL、文档、改名或批量机械修改可以标记为“机械任务”，不伪造 Java 生产代码或 UT。必须给出完整变更内容、受影响路径和确定性验证/不变量检查。

### 多子系统

多个子系统能独立测试和交付时，建议拆为多个 topic/Plan；强耦合且必须一起变更时保留一个 Plan，并明确依赖顺序和链路边界。不得在 Plan 阶段擅自拆改 PRD/Design。

## 测试与验证合同

行为变更和 Bug 修复必须按 `references/tdd-plan.md` 设计 UT；行为保持型重构先固定现有行为，再设计等价重构。

- 测试使用真实被测规则和真实领域对象；边界外协作者才使用 fake/stub/mock。
- 主要断言业务结果、状态变化或完整边界请求，不以调用次数或调用顺序为主要成功标准。
- 默认只新增或扩展快速、确定、可并行的 UT；不得提议 `@SpringBootTest`、`@WebMvcTest`、`@DataJpaTest`、集成/契约/E2E、Testcontainers、嵌入式数据库或真实基础设施测试。
- 优先沿用仓库已有 JUnit/Mockito/AssertJ 和命名方式；仓库没有测试栈时，Java 默认 JUnit 5，只有确需隔离边界协作者才使用 Mockito。不新增无必要依赖。
- 先从 `pom.xml`、`build.gradle`、CI 和现有脚本确认 Java/Spring/测试版本；不得提议当前版本无法编译的语法。版本升级是前提时返回 Design。
- Plan 不运行项目编译、测试或覆盖率，只写来自真实配置的可复制命令。不能确认命令时不填占位符，记录事实缺口并停止或降低结论。
- 覆盖率优先继承仓库政策；没有明确政策时覆盖主路径、边界、异常和高风险分支，但不擅自设固定百分比。覆盖率不能替代断言质量。

校验生成的文档：

```bash
python3 <pretty-writing-plan>/scripts/validate_plan.py docs/pretty/<topic>/plan.md
```

将 `<pretty-writing-plan>` 替换为本 skill 的真实目录；未解析的占位符只能出现在这条说明中，不能进入生成的 Plan。校验器只做机械检查，不替代质量判断。

## 只读评审与修订

只读评审固定输出：

1. 阻塞问题。
2. 重要质量与链路问题。
3. 代码事实与 Plan 假设的偏差。
4. TDD、UT 边界、命令和覆盖率影响。
5. `可进入 Execution` 或 `修正后再进入 Execution`。

修订前先读取工作区状态和原文，保留用户无关改动，只更新请求范围。若新 PRD/Design 与已有 Plan 冲突，报告冲突并返回上游，不静默重写。创建、修订、评审都必须运行独立校验器；校验失败不能报告可进入 Execution。

## 反模式与红线

以下想法代表正在绕过本 skill，必须停止并重新检查：

- “只改一个类最快”——先查完整 caller/callee 链路和语义重复。
- “仓库一直这么写”——仓库是事实和兼容参考，不是质量标准。
- “有两个分支就一定上 Factory/Strategy”——先确认真实变化轴、Interface 深度和创建问题。
- “MockMvc/集成测试更真实”——Plan 默认 UT-only；边界用替身，行为用真实对象。
- “测试以后补”“已经手动验证”“代码太简单”——测试先行且必须设计真实 RED。
- “先写一个泛化命令，执行时再替换”——命令和路径必须来自仓库事实。
- “先留下重复，后面再抽”——在 Plan 里先决定唯一归属和迁移边界。
- “为了覆盖率补无价值测试”——覆盖率不能替代业务断言和错误路径。
- “为了满足格式写第二个方案/图”——只对真实决策提供候选。
- “这是全局最优，所以顺便重构整个仓库”——全局优化只覆盖受影响链路。

违反上述红线时，删除未验证的提案，从原则基线和链路分析重新开始。完成写作后必须停止并请求用户 Review，不自动实现、执行 TDD 或运行 Git 命令。
