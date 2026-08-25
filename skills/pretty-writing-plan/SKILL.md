---
name: pretty-writing-plan
description: Create, revise, or review a Java/Spring implementation Plan from an approved Design, its PRD, domain context, and real repository code.
---

# 编写 Java/Spring Implementation Plan

把已批准 Design 转成可审查、可落地的核心代码实施方案。Plan 是唯一最终产物，也是 Execution 的规范实现基线；本阶段只读，不修改或编译项目代码。

## 输入 Gate

主输入是 `docs/pretty/<topic>/design.md`。创建或修订前必须：

1. 同目录存在 `prd.md`，且用户在当前对话明确批准 PRD 与 Design 进入 Plan。
2. 完整读取 `design.md` 和 `prd.md`。
3. 查找并读取仓库中适用的 Context、Context Map 和相关 ADR；使用仓库真实文件名（如 `Context.md`、`Context-Map.md` 或仓库约定的全大写形式），不存在时不伪造也不阻断。
4. 读取仓库规则、构建版本和真实代码，验证调用链、类型、API、配置、Schema 与协议事实。
5. 不存在会改变业务结果、外部合同、Interface、所有权、依赖方向或长期扩展点的未决问题。

业务语义不明返回 PRD，技术合同不明返回 Design。只接受 `docs/pretty/<topic>/plan.md`，topic 使用小写 kebab-case。

## 唯一共享规则

创建、修订和审查都完整读取：

- [共享质量基线](../pretty-common/references/quality-principles.md)
- [质量路由](../pretty-common/references/quality-routing.md)
- [独立审查协议](../pretty-common/references/quality-review-protocol.md)

逻辑 TASK 还读取 `tdd`；不可用时读取 [测试设计](references/test-design.md)。不调用额外草稿 Skill，不复制共享规则到本文件或 Plan。

## 工作流

1. **确认合同**：提取批准结果、非目标、外部行为和不可改变边界。
2. **一次代码盘点**：广度查找入口、caller、callee、Adapter、消费者、注册点、配置、Schema、协议和测试；范围止于受影响链路，并复用已确认的路径、symbol 和合同事实，不重复全仓扫描。
3. **深读实现**：确认规则归属、数据所有权、异常和副作用顺序、事务、并发、幂等及兼容限制。不能把存量实现默认当作正确设计。
4. **完整路由**：按共享路由为每个有证据的风险分配唯一主审 Skill，不限制风险维度数量；新风险增量路由。
5. **一次成稿**：按可观察领域结果垂直切分 TASK，展示完整变更 symbol、必要声明内容和核心行为测试，不复制整个文件、重复调用链或不会改变实现决策的样板说明。
6. **机械 Gate 与自审**：对完整候选运行一次 `scripts/validate_plan.py --scan-only`，集中修复全部 `error`，再按 findings 完成 Writer 自审。
7. **一次独立审查**：Reviewer 按共享协议审查完整候选和路由完整性。修复后只复核 findings 涉及的增量，最终证据仍绑定完整候选摘要；Reviewer 超时不创建重复审查任务或继续串行空等。
8. **交付**：只写最终 `plan.md` 并请求用户 Review；不执行编译、测试、覆盖率或 Git 动作。

## Plan 合同

最终文档只包含标题、按需的受影响链路和实施任务。任务编号从 `TASK-001` 连续递增，并按以下顺序组织：

1. `约束`：只写代码无法直接表达的外部合同、归属或兼容限制。
2. `Files`：列出真实仓库相对路径及 Create、Modify、Test 或 Delete。
3. `修改`：逻辑 TASK 展示完整核心生产 symbol；声明 TASK 展示完整声明内容。
4. `测试`：Java 逻辑 TASK 展示公共行为入口、真实输入、边界替身和结果断言。
5. `数据库验证`：SQL、DDL、索引或迁移 TASK 声明验证类型、目标引擎、可观察期望和非破坏性 SQL；不得用 Java UT 或 SQL 文本断言代替数据库验证。Java 与 SQL 混合 TASK 同时保留 `测试` 和 `数据库验证`。
6. `依赖`：只在 TASK 顺序确实受影响时保留。

核心代码必须让人看出输入输出、异常合同、不变量边界、正常与失败流、副作用顺序、规则唯一归属和类型约束。每个外部类型、方法和注解都从真实源码或当前依赖版本确认。不得使用占位符、伪代码、省略号、行号范围、个人绝对路径、质量自评、Skill 名称、执行状态或验证结果。

Execution 默认遵守核心代码表达的职责、公共签名、异常合同、数据所有权、测试边界和外部行为。只有语义不变的编译或集成调整可以继续；改变上述基线必须返回 Plan。

## 校验

候选审查时运行：

```bash
python3 <pretty-writing-plan>/scripts/validate_plan.py \
  docs/pretty/<topic>/plan.md --scan-only

python3 <pretty-writing-plan>/scripts/validate_plan.py \
  docs/pretty/<topic>/plan.md --review-evidence /tmp/<run>/plan-review.json
```

校验器只验证可机械证明的结构、代码规则和审查证据，不代替独立语义 Reviewer。
