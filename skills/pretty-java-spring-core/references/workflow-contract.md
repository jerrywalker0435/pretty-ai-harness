# Pretty 四阶段合同

## 目录

- [共同规则](#共同规则)
- [领域模型一致性](#领域模型一致性)
- [阶段合同](#阶段合同)
- [问题与回退](#问题与回退)
- [质量 Skill 路由](#质量-skill-路由)
- [依赖缺失](#依赖缺失)

## 共同规则

四阶段服务 Java/Spring 项目，并分别产出供人 Review 的 Markdown。Git 历史负责版本记录；文档中不维护审计元数据。

除 PRD 评审模式外，每个阶段：

1. 读取所有已有上游文档和足够的仓库事实。
2. 只询问阻塞决策，一次一个，并给出推荐答案。
3. 生成或更新当前阶段唯一文档。
4. 运行共享机械校验，再执行当前阶段的语义质量检查。
5. 请求一次人工 Review，然后停止。

文档核心章节固定；事务、并发、缓存、安全、消息、数据库迁移等专项章节只在相关时加入。不适用的专项章节直接省略。

用户只要求评估现有 PRD 时，可以进入评审模式（不修改文件）：读取任意路径的 PRD 与必要上下文，在对话中报告语义就绪度并停止，不创建或更新阶段文档。只有标准 `docs/pretty/<topic>/prd.md` 才运行完整文档链校验；非标准路径不拒绝评审，也不自动移动文件。

## 领域模型一致性

四阶段都消费既有领域语言：根目录存在 `CONTEXT-MAP.md` 时，先确定本次变化涉及的上下文并读取其指向的 `CONTEXT.md`；否则读取根目录已有的 `CONTEXT.md`。文件不存在不默认创建，也不构成阻塞。仅仅读取词汇不算调用 `domain-modeling`。

`domain-modeling` 在 PRD 与 Design 中条件触发、触发后强制：

- **PRD：** 新增、歧义或冲突的核心术语、业务身份、生命周期、状态、不变量、归属或关系会影响需求时使用。用具体场景澄清后立即更新对应 `CONTEXT.md`；PRD 阶段只维护领域词汇，不创建 ADR。
- **Design：** 新增或改变实体、值对象、业务身份、状态流转、不变量、聚合边界、数据所有权、领域上下文关系或领域事件时使用。结果写入对应 `CONTEXT.md` 和 `DEC`；上下文映射关系发生变化时同步 `CONTEXT-MAP.md`。只有难以撤销、缺少背景会令人困惑且存在真实权衡时才创建 ADR。若结果改变外部行为、`REQ` 或 `AC`，先返回 PRD。
- **Plan 与 Executing：** 只检查命名、身份、状态、不变量、所有权和边界是否与上游及领域文档一致，不调用 `domain-modeling`，不得更新 `CONTEXT.md`、`CONTEXT-MAP.md` 或 ADR。当前阶段表达错误且上游语义明确时直接修正；需要改变需求时返回 PRD，需要改变领域设计时返回 Design。

仓库证据已唯一决定时直接同步，不重复询问。存在会改变业务身份、生命周期、不变量、所有权、上下文边界或验收行为的真实分歧时，先使用 `grilling` 一次解决一个决策，再由 `domain-modeling` 更新领域语言。

PRD 或 Design 的一次阶段 Review 同时覆盖本阶段修改的 `CONTEXT.md`、`CONTEXT-MAP.md` 和 ADR，不增加 Skill 调用日志或额外 Review。若触发后缺少 `domain-modeling`，停止当前阶段并说明依赖；未触发时不要求加载该 Skill。

PRD 评审模式（不修改文件）发现领域歧义时，不修改文件，只报告会触发 `domain-modeling` 的问题及下游影响；用户明确进入创建或修订模式后，才按上述触发规则调用并更新领域语言。

## 阶段合同

### PRD

- 输入：用户目标、仓库中的现有行为与约束。
- 决定：问题、目标、非目标、用户场景、需求和可验证验收标准。
- 不决定：类、方法、数据库 schema、事务边界或实现模式。
- 输出：`prd.md`，定义 `REQ` 与 `AC`。
- 评审模式：输出阻塞问题、建议改进、下游影响和是否可进入 Design，不修改文件或生成评审文档。

### Design

- 输入：已 Review 的 `prd.md` 和仓库结构。
- 决定：技术方案及权衡、模块职责、接口、数据流、错误行为、事务/一致性、测试策略和风险。
- 不决定：逐步实施顺序或完整实现。
- 输出：`design.md`，定义 `DEC` 并覆盖全部 `REQ/AC`。

### Plan

- 输入：已 Review 的 `prd.md`、`design.md` 和真实源码/API。
- 决定：实施任务、准确文件、关键代码、完整测试代码、增量覆盖率合同和验证命令。
- 展示：公共接口、核心业务方法、异常/事务边界和测试代码；机械修改使用逐项变更表。
- 输出：`plan.md`，定义 `TASK` 并覆盖全部 `REQ/AC/DEC`。
- 构建文件不是默认禁区；业务目标确需依赖、插件或构建调整时，把它作为普通受 Review 变更写入任务。只有 Harness 的临时覆盖率采集不得改写项目构建文件。

### Executing

- 输入：已 Review 的 `plan.md` 及其上游文档。
- 执行：基线验证、分类式 TDD、增量覆盖率、一次最终独立 Review 和最终验证。
- 输出：代码变更与 `execution.md`；不自动提交 Git。

## 问题与回退

只有“存在真实选项分歧、影响重大或难以撤销、且仓库证据无法决定”时，才属于高影响分歧。典型影响包括：

- 用户行为或验收标准；
- 公共 API、事件、schema 或兼容性；
- 数据所有权、事务、一致性、幂等或并发；
- 权限、安全、隐私或合规；
- 模块边界、依赖方向或核心领域模型；
- 性能目标、可用性或重大实施范围。

高影响分歧使用 `grilling`；其他问题采用仓库惯例和最简单可行方案。下游发现错误时返回最早受影响阶段，不创建跨层修订包，不沿用失效的下游内容。

## 质量 Skill 路由

| 场景 | 使用 |
|---|---|
| Java 对象职责、封装、组合/继承 | `121-java-object-oriented-design` |
| 值对象、泛型、类型层次、金额类型或 primitive obsession | `122-java-type-design` |
| 服务职责、端口、依赖方向、扩展点 | `solid-principles` |
| 遗留结构调整且保持行为 | `refactor` |
| PRD/Design 改变领域术语、身份、生命周期、不变量、归属或边界 | `domain-modeling` |
| 公共 API/模块接口存在多种合理形状 | `design-an-interface` |
| 已证明存在构造、替换、通知或适配变化轴 | `design-patterns` |
| Spring 测试选型与实现 | `springboot-tdd` |
| 任意生产行为变更 | `superpowers:test-driven-development` |
| 完成后的通用代码质量 | `clean-code-guard` |
| 完成后的 Java 专项 Review | `java-code-review` |
| 声明完成前 | `superpowers:verification-before-completion` |

`design-an-interface` 只在接口选择确有价值时使用，并遵循其多方案流程。`design-patterns` 必须先证明直接实现不足，禁止为了模式而模式。

## 依赖缺失

以下核心门禁缺失时停止并说明安装需求：

- `121-java-object-oriented-design`
- `superpowers:test-driven-development`
- `clean-code-guard`
- `java-code-review`
- `superpowers:verification-before-completion`

`domain-modeling` 是条件必需能力：PRD 或 Design 命中领域模型触发条件时缺失则停止；未命中时不加载。

条件增强 Skill 缺失时继续，说明未执行的专项检查：`122-java-type-design`、`solid-principles`、`refactor`、`design-an-interface`、`design-patterns`、`springboot-tdd`。
