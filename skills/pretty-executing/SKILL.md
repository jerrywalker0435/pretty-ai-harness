---
name: pretty-executing
description: Apply an approved Java/Spring Design or explicitly run a non-authoritative Dry Run preview, with evidence-backed testing and quality gates.
---

# 执行 Design

`pretty-executing` 有两个显式模式：默认 Apply 修改真实代码并交付 `execution.md`；用户明确说 Dry Run/预演时只生成 `execution-preview.md`。Design 是唯一强制合同，Preview 是可选输入资料，不是 Apply 前置条件。

按需读取：[Apply Gate](references/quality-contract-gates.md)、[Preview 测试提案](references/test-preview.md)、[质量基线](../pretty-common/references/quality-principles.md)、[质量路由](../pretty-common/references/quality-routing.md) 和 [独立审查协议](../pretty-common/references/quality-review-protocol.md)。确定性检查使用 `scripts/validate_preview.py`、`scripts/verify_quality_contract.py`、`scripts/verify_test_execution.py`、`scripts/verify_incremental_coverage.py` 与 `scripts/validate_execution.py`。

调用本 Skill 即批准当前同目录最新 Design；不追加常规审批，不自动提交、推送、部署或发布。Design 完成后必须存在 `prd.md` 和 `design.md`，否则停止并返回 Design。

调用本 Skill 也授权同一次 Dry Run 或 Apply 创建、更新和清理必要的临时目录、执行矩阵、日志、质量/测试/覆盖率证据和构建中间产物，不逐文件请求确认。正常完成或明确停止后清理；意外中断只保留用于恢复同一次 Apply 的 `.execution-state.json`。该授权不覆盖用户既有文件，不扩大数据库执行、提交、推送、部署、外部系统写入或平台受保护路径权限。

## 模式边界

### Apply

实现 Design TASK，调用全局 `$tdd` 完成行为测试，运行真实质量门禁，写入同目录 `execution.md`。只有最终 Diff、测试实际执行、编译/回归、适用增量覆盖率和独立 Reviewer 全部通过才可使用“完成”。

### Dry Run

只读取 Design、PRD、仓库事实和有效测试，生成或更新同目录 `execution-preview.md`。Preview 可展示精确 Files/Symbols、核心实现提案和行为测试提案，但不修改生产代码、测试代码、Schema、配置或构建文件；不运行编译、测试、覆盖率、代码生成或数据库命令。只对 Preview 文档和代码块运行机械校验，不调用 `$tdd`，不启动独立 Preview Reviewer。用户自行保证 Preview 是否适用于后续 Apply；Design 和真实仓库事实优先于 Preview。

## 共同输入

1. 直接读取用户批准的同目录 `prd.md`、`design.md` 作为输入合同；不调用 Design 机械校验器，不重新检查 REQ/AC，不读取或重新生成 Design Reviewer receipt。无法读取文件或无法识别执行所需 TASK 时停止，这是输入不可消费，不是重新审批 Design。
2. 只把 Design TASK 作为结果追踪单元；内部执行步骤可拆分或合并，但不得删除 Design 结果、改变合同、公共验证入口、职责、所有权或观察面。
3. Preview 存在时可作为输入资料，不验证其新鲜度、不复用其审查证据，也不因 Preview 过期阻断 Apply。
4. 工作区洁净检查只要求会被编译、测试、运行或部署消费的路径没有未提交变化。PRD、Design、Preview、Execution、Context、Context Map、ADR 和其他说明性文件可脏；不分析改动归属。
5. Apply 新运行要求运行相关路径干净；同一次中断 Apply 仅在 `.execution-state.json` 与登记文件摘要完全匹配时恢复。状态不匹配立即停止；不 stash、reset、rebase、提交或覆盖用户文件。正常完成或明确停止后删除状态文件。

`.execution-state.json` 只服务于同一次 Apply 恢复，放在主题目录，至少记录 schema version、topic、起始 HEAD、Design SHA-256、已登记运行相关路径及其恢复摘要、执行矩阵摘要和 `in_progress` 状态。它不是 Design/Preview 合同，不授权使用其他运行留下的状态；首次编辑前创建，意外中断时保留。

## Design 偏差

语义不变的 import、构造器注入、测试 fixture、必要编译闭包、局部方法拆分或辅助文件可继续并记录。以下变化必须停止并返回 Design：

- 公共签名、外部行为、异常合同或测试观察面改变；
- 职责归属、数据所有权、依赖方向、外部边界、状态、不变量、事务、并发、幂等或一致性改变；
- 需要新增无 Design 依据的可观察结果或验证义务。

Preview 与真实代码冲突但 Design 合同不变时，以真实事实修正；Preview 不构成偏差基线。

## Apply 工作流

首次修改生产或测试代码前：

