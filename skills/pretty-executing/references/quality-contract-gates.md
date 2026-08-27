# Apply 质量合同 Gate

首次修改生产或测试代码前确认：

- 当前主题的 `prd.md`、`design.md` 可读取，且 Design TASK 可载入执行矩阵；Execution 不重新运行 Design 校验或审查；
- 运行相关路径（源码、测试、构建配置、运行时资源、Schema、迁移、生成输入和构建脚本）没有未提交变化；说明性文档可脏；
- 已建立 `.execution-state.json`，或恢复状态与登记文件摘要完全匹配；
- 最小相关基线已运行并能区分历史失败；
- 目标测试文件已扫描 `@Disabled`、`@Ignore`、元注解和条件禁用；新增测试不进入禁用作用域；
- Design TASK、公共验证入口、影响锚点和验证观察面已载入临时执行矩阵；
- Writer 已完成合同可执行性预检：模块边界、运行时语义、验证观察面和交付归属均为 `clear`，或有事实依据的 `not_applicable`；缺失、冲突或无法落实时返回 Design。

合同可执行性预检是首次编辑硬停止点，不是独立 Reviewer，也不得补写或改变 Design。执行矩阵的 `contract_preflight` 至少包含 `module_boundaries`、`runtime_semantics`、`verification_surface` 和 `delivery_ownership`；每项记录 `status`、具体 `evidence`，不适用时还要记录 `reason`。

执行矩阵为每个 TASK 记录适用 Gate。Java 行为 TASK 通常适用 `compile`、`new_tests`、`regression_tests` 和覆盖率；纯 DDL/声明性 TASK 可将这些 Gate 结构化标为不适用并说明原因。汇总 `build.json` 用 `required_kinds` 声明本次实际要求的命令种类，不能仅在报告文字中跳过。

Java 行为 TASK 的每个 `behavior_slices` 条目至少记录：`id`、`paths`、`production_symbols`、`test_entry`、`input_invariants`、`boundary_substitutes`、`result_assertions`、`nearest_neighbors`、`coverage_obligations`、`resolver_rules`、`resolver_risks` 和 `depends_on`。`production_symbols`、`result_assertions`、`coverage_obligations`、`resolver_rules` 不得为空；`resolver_rules` 和 `resolver_risks` 只能来自共享 `quality_resolver.py`，Writer 不得自报、删除或降级。其他列表在事实不适用时可为空。没有 Java 行为的 TASK 使用空 `behavior_slices` 并提供 `non_behavior_reason`。这是生成前的执行预检，不冻结完整代码，也不成为 Design 之外的新规范合同。

`coverage_obligations` 按生产 Symbol 或分支记录正常、失败和边界路径、对应测试入口及必须断言的业务结果。切片只有在目标测试实际执行且当前增量覆盖率闭环后才能冻结；关键业务组合不能仅凭总体百分比跳过。

执行矩阵不拥有真实变更范围。质量扫描和覆盖率必须以 `.execution-state.json` 中的 `start_head` 计算 Git Diff，并包含所有新增、修改、删除和未跟踪的运行相关路径；`changed-manifest` 只能作为 TASK 行归因资料，存在时必须覆盖 Git 推导的全部 Java 路径并使用相同变更行，覆盖率部分必须与生产 Java 路径和行集合完全一致，不能缩小扫描范围。

生成质量采用两层 Gate：每个行为切片完成后立即运行共享机械扫描、目标测试和切片覆盖率，冻结候选前再对完整 Git Diff 运行一次机械扫描和正式增量覆盖率。前者用于尽早反馈和阻止坏代码继续扩散，后者用于绑定最终真实候选；两者不重复承担对方的证据职责。

最终 Reviewer 启动前确认：

