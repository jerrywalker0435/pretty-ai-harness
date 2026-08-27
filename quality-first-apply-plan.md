# Pretty Apply 首次生成质量优化方案

> 状态：提案（可实施）
> 版本：0.2
> 更新日期：2026-08-27
> 范围：`pretty-common`、`pretty-executing` 及其 Harness；`prd.md`、`design.md` 和业务治理文档只读

## 1. 结论

可以提高第一次生成代码的质量，但现有方案主要保证“最终候选能否放行”，还没有把质量约束前移到 Writer 首次落笔前。

本方案采用两层目标：

1. **首次生成质量**：Writer 在第一次写入 Candidate Lane 前，已经拿到可执行的 Design、真实代码事实、完整质量路由和切片合同；第一次候选一旦产生就立即检查，不得带着不可豁免的机械错误、越界写集或无测试观察面继续推进。
2. **交付质量**：首次候选或后续定向修复形成的冻结候选，必须通过完整质量、构建、测试、覆盖率和一次独立 Reviewer，之后才能 Promotion。

这不能证明业务判断或测试断言绝对正确，但能把“已知的结构性错误”和“没有合同就开始猜实现”从最终阶段前移到首次生成阶段。质量规则不复制到本方案；本方案只定义各共享规则如何被执行。

### 1.1 预期收益与边界

| 机制 | 对首次生成质量的直接收益 | 对耗时的影响 | 仍不能证明 |
| --- | --- | --- | --- |
| 生成前 Slice Contract + Resolver | 降低臆造 API、漏掉失败语义、漏测观察面和错误依赖方向 | 一次性预检成本；后续切片复用 packet | 业务结果本身是否判断正确 |
| Candidate Lane + 权限隔离 | 首次错误候选不会污染目标工作区，失败可安全修复 | 创建 worktree 和摘要计算有固定小成本 | 平台若不能隔离写权限则无法执行 |
| Slice Fast Gate | 在下一切片前发现机械错误、测试失败和越界写集，减少错误扩散 | 比每切片完整回归/覆盖率明显更快 | 不替代最终完整 Gate |
| 冻结候选一次性完整 Gate | 统一证明真实 Diff、编译、测试、覆盖率和路由 | 消除逐切片 JaCoCo、重复编译和重复回归 | Reviewer 仍需做语义判断 |
| 删除 Dry Run/Preview | 减少模式分支、上下文加载、脚本和模板维护；Design 成为唯一前置资料 | 降低 token 和分支执行开销 | 不再提供非权威预演，需由 Design Review 承担方案确认 |

因此“提高第一次生成质量”应以可度量指标验收：每个切片的首尝试机械错误数、首尝试通过率、越界写入数、首尝试测试失败数和定向修复次数；最终交付仍以冻结候选 Gate 为准，不能把首尝试指标冒充最终正确性。

## 2. 现状差距与必须修正的冲突

