---
name: pretty-executing
description: 根据 Java/Spring Design、用户 Prompt 或 execution-plan 生成完整代码实现；支持仅产出详细 Plan，或默认直接修改真实代码并完成质量、编译、测试和 JaCoCo 增量覆盖率验证。
---

# 生成并执行 Java 实现

本 Skill 面向 Java/Spring 代码实现。它把已批准的 Design、用户当前 Prompt 或已有
`execution-plan.md` 与真实代码仓库结合，生成完整、具体、可落库的生产代码和行为测试。
它不修改 PRD、Design、Context、ADR 或治理文档，不提交、推送、部署或发布。

## 输入与优先级

按以下顺序处理输入；冲突不能猜测解决：

1. 当前用户 Prompt：决定目标、范围、模式和本次修改授权。
2. `docs/pretty/<topic>/design.md`：提供业务语义和技术合同。
3. `docs/pretty/<topic>/execution-plan.md`：提供已确认的实现拆解和顺序。
4. 真实代码仓库：提供文件、调用链、依赖、Java/JDK 版本、构建配置和项目惯例等事实。

Design 或 execution plan 不得覆盖用户当前明确的目标和授权；文档与真实仓库事实不一致时，
停止并报告冲突。只有已有 `execution-plan.md` 且它与当前 Prompt、Design 和仓库事实一致时，
才可直接执行该计划。

### 生成代码质量规范优先级与事实约束

在用户明确当前任务边界后，优先级依次为：
- [质量原则](references/quality-principles.md)
- AGENTS、Trellis。

该顺序只解决真实冲突，不改变质量 路由或审查强度；质量原则始终适用，专项路由根据执行合同与仓库事实选择。
执行合同中的普通实现偏好不能伪装成业务合同来覆盖质量原则。外部或遗留合同确需例外时，
必须绑定具体 symbol、不可修改原因，以及测试、Schema 或签名事实。真实 API、Schema、依赖
版本和运行结果是不可伪造的事实约束；禁止参考既有实现方式，只能通过质量则或适用的专项建议。稳定业务规则不做成模式码、SpEL 或配置开关。Java 版本与依赖 API 以
真实构建配置和已安装版本为准。

输入可以只有 Prompt。若没有可复用的 topic，从 Prompt 生成小写 kebab-case topic；在写入
文档或开始执行前展示该 topic 并确认。Design 或 execution plan 已位于
`docs/pretty/<topic>/` 时，使用其所在 topic。

## 模式选择

- 用户明确指定 `Plan` 时进入 Plan 模式；`Plan` 是唯一的计划模式名称。
- 未明确指定 `Plan` 时，默认进入执行模式，直接修改真实代码库。
- 流程只有 Plan 和执行两种模式。

### Plan 模式

Plan 模式只写 `docs/pretty/<topic>/execution-plan.md`，不修改生产代码、测试代码、项目配置或
其他真实实现文件，也不写 `execution.md`。目标文件已存在时停止并报告，除非用户明确要求更新
已有计划。

严格使用 [execution-plan 模板](assets/execution-plan.md)，并生成足够具体的实现内容：

- 按可观察行为垂直拆分 TASK，写出变更链路、Files 和依赖顺序。
- 为每个生产文件给出完整新增或修改的核心 symbol，包括字段、构造器、注解、方法和配置；
  不展示 import。
- 同时给出从公共行为入口验证结果、状态或异常的完整测试代码；不以伪测试、调用次数或
  private 方法测试替代行为断言。
- 不保留 TBD、伪 API、半实现、无调用者的抽象或无法由仓库事实支持的配置。

生成前读取仓库并匹配质量原则和适用质量路由；生成后对计划中的代码进行结构校验、静态质量
扫描、独立 Review，并在发现问题时重构计划内容后重新检查。Plan 不执行正式编译、测试或
覆盖率，因为它不把实现集成进真实代码库；这些验证只在执行模式完成。

### 执行模式

执行模式直接在当前真实代码库生成代码，不创建隔离工作树，也不生成额外的运行状态协议。

开始修改前必须完成：

1. 读取 Prompt、适用 Design、已有 execution plan、目标文件、相邻实现、调用方和被调用方、
   测试入口、Java/JDK/依赖版本、构建配置以及适用的 AGENTS/Trellis/ADR。
2. 若已有 `execution-plan.md`，校验其与上述输入和当前仓库事实一致；过期或冲突时停止并
   报告，不按过期计划修改。
3. 确定本次真实影响文件集合。只检查该集合中的未提交修改；集合包含受影响的 Java、测试、
   `pom.xml`、Gradle 文件和实际项目配置等。若这些文件已有用户修改，停止并报告；不相关
   文件的脏状态不阻塞，也不得触碰。
4. 确认 `docs/pretty/<topic>/execution.md` 不存在。若已存在，立即停止并报告，不覆盖、追加
   或继续修改代码。
5. 按 [execution 模板](assets/execution.md) 创建空白执行记录，然后只更新模板已有字段；
   不新增输入来源、仓库基线或内部执行计划字段。

若没有现成的 execution plan，只在内部生成实现计划，不额外落盘
`execution-plan.md`。按最小可验证行为切片生成生产代码和测试代码，并保持每个切片都能由
公共行为入口观察。

## 质量驱动实现

生成前必须完整阅读 [质量原则](references/quality-principles.md)，先根据真实受影响链路、
文件、symbol、类型、依赖和行为风险选择质量路由。质量原则始终生效：

