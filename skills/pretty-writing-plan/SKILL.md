---
name: pretty-writing-plan
description: Use when reviewed Pretty PRD and Design documents for a Java/Spring change need a pre-implementation code-review plan before execution begins.
---

# 编写 Java/Spring Plan

## 目标

把已 Review 的 PRD、Design 和真实源码转化为实施前 CR 文档。Plan 应让人能够审查具体实现与测试，并让执行者逐项实施和验证；它不修改代码，也不编排 Git 操作。

**REQUIRED SUB-SKILL：** 完整读取并使用 `pretty-java-spring-core` 的共享合同、Plan 模板和 Java/Spring 质量检查。本 Skill 是当前阶段的唯一流程控制器。

## 工作流

### 1. 校验输入

宣布使用 `pretty-writing-plan`。读取同一主题下已由用户 Review 的：

```text
docs/pretty/<topic>/prd.md
docs/pretty/<topic>/design.md
```

根目录存在 `CONTEXT-MAP.md` 时读取相关上下文的 `CONTEXT.md`，否则读取根目录已有的 `CONTEXT.md`。缺失、未 Review 或存在矛盾时停止，返回最早受影响阶段。Plan 不改变 `REQ`、`AC` 或 `DEC`。唯一输出文件是：

```text
docs/pretty/<topic>/plan.md
```

已有文件时原地修订。简单 Bug 或局部重构可以只有一个任务。

### 2. 核实实施证据

读取完成本次变化所需的真实生产源码、调用方、测试、构建配置和仓库规则，确认准确路径、类型、签名、依赖、测试命令及现有 JaCoCo 约定。

- 能从仓库确定的事实自行查明，不虚构文件、API、命令或预期结果。
- 非阻塞细节沿用仓库惯例和最简单实现。
- 缺少会导致关键代码不准确的事实时，只问一个聚焦问题。
- Plan 只消费领域模型，不调用 `domain-modeling`，不得更新 `CONTEXT.md`、`CONTEXT-MAP.md` 或 ADR。当前代码示例或命名错误而上游语义明确时直接修正 Plan；需要改变需求、`REQ` 或 `AC` 时返回 PRD，需要改变领域设计、边界、所有权或 `DEC` 时返回 Design。

### 3. 审查拟议 Java/Spring 代码

涉及生产 Java 对象、方法或职责时，**REQUIRED SUB-SKILL：** 使用 `121-java-object-oriented-design`。再按真实变化选择：

| 触发场景 | 使用的 Skill |
|---|---|
| 类型层次、值对象、泛型或 primitive obsession | `122-java-type-design` |
| 新增或改变服务职责、端口或依赖方向 | `solid-principles` |
| 保持行为的遗留结构调整 | `refactor` |
| Spring 测试层级、JUnit、Mockito、MockMvc 或 Testcontainers | `springboot-tdd` |

完整读取实际触发的 Skill，把发现落实到代码和任务。在 Design 已确定的既有职责内修改方法实现，不单独触发职责或依赖方向检查。关键生产代码起草后使用 `clean-code-guard` 做一次实现方案 Review，修正命名、职责、控制流、重复、无必要抽象和 LLM 常见缺陷。若修正会改变 Design，返回 Design 阶段。

### 4. 编写可作为 CR 的 Plan

使用共享 Plan 模板并替换全部占位内容。用 `TASK-001` 起连续编号；每个任务关联适用的 `REQ`、`AC` 和 `DEC`，列出准确文件和依赖顺序。

每个任务必须足够自包含：

- 标明变更类型与实现要点。
- 行为变化按 `superpowers:test-driven-development` 规划 RED 测试、预期失败、最小 GREEN 实现、通过命令、重构与再验证；非行为变化给出等价验证。
- 完整展示关键生产代码与测试代码，包括公共签名、核心业务方法、校验/异常/事务边界以及可执行的关键测试。
- 修改既有方法时展示完整替换方法及必要上下文；新增类型展示可编译的完整类型。
- import、注解替换、配置键、简单映射和重复改名等机械修改使用逐项变更表，列清文件、符号、旧值、新值和验证方式。
- 给出可直接运行的定向测试、受影响模块测试和最终仓库验证命令及预期结果。

不得使用省略内容、伪代码或“类似修改”。Plan 中的代码必须与任务间的类型、签名和错误语义一致，并严格限定在需求所需范围。

### 5. 定义测试与新增代码覆盖率门禁

Plan 必须让执行阶段可以证明，而不是猜测覆盖率：

- 新增生产代码行覆盖率至少 `90%`，分支覆盖率至少 `80%`。
- 修改遗留行为必须有针对本次变化的回归测试。
- 未触碰历史代码不进入覆盖率分母，也不要求补测。
- 测试须覆盖主流程、关键边界、失败行为以及适用的权限、金额、状态、幂等和事务语义；覆盖率不能替代有效断言。
- PRD 含业务故事时，用其检查测试方案是否覆盖代表性业务结果；故事与测试允许多对多，不要求每个故事都有独立 E2E 测试，也不新增 `US` 标识，`REQ/AC` 仍是唯一需求合同。

写入捕获执行起点、生成报告和检查增量的准确命令，使用共享工具：

```bash
<pretty-java-spring-core-dir>/scripts/run-coverage.sh --project-dir <repo-root>
python3 <pretty-java-spring-core-dir>/scripts/check-new-code-coverage.py \
  --repo <repo-root> --base <execution-start-head> --report <jacoco.xml> \
  --file <plan-owned-production-file> \
  --line-threshold 90 --branch-threshold 80
```

按仓库实际情况把命令中的运行时值写成可取得的具体路径或变量，并为每个 Plan 拥有的生产文件重复 `--file`，避免把工作区内无关改动算入分母；同时说明报告位置与失败判定。共享覆盖率工具不得为了采集报告修改项目构建文件；业务实现确需的依赖或构建变化仍作为普通 CR 内容列出。

### 6. 自审并机械校验

确认所有 `REQ/AC/DEC` 均有任务和验证，每个任务都有来源；拟议命名、身份、状态、不变量、所有权和边界与领域文档及 Design 一致；关键代码符合项目规则、Clean Code、Java/Spring 质量检查和最简单可行原则；测试代码能够覆盖计划中的新增分支；命令、路径和报告位置真实。

运行：

```bash
python3 <pretty-java-spring-core-dir>/scripts/validate-pretty-docs.py \
  docs/pretty/<topic> --through plan
```

修正所有机械或语义问题后再交付。

### 7. 请求一次 Review 并停止

告知用户 Plan 路径、任务数量、关键代码 Review 结论、覆盖率合同和校验结果，请求一次人工 Review，然后停止。不得开始实施、创建 Issue、提交或推送代码。

## 红线

- 只有文件名却没有源码，仍生成貌似完整的代码。
- 把 Plan 写成只有意图、没有可 Review 代码的任务清单。
- 用全仓覆盖率掩盖新增代码覆盖不足，或要求无关遗留代码补测。
- 为提高指标扩大排除、弱化断言或增加无业务价值测试。
- 在 Plan 中改变需求、设计或加入无关重构。
- Plan 完成后自动进入执行阶段。
