---
name: pretty-executing-plan
description: Implement or resume an approved Java/Spring Plan, independently review the real diff, and verify affected behavior, quality, and incremental coverage.
---

# 执行 Plan

把当前工作区唯一有效的 `plan.md` 转成真实代码、测试和简要证据。调用本 Skill 即批准执行当前主题；不追加常规审批，也不自动提交、推送、部署或发布。

先读取 [报告模板](assets/execution.md)、[Execution Gates](references/quality-contract-gates.md) 以及共享的[质量基线](../pretty-common/references/quality-principles.md)、[质量路由](../pretty-common/references/quality-routing.md)和[独立审查协议](../pretty-common/references/quality-review-protocol.md)。

## 优先级与范围

依次遵守：用户当前明确要求、当前已批准 Plan、Pretty 共享质量规则、真实仓库既有惯例、`AGENTS.md`、Trellis 质量规范。真实 API、Schema、依赖版本和构建结果是不可伪造的事实；事实使 Plan 无法实现时返回 Plan。Reviewer 不得用 AGENTS/Trellis 的偏好推翻 Plan、阻断已批准实现或扩大范围。

只实现 Plan 明确 Files 和必要编译闭包。不得自行修改 `.trellis`、ADR、`business-map`、规范索引或其他项目治理文档。配置数据由人工处理；不创建或执行种子数据、白名单、事件定义等配置 DML。表、字段和索引 DDL 按 Plan 实现，但不生成或执行测试、数据库验证和验证命令，最终报告将其列入未验证范围且不阻止完成。

## 执行起点

确认当前主题唯一 `plan.md`，以 `validate_plan.py --scan-only` 复验结构与核心代码；零 finding 直接进入执行，存在 `review_required` 时复用与当前 Plan 摘要匹配的审查证据或只做一次聚焦复核，不重新进行完整 Plan 流程。把同目录 `execution.md` 作为结果账本。Plan 是规范实现基线；PRD、Design 只在 Plan 不足或冲突时按需读取，Execution 不修改上游文档。

在仓库外临时目录记录起始 HEAD、用户已有改动、本次 changed-line manifest、命令日志和审查证据。不得 stash、reset、rebase、覆盖或归入用户已有改动；目标写集无法安全归因时停止。

首次修改生产代码前完成输入、范围、工作区归因和质量路由 Gate。基线只运行能够区分历史失败的最小相关既有测试和必要确定性检查，不预先执行完整模块编译；能安全并行的只读检查批量执行，路径、依赖和构建事实只盘点一次并复用。基线失败时不修改生产代码。

## TASK 执行

按 Plan TASK 和文件/symbol 依赖串行集成。并行只允许在隔离 worktree 中处理文件、symbol、接口、测试资源和构建输出均不重叠的 TASK；主 Agent 负责最终集成和验证。

行为变化、Bug 修复和新增测试使用 `tdd`，按一个行为一轮推进：

```text
正确 RED → 最小 GREEN → 必要重构 → 复验
```

使用 Plan 已批准的公共 Seam，不重复询问。RED 不能来自语法、依赖或环境错误；不 mock 自有内部协作者，不批量先写生产代码，不以覆盖率替代行为断言。

## Writer 与独立 Reviewer

Writer 按 TASK 实现并只运行该行为的目标测试；低风险 TASK 不逐个启动机械扫描或独立审查。全部 TASK 集成并稳定后，共享机械扫描和独立 Reviewer 各运行一次；Reviewer 对当前完整 Diff 和调用链完成质量审查、风险路由和 `clean-code-guard`。只有公共合同、并发、数据迁移或不可逆副作用等高风险变更才在集成前增加一次聚焦审查。

Reviewer 输出可追踪 finding 和机械 finding 裁决，不得改变上游合同。Writer 修复后只运行受影响扫描与目标测试，由同一 Reviewer 只复核修复增量；只有修复改变完整候选结论时才重跑对应重门禁。最终证据绑定完整候选摘要。不得因等待超时创建重复 Reviewer、重复全仓盘点或无新候选地再次审查。无法获得独立 Reviewer 时不能完成生产 Java Diff。

## Plan 偏差

允许为编译和集成做不改变语义的局部调整，并在报告中记录。若真实实现需要改变职责归属、公共签名、异常合同、数据所有权、测试边界或外部行为，立即返回 Plan；Execution 不自行重设计。

## 验证与证据

只验证本次可归因增量和受影响范围。存在生产 Java 增量时，最终必须具有：

- Plan 与实际 Diff 范围核对；
- 共享机械 Gate 与独立质量审查；
- 受影响模块按真实 Java 配置编译；
- 本次新增或修改测试和直接相关回归测试；
- 增量行覆盖率 `90%`、分支覆盖率 `80%`，或用户明确指定的阈值。

覆盖率使用 `scripts/verify_incremental_coverage.py` 生成 JSON。`未达标`或`无法验证`不能完成；没有可执行生产增量时为`不适用`。不得降低阈值、扩大排除、复用陈旧报告或跳过测试。TASK 期间只运行目标测试；受影响模块编译、合并后的相关回归、机械 Gate、独立审查和覆盖率在集成候选稳定后各执行一次，除非后续代码改变对应结论。互不干扰的只读检查和测试可安全并行，不运行无因果关系的全仓构建或全量测试。

使用 `scripts/verify_quality_contract.py` 生成质量证据，再由 `scripts/validate_execution.py` 将 Plan、临时证据和最终报告交叉校验。报告中的覆盖率数值必须来自覆盖率 JSON。

## 报告与状态

`execution.md` 只记录执行起点、基线、TASK 结果、最终门禁、未验证范围和结论。详细日志与 findings 留在临时目录。结论必须明确写出：

```text
测试覆盖率：增量行覆盖率 100.00%，分支覆盖率 98.91%
```

没有可执行生产增量时写“不适用”；无法测量时不得使用完成状态。

最终状态只允许 `完成`、`停止：<原因>`、`返回 PRD：<原因>`、`返回 Design：<原因>` 或 `返回 Plan：<原因>`。完成后交付真实 Diff、报告路径、验证结果、覆盖率和未验证范围。

## 红线

- 不修改或追认 PRD、Design、Plan 或 ADR；
- 不生成配置数据 DML、项目治理文档同步或手工耗时日志；
- 不在基线失败后修改生产代码；
- 不伪造 RED、测试、覆盖率、审查或完成证据；
- 不把 UT 描述成数据库、远端服务、部署或人工联调；
- 不集成未通过独立审查和共享机械 Gate 的生产 Diff；
- 不自动执行 Git 提交、远端或发布动作。
