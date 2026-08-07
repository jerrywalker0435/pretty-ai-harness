---
name: pretty-writing-prd
description: Use when creating or revising a Pretty prd.md for a Java/Spring feature, bug fix, or behavior-preserving refactor before technical design begins.
---

# 编写 Java/Spring PRD

## 目标

把用户目标和仓库事实整理成一份简洁、可验证、可供人 Review 的 PRD。PRD 只定义问题、范围、外部可观察行为和验收标准，不提前决定技术实现。

**REQUIRED SUB-SKILL：** 完整读取并使用 `pretty-java-spring-core` 的共享合同与 PRD 模板。本 Skill 是当前阶段的唯一流程控制器；不要再启动第二套创意讨论或文档流程。

## 工作流

### 1. 确认主题与输入

宣布使用 `pretty-writing-prd`。确定小写 kebab-case 的 `<topic>`，并使用唯一文件：

```text
docs/pretty/<topic>/prd.md
```

已有该文件时原地修订，不创建日期版本或第二份 PRD。读取适用的仓库规则、现有入口、可观察行为和测试；根目录存在 `CONTEXT-MAP.md` 时读取相关上下文的 `CONTEXT.md`，否则读取根目录已有的 `CONTEXT.md`。文件不存在不默认创建。只探索足以解释当前需求的范围。

Bug PRD 至少确认复现条件、当前行为、期望行为和回归边界。纯重构 PRD 至少确认当前问题、行为保持约束和可验证成功标准。简单任务的文档可以很短。

### 2. 只解决阻塞决策

区分仓库事实、用户明确要求和仍会改变需求结果的未知项，但不要生成“澄清审计”章节。

- 能从仓库查明的事实自行查明。
- 非阻塞细节采用仓库惯例或最简单可逆选择。
- 新增、歧义或冲突的核心术语、业务身份、生命周期、状态、不变量、归属或关系会影响需求时，**REQUIRED SUB-SKILL：** 使用 `domain-modeling`。用具体场景澄清语言并立即更新对应 `CONTEXT.md`；未触发时只消费既有词汇，不调用该 Skill。
- 存在共享合同定义的高影响分歧时，使用 `grilling`，一次只解决一个决策并给出推荐答案。
- 只有存在真实、结果不同的产品方案时才比较 2–3 个方案；没有分歧时直接起草。

PRD 只维护不含实现细节的领域词汇，不创建 ADR。`domain-modeling` 触发后不可用时停止并说明依赖。不得要求逐节确认、方案审批元数据或其他审计字段。

### 3. 起草 PRD

使用共享 PRD 模板并替换全部占位内容：

- 用 `REQ-001` 起连续编号，每条只表达一个需求或业务规则。
- 用 `AC-001` 起连续编号，每条关联至少一个 `REQ`，并写成可观察、可测试的结果。
- 明确目标与非目标，覆盖主流程、关键边界和失败行为。
- 使用已同步的项目领域语言；将生命周期、不变量和失败结果落实到对应 `REQ/AC`。
- 不写类、方法、模块职责、数据库 schema、事务边界、设计模式、完整代码或实施任务。

### 4. 自审并机械校验

逐项确认：

- 问题、目标、用户场景、需求和验收标准互相一致；
- 每个 `REQ` 都能由一个或多个 `AC` 验收；
- 成功、失败和重要边界均有可验证结果；
- PRD 与相关 `CONTEXT.md` 的术语、身份、状态和不变量一致；
- 没有把实现偏好伪装成需求；
- 没有 `TODO`、`TBD`、`FIXME`、待定或占位内容。

运行：

```bash
python3 <pretty-java-spring-core-dir>/scripts/validate-pretty-docs.py \
  docs/pretty/<topic> --through prd
```

修正所有机械或语义问题后再交付。

### 5. 请求一次 Review 并停止

告知用户 PRD 路径、需求数量、验收标准数量、相关 `CONTEXT.md` 变更和校验结果，请求一次文档 Review，然后停止。该次 Review 同时覆盖 PRD 与本阶段领域词汇变更；不得自动生成 Design、Plan、Issue 或生产代码。

## 红线

- 没有真实分歧仍制造多方案或盘问。
- 使用日期文件名、审批元数据、哈希、指纹或跨阶段修订协议。
- 为了填满模板扩写简单 Bug 或重构。
- 机械校验通过就声称需求语义正确。
- PRD 完成后自动进入下一阶段。