| 方面 | 当前事实 | 问题 | 更新决定 |
| --- | --- | --- | --- |
| 首次生成 | `quality-principles.md` 要求 Writer 主动遵守，但没有生成前的机器可消费合同包 | Writer 仍可能先猜 API、边界或测试观察面 | 用执行矩阵作为唯一 Slice Contract；生成前预检未通过不得写代码 |
| 写入隔离 | 方案声称有 Candidate Lane，`apply_run.py` 实际只记录目标工作区路径摘要，没有创建 Lane 或 Promotion | 目标工作区可能被 Writer 直接修改，无法保证失败候选不落地 | `apply_run.py` 统一实现 Lane、冻结、Promotion 和清理 |
| 范围来源 | Resolver 以 `start_head` 推导真实 Diff，但矩阵、切片和脚本各自保存范围 | 可能重复计算或错误缩小扫描范围 | `start_head` 推导完整范围；矩阵只做 TASK/切片归因，不能缩小范围 |
| 切片覆盖 | `quality-contract-gates.md` 要求每个切片跑新鲜 JaCoCo；方案性能段又说切片不做正式覆盖率 | 流程规范互相冲突，且首次生成反馈过慢 | 切片只做静态 Gate、目标测试和受影响模块编译；正式覆盖率只在冻结候选执行一次，保留 registry 当前最低阈值 |
| 规则来源 | 规则 ID 在 `quality_registry.py`，说明和数字又散落在多个文档/脚本 | 修改规则时容易出现漂移 | registry 是规则、严重级别和覆盖率最低阈值的唯一来源；文档只引用 ID |
| 路由 | Resolver 负责风险，但 Writer 仍有机会自行解释或降级 | 首次生成可能漏审查风险 | Resolver 在生成前运行；新增 Symbol/依赖/边界才增量运行；Writer 不能修改路由结果 |
| Reviewer | 方案已有唯一最终 Reviewer，但 Lane/证据绑定尚未落地 | Reviewer 可能审查到过期候选 | Reviewer 只在冻结候选的客观 Gate 全通过后启动，receipt 绑定同一候选摘要 |
| Dry Run | `pretty-executing`、Design Skill、agents、Preview 资产、校验脚本和共享引用仍保留分支 | 两套流程、两套文档和两套校验增加上下文与维护成本 | 删除 Dry Run/Preview 全部入口、资产、脚本、字段和引用，只保留 Apply |
| 一致性检查 | 当前 `validate_pretty_consistency.py` 能通过，但只覆盖 owner、优先级和 Reviewer/Preflight 的少量不变量 | 检不出重复阈值/哈希、缺失 Lane/Promotion、逐切片覆盖冲突和已删除模式回流 | 扩展为唯一来源、状态迁移、残留模式和代码重复的结构检查 |

## 3. 唯一规范归属（消除重复）

以下归属是全局唯一解释，不允许在其他 Skill 再定义第二套规则：

| 内容 | 唯一来源 | 其他文件的职责 |
| --- | --- | --- |
| QP-01～QP-11 质量要求 | `pretty-common/references/quality-principles.md` | 只引用适用 QP，不改写规则 |
| 规则 ID、严重级别、风险 ID/owner、覆盖率最低阈值 | `pretty-common/scripts/quality_registry.py` | 扫描器、Resolver、Gate 读取注册表 |
| 风险触发算法 | `pretty-common/scripts/quality_resolver.py` | `quality-routing.md` 只解释由 registry 生成/校验的风险语义，不手写第二份 owner 表 |
| Gate 时机、证据字段、适用性 | `pretty-executing/references/quality-contract-gates.md` | 只定义何时执行和怎样绑定，不复制 QP 文案 |
| 运行状态、Lane、冻结、Promotion、清理 | `pretty-executing/scripts/apply_run.py` | Skill 只描述调用顺序 |
| 机械扫描实现 | `pretty-common/scripts/quality_contract_gate.py` | Slice/Candidate 通过 scope 参数调用同一实现 |
| canonical JSON、候选和证据摘要 | `pretty-common/scripts/evidence_binding.py` | 所有脚本调用，不再自定义哈希函数 |
| 真实范围 | `execution-state.json.start_head` 推导的 Git Diff | `execution-matrix.json` 只能归因，不能缩小 |
| 完成状态 | Apply 状态机和 `execution.md` 模板 | 不在 Skill、脚本和报告中分别发明状态 |

共享质量原则与质量路由必须全部适用。路由不改变 QP 优先级；`JAVA_OOD` 与 `FOCUSED_SOLID` 继续按现有规则二选一，`CHANGE_AXIS` 只有真实第二实现或批准变化轴才触发，`clean-code-guard` 对非平凡生产 Java 在最终候选执行一次。

registry 定义最低阈值；Design 或执行矩阵只能基于真实风险提高，不能降低。Apply 开始时把已解析策略写入 state 作为运行快照，这个快照是证据，不是第二个规范来源。

QP 的执行映射只保留这一张表，具体规则仍以 `quality-principles.md` 为准：

