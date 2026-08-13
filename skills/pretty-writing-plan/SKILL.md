---
name: pretty-writing-plan
description: Use when creating, revising, or reviewing a Pretty plan.md for an approved Java/Spring PRD and Design before implementation begins.
---

# 编写 Java/Spring Plan

## 目标

把已批准的 PRD、Design 和真实源码转化为约束性实施合同与可审查代码提案。Plan 不实施代码、不执行 RED/GREEN，也不改变上游合同。

**REQUIRED SUB-SKILL：** 完整读取并使用 `pretty-java-spring-core` 的共享合同、Plan 模板和 Java/Spring 质量参考。本 Skill 是本阶段唯一流程控制器。

## 工作流

### 1. 确认模式与输入

宣布使用 `pretty-writing-plan`。只读评审只接受标准路径，严格不修改文件、不生成 Execution。写作模式读取同目录下已批准的 `prd.md`、`design.md`、领域上下文、仓库规则、相关生产源码、调用方、测试、构建配置和覆盖率政策。

缺失、含占位或互相矛盾时返回最早受影响阶段。业务结果未知返回 PRD；职责、边界、合同、所有权或一致性未知返回 Design；仓库事实自行调查。Plan 不调用 `grilling` 或 `domain-modeling`。

### 2. 先确定最终职责形状

在分 TASK 和编写代码提案前，建立：

```text
生产 symbol -> TASK -> 最终职责 -> 直接依赖 -> 规则所有权
```

同一生产类被两个以上 TASK 修改时，合并阅读全部拟议变化，先确定最终职责和依赖。若最终组合形状出现多个 actor、业务编排与基础设施 DTO 混合、抽象层级混合、跨层依赖或重复规则，先调整职责、边界或 TASK；涉及 Design 合同时返回 Design，不把累计设计问题留给 Execution。

### 3. 编写 TASK 与代码提案

`TASK-001` 起连续编号，按可验证行为或独立风险垂直切分，不按技术层切分。TASK 是 Plan 与 Execution 间唯一身份；每个 TASK 内使用无编号的“用例”短名称。

每个行为 TASK 按顺序包含：

1. 可观察结果和不可改变的合同；
2. 完整仓库相对路径、symbol 和修改目的表；
3. 接近可编译的核心生产代码；
4. 用例及完整核心测试代码；
5. 必要机械修改、真实依赖和完成证据；
6. 末尾 `REQ/AC/DEC` 追溯。

在写第一段非机械 Java 代码提案前使用一次 `clean-code-guard` live mode，并在后续全部提案中持续应用，不按 TASK 重复加载或生成报告。代码优先满足清晰职责、DRY、SOLID、KISS 与 YAGNI，不盲目复制仓库坏样例。

- 对象职责、协作、封装或聚合变化：使用 `121-java-object-oriented-design`。
- 服务职责、端口或依赖方向变化：使用 `solid-principles`。
- 值对象、类型层次、接口或模式只按共享路由中的实际风险使用对应能力。
- 质量发现直接修正代码提案；改变 Design 合同返回 Design，改变外部结果返回 PRD。

行为任务必须同时包含核心生产和测试代码，不用省略号或文案隐藏关键逻辑。相同 fixture、builder、import、getter、普通 DTO/映射和机械常量只定义一次。纯 DDL、配置、文档、改名或批量机械任务使用完整机械变更和确定性验证，不制造 Java 或 UT。

### 4. 审查测试提案

新增或改变行为、Bug 修复时，**REQUIRED SUB-SKILL：** 使用 `tdd` 审查提案，但不创建测试文件、不执行 RED/GREEN。测试应展示 public 行为入口、fixture、边界替身以及业务结果、状态或完整边界请求断言。

只提议 UT；不新增或扩展集成、契约、端到端、Spring slice、Testcontainers 或嵌入式基础设施测试。不要用 Given-When-Then、预期 RED 或最小 GREEN 等重复文案代替测试代码。

### 5. 一次组合审查与最终验证定义

全部 TASK 写完后只审一次最终组合形状，跨 TASK 检查重复知识、累计职责、接口膨胀、依赖方向和错误/事务/并发/兼容合同。只修正组合后才显现的问题，不重复逐 TASK 已关闭的局部检查。未关闭的代码质量发现阻塞请求 Review。

Plan 只定义一次最终验证：受影响模块编译、本次全部新/改 UT、直接相关回归 UT、快速静态检查和适用覆盖率。不定义执行前编译、UT、静态检查或测试入口基线。列出 Pretty 外未验证范围和严格声明限制。

### 6. 校验并请求 Review

确认最终职责视图、连续 TASK、用例、任务末尾追溯、文件表、生产/测试代码对、真实命令、覆盖率政策和声明限制一致。运行：

```bash
python3 <pretty-java-spring-core-dir>/scripts/validate-pretty-docs.py \
  docs/pretty/<topic> --through plan
```

告知路径、TASK 数量、最终组合形状、测试入口、覆盖率政策和校验结果，请求 Review 后停止。用户批准 Plan 后才进入 Execution。

## 红线

- 不虚构源码、API、命令或结果。
- 不把 Plan 写成逐文件完整补丁或创建代码附件。
- 不执行 RED/GREEN，不修改生产或测试文件。
- 不新增或扩展非 UT 测试。
- 不以当前仓库样例为由保留已识别的 DRY、SOLID 或职责问题。
