# <主题> Plan

## 输入与范围

- PRD：`docs/pretty/<topic>/prd.md`
- Design：`docs/pretty/<topic>/design.md`

## 变更概览

<实施策略、任务边界与依赖顺序>

## 实施任务

### TASK-001 <中文动宾任务名>

- 覆盖需求：`REQ-001`
- 设计决策：`DEC-001`
- 验收标准：`AC-001`
- 变更文件：`<repo-relative-path>`
- 变更类型：<新增行为/Bug 修复/修改遗留行为/纯重构/机械变更>
- 实现要点：<说明>
- 测试先行：<失败测试、关键边界和测试层级>
- 定向验证：`<真实命令>`；预期：<结果>

#### 关键代码

```java
// 完整展示公共接口、核心业务方法、异常/事务边界；机械代码改用变更表。
```

#### 测试代码

```java
// 展示可执行的完整关键测试。
```

## 测试与增量覆盖率

- 新增代码行覆盖率阈值：90%
- 新增代码分支覆盖率阈值：80%
- 修改遗留行为：<针对性回归测试>
- 未触碰历史代码：不纳入覆盖率治理。
- JaCoCo 生成命令：`<core-skill-dir>/scripts/run-coverage.sh --project-dir <repo-root>`
- 增量检查命令：`python3 <core-skill-dir>/scripts/check-new-code-coverage.py ...`

## 最终验证

- 受影响模块：`<verify/check 命令>`
- 跨模块或仓库标准检查：<按影响范围列出>

## 执行交接

- 使用 `pretty-executing-plan`。
- 不自动提交或推送 Git。
