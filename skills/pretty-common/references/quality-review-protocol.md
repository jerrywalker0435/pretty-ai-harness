# 独立质量审查协议

高风险 Design 和 Apply 的真实可执行产物必须由独立 Reviewer 审查。Reviewer 使用独立上下文，不继承 Writer 的解释或自评；只接收批准合同、候选内容、必要调用链、共享基线和已命中专项 Skill。无法获得适用独立 Reviewer 时不能声明质量 Gate 通过。非权威 Preview 不启动独立 Reviewer。

## 审查对象

- Design Reviewer：PRD/Design、职责链路、合同、影响 TASK、公共验证入口和观察面；不审最终实现细节。
- Apply Reviewer：真实增量代码、测试、配置或 Schema、Design 规范基线及完整调用链。
- Apply Reviewer 检查风险路由完整性、职责与依赖方向、规则唯一归属、边界与失败语义、类型、日志所有权、测试观察面和 AI 生成完整性。

每条语义 finding 必须可追踪，并同时写明：位置（文件、TASK 或 symbol）、违反的合同或标准、可观察后果、具体修正和修正后的验证方式。机械 finding 复用扫描器的 code、位置、消息与 fingerprint。缺少这些字段的泛泛建议不算 finding，不能阻断交付。

## 临时证据

详细审查证据写入本次运行的临时目录，不进入 Design、Preview 或独立 evidence 文档。Design 阶段的临时证据不作为 Apply 前置产物；Apply 遇到高风险 Design 时重新取得 Design Reviewer 证据。Execution 只把实际路由、修复摘要和最终结论写入 `execution.md`。证据使用 JSON：

```json
{
  "candidate_sha256": "<候选内容摘要>",
  "reviewer": "<独立 reviewer 标识>",
  "independent": true,
  "contract_sources_sha256": {},
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

`guards` 只用于 Apply；Design Reviewer 不要求代码 Guard。Design Reviewer 的候选摘要绑定 PRD、Design 和显式合同来源内容，`contract_sources_sha256` 使用相同仓库相对路径与内容摘要；Apply 重审时必须传入同一来源集合。

候选内容改变后旧证据失效。机械 `error` 不能豁免；`review_required` 必须修复后消失，或由 Reviewer 以具体 symbol、合同事实和 `evidence` 接受。注释存在、输入规范化以及 `normal`/`special` 等相对分类命名都不能凭 Writer 自述放行。`以后处理`、`改动较小`、`不影响功能`不是依据。

Writer 用 `--scan-only` 获取候选 findings；最终放行必须移除该参数并提供匹配当前候选的独立审查证据。`--scan-only` 不是可交付的质量结论。

## 修复与停止

Writer 根据 findings 修复后，只重跑受影响机械规则和目标测试，并由同一 Reviewer 复核修复增量；只有修复改变完整候选结论时才重跑对应编译、回归、覆盖率或完整审查。只要每轮关闭问题、缩小范围或产生新证据就继续，不设固定轮次。相同阻断原因持续重复、已穷尽安全路径且没有新证据时停止；不得降低规则、复用旧结论或把未解决问题写成完成。
