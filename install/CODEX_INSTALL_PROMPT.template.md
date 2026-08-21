# 安装最新 Pretty Skills

请使用 `npx skills@1.5.22` 安装下面 4 个 Pretty Skills 及其 12 个实际依赖，共 16 个 Skill。仓库 URL 不附加 Git ref，以获取远程默认分支 HEAD 的最新版本。

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

## 1. 确认安装范围

记录 Codex 启动时的绝对目录为 `<original-CWD>`，只读检查 `git`、`node`、`npm`、`npx` 是否可用，然后询问：

```text
1. 当前目录：<original-CWD>/.agents/skills（默认，推荐）
2. 全局用户目录：$HOME/.agents/skills
3. 取消
```

展示默认值不等于获得同意。只有用户明确选择 1 或 2 才继续；空回复、含糊回复、取消或未回复时停止，不得获取任何仓库，也不得写入任何文件。

检查所选目录中的 16 个同名路径，文件、目录或符号链接都算已存在。只要存在任意同名项，列出名称并询问：“是否更新全部 16 个 Skill 到最新版本？”只有明确同意才继续，否则停止且不修改。

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

## 3. 验证

检查全部 16 个目录均存在 `SKILL.md`，且 frontmatter 的 `name` 与目录名一致。再运行与所选范围对应的命令：

```text
# 当前目录
npx skills@1.5.22 list --agent universal --json

# 全局用户
npx skills@1.5.22 list --global --agent universal --json
```

最终报告安装范围、绝对目标目录、成功和失败名称。只有 16 个 Skill 全部验证通过才报告成功；若 Codex 未立即识别新版本，建议重启 Codex 一次。
