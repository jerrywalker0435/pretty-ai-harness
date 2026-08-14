---
name: pretty-writing-plan
description: Use when creating, revising, or reviewing a Pretty plan.md for a Java/Spring change before implementation begins.
---

# 编写 Java/Spring Plan

## 目标

把用户目标、可用设计和真实源码整理成可执行的实施步骤。Plan 只说明怎么改、改动边界和主要依赖，不实施代码。

**REQUIRED SUB-SKILL：** 使用 `pretty-java-spring-core` 的共享约定、Plan 模板和 Java/Spring 质量参考。本 Skill 负责 Plan 阶段的工作方式。

## 工作流

### 1. 确认模式与输入

宣布使用 `pretty-writing-plan`。用户要求评估、检查或 Review 时只读处理；用户要求创建或修订时进入写作模式。

优先读取同目录可用的 `prd.md`、`design.md`、领域上下文、仓库规则、相关源码、调用方和构建配置。缺失或互相矛盾时说明需要补充的内容；仓库事实自行调查。Plan 不修改代码文件，也不生成 Execution。

### 2. 先确定整体职责

在拆分实施步骤前，合并阅读所有拟议变化，先确定最终职责、依赖方向、公共接口和规则归属。同一生产类涉及多个变化时，先检查组合后的形状，避免把不同职责堆在同一个类中。发现需要改变技术方案时回到 Design。

### 3. 编写实施步骤

使用共享模板，以可读的自然语言标题拆分步骤，不使用固定编号。每个步骤说明：

- 要达到的结果和不能改变的既有行为；
- 关键文件、类型或方法（按需列出，不制作完整路径映射表）；
- 生产代码的主要改法、必要的机械变更和依赖调整；
- 会影响其他步骤的共享事实或实现规则。

代码片段只在能澄清非显然的职责或接口时保留，不把 Plan 写成完整补丁。纯文档、配置、迁移、改名或批量机械变更直接描述变更方式。

编写生产代码提案时按实际风险使用 `clean-code-guard`、`121-java-object-oriented-design`、`122-java-type-design`、`solid-principles`、`codebase-design`、`design-patterns`、`java-code-review` 或 `refactor`；不创建能力清单。

### 4. 收尾

替换全部占位内容，确认步骤之间的顺序、职责和改动范围清楚。告知文档路径和主要实施步骤，请求用户 Review 后停止，不自动进入 Execution。

## 红线

- 不虚构源码、API、命令或结果。
- 不把 Plan 写成逐文件完整补丁。
- 不在 Plan 阶段修改代码文件。
- 不以当前仓库的坏样例为理由复制职责、重复规则或不必要的抽象。
