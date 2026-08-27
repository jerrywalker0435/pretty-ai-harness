# Execution Gates

本文件只定义 Execution 放行条件。代码原则、质量路由和审查协议使用 `pretty-common` 的唯一共享来源。

## 输入与范围

- 当前主题只有一个有效 Plan，TASK、Files、核心代码和测试边界完整。
- 实际写集可与用户已有改动可靠区分。
- 输入输出、异常、事务、并发、幂等和上下游合同足以实现。
- 必要协同修改不改变 Plan 语义和风险等级；否则返回 Plan 或 Design。

## 基线

- 工作区归因清晰，Plan Files 与用户已有改动能够区分。
- 只运行能够区分历史失败的最小相关既有测试和必要确定性检查；完整编译留到集成候选稳定后执行一次。
- 基线失败时不编辑生产代码；历史失败只记录，不归入成果。

## TASK

- 生产 Java 候选通过共享机械 Gate。
- 表、字段和索引 DDL 不生成测试或数据库验证；实现后在报告的未验证范围中记录，不阻止 Java 交付完成。
- 所有 `review_required` 已修复或由独立 Reviewer 基于合同事实接受。
- 独立 Reviewer 已检查风险路由完整性、共享基线、Plan 规范和真实 Diff，并执行 `clean-code-guard`。
- Reviewer 提出问题且 Writer 修复后，只重跑受影响扫描、目标测试和同一 Reviewer 的增量复核；修复改变完整候选结论时才重跑对应编译、回归或覆盖率。
- 未修改且与本次增量无因果关系的问题不扩张为当前范围。

## 最终验证

- Plan Files 与真实 Diff 一致，语义不变的范围扩展已记录。
- 全部 TASK 组合后不存在新增职责混杂、重复知识、接口膨胀或依赖反转。
- 候选稳定后，编译、相关测试、机械 Gate、独立审查和增量覆盖率各有一次新鲜证据。
- 任一质量阻断、测试失败、覆盖率未达标或无法验证都不能进入完成状态。

构建证据使用临时 JSON，绑定当前 Plan、质量候选和覆盖率候选：

```json
{
  "plan_sha256": "<plan 文件摘要>",
  "quality_candidate_sha256": "<quality evidence 中的候选摘要>",
  "coverage_candidate_sha256": "<coverage evidence 中的候选摘要>",
  "started_at": 0,
  "commands": [
    {"kind": "compile", "command": "<真实命令>", "exit_code": 0, "finished_at": 0},
    {"kind": "new_tests", "command": "<真实命令>", "exit_code": 0, "finished_at": 0},
    {"kind": "regression_tests", "command": "<真实命令>", "exit_code": 0, "finished_at": 0}
  ]
}
```

时间使用 Unix 秒；命令必须在 `started_at` 之后结束。停止态保留已执行命令及真实退出码，不要求伪造成功。
