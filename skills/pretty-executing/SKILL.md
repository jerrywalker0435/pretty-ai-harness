---
name: pretty-executing
description: Execute an approved Java/Spring Design in an isolated Candidate Lane with evidence-bound quality gates and a single Promotion step.
---

# 执行 Design

本 Skill 只执行已批准的 `design.md`，修改真实代码并交付 `execution.md`。Design 是唯一业务与技术合同；本 Skill 不修改 PRD、Design、Context、ADR 或治理文档，也不提交、推送、部署或发布。

按需读取：

- [执行 Gate](references/quality-contract-gates.md)：执行矩阵、Slice Fast Gate、最终 Gate 和证据字段；
- [质量基线](../pretty-common/references/quality-principles.md)：各项质量原则；
- [质量路由](../pretty-common/references/quality-routing.md)：Resolver 风险和语义 owner；
- [独立审查协议](../pretty-common/references/quality-review-protocol.md)：唯一最终 Reviewer；
- [运行授权](../pretty-common/references/runtime-authorization.md)：topic run、Candidate Lane 和清理边界；
- [Execution 模板](assets/execution.md)：最终报告结构。

## 执行协议

1. 读取当前 `prd.md`、`design.md`、目标文件、最近邻实现、真实 Java/JDK/依赖和构建配置。检查运行相关路径干净；说明性文档可以保持脏状态。
2. 创建或恢复同一 topic run 的 `execution-matrix.json`、`execution-state.json` 和 detached Candidate Lane。首次编辑前完成合同可执行性预检、共享规则包摘要和 Quality Resolver；预检失败立即返回 Design。
3. 以 Design TASK 的最小垂直行为切片推进。每个切片先在批准的公共入口建立 `$tdd` RED，再做最小 GREEN；Writer 和所有验证命令只能写 Candidate Lane。
4. 每个切片运行 Slice Fast Gate：共享机械扫描、目标测试实际执行以及测试命令未覆盖时才补充的必要局部编译。不可豁免 `error`、越界写集、缺失观察面或禁用测试会阻断下一切片；新文件、Symbol、依赖或边界在批准合同内时用 `apply_run.py rebind`，改变公共合同时返回 Design。
5. 每个切片首次 GREEN 后记录不可覆盖的 `first_attempt` 指标；修复必须创建新候选摘要，不能伪造或复用旧证据。
6. 所有切片通过后停止 Writer，完整 Diff 由 `start_head` 推导并排除 topic run。冻结候选，执行一次最终机械 Gate、必要编译、目标测试/相关回归、正式增量覆盖率和 `clean-code-guard`。证据必须绑定同一候选、Design、矩阵、共享规则包和起始 HEAD。
7. 客观 Gate 全部通过后启动一名独立 Reviewer。Reviewer 不能批量豁免机械错误；receipt 必须绑定当前冻结候选和 objective Gate。失败修复只能经 `apply_run.py reopen --reason ...`，所有受影响证据重新生成。
8. 仅由 `apply_run.py promote` 将冻结 patch 应用到目标工作区。Promotion 前后校验目标 HEAD、运行路径摘要、patch 和候选摘要；完成后用 `apply_run.py cleanup` 清理登记的 Lane 和证据。

运行恢复只使用同一编排器的 `register`、`resume`、`checkpoint`、`rebind`、`reopen`、`promote` 和 `cleanup` 命令；不创建第二套状态或证据协议。

## 硬停止

- 无法让 Writer 的可写根只指向 Candidate Lane；
- Design TASK、模块边界、失败语义、验证观察面或交付归属无法从真实代码落实；
- Quality Resolver 风险缺失、owner 不匹配或出现未登记文件/Symbol/依赖/边界；
- 机械 `error`、编译、测试、覆盖率、`clean-code-guard` 或独立 Reviewer 未通过；
- 候选、规则包、Design、矩阵、起始 HEAD、目标 HEAD 或任一证据摘要过期；
- 需要改变公共签名、外部行为、职责/所有权/依赖方向、状态/事务/并发/幂等或公共观察面；
- 需要执行 DDL、配置数据 DML、数据库客户端、迁移、部署或发布。

失败只在 `execution.md` 记录已执行事实、原因和恢复点，状态使用 `完成`、`停止：<原因>`、`返回 PRD：<原因>` 或 `返回 Design：<原因>`。
