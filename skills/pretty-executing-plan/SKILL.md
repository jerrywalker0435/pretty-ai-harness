---
name: pretty-executing-plan
description: Use when a reviewed Pretty plan.md for a Java/Spring feature, bug fix, or refactor is ready to implement or resume in the target repository.
---

# 执行 Java/Spring Plan

## 目标

按已 Review 的 Plan 实施代码，通过分类式 TDD、新增代码覆盖率、代码质量和新鲜验证门禁，并产出简洁的 Execution 文档供人 Review。默认在当前工作区保留未提交差异。

**REQUIRED SUB-SKILL：** 完整读取并使用 `pretty-java-spring-core` 的共享合同、Execution 模板和 Java/Spring 质量检查。本 Skill 是执行阶段的唯一流程控制器。

## 工作流

### 1. 校验输入与工作区

宣布使用 `pretty-executing-plan`。读取同一主题下已由用户 Review 的完整文档链：

```text
docs/pretty/<topic>/prd.md
docs/pretty/<topic>/design.md
docs/pretty/<topic>/plan.md
```

同时按共享合同读取领域上下文：根目录存在 `CONTEXT-MAP.md` 时先定位本次涉及的上下文并读取其 `CONTEXT.md`，否则读取根目录已有的 `CONTEXT.md`。Executing 只消费并检查既有领域模型，不调用 `domain-modeling`，也不得更新 `CONTEXT.md`、`CONTEXT-MAP.md` 或 ADR；文件不存在时不默认创建。

运行共享校验器至 Plan；缺失、矛盾或不可执行时返回最早受影响阶段，不在执行中改写 Plan：

```bash
python3 <pretty-java-spring-core-dir>/scripts/validate-pretty-docs.py \
  docs/pretty/<topic> --through plan
```

执行前检查仓库规则、`git status`、相关 diff 和 Plan 涉及文件。保留用户已有改动；无重叠时可以在非洁净工作区继续，存在无法安全区分的重叠时停止并说明。不得自动 stash、reset、rebase 或覆盖用户内容。

记录仅用于增量覆盖率的执行开始 HEAD，运行 Plan 指定的基线编译和相关测试。会妨碍可靠验证的基线失败必须先解决；不得把历史失败算成本次成功。

使用共享模板创建或更新唯一报告：

```text
docs/pretty/<topic>/execution.md
```

恢复执行时同时核对 Plan、实际 diff、测试输出和报告，从第一个未闭环任务继续；不只信任报告文字。

### 2. 按任务类型执行

依 Plan 顺序实施全部 `TASK`，并把实际文件、命令、结果和偏差写入 Execution。用户要求执行整个 Plan 后，不在任务间增加 Review 或确认。

- **新增或改变行为、Bug 修复：** **REQUIRED SUB-SKILL：** 使用 `superpowers:test-driven-development`。每次只写一个可观察行为的测试，运行并确认 RED 因目标行为缺失而失败；写最小生产代码，运行 GREEN；仅在通过后重构并复验。
- **修改遗留行为：** 同样执行 RED→GREEN，并加入针对本次变化的回归边界测试；不要求顺便治理无关历史代码。
- **行为保持型重构：** 使用 `refactor`，先取得通过的特征/回归测试基线，小步重构并持续复验，不制造虚假 RED。
- **非行为任务：** 只有能证明不改变生产行为的文档、格式、生成物或机械修改才归入此类；运行 Plan 中与风险匹配的等价验证，不制造 RED/GREEN 记录。

测试初次通过、失败原因不正确或目标实现已预先存在时，不伪造 TDD 证据；记录真实情况并判断是否需要返回 Plan。测试聚焦业务结果和外部契约，mock 只放在不可避免的边界。

Plan 和上游语义清楚时，错误实现（包括误导性命名、职责或包归属错误）在本阶段直接修正。机械路径或等价命令变化且不改变设计、范围和验收时可采用真实值并记录。若修正要求改变需求、`REQ/AC` 或外部行为，停止并返回 PRD；若要求改变领域设计、不变量、边界、所有权或 `DEC`，返回 Design；若上游仍有效但实施计划的任务、测试或覆盖率口径缺失、矛盾或不可执行，返回 Plan。不得通过改写上游文档来迁就当前实现。

