---
name: pretty-writing-design
description: Create or revise an approved Java/Spring Design and its implementation impact contract from a PRD and real repository evidence.
---

# 编写 Design

把 PRD 和真实仓库事实转化为可由技术团队评审、可直接进入 Execution 的技术合同。Design 决定外部边界、职责、契约、运行时语义、模型、风险和行为级实施影响；不选择业务结果，也不复制完整源码。

## 输入与输出

- 主输入是同目录 `prd.md`，用户调用本 Skill 即表示 PRD 可进入 Design。
- 默认写入 `docs/pretty/<topic>/design.md`，topic 使用小写 kebab-case。
- 必须完整读取 PRD、适用 Context/Context Map/ADR、构建配置和受影响真实代码。
- Design 完成后停止并请求用户 Review，不自动进入 Execution。
- 交付时明确提示两种后续用法：Apply 使用 `$pretty-executing`；Dry Run 使用 `$pretty-executing Dry Run`，只生成 `execution-preview.md`。
- 调用本 Skill 即授权本次运行创建、更新和清理必要的候选摘要、Reviewer receipt、校验日志及其他临时证据，不逐文件请求确认；正常完成后清理，且不得借此覆盖用户既有文件或扩大外部写入权限。

## 领域与合同门禁

`domain-modeling` 是领域信号命中时的强制全局 Skill；由它读取和维护 Context、Context Map 与 ADR。Design 不自行修改这些文件。

Design 必须关闭会改变业务结果、外部合同、职责归属、数据所有权、依赖方向、一致性或长期扩展点的未知项。业务语义不明返回 PRD，技术合同不明停止并请求澄清；不把未知项推给 Execution。

## 一次仓库调查

先广度扫描公开入口：HTTP/RPC、MQ、CLI、调度、公开接口、注册点、Schema/迁移和测试入口；再沿受影响链路深读到持久化、外部调用和消费者。仓库事实是证据，不自动成为设计约束。

“设计边界”只描述系统与外部参与者、服务、消息基础设施和调度器之间的合同。“实施影响”可用有限职责链路表达内部承接，但不把内部 Maven module 或技术分层提升为外部边界，不展开逐方法调用树、DTO/VO 转换或胶水代码。

## 固定文档结构

最终文档严格使用以下六个二级章节：

1. `设计结论`
2. `方案全景`
3. `关键设计与权衡`
4. `设计边界`
5. `实施影响`
6. `验证与风险`

`实施影响` 是可执行 Design 的结构化硬门禁，必须包含变更职责链路和至少一个结果 TASK。每个行为 TASK 必须包含：

```markdown
### TASK-001：<可观察结果>

- 覆盖需求：REQ-001、AC-001
- 结果：<用户或外部系统可观察的结果>
- 公共验证入口：<稳定的公开行为入口>
- 影响锚点：<真实入口、规则所有者、持久化点或外部边界>
- 验证观察面：<结果、状态、异常、消息或完整边界请求>
- Execution 交付：<Java、测试、表/字段/索引 DDL，或无>
- 人工运维产物：<配置数据 DML，或无>
- 依赖：（按需）
```

规则：

- TASK 是稳定的结果与追溯单元，不是冻结的最终文件集合或实现顺序。
- `REQ-*` / `AC-*` 必须来自同目录 PRD；每个需求和验收标准必须有 TASK 映射，明确非实施项除外并说明原因。
- 公共验证入口是用户批准的测试可观察边界，不是私有方法，也不是为了覆盖率临时暴露的方法。
- 可以记录真实已存在的关键 Symbol 作为影响锚点；不预测私有辅助方法、fixture 或完整编译闭包。
- 按可观察结果垂直拆分，不按 Controller/Service/Repository 横向拆分。
- 纯 DDL 或声明性 TASK 可将不适用字段写明原因；没有可执行结果的 Design 不调用 `$pretty-executing`。
- 事件定义、模板关系、白名单、种子/reference data、配置激活/禁用/回滚及其他配置数据 DML 都是人工运维产物。Design 可以定义其语义、顺序、前置条件和人工验收，但不得要求 Execution 生成或执行。
- Execution 只能把 Java、测试及表、字段、索引等结构性 DDL 作为交付物。DDL 仅写入代码库，不得由 Execution 直接或通过迁移工具、应用启动、构建插件、测试间接执行，也不得声明数据库验证成功。
- 不写完整 Java 生产代码、完整测试代码、执行命令、执行结果、覆盖率数字或质量自评。

