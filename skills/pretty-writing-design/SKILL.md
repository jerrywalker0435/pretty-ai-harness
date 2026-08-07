---
name: pretty-writing-design
description: Use when a reviewed Pretty PRD for a Java/Spring feature, bug fix, or behavior-preserving refactor needs a technical design before implementation planning.
---

# 编写 Java/Spring Design

## 目标

把已 Review 的 PRD 和真实仓库约束转化为一份可实施、可测试、可供人 Review 的技术设计。Design 决定技术边界与关键权衡，不展开实施步骤或完整代码。

**REQUIRED SUB-SKILL：** 完整读取并使用 `pretty-java-spring-core` 的共享合同、Design 模板和 Java/Spring 质量检查。本 Skill 是当前阶段的唯一流程控制器。

## 工作流

### 1. 校验输入与范围

宣布使用 `pretty-writing-design`。读取：

```text
docs/pretty/<topic>/prd.md
```

确认 PRD 已由用户 Review，且不存在占位内容。缺失、未 Review 或需求错误时，停止并返回 PRD 阶段。根目录存在 `CONTEXT-MAP.md` 时读取相关上下文的 `CONTEXT.md`，否则读取根目录已有的 `CONTEXT.md`。Design 使用同一主题目录和唯一文件：

```text
docs/pretty/<topic>/design.md
```

已有文件时原地修订。简单 Bug 或局部重构可以写得很短，但仍须覆盖所有适用的需求、边界和风险。

### 2. 建立仓库事实

检查与本次变化相关的入口、调用链、模块职责、领域对象、持久化、外部契约、配置和测试缝。只探索足以支持设计决策的范围，并区分仓库事实、PRD 要求和设计选择。

- 能由源码、测试或项目规则决定的事项自行查明。
- 非阻塞细节沿用仓库惯例和最简单可逆方案。
- 存在共享合同定义的高影响分歧时，使用 `grilling`，一次只解决一个决策并给出推荐答案。
- 只有存在真实、结果不同的设计选项时才比较方案；仓库证据已经决定时，直接说明依据。

不得虚构现有能力，也不得为展示完整性而扩展范围。

### 3. 路由 Java/Spring 设计质量

Java 对象职责、封装和协作是默认设计检查，**REQUIRED SUB-SKILL：** 使用 `121-java-object-oriented-design`。再按证据选择增强检查：

| 触发场景 | 使用的 Skill |
|---|---|
| 值对象、泛型、类型层次、金额类型或 primitive obsession | `122-java-type-design` |
| 服务职责、端口、依赖方向或扩展点 | `solid-principles` |
| 保持行为的遗留结构调整 | `refactor` |
| 公共 API 或模块接口有多种合理形状 | `design-an-interface` |
| 已证明确有构造、替换、通知或适配变化轴 | `design-patterns` |
| 共享合同定义的 Design 领域模型变化 | `domain-modeling` |
| Spring 测试层级、JUnit、MockMvc 或 Testcontainers 选择 | `springboot-tdd` |

完整读取实际触发的 Skill，并把发现落实为设计决策。`domain-modeling` 触发后按共享合同同步对应 `CONTEXT.md`、必要的 `CONTEXT-MAP.md` 和 `DEC`；若结果改变外部行为、`REQ` 或 `AC`，停止并返回 PRD。ADR 只按共享合同的三项条件创建；触发后缺少该 Skill 时停止。不要无条件串行调用全部 Skill；接口已由兼容性或项目惯例决定时不制造备选接口，没有现实变化轴时不套设计模式。

### 4. 编写 Design

使用共享 Design 模板，替换全部占位内容：

- 用 `DEC-001` 起连续编号；每个 `DEC` 说明覆盖的 `REQ`、职责边界、接口/数据、错误与一致性。
- 覆盖全部 `REQ` 和 `AC`，保持 PRD 的外部行为不变。
- 明确模块职责、依赖方向、主要数据流、边界契约、失败行为和适用的事务/并发/幂等语义。
- 测试策略把每个 `AC` 映射到合适的单元、slice、集成或契约测试层级。
- 记录实际使用的质量 Skill、重要发现及设计修正；无阻塞问题时明确写出。
- 事务、消息、缓存、安全、迁移等专项内容只在相关时增加三级章节。

Design 可以展示短接口签名或关键伪代码来澄清契约，但不写逐文件任务、完整实现或完整测试代码。

### 5. 自审并机械校验

逐项确认需求追溯、职责内聚、依赖方向、接口最小化、错误语义、数据一致性、可测试性、兼容性、风险与回退互相一致；领域术语、身份、状态、不变量、所有权和边界与相关领域文档一致，并符合共享 Java/Spring 质量检查。机械校验不能证明架构正确。

运行：

```bash
python3 <pretty-java-spring-core-dir>/scripts/validate-pretty-docs.py \
  docs/pretty/<topic> --through design
```

修正所有机械或语义问题后再交付。

### 6. 请求一次 Review 并停止

告知用户 Design 路径、主要 `DEC`、相关 `CONTEXT.md`/`CONTEXT-MAP.md`/ADR 变更、实际使用的质量 Skill 和校验结果，请求一次人工 Review，然后停止。该次 Review 同时覆盖本阶段领域文档变更；不得自动生成 Plan、Issue 或生产代码。

## 红线

- PRD 尚未 Review 就开始设计，或在 Design 中悄悄改变需求。
- 没有真实分歧仍强制多个方案、多个接口或设计模式。
- 只列质量 Skill 名称，却不应用其发现。
- 强制固定架构、无现实调用方的抽象或逐层对象复制。
- 用机械校验结果代替技术判断。
- Design 完成后自动进入下一阶段。