- 读取共享质量基线、质量路由、独立审查协议和相关全局 Skill；
- 从 Design TASK 生成临时执行矩阵：TASK → 生产 Files/Symbols → 测试文件 → 行为切片 → 适用 Gate → 编译/回归/覆盖率证据；纯 DDL/声明性 TASK 必须结构化声明不适用 Gate 及原因；
- 运行最小相关既有测试和确定性检查作为基线；基线失败时不修改代码；
- 做生产代码安全画像：JDK/依赖方向、入口不变量、最近邻 Adapter 规范化/默认值/异常、DTO 真实访问器、空值和宽泛异常风险；
- 首次测试编辑前扫描目标测试文件及其嵌套作用域的 `@Disabled`、JUnit 4 `@Ignore`、元注解禁用和条件禁用。

### 测试实际执行 Gate

- 禁止在类级、祖先/嵌套类级或方法级禁用范围内新增业务测试；关键行为新增测试必须位于已启用测试类或新的启用测试类。
- 不为本次变更移除历史禁用标记。只有 Design 明确包含恢复义务，且被重新启用的完整测试作用域全部实际通过，才允许移除。
- 构建参数、过滤器或测试发现配置不得跳过测试；现有 coverage Gate 的拒绝规则继续生效。
- 最终验收必须由真实测试运行报告证明新增/修改测试实际执行并通过；仅编译成功、发现测试类或生成覆盖率报告不算通过。
- 无法证明实际执行时，不能使用“完成”；`execution.md` 记录执行数量和证据来源。

### 行为实现

行为变化、Bug 修复和新增测试调用全局 `$tdd`。TDD 决定公共验证入口上的垂直切片、RED/GREEN 循环和测试放置；Execution 不复制切片顺序或重构规则。使用 Design 已批准的公共验证入口，不重复询问用户，不 mock 自有内部协作者，不以覆盖率替代业务断言。

Design 和 Preview/Apply 测试合同都必须从真实业务输入追踪到具体业务结果断言；关键 Gateway 请求用精确匹配或 captor，状态/事件分支断言角色、动作和结果，特殊守卫保留普通路径回归。

## 冻结与验证

Writer 完成所有 Design TASK、目标测试通过、完整 Diff 自审并无待做机会性重构后，先运行一次高置信机械扫描。`error` 必须为零；`review_required` 必须已分诊并附合同事实、位置和裁决条件。此时形成 Reviewer-ready 候选并冻结。

冻结后可并行运行互不写入相同构建输出的独立 Reviewer、受影响模块编译、相关回归和增量覆盖率。门禁是独立证据要求，不强制一一对应独立命令；真实构建配置允许合并时去重。Reviewer 期间 Writer 不主动修改。

修复 finding 后候选摘要改变，按证据依赖关系使受影响证据失效：重跑受影响目标测试和机械规则；生产代码变化后覆盖率必须证明修复后的完整 Diff；同一 Reviewer 复核修复增量并确认最终完整候选。公共合同、依赖方向或观察面变化时相关完整门禁失效并返回 Design。

## 最终报告

Apply 只写 `execution.md`，按 Design TASK 汇总真实 Files/Symbols、行为测试、语义不变调整、最终门禁、未验证范围和恢复点。报告状态只允许：`完成`、`停止：<原因>`、`返回 PRD：<原因>`、`返回 Design：<原因>`。删除 `返回 Plan`。

`完成` 状态绑定完整质量、编译、测试、覆盖率和候选摘要证据。`停止`、`返回 PRD`、`返回 Design` 只提交截至停止点已产生的事实、原因和恢复点；不得为了让早停报告通过而伪造尚未产生的最终证据。

Dry Run 只写 `execution-preview.md`，包含非权威声明、受影响职责链路、TASK 提案、精确 Files/Symbols、核心实现提案和测试提案；不写执行结果、覆盖率数字或审查结论。配置数据 DML 不进入 Preview；DDL 只能展示拟交付文件内容，不能展示或运行数据库执行、迁移或验证命令。

## 红线

- 不创建、读取或追认 `plan.md`，不创建新的 Plan 阶段。
- 不重新校验、审查或批准 Design；用户调用本 Skill 即表示当前 Design 已完成人工 Review。
- 不修改 PRD、Design、Context、Context Map、ADR 或项目治理文档；Design 伴随文档由其负责 Skill 维护。
- 不生成或执行配置数据 DML；事件定义、模板关系、白名单、种子/reference data、配置激活/禁用/回滚均由人工运维处理。
- 表、字段、索引等结构性 DDL 只能作为代码库文件交付，不得直接执行，也不得通过 Flyway、Liquibase、数据库客户端、应用启动、构建插件、集成测试或其他路径间接执行；报告必须写明“已交付、未执行、未进行数据库验证”。
- 不伪造测试、覆盖率、Reviewer、RED 或完成证据。
- 无全局 `$tdd` 时，行为实现停止，不内置降级版。