- 所有 Design TASK 已集成并归档到执行矩阵；
- 目标测试通过，Writer 完成完整 Diff 自审且没有机会性重构；
- 高置信机械 Gate 的 `error` 为零，`review_required` 均已分诊；
- 测试实际执行证据覆盖新增/修改测试，不能只证明编译成功；
- 受影响模块编译、目标测试、相关回归和正式增量覆盖率已经通过；
- build、tests、coverage 和候选摘要已经固定，随后 Writer 不再主动修改。

先用 `verify_quality_contract.py --scan-only` 固定机械候选摘要；build、tests 和 coverage 绑定该摘要并可在隔离输出下并行运行。全部客观 Gate 通过后，Reviewer receipt 通过 `pre_review_gate` 绑定其候选摘要；最终 Reviewer 不与这些 Gate 并行，任何摘要变化都会使 Reviewer 证据失效。`--scan-only` 只形成候选和阻断机械 `error`，不构成交付质量结论。

最终 Apply Gate 确认：

- Design TASK 与真实 Diff、执行矩阵一致；
- 机械扫描与唯一最终独立 Reviewer 通过；
- 受影响模块编译、目标测试和相关回归通过；
- 增量行覆盖率至少 90%、分支覆盖率至少 80%，或无生产 Java 增量时不适用；
- 修复后证据绑定最终完整 Diff，旧候选证据没有被复用；
- 公共合同、职责、所有权、依赖方向、外部行为或验证观察面变化均已返回 Design。

`quality.json`、`coverage.json` 和汇总 `build.json` 都必须记录同一个完整 `start_head`，并与 `execution.md` 的起始 HEAD 一致；不同运行的证据不能拼接成完成状态。

`build.json` 的最小绑定字段为：

```json
{
  "candidate_sha256": "<移除本字段后按 UTF-8 canonical JSON 计算的 SHA-256>",
  "start_head": "<与 .execution-state.json 相同的完整 Git SHA>",
  "design_sha256": "<Design 摘要>",
  "quality_candidate_sha256": "<quality.json 候选摘要>",
  "coverage_evidence_sha256": "<coverage.json evidence_sha256>",
  "test_evidence_sha256": "<tests.json evidence_sha256>",
  "required_kinds": ["compile", "new_tests", "regression_tests"],
  "commands": [
    {"kind": "compile", "command": "<真实命令>", "exit_code": 0, "finished_at": 0}
  ]
}
```

最终 Reviewer receipt 的 `pre_review_gate` 至少绑定：

```json
{
  "quality_candidate_sha256": "<quality.json 候选摘要>",
  "build_candidate_sha256": "<build.json 自身摘要>",
  "test_evidence_sha256": "<tests.json evidence_sha256>",
  "coverage_evidence_sha256": "<coverage.json evidence_sha256>"
}
```

`required_kinds` 按 TASK 实际 Gate 汇总；适用项不能通过省略来降级。停止状态保留真实已执行命令，不伪造成功条目。

表、字段和索引等结构性 DDL 只能作为代码库文件实现，不得直接执行，也不得通过 Flyway、Liquibase、数据库客户端、应用启动、构建插件、集成测试或其他路径间接执行。最终报告写明“已交付、未执行、未进行数据库验证”。配置数据 DML 由人工运维处理，Preview 和 Apply 都不生成或执行。

`.execution-state.json` 的最小形状：

```json
{
  "schema_version": 2,
  "mode": "apply",
  "topic": "<topic>",
  "start_head": "<git-sha>",
  "design_sha256": "<sha256>",
  "execution_matrix_sha256": "<sha256>",
  "contract_preflight": {"status": "passed", "areas": ["module_boundaries", "runtime_semantics", "verification_surface", "delivery_ownership"]},
  "registered_runtime_paths": {"<relative-path>": "<resume-sha256>"},
  "status": "in_progress"
}
```

此状态只用于判断能否恢复同一次 Apply。首次编辑前写入；意外中断时保留；完成或明确停止时删除。任何字段或登记摘要不匹配都停止，不尝试自动修复工作区。
