---
name: pretty-executing
description: 根据 Java/Spring Design、用户 Prompt 或 execution-plan 生成完整代码实现；支持仅产出详细 Plan，或默认直接修改真实代码并完成质量、编译、测试和 JaCoCo 增量覆盖率验证。
---

# 生成并执行 Java 实现

本 Skill 面向 Java/Spring 代码实现。它把已批准的 Design、用户当前 Prompt 或已有
`execution-plan.md` 与真实代码仓库结合，生成完整、具体、可落库的生产代码和行为测试。
它不修改 PRD、Design、Context、ADR 或治理文档，不提交、推送、部署或发布。


## 变更边界

- Design/Plan 锚点有效时直接读取目标实现；只有 Prompt-only 或锚点失效时才定向搜索可复用实现。
- 保持最小 diff，只修改任务范围内的文件。
- 不进行未请求的重构、清理或依赖升级。
- 保持现有 API 和行为，除非任务明确要求改变。


## Response style

- 先给结论。
- 不重复用户需求或已经说明的内容。
- 不粘贴完整文件。
- 只报告改动、验证结果和必要风险。
- 常规工具调用不需要逐条解释。



## 输入与优先级

按以下顺序处理输入；冲突不能猜测解决：

1. 当前用户 Prompt：决定目标、范围、模式和本次修改授权。
2. 已批准的 `docs/pretty/<topic>/design.md`：是业务结果、失败语义、不变量、所有权、依赖方向
   和外部边界的权威合同，并提供候选锚点、交付文件和构建模块。
3. `docs/pretty/<topic>/execution-plan.md`：在 Design 合同内提供更具体的 Files、Symbol、测试和
   实现顺序。
4. 真实代码仓库：只用于确认易变事实，包括当前文件内容、路径和签名、依赖 API、Java/JDK、
   构建任务、工作树状态及运行结果。

Design 或 execution plan 不得覆盖用户当前明确的目标和授权；文档与真实仓库事实不一致时，
停止并报告冲突。只有已有 `execution-plan.md` 且它与当前 Prompt、Design 和仓库事实一致时，
才可直接执行该计划。


### 质量来源与事实约束

