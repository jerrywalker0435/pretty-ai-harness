# Execution 质量与契约 Gate

本文件只定义 Execution 的放行、返回和降级条件；代码设计原则集中在 `quality-principles.md`，不在此重复。

## 契约 Gate

- TASK 必须对应 Plan 的目标、范围、验收条件、公共 Seam 和测试边界。
- 实现前必须明确输入输出、异常、事务、并发、幂等和上下游契约。
- 发现 PRD、Design 或 Plan 冲突、歧义，或 Plan 无法覆盖当前行为时，返回对应阶段，不自行猜测。
- 必要的存量协同修改若不改变契约、架构边界和风险等级，记录“范围扩展（契约不变）”后继续；否则返回 Design 或 Plan。

## 质量路由 Gate

- 首次生产代码编辑前选择最小、不重叠的质量 Skill 集合，不批量加载全部 Skill。
- 行为变更必须完成 TDD Gate；生产代码完成后必须完成收尾质量审查；其他专项 Skill 按增量风险选择。
- 接口/Seam/模块边界使用 `codebase-design`；Java 职责与封装使用 `121-java-object-oriented-design`；类型和值对象使用 `122-java-type-design`；依赖方向与职责使用 `solid-principles`；真实变化轴使用 `design-patterns`；null、异常、并发、资源、性能或 API 风险使用 `java-code-review`；命名和可读性风险按需使用 `clean-code`。
- 普通专项能力缺失时使用本地质量基线并记录“降级”；公开接口、迁移、并发、安全或高风险架构缺少必要能力时返回 Design 或 Plan。

## TASK 质量 Gate

- 以 `quality-principles.md` 审查真实增量代码、调用链、测试和配置/Schema 证据。
- 生产代码 TASK 完成后必须完成适用的 `clean-code-guard` 和专项审查，并修复契约内问题。
- 全部 TASK 完成后再做一次跨 TASK 组合检查，处理累计职责、重复知识、接口膨胀和依赖方向问题。
- 未修改且无本次增量因果证据的存量问题只记录，不纳入本次门禁。

## 验证 Gate

- 基线失败时不修改生产代码。
- TASK 必须有受影响范围编译、相关测试和适用覆盖率证据；验证失败按实现、环境或上游契约归因处理。
- 增量覆盖率的阈值、中文状态和例外规则以 `SKILL.md` 的独立验证章节为准。
- 测试、覆盖率或质量验证失败时不能将最终状态写为“完成”，除非存在明确例外依据。
