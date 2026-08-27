# 安装最新 Pretty Skills

请使用 `npx skills@1.5.22` 安装下面 3 个 Pretty Skills 及其 10 个实际依赖，共 13 个可注册 Skill；另外从同一仓库默认分支复制 1 个 `pretty-common` 共享资源目录。仓库 URL 不附加 Git ref，以获取远程默认分支 HEAD 的最新版本。

<!-- SOURCE_CATALOG_START -->
| 仓库 | Skills |
|---|---|
| `git@gitlab-inner.haidilao.com:zhangy114/pretty-ai-harness.git` | `pretty-writing-prd`、`pretty-writing-design`、`pretty-executing` |
| `https://github.com/mattpocock/skills.git` | `domain-modeling`、`grilling`、`codebase-design`、`tdd` |
| `https://github.com/jabrena/cursor-rules-java.git` | `121-java-object-oriented-design`、`122-java-type-design` |
| `https://github.com/florianbuetow/claude-code.git` | `solid-principles` |
| `https://github.com/amelnagdy/guard-skills.git` | `clean-code-guard` |
| `https://github.com/decebals/claude-code-java.git` | `design-patterns`、`java-code-review` |
<!-- SOURCE_CATALOG_END -->

共享资源（不注册为 Skill）：

- `skills/pretty-common/references/quality-principles.md`：`pretty-writing-design` 与 `pretty-executing` 必须共同读取的质量基线。
- `skills/pretty-common/references/quality-routing.md`：Apply 风险与专项主审 Skill 的路由表。
- `skills/pretty-common/references/quality-review-protocol.md`：唯一 Apply 最终独立审查及证据协议；Design 不启动 Reviewer。
- `skills/pretty-common/references/runtime-authorization.md`：topic 内临时证据与安全清理边界。
- `skills/pretty-common/scripts/quality_contract_gate.py`：Preview 和 Apply 共用的高确定性 Java 代码质量扫描器。
- `skills/pretty-common/scripts/pretty_tmp.py`：统一校验 `docs/pretty/<topic>/tmp/<run-id>/` 并按登记清单清理。
- 安装后目标结构必须保持为 `<target-skills-dir>/pretty-common/...`，与三个 Pretty Skill 目录同级；不要把它嵌套进任一 Skill 目录。

## 1. 确认安装范围

记录 Codex 启动时的绝对目录为 `<original-CWD>`，只读检查 `git`、`node`、`npm`、`npx` 是否可用，然后询问并将选定目录记录为 `<target-skills-dir>`：

```text
1. 当前目录：<original-CWD>/.agents/skills（默认，推荐）
2. 全局用户目录：$HOME/.agents/skills
3. 取消
```

展示默认值不等于获得同意。只有用户明确选择 1 或 2 才继续；空回复、含糊回复、取消或未回复时停止，不得获取任何仓库，也不得写入任何文件。

检查所选目录中的 13 个同名 Skill 路径和上述 6 个共享资源，文件、目录或符号链接都算已存在。只要存在任意同名项或共享资源，列出名称并询问：“是否更新全部 13 个 Skill 和 pretty-common 共享资源到最新版本？”只有明确同意才继续，否则停止且不修改。

同时检查 `<target-skills-dir>/refactor`、`<target-skills-dir>/verification-before-completion`、`<target-skills-dir>/pretty-writing-plan` 和 `<target-skills-dir>/pretty-executing-plan`。它们是旧版 Harness 安装过、但不再属于当前 13-Skill 组合的遗留项。若存在任意一个，单独列出并要求用户明确选择：

```text
1. 保留这些额外 Skill（最终报告必须逐项标记为“保留的额外 Skill”，不得声称目标目录只有 13 个 Skill）
2. 删除这些旧版遗留 Skill（仅在当前 13 个 Skill 和 pretty-common 全部更新、验证成功后删除）
3. 取消
```

不得默认删除，也不得把“更新当前组合”的同意解释为删除遗留项的授权。记录明确选择为 `PRETTY_LEGACY_ACTION=keep` 或 `PRETTY_LEGACY_ACTION=remove`；取消或含糊回复时停止且不修改。

## 2. 安装最新版本

从 `<original-CWD>` 对目录中每个仓库执行一次命令，把 `<name...>` 替换为该行列出的全部 Skill 名称。不得指定 commit、tag、branch 或其他 Git ref。

当前目录安装：

```text
npx skills@1.5.22 add <repository-url> --agent universal --copy --full-depth --yes --skill <name...>
```

全局用户安装：

```text
npx skills@1.5.22 add <repository-url> --global --agent universal --copy --full-depth --yes --skill <name...>
```

`add --yes --copy` 用同一流程完成首次安装和已有版本更新。每条命令必须确认请求的全部名称都出现在 Selected 和 Installed，且没有 Failed to install；否则停止后续命令并报告失败。不得只凭退出码或旧目录仍存在判定更新成功，也不要更换来源或缩减依赖。

