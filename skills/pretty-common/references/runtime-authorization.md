# Pretty 运行授权

用户调用 Pretty Apply，即授权本次运行直接创建、更新和清理必要的临时文件，并直接执行完成该流程所需的本地命令，无需逐文件、逐命令确认。

Pretty Apply 运行期临时文件的唯一位置是当前主题的 `docs/pretty/<topic>/tmp/<run-id>/`。Apply 使用 `execution-state.json` 作为登记清单；质量、测试、覆盖率、Resolver、矩阵和 Reviewer 证据都是 run 直属文件。Apply 仅允许一个固定的 `candidate/` 子目录作为 detached Git worktree。脚本拒绝其他目录、绝对 artifact 路径、`/private/tmp`、其他 topic 的 tmp 和路径穿越。

Maven/Gradle 自己管理的 `target/`、`build/`、Surefire 和 JaCoCo 报告保持项目约定位置；它们是构建输出，不是 Pretty 临时证据，也不由 Pretty 清理脚本删除。

授权范围包括：

- Git 读取、Diff、工作区检查和依赖事实检查；
- Candidate Lane、冻结 patch、执行矩阵、Resolver 结果、日志和 Reviewer receipt；
- 隔离 worktree 和恢复同一次 Apply 所需的 `execution-state.json`；
- 质量扫描、编译、目标测试、相关回归和覆盖率命令；
- 构建、测试和覆盖率产生的临时中间文件。

Apply 的 Writer 和验证命令只能写 `candidate/`；目标代码、测试、配置、Schema 和构建文件只允许 `apply_run.py promote` 写入。运行完成或明确停止后只能调用对应脚本按登记清单清理：先由 Git 移除登记 worktree，再删除直属 evidence。意外中断保留 run 目录和恢复状态。禁止直接执行 shell `rm -rf`，清理发现未登记文件时必须停止，不得扩大删除范围。

此授权不包括：

- 执行结构性 DDL 或配置数据 DML；
- commit、push、merge、部署或发布；
- 向外部系统写入；
- 覆盖或删除非本次运行创建的用户文件；
- 执行与当前 Pretty 流程无关的命令。

平台自身的安全授权和受保护路径限制仍然有效。
