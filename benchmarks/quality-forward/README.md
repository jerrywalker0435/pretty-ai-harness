# Quality Forward Replay

本基准只包含合成任务，不收录或伪装历史真实实例。8 个场景分别覆盖分支合同、值对象、失败语义、强类型边界、真实变化轴、批量失败、显式可缺失查询和配置边界。

每个场景在全新临时 Git 仓库中由真实 Codex Agent 完整执行 `Design → Design Gate → Apply → Execution Gate`，默认独立运行两次。Execution Gate 通过后，评估器才从 Agent 无法修改的 Harness 目录注入该场景的 JUnit 行为 oracle 并单独执行。通过条件是 Agent、两个 Gate 和行为 oracle 均成功、场景合同 token 落入 Design 与真实代码、`execution.md` 到达完成状态并包含精确增量行/分支覆盖率结论。

```bash
python3 benchmarks/quality-forward/run_replay.py
```

每条 Agent、Gate 和 oracle 命令默认最多运行 900 秒，可用 `--command-timeout <秒>` 调整。进程无法启动或超时会写入对应任务日志并标记为 `infrastructure_error`，不会中断其他并行任务或阻止 `summary.json` 生成。

结果和完整 Agent 日志只写入命令输出所示的临时目录；仓库不保存生成的示例 Design 或实现。
认证过期、额度耗尽或 Agent 运行时无法初始化会单独标记为 `infrastructure_error`，不冒充场景质量失败，也不计为通过。
