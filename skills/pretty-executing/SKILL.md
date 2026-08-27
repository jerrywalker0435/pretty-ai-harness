---
name: pretty-executing
description: Apply an approved Java/Spring Design or explicitly create a non-authoritative Dry Run preview with evidence-backed quality gates.
---

# 执行 Design

默认模式是 Apply：修改真实代码并交付 `execution.md`。用户明确说 Dry Run/预演时只生成 `execution-preview.md`。Design 是唯一业务与技术合同，Preview 是可选资料，不是 Apply 前置条件；本 Skill 不自动提交、推送、部署或发布。

按需读取：[Apply Gate](references/quality-contract-gates.md)、[Preview 测试提案](references/test-preview.md)、[质量基线](../pretty-common/references/quality-principles.md)、[质量路由](../pretty-common/references/quality-routing.md)、[独立审查协议](../pretty-common/references/quality-review-protocol.md) 和 [运行授权](../pretty-common/references/runtime-authorization.md)。具体字段、哈希、命令和阈值以 reference 与脚本为准。所有 Pretty 运行证据必须位于 `docs/pretty/<topic>/tmp/<run-id>/`，不得使用 `/private/tmp` 或其他外部临时路径。

## 模式边界

### Apply

读取同目录 `prd.md`、`design.md`，实现全部 Design TASK，使用全局 `$tdd`，完成真实质量 Gate、最终独立 Reviewer 和 `execution.md`。只有完整候选的机械扫描、编译、实际测试、相关回归、适用增量覆盖率和最终 Reviewer 全部通过，才可报告“完成”。

### Dry Run

只读 PRD、Design、仓库事实和有效测试，生成非权威 `execution-preview.md`。可展示精确 Files/Symbols、实现提案和测试提案，但不修改生产代码、测试、Schema、配置或构建文件，不运行编译、测试、覆盖率、代码生成或数据库命令，不调用 `$tdd`，不启动 Reviewer。Design 和真实仓库事实优先于 Preview。

## Apply 开始前：合同可执行性预检

首次编辑任何生产或测试代码前，Writer 必须完成轻量预检并记录在执行矩阵/临时证据中：

- 模块职责、数据所有权、依赖方向和规则唯一归属足够明确；
- 失败语义、状态、不变量、事务、并发、幂等、一致性和不可逆副作用可以落实，明确“不适用”也要有依据；
- 公共验证入口、业务结果断言、完整边界请求/状态/异常观察面真实可用；
- Java、测试、结构性 DDL、配置数据 DML、发布和人工运维的交付归属明确。

预检不是独立 Reviewer，不得补写或改变 Design 合同。发现缺失、冲突或无法从真实代码落实时，立即返回 Design；不得先写代码再补合同。`apply_run.py`、Apply Gate 和 Resolver 负责可机械证明的部分，Writer 只补充事实证据。

## 最短 Apply 工作流

1. 确认当前 Design 可读、TASK 可消费；Preview 可选且不作为批准或新鲜度依据。
2. 检查运行相关路径干净，在同一 topic tmp run 目录创建或恢复 `execution-state.json`；状态摘要不匹配时停止，不 stash、reset、rebase 或覆盖用户文件。
3. 按 [Apply Gate](references/quality-contract-gates.md) 建立执行矩阵、行为切片、覆盖归属和 Quality Resolver 路由；先运行最小相关基线并记录基线结果。基线只用于区分历史失败，不把历史覆盖率债务归因给本次任务，也不作为放行条件。
4. 行为变化调用 `$tdd`：先在批准公共入口建立可观察 RED，再做最小 GREEN；只替换数据库、网络、时间、随机等系统边界，不 mock 自有内部协作者，不测试 private 方法，不以覆盖率代替业务断言。
5. 严格按行为切片串行推进：当前切片先完成行为测试，再运行机械扫描、目标测试和新鲜增量 JaCoCo（最低行 90%、分支 80%），先用 `apply_run.py checkpoint` 固定范围，再用 `apply_run.py slice-coverage` 关闭切片；`checkpoint` 只接受当前切片声明范围内的运行路径变化，全部切片关闭后运行路径冻结。未达到门槛或没有证据时，禁止进入下一个切片、并行扩展其他生产层或冻结候选。可以并行运行互不修改工作区的验证命令，但不能并行实现多个未闭环切片。禁止在禁用测试作用域新增业务测试，不得通过过滤器或构建参数跳过测试。最终必须有新鲜报告证明新增/修改测试实际执行。
6. 所有 TASK 集成后，对从起始 HEAD 推导的完整真实 Diff 运行最终机械 Gate、编译、目标测试、相关回归和正式增量覆盖率；每个 JSON/日志输出先用 `apply_run.py register --state ... --artifact ...` 登记，`error` 为零，`review_required` 已处理，阈值或“不适用”理由满足 Apply Gate。
7. 客观证据绑定同一冻结候选后，启动唯一最终独立 Reviewer。Reviewer 同时检查 Design 与实现的一致性、职责/依赖、失败语义、状态/事务/并发/幂等/副作用、完整观察面和证据；Reviewer 期间 Writer 不主动修改。候选或 Gate 摘要变化即使旧证据失效并重新验证。
8. 按 [Execution 模板](assets/execution.md) 写入真实 Files/Symbols、测试执行、覆盖闭环、DDL 状态、路由、未验证范围、最终证据和恢复点；正常完成后只用 `apply_run.py cleanup` 清理 manifest 已登记的 tmp 文件，禁止手写 `rm -rf`。

## 设计偏差与交付边界

语义不变的 import、构造器注入、测试 fixture、必要编译闭包、局部方法拆分或辅助文件可继续并记录。公共签名、外部行为、异常合同、职责/所有权/依赖方向、状态/不变量/事务/并发/幂等/一致性、公共观察面或新增可观察结果改变时，停止并返回 Design。真实代码与 Preview 冲突但合同不变时，以真实事实修正。

结构性 DDL 只能作为代码库文件交付，报告写明“已交付、未执行、未进行数据库验证”；配置数据 DML、事件定义、模板关系、白名单、种子/reference data、激活/禁用/回滚始终由人工运维处理，Apply 和 Dry Run 都不生成或执行。

## 最终状态与红线

`execution.md` 的状态只能是：`完成`、`停止：<原因>`、`返回 PRD：<原因>`、`返回 Design：<原因>`。停止或返回时只写已产生的事实、原因和恢复点，不伪造成功证据。

- 不创建、读取或追认 `plan.md`，不重新审批 Design，不修改 PRD、Design、Context、Context Map、ADR 或治理文档。
- 不降低共享规则，不伪造 RED、测试、覆盖率、Reviewer、候选摘要或完成结论；没有全局 `$tdd` 时行为实现停止。
- 不执行 DDL/DML、数据库客户端、迁移、部署或发布；不覆盖非本次运行创建的用户文件。
