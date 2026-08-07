---
name: pretty-java-spring-core
description: Use when one of the four Pretty Java/Spring workflow skills needs shared document contracts, cross-stage consistency rules, quality-skill routing, or new-code coverage tooling. Do not use for application work outside the Pretty workflow.
---

# Pretty Java/Spring 共享核心

## 核心原则

保持 PRD、Design、Plan 与 Execution 简单、一致且可供人 Review。只维护文档合同和确定性工具；不要引入审计、审批证据、哈希链、提交状态机或固定架构形式。

## 使用方式

1. 完整读取 [references/workflow-contract.md](references/workflow-contract.md)。
2. 只加载当前阶段的模板：
   - PRD：[assets/templates/prd.md](assets/templates/prd.md)
   - Design：[assets/templates/design.md](assets/templates/design.md)
   - Plan：[assets/templates/plan.md](assets/templates/plan.md)
   - Execution：[assets/templates/execution.md](assets/templates/execution.md)
3. Design、Plan 或 Executing 涉及 Java/Spring 工程判断时，读取 [references/java-spring-quality.md](references/java-spring-quality.md)。
4. 生成中文文档；代码标识、路径、命令、协议字段和 Skill 名称保留原文。
5. 替换模板中的全部占位内容后再运行校验器。

## 共享合同

- 固定目录：`docs/pretty/<topic>/`，其中 `<topic>` 使用小写 kebab-case。
- 固定文件：`prd.md`、`design.md`、`plan.md`、`execution.md`。
- 使用 `REQ-<nnn>`、`AC-<nnn>`、`DEC-<nnn>`、`TASK-<nnn>` 建立轻量追溯。
- 每个阶段完成后只请求一次人工 Review；一句确认即可，不记录批准证据。
- 下游发现上游错误时，停止当前阶段，回到最早受影响阶段，再顺序刷新下游文档。
- 文档按复杂度缩放；只保留固定核心章节，专项内容按场景加入。
- 不得残留 `TODO`、`TBD`、`FIXME`、待定或其他占位内容。

## 确定性工具

按当前阶段验证文档链：

```bash
python3 <core-skill-dir>/scripts/validate-pretty-docs.py \
  docs/pretty/<topic> --through <prd|design|plan|execution>
```

生成 JaCoCo XML，不修改目标项目构建文件：

```bash
<core-skill-dir>/scripts/run-coverage.sh --project-dir <repo-root>
```

检查本次新增生产 Java 代码：

```bash
python3 <core-skill-dir>/scripts/check-new-code-coverage.py \
  --repo <repo-root> --base <execution-start-head> \
  --report <jacoco.xml> --line-threshold 90 --branch-threshold 80
```

覆盖率脚本只统计 `src/main/java` 中相对基线新增的可执行行与分支。未触碰历史代码不进入分母；修改遗留行为仍须有针对性回归测试。

## 红线

- 不用机械校验器判断需求、架构或代码质量。
- 不把所有质量 Skill 无条件串行调用。
- 不强制 DDD、六边形架构、设计模式或无现实调用方的抽象。
- 覆盖率运行器不得修改项目 `pom.xml` 或 Gradle 文件。业务实现本身确需依赖或构建变更时，仍可由 Design 与 Plan 明确纳入范围并正常实施。
- 不自动执行 `git add`、`commit`、`push`、merge 或创建 MR。
