# Pretty AI Harness

Pretty AI Harness 提供 4 个 Java/Spring 研发流程 Skills。安装 Prompt 会同时安装当前工作流实际使用的 12 个外部依赖，共 16 个可注册 Skill，并同步复制 1 个供 Plan/Execution 使用的共享资源目录；所有来源都从远程默认分支获取最新版本。

## 规范源

当前运行规范唯一来源是 `skills/` 下各 Skill 的 `SKILL.md` 及其直接引用的资源。`README.md` 和安装模板只维护分发元信息，不复制 Skill 正文；历史设计文档不作为运行规范。

## 安装

1. 复制 [安装 Prompt](install/CODEX_INSTALL_PROMPT.template.md) 全文并发送给 Codex。
2. 选择安装到当前项目的 `.agents/skills`（推荐）或全局 `$HOME/.agents/skills`。
3. 若目标中已有同名 Skill 或 `pretty-common` 共享资源，确认是否将全部 16 个 Skill 和共享资源更新到最新版本。

`pretty-common` 不是独立 Skill，不会出现在 `Selected`/`Installed` 列表中；它必须与四个核心 Skill 位于同一 `skills` 目录下，供 `pretty-writing-plan` 和 `pretty-executing-plan` 的相对引用使用。

安装需要 `git`、Node.js/npm/npx，以及访问内部 Pretty GitLab 仓库的凭证。

## 验证

```bash
npx skills@1.5.22 add . --list --full-depth
```

另外确认所选目标目录存在 `pretty-common/references/quality-principles.md` 和 `pretty-common/scripts/quality_contract_gate.py`；后者是 Plan/Execution 共用的高确定性 Java 代码质量扫描器。
