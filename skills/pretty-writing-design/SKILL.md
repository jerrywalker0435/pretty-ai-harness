---
name: pretty-writing-design
description: Use when creating, revising, or reviewing a Pretty design.md for a Java/Spring change that needs a technical design.
---

# 编写 Java/Spring Design

## 目标

把用户目标、可用 PRD 和真实仓库约束整理成简洁的技术设计。Design 先呈现方案、流程、职责和边界，再说明关键权衡；不展开逐文件实施或完整代码。

**REQUIRED SUB-SKILL：** 使用 `pretty-java-spring-core` 的共享约定、Design 模板和 Java/Spring 质量参考。本 Skill 负责 Design 阶段的工作方式。

## 工作流

### 1. 确认模式与输入

宣布使用 `pretty-writing-design`。用户要求评估、检查或 Review 时只读处理；用户要求创建或修订时进入写作模式。

写作模式优先读取 `docs/pretty/<topic>/prd.md`、用户意图、必要领域上下文和真实仓库事实。唯一输出为 `docs/pretty/<topic>/design.md`，已有文件原地修订。若外部结果仍不清楚，先回到需求澄清。

### 2. 执行只读评审

读取用户给出的 Design 以及支撑理解所需的文档、源码、配置和领域上下文；不修改、移动或复制文件，不更新领域文档，不生成 Plan。

输出阻塞问题、重要改进和是否适合继续拆实施步骤，然后停止。结论应使用自然语言，避免把格式化编号当作论证主体。

### 3. 建立事实并关闭技术未知

检查入口、调用关系、职责、领域对象、持久化、外部合同、配置和依赖方向，区分用户目标、仓库事实和设计选择。个人绝对路径或私有资料不进入文档。

事实无法裁决且会改变技术方案时，使用 `grilling` 一次处理一个问题；领域模型变化时使用 `domain-modeling`。按照共享约定只读取实际触发的质量 Skill，把结论直接写入设计，不记录调用清单。

### 4. 编写 Design

使用共享模板，按需要说明：

- 设计结论和方案全景；
- 主流程、状态、职责、依赖方向和跨边界数据；
- 关键选择、未采用方案、代价和重新考虑条件；
- 输入输出、错误、一致性、兼容、事务、并发和安全边界。

Mermaid、Markdown 表格、伪码或 ASCII 只在确实能降低理解成本时使用；图表使用业务语义、类型名和模块短名，不堆叠路径或长代码。

### 5. 收尾

替换全部占位内容，确认方案、职责、接口和边界互相一致。告知文档路径和主要设计结论，请求用户 Review 后停止，不自动进入 Plan。

## 红线

- 不替用户目标决定外部结果。
- 不为展示完整性制造候选方案、接口、图或模式。
- 不把内部实现细节伪装成技术合同。
- 不在只读评审中修改文件。
