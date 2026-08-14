# Pretty 四阶段共享约定

本文件只定义四个阶段共用的边界和术语；具体操作顺序由对应阶段 Skill 决定。

## 阶段边界

```text
[PRD：外部结果] -> [Design：技术方案] -> [Plan：实施步骤] -> [Execution：代码改动]
```

- PRD 说明问题、目标、范围、场景和业务规则，不选择技术实现。
- Design 说明职责、依赖方向、跨边界接口、数据与一致性、兼容策略和主要权衡。
- Plan 根据用户目标、可用设计和真实源码拆分实施步骤，不修改代码。
- Execution 按实施步骤修改代码和配置，保持用户已有内容。
- 四个阶段可以按需单独使用；已有文档只是背景输入，不要求固定编号、逐项映射或额外附录。

## 共同写作规则

- 制品默认放在 `docs/pretty/<topic>/`，`<topic>` 使用小写 kebab-case。
- 只创建实际需要的 `prd.md`、`design.md`、`plan.md` 和 `execution.md`。
- 使用中文；代码标识、路径、命令、协议字段和 Skill 名称保留原文。
- 删除不适用的条件块，不保留 `TODO`、`TBD`、`FIXME`、待定或占位内容。
- 团队可访问的仓库路径、类型名、配置键和稳定文档可以写入制品；不写个人绝对路径或私有资料。
- 只读 Review 只读取文档和必要上下文，不修改、移动或复制文件，不生成其他阶段制品。

## 澄清与领域语言

PRD 与 Design 先调查用户意图、仓库、协议、领域文档、配置和相邻行为。只有存在多个真实答案、答案会改变结果且仓库无法裁决时才使用 `grilling`；一次处理一个问题并给出推荐方向。

- 领域术语、身份、生命周期、状态、不变量、归属或关系发生变化时，使用 `domain-modeling`。
- 领域文档不存在时不默认创建；只在确有领域语言变化时更新。
- Plan 与 Execution 使用已有领域语言，不擅自重新定义业务含义。

## Java/Spring 质量路由

按实际问题读取最小的专项 Skill，把判断直接落实到当前阶段内容或代码：

| 阶段 | 实际问题 | 可用 Skill |
| --- | --- | --- |
| Design / Plan / Execution | 对象职责、协作、封装、聚合或继承变化 | `121-java-object-oriented-design` |
| Design / Plan | 值对象、泛型、类型层次或金额类型 | `122-java-type-design` |
| Design / Plan / Execution | 服务职责、端口、依赖方向或扩展点 | `solid-principles` |
| Design / Plan | 模块接口、seam 或 adapter 需要设计 | `codebase-design` |
| Design / Plan | 存在明确的构造、替换、通知或适配变化轴 | `design-patterns` |
| Execution | 行为保持整理 | `refactor` |
| Plan / Execution | 编写或修改生产代码 | `clean-code-guard` |
| Execution | Java 代码出现异常、并发、资源、性能或 API 兼容问题 | `java-code-review` |

## Git 边界

工作区可以不洁净，但必须保留用户改动；同一位置无法安全区分且有覆盖风险时停止。commit、push、创建 MR、合并和发布均需用户另行授权。
