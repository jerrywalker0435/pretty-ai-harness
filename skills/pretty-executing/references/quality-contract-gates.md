# Apply 质量合同 Gate

首次修改生产或测试代码前确认：

- 当前主题的 `prd.md`、`design.md` 可读取，且 Design TASK 可载入执行矩阵；Execution 不重新运行 Design 校验或审查；
- 运行相关路径（源码、测试、构建配置、运行时资源、Schema、迁移、生成输入和构建脚本）没有未提交变化；说明性文档可脏；
- 已建立 `.execution-state.json`，或恢复状态与登记文件摘要完全匹配；
- 最小相关基线已运行并能区分历史失败；
- 目标测试文件已扫描 `@Disabled`、`@Ignore`、元注解和条件禁用；新增测试不进入禁用作用域；
- Design TASK、公共验证入口、影响锚点和验证观察面已载入临时执行矩阵。

执行矩阵为每个 TASK 记录适用 Gate。Java 行为 TASK 通常适用 `compile`、`new_tests`、`regression_tests` 和覆盖率；纯 DDL/声明性 TASK 可将这些 Gate 结构化标为不适用并说明原因。汇总 `build.json` 用 `required_kinds` 声明本次实际要求的命令种类，不能仅在报告文字中跳过。

候选冻结前确认：

- 所有 Design TASK 已集成并归档到执行矩阵；
- 目标测试通过，Writer 完成完整 Diff 自审且没有机会性重构；
- 高置信机械 Gate 的 `error` 为零，`review_required` 均已分诊；
- 测试实际执行证据覆盖新增/修改测试，不能只证明编译成功；
- Reviewer-ready 候选摘要已生成，随后 Writer 不再主动修改。

最终 Apply Gate 确认：

- Design TASK 与真实 Diff、执行矩阵一致；
- 机械扫描与适用的独立 Reviewer 通过；
- 受影响模块编译、目标测试和相关回归通过；
- 增量行覆盖率至少 90%、分支覆盖率至少 80%，或无生产 Java 增量时不适用；
- 修复后证据绑定最终完整 Diff，旧候选证据没有被复用；
- 公共合同、职责、所有权、依赖方向、外部行为或验证观察面变化均已返回 Design。

表、字段和索引等结构性 DDL 只能作为代码库文件实现，不得直接执行，也不得通过 Flyway、Liquibase、数据库客户端、应用启动、构建插件、集成测试或其他路径间接执行。最终报告写明“已交付、未执行、未进行数据库验证”。配置数据 DML 由人工运维处理，Preview 和 Apply 都不生成或执行。

`.execution-state.json` 的最小形状：

```json
{
  "schema_version": 1,
  "mode": "apply",
  "topic": "<topic>",
  "start_head": "<git-sha>",
  "design_sha256": "<sha256>",
  "execution_matrix_sha256": "<sha256>",
  "registered_runtime_paths": {"<relative-path>": "<resume-sha256>"},
  "status": "in_progress"
}
```

此状态只用于判断能否恢复同一次 Apply。首次编辑前写入；意外中断时保留；完成或明确停止时删除。任何字段或登记摘要不匹配都停止，不尝试自动修复工作区。