### 同步共享资源

`pretty-common` 没有 `SKILL.md`，不能作为 `--skill` 名称传给 `npx skills`；完成 13 个 Skill 安装后，从同一 Pretty Harness 仓库的远程默认分支复制它：

```bash
set -eu
PRETTY_TARGET_SKILLS_DIR="<target-skills-dir>"
PRETTY_COMMON_TARGET="$PRETTY_TARGET_SKILLS_DIR/pretty-common"
PRETTY_TEMP_ROOT="$(mktemp -d "$PRETTY_TARGET_SKILLS_DIR/.pretty-install.XXXXXX")"
PRETTY_SWAP_ROOT="$(mktemp -d "$PRETTY_TARGET_SKILLS_DIR/.pretty-common.swap.XXXXXX")"
PRETTY_STAGED_PATH="$PRETTY_SWAP_ROOT/next"
PRETTY_BACKUP_PATH="$PRETTY_SWAP_ROOT/previous"
PRETTY_RESTORE_REQUIRED=false

pretty_restore_previous() {
  if [ "$PRETTY_RESTORE_REQUIRED" = "true" ] && \
     { [ -e "$PRETTY_BACKUP_PATH" ] || [ -L "$PRETTY_BACKUP_PATH" ]; }; then
    rm -rf "$PRETTY_COMMON_TARGET"
    mv "$PRETTY_BACKUP_PATH" "$PRETTY_COMMON_TARGET"
  fi
  rm -rf "$PRETTY_TEMP_ROOT" "$PRETTY_SWAP_ROOT"
}
trap pretty_restore_previous EXIT

test -d "$PRETTY_TARGET_SKILLS_DIR"
git clone --depth 1 git@gitlab-inner.haidilao.com:zhangy114/pretty-ai-harness.git \
  "$PRETTY_TEMP_ROOT/pretty-ai-harness"
cp -R "$PRETTY_TEMP_ROOT/pretty-ai-harness/skills/pretty-common" \
  "$PRETTY_STAGED_PATH"
test -f "$PRETTY_STAGED_PATH/references/quality-principles.md"
test -f "$PRETTY_STAGED_PATH/references/quality-routing.md"
test -f "$PRETTY_STAGED_PATH/references/quality-review-protocol.md"
test -f "$PRETTY_STAGED_PATH/references/runtime-authorization.md"
test -f "$PRETTY_STAGED_PATH/scripts/quality_contract_gate.py"
test -f "$PRETTY_STAGED_PATH/scripts/pretty_tmp.py"

if [ -e "$PRETTY_COMMON_TARGET" ] || [ -L "$PRETTY_COMMON_TARGET" ]; then
  PRETTY_RESTORE_REQUIRED=true
  mv "$PRETTY_COMMON_TARGET" "$PRETTY_BACKUP_PATH"
fi
mv "$PRETTY_STAGED_PATH" "$PRETTY_COMMON_TARGET"
PRETTY_RESTORE_REQUIRED=false
```

复制、校验或最终替换失败时，退出 trap 必须恢复先前的 `pretty-common`；不得留下半安装目录，也不得报告安装成功。临时目录只能使用本段刚创建的 `PRETTY_TEMP_ROOT` 和 `PRETTY_SWAP_ROOT`。

## 3. 验证

检查全部 13 个 Skill 目录均存在 `SKILL.md`，且 frontmatter 的 `name` 与目录名一致；另行确认上述 6 个共享资源存在。再运行与所选范围对应的命令：

```text
# 当前目录
npx skills@1.5.22 list --agent universal --json

# 全局用户
npx skills@1.5.22 list --global --agent universal --json
```

### 处理旧版遗留 Skill

仅当之前明确记录 `PRETTY_LEGACY_ACTION=remove`，并且本节已确认 13 个当前 Skill 与 6 个共享资源全部验证成功后，才删除实际存在的精确路径：

```bash
rm -rf "$PRETTY_TARGET_SKILLS_DIR/refactor"
rm -rf "$PRETTY_TARGET_SKILLS_DIR/verification-before-completion"
rm -rf "$PRETTY_TARGET_SKILLS_DIR/pretty-writing-plan"
rm -rf "$PRETTY_TARGET_SKILLS_DIR/pretty-executing-plan"
```

选择 `keep` 时不修改这四个目录，并在最终报告中逐项列出。路径不存在时不制造失败，也不得删除其他来源的同名或相邻目录。

最终报告安装范围、绝对目标目录、13 个 Skill 的成功和失败名称、共享资源验证结果，以及四个 legacy 路径各自的“不存在 / 已删除 / 保留为额外 Skill”状态。只有 13 个 Skill 和 6 个共享资源全部验证通过才报告当前组合安装成功；若保留 legacy 项，必须明确实际目录含额外 Skill。若 Codex 未立即识别新版本，建议重启 Codex 一次。