`clean-code-guard` 负责通用代码质量，并作为执行模式[非平凡生产代码](references/quality-principles.md#非平凡生产代码判定)
的阻断质量合同；
[质量补充](references/quality-principles.md)只负责执行合同、Java/Spring 语义、运行观测和行为测试。
AGENTS、Trellis 等项目规则决定仓库本地惯例；它们都不能覆盖用户、Design 或 Plan 已明确的业务
合同。`clean-code-guard` 有具体代码证据的违反项默认阻断交付，只有下文允许的质量例外可以关闭。

真实 API、Schema、Java/JDK、依赖版本和运行结果以仓库事实为准；既有实现不能代替 Design、Plan
或 Prompt 决定本次业务语义。外部或遗留合同确需例外时，必须绑定具体 symbol、不可修改原因，
以及测试、Schema 或签名事实。
输入可以只有 Prompt。若没有可复用的 topic，从 Prompt 确定小写 kebab-case topic；只有名称存在
歧义或会与现有 topic 冲突时才请求确认，否则直接使用并在交付时报告。Design 或 execution plan
已位于 `docs/pretty/<topic>/` 时，使用其所在 topic。

## 模式选择

- 用户明确指定 `Plan` 时进入 Plan 模式；`Plan` 是唯一的计划模式名称。
- 未明确指定 `Plan` 时，默认进入执行模式，直接修改真实代码库。
- 流程只有 Plan 和执行两种输出模式；Design、已有 execution plan 和 Prompt-only 是三种输入
  路径，不是额外模式。

### Plan 模式

Plan 模式只写 `docs/pretty/<topic>/execution-plan.md`，不修改生产代码、测试代码、项目配置或
其他真实实现文件，也不写 `execution.md`。目标文件已存在时停止并报告，除非用户明确要求更新
已有计划。

严格使用 [execution-plan 模板](assets/execution-plan.md)，并生成足够具体的实现内容：

- 按可观察行为垂直拆分 TASK，写出变更链路、Files 和依赖顺序。
- 每个 TASK 写明构建根或模块，并将公共验证入口标记为“现有”或“新增”的
  `仓库相对路径#symbol`，供后续执行直接定位且避免误判新 Symbol 为锚点漂移。
- 为每个生产文件给出完整新增或修改的核心 symbol，包括字段、构造器、注解、方法和配置；
  不展示 import。
- 同时给出从公共行为入口验证结果、状态或异常的完整测试代码；不以伪测试、调用次数或
  private 方法测试替代行为断言。

按输入路径执行：

- **Design → Plan**：直接投影 `实施影响` 中的 TASK 语义，以及文档末尾
  `Executing 定位与交付` 中的职责链路、公共验证入口、影响锚点、交付文件和构建模块，不重建
  合同或输出前置分析。锚点已知后，用一个并行批次读取候选文件当前内容、公共测试、必要直接
  依赖、构建配置、质量补充和仓库规则；不重新读取 PRD、Context 或 ADR 证明 Design 已关闭的知识。
- **Prompt-only → Plan**：只做一次受限的内部 Design-lite 调查，确定可观察结果、失败语义、
  规则所有者、公共测试入口、影响文件和构建模块，直接写入 Plan，不另建 Design 或调查报告。
  Prompt 已给入口时用一个并行批次完成；入口未知时先定向定位，再并行读取受影响链路。若仍需
  决定外部行为、不可逆 Schema、所有权、依赖方向或一致性方案，停止并返回 Design。
- **已有 Plan 修订**：只有用户明确要求更新时才处理，并只重新读取受反馈或上游合同变化影响的
  TASK 和锚点；其余内容不重新调查。

路径或 symbol 失效时只围绕该锚点搜索。成稿后只执行一次结构检查、静态质量扫描和全量发现 Review；
阻断问题集中修复后只复核受影响的 Plan 片段，不生成额外全量证据。三者属于同一收尾批次。Plan
不执行编译、测试、测试守卫或覆盖率。

### 执行模式

执行模式直接在当前真实代码库生成代码，不创建隔离工作树或项目内交接文档；质量闭环允许在系统
临时目录保留一个不交付、不提交的 Review JSON，供限定修复期间的门禁复核。

开始修改前按输入路径获取范围：

- **Design → Execution**：直接采用 `实施影响` 中的 Design TASK，并从文档末尾的
  `Executing 定位与交付` 获取变更职责链路、公共验证入口、影响锚点、Execution 交付和构建
  模块。两部分按 TASK ID 对应；业务结果、失败语义、不变量、所有权和依赖方向不再从 PRD、
  Context、ADR 或全仓搜索中重新获取。
- **Plan → Execution**：直接采用已确认 Plan 的 Files、Symbol、测试、构建模块和顺序，并与
  Design 的语义合同对齐；没有 Design 时以 Prompt 和 Plan 中明确的行为约束为准。不得重新推导
  已由 Plan 给出的范围或实现结构。
- **Prompt-only → Execution**：只做一次受限的内部 Design-lite 调查，确定结果、状态迁移、失败
  语义、规则所有者、公共测试入口、影响文件和构建根，不落盘 Design 或 execution plan。Prompt
  已给入口时在预检批次内完成；入口未知时允许一次定向定位。合同级决定仍不明确时返回 PRD 或
  Design，不猜测执行。

范围已知后只执行一个并行预检批次：读取候选生产文件、公共测试、必要直接依赖、构建配置、
`clean-code-guard`、质量补充及适用 AGENTS/Trellis；同时检查候选文件的未提交修改、路径与
symbol 新鲜度，以及 `docs/pretty/<topic>/execution.md` 是否已存在。同一调用内这些质量说明只读
一次并持续用于后续生成、Review 和修复。Design/Plan 标记为新增的路径或 symbol 不要求预先存在。
候选文件已有用户修改或已有 `execution.md` 时停止；不相关脏文件不阻塞，也不得触碰。只有单个
锚点失效时才围绕它定向搜索；职责、所有权、依赖方向或外部合同漂移时返回 Design。ADR 只在
Prompt-only 路径或 Design 明确引用的例外需要核验时读取。

将 Design TASK 或 Plan 测试直接投影为简短内部测试清单；Prompt-only 才自行提取不同的成功
结果、失败语义和状态迁移。不给清单分配 ID、状态或证据字段，不输出前置分析，也不创建额外
交接文档。没有现成 Plan 时只在内部安排实现顺序。

按可观察行为逐个切片：先完成当前切片的行为测试，再完成从公共入口到 Module、Adapter 或
持久化的必要生产链路，然后进入下一切片。跨文件签名、依赖装配或生成代码等事实无法通过静态
检查可靠确认，或者一个切片闭环后需要尽早验证公共行为时，可以执行受影响模块的 `compile` 或
该切片相关的定向测试。中间反馈只使用最小相关模块和测试选择，不运行相关模块全量测试、JaCoCo
或覆盖率验收，也不为保存 RED/GREEN 证据机械触发；代码和命令输入未变化时复用已有结果，失败
修复后可以重跑。`execution.md` 不预先创建；最终成功或停止时按
[execution 模板](assets/execution.md) 一次性写入。

### 测试范围

- 纳入不同的成功结果、业务拒绝、查询未命中、非法或损坏数据、状态迁移、异常分类、远程
  空/失败/异常响应，以及完整外部边界请求等会改变可观察行为的合同。
- 相同公共入口和可观察结果的等价输入优先使用参数化测试，不按输入数量或每个 `if` 增加测试。
- 纯 DTO/Request/Response 的字段、无逻辑 getter/setter、普通构造器，以及 Lombok、编译器或
  其他工具生成的 accessor、`equals/hashCode/toString` 不创建专门测试。字段校验、转换、默认
  值、不变量、自定义相等性或协议语义属于真实行为时仍纳入，并优先从序列化、校验、Mapper
  或业务公共入口观察，不直接测试 accessor。
- 注释、声明和没有独立合同的机械转发不因覆盖率建测试；包含业务逻辑和样板代码的同一文件
  仍整体进入覆盖率范围，不按行手工规避。
- 覆盖率是发现遗漏的反馈，不是测试目标；不得为提高百分比测试 private 方法、无逻辑
  accessor、内部协作者调用次数或复制生产算法。

## 质量驱动实现

在预检批次中完整读取或复用本次会话未变化的 `clean-code-guard` 和
[质量补充](references/quality-principles.md)。`clean-code-guard` 的规则从首次生成到最终交付持续
生效；再根据 Design/Plan、真实受影响链路和计划修改的 symbol、类型、依赖与行为风险选择最小
专项路由。生成后以实际代码增量确认最终路由，不使用无关历史代码或全仓盘点扩大范围。

- 命中路由时，在同一次全量发现 Review 中应用其专项约束；没有命中时继续使用通用基线和质量补充。
- 路由只指导生成和 Review，不要求把路由字段写入 `execution.md`，也不把专项 Skill 的
  流程、命令或阈值复制进本 Skill。
- 只有真实事实证明需要时才增加模块边界、类型设计、Java 运行时或行为测试专项约束。

路由匹配后，在每个行为切片首次生成时直接落实约束。执行模式只保留以下收尾关键路径；Plan
模式使用前文规定的收尾批次，不执行真实项目验证：

1. **静态批次**：代码和测试全部完成后，并行执行一次质量路由解析和一次机械质量门禁；两者
   共享相同 Git 基线和实际影响文件，不分别扩展扫描范围。
2. **强制质量闭环**：只执行一次覆盖完整实际增量的全量发现 Review，同时应用
   `clean-code-guard`、全部命中专项路由和测试守卫。Reviewer 将每个有具体代码、合同或行为证据的
   问题记录为阻断 finding，至少包含稳定 ID、根因组、规则、`path:line#symbol` 证据、允许修复的
   范围和 `open / fixed / exception` 状态；finding 位置和允许范围必须处于实际影响或明确授权文件
   内，没有证据的偏好不得成为 finding。按
   [质量 Review 合同](references/quality-review-contract.md) 将清单写入系统临时目录，并先用
   `scripts/quality_review_gate.py` 校验结构。测试守卫检查新增/修改测试是否通过公共入口覆盖内部
   清单中的结果、状态和异常，是否包含本次行为产生的查询未命中、解析失败、依赖缺失及远程空/失败/
   异常响应，并拒绝测试禁用、private 方法测试、内部协作者调用次数或复制生产算法。

   对 `open` finding 按共同根因分组执行限定修复。命名、异常和局部控制流等问题直接最小修复；
   只有职责、抽象、耦合或方法结构问题才调用 `refactor`，并把输入限制为 finding 证据、允许文件和
   symbol、必须保持的行为及禁止改变的边界。每组最多两次修复尝试；每次后只复核该组 finding、
   实际修改的 symbol 及修复新增的代码，不再次执行全量 Review。受影响文件重跑机械门禁；只有
   签名、装配或可观察行为可能变化时才运行最小相关编译或定向测试，不启动全量测试或 JaCoCo。

   质量例外只能由当前 Prompt、Design、Plan、项目强制规则或不可修改的外部/遗留合同证明，必须
   记录具体 symbol、原因、测试/Schema/签名事实和复查触发条件。两次修复后仍为 `open`、修复需要
   扩大任务范围或改变上游合同时停止。只有全部阻断 finding 均为 `fixed` 或有效 `exception`，即
   `open=0`，并且 `quality_review_gate.py --require-closed` 返回 `0`，才可进入最终验证。
3. **最终验证**：每个受影响构建根在绿路径只执行一次最终验收调用，在同一 Maven/Gradle 调用中
   完成增量编译、相关模块全量测试和 JaCoCo XML。此前的受限编译或定向测试不计入这一次最终
   验收，也不能替代它；最终验收前不得预跑相关模块全量测试或覆盖率。多模块或自定义项目通过
   同一命令的参数合并任务。项目既有全量测试入口已经生成新鲜 JaCoCo XML 时，只读取报告，不
   再次启动测试。只有纯数据载体或生成代码且没有可执行行为时，覆盖率可以不适用，但仍按项目
   需要执行一次最小相关最终编译/测试。多个构建根只有在不共享数据库、端口、生成目录或全局
   状态且资源允许时并行，否则串行；同一构建根的最终验收绝不拆分。
4. **记录**：最终成功或停止时一次性创建并填写 `execution.md`。质量门禁必须使用
   `clean-code-guard found=<n> fixed=<n> exception=<n> open=<n>`，且四项计数一致；限定修复按
   根因组和 finding ID 记录次数，质量例外记录上述依据。完成状态必须为 `open=0`，再执行一次
   `scripts/validate_execution.py`。填写或修正记录不得触发编译、测试、Review、门禁或 JaCoCo。
5. **失败收敛**：最终验收的编译、测试或覆盖率失败时，保留完整失败事实并定位当前已知问题；
   修复后尽可能先用最小范围的 `compile` 或定向测试确认，再重跑同一条最终验收命令。重跑发现
   新的、任务范围内且有明确修复依据的问题时，继续同一收敛循环。固定的是单一最终验收入口，
   不为失败修复设置任意次数上限；但代码、测试、配置和相关外部状态均未变化时不得重跑。只有
   已知失败得到局部确认，或该失败无法局部复现但已有具体修复或外部状态恢复证据时，才能再次
   启动完整验收。覆盖率不足时只为遗漏的可观察行为补测试；无独立行为时简化死分支，纯载体
   误入范围时更正覆盖文件集合。没有新的诊断证据或范围内修复动作时停止。

成功且没有 finding 的固定性能预算是一次并行预检、一次静态批次、一次全量发现 Review、每个
构建根一次最终全量测试与 JaCoCo、一次执行记录写入与校验。存在 finding 时只增加每组最多两次
限定修复、局部复核以及确有风险时的最小中间反馈，不增加第二次全量 Review。中间反馈只由尚未
确认的编译风险或已闭环切片的行为风险触发，并限制在最小相关范围，同一代码与命令不重复执行。
Design/Plan 快速路径不得增加合同调查；任何额外调查、静态复核、全量测试或覆盖率运行必须由
锚点漂移、校验失败或真实运行失败触发，每次失败路径的完整重跑还必须具备上述进展证据，不能
为了保存 RED、GREEN 或阶段性覆盖率证据而增加。

执行模式的常用辅助命令如下；`<base>` 是开始修改前记录的 Git 基线，输出仅供当前执行判断：

```bash
python3 skills/pretty-executing/scripts/quality_resolver.py --repo . --base <base> --path <affected-java-file> --json
python3 skills/pretty-executing/scripts/quality_contract_gate.py --repo . --base <base> --path <affected-java-file>
python3 skills/pretty-executing/scripts/quality_review_gate.py <system-temp>/quality-review.json --path <affected-java-file> --require-closed
python3 skills/pretty-executing/scripts/validate_execution.py docs/pretty/<topic>/execution.md
```

`tests/` 仅存放上述辅助脚本的回归测试，不属于正常执行路径；只有修改辅助脚本时才运行：

```bash
python3 -m unittest discover -s skills/pretty-executing/tests -p 'test_*.py'
```

## Java / JaCoCo 增量覆盖率

`scripts/verify_incremental_coverage.py` 仅支持 Java 项目，并自动识别 Maven 或 Gradle：

- 优先使用 `mvnw`/`pom.xml` 或 `gradlew`/`build.gradle(.kts)` 及项目已有 JaCoCo 配置。
- 项目配置了行或分支阈值时分别使用项目阈值；未配置的维度使用默认增量行覆盖率 `90%`、
  分支覆盖率 `80%`；不把阈值提高到 `100%` 来替代行为测试完整性。
- 每次都用重复的 `--path` 显式传入含本次可执行行为增量的生产 Java 文件。纯数据载体、无逻辑
  accessor 和生成代码不作为覆盖目标并在 `execution.md` 的“覆盖率范围”逐项说明；不能仅按
  `dto` 包名排除，混有校验、转换、默认值、不变量或其他行为的文件必须纳入。
- 脚本根据执行开始时的 Git 基线计算所选文件新增或修改的可执行行；`--run` 只用于最终一次
  相关模块全量测试和报告生成。`--report`/`--report-not-before` 只读取已有报告，绝不启动
  测试。只改测试或没有行为生产增量时明确记录“不适用”。
- 发现没有 JaCoCo 报告、报告过期、源文件无法匹配或覆盖率未达阈值时，执行模式先修复并
  重新验证；脚本输出未覆盖行和部分覆盖分支供判断，不据此机械增加测试。仍无法通过则
  停止并报告。

Maven 的 `--run` 由脚本自动追加按仓库隔离的系统临时目录作为
`-Dmaven.repo.local`，不写用户目录下的 `~/.m2`，因此不需要为本地仓库写权限单独授权。
如果构建必须使用指定的可写仓库，可通过 `--build-arg=-Dmaven.repo.local=<path>` 显式传入；
已有新鲜 XML 时使用 `--report` 只读报告，不启动 Maven。

绿路径唯一一次带测试的命令同时完成相关模块全量测试和 JaCoCo：

```bash
python3 skills/pretty-executing/scripts/verify_incremental_coverage.py \
  --repo . --base <base> --path <behavior-java-file> --run \
  --build-arg=-pl --build-arg=<module> --build-arg=-am \
  --test-task=test --jacoco-task=org.jacoco:jacoco-maven-plugin:report
```

Gradle 多模块项目将任务本身限定到目标模块，例如
`--test-task=:module:test --jacoco-task=:module:jacocoTestReport`；不要同时再传根项目
`test` 任务。

项目自己的全量测试已经生成 JaCoCo XML 时，只读取该报告，不得
使用 `--run`：

```bash
python3 skills/pretty-executing/scripts/verify_incremental_coverage.py \
  --repo . --base <base> --path <behavior-java-file> \
  --report <jacoco-xml-report>
```

## 执行范围与代码生成约束

### i-have-adhd 聚焦实现

将 `$i-have-adhd` 的“明确下一动作、单一当前状态、抑制旁支、完成可见”用于代码生成决策，
不增加额外文档或验证阶段：

- 同一时刻只实现一个可观察行为切片；锁定该切片的公共入口、规则所有者、必要文件和测试观察面，
  完成生产链路与行为测试后再进入下一切片。内部保留完整任务清单；只在编译性或公共行为仍有
  实际不确定性时运行最小范围的中间反馈，不逐文件启动构建，也不维护中间状态证据。
- 当前行为之外的重构、清理、依赖升级和相邻问题是旁支，只有真实阻塞当前实现时才做最小必要修改。
  完成可见于生产代码、行为测试和最终验证结果，不通过过程状态、RED 证据或重复报告制造进度。

### DDL、DML 与数据库边界

- 表、字段和索引等 DDL 只能作为代码库文件交付，不生成针对 DDL 的测试，不直接执行，也不
  通过迁移工具、应用启动、构建插件或测试间接执行。
- Java 与 DDL 混合变更只测试 Java 的可观察行为，并在 `execution.md` 的“未验证范围”和
  “声明限制”中明确 DDL 已交付、未执行、未进行数据库验证。
- 配置数据 DML 始终由人工运维处理，不属于本 Skill 的执行交付物。

### 静态检查时机

质量路由、机械门禁和测试守卫都只做静态检查，不隐式启动测试。它们在最终全量测试前统一执行；
静态 finding 本身不触发完整回归，修复后的编译性或行为风险只使用前文规定的最小中间反馈确认。

## 执行记录与停止条件

每个行为 TASK 的结果、实际落点、审查摘要、行为证据、最终验收命令、执行次数及最终退出码、
未验证范围、覆盖率范围、覆盖率和结论，严格按 `assets/execution.md` 一次性填写。不得记录
测试清单、阶段状态或另写证据协议。失败允许在本次执行中修复并重新验证；无法修复时创建最终
记录并填写 `停止：<原因>`，然后停止。

以下情况直接停止并报告：

- 输入合同、Design、execution plan 与仓库事实冲突，或无法确定真实职责、失败语义、观察面
  和影响范围；
- 目标项目影响文件存在用户未提交修改，或已有 `execution.md`；
- 需要擅自改变公共接口、外部行为、数据所有权、依赖方向、事务、并发、幂等或安全边界；
- 机械门禁失败，或强制质量闭环在限定修复后仍有 `open` finding，且没有新的诊断证据或任务范围内
  有明确依据的修复动作；
- 编译、测试或 JaCoCo 增量覆盖率失败，且没有新的诊断证据或任务范围内有明确依据的修复动作；
- 需要执行 DDL、配置数据 DML、真实数据库操作、部署、发布或人工运维动作。

停止时只按 `assets/execution.md` 一次性记录已经发生的事实、未验证范围和恢复/返回原因，不
自动覆盖或回滚用户已有修改。若预检发现已有 `execution.md`，不覆盖该文件，只向用户报告。
