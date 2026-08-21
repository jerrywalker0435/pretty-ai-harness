# 安装最新 Pretty Skills

请使用 `npx skills@1.5.22` 安装下面 4 个 Pretty Skills 及其 12 个实际依赖，共 16 个可注册 Skill；另外从同一仓库默认分支复制 1 个 `pretty-common` 共享资源目录。仓库 URL 不附加 Git ref，以获取远程默认分支 HEAD 的最新版本。

<!-- SOURCE_CATALOG_START -->
| 仓库 | Skills |
|---|---|
| `git@gitlab-inner.haidilao.com:zhangy114/pretty-ai-harness.git` | `pretty-writing-prd`、`pretty-writing-design`、`pretty-writing-plan`、`pretty-executing-plan` |
| `https://github.com/mattpocock/skills.git` | `domain-modeling`、`grilling`、`codebase-design`、`tdd` |
| `https://github.com/jabrena/cursor-rules-java.git` | `121-java-object-oriented-design`、`122-java-type-design` |
| `https://github.com/florianbuetow/claude-code.git` | `solid-principles` |
| `https://github.com/github/awesome-copilot.git` | `refactor` |
| `https://github.com/amelnagdy/guard-skills.git` | `clean-code-guard` |
| `https://github.com/decebals/claude-code-java.git` | `design-patterns`、`java-code-review` |
| `https://github.com/obra/superpowers.git` | `verification-before-completion` |
<!-- SOURCE_CATALOG_END -->

共享资源（不注册为 Skill）：

- `skills/pretty-common/references/quality-principles.md`：`pretty-writing-plan` 与 `pretty-executing-plan` 必须共同读取的质量基线。
- 安装后目标结构必须保持为 `<target-skills-dir>/pretty-common/...`，与四个 Pretty Skill 目录同级；不要把它嵌套进任一 Skill 目录。

## 1. 确认安装范围

记录 Codex 启动时的绝对目录为 `<original-CWD>`，只读检查 `git`、`node`、`npm`、`npx` 是否可用，然后询问并将选定目录记录为 `<target-skills-dir>`：

```text
1. 当前目录：<original-CWD>/.agents/skills（默认，推荐）
2. 全局用户目录：$HOME/.agents/skills
3. 取消
```

展示默认值不等于获得同意。只有用户明确选择 1 或 2 才继续；空回复、含糊回复、取消或未回复时停止，不得获取任何仓库，也不得写入任何文件。

检查所选目录中的 16 个同名 Skill 路径和 `<target-skills-dir>/pretty-common/references/quality-principles.md`，文件、目录或符号链接都算已存在。只要存在任意同名项或共享资源，列出名称并询问：“是否更新全部 16 个 Skill 和 pretty-common 共享资源到最新版本？”只有明确同意才继续，否则停止且不修改。

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

`pretty-common` 没有 `SKILL.md`，不能作为 `--skill` 名称传给 `npx skills`；完成 16 个 Skill 安装后，从同一 Pretty Harness 仓库的远程默认分支复制它：

```bash
set -e
PRETTY_TARGET_SKILLS_DIR="<target-skills-dir>"
PRETTY_TEMP_ROOT="$(mktemp -d)"
git clone --depth 1 git@gitlab-inner.haidilao.com:zhangy114/pretty-ai-harness.git \
  "$PRETTY_TEMP_ROOT/pretty-ai-harness"
mkdir -p "$PRETTY_TARGET_SKILLS_DIR/pretty-common"
cp -R "$PRETTY_TEMP_ROOT/pretty-ai-harness/skills/pretty-common/." \
  "$PRETTY_TARGET_SKILLS_DIR/pretty-common/"
rm -rf "$PRETTY_TEMP_ROOT"
```

复制失败或源目录缺失时停止，不报告安装成功；临时目录只能使用刚创建的 `PRETTY_TEMP_ROOT`。

## 3. 验证

检查全部 16 个 Skill 目录均存在 `SKILL.md`，且 frontmatter 的 `name` 与目录名一致；另行确认 `<target-skills-dir>/pretty-common/references/quality-principles.md` 存在。再运行与所选范围对应的命令：

```text
# 当前目录
npx skills@1.5.22 list --agent universal --json

# 全局用户
npx skills@1.5.22 list --global --agent universal --json
```

最终报告安装范围、绝对目标目录、16 个 Skill 的成功和失败名称，以及共享资源验证结果。只有 16 个 Skill 和 `pretty-common` 全部验证通过才报告成功；若 Codex 未立即识别新版本，建议重启 Codex 一次。
