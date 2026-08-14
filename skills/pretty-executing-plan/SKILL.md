---
name: pretty-executing-plan
description: Use when an approved Pretty plan.md for a Java/Spring feature, bug fix, or refactor is ready to implement or resume in the target repository.
---

# 执行 Java/Spring Plan

## 目标

按已批准 Plan 实施代码，以可控基线、逐用例 TDD、受影响范围验证和自动审计证明过程与结果。Execution 是增量维护的证据账本；完成后直接交付，不增加人工审批或 Git 动作。

加载当前阶段模板[assets/design.md](assets/design.md)

## 工作流

### 1. 校验完整输入

宣布使用 `pretty-executing-plan`。读取同一标准目录下已批准的：

```text
docs/pretty/<topic>/prd.md
docs/pretty/<topic>/design.md
docs/pretty/<topic>/plan.md
```

读取共享合同要求的领域上下文。Execution 只消费并核对，不调用 `domain-modeling`，不得更新 `CONTEXT.md`、`CONTEXT-MAP.md` 或 ADR。运行校验器至 Plan；合同缺失、矛盾或不可执行时返回最早受影响阶段，不在 Execution 中改写上游。

### 2. 采集归因并运行可控基线

在临时目录采集执行开始 HEAD、staged、unstaged、untracked 范围和必要 diff。保留用户原改动，不 stash、reset、rebase 或覆盖。无重叠时可在非洁净工作区继续；同一位置无法安全区分且有覆盖风险时停止。临时基线不进仓库。

尚未创建或修改 `execution.md` 时运行 Plan 指定基线。基线只包含受影响模块编译、相关现有 UT、必要快速静态检查和将修改的测试入口。任一基线命令失败，Execution 强制停止：

- 不开始 TDD；
- 不修改生产代码；
- 不自动把基线失败纳入本次修复；
- 创建最小 `execution.md`，记录命令、退出码、摘要和恢复条件。

外部数据库、服务、凭证或 Reviewer 不进入可控基线，缺失不算基线失败。基线全绿后立即使用共享模板创建或更新：

```text
docs/pretty/<topic>/execution.md
```

恢复时核对上游、真实 diff、测试输出和证据账本，从首个未闭环 TASK 继续，不只相信文档文字。

### 3. 逐行为切片执行

Plan 已获用户批准，显式测试边界无需逐项再问。重新核验关键代码事实：等价源码漂移采用真实相对路径/symbol 并记录；改变 Plan 合同返回 Plan，改变 `DEC` 返回 Design，改变业务结果返回 PRD。

新增/改变行为或 Bug 修复时，**REQUIRED SUB-SKILL：** 使用 `tdd`。每个切片严格执行：

```text
[一个 UT] -> [确认正确 RED] -> [当前切片最小 GREEN]
  -> [检查明确整理目标]
       +-- 确需整理 --> [使用 refactor，小步复验]
  -> [更新 TASK 证据]
```

- 每次只落地一个 UT；RED 必须因目标行为缺失而失败，不得是语法、依赖、环境或测试基础设施错误。
- 只写当前切片最小生产实现，不先批量写测试或生产代码。
- GREEN 后只有存在明确整理目标时，**REQUIRED SUB-SKILL：** 使用 `refactor`；无目标时不记录形式化“不触发”。
- 独立行为保持重构先取得通过基线，使用 `refactor` 小步复验，不制造 RED。
- 非行为任务运行 Plan 中确定性等价验证，不制造 RED/GREEN。

强制只能创建或扩展 UT：不启动 Spring，不访问真实/嵌入式基础设施；禁止新增或扩展集成、契约、端到端、Spring slice、Testcontainers 或本地基础设施测试。使用真实被测规则，边界接口可 mock/fake/stub；主要断言业务结果、状态或完整边界请求。

### 4. 处理 RED 首次通过、漏测和偏差

UT 首次通过时立即停止切片，不伪造 RED。检查断言有效性、现有实现和用户原改动：

