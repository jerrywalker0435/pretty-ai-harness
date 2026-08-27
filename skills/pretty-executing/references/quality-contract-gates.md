# Apply 质量合同 Gate

本文件只定义 Apply 的 Gate 时机、证据结构和绑定关系。QP 内容见共享质量基线，风险 owner 见质量路由/registry，阈值只从 `quality_registry.py` 读取。

## 1. 首次编辑前

在 Candidate Lane 创建并写入代码前，Harness 必须验证：

- 当前 topic 的 `prd.md`、`design.md` 可读，Design TASK 可载入执行矩阵；Execution 不重新运行 Design 校验或审查；
- 目标运行路径干净，说明性文档不影响 Apply；
- 当前 run 有 `execution-matrix.json` 和 `execution-state.json`，状态、起始 HEAD、Design 摘要、共享规则包摘要和路径快照一致；
- `execution_contract.py` 的 `contract_preflight` 四个区域均为 `clear` 或有理由的 `not_applicable`；
- 骨架矩阵先由 TASK/切片合同组成，再由 `quality_resolver.py` 派生并绑定 `resolver_rules`、`resolver_risks`；Writer 不得自报、删除或降级路由；
- 最小相关基线已运行并记录历史失败；新增测试的禁用作用域已扫描。

预检缺失、冲突或无法从真实代码落实时，硬停止并返回 Design；不得补写 Design 或先写代码。

## 2. Slice Contract 与 Fast Gate

每个 Java 行为切片至少包含：

`id`、`paths`、`production_symbols`、`test_entry`、`input_invariants`、`boundary_substitutes`、`result_assertions`、`nearest_neighbors`、`coverage_obligations`、`resolver_rules`、`resolver_risks`、`depends_on`、`non_goals`。

`production_symbols`、`result_assertions`、`coverage_obligations`、`resolver_rules` 不得为空。纯声明/DDL TASK 使用空 `behavior_slices` 并填写 `non_behavior_reason`。

每个切片固定执行：

```text
RED → 最小 GREEN → checkpoint → 共享机械扫描 → 目标测试实际执行
→ 必要时局部编译 → slice-gate receipt → 下一个切片
```

Slice Fast Gate 不运行正式 JaCoCo、全量回归或独立 Reviewer。目标测试命令已完成必要编译时，不得重复执行等价编译；无可执行目标测试或构建系统不会完成必要编译时，才补局部编译。不可豁免的机械 `error`、越界写集、禁用测试、缺失观察面或失败测试阻断下一切片。

每个切片第一次 GREEN 后固化不可覆盖的 `first_attempt`：候选摘要、机械 finding、测试结果和修复次数。修复通过新候选摘要记录；旧证据不可复用。

## 3. 完整候选 Gate

所有切片通过后停止 Writer 主动修改，以 `start_head` 推导包含新增、修改、删除、重命名、二进制和未跟踪路径的完整 Diff；topic run 和 Candidate Lane 不进入目标范围。先运行完整机械 Gate，`error=0` 后冻结候选。

冻结候选依次执行：

1. 受影响模块必要编译、目标测试和相关回归；新鲜报告必须证明新增/修改测试实际执行；
2. 正式增量 JaCoCo；策略从 registry 读取，矩阵只能提高不能降低；无生产 Java 增量才允许结构化 `not_applicable`；
3. 非平凡生产 Java 的一次 `clean-code-guard`，receipt 绑定候选；
4. objective Gate 汇总。一个真实命令可以通过 `satisfies` 字段声明同时满足多个 Gate，但必须有真实报告，不能为凑 evidence 重复或虚标命令。

最终证据必须来自同一个 `start_head`、Design SHA、execution-matrix SHA、shared-bundle SHA、resolver SHA 和冻结 `candidate_sha256`。`quality.json`、`build.json`、`tests.json`、`coverage.json` 的 evidence 摘要不可跨 run 拼接。

## 4. Reviewer 与 Promotion

objective Gate 全部通过后才启动一名独立 Reviewer。receipt 至少绑定：

```json
{
  "candidate_sha256": "<frozen-candidate>",
  "independent": true,
  "risks": "<current-risk-set>",
  "guards": ["clean-code-guard"],
  "pre_review_gate": {
    "quality_candidate_sha256": "<quality-candidate>",
    "build_candidate_sha256": "<build-candidate>",
    "test_evidence_sha256": "<tests-evidence>",
    "coverage_evidence_sha256": "<coverage-evidence>"
  },
  "blocking_findings": []
}
```

`review_required` 必须逐条给出 Symbol、合同事实和 evidence；机械 `error` 不可豁免。Reviewer 或 objective Gate 失败必须由 `apply_run.py reopen --reason ...` 显式恢复写权限；修改后重新计算候选和受影响证据。

只有 `apply_run.py promote` 可以修改目标工作区。Promotion 前检查目标 HEAD、目标运行路径、冻结 patch 和候选摘要，先 `git apply --check`，应用后重新计算目标 Diff。摘要不一致立即停止并保留 Lane。

## 5. 证据与 DDL 边界

证据链固定为：

```text
Design + start HEAD → matrix → shared bundle → resolver
→ first-attempt metrics → frozen candidate
→ quality/build/test/coverage → Reviewer receipt → Promotion
```

结构性 DDL 只能作为代码库文件交付，报告写明“已交付、未执行、未进行数据库验证”；不得通过迁移、应用启动、构建插件、集成测试或数据库客户端间接执行。配置数据 DML、事件定义、模板关系、白名单、种子/reference data、激活/禁用/回滚由人工运维处理。
