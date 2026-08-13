---
name: pretty-writing-plan
description: Use when creating, revising, or reviewing a Pretty plan.md for an approved Java/Spring PRD and Design before implementation begins.
---

# 编写 Java/Spring Plan

## 目标

把已批准的 PRD、Design 和真实源码转化为约束性实施合同与可审查实现提案。Plan 是代码事实前置 CR 和 Execution 的事实依据；不实施代码，不执行 TDD，不编排 Git。

**REQUIRED SUB-SKILL：** 完整读取并使用 `pretty-java-spring-core` 的共享合同、Plan 模板和 Java/Spring 质量检查。本 Skill 是本阶段唯一流程控制器。

## 工作流

### 1. 确认模式与输入

宣布使用 `pretty-writing-plan`。用户只要求评估、检查或 Review 时进入只读评审；要求创建或修订时进入写作模式。

写作模式读取同一标准目录下已由用户批准的：

```text
docs/pretty/<topic>/prd.md
docs/pretty/<topic>/design.md
```

读取共享合同要求的领域上下文。缺失、未批准、含占位或互相矛盾时返回最早受影响阶段。Plan 不改变 `REQ/AC/DEC`，唯一输出为：

```text
docs/pretty/<topic>/plan.md
```

已有文件原地修订。简单变更仍保留五章，可以只有一个短 TASK。

### 2. 执行只读评审

只接受 `docs/pretty/<topic>/plan.md`；同目录必须存在 PRD、Design，并能定位真实源码。非标准路径不接受、不迁移、不复制。

严格不修改文件、不生成 Execution、不开始实施。核对真实源码、上游合同、TASK、UT 方案、基线、覆盖率和声明边界，运行至 Plan 的机械校验但只把失败作为发现。依次输出并停止：阻塞问题、重要改进、代码事实与上下游偏差、执行与验证影响、`可进入 Execution / 修正后再进入 Execution`。结论不等于用户批准。

### 3. 核实代码事实并分流未知

读取完成变更所需的生产源码、调用方、现有测试、构建配置、仓库规则和 JaCoCo 政策，确认真实相对路径、symbol、类型、签名、依赖和命令。

- 区分已核实代码事实、`REQ/AC/DEC` 上游约束和拟议实现。
- 仓库事实自行查明，不虚构文件、API、命令或结果。
- Plan 不调用 `grilling`：业务结果未知返回 PRD；职责、边界、合同、所有权、一致性或 `DEC` 未知返回 Design；低风险外部等价实现给出推荐提案。
- Plan 只消费领域文档，不调用 `domain-modeling`，不得更新 `CONTEXT.md`、`CONTEXT-MAP.md` 或 ADR。
- 数据库、外部服务、凭证、部署或 Reviewer 是否存在可以保持运行时未知，不阻塞 Plan。

### 4. 审查拟议实现

按真实风险使用质量能力：对象职责、封装、聚合、组合或继承变化时使用 `121-java-object-oriented-design`；类型、SOLID、接口和行为保持重构按共享路由触发。不要无条件运行 Java/OOD 检查；纯 SQL、配置、部署、文档和机械修改不触发无关能力。

对职责、依赖、契约、算法、异常、事务、SQL、安全、兼容和可测试性执行风险导向 CR。改变职责、依赖方向、所有权、事务、跨模块合同或长期扩展点时返回 Design；改变业务结果时返回 PRD。不为测试暴露生产方法，不引入无现实用途抽象。

### 5. 编写五章 Plan

使用共享模板。`TASK-001` 起连续编号，优先按可验证行为或独立风险垂直切分，不按技术层或 commit 大小切分。每个 TASK 按适用性写清目标闭环、追溯、事实、继承约束、拟议变更、具名行为切片、验证入口、真实依赖和完成证据。

所有 `REQ/AC/DEC` 必须有真实落点，但可以落到生产代码、UT、跨任务门禁或不变边界验证。TASK 只声明真实依赖，外部环境不是依赖。两个以上 TASK 提供任务索引；简单 Plan 不生成空表或虚假内容。

代码按风险选择性展开：

- 高风险算法、SQL、事务、并发、兼容、异常路径或复杂 UT 可以展示完整代码；
- DTO、getter、普通映射、import、改名和样板使用签名、关键片段或机械变更表；
- 展示的签名、类型和片段必须与仓库一致、自洽，不用省略号隐藏高风险逻辑；
- Plan 不要求所有片段可单独编译，也不是完整候选补丁。

### 6. 用 `tdd` 审查 UT 方案

新增/改变行为或 Bug 修复时，**REQUIRED SUB-SKILL：** 使用 `tdd`，但只用于保证测试计划质量。Plan 不写测试文件、不执行 RED/GREEN、不声称 TDD 已发生。

每个行为切片必须说明：

- 不启动 Spring 的稳定 UT 边界和 Given-When-Then；
- 独立预期值；
- mock/fake/stub 边界；
- 因目标行为缺失而失败的预期 RED 原因；
- 当前切片最小 GREEN 条件；
- 可解析验证入口。

文档统一使用“UT 边界”或“测试边界”，不另造英文同义术语。

测试断言业务结果、状态变化或完整边界请求，不以调用次数/顺序为主要成功标准。边界外 Repository、Gateway、Service、远程客户端、时钟等可以替换；被测规则使用真实对象。JUnit 5、Mockito、AssertJ 写法遵循 `tdd` 和最佳实践，并兼容仓库实际依赖版本。

强制 UT-only：不得提议新增或扩展集成、契约、端到端、Spring slice、`@SpringBootTest`、`@WebMvcTest`、`@DataJpaTest`、Testcontainers、嵌入式数据库或本地基础设施测试。SQL、配置、文档和机械修改使用确定性验证，不制造 UT。用户批准 Plan 即确认测试边界，Execution 不逐项再问。

### 7. 定义基线、最终验证与覆盖率

Execution 基线只包含可控的受影响模块编译、相关现有 UT、必要快速静态检查和将修改的测试入口，不默认全仓或外部环境检查。

最终验证默认包含受影响模块编译、本次全部新/改 UT、直接相关回归 UT、快速静态检查和适用覆盖率。优先继承仓库覆盖率政策；无政策时，可由 UT 覆盖的新增或实质修改 Java 行为默认行 90%、分支 80%。修改既有行为以针对性 UT 证明；工具不能统计修改行时不虚构百分比。覆盖率不得驱动非 UT、弱断言或无价值测试。

列出 Pretty 外未验证范围和严格声明限制；外部资源不可用不形成 TASK 依赖或完成门禁。

### 8. 自审、校验并请求 Review

确认五章、连续 TASK、追溯落点、三类事实、风险选择性代码、垂直 UT 切片、真实命令、覆盖率政策与声明限制一致；无占位、个人路径或上游越权。运行：

```bash
python3 <pretty-java-spring-core-dir>/scripts/validate-pretty-docs.py \
  docs/pretty/<topic> --through plan
```

告知路径、TASK 数量、关键 CR 结论、UT 边界、覆盖率政策和校验结果，请求一次用户 Review，然后停止。用户批准 Plan 后才可进入 Execution。

## 红线

- 不用文件名或 Design 示例冒充已核实源码。
- 不退化为完整候选补丁或只有意图的任务清单。
- 不按技术层横向切分 TASK。
- 不在 Plan 中写测试、执行 RED/GREEN 或改变上游合同。
- 不新增或扩展非 UT 测试。
- 不创建代码附件、前置 CR 结论、执行交接或任务流程图。
