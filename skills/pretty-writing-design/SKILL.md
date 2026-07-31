---
name: pretty-writing-design
description: Use when creating or substantively revising a technical design from approved input, or mechanically reviewing an existing Pretty Design before implementation planning.
---

# 编写高质量设计

## 概述

将已批准需求转化为一份基于仓库证据、经过方案权衡和用户批准的中文 Design；也可在不改变技术语义时修复既有 Design 的机械合同。先判定分支，再执行对应门禁。

新建 Design，或改变架构、职责、契约、数据、一致性、兼容性、测试策略与风险处置时，**必需子 Skill：** 使用 `superpowers:brainstorming` 完成方案比较、分节呈现和整体批准。

## 1. 校验输入

业务功能、业务规则或跨系统能力必须以已批准且通过门禁的 PRD 为输入；缺少 PRD 时停止并路由到 `pretty-writing-prd`。

以下情况可使用经用户批准的替代输入：

- 纯技术重构、性能治理或基础设施调整：问题陈述、范围、非目标和可验证成功标准。
- Bug 修复：复现条件、期望行为、根因分析和回归边界。

Design 不得补写或改变需求。输入存在矛盾、关键缺口或不可实现约束时，返回需求阶段澄清。

先判定工作分支：

- **机械审查：** 只调整路径、章节顺序、固定字段、中文格式或占位符，保持全部设计决策与批准记录不变。读取文档合同后直接修订、校验并请求文件复审。
- **新建或实质修订：** 新建设计，或改变任何技术决策、边界、风险及验证策略。完整执行后续探索、方案和批准步骤。

机械审查中发现语义缺陷时停止，说明影响并切换到实质修订分支。

## 2. 加载约束与仓库证据

宣布正在使用 `pretty-writing-design`。仓库包含 `.trellis/` 时，**必需子 Skill：** 使用 `before-dev`。

建立有边界的证据清单，覆盖入口与调用方、应用编排、领域模型与端口、持久化、外部适配、API/事件/schema 契约、测试缝、配置、兼容性和运维影响。

对每个清单项记录仓库来源、已批准输入或明确阻塞结论。独立证据可并行查询；清单全部闭环后停止广泛浏览。缺少关键事实时只询问一个聚焦问题，不得根据文件名、旧文档或架构印象虚构能力。

## 3. 审计未决问题并条件执行 grilling

每次都区分仓库事实、已批准需求、已批准设计决策和未决设计问题，并记录审计结论。

以下任一条件成立时，**必需子 Skill：** 使用 `grilling`：

- 用户明确要求 `grill-me` 或压力测试设计；
- 存在会改变架构、契约、数据所有权或一致性语义的未决项；
- PRD、领域语言、ADR 或仓库事实相互冲突；
- 关键边界场景仍可被多种方式解释。

`grilling` 一次只问一个决策并给出推荐答案，只负责达成共同理解，不生成 Design。没有未决项时记录“未决设计问题：无”及证据，不重复盘问已批准需求。

涉及领域术语、状态、不变量、聚合职责、业务身份或边界变化时，**必需子 Skill：** 使用 `domain-modeling`，即时更新 `CONTEXT.md`；只在难以逆转、缺少背景会令人困惑且存在真实权衡时创建 ADR。

## 4. 在 brainstorming 中生成并审查实质设计

新建或实质修订分支调用 `superpowers:brainstorming`，复用已有证据，提出两个到三个方案，说明权衡和推荐项，分节呈现设计并逐节批准，最后获得整体设计批准。机械审查分支不制造虚假的技术方案或批准。

根据证据确定并实际使用适用 Skill：

- Bug 或异常行为：`superpowers:systematic-debugging`。
- Java 对象职责变化：`121-java-object-oriented-design`。
- Java 类型、DTO、Entity、VO、PO、枚举或边界变化：`122-java-type-design`。
- 端口、服务、依赖方向或职责拆分变化：`solid-principles`。
- 领域术语、状态、不变量或聚合变化：`domain-modeling` 和 `solid-principles`。
- 跨层或跨模块设计：读取项目跨层思考规范。
- 行为保持型重构：`refactor`。

