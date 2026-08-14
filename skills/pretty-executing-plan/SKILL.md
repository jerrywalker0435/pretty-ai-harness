---
name: pretty-executing-plan
description: Use when implementing or resuming a Java/Spring feature, bug fix, or refactor described by a Pretty plan.md or a direct user request.
---

# 执行 Java/Spring Plan

## 目标

按 Plan 实施改动，保持用户已有内容和既有外部行为；执行过程中发现方案或范围需要变化时，先说明再调整。

**REQUIRED SUB-SKILL：** 使用 `pretty-java-spring-core` 的共享约定、Execution 模板和 Java/Spring 质量参考。本 Skill 负责实施阶段的工作方式。

## 工作流

### 1. 读取输入并检查工作区

宣布使用 `pretty-executing-plan`，读取可用的 `prd.md`、`design.md`、`plan.md`、领域上下文和仓库规则。缺失或不可执行时说明问题；不改写上游文档。

开始前查看工作区状态，保留用户原有改动；不自动 stash、reset、rebase、覆盖文件或执行 Git 发布动作。同一位置无法安全区分时停止并说明。

### 2. 按步骤实施

按 Plan 的自然语言步骤推进，优先完成能独立理解的改动。生产代码写入前使用 `clean-code-guard`；对象职责、类型、依赖方向、模式或行为保持整理出现相应风险时，按共享约定读取专项 Skill。

每次修改后重新阅读受影响代码，保持职责清晰、规则不重复、依赖方向一致。发现用户目标、技术方案或实施范围发生变化时，暂停当前修改并返回相应阶段。

### 3. 写简短结果

需要留下执行文档时，使用 `docs/pretty/<topic>/execution.md`，只记录实际改动、主要落点和需要用户知道的备注；不复制 Plan，也不维护过程日志。无需记录时可以不创建该文件。

## 红线

- 不把未确定的方案擅自扩展成新需求。
- 不用仓库既有坏样例掩盖职责、异常、安全或兼容问题。
- 不在没有用户授权时执行 `git add`、commit、push、创建 MR、合并或发布。