| QP | 首次生成时的约束 | 最终证明 |
| --- | --- | --- |
| QP-01、QP-09 | context packet 固定完整链路、规则归属、数据所有权、依赖方向和最小 Module 边界 | `MODULE_BOUNDARY` 路由 + Reviewer |
| QP-02、QP-04、QP-05、QP-07、QP-08 | Slice Contract 固定不变量、正常/失败语义、查询/命令、类型/返回值和日志边界；不允许猜测或兜底 | 机械规则 + 运行测试 + Reviewer |
| QP-03 | Design、共享规则、专项建议和仓库惯例只按共享优先级解释；Writer 不能改优先级 | 规则包摘要和 Reviewer receipt |
| QP-06 | packet 要求领域命名和必要注释；弱命名、复述注释等只在证据支持时保留 | 机械扫描 + `JAVA_OOD`/Reviewer |
| QP-10 | 先公共入口 RED，再最小 GREEN；只替换系统边界并证明业务结果 | 新鲜测试报告和覆盖义务 |
| QP-11 | 生成前读取真实文件/依赖，禁止臆造 API、fixture、抽象和依赖 | 范围校验、Resolver、最终独立 Reviewer |

### 3.1 Pretty Skill 分工

| Skill | 在新流程中的唯一职责 | 明确不做 |
| --- | --- | --- |
| `pretty-writing-prd` | 锁定业务可观察结果、REQ/AC 和领域上下文门禁 | 不选技术实现、不写代码、不进入 Apply |
| `pretty-writing-design` | 把 PRD 收敛为可执行的职责、边界、失败语义和 TASK 合同，并等待用户 Review | 不生成完整源码、不启动 Reviewer、不提供第二套 Preview |
| `pretty-executing` | 在 Candidate Lane 中按 Slice Contract 生成、验证、冻结和 Promotion | 不修改 PRD/Design，不绕过 Harness 写目标工作区 |
| `pretty-common` | 提供唯一质量基线、路由、规则注册、摘要绑定和临时目录安全 | 不拥有业务合同，不重复编排 Apply 状态 |
| 路由专项 Skill（`codebase-design`、Java OOD/Type/Runtime、SOLID、patterns、`tdd`、`clean-code-guard`） | 只提供 Resolver 指定的语义判断或固定 Guard，结论回填同一 evidence bundle | 不各自创建 Reviewer、Gate、阈值或审批流 |

## 4. 目标执行模型

```text
批准 Design
    ↓
Apply Preflight（真实事实 + 共享规则包 + Resolver + Slice Contract）
    ↓
创建 Candidate Lane（目标工作区保持不变）
    ↓
Writer：每个最小垂直行为切片 TDD RED → 最小 GREEN
    ↓
Slice Fast Gate（静态扫描 + 能完成相关编译的目标测试）
    ↓
候选扫描并冻结 → Final Objective Gate（编译/回归 + 覆盖率）
    ↓
唯一独立 Reviewer
    ↓
唯一 Promotion → 目标工作区
```

状态机只有 `apply_run.py` 定义：

```text
INIT
  → PREFLIGHT_PASSED
  → LANE_READY
  → WRITING
  → SLICE_GATED
  → FROZEN
  → OBJECTIVE_GATED
  → REVIEWING
  → REVIEW_PASSED
  → PROMOTED
  → CLEANED
```

任一候选内容、Design、矩阵、共享规则包、Resolver 输出、目标 HEAD 或 Gate 摘要变化，均使后续证据失效并回退到最早受影响状态。失败时保留 run 和恢复信息，不自动 stash、reset、rebase 或覆盖用户文件。

“目标工作区保持不变”特指目标代码、测试、配置、Schema、构建文件及其 Git Diff/HEAD 不变；已授权的 `docs/pretty/<topic>/tmp/<run-id>/` evidence 和嵌套 Lane 是隔离运行设施，必须从目标 Diff、范围扫描和 Promotion 摘要中排除。

### 4.1 Candidate Lane 与 Promotion