### 3. 完成任务级与整体验证

每个行为闭环后运行定向测试；每个任务结束后运行 Plan 指定的受影响测试。全部任务完成后运行受影响模块和仓库最终命令。失败属于 Plan 范围且不改变设计时直接修复并复验；不得降低断言、跳过测试或扩大排除来刷绿。

执行开始时保存基线，例如：

```bash
pretty_execution_start_head=$(git rev-parse HEAD)
```

按 Plan 的实际项目路径生成 JaCoCo XML，并检查新增生产代码：

```bash
<pretty-java-spring-core-dir>/scripts/run-coverage.sh --project-dir <repo-root>
python3 <pretty-java-spring-core-dir>/scripts/check-new-code-coverage.py \
  --repo <repo-root> --base "$pretty_execution_start_head" \
  --report <jacoco.xml> --file <plan-owned-production-file> \
  --line-threshold 90 --branch-threshold 80
```

把运行器返回的每个实际报告路径传给检查器，并为每个 Plan 拥有的生产文件重复 `--file`；这样无关的既有工作区差异不会污染分母。新增生产代码行覆盖率必须至少 `90%`、分支覆盖率至少 `80%`；未触碰历史代码不进入分母，也不要求补测。报告记录实际分子/分母、未覆盖位置和命令退出结果。覆盖不足时补充有意义的业务测试并重跑。

### 4. 执行一次最终独立 Review

全部任务和首轮整体门禁通过后，只执行一次最终独立 Review，不做逐任务或逐单元 Review：

1. 由未参与实现的 Reviewer 读取 PRD、Design、Plan、包含 staged 与 untracked 文件的完整最终差异、相关源码和测试，不向其泄露实现者的质量结论。
2. Reviewer 对生产代码使用 `clean-code-guard`，对完整 Java 变更使用 `java-code-review`，同时核对需求/设计符合性、领域语言、不变量、所有权与边界一致性、测试价值、Spring 边界、内聚耦合、异常、事务、并发和性能风险。
3. 修复所有阻塞发现并重跑受影响的 TDD、测试和覆盖率；由同一 Reviewer 确认发现关闭，视为同一次 Review 闭环。

没有独立 Reviewer 能力时标记阻塞；实现者自审不能替代该门禁。Plan 明确要求的其他 Java/OOD/SOLID 专项检查按实际差异执行，不重复无关 Skill。

### 5. 最终验证与报告

Review 修正完成后，**REQUIRED SUB-SKILL：** 使用 `superpowers:verification-before-completion`，重新运行并亲自读取：

- Plan 的最终测试、编译和仓库检查；
- JaCoCo 报告生成及新增代码覆盖率检查；
- 共享文档校验器。

更新 Execution 的所有 `TASK` 结果、实际覆盖率、质量发现与修正、偏差和最终结论，然后运行：

```bash
python3 <pretty-java-spring-core-dir>/scripts/validate-pretty-docs.py \
  docs/pretty/<topic> --through execution
```

只有最新命令全部成功、Plan 的每项任务与验收标准均闭环、独立 Review 无未解决阻塞时，才能写“完成并等待人工 Review”；否则如实写明阻塞。

### 6. 请求一次人工 Review 并停止

告知用户代码差异、Execution 路径、测试与覆盖率结果、独立 Review 结论和未解决事项，请求一次人工 Review，然后停止。保持实现和报告为未提交差异；不创建 worktree，不自动执行 `git add`、`commit`、`push`、merge 或创建 MR。

## 红线

- 修改代码前不读 Plan，或执行中静默改变 Plan。
- 执行中调用 `domain-modeling`，或更新 `CONTEXT.md`、`CONTEXT-MAP.md`、ADR 来迁就实现。
- 为非行为任务制造 RED，或把事后测试写成 TDD。
- 只看覆盖率百分比，不审查断言和业务边界。
- 用全仓历史覆盖率掩盖新增代码不足。
- 用实现者自审代替最终独立 Reviewer。
- 未运行新鲜最终命令就声称完成。
- 自动提交、推送或改动用户无关文件。
