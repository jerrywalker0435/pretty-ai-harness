# Java 质量路由

共享质量基线始终适用，不需要 AI 选择。Quality Resolver 按文件、Symbol、调用链、依赖、Schema 和候选 Diff 等事实累积派生专项风险，不设数量上限；每个风险只有一个语义归属 Skill，不能因“最小路由”遗漏风险，也不能让多个 Skill 重复审查同一问题。

## 引用边界

Pretty Harness 决定阶段、审批、构建范围、证据格式和完成状态。冲突优先级唯一以 [quality-principles.md 的 QP-03](quality-principles.md#qp-03-约定优先) 为准；本文不定义风险路由之外的第二套优先级。本文只规定 Pretty 质量层内部的风险所有权：Resolver 决定必须检查哪些风险和主审者，专项 Skill 只提供适用的语义判断，其具体重构建议位于共享规则之后、仓库惯例之前。专项 Skill 自带命令、报告格式、审批流程和数值阈值不进入 Harness。真实 API、Schema 和依赖版本仍作为不可伪造的事实约束。

本表服务执行实现和最终独立 Reviewer。执行 Writer 在首次编辑前完成合同可执行性预检，最终 Reviewer 使用全部适用风险协议一次审完真实候选，不按风险拆分 Reviewer。

## 风险所有权

下表是 `../scripts/quality_registry.py` 中 `RiskSpec` 的人类可读投影，owner 以注册表为唯一机器来源；一致性检查阻止本文与注册表漂移。

| 风险 ID | 触发事实 | 语义归属 Skill |
| --- | --- | --- |
| `MODULE_BOUNDARY` | Interface、公共验证入口、Depth、Locality、跨模块规则归属 | `codebase-design` |
| `JAVA_OOD` | Java 职责、封装、重复、对象创建、类或方法合同 | `121-java-object-oriented-design` |
| `FOCUSED_SOLID` | 只有一个明确 SOLID 原则需要定向判断 | `solid-principles` |
| `TYPE_DESIGN` | primitive obsession、值对象、类型层级、精度或签名混淆 | `122-java-type-design` |
| `CHANGE_AXIS` | 已存在第二实现或已批准的真实变化轴 | `design-patterns` |
| `JAVA_RUNTIME_RISK` | null、异常、并发、资源、性能或 Java API 风险 | `java-code-review` |
| `BEHAVIOR_TEST` | 行为变化、Bug 修复、公共验证入口、断言或边界替身 | `tdd` |

`JAVA_OOD` 与 `FOCUSED_SOLID` 对同一问题二选一：跨多个 OOD 关注点使用前者，只审一个已证实原则时使用后者。`CHANGE_AXIS` 不能由假想扩展触发。

Execution 对所有非平凡生产代码额外执行一次 `clean-code-guard`，作为 AI 失败模式的固定收尾 Guard，不替代最终独立 Reviewer。

## 路由闭环

1. 生成前由 `scripts/quality_resolver.py` 从执行矩阵和仓库事实派生规则与风险；Writer 只消费结果。
2. Java 生产切片保守命中 `JAVA_OOD`、`JAVA_RUNTIME_RISK` 和 `BEHAVIOR_TEST`，再按观察到的边界、类型和变化轴事实累积其他风险；不确定时取并集。
3. 每项风险必须绑定具体文件、symbol、调用链或合同事实，并使用表中的语义归属；最终仍由同一名独立 Reviewer 汇总结论。
4. 候选出现新文件、Symbol、依赖或边界时增量运行 Resolver；批准合同内用执行编排器 `rebind` 更新矩阵与 Resolver 摘要，改变公共合同时返回上游合同；完整候选冻结前对真实 Diff 复核一次。
5. 最终 Reviewer 检查 Resolver 是否漏掉新事实，但不能删除已派生风险；专项结论落实到职责、签名、异常、类型、测试或配置。

普通专项不可用时，按共享基线完成同一语义检查并记录降级；公开 Interface、迁移、并发、安全或高风险架构缺少必要审查能力时停止并返回上游。
