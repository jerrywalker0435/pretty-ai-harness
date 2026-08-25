# Java 质量路由

共享质量基线始终适用。专项 Skill 按已观察到的风险维度累积选择，不设数量上限；每个风险只有一个主审者，不能因“最小路由”遗漏风险，也不能让多个 Skill 重复审查同一问题。

## 引用边界

Pretty Harness 决定阶段、审批、构建范围、证据格式和完成状态。专项 Skill 只提供适用的语义检查；其自带命令、报告格式、审批流程和数值阈值不进入 Harness。冲突时依次遵守：用户当前要求、批准合同、共享质量基线、本文路由所有权、真实仓库既有惯例、AGENTS、Trellis、专项建议。真实 API、Schema 和依赖版本仍作为不可伪造的事实约束。

## 风险所有权

| 风险 ID | 触发事实 | 主审 Skill |
| --- | --- | --- |
| `MODULE_BOUNDARY` | Interface、公共验证入口、Depth、Locality、跨模块规则归属 | `codebase-design` |
| `JAVA_OOD` | Java 职责、封装、重复、对象创建、类或方法合同 | `121-java-object-oriented-design` |
| `FOCUSED_SOLID` | 只有一个明确 SOLID 原则需要定向判断 | `solid-principles` |
| `TYPE_DESIGN` | primitive obsession、值对象、类型层级、精度或签名混淆 | `122-java-type-design` |
| `CHANGE_AXIS` | 已存在第二实现或已批准的真实变化轴 | `design-patterns` |
| `JAVA_RUNTIME_RISK` | null、异常、并发、资源、性能或 Java API 风险 | `java-code-review` |
| `BEHAVIOR_TEST` | 行为变化、Bug 修复、公共验证入口、断言或边界替身 | `tdd` |

`JAVA_OOD` 与 `FOCUSED_SOLID` 对同一问题二选一：跨多个 OOD 关注点使用前者，只审一个已证实原则时使用后者。`CHANGE_AXIS` 不能由假想扩展触发。

Execution 对所有非平凡生产代码额外执行一次 `clean-code-guard`，作为 AI 失败模式的固定收尾 Guard，不占专项路由名额，也不替代上表主审者。

## 路由闭环

1. 用具体文件、symbol、调用链或合同事实识别风险。
2. 为每个风险选择唯一主审者；Reviewer 再检查是否漏掉风险维度。
3. 把专项结论落实到职责、签名、异常、类型、测试、配置或任务切分。
4. 候选变化出现新风险时增量路由并重新审查。

普通专项不可用时，按共享基线完成同一语义检查并记录降级；公开 Interface、迁移、并发、安全或高风险架构缺少必要审查能力时停止并返回上游。
