# Pretty 四阶段共享合同

本文件只定义跨阶段不变量；每个阶段的操作顺序、停止条件和交付由对应阶段 Skill 定义。

## 四阶段边界与回退

```text
[用户批准 PRD] -> [Design] -> [用户批准 Design]
  -> [Plan] -> [用户批准 Plan] -> [Execution] -> [交付]
```

- PRD 决定问题、非目标、外部可观察规则与验收结果，定义 `REQ`、`AC`；不决定实现。
- Design 决定职责、依赖方向、跨边界合同、数据与一致性、兼容策略和验证边界，按需定义 `DEC`；不决定逐文件实施。
- Plan 依据真实源码提出可审查实现和连续 `TASK`；不改变上游合同，不实施代码。
- Execution 实施已批准 Plan；不改变业务结果、Design 合同或 Plan 测试边界。
- 下游发现上游合同错误时，停止并返回最早受影响阶段；上游重新批准后，从首个受影响阶段恢复。
- PRD、Design、Plan 各请求一次用户 Review 并停止；Execution 按真实状态交付，不新增审批。

## 澄清规则

PRD 与 Design 先调查仓库、协议、领域文档、配置、相邻行为和测试。仅当以下条件同时成立时使用 `grilling`：

1. 存在两个以上会产生不同结果的真实答案；
2. 答案会改变业务结果或高影响技术合同；
3. 仓库和既有文档无法唯一裁决；
4. 不解决会迫使下游代做决定。

一次只解决一个决策，给出具体场景、2–3 个结果、主要后果和推荐答案；将结论写入 `REQ/AC` 或 `DEC`，不保存问答审计。Plan 不调用 `grilling`：业务结果未知返回 PRD，技术合同未知返回 Design，仓库事实自行调查，低风险外部等价实现给出推荐提案。

## 领域文档归属

根目录存在 `CONTEXT-MAP.md` 时，定位并读取相关 `CONTEXT.md`；否则读取根目录已有 `CONTEXT.md`。文件不存在不默认创建，也不构成阻塞。

- PRD 的核心术语、业务身份、生命周期、状态、不变量、归属或关系发生变化时，使用 `domain-modeling` 同步领域语言，不创建 ADR。
- Design 的实体、值对象、聚合、数据所有权、上下文关系或领域事件发生变化时，使用 `domain-modeling` 同步相关领域文档和必要 ADR；若改变外部结果，先返回 PRD。
- Plan 与 Execution 只消费领域文档，不调用 `domain-modeling`，不更新 `CONTEXT.md`、`CONTEXT-MAP.md` 或 ADR。
- 只读评审只报告领域问题，不修改领域文档。

## 文档与追溯

- 制品固定在 `docs/pretty/<topic>/`，`<topic>` 使用小写 kebab-case；只使用 `prd.md`、`design.md`、`plan.md`、`execution.md`。
- `REQ-<nnn>`、`AC-<nnn>`、`DEC-<nnn>`、`TASK-<nnn>` 从 `001` 连续编号；TASK 是 Plan 与 Execution 间唯一执行身份。
- `REQ/AC/DEC` 就近追溯到实际相关内容，不以编号代替自然语言结论。
- 使用“用例”“逐用例 TDD”“当前用例最小 GREEN”“返回相应用例修正”；用例在 TASK 内使用可读短名称，不新增 `CASE-*` 或 `STEP-*`。
- 团队证据使用仓库相对路径、`Class#method`、类型名、配置键或团队可访问的稳定文档；不使用个人绝对路径或私有本地资料。
- Git 历史负责版本记录；文档不维护审批元数据、时间戳、哈希链、证据指纹、Skill 调用清单或终端日志。
- 删除模板中不适用的条件块；不得保留 `TODO`、`TBD`、`FIXME`、待定、占位或虚假内容。

PRD、Design、Plan 支持只读评审：严格不修改、移动或复制文档，不更新领域文档，不生成下游制品。Plan 只读评审仅接受标准路径，并要求同目录上游和可定位的真实源码。只读评审结论不等于用户批准。

## UT-only 与验证边界

- Pretty 只能新增或扩展快速、确定、无基础设施依赖的 UT；不得新增或扩展集成、契约、端到端、Spring slice、Testcontainers 或嵌入式基础设施测试。
- UT 使用真实被测规则；Repository、Gateway、远程客户端、时钟、随机性等边界可以 mock/fake/stub。主要断言业务结果、状态变化或完整边界请求。
- SQL、配置、文档、生成物和纯机械修改使用静态解析、编译、搜索不变量或确定性脚本，不制造 UT。
- Pretty 内验证包括 UT、编译、快速静态检查、机械校验和适用覆盖率。
- Pretty 外验证包括真实数据库、真实服务、凭证、基础设施语义、部署、人工联调和独立 Reviewer；缺失不阻塞完成，但必须降低声明。
- 覆盖率优先继承仓库政策；无政策时，可由 UT 覆盖的新增或实质修改 Java 行为默认行 90%、分支 80%。覆盖率不替代行为和断言质量。

## 质量 Skill 路由

只加载真实风险命中的能力；有效发现直接进入需求、设计、Plan 提案或代码，不保存调用清单。

| 阶段 | 触发场景 | 使用 |
| --- | --- | --- |
| PRD/Design | 领域模型发生上述变化 | `domain-modeling` |
| Design/Plan/Execution | 对象职责、协作、封装、聚合或继承变化 | `121-java-object-oriented-design` |
| Design/Plan | 值对象、泛型、类型层次、金额类型或 primitive obsession | `122-java-type-design` |
| Design/Plan/Execution | 服务职责、端口、依赖方向或扩展点变化 | `solid-principles` |
| Design/Plan | 模块接口、seam、adapter 或测试表面需要设计 | `codebase-design` |
| Design/Plan | 已证明存在构造、替换、通知或适配变化轴 | `design-patterns` |
| Plan/Execution | 行为测试提案或实施 | `tdd` |
| Execution | 行为保持重构或明确结构整理 | `refactor` |
| Plan/Execution | 编写非机械生产代码提案或实现 | `clean-code-guard` live mode |
| Execution | 实际 Java diff 命中 null、异常、并发、资源、性能或 API 合同风险 | `java-code-review` |

当前阶段没有可替代的必需 Skill 时停止并说明。领域、对象、类型、SOLID、接口、模式和 Java 专项能力均按实际风险触发；`tdd` 对行为 Plan/Execution 必需，`refactor` 只在确有整理目标时必需。

## 状态、声明与 Git 边界

- Execution 最终状态只能是 `完成`、`停止：<原因>`、`返回 Plan / Design / PRD：<原因>`。
- 只声明实际执行的验证范围；外部未验证项不得称为已验证。
- 工作区可以不洁净，但必须保留用户改动；同一位置无法安全区分且有覆盖风险时停止。禁止自动 stash、reset、rebase 或覆盖用户内容。
- commit、push、创建 MR、合并和发布均需用户另行授权。
