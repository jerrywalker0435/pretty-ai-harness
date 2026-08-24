# Execution 质量与输入范围 Gate

本文件只定义 Execution 的放行、返回和降级条件；代码设计原则集中在[共享质量基线](../../pretty-common/references/quality-principles.md)，不在此重复。

## 输入与范围 Gate

- 当前 Plan 必须先通过 `pretty-writing-plan/scripts/validate_plan.py`；代码提案扫描失败时返回 Plan，不进入 Writer。Plan 的完整代码提案由 Plan 阶段负责 Reviewer/Repair，Execution 不把重复的结构化契约字段作为输入前提。
- TASK 必须对应 Plan 的目标、范围、验收条件、公共 Seam 和测试边界。
- 实现前必须明确输入输出、异常、事务、并发、幂等和上下游契约。
- 发现 PRD、Design 或 Plan 冲突、歧义，或 Plan 无法覆盖当前行为时，返回对应阶段，不自行猜测。
- 必要的存量协同修改若不改变外部语义、架构边界和风险等级，记录“范围扩展（范围与语义不变）”后继续；否则返回 Design 或 Plan。

## 质量路由 Gate

- 首次生产代码编辑前完整读取共享质量基线，并根据真实增量风险选择最小、不重叠的质量 Skill 集合，不批量加载全部 Skill。
- 行为变更必须完成 TDD Gate；命中的专项路由必须在实现前转成具体的职责、签名、异常合同、类型、测试行为、配置/Schema 或任务切分约束。
- 实现或 TASK 复核中出现新风险时，重新评估并只补充必要的专项路由；新增路由的结论必须落到实际 diff 和验证证据。
- 接口/Seam/模块边界使用 `codebase-design`；Java 职责与封装使用 `121-java-object-oriented-design`；类型和值对象使用 `122-java-type-design`；依赖方向与职责使用 `solid-principles`；真实变化轴使用 `design-patterns`；null、异常、并发、资源、性能或 API 风险使用 `java-code-review`；命名和可读性风险按需使用 `clean-code`。
- `clean-code-guard` 不是默认专项路由；只有实际风险与现有工作流明确命中时才调用，不能替代共享质量基线或其他已命中的专项审查。
- 普通专项能力缺失时使用共享质量基线并记录“降级”；公开接口、迁移、并发、安全或高风险架构缺少必要能力时返回 Design 或 Plan。

## Writer–Reviewer/Repair Gate

- Writer 的候选 Diff 不是交付结果；生产代码 TASK 必须经过候选 Diff 的共享 Java 代码质量扫描和适用的语义质量审查。
- Reviewer/Repair 可以在隔离候选中直接修复局部质量违规，但不得改变 PRD、Design、Plan、外部结果、架构边界、测试边界或任务范围；触及这些边界时返回对应阶段。
- Reviewer/Repair 每次修改后必须重新运行共享 Java 代码质量扫描、受影响编译和相关测试；不得沿用修改前的通过证据。
- 不同 TASK 只有在文件、symbol、接口、测试资源和构建环境均隔离时才可并行；主 agent 负责集成、真实 Diff 复核和最终裁决。
- 纯文档、配置、SQL、资源或确定性改名任务不启动代码 Writer/Reviewer，但仍须执行适用的机械 Gate，并记录未触发原因。

## TASK 质量 Gate

- 以共享质量基线和该 TASK 命中的专项路由审查真实增量代码、调用链、测试和配置/Schema 证据；命中的原则必须能在实际 diff 中找到落实证据。
- 包含 Java 增量的 TASK 必须通过 `pretty-common/scripts/quality_contract_gate.py` 的共享 Java 代码质量扫描；扫描失败时先修复，不能只记录 findings。命令/查询方法分类若要进行机械检查，使用 Execution 临时方法清单，不把重复字段写回 Plan。
- 共享扫描器阻断通配符 import、生产字段注入、空 `catch`、空值传播三元、过量日志、分支重复日志、方法内过量注释和既有高确定性契约违规；长方法、参数超过 6 个及嵌套/多个三元只记录 warning，简单三元表达式允许。warning 不阻断 Gate，error 必须修复。
- JDK 8 兼容性不由正则扫描器判断；使用受影响模块的实际 Maven `source`/`target`/`release` 或 Gradle Java compatibility/toolchain 编译 Gate 验证。
- 生产代码 TASK 完成后必须完成适用的收尾质量审查和专项审查；不为形式补载未命中的通用审查。
- 共享质量基线或命中专项路由发现的阻断问题必须在 TASK 完成前修复；未修复时 TASK 不能标记为完成，也不能被最终状态掩盖。
- 全部 TASK 完成后再做一次跨 TASK 组合检查，处理累计职责、重复知识、接口膨胀和依赖方向问题。
- 未修改且无本次增量因果证据的存量问题只记录，不纳入本次门禁。

## 验证 Gate

- 基线失败时不修改生产代码。
- TASK 必须有受影响范围编译、相关测试和适用覆盖率证据；验证失败按实现、环境或上游契约归因处理。
- 增量覆盖率的阈值、中文状态和例外规则以 `SKILL.md` 的独立验证章节为准。
- 测试、覆盖率或质量验证失败时不能将最终状态写为“完成”，除非存在明确例外依据；质量阻断项未修复时不适用完成例外。
