# 强制质量闭环合同

本合同只用于执行模式中非平凡生产代码的一次全量发现 Review 及其限定修复。Review 在
`docs/pretty/<topic>/tmp/` 写入 JSON；该文件不属于项目交付物，也不提交到仓库。

## Review JSON

以下示例表示一个 finding 已完成一次限定修复后的最终状态：

```json
{
  "review_type": "full-discovery",
  "full_review_count": 1,
  "routes_applied": ["clean-code-guard", "tdd"],
  "reviewed_paths": [
    "module/src/main/java/example/OrderService.java",
    "module/src/main/java/example/OrderRepository.java"
  ],
  "type_necessity_checks": [],
  "type_necessity_not_applicable": "本次仅修复 loadOrder 的异常传播，未新增类型或修改既有类型职责",
  "cqs_checks": [
    {
      "method": "module/src/main/java/example/OrderService.java:42#loadOrder",
      "call_chain": [
        "module/src/main/java/example/OrderService.java:42#loadOrder",
        "module/src/main/java/example/OrderRepository.java:18#findById"
      ],
      "side_effects": [],
      "caller_consumption": [],
      "return_use": "mapped into the response",
      "finding_ids": [],
      "status": "clear"
    }
  ],
  "findings": [
    {
      "id": "QF-001",
      "source": "clean-code-guard",
      "rule": "15",
      "severity": "blocking",
      "location": "module/src/main/java/example/OrderService.java:42#loadOrder",
      "evidence": "catch Exception returns null and hides a repository outage",
      "allowed_scope": ["module/src/main/java/example/OrderService.java#loadOrder"],
      "repair_group": "QG-001",
      "status": "fixed",
      "attempts": 1,
      "resolution": "removed the fallback so the storage failure propagates",
      "verification": "targeted test and mechanical gate passed"
    }
  ]
}
```

`routes_applied` 记录本次 Review 实际执行的质量路由。存在非平凡生产变更时必须包含
`clean-code-guard`；其他项来自 `quality_resolver.py` 的命中结果及当前明确选择的适用路由。最终
执行门禁会拒绝缺少该字段或未执行通用 `clean-code-guard` 的生产代码完成记录。
该字段必须是非空且不重复的 Skill 名称列表；没有专项命中时也填写 `clean-code-guard`。

- ID 使用连续的 `QF-001` 形式，在本次执行中保持稳定。
- `reviewed_paths` 覆盖最终实际修改、必要调用链证据及明确允许限定修复的生产、测试和其他代码文件；
  命令中为每个路径重复传入 `--path`，CQS 位置、finding 位置及允许范围都不得逸出该集合。
- `source` 使用 `clean-code-guard`、`pretty-executing-quality`（本地质量补充）、
  `pretty-executing-test-guard`（内置测试审查）或实际命中的专项路由名。
  `pretty-executing-quality` 和 `pretty-executing-test-guard` 均为内置规则的来源标签，不是独立 Skill，
  不加入 `routes_applied`；测试审查规则见 [SKILL.md](../SKILL.md) 的“强制质量闭环”步骤。
- `location` 和 `allowed_scope` 必须定位到 `path#symbol`；行号只作为辅助证据。
- 同一根因使用相同且稳定的 `QG-001` 形式 `repair_group`；`attempts` 表示该组共享的累计修复次数，
  组内所有 finding 必须一致且最多为两次。
- `fixed` 必须记录至少一次修复、实际 resolution 和 verification。
- `exception` 必须包含 `reason`、`facts` 和 `revisit_trigger`；普通实现偏好不能构成例外。
- `open` 表示尚未关闭；达到两次修复、需要越界或没有新证据时保持 `open` 并停止执行。

### 控制流终点 Review 规则

全量 Review 必须检查每个新增或修改方法的控制流终点：方法自然到达末尾时，禁止保留无条件尾部
`return;`；仅当 `return` 位于仍有后续可执行语句的方法中，或表达明确的提前结束语义时允许。
此项使用 `source=clean-code-guard`、`rule="21"`，并在 finding 中提供具体的
`path:line#symbol` 位置和控制流证据。未修复时 `status="open"`，`--require-closed` 必须拒绝进入
最终验收；例外仍须满足本合同的 `reason`、`facts` 和 `revisit_trigger` 要求。

## 整体实现简洁性核验

