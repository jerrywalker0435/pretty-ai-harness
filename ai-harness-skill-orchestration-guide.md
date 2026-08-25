# Pretty AI Harness 三阶段编排指南

## 核心流程

Pretty AI Harness 将 Java/Spring 研发工作组织为：

```text
PRD → Design → Execution
```

三个阶段分别回答“要产生什么业务结果”“系统以什么合同承担结果”“真实实现和证据是什么”。独立实施计划阶段已删除：可执行的结果拆分和变更职责链路进入 Design，精确文件、Symbol 与代码提案由 Execution 的可选 Dry Run 提供。

运行规范以 `skills/` 中各 Skill 的 `SKILL.md` 及其直接引用资源为准；本文只解释编排方式。

## 三个核心 Skill

| Skill | 输入 | 权威产物 | 停止点 |
| --- | --- | --- | --- |
| `pretty-writing-prd` | 用户目标、业务事实、领域上下文 | `docs/pretty/<topic>/prd.md` | 请求用户 Review |
| `pretty-writing-design` | 已批准 PRD、Context/ADR、仓库事实 | `docs/pretty/<topic>/design.md` | 请求用户 Review，并提示两种 Execution 用法 |
| `pretty-executing` | 当前最新 Design、真实仓库 | Apply：`execution.md`；Dry Run：`execution-preview.md` | 门禁完成或明确停止/返回上游 |

### PRD

PRD 使用稳定的 `REQ-001`、`AC-001` 编号表达唯一需求合同。它锁定外部可观察结果、主流程、边界和失败语义，不选择类、Schema、事务或实现步骤。领域术语、状态、身份或跨上下文关系发生变化时，由全局 `domain-modeling` 维护领域上下文。

### Design

Design 是 Execution 的唯一强制合同，固定包含：

1. 设计结论
2. 方案全景
3. 关键设计与权衡
4. 设计边界
5. 实施影响
6. 验证与风险

“实施影响”提供有限的变更职责链路和稳定 `TASK-*`。TASK 按可观察结果垂直拆分，至少追踪 REQ/AC、业务结果、公共验证入口、影响锚点和验证观察面；它不是冻结文件清单或实现顺序。

高风险 Design 在请求用户 Review 前接受独立 Reviewer 审查。高风险包括外部 API/RPC/MQ/调度、DDL/迁移/兼容、职责或所有权变化、依赖方向、事务/并发/幂等/一致性、状态机、安全、不可逆副作用、跨模块公共行为和部署协作。Reviewer 审查合同与证据完整性，不审尚不存在的最终代码。

Design 完成后必须提示：

```text
$pretty-executing
$pretty-executing Dry Run
```

前者直接 Apply；后者只生成非权威 Preview。用户调用任一种方式，即批准当前最新 Design。

## Execution 的两种模式

### Apply

Apply 直接实现 Design，不要求先有 Preview。它调用用户全局 `tdd` 完成行为变化，按 Design TASK 建立临时执行矩阵，并以真实代码、测试报告、编译、回归、覆盖率和独立审查完成交付。

Apply 新运行只要求运行相关路径干净，包括源码、测试、构建文件、运行时资源、Schema/迁移、生成输入和构建脚本。PRD、Design、Preview、Execution、Context、ADR 和其他说明性文件可以有未提交变化；工作区状态由用户负责，不执行 stash、reset、rebase 或自动提交。

主题目录中的 `.execution-state.json` 只用于恢复同一次意外中断的 Apply。起始 HEAD、Design 摘要、执行矩阵和已登记运行文件摘要必须全部匹配，否则停止。正常完成或明确停止后删除状态文件。

行为实现遵循全局 `tdd` 的 RED/GREEN/重构节奏。Pretty Execution 负责合同、范围和门禁，不复制一套项目内 TDD。全局 `tdd` 不可用时，行为实现停止；不使用内置降级流程。

首次编辑测试前必须扫描目标文件及嵌套作用域中的 `@Disabled`、JUnit 4 `@Ignore`、元注解和条件禁用。新增业务测试不得进入被禁用作用域。历史禁用默认保持；只有 Design 明确包含恢复义务且整个恢复作用域真实通过时才移除。最终必须从新鲜 JUnit XML 证明新增或修改测试实际执行且通过，只有编译成功不算完成。

Writer 在所有 TASK 集成、目标测试通过、Diff 自审完成且无待做重构后冻结候选。机械 `error` 必须为零，`review_required` 必须分诊。冻结后可以并行独立 Reviewer、编译、回归和覆盖率；Reviewer 期间 Writer 不做机会性修改。finding 修复后，只重跑受影响证据，但最终覆盖率和审查结论必须绑定修复后的完整 Diff。

如果实际集成只需要 import、构造器注入、fixture、编译闭包或同语义局部拆分，可以继续并记录。公共签名、异常合同、职责、所有权、依赖方向、外部行为或测试观察面改变时，必须返回 Design。

### Dry Run

Dry Run 不修改会影响编译、测试、运行或部署的文件，只生成 `execution-preview.md`。Preview 可以包含：

- 受影响职责链路；
- 与 Design 一致的 TASK；
- 精确 Files/Symbols；
- 核心生产实现提案；
- 公共行为测试提案。

Dry Run 不调用 `tdd`，不运行编译、测试、覆盖率、代码生成或数据库命令，不启动独立 Preview Reviewer，也不输出验证结果或审查结论。Preview 是可选资料，不是 Apply 前置条件；Apply 不自动验证其新鲜度，也不复用其审查证据。Design 与真实仓库事实始终优先。

## 质量与证据

机械 Gate 负责高确定性规则，例如空值成功、禁用测试、跳过测试参数、JDK/方法约束和候选摘要。语义 Reviewer 负责合同、职责、边界、失败语义、测试观察面以及 AI 生成完整性。二者互补，不能互相替代。

Design Reviewer 的证据绑定 PRD、Design 和明确合同来源共同计算的候选 SHA；候选内容变化后证据失效。Apply 的测试、质量、覆盖率和构建证据同时绑定 Design SHA、真实文件摘要和最终候选摘要。详细 JSON 放临时目录，`execution.md` 只汇总人可读结果。

## 推荐使用方式

完整路径：

```text
$pretty-writing-prd
→ 用户 Review
→ $pretty-writing-design
→ 用户 Review
→ $pretty-executing
```

需要先查看精确提案时：

```text
$pretty-writing-design
→ 用户 Review
→ $pretty-executing Dry Run
→ 可选人工检查 Preview
→ $pretty-executing
```

简单且已具备 PRD/Design 的变更可以直接从对应阶段开始，但 Execution 不能绕过当前有效 Design。提交、推送、MR、部署和发布均不由上述调用自动授权。
