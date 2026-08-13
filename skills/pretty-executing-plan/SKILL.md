---
name: pretty-executing-plan
description: Use when an approved Pretty plan.md for a Java/Spring feature, bug fix, or refactor is ready to implement or resume in the target repository.
---

# 执行 Java/Spring Plan

## 目标

按已批准 Plan 逐用例实施，在生产代码写入期间持续关闭质量问题，完成最终组合检查后执行一次最终验证。`execution.md` 只记录结果，不维护过程账本。

**REQUIRED SUB-SKILL：** 完整读取并使用 `pretty-java-spring-core` 的共享合同、Execution 模板和 Java/Spring 质量参考。本 Skill 是本阶段唯一流程控制器。

## 工作流

### 1. 读取输入并记录执行起点

宣布使用 `pretty-executing-plan`，读取同一标准目录下已批准的 `prd.md`、`design.md`、`plan.md` 和共享领域上下文。合同缺失、矛盾或不可执行时返回最早受影响阶段；Execution 不改写上游或领域文档。

开始时只运行并记录：

```bash
git rev-parse HEAD
```

不运行 Plan 文档校验、执行前编译、UT、静态检查或起始 HEAD 对照。保留用户原改动，不 stash、reset、rebase 或覆盖；发现同一位置存在无法安全保留的改动时停止。恢复时读取上游、真实 diff、测试结果和已完成 TASK 结果，从首个未闭环 TASK 继续。

### 2. 在生产编辑前启用质量约束

Plan 含非机械生产代码修改时，在第一次生产代码编辑前使用一次 `clean-code-guard` live mode；它在本次 Execution 后续全部生产修改中持续生效，不按用例或 TASK 重复加载，也不生成逐项报告。

确认此约束已启用后才进入逐用例 TDD。代码应持续满足清晰职责、DRY、SOLID、KISS 和 YAGNI，不以仓库既有坏样例为优先依据。

### 3. 逐用例 TDD

新增/改变行为或 Bug 修复时，**REQUIRED SUB-SKILL：** 使用 `tdd`。每次只闭环一个用例：

```text
[一个 UT] -> [确认因目标行为缺失而正确 RED]
  -> [当前用例最小 GREEN] -> [下一个用例]
```

- 不先批量写测试或生产代码，不伪造 RED。
- UT 首次通过时检查断言和现有实现：行为完整存在则记为 `已满足（无生产差异）`；部分存在时只为缺失行为取得 RED；测试入口或预期需改变时返回 Plan。
- 同一入口和预期遗漏的输入或错误分支可直接补用例；新增验收语义返回 PRD，改变技术合同返回 Design。
- 独立行为保持重构先确认当前测试通过，再使用 `refactor` 小步复验，不制造 RED。
- 非行为任务执行 Plan 中的确定性验证，不制造 RED/GREEN。
- 只创建或扩展 UT；测试边界和验证声明遵循共享合同。

### 4. 在 TASK 边界关闭局部问题

TASK 的全部用例 GREEN 后，只检查该 TASK 新增生产差异是否违反已启用的 guard：

- 行为错误返回相应用例修正；
- 行为保持的结构问题使用 `refactor` 立即修正；
- 超出 Plan、Design 或 PRD 合同的发现返回对应上游；
- 修正后只复验当前 TASK；
- 未关闭的局部代码质量问题阻塞进入下一 TASK。

`execution.md` 只记录 TASK 的可观察结果、主要落点、TASK 验证和实质偏差，不记录逐用例 RED/GREEN 命令或 Skill 调用。

### 5. 最终组合检查

全部 TASK 完成后、最终验证前执行一次最终组合检查，只关注跨 TASK 组合后才显现的问题：

- 重复知识或规则所有权分散；
- 同一类累计职责或混合抽象层级；
- 多个 TASK 叠加造成接口膨胀；
- 依赖方向或边界对象转换不一致；
- 跨 TASK 异常、事务、并发或兼容合同冲突。

不重复 TASK 已关闭的局部检查。对象职责、协作或封装命中风险时使用 `121-java-object-oriented-design`；服务职责、端口或依赖方向命中风险时使用 `solid-principles`。只有实际 Java 风险命中 null、异常、并发、资源、性能或 API 合同时使用 `java-code-review`，不把它作为固定全量扫描。

组合问题立即修正并复验受影响 TASK。未关闭的代码质量发现阻塞最终验证。

### 6. 执行一次最终验证

质量问题全部关闭后，运行 Plan 定义的受影响模块编译、本次全部新/改 UT、直接相关回归 UT、快速静态检查和适用覆盖率。真实 diff 扩大范围时纳入本次最终验证，不默认运行全仓或既有非 UT 测试。

失败能从当前 diff、失败测试和调用链可靠归因时，返回相应用例修正；无法可靠归因时停止并写明“归因不确定”，不自动扩大修复范围。最终验证后没有相关代码变化时不重复命令；有相关变化时只重跑受影响范围。

### 7. 写结果并交付

完成态使用 Execution 模板的四章：`执行起点`、`TASK 结果`、`最终验证`、`结论与限制`。停止态只记录已经发生的事实：

- 没有完成 TASK：`执行起点 -> 恢复点 -> 结论与限制`；
- 已完成 TASK：`执行起点 -> TASK 结果 -> 恢复点 -> 结论与限制`。

运行文档校验器；告知用户真实代码差异、Execution 路径、最终验证范围和限制后停止。不请求批准 Execution，不自动执行 Git 或发布动作。

## 红线

- 不在生产编辑完成后才首次应用代码质量规则。
- 不把 TASK 局部检查拖到最后重新全量返工。
- 不用覆盖率替代行为、断言或代码质量。
- 不记录无意义过程输出或夸大验证范围。
- 不自动 `git add`、commit、push、创建 MR、合并或发布。