在同一次全量 Review 中按[简单实现优先](quality-principles.md#简单实现优先)从公共入口核对
实际受影响链路：新增或修改的类型、方法、分支和转换是否有当前用途；是否存在无独立语义的
转发与包装、重复决策/校验/规范化、死分支或为未来扩展增加的抽象。结合实际调用方和必要边界
判断整体理解成本；单调用方、方法行数、参数数量或分支语法本身不构成违规。
复用实现与 CQS 核验中已读取的定义和调用方，只定向补查缺少的必要证据。

发现冗余时，`evidence` 必须引用具体定义与调用方，说明可采用的直接实现、合并或删除，以及
为何不损失业务行为、必要约束或边界。优先使用实际适用的 `clean-code-guard` 或专项路由规则；
没有对应规则时使用 `source=pretty-executing-quality`、`rule=UNNECESSARY-STRUCTURE`。不得仅以
“代码太多”“看起来复杂”或偏好某种模式记录 finding，也不得在修复时以更多抽象替代原有冗余。

沿用现有 finding、类型必要性记录和限定修复流程，不新增逐方法 JSON 清单或第二次 Review。
复核实际修复的 symbol 与调用方，确认整体简化且合同保持；门禁只校验证据结构和关闭状态，
门禁通过不替代本项语义核验。

## 注释与日志信息充分性核验

在同一次全量发现 Review 中，按[信息充分性原则](quality-principles.md#注释与日志的信息充分性)
检查实际受影响链路。逐一核对本次新增或修改的 RPC/HTTP 外部调用及 MQ 收发是否逐次留下安全、
可关联的结果日志（已有框架日志可复用）；核对关键操作的结果、影响预期结果的跳过、降级、
部分成功和异常记录边界，以及代码无法表达的业务原因、隐含约束、调用合同和兼容取舍；同时
核对现有观测与注释，避免重复。

满足补充条件却缺失时，记录阻断 finding：`source=pretty-executing-quality`，`rule` 使用
`COMMENT-INFORMATION-GAP` 或 `LOG-INFORMATION-GAP`。`evidence` 必须说明缺少的信息、可能造成的
维护/调用误判或无法定位的运行问题，以及现有代码表达或观测为何不足；`location` 指向应补充的
具体 symbol，`allowed_scope` 限定必要修复位置。外部调用或 MQ 收发缺少逐次日志时须指出具体边界
与缺失字段；“注释太少”“日志太少”不构成有效 finding。

沿用现有 `open / fixed / exception` 和限定复核流程，不新增独立 Review、JSON 清单或机械扫描。
复核补充内容是否真实、足够且无重复；不以数量、比例或正则判定信息充分性。

## CQS 调用链核验

每次全量发现 Review 都必须提供顶层 `cqs_checks` 数组。数组必须逐一列出本次新增或修改的非 `void`
生产方法；每个条目包含：

当本次没有新增或修改的非 `void` 生产方法时，`cqs_checks` 可以为空，但必须同时提供
`cqs_not_applicable` 对象，包含非空 `reason` 和 `facts`，明确说明为什么没有适用方法。不能省略
`cqs_checks` 或用空数组静默跳过核验。

- `method`：被核验的方法，使用 `path:line#symbol` 或 `path#symbol`。
- `call_chain`：从该方法到必要副作用边界的调用链，至少包含 `method` 自身；每个位置都使用
  `path#symbol`，且路径必须属于 `reviewed_paths`。
- `side_effects`：副作用位置数组。每项必须包含非空 `kind`（例如 `persistence`、`remote-call`、
  `message-send` 或 `state-modification`）和 `location`。
- `caller_consumption`：调用方消费返回值的位置数组。每项必须包含 `location`、非空 `use` 和
  `evidence`；当存在副作用时不得为空。
- `return_use`：该方法返回值在调用链中的实际用途；不得使用“unknown”或其他空泛占位词。
- `finding_ids`：该核验关联的 `QF-###` finding ID；没有 finding 时为空数组。
- `status`：`clear`、`finding` 或 `exception`。

`source=clean-code-guard` 且 `rule=4` 的 finding 还必须包含非空的
`side_effect_locations` 和 `caller_consumption_locations` 数组；两者都使用
`path:line#symbol` 或 `path#symbol`，并分别覆盖该 CQS 条目的副作用和调用方消费位置。
每个 rule 4 finding 都必须被至少一个 `cqs_checks[].finding_ids` 引用，不能游离在 CQS 清单之外。

`status=clear` 只能用于 `side_effects` 为空且 `finding_ids` 为空的条目。存在副作用时，必须完成调用
方消费核验，并将状态设为 `finding` 或 `exception`；两种状态都必须关联 finding。副作用与返回值并存
时按 `clean-code-guard` 第 4 条记录 finding；返回值仅用于日志、调试或被丢弃不能豁免。finding 的
证据必须同时引用 `side_effects[].location` 与 `caller_consumption[].location`。合同明确要求返回执行
结果时，按既有质量例外机制记录；`status=exception` 只能关联 `status=exception` 的 finding，不得
自行豁免。未完成调用方核验，不得将条目标为 `clear` 或关闭 Review。

门禁校验 `cqs_checks` 的字段、位置范围、状态约束和 finding 关联；它保证 Review 不能缺少结构化 CQS
证据，但不替代 Reviewer 对动态分派和间接调用的语义判断。

## 生产类型必要性核验

Reviewer 根据实际 diff 逐一核对本次新增或修改职责的生产类型，读取定义及实际调用方，并回答：

- 类型承载了什么独立规则、不变量或必要的跨层契约？
- 调用方是否创建对象后立即拆出字段，再完成同一项决策？
- 删除该类型后，是否会丢失业务约束、破坏分层，或导致规则重复？
- 它是否只是对已有实体和可直接计算的标记进行包装？

如果只有包装和转发作用，删除后不损失上述价值，必须按实际命中的质量路由记录阻断 finding；
未命中专项路由时使用 clean-code-guard 的适用规则。不得仅因业务命名、符合 CQS 或出现在 Design
中判定合规。两字段、单调用方及 DTO 后缀不构成违规或豁免；合法 DTO、值对象和端口可以凭协议、
不变量或分层证据证明必要性。Reviewer 确认路由适用性并将其具体规则落实到证据和 finding 的
source/rule，不为本核验增加专项 Skill 的构建流程。

复用实现阶段和 CQS 核验中已读取的定义及调用方，仅补查缺少的必要证据。顶层必须包含
`type_necessity_checks`，每个相关类型一条紧凑记录：

```json
{
  "type": "module/src/main/java/example/OrderRequest.java:10#OrderRequest",
  "caller_locations": ["module/src/main/java/example/OrderController.java:24#create"],
  "responsibility": "承载已发布下单 API 的请求字段",
  "necessity_evidence": "序列化入口按发布的请求 Schema 绑定该类型，隔离外部协议与领域实体",
  "caller_usage": "Controller 读取字段转换为领域输入；拆字段用于边界转换，没有重做领域决策",
  "deletion_impact": "直接暴露领域实体会将内部字段纳入外部协议，破坏协议隔离",
  "wrapper_assessment": "纯数据载体，但承担必要的外部协议契约",
  "contract_constraints": "发布的请求 Schema 固定；当前授权不包含 API 变更",
  "conclusion": "necessary",
  "finding_ids": []
}
```

- `type` 与 `caller_locations` 使用 `path:line#symbol` 或 `path#symbol`，路径纳入
  `reviewed_paths` 和既有 `--path` 集合。只读证据文件纳入 Review 不代表获得修改授权。
- 六项文字证据均必填，不使用 unknown、todo 等占位。没有合同限制时明确写明；
  `contract_constraints` 如有 Design/Plan 约束，应引用文档路径、章节及具体约束。
- 没有直接调用方时允许 `caller_locations=[]`，但必须提供 `no_callers_evidence`，说明定向检索
  范围和结果，或框架/外部消费者事实，不能伪造调用方。
- `conclusion=necessary` 时 `finding_ids=[]`；`unnecessary` 必须关联实际存在的 finding。
  结论是发现时的语义判断，修复状态由 finding 表达；删除类型后仍保留原记录、位置及关联 ID，
  在 finding 的 resolution/verification 中说明授权、修复及验证事实。
- 无相关类型时，数组为空且必须提供非空 `type_necessity_not_applicable`，说明实际 diff 为什么
  不适用；有记录时不得同时声明不适用。纯数据载体的测试或覆盖率豁免不等于新增类型免审。

Design/Plan 中的类型仍须审查。发现不必要时记录 finding，并在 `contract_constraints` 区分内部
实现建议与明确的保留要求或业务合同。仅在示例或 Files 中出现的内部类型可在既定范围内直接
简化；删除会违反明确保留要求或业务合同时，只有当前用户已授权该变化才能实施，否则保持
open，报告具体约束并停止请求方向。仅“Design 指定”不能关闭为 exception；不得自行改写
上游文档。其他真实不可修改合同的质量例外仍按既有机制提供事实与复查条件，由 Reviewer 判断。

门禁仅检查已申报记录的字段完整性、位置范围、类型重复、结论及 finding 引用一致性；类型是否
漏列、必要性、路由适用性和删除授权由 Reviewer 核验。不扫描 Java 类型、不冻结自动清单，
不增加命令参数或第二次全量 Review。限定修复只更新关联 finding 和受影响类型的证据。

## 门禁调用

全量发现 Review 后先检查结构；每次限定修复只更新对应 finding 和受影响核验记录：

```bash
python3 skills/pretty-executing/scripts/quality_review_gate.py \
  docs/pretty/<topic>/tmp/quality-review.json \
  --path module/src/main/java/example/OrderService.java \
  --path module/src/main/java/example/OrderRepository.java
```

全部 finding 关闭后，用相同生产文件集合执行阻断检查；只有退出码为 `0` 才进入最终验证：

```bash
python3 skills/pretty-executing/scripts/quality_review_gate.py \
  docs/pretty/<topic>/tmp/quality-review.json \
  --path module/src/main/java/example/OrderService.java \
  --path module/src/main/java/example/OrderRepository.java \
  --require-closed
```

将命令输出的唯一汇总行原样写入 `execution.md` 的“质量门禁”。不把完整 finding、测试清单或阶段
状态复制到执行记录。

限定修复 CQS finding 时，返回值仅供日志使用应优先评估将执行方法改为 `void`，并由掌握执行结论的
位置记录日志；不得为满足 CQS 新增结果查询、共享状态或额外存储。
