---
name: pretty-executing-plan
description: Use when the user invokes Pretty Execution to implement or resume a Java/Spring change from the current workspace Plan, including behavior changes, bug fixes, and behavior-preserving refactors.
---

# 执行 Plan

Execution 将当前工作区最新的 Plan 转成代码、测试和可追溯证据。用户使用本 Skill 即视为批准执行该主题，不追加审批轮次。Execution 不负责重新定义需求、设计或 Plan，也不自动执行提交、推送、合并、部署或发布。

先加载同目录的 [assets/execution.md](assets/execution.md) 作为报告模板。首次修改生产代码前加载 [references/quality-contract-gates.md](references/quality-contract-gates.md) 和 [../pretty-common/references/quality-principles.md](../pretty-common/references/quality-principles.md)，然后使用本 Skill 提供的脚本：

- [scripts/validate_execution.py](scripts/validate_execution.py)：校验报告结构和完成证据；
- [scripts/verify_quality_contract.py](scripts/verify_quality_contract.py)：先校验当前 Plan 代码提案，再对本次真实 Java 增量运行共享 Java 代码质量 Gate；
- [scripts/verify_incremental_coverage.py](scripts/verify_incremental_coverage.py)：独立计算增量覆盖率。

## 1. 输入与范围 Gate

在当前主题目录确认唯一有效的 Plan，并将同目录的 `execution.md` 作为结果账本。Plan 是 Execution 的唯一必需输入；报告只写 `执行依据：Plan`，不记录 PRD、Design 或 Plan 路径。PRD、Design 不是例行执行输入，只有发现 Plan 信息不足或契约冲突时才按需查阅。

Plan 缺失、重复或无法确认有效版本时停止。用户负责执行期间的文档稳定性；不做文档版本指纹或变更检测，读取到的始终是当前工作区最新内容。Execution 不修改 PRD、Design、Plan 或 ADR。

首次生产代码编辑前按 `references/quality-contract-gates.md` 完成输入/范围 Gate 和质量路由 Gate。发现需求、设计或 Plan 的冲突/歧义时，立即返回对应阶段，不自行猜测。

## 2. 增量范围和基线

执行前在仓库外临时目录记录起始 `HEAD`、staged/unstaged/untracked 归因和必要的 changed-line manifest。不得 stash、reset、rebase、覆盖或把用户已有改动归入本次成果。目标文件已有重叠改动且无法安全区分时停止；无重叠时可在非洁净工作区继续。

只把本次增量代码纳入质量和覆盖率门禁。未修改的存量问题默认忽略；修改存量文件时，只检查本次改动及必要上下文。

输入与范围 Gate 通过后，首次修改生产代码前运行最小可控基线：受影响模块编译、相关既有 UT、拟修改测试入口和必要的确定性检查。受影响模块编译必须使用仓库实际的 Java 兼容性配置验证 JDK 8 目标；不要用正则扫描源码替代编译验证。不要默认运行全仓测试、真实数据库、远端服务、部署或人工联调。

基线失败时不修改生产代码，不把历史失败归入本次成果；记录命令、退出码、摘要和恢复条件。纯文档、配置、SQL、资源或确定性改名任务使用相应机械检查，不伪造 Java 基线或 RED/GREEN。

## 3. 执行引擎和并行策略

主 agent 是唯一的契约裁决者、集成者和最终验证者。先按 TASK 及文件/symbol 依赖建立执行图，再决定并行：

- 追溯、调用链扫描、风险和质量审查等只读工作可并行，通常使用 2–3 个子 agent；
- Writer 与 Reviewer/Repair 只能在候选快照或隔离 worktree 中协作，不能同时写同一工作区；
- 同一 TASK、共享接口/类/DTO/Mapper、迁移、fixture 或重叠写集必须串行；
- 文件、symbol、接口和测试资源完全不重叠的 TASK 可在隔离 worktree 中并行；
- 冲突合并、TASK 集成、最终编译、覆盖率和最终审计由主 agent 串行完成。

并行实现必须使用隔离 worktree，不能共享构建输出、端口、数据库 schema、临时目录，worker 不写主工作区的 `execution.md`。没有隔离环境时退回串行。子 agent 的完成消息不是最终证据；主 agent 必须检查真实 diff 并重新验证。

### Writer–Reviewer/Repair 闭环

有生产代码增量的 TASK 按以下闭环推进；纯文档、配置、SQL、资源或确定性改名任务不启动代码 Writer，只执行适用的机械检查：

