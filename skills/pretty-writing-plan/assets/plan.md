# <主题> Implementation Plan

## 变更链路

<单模块且无跨边界时删除本节；否则删除本行并保留箭头摘要和关系表。>

### 主路径

`path/to/Caller#method` → `path/to/Module#method` → `path/to/Adapter#method` → `external boundary`

| 顺序/分支 | 上游 | 下游 | 跨边界数据与转换 | 规则/数据归属 | 失败/副作用边界 | TASK |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `...` | `...` | `...` | `...` | `...` | `TASK-001` |

## 实施任务

### <领域结果或独立风险>（TASK-001）

<可观察结果、不可改变合同和必要实现限制。>

| 仓库相对路径 | symbol | 修改目的 |
| --- | --- | --- |
| `module/src/main/java/...` | `ExampleModule#publish` | <目的> |
| `module/src/test/java/...` | `ExampleModuleTest` | <目的> |

#### 核心生产代码

```java
<完整展示所有受影响 symbol 的签名、依赖、返回值、异常和关键分支。>
```

#### 核心测试代码

```java
<展示 public 行为入口、真实输入/fixture、边界替身和业务结果断言。>
```

**依赖：** <仅在依赖关系不等于 TASK 编号顺序时填写>

### <声明或结构变更结果>（TASK-002）

<可观察结构不变量、受影响路径和不可改变限制。>

| 仓库相对路径 | 目标 | 修改目的 |
| --- | --- | --- |
| `db/migration/...sql` | `table.column` | <目的> |

#### 完整变更内容

```sql
<完整 DDL 或其他声明/结构变更内容。>
```
