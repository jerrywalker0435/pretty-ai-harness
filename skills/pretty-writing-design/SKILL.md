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
- 依赖：（按需）
```

规则：

- TASK 是稳定的结果与追溯单元，不是冻结的最终文件集合或实现顺序。
- `REQ-*` / `AC-*` 必须来自同目录 PRD；每个需求和验收标准必须有 TASK 映射，明确非实施项除外并说明原因。
- 公共验证入口是用户批准的测试可观察边界，不是私有方法，也不是为了覆盖率临时暴露的方法。
- 可以记录真实已存在的关键 Symbol 作为影响锚点；不预测私有辅助方法、fixture 或完整编译闭包。
- 按可观察结果垂直拆分，不按 Controller/Service/Repository 横向拆分。
- 纯 DDL 或声明性 TASK 可将不适用字段写明原因；没有可执行结果的 Design 不调用 `$pretty-executing`。
- 不写完整 Java 生产代码、完整测试代码、执行命令、执行结果、覆盖率数字或质量自评。

## 成稿前质量预检

在机械校验前，Writer 内部确认：

- 外部 API、配置默认值、Schema、异常和最近邻实现事实均已核实；
- 必填/可选输入、fail-fast、规范化首个信任边界、状态/幂等/并发/一致性语义已明确；
- 每个 TASK 有 REQ/AC、公共验证入口、影响锚点、业务结果和观察面；
- 多枚举、多状态和首次/重复/失败组合覆盖行为交互相关子空间，未覆盖组合有等价或不可达依据；
- 方法长度、参数数量、注释、空值和测试禁用等代码级规则留给 Preview/Apply 机械 Gate，不伪装成已验证。

## 高风险 Design Reviewer

`验证与风险` 必须结构化声明 `Design 风险级别：低|高`、`Design 风险类型：无|<具体类型>` 和 `合同来源：无|<仓库相对路径列表>`。低风险的类型必须为“无”；高风险必须列出具体类型。合同来源参与 Design Reviewer 候选摘要，Apply 重新校验时从该字段加载同一批路径。公共 API/RPC/MQ/调度合同、DDL/迁移/历史兼容、职责/所有权/依赖方向、事务/并发/幂等/一致性、状态机、不可逆副作用、安全、跨模块公共行为或部署协作必须声明为高风险；否定性文字和单个关键词不直接决定风险级别。

机械校验通过后，高风险 Design 先启动独立 Design Reviewer，再请求用户 Review。

Reviewer 只审 Design 合同、链路完整性、事实证据、任务覆盖和验证闭合；不审最终 Java 代码质量。候选内容变化后旧证据失效。详细 JSON 证据留在临时目录，不写入 Design。低风险 Design 只运行机械校验并请求用户 Review。由于临时证据不跨运行持久化，后续 Apply 对高风险 Design 重新取得 Design Reviewer 证据；这不是要求用户先执行 Preview。

## 质量路由与依赖

只加载真实相关的最小专项 Skill。行为测试使用用户全局 `$tdd`，Design 不执行 TDD；领域信号使用全局 `$domain-modeling`。不把这些 Skill 复制进项目或 Pretty Skill 目录。

需要质量基线、风险路由或独立审查字段时，读取共享资源：

- [质量基线](../pretty-common/references/quality-principles.md)
- [风险路由](../pretty-common/references/quality-routing.md)
- [独立审查协议](../pretty-common/references/quality-review-protocol.md)

## 校验与交付

运行 `scripts/validate_design.py docs/pretty/<topic>/design.md`。交付 Design 路径、主要结论、领域文档变更、校验/风险审查结果，并请求用户 Review。用户调用 `$pretty-executing` 即批准当前最新 Design。

## 红线

- 不创建 Plan、`plan.md` 或任何新的规范阶段。
- 不修改 PRD、生产代码、测试代码或配置数据；Context/ADR 仅由 `domain-modeling` 按其职责维护。
- 不写逐文件实施计划冒充外部设计边界，不猜测 API、Schema 或依赖。
- 不保留待定技术选择、占位内容或未经证据支持的兼容承诺。
