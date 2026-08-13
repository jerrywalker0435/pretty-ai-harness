---
name: pretty-java-spring-core
description: Use when a Pretty Java/Spring PRD, Design, Plan, or Execution stage skill needs the shared document contract, templates, validation rules, quality routing, or coverage tools.
---

# Pretty Java/Spring 共享核心

本 Skill 只提供共享合同与确定性工具；阶段 Skill 负责本阶段流程。

## 加载顺序

1. 完整读取 [references/workflow-contract.md](references/workflow-contract.md)。
2. 只读取当前阶段模板：
   - PRD：[assets/templates/prd.md](assets/templates/prd.md)
   - Design：[assets/templates/design.md](assets/templates/design.md)
   - Plan：[assets/templates/plan.md](assets/templates/plan.md)
   - Execution：[assets/templates/execution.md](assets/templates/execution.md)
3. Design、Plan 或 Execution 涉及 Java/Spring 判断时，读取 [references/java-spring-quality.md](references/java-spring-quality.md)。
4. 使用中文撰写制品；代码标识、路径、命令、协议字段和 Skill 名称保留原文。
5. 删除不适用的条件块并替换占位内容。

标准目录为 `docs/pretty/<topic>/`，其中 `<topic>` 使用小写 kebab-case；标准文件为 `prd.md`、`design.md`、`plan.md`、`execution.md`。

## 工具入口

校验文档链：

```bash
python3 <core-skill-dir>/scripts/validate-pretty-docs.py \
  docs/pretty/<topic> --through <prd|design|plan|execution>
```

生成 JaCoCo XML：

```bash
<core-skill-dir>/scripts/run-coverage.sh --project-dir <repo-root>
```

检查相对 Execution 起始 HEAD 新增的生产 Java 代码：

```bash
python3 <core-skill-dir>/scripts/check-new-code-coverage.py \
  --repo <repo-root> --base <execution-start-head> \
  --report <jacoco.xml> --file <plan-owned-production-file> \
  --line-threshold <policy-line-threshold> \
  --branch-threshold <policy-branch-threshold>
```

## 工具红线

- 校验器只判断可确定的结构、编号、引用和禁止项，不判断需求、架构、代码质量或 TDD 真实性。
- 覆盖率工具只统计 `src/main/java` 的新增可执行行与分支，不为采集结果改写项目构建文件。
- 不用非 UT、外部环境或独立 Reviewer 作为 Pretty 完成门禁。
- 不自动执行 `git add`、`commit`、`push`、merge、创建 MR 或发布。
