# 强制质量闭环合同

本合同只用于执行模式中非平凡生产代码的一次全量发现 Review 及其限定修复。Review 在系统临时
目录写入 JSON；该文件不属于项目交付物，不写入 `docs/pretty/`，也不提交到仓库。

## Review JSON

以下示例表示一个 finding 已完成一次限定修复后的最终状态：

```json
{
  "review_type": "full-discovery",
  "full_review_count": 1,
  "reviewed_paths": ["module/src/main/java/example/OrderService.java"],
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

- ID 使用连续的 `QF-001` 形式，在本次执行中保持稳定。
- `reviewed_paths` 覆盖最终实际修改及明确允许限定修复的生产、测试和其他代码文件；命令中为每个
  路径重复传入 `--path`，finding 位置及允许范围都不得逸出该集合。
- `source` 使用 `clean-code-guard`、`pretty-executing-test-guard` 或实际命中的专项路由名。
- `location` 和 `allowed_scope` 必须定位到 `path#symbol`；行号只作为辅助证据。
- 同一根因使用相同且稳定的 `QG-001` 形式 `repair_group`；`attempts` 表示该组共享的累计修复次数，
  组内所有 finding 必须一致且最多为两次。
- `fixed` 必须记录至少一次修复、实际 resolution 和 verification。
- `exception` 必须包含 `reason`、`facts` 和 `revisit_trigger`；普通实现偏好不能构成例外。
- `open` 表示尚未关闭；达到两次修复、需要越界或没有新证据时保持 `open` 并停止执行。

## 门禁调用

全量发现 Review 后先检查结构；每次限定修复只更新对应 finding：

```bash
python3 skills/pretty-executing/scripts/quality_review_gate.py \
  <系统临时目录>/quality-review.json \
  --path module/src/main/java/example/OrderService.java
```

全部 finding 关闭后，用相同生产文件集合执行阻断检查；只有退出码为 `0` 才进入最终验证：

```bash
python3 skills/pretty-executing/scripts/quality_review_gate.py \
  <系统临时目录>/quality-review.json \
  --path module/src/main/java/example/OrderService.java \
  --require-closed
```

将命令输出的唯一汇总行原样写入 `execution.md` 的“质量门禁”。不把完整 finding、测试清单或阶段
状态复制到执行记录。
