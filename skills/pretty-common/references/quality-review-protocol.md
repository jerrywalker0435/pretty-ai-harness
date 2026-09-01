# Apply 最终独立审查协议

只有 Apply 的真实可执行产物强制独立 Reviewer。Design 由机械校验和用户对业务/技术合同的审批负责；Design 不生成 Reviewer receipt。

## 唯一 Reviewer 与启动条件

- 每次 Apply 只启动一名最终独立 Reviewer，不启动 Design Reviewer、切片 Reviewer 或第二名专项 Reviewer。
- Reviewer 使用独立上下文，不继承 Writer 的解释或自评；无法获得独立 Reviewer 时不能声明 Apply 完成。
- 机械 `error`、编译、目标测试、相关回归、测试实际执行和正式增量覆盖率全部通过，且证据绑定同一冻结候选后，才能启动 Reviewer。Reviewer 期间 Writer 不主动修改。
- Quality Resolver 派生的风险由同一 Reviewer 统一审查；风险可以有不同语义归属 Skill，但不能因此拆成多个 Reviewer。

## 审查范围

Reviewer 读取从 topic tmp run 内 `execution-state.json` 起始 HEAD 推导的完整运行相关 Diff、当前 Design、完整调用链、执行矩阵及 build/tests/coverage 证据，检查：

- Design 合同与真实实现是否一致：TASK、公共入口、结果、失败语义、观察面、职责、数据所有权和依赖方向；
- 状态、事务、并发、幂等、恢复、不可逆副作用、类型、异常、日志和边界替身；
- Quality Resolver 是否覆盖新增文件、Symbol、依赖和边界事实，Writer 是否遵守共享质量基线；
- 测试是否通过公共入口证明业务结果，新增/修改测试是否真实执行，证据是否来自同一候选。

## Finding 与 receipt

语义 finding 必须包含位置、风险 ID、违反的合同或事实约束、可观察后果、必须修正的内容和修正后的验证方式；机械 finding 复用扫描器的 code、位置、消息和 fingerprint。只输出阻断问题和逐条有证据的例外，不输出代码风格、命名偏好或非阻断建议。

Apply receipt 至少包含 `candidate_sha256`、独立 Reviewer 标识、`independent: true`、`risks`（Resolver 风险及 owner）、`guards`、`pre_review_gate`、`scope_extensions`、`accepted_findings` 和 `blocking_findings`。`pre_review_gate` 必须绑定当前 `quality_candidate_sha256`、`build_candidate_sha256`、`test_evidence_sha256` 和 `coverage_evidence_sha256`；具体 JSON 字段由 [Apply Gate](../../pretty-executing/references/quality-contract-gates.md) 与校验脚本定义。

候选内容或任一 Gate 摘要变化后旧 receipt 立即失效。机械 `error` 不能豁免；`review_required` 只能由 Reviewer 逐条以具体 Symbol、合同事实和 evidence 接受。修复必须由 Apply `reopen` 显式恢复 Lane 写权限，再复核修复增量并按证据依赖重跑受影响 Gate；公共合同、依赖方向或观察面变化时返回 Design。相同阻断原因持续重复且无新证据时停止，不降低规则或复用旧结论。