- `apply_run.py start` 在 `docs/pretty/<topic>/tmp/<run-id>/candidate/` 创建 detached Git worktree，起点为目标 `start_head`。该目录必须由 `execution-state.json` 精确登记并受运行平台写权限约束；Lane 是 run 的受管目录，不是普通 evidence 文件，也不允许回退到未登记的外部临时路径。
- `execution-state.json` 记录 `target_repo`、`candidate_lane`、`start_head`、Design/矩阵/共享规则/Resolver 摘要、运行路径和当前状态。所有代码、测试、编译和覆盖率命令在 Lane 中执行。
- Writer、专项 Skill 和普通命令的工作目录及可写根必须指向 Lane；目标工作区只允许 `apply_run.py promote` 写入。单纯约定目录、不具备平台写权限隔离不算落实，无法隔离时立即停止 Apply。
- Apply 起点要求目标运行路径干净；无关脏文件原样保留。Lane 内变更在冻结前通过同一候选摘要计算器生成 manifest 和 binary/full-index patch，完整覆盖新增、修改、删除、重命名和二进制文件。Promotion 前验证目标 HEAD、运行路径摘要和目标外部修改均未变化，执行 `git apply --check` 后再应用冻结 patch。
- Promotion 后重新计算目标 Diff 摘要，必须等于冻结候选；失败则停止并保留 Lane，不尝试自动修复。
- 清理由 `apply_run.py cleanup` 通过 `git worktree remove` 清理已登记 Lane，再由 `pretty_tmp.py` 删除 manifest 登记的证据。`pretty_tmp.py` 只为固定名称 `candidate` 接受一个受管目录，普通 artifact 仍必须是 run 直属文件；两个动作均校验精确路径，禁止手写递归删除。

## 5. 首次生成协议

### 5.1 生成前一次性预检

`execution_contract.py`、`quality_resolver.py` 和 `apply_run.py start` 在首次编辑前必须完成：

1. 读取当前 Design、目标文件、最近邻实现、实际 Java/JDK/构建配置和依赖版本；不能用相似代码猜 API。
2. 在同一 Writer run 启动时完整读取一次共享规则包（QP、routing、registry、gate、runtime authorization）并固定摘要和工具版本；后续切片不重复加载整套长文。
3. 先生成只含 TASK、切片范围和合同事实的骨架矩阵；`quality_resolver.py` 读取它和真实调用链、Schema、依赖后派生风险，再把 `resolver_rules` / `resolver_risks` 绑定回最终矩阵。Writer 不得自报、删除或降级，从而避免“矩阵依赖 Resolver、Resolver 又依赖完整矩阵”的循环。
4. 记录最小相关基线测试；历史失败只用于归因，不替代本次测试证据。
5. 校验每个 TASK 的 `contract_preflight` 和 `behavior_slices`。每个 Java 行为切片至少拥有：`paths`、`production_symbols`、`test_entry`、`input_invariants`、`boundary_substitutes`、`result_assertions`、`nearest_neighbors`、`coverage_obligations`、`resolver_rules`、`resolver_risks`、`depends_on` 和 `non_goals`。`production_symbols`、`result_assertions`、`coverage_obligations` 为空时硬停止；纯声明/DDL TASK 必须写明 `non_behavior_reason`。
6. 将 Slice Contract 编译成短的 Writer context packet。packet 只包含当前切片的允许文件/Symbol、输入不变量、正常/失败/边界结果、公共验证入口、替身边界、最近邻实现、适用规则 ID/registry 标准描述和禁止扩展范围。packet 必须从唯一来源自动投影，不能维护手写副本；同一 Writer run 已加载的完整 QP 不在每个切片重复注入。

这一步复用执行矩阵，不新增第二份 `plan.md`、Preview 或独立“生成规范”文档。预检失败只能返回 Design，不能先写代码再补合同。

### 5.2 每个行为切片

切片按 Design 中的最小垂直可观察结果拆分；只有存在独立行为、独立失败语义或真实依赖顺序时才拆分，避免人为增加切片数量。

Writer 在 Candidate Lane 中按以下固定顺序工作：

```text
确认 context packet
  → TDD RED（批准的公共入口和业务断言）
  → 最小 GREEN
  → Slice Fast Gate
  → 失败时只做定向修复并重新计算候选摘要
  → Slice 冻结，进入下一个切片
```

Slice Fast Gate 包含：