完整读取每个被触发 Skill，在候选方案比较和章节批准前应用其检查表并修正设计，直至无阻塞发现。不得只列 Skill 名称或推迟到 Plan。

Design 必须包含：

```markdown
## 设计生成质量审查

**实际使用的设计 Skill：**
- `<skill>` — <触发证据与审查范围>

**质量发现与设计修正：**
- <具体发现和修正，或基于已审查证据说明无阻塞问题>
```

新建或实质修订分支中，用户零散确认不能代替整体批准。实质修改已批准章节后，重新批准受影响章节和整体设计。整体批准前不得写正式 Design 文件。

涉及页面布局、交互流程、复杂拓扑或视觉比较时，按 brainstorming 规则单独询问是否使用可视化伴侣；纯文本决策不主动启用。视觉结果必须转写为文档中的明确规则和契约。

## 5. 覆盖 brainstorming 默认终态

新建或实质修订分支整体批准后写本地 Design；机械审查分支沿用既有批准并直接修订原文件。产出阶段遵循以下终态；调用过 brainstorming 时这些规则覆盖其默认终态：

- 不自动提交 Git；
- 不自动调用 `superpowers:writing-plans` 或 `pretty-writing-plan`；
- 不发布外部 Issue；
- 先执行机械和语义质量门禁；
- 请求用户复审本地文件并停止；
- 用户后续明确要求 Plan 时，作为独立请求交由 `pretty-writing-plan`。

## 6. 发布唯一中文 Design

唯一权威文档写入：

```text
docs/pretty/<topic>/YYYY-MM-DD-<topic>-design.md
```

`<topic>` 必须沿用已批准 PRD 的小写 kebab-case 主题，目录名必须与文件名中的 `<topic>` 完全一致。日期使用 Design 首次创建日期，后续修订不得改名。使用已批准替代输入时，先确定稳定主题，并在后续 Plan 和 Execution Report 中沿用同一主题目录。

同一主题已有权威 Design 时更新原文件，不创建第二份。只有主题、业务边界或独立交付单元确实不同才创建新文件。未经用户明确要求，不提交、推送或发布。

标题、章节、正文、方案权衡和测试说明使用中文；代码标识、协议字段、路径和技术名称可保留英文。章节不适用时写明“不适用”及理由，不得删除章节或留下占位符。

起草或机械修订前，完整读取 [references/quality-gates.md](references/quality-gates.md) 的“文档合同”，按其唯一章节顺序和追溯表结构生成。该 reference 是固定文档结构的单一真相源。

## 7. 测试与覆盖率设计

完整读取 [references/quality-gates.md](references/quality-gates.md) 的“测试与覆盖率合同”。Design 定义测试分层、行为矩阵、统计与排除原则；具体测试文件、代码、命令、报告位置和逐项排除对象由 Plan 基于仓库证据确定。

## 8. 执行质量门禁

完整读取 [references/quality-gates.md](references/quality-gates.md)，运行：

```bash
bash <skill-dir>/scripts/validate-design.sh <design-file>
```

机械校验不能批准架构。脚本通过后继续审查需求覆盖、仓库证据、方案权衡、领域与分层、边界契约、一致性、兼容性、可测试性、覆盖率策略、范围和批准记录。任何失败都必须修复并重新运行对应门禁。

## 9. 停在文件复审门禁

请求用户复审已写入的 Design。用户要求修改时，修订、重新执行机械与语义门禁，并重新获得受影响批准。

用户批准文件后停止。不得生成实施计划或修改生产代码；后续明确要求计划时使用 `pretty-writing-plan`。

## 危险信号

- 没有批准输入就开始技术设计。
- 把改变设计决策的修订伪装成机械审查。
- 把 grilling 当成自动文档生成器。
- 重复询问 PRD 已批准的问题。
- 只调用 brainstorming，跳过项目质量包装。
- 方案比较、分节批准或整体批准缺失。
- 用旧文档或文件名推测当前契约。
- 声称使用质量 Skill 却没有记录发现和修正。
- 把测试命令、完整代码或实施任务提前塞进 Design。
- 机械校验通过后跳过语义审查。
- 自动提交、自动生成 Plan 或创建第二份 Design。

出现任一危险信号时停止、修正并重新执行门禁。