- 行为完整存在：记录 `已满足（无生产差异）`，运行回归 UT；
- 部分存在：只为缺失行为取得真实 RED；
- 断言无效：在已批准边界内修正并重新取得 RED；
- 必须改变入口、预期、范围或 TASK：返回 Plan。

同一稳定入口、行为和预期下遗漏的输入或错误分支，可直接补 UT，执行真实 RED/GREEN 并记录偏差。改变测试层级/入口、预期或新增验收语义，返回 Plan、Design 或 PRD。

只记录实质偏差：文件/symbol、TASK/切片、测试边界/命令、有意义等价实现、未实施/必要新增内容和外部未验证范围；不记录格式、import 或局部变量。

每个 TASK 增量记录结果、实际相对路径与 symbol、切片 RED/GREEN/实际重构证据、实质偏差和任务完成证据。保留命令、退出码、预期/实际失败摘要和通过摘要，不复制完整日志。

### 5. 完成受影响范围验证

全部 TASK 完成后运行：受影响模块编译、本次全部新/改 UT、直接相关回归 UT、快速静态检查和适用覆盖率。真实 diff 扩大影响范围时补跑新增范围；不默认全仓或已有非 UT 测试。

覆盖率优先使用仓库政策；无政策时按 Plan 默认门禁。工具只机械统计新增可执行行和分支；修改既有行为以针对性 UT 证明。不得降低断言、增加非 UT、扩大排除或创建无价值测试刷数字。

只能声明实际运行的“受影响范围通过”。真实数据库、服务、基础设施语义、部署、人工联调和独立 Reviewer 未执行时写入“未验证范围”，不阻塞完成，也不得被称为已验证。

### 6. 执行自动审计闭环

最终验证通过后，当前 Agent 对一个稳定最终版本自动审计。独立 Agent/Reviewer 是可选增强，不可用不阻塞。审计读取最终 diff、上游链、Execution 和真实命令证据，核对 TASK 归属、`REQ/AC/DEC/Plan`、RED/GREEN、基线、编译、UT、覆盖率、偏差、声明、代码质量、安全、异常、事务和兼容风险。

有生产代码差异时使用 `clean-code-guard`；有 Java 生产代码差异时再使用 `java-code-review`。专项能力按真实风险触发。无生产代码差异时只核对任务、证据与声明。

自动审计只检查，不直接修改：

- 行为错误返回对应 TDD 切片；
- 行为保持结构问题返回切片，使用 `refactor`；
- 超出合同返回 Plan、Design 或 PRD。

修正、复验后审计新的稳定最终版本。审计一次通过且没有影响验证的变化，不重复同一审计或命令。

### 7. 核对新鲜证据并交付

自动审计闭环后，**REQUIRED SUB-SKILL：** 使用 `superpowers:verification-before-completion` 核对证据新鲜度；不机械运行第三轮相同命令，审计后发生相关变化时只重跑受影响范围。

写入“最终审计与结论”，用“发现 -> 证据 -> 影响 -> 修正/处置 -> 复验”记录实质发现；无发现时写真实核对范围和依据。运行：

```bash
python3 <pretty-java-spring-core-dir>/scripts/validate-pretty-docs.py \
  docs/pretty/<topic> --through execution
```

最终状态只能是：`完成`、`停止：<原因>`、`返回 Plan / Design / PRD：<原因>`。多 TASK 中途停止时保留已完成证据，当前任务停止，后续任务未执行，不能声称“部分完成”。

告知用户真实代码差异、Execution 路径、受影响范围验证、自动审计和未验证范围，然后停止。不请求批准 Execution，不自动 `git add`、commit、push、创建 MR、合并或发布。

## 红线

- 不在基线失败后继续 TDD 或修改生产代码。
- 不伪造 RED，不把事后测试称为 TDD。
- 不创建或扩展非 UT 测试。
- 不把外部能力缺失或独立 Reviewer 缺失设为阻塞。
- 不在自动审计动作中直接修改代码。
- 不用覆盖率替代行为与断言质量。
- 不夸大验证范围或自动执行 Git/发布动作。
- - 不自动执行 `git add`、`commit`、`push`、merge、创建 MR 或发布。