- `quality_contract_gate.py` 只扫描当前切片实际变更文件；不可豁免 `error` 必须为零，`review_required` 记录待最终 Reviewer 处理；
- 新增/修改测试实际执行并生成新鲜报告；测试只替换数据库、网络、时间、随机等系统边界，不 mock 自有内部协作者，不测试 private 方法，不用调用次数代替行为断言；
- 运行能编译受影响模块及必要闭包的最小目标测试；若该 TASK 无可执行测试或构建系统不会随测试完成必要编译，才补一个独立局部编译命令。不重复执行等价编译，不做全量回归和正式 JaCoCo；
- 发现新文件、Symbol、依赖或边界时立即增量运行 Resolver。仍在批准 Design 内时更新矩阵归因，并由 `apply_run.py rebind` 原子更新矩阵/Resolver 摘要、使当前切片旧 Gate 失效后重跑；公共合同、所有权、依赖方向、外部行为或观察面发生变化时返回 Design；
- 所有变更仍只存在 Lane，未通过切片 Gate 不得扩展其他生产层。

“第一次生成”按行为切片度量：每个切片第一次 `GREEN` 后，Harness 立即固化该切片的 `first_attempt_sha256`、机械 finding、测试结果和后续定向修复次数。这样不会只衡量第一个切片，也不会把集成后的多轮结果冒充首次生成；后续候选不能覆盖这些指标。Promotion 只接受最终完整冻结候选。

### 5.3 完整候选与最终 Reviewer

所有切片完成后先停止 Writer 主动修改，先对当前 Lane 候选扫描并冻结，再执行一次：

1. 以 `start_head` 推导完整 Git Diff，包含新增、修改、删除和未跟踪运行路径；topic tmp 排除在外。
2. 对完整 Diff 运行候选机械 Gate；高置信 `error=0` 后固定候选摘要并进入 `FROZEN`。`review_required` 保留给最终 Reviewer 逐条处理，机械错误不可批量豁免。
3. 对冻结候选的受影响模块执行编译、目标测试和相关回归；新鲜报告必须证明新增/修改测试实际执行。
4. 对冻结候选的完整生产 Java 增量执行正式 JaCoCo，阈值取本次 state 中由 registry 解析的策略快照；无生产 Java 增量才使用结构化 `not_applicable`。覆盖义务按 Symbol/分支和业务断言核对，不能仅凭总体百分比跳过关键组合。
5. 对非平凡生产 Java 执行一次 `clean-code-guard`，receipt 绑定完整候选；不按风险拆分 Reviewer。
6. 固定 `quality.json`、`build.json`、`tests.json`、`coverage.json`，进入 `OBJECTIVE_GATED`。客观 Gate 或 Reviewer 失败时必须通过 `apply_run.py reopen --reason <finding>` 显式回到 `WRITING` 并恢复 Lane 写权限；定向修复产生新摘要，所有受源码或构建结果影响的旧 Gate/receipt 立即失效。
7. 只有完整客观 Gate 通过后启动一名独立 Reviewer。Reviewer 使用独立上下文，检查 Design 一致性、完整链路、职责/所有权/依赖、失败语义、状态/事务/并发/幂等/副作用、类型/异常/日志、测试观察面和 Resolver 完整性。

## 6. 性能与字符/代码精简策略

### 6.1 不降低质量的运行优化

| 成本项 | 优化 | 不可省略的证明 |
| --- | --- | --- |
| 规则上下文 | 每个 run 读取并哈希一次共享规则包，Slice packet 只带适用 ID | 规则包摘要绑定所有证据 |
| Resolver | 预检一次；只有新文件/Symbol/依赖/边界增量复核；冻结前完整复核 | 风险集合不可删除，owner 必须来自 registry |
| 静态扫描 | 同一扫描器支持 `slice`/`candidate` scope；按文件内容摘要缓存 | Slice 和完整 Diff 各有当前候选证据 |
| 编译 | Slice 的目标测试命令已完成必要编译时不再单独编译；最终命令图只保留一次完整必需编译；复用 Maven/Gradle/JDK 缓存 | `build.json` 记录真实命令、退出码、满足的 Gate 和候选摘要 |
| 测试 | Slice 只跑目标测试；最终把目标测试、相关回归和覆盖率按实际选择集合去重；复用构建缓存但不复用过期证据 | 新鲜报告证明新增/修改测试实际执行 |
| 覆盖率 | 去掉逐切片 JaCoCo，仅冻结候选跑一次正式增量覆盖率 | 最终仍必须达到 registry 阈值或结构化不适用 |
| Reviewer | 每次 Apply 仅一名最终独立 Reviewer | receipt 绑定 objective Gate 和候选摘要 |
| 并行 | 只并行依赖图无先后关系、互不写同一构建输出的冻结候选 Gate；测试依赖编译、覆盖率依赖测试时仍串行 | 所有客观证据汇总后再启动 Reviewer |
| 切片数量 | 只按真实行为/依赖拆分，不按 Controller/Service/Repository 人为拆分 | 每个切片仍有完整结果断言和路由 |

