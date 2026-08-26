# 独立质量审查协议

所有 Design 和 Apply 的真实可执行产物必须由独立 Reviewer 审查。Reviewer 使用独立上下文，不继承 Writer 的解释或自评。无法获得适用独立 Reviewer 时不能声明对应质量 Gate 通过。非权威 Preview 不启动独立 Reviewer。

## 审查对象

- Design Reviewer：始终只有一名，固定审查模块边界、运行时风险和行为验证；模块边界包括 Execution 与人工运维的交付归属，必须阻断把配置 DML、数据库执行、发布、激活或回滚错误分配给 Execution；不审最终实现细节，不启动专项 Reviewer。
- Apply Reviewer：真实增量代码、测试、配置或 Schema、Design 规范基线及完整调用链。
- Apply Reviewer 检查风险路由完整性、职责与依赖方向、规则唯一归属、边界与失败语义、类型、日志所有权、测试观察面和 AI 生成完整性。

Design Reviewer 只输出阻断 finding；代码风格、命名偏好、泛化建议和非阻断优化不进入输出。每条阻断 finding 必须同时写明位置、所属风险面、违反的批准合同或事实约束、可观察后果、必须修正的内容和修正后的验证方式。Apply Reviewer 的语义 finding 使用相同的可核查字段；机械 finding 复用扫描器的 code、位置、消息与 fingerprint。缺少必要字段的意见不算 finding。

## 临时证据

调用 Pretty Design、Dry Run 或 Apply 即授权同一次运行创建、更新和清理必要的临时证据，无需逐文件确认，包括候选摘要、Reviewer receipt、执行矩阵、校验日志、编译/测试/覆盖率证据、构建中间产物和 `.execution-state.json`。正常完成或明确停止后清理；意外中断只保留恢复同一次 Apply 所需的 `.execution-state.json`。该授权不允许覆盖或删除非本次运行创建的用户文件，也不扩大配置 DML、DDL 执行、提交、推送、部署、外部系统写入或受保护路径权限。

详细审查证据写入本次运行的临时目录，不进入 Design、Preview 或独立 evidence 文档。Design receipt 不作为 Apply 输入，Execution 不读取、不复用也不重新生成 Design Reviewer 证据。Execution 只把 Apply 的实际路由、修复摘要和最终结论写入 `execution.md`。

Design Reviewer receipt 使用最小运行态格式：

```json
{
  "candidate_sha256": "<prd.md + design.md 摘要>",
  "reviewer": "<唯一独立 Reviewer 标识>",
  "independent": true,
  "risk_surfaces": {
    "MODULE_BOUNDARY": {"checked": true},
    "JAVA_RUNTIME_RISK": {"checked": true},
    "BEHAVIOR_TEST": {"checked": true}
  },
  "blocking_findings": []
}
```

它只证明本次冻结候选由一名独立 Reviewer 检查了三个固定风险面且没有未关闭阻断项，不承担跨会话追踪。PRD 或 Design 改变后 receipt 立即失效。

Apply Reviewer 证据使用以下格式：

```json
{
  "candidate_sha256": "<候选内容摘要>",
  "reviewer": "<独立 reviewer 标识>",
  "independent": true,
  "risks": [
    {"id": "JAVA_OOD", "owner": "121-java-object-oriented-design", "evidence": ["path#symbol"]}
  ],
  "guards": ["clean-code-guard"],
  "scope_extensions": [
    {"path": "module/src/main/java/example/Adjacent.java", "reason": "保持已批准接口的编译一致性"}
  ],
  "accepted_findings": [
    {
      "fingerprint": "<机械 finding 摘要>",
      "reason": "<合同事实和适用例外>",
      "evidence": ["<批准协议、Schema、仓库规则或稳定 symbol>"]
    }
  ],
  "blocking_findings": []
}
```

`guards`、`risks`、`scope_extensions` 和 `accepted_findings` 只用于 Apply。

候选内容改变后旧证据失效。机械 `error` 不能豁免；`review_required` 必须修复后消失，或由 Reviewer 以具体 symbol、合同事实和 `evidence` 接受。注释存在、输入规范化以及 `normal`/`special` 等相对分类命名都不能凭 Writer 自述放行。`以后处理`、`改动较小`、`不影响功能`不是依据。

Writer 用 `--scan-only` 获取候选 findings；最终放行必须移除该参数并提供匹配当前候选的独立审查证据。`--scan-only` 不是可交付的质量结论。

## 修复与停止

Design Writer 修订后，由同一 Reviewer 只复核原阻断项及修订直接引入的问题；不重新检查未改动内容。原 Reviewer 不可用时，新 Reviewer 对当前完整候选重新执行三个风险面审查。

Apply Writer 根据 findings 修复后，只重跑受影响机械规则和目标测试，并由同一 Reviewer 复核修复增量；只有修复改变完整候选结论时才重跑对应编译、回归、覆盖率或完整审查。只要每轮关闭问题、缩小范围或产生新证据就继续，不设固定轮次。相同阻断原因持续重复、已穷尽安全路径且没有新证据时停止；不得降低规则、复用旧结论或把未解决问题写成完成。
