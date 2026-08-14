---
name: pretty-java-spring-core
description: Use when a Pretty Java/Spring stage skill needs shared document conventions, templates, or Java/Spring quality guidance.
---

# Pretty Java/Spring 共享核心

本 Skill 提供四个阶段共用的目录约定、模板和质量参考；各阶段 Skill 自己负责工作方式。

## 加载顺序

1. 读取 [references/workflow-contract.md](references/workflow-contract.md)。任何Java代码编写，优先遵循该质量，而不是参考当前仓库代码。
2. 只读取当前阶段模板：
   - PRD：[assets/templates/prd.md](assets/templates/prd.md)
   - Design：[assets/templates/design.md](assets/templates/design.md)
   - Plan：[assets/templates/plan.md](assets/templates/plan.md)
   - Execution：[assets/templates/execution.md](assets/templates/execution.md)
3. Design、Plan 或 Execution 涉及 Java/Spring 判断时，读取 [references/java-spring-quality.md](references/java-spring-quality.md)。
4. 使用中文撰写制品；代码标识、路径、命令、协议字段和 Skill 名称保留原文。
5. 删除不适用的条件块并替换占位内容。

标准目录为 `docs/pretty/<topic>/`，其中 `<topic>` 使用小写 kebab-case；文件名按需要使用 `prd.md`、`design.md`、`plan.md` 或 `execution.md`。

## 共同边界

- 上一阶段文档存在时作为背景输入；没有时以用户意图和真实仓库事实为准，不为了补齐格式制造文档。
- 只读 Review 不修改、移动或复制文档，不更新领域文档，不生成其他阶段制品。
- 需要修改领域语言时使用 `domain-modeling`；Plan 和 Execution 不擅自更新领域文档。
- 质量 Skill 只按实际问题读取，结论直接落实到当前设计、Plan 或代码，不记录调用清单。
- 保留用户已有改动；不自动执行 `git add`、commit、push、merge、创建 MR 或发布。