最终 Gate 先生成命令依赖图。一次真实命令可以同时满足 `compile`、`new_tests`、`regression_tests`、`coverage` 中的多个 Gate，但必须在 `build.json` 逐项登记它满足的范围和报告；禁止为了凑四类 evidence 重复运行相同测试集，也禁止把未实际覆盖的 Gate 标为满足。

### 6.2 精简 Skill 和脚本

- `pretty-executing/SKILL.md` 只保留 Apply 顺序、停止条件和引用；不再重复 QP、风险表、JSON 字段或命令细节。
- `quality-contract-gates.md` 只保留 Gate 时机/字段/阈值引用；规则解释回到 QP，owner 回到 routing，数字回到 registry。
- `apply_run.py` 是唯一状态/Lane/Promotion/rebind/reopen/cleanup 编排器；不再在其他脚本复制状态机或路径清理。
- 扩展现有 `pretty-common/scripts/evidence_binding.py`，集中候选摘要、证据摘要和 canonical JSON 哈希；删除 `quality_contract_gate.py`、`apply_run.py`、`validate_execution.py` 中的重复实现，不新增另一个哈希模块。
- 从 `apply_run.py` 删除 `SliceCoverageRequest`、`slice-coverage` 及逐切片覆盖状态；改为一个 `slice-gate` receipt 绑定静态扫描、目标测试/必要编译和 first-attempt 指标。
- 从 `verify_incremental_coverage.py` 删除 `--slice-manifest`、`--slice-id` 和切片分支，只保留完整冻结候选的增量覆盖率；`execution.md` 模板删除切片覆盖率表，改为简短 Slice Fast Gate 结果。
- 删除 Preview 专用校验、模板、测试提案协议和模式分支，减少 token、文件扫描和执行分支。
- 允许脚本复用编译/依赖缓存；不允许通过测试过滤器、构建参数、`@Disabled` 或降低阈值来换取速度。

## 7. Dry Run 删除清单

这是一次性迁移，不保留兼容模式或隐式 Preview：

### 删除文件

- `skills/pretty-executing/assets/execution-preview.md`
- `skills/pretty-executing/references/test-preview.md`
- `skills/pretty-executing/scripts/validate_preview.py`

### 修改文件

- `skills/pretty-executing/SKILL.md`：删除 Dry Run 段、Preview 输入和所有分支，只保留 Apply。
- `skills/pretty-executing/agents/openai.yaml`：默认提示只调用 Apply。
- `skills/pretty-executing/assets/execution.md`：删除 `Preview 输入` 字段和 Preview 相关文案。
- `skills/pretty-writing-design/SKILL.md`、`agents/openai.yaml`：后续只提供 Apply，不再展示 Preview 选项。
- `skills/pretty-common/references/quality-principles.md`：删除 Preview 共同适用语句，改为 Apply 生成与候选共同遵守。
- `skills/pretty-common/references/quality-review-protocol.md`：删除 Dry Run 例外，明确 Apply 唯一 Reviewer 规则。
- `skills/pretty-common/references/runtime-authorization.md`：授权对象只保留 Design/Apply；删除 Preview 路径和说明，并区分 topic run 内的 evidence 文件与固定 `candidate/` worktree。
- `skills/pretty-common/scripts/disabled_test_scope.py`：文档字符串和调用说明只保留 Apply。
- `skills/pretty-common/scripts/validate_pretty_consistency.py`：增加已删除模式的残留引用检查，检测词串用拆分/编码常量表示，避免检查器自身成为残留。