1. Writer 在隔离 worktree 或候选快照中实现当前 TASK，不直接写主工作区的 `execution.md`。
2. 候选 Diff 生成后先运行共享 Java 代码质量 Gate；确定性违规必须先修复，不能交给报告或最终审计掩盖。
3. 按真实风险把候选 Diff 和已命中的质量路由交给 Reviewer/Repair。Reviewer 先复核共享基线、Plan 代码提案与约束、调用链和实际 Diff；发现局部质量违规时可直接在该隔离候选中修复。
4. Reviewer/Repair 不得改变 PRD、Design、Plan、外部结果、架构边界、测试边界或任务范围；发现这类问题必须返回对应阶段。
5. Reviewer 的每次修改都必须重新运行共享 Java 代码质量 Gate、受影响编译和相关测试；修复前的证据不能沿用。
6. 只有候选 Diff 通过适用审查和验证后，主 agent 才能集成；集成后仍需检查真实 Diff，并串行完成跨 TASK 组合检查和最终验证。

独立 TASK 可以流水线并行：一个 TASK 进入 Reviewer/Repair 时，另一个无重叠 TASK 可以由 Writer 实现；共享文件、公共 symbol 或无法隔离构建环境时退回串行。低风险 TASK 可由主 agent 完成同等审查，不为形式额外启动 Reviewer。

Superpowers 仅是可选调度引擎，不是硬依赖，也不能带入自动 Git、MR、部署或发布动作。Superpowers 或子 agent 不可用时，主 agent 仍按本 Skill 完成执行。

## 4. TDD 和测试边界

行为变化、Bug 修复和新增测试先检查外部 `tdd` Skill：可用时优先加载一次，并贯穿本次 Execution；不可用时使用本 Skill 的内置 TDD。已批准 Plan 中明确的公共 Seam 视为已确认，不重复询问用户。

逐行为执行：

```text
写一个行为测试 → 因目标行为缺失而正确 RED → 最小 GREEN → 必要时小步重构 → 复验
```

- 一次只推进一个行为，不批量先写生产代码；
- RED 不能来自语法、依赖、环境或测试基础设施错误；
- 首次通过时检查行为是否原本已存在、断言是否无效或是否只部分满足；
- 行为保持型重构先通过基线，再用小步重构验证，不制造 RED；
- 只在已批准 Seam 上测试公共行为，避免绑定私有实现；mock 只用于系统边界，不 mock 自有内部协作者；
- UT 是默认边界；只有 Plan 明确要求时才增加集成、契约、端到端或 Spring slice 测试；
- 覆盖率不能替代业务结果、状态、异常、幂等、并发和边界请求断言。

## 5. 质量路由和 Quality Gate

首次生产代码编辑前完整读取共享质量基线，并根据真实增量风险完成精确质量路由；在读取和路由完成前不得生成或修改生产代码。只选择最小、不重叠且实际适用的 Skill 集合，不批量加载所有质量 Skill。命中的原则必须转成真实实现中的职责、签名、异常语义、类型、测试行为、配置/Schema 或任务切分，不能只写在报告里。质量路由、输入/范围 Gate、降级和返回条件以 `references/quality-contract-gates.md` 为准。

共享 Java 代码质量 Gate 是所有包含 Java 增量的 TASK 的快速阻断层，必须在 Writer 或 Reviewer/Repair 每次修改后运行；它复用 `pretty-common/scripts/quality_contract_gate.py`，阻断 `continue`、通配符 import、生产字段注入、空 `catch`、未声明可空返回、空值传播三元、宽泛 fallback、通用结果码形状、单方法超过两个常规 logger 调用、显式分支重复日志和单方法超过一个连续注释块，并对长方法、参数过多及嵌套/多个三元输出 warning。简单三元表达式允许。命令/查询方法只有在 Execution 根据真实调用链生成临时方法清单时才附加机械检查，不从 Plan 的重复字段推导。warning 不改变退出码；error 退出码非 `0` 时先修复，不得进入“完成”。命令示例：

```bash
python3 <pretty-executing-plan>/scripts/verify_quality_contract.py \
  --repo . --base <execution-start-head> --plan docs/pretty/<topic>/plan.md \
  [--method-manifest /tmp/<run>/java-methods.json]
```

若使用工作区归因的 changed-line manifest，将 `--base` 替换为 `--changed-manifest /tmp/<run>/changed-lines.json`。`--method-manifest` 只存放 Execution 临时确认的命令/查询方法分类，不写入 Plan；格式为 `{"commands":{"publish":false},"queries":["find"]}`。该扫描器只负责高确定性规则；职责、边界、重复、依赖方向等语义问题仍由命中的 Reviewer/Repair 路由审查。

