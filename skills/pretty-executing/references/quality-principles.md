# Java 执行质量补充

本文件只补充 `clean-code-guard` 没有覆盖的执行合同、Java/Spring 语义、运行观测和行为测试要求，
不复述或覆盖其命名、函数、注释、SOLID、DRY、KISS、YAGNI 及 AI 代码失败模式规则。
机械规则及默认覆盖率阈值以 `../scripts/quality_registry.py` 为机器来源。

## 受影响链路与合同归属

已批准 Design 或 Plan 提供有效锚点时直接采用其链路；只有 Prompt-only 或锚点失效时才定向确认：

```text
入口 → caller → callee → Adapter → 持久化或外部系统
```

- 修改范围止于真实受影响链路，并确认状态迁移、消费者、注册点，以及事务、并发、幂等、安全和兼容边界。
- 每项稳定的领域规则、状态迁移和失败分类只有一个业务所有者；调用方不得重新解释该合同。
- 需要改变外部结果、公共接口、数据所有权或依赖方向时，返回上游合同确认。
- 真实仓库用于确认签名、依赖 API、项目惯例和可复用组件，不能代替 Design、Plan 或 Prompt
  决定业务语义。

## Java/Spring 合同语义

### 规范化、可空性与字段选择

- 外部文本只有在协议或 Schema 明确要求时，才在首次接收它的边界完成 `trim`、大小写折叠或默认值转换。
  已可信的内部值、持久化值、ID 和 Code 不再执行 `hasText`、`trim`、大小写转换或空值兜底。
- 领域类型、协议类型或兼容 Adapter 可以拥有合同明确的转换；Helper 名称不能证明转换责任，
  必须根据输入来源、调用链和边界合同判断。
- 备用字段选择必须由 Design、外部协议或 Schema 明确字段优先级、等价性和缺失语义；不能用另一字段
  掩盖必填值缺失或数据损坏。
- `null` 只用于框架、外部协议或遗留签名明确声明的可空合同，并通过注解或测试固定；查询未命中、
  数据损坏和外部失败不得共享同一个空值语义。

### 结果、失败与协议映射

- 查询未命中、数据损坏、非法外部输入、配置或依赖缺失及外部故障必须具有可区分的结果或异常语义。
- 异常在边界映射时保留 cause；不解析异常消息决定控制流。
- 外部状态码只在 Adapter 映射一次，不以裸 `int`、`String` 或 `boolean` 跨层分派业务行为。
- `success/code/message/data` 一类协议响应壳只留在 Adapter；业务 Module 返回领域结果。
- 精度、长度、格式、可空性和集合语义必须与真实 Schema 或外部协议一致。

## 日志、时间与运行观测

- 日志只服务故障定位、运营或审计。一次失败由终止其传播或完成边界映射的位置记录一次，继续抛出的
  中间层不重复记录。
- 记录必要的结构化字段和完整异常，不序列化整个请求或响应，不记录凭证、认证头、完整载荷或敏感数据。
  只有 Prompt、Design 或项目现有观测合同要求时才新增日志。
- 耗时观测复用项目已有 tracing、metrics、AOP 或统一埋点，不使用
  `System.currentTimeMillis()`、`System.nanoTime()` 或局部 duration 变量生成日志。
- 业务时间使用注入的 `Clock` 或项目已有时间抽象。

## 机械门禁边界

机械门禁只保留无需理解业务上下文即可判定的 Java/Spring 交付错误：

- `LABELED-CONTINUE`
- `WHOLE-OBJECT-LOGGING`
- `SENSITIVE-LOGGING`
- `MANUAL-DURATION-LOGGING`

门禁 finding 均为 `error`，发现即失败。通用可读性、异常处理、依赖注入和复杂度由
`clean-code-guard` 判断；测试禁用由测试守卫判断；import 风格交给项目既有工具，不再增加正则式
质量要求。

## 质量路由

`clean-code-guard` 是非平凡生产代码合并 Review 的通用基线。路由器只按实际增量选择它未覆盖的专项
能力，不为同一问题加载另一套通用 Clean Code、SOLID、DRY、KISS 或 YAGNI 审查：

| 事实或风险 | 精确 Skill | 允许用途 |
| --- | --- | --- |
| Interface、Seam、Depth、Locality、跨模块规则归属 | `$codebase-design` | 受影响链路和深模块边界 |
| primitive obsession、值对象、类型层级、签名混淆 | `$122-java-type-design` | Java 类型与签名设计 |
| 并发、事务、资源、响应式链路或外部依赖 API 风险 | `$java-code-review` | Java/Spring 运行时专项检查 |
| 逻辑行为、测试 seam、行为断言或边界替身 | `$tdd` | 行为测试设计 |

所有命中路由与 `clean-code-guard` 在一次合并 Review 中执行；路由不得扩大 Design、Plan 或 Prompt
确定的影响范围，也不得把相邻实现直接当作业务合同。

## 行为测试与验证

测试通过执行合同批准的公共入口观察业务结果、状态、异常或完整边界请求。只替换数据库、网络、
时间和随机等系统边界；不 mock 自有内部协作者，不测试 private 方法，不复制生产算法生成期望值，
不以调用次数代替主要行为证据。

不得在 `@Disabled`、`@Ignore`、元注解或条件禁用范围新增业务测试，也不得通过构建参数、过滤器
或测试发现配置跳过测试。