删除后执行 `rg -n -i 'dry.?run|preview|execution-preview|test-preview' skills --glob '!**/validate_pretty_consistency.py'` 必须无结果；计划、迁移记录和检查器的编码常量不算运行时入口，其他 Skill、资产、模板、脚本和 agents 不得保留这些术语、文件或分支。

## 8. 文件级实施顺序

### Phase 0：规范收敛

- 在 `quality_registry.py` 增加覆盖率最低阈值和完整 `RiskSpec`；`quality-routing.md` 的风险视图由 registry 生成或一致性校验，删除手写 owner 重复。
- 扩展 `evidence_binding.py` 并删除各脚本的本地哈希实现；共享规则包版本由规范文件内容直接计算，不再人工维护另一个版本号。
- 集中候选/证据摘要计算，统一 `start_head`、Design、矩阵、规则包和源文件绑定。
- 更新 Gate reference，明确 Slice Fast Gate 与 Final Objective Gate；删除逐切片覆盖率的旧要求。
- 完成 Dry Run 删除清单，并运行一致性检查。

### Phase 1：隔离写入

- 在 `apply_run.py` 实现 `start` 创建 Lane、状态登记和目标路径只读快照；增加 `rebind`（批准范围内增量路由）和 `reopen`（带 finding 的定向修复）状态转换。
- 将 checkpoint、resume、register、cleanup 全部改为围绕 Lane；删除目标工作区直接写入路径。
- 增加 Lane 生命周期和目标工作区未修改的 Harness 回归测试。

### Phase 2：首次生成闭环

- 扩展执行矩阵校验：Slice Contract、`non_goals`、Resolver 风险和生成前预检。
- `quality_resolver.py` 支持完整起始 Diff、切片增量和冻结前复核；禁止 Writer 自报路由。
- `quality_contract_gate.py` 增加 scope/摘要缓存；Slice Fast Gate 失败时只允许在当前 Lane 定向修复。
- `apply_run.py slice-gate` 记录每个切片 first-attempt 与最新 Gate，验证首次生成质量指标不被修复结果覆盖。

### Phase 3：冻结、审查和 Promotion

- `verify_quality_contract.py` 只接受完整 Diff 和当前候选；生成 objective Gate 绑定的四类证据。
- `apply_run.py` 增加 `freeze`、`start-review`、`record-review`、`reopen`、`promote`，并在每个入口重新校验摘要和目标 HEAD；任何入口不得隐式改变 phase。
- Promotion 使用冻结 patch；成功后重新计算目标 Diff，失败保留 Lane 供恢复。
- `validate_execution.py` 按唯一状态和唯一证据链校验 `execution.md`。

### Phase 4：性能和回归

- 复用 Maven/Gradle 依赖与编译缓存；只并行冻结后的只读 Gate。
- 用命令依赖图合并等价的编译/测试/覆盖命令，并验证一个命令只声明它真实满足的 Gate。
- 运行共享一致性检查、Python 编译、Harness 回归和一条真实 Apply 演练；记录首候选通过率、修复次数和端到端耗时。

必须覆盖的 Harness 回归：

- preflight、共享规则包或 Resolver 未绑定时拒绝首次写入；
- Writer 写目标工作区、切片越界写入或新 Symbol 未 `rebind` 时拒绝；
- first-attempt 只写一次，修复不能覆盖首次 finding/测试结果；
- `error` 阻断 slice/freeze，降低 registry 阈值被拒绝；
- 完整 patch 覆盖新增、修改、删除、重命名和二进制文件；
- frozen 后修改、客观 Gate 失败或 Reviewer finding 只能通过 `reopen`，旧 evidence/receipt 全部失效；
- Resolver 漏风险、owner 错误、共享包/矩阵/候选摘要过期时拒绝；
- 目标 HEAD、运行路径或 patch 校验变化时拒绝 Promotion；
- 全部 Gate 和唯一 Reviewer 通过时 Promotion 摘要一致，cleanup 只删除登记 Lane/证据；
- Skill 中出现 Dry Run/Preview 残留、逐切片覆盖分支或重复哈希实现时一致性检查失败；
- 合并命令不会重复执行等价测试，也不会漏报 compile/test/regression/coverage 中的适用 Gate。

## 9. 最小证据链与状态字段