- 命中路由时，合并所有命中路由的约束；同一问题采用更严格的约束。
- 没有命中专项路由时，仍按通用质量原则继续生成，不停止。
- 路由只指导生成和 Review，不要求把路由字段写入 `execution.md`，也不把专项 Skill 的
  流程、命令或阈值复制进本 Skill。
- 生产 Java 默认考虑职责/封装、运行时失败语义和行为测试；只有真实事实证明需要时才增加
  模块边界、类型设计、变化轴、SOLID 或其他专项约束。

路由匹配后，在生成过程中落实其设计约束；生成完成后同时执行：

1. 机械质量门禁：使用 `scripts/quality_contract_gate.py` 通过重复的 `--path` 只扫描本次影响
   的 Java 文件；Plan 中的临时代码文件可通过 `--source` 扫描，临时文件不得写入仓库。
2. 独立 Review：由适用质量路由对应的 Reviewer 审查完整生产代码、测试、公共接口和真实
   影响范围；执行模式对所有非平凡生产代码额外使用 `clean-code-guard`。
3. 重构修复：发现问题时调用 `refactor` 完成必要重构，然后重新执行机械门禁和 Review；
   不以豁免、删除规则或降低阈值掩盖问题。
4. 项目验证：执行仓库现有的编译和相关测试入口，不跳过测试。Java 项目必须运行
   `scripts/verify_incremental_coverage.py`，使用 JaCoCo 检查本次生产 Java 增量覆盖率。

新增或修改的测试必须实际执行并观察业务结果、状态、异常或完整边界请求；不得通过构建参数、
过滤器或测试发现配置跳过测试。测试命令失败时进入修复和重新验证流程。

Plan 模式执行前述静态门禁和 Review，但不执行第 4 项正式编译、测试和覆盖率。

执行模式的常用辅助命令如下；`<base>` 是开始修改前记录的 Git 基线，输出仅供当前执行判断：

```bash
python3 skills/pretty-executing/scripts/quality_resolver.py --repo . --base <base> --json
python3 skills/pretty-executing/scripts/quality_contract_gate.py --repo . --base <base> --path <affected-java-file>
python3 skills/pretty-executing/scripts/validate_execution.py docs/pretty/<topic>/execution.md
```

## Java / JaCoCo 增量覆盖率

`scripts/verify_incremental_coverage.py` 仅支持 Java 项目，并自动识别 Maven 或 Gradle：

- 优先使用 `mvnw`/`pom.xml` 或 `gradlew`/`build.gradle(.kts)` 及项目已有 JaCoCo 配置。
- 项目配置了行或分支阈值时分别使用项目阈值；未配置的维度使用默认增量行覆盖率 `90%`、
  分支覆盖率 `80%`。
- 脚本根据执行开始时的 Git 基线计算新增或修改的生产 Java 行，运行 JaCoCo 测试报告并
  输出行、分支覆盖率和阈值；只改测试或没有生产 Java 增量时明确输出“不适用”。
- 发现没有 JaCoCo 报告、报告过期、源文件无法匹配或覆盖率未达阈值时，执行模式先修复并
  重新验证；仍无法通过则停止并报告。

示例：

```bash
python3 skills/pretty-executing/scripts/verify_incremental_coverage.py \
  --repo . --base HEAD --path <affected-java-file> --run
```

## 执行范围与代码生成约束

### DDL、DML 与数据库边界

- 表、字段和索引等 DDL 只能作为代码库文件交付，不生成针对 DDL 的测试，不直接执行，也不
  通过迁移工具、应用启动、构建插件或测试间接执行。
- Java 与 DDL 混合变更只测试 Java 的可观察行为，并在 `execution.md` 的“未验证范围”和
  “声明限制”中明确 DDL 已交付、未执行、未进行数据库验证。
- 配置数据 DML 始终由人工运维处理，不属于本 Skill 的执行交付物。

### AI 生成与实现完整性

- 生成代码前读取目标文件、相邻实现和真实依赖版本；AGENTS、Trellis、ADR 和项目治理文档
  只作上下文，不能自行触发同步任务或扩大写集。
- 禁止臆造 API、硬编码成功、生产 fixture、半实现、无调用者的抽象、无价值新依赖，以及从
  相似代码复制后猜测语义。
- 边界、空值、范围和顺序问题必须从合同重新推导，并由行为测试固定。
- Writer 在首次落笔和每个行为切片中主动满足质量基线，机械扫描用于即时反馈；不等最终检查
  才集中清理问题。

## 执行记录与停止条件

每个行为 TASK 的结果、实际落点、路由与审查摘要、行为证据、验证命令及退出码、未验证范围、
覆盖率和结论，严格按 `assets/execution.md` 的已有字段填写。不得增加自定义字段或另写状态
协议。生成或修复过程中如果某项门禁、Review、编译、测试或 JaCoCo 覆盖率失败，允许在本次
执行中修复并重新验证；无法修复或反复失败时，将报告状态写为 `停止：<原因>` 并停止。

以下情况直接停止并报告：

- 输入合同、Design、execution plan 与仓库事实冲突，或无法确定真实职责、失败语义、观察面
  和影响范围；
- 目标项目影响文件存在用户未提交修改，或已有 `execution.md`；
- 需要擅自改变公共接口、外部行为、数据所有权、依赖方向、事务、并发、幂等或安全边界；
- 机械门禁、独立 Review、编译、测试或 JaCoCo 增量覆盖率在修复后仍失败；
- 需要执行 DDL、配置数据 DML、真实数据库操作、部署、发布或人工运维动作。

停止时只在已有 `execution.md` 模板字段中记录已经发生的事实、未验证范围和恢复/返回原因，
不自动覆盖或回滚用户已有修改。