每个 TASK 完成时按 `references/quality-contract-gates.md` 复核共享质量基线、Plan 代码提案与约束、命中路由和实际 diff；实现或复核中发现新风险时增量路由，阻断项必须修复并重跑受影响验证。全部 TASK 完成后做一次跨 TASK 组合检查；任何未修复的共享基线、Plan 范围偏差或命中路由阻断项都不能进入“完成”。质量原则检查对象是真实生产代码和测试，不是质量自评。

## 6. 增量覆盖率和独立验证

覆盖率验证必须使用本 Skill 自带脚本，不调用仓库私有脚本、个人绝对路径或历史工具。脚本支持 Maven、Gradle 和 JaCoCo XML；仓库可以增加最小测试依赖或 test-scope 配置，但不得增加生产运行时依赖或无价值测试。

默认阈值为增量行覆盖率 `90%`、分支覆盖率 `80%`。Execution 开始时提示实际阈值但不等待确认；用户未指定时直接使用默认值，用户可通过执行配置或命令参数覆盖。只统计本次新增或修改的生产可执行代码，存量代码不进入门禁。

用户可见状态使用中文：

- `通过`：达到阈值；
- `未达标`：有可测量增量但未达到阈值；
- `无法验证`：有生产增量但缺少可靠覆盖率报告或无法映射；
- `不适用`：没有可执行生产增量。

`不适用`不阻塞；`未达标`或`无法验证`不能使最终报告成为“完成”，除非有仓库政策、Plan 或用户明确批准的例外。不得自行降低阈值、扩大排除、伪造报告或把测试代码计入生产覆盖率。

典型调用：

```bash
python3 <pretty-executing-plan>/scripts/verify_incremental_coverage.py \
  --repo . --base <execution-start-head> --run --build-tool auto
```

工作区有用户预存改动时使用归因产生的临时 manifest：

```bash
python3 <pretty-executing-plan>/scripts/verify_incremental_coverage.py \
  --repo . --changed-manifest /tmp/<run>/changed-lines.json \
  --report target/site/jacoco/jacoco.xml
```

## 7. 失败、范围扩展和恢复

- 实现、测试或局部质量问题：Reviewer/Repair 或主 agent 修复并重跑受影响验证；
- 环境、权限、依赖下载、数据库或外部服务问题：停止并记录恢复条件；
- 无法可靠归因或反复没有进展：停止，不盲目重试；
- 需要改变上游合同：返回 PRD、Design 或 Plan。

停止时保留已有代码、测试和报告，记录当前 TASK、原因和恢复点；不得自动回滚用户或已完成的 Execution 改动。无因果证据的存量缺陷不扩展范围。

## 8. Execution 报告和交付

持续更新 Plan 同目录的 `execution.md`。报告是简要、可恢复的结果账本，只保留：

- 执行依据 `Plan`、起始 HEAD、工作区归因、执行模式和基线结论；
- 每个 TASK 的中文状态、实际文件/symbol、命中的质量原则与专项路由、实际落实、验证摘要和实质偏差；
- Writer、Reviewer/Repair、共享 Java 代码质量 Gate 及修复轮次的短结果；
- 最终范围/质量 Gate、覆盖率实际范围、质量 findings 处置和未验证范围；
- 恢复点和最终状态。

不复制完整终端日志、重复命令或每个 RED/GREEN 的长输出；失败和偏差保留命令、退出码及足以归因的短摘要，完整日志放仓库外临时目录。最终报告不得残留 `TODO`、`TBD`、`待验证`、`待审计` 或 `执行中`。

最终状态只允许：

- `完成`；
- `停止：<原因>`；
- `返回 PRD：<原因>`、`返回 Design：<原因>` 或 `返回 Plan：<原因>`。

多 TASK 中途停止时，保留已完成 TASK 的证据，当前 TASK 写恢复点，后续 TASK 写未执行；总体状态为 `停止`，不使用“部分完成”。完成后交付真实代码差异、报告路径、受影响范围验证、覆盖率结果、质量审查结论和未验证范围。

## 红线

- 不修改或追认 PRD、Design、Plan；
- 不在基线失败后修改生产代码；
- 不伪造 RED、覆盖率、测试通过或完成证据；
- 不把 UT 说成真实数据库、远端服务、部署或人工联调验证；
- 不为了覆盖率降低断言、扩大排除或新增无价值测试；
- 不在同一工作区并行写重叠文件；
- 不集成未经过 Reviewer/Repair（或主 agent 等价审查）及共享 Java 代码质量 Gate 的候选 Diff；
- 不自动执行 Git、发布或外部环境动作。
