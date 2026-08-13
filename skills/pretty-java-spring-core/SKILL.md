---
name: pretty-java-spring-core
description: Use when a Pretty Java/Spring PRD, Design, Plan, or Execution stage skill needs the shared document contract, templates, validation rules, quality routing, or coverage tools.
---

# Pretty Java/Spring 共享核心

## 目标

为四阶段 Skill 提供唯一共享合同和确定性工具。阶段 Skill 负责流程；本 Skill 不直接代替任何阶段写文档或实施代码。

## 使用方式

1. 完整读取 [references/workflow-contract.md](references/workflow-contract.md)。
2. 只加载当前阶段模板：
   - PRD：[assets/templates/prd.md](assets/templates/prd.md)
   - Design：[assets/templates/design.md](assets/templates/design.md)
   - Plan：[assets/templates/plan.md](assets/templates/plan.md)
   - Execution：[assets/templates/execution.md](assets/templates/execution.md)
3. Design、Plan 或 Execution 涉及 Java/Spring 判断时，读取 [references/java-spring-quality.md](references/java-spring-quality.md)。
4. 使用中文撰写文档；代码标识、路径、命令、协议字段和 Skill 名称保留原文。
5. 删除模板中不适用的条件块，替换全部占位内容，再运行校验器。

## 固定合同

- 标准目录是 `docs/pretty/<topic>/`，`<topic>` 使用小写 kebab-case。
- 标准文件是 `prd.md`、`design.md`、`plan.md`、`execution.md`。
- 使用 `REQ-<nnn>`、`AC-<nnn>`、`DEC-<nnn>`、`TASK-<nnn>` 追溯。
- PRD、Design、Plan 分别经用户批准后进入下一阶段；Execution 自动审计后直接交付。
- 文档按复杂度缩放；固定章节必须存在，内容可以很短，不制造空表、虚假决策或形式化“无影响”。
- 不保留 `TODO`、`TBD`、`FIXME`、待定、个人绝对路径或其他占位内容。

## 工具

校验标准文档链：

```bash
python3 <core-skill-dir>/scripts/validate-pretty-docs.py \
  docs/pretty/<topic> --through <prd|design|plan|execution>
```

生成 JaCoCo XML，不修改目标项目构建文件：

```bash
<core-skill-dir>/scripts/run-coverage.sh --project-dir <repo-root>
```

检查相对基线新增的生产 Java 代码：

```bash
python3 <core-skill-dir>/scripts/check-new-code-coverage.py \
  --repo <repo-root> --base <execution-start-head> \
  --report <jacoco.xml> --file <plan-owned-production-file> \
  --line-threshold <policy-line-threshold> \
  --branch-threshold <policy-branch-threshold>
```

覆盖率工具只机械统计 `src/main/java` 中相对基线新增的可执行行与分支。修改既有行为由针对性 UT 证明，不虚构修改行覆盖率。

## 红线

- 不用校验器判断需求、架构、代码质量或 TDD 真实性。
- 不无条件调用全部质量 Skill，不强制固定架构或无现实用途抽象。
- 不用非 UT 测试、外部环境或独立 Reviewer 作为 Pretty 完成门禁。
- 不为覆盖率采集改写项目构建文件。
- 不自动执行 `git add`、`commit`、`push`、merge、创建 MR 或发布。