证据只允许单向绑定，不允许跨运行拼接：

```text
Design SHA + start HEAD
  → execution-matrix SHA
  → shared-bundle SHA + resolver SHA
  → per-slice first-attempt SHA（指标）
  → frozen candidate SHA
  → quality/build/test/coverage evidence
  → Reviewer receipt
  → Promotion result
```

`execution-state.json` 的最小字段为：

```json
{
  "schema_version": 4,
  "mode": "apply",
  "topic": "<topic>",
  "run_id": "<run-id>",
  "target_repo": "<repo>",
  "candidate_lane": "docs/pretty/<topic>/tmp/<run-id>/candidate",
  "start_head": "<git-sha>",
  "design_sha256": "<sha256>",
  "execution_matrix_sha256": "<sha256>",
  "shared_bundle_sha256": "<sha256>",
  "resolver_sha256": "<sha256>",
  "coverage_policy": "<resolved-policy-snapshot>",
  "contract_preflight": "<passed-summary>",
  "registered_runtime_paths": {"<relative-path>": "<sha256-at-start>"},
  "slice_runtime_paths": {"SLICE-001": ["<relative-path>"]},
  "slice_order": ["SLICE-001"],
  "active_slice": "SLICE-001",
  "phase": "writing",
  "first_attempts": {
    "SLICE-001": {
      "candidate_sha256": "<sha256>",
      "mechanical_findings": 0,
      "tests_passed": true,
      "repair_count": 0
    }
  },
  "slice_results": {
    "SLICE-001": {
      "candidate_sha256": "<sha256>",
      "quality_evidence_sha256": "<sha256>",
      "test_evidence_sha256": "<sha256>",
      "passed": true
    }
  },
  "candidate_sha256": null,
  "objective_gate": null,
  "temporary_artifacts": ["execution-matrix.json", "candidate-manifest.json", "candidate.patch"],
  "status": "in_progress"
}
```

路径快照、证据文件名和时间字段可以扩展，但不得另起一套状态、哈希或清理协议。旧 `.execution-state.json` 兼容别名随 schema 4 一并移除，避免两个状态文件产生分叉。

## 10. 验收标准

### 10.1 首次生成质量

- Writer 第一次写入前，Slice Contract、真实依赖事实、共享规则包和 Resolver 风险均已绑定当前 run。
- 第一次候选只存在 Candidate Lane；目标运行路径的内容、Diff 和 HEAD 保持不变，topic run 临时设施不计入目标 Diff。
- 第一次候选必须经过 Slice Fast Gate；若有不可豁免机械错误、越界写集或缺失观察面，不得进入下一切片。首候选 finding、是否首过和定向修复次数必须单独记录，且不可被后续候选覆盖。
- 首次候选失败时只能产生带新摘要的定向修复，不得覆盖首次结果或复用旧证据。

### 10.2 最终交付质量

- Design TASK、完整真实 Diff、执行矩阵和 Resolver 风险一致；新增文件、Symbol、依赖和边界没有漏路由。
- 完整机械 Gate 的 `error=0`；`review_required` 逐条有证据；编译、目标测试、相关回归和新增/修改测试实际执行均通过。
- 正式增量覆盖率达到 registry 阈值或有结构化 `not_applicable`；DDL 只交付文件，不执行或验证数据库；配置数据 DML 仍由人工运维。
- 只有一名独立 Reviewer，receipt 与当前冻结候选及 objective Gate 完全绑定；Reviewer 不能批量豁免机械错误。
- 只有 `apply_run.py promote` 能修改目标工作区；Promotion 前后摘要一致，目标 HEAD 未变化。

### 10.3 全局一致性与效率

- Pretty 运行时不存在 Dry Run/Preview 文件、字段、入口或分支。
- 规则、路由 owner、阈值、状态、摘要和清理各只有一个来源；一致性脚本无错误。
- 不再逐切片运行正式覆盖率、全量回归或 Reviewer；缓存和只读 Gate 并行有效。
- 以“首次候选机械错误数、首次通过率、定向修复次数、最终通过率、Apply 总耗时”作为回归指标；任何性能优化不得改变质量 Gate 的最终放行条件。