## 成稿前质量预检

在机械校验前，Writer 内部确认：

- 外部 API、配置默认值、Schema、异常和最近邻实现事实均已核实；
- 必填/可选输入、fail-fast、规范化首个信任边界、状态/幂等/并发/一致性语义已明确；
- 每个 TASK 有 REQ/AC、公共验证入口、影响锚点、业务结果和观察面；
- 多枚举、多状态和首次/重复/失败组合覆盖行为交互相关子空间，未覆盖组合有等价或不可达依据；
- 方法长度、参数数量、注释、空值和测试禁用等代码级规则留给 Preview/Apply 机械 Gate，不伪装成已验证。

## Design Reviewer

所有 Design 在机械校验通过后、请求用户 Review 前，必须由一名独立 Reviewer 审查；不按高低风险分流，不由 Design 自我声明审查强度，也不启动第二名 Reviewer 或专项 Reviewer。

机械校验只负责固定结构、TASK 字段和 REQ/AC 覆盖。Reviewer 信任这些机械结果，不重复检查，只固定审查三个语义风险面：

- 模块边界：职责与数据所有权、依赖方向、公共入口、外部合同泄漏，以及 Execution 与人工运维的交付归属；必须阻断把配置 DML、数据库执行、发布、激活或回滚错误分配给 Execution，以及交付归属与 TASK 锚点、依赖、观察面不一致；
- 运行时风险：失败语义、事务、并发、幂等、一致性、状态恢复和不可逆副作用；
- 行为验证：公共验证入口是否真实可用，观察面能否区分正确、失败和回归行为。

Reviewer 只输出阻断 finding，不输出代码风格、命名偏好、泛化建议或非阻断优化。每个阻断 finding 必须包含位置、风险面、违反的批准合同或事实约束、可观察后果、必须修正的内容和修正后的验证方式。无阻断问题时只确认三个风险面均已检查且 `blocking_findings` 为空。

Writer 根据 finding 修订后，由同一 Reviewer 只复核原阻断项及修订直接引入的问题，不重扫未改动 Design。原 Reviewer 不可用时，新 Reviewer 必须对当前完整候选重新检查三个风险面。临时 receipt 只服务于本次 Design Gate，候选摘要仅绑定 `prd.md + design.md`；receipt 不写入 Design，也不供 Execution 使用。

## 质量路由与依赖

Writer 成稿前只加载真实相关的最小专项 Skill。冻结后的正式 Design Review 不启动 `codebase-design`、`java-code-review`、`tdd` 或其他专项 Reviewer；三个固定风险面由同一名独立 Reviewer 完成。行为测试使用用户全局 `$tdd`，Design 不执行 TDD；领域信号使用全局 `$domain-modeling`。不把这些 Skill 复制进项目或 Pretty Skill 目录。

需要质量基线、风险路由或独立审查字段时，读取共享资源：

- [质量基线](../pretty-common/references/quality-principles.md)
- [风险路由](../pretty-common/references/quality-routing.md)
- [独立审查协议](../pretty-common/references/quality-review-protocol.md)

## 校验与交付

先运行 `scripts/validate_design.py docs/pretty/<topic>/design.md`，机械 Gate 通过后启动一名独立 Reviewer，并用 `scripts/validate_design_review.py docs/pretty/<topic>/design.md --review-evidence <temporary-receipt>` 验证冻结候选。交付 Design 路径、主要结论、领域文档变更和未关闭阻断项，并请求用户 Review；不把 Reviewer 过程或结论写入 Design。用户调用 `$pretty-executing` 即批准当前最新 Design。

## 红线

- 不创建 Plan、`plan.md` 或任何新的规范阶段。
- 不修改 PRD、生产代码、测试代码或配置数据；Context/ADR 仅由 `domain-modeling` 按其职责维护。
- 不写逐文件实施计划冒充外部设计边界，不猜测 API、Schema 或依赖。
- 不保留待定技术选择、占位内容或未经证据支持的兼容承诺。
