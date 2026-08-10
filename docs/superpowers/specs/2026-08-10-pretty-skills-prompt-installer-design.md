# Pretty Skills 提示式一键安装设计

## 摘要

Pretty Java/Spring 工作流由 5 个仓库内 Skill 和一组外部质量 Skill 共同组成。外部 Skill 不是可选装饰，而是 Pretty 工作流综合应用既有专业能力的核心。因此，一键安装必须安装完整依赖闭包，同时保持各外部 Skill 的原始来源和独立版本。

v1 面向公司内部的 Codex/ChatGPT 用户。用户只需向 Codex 发送一条由内部发布渠道提供的版本化安装提示语；该提示语固定 Pretty 仓库 URL 和不可变发布 commit，Codex 据此获取仓库并运行其中的确定性 Node.js 安装模块。提示语只负责启动流程、解释结果和请求必要授权，版本锁定、校验、冲突检测、事务安装与恢复全部由代码完成。

## 背景与问题

当前仓库包含以下 5 个 Skill：

- `pretty-java-spring-core`
- `pretty-writing-prd`
- `pretty-writing-design`
- `pretty-writing-plan`
- `pretty-executing-plan`

四个阶段 Skill 共同依赖 `pretty-java-spring-core`。当前 required 外部依赖闭包固定为以下 13 个 Skill：

- `domain-modeling`
- `grilling`
- `121-java-object-oriented-design`
- `122-java-type-design`
- `solid-principles`
- `refactor`
- `design-an-interface`
- `design-patterns`
- `springboot-tdd`
- `clean-code-guard`
- `test-driven-development`
- `java-code-review`
- `verification-before-completion`

Codex 以 `SKILL.md` frontmatter 的 `name` 发现 standalone Skill；插件名则是插件组件的 namespace。当前 Pretty 文本中的 `superpowers:test-driven-development` 和 `superpowers:verification-before-completion` 是 plugin-qualified 引用，不是这两个 Skill 的 standalone `name`。v1 发布前必须把这些引用改成上表中的 canonical name，并由合同测试防止再次混用；外部 Skill 内容仍保持原始来源，不内化到 Pretty。

逐个安装会给用户带来以下问题：

- 需要理解多个来源、路径和安装命令。
- 不同日期安装可能得到不同版本组合。
- 中途缺少条件依赖会阻断 PRD、Design、Plan 或 Execution。
- 同名已有 Skill 可能被静默覆盖或产生重复发现。
- 多次独立写入失败后可能留下不完整工作流。

现有 `~/.agents/.skill-lock.json` 可以提供部分来源线索，但它不构成 Pretty 的发布合同：部分本地 Skill 没有来源记录，且记录内容不足以统一证明不可变 commit。Pretty 必须维护自己的依赖锁和验证规则。

## 目标

- 用户通过一条 Codex 提示语安装完整 Pretty Skill 闭包到全局用户 scope。
- 安装结果由不可变 Git commit 和规范化目录 integrity 决定，可重复验证。
- 首次安装一次装齐全部依赖，不在运行工作流时按需下载。
- 默认保护已有同名内容；只有用户明确授权后才能备份并替换。
- 安装、升级和失败恢复具有幂等、可解释和可补偿的事务语义。
- Git 来源解析不绑定 GitLab 专属接口，后续可以迁移到 GitHub。
- 安装完成后离线使用已安装 Skill，不要求 Pretty 工作流运行时联网。

## 非目标

- v1 不通过 Codex Plugin Marketplace 分发。
- v1 不发布 npm CLI 包；Node.js 只是仓库内安装模块的运行时。
- 不把外部 Skill 改写为 Pretty 内部能力，也不降低为可选增强。
- 不把第三方 Skill 源码提交进 Pretty 仓库或重新分发为一个大包。
- 不支持只装部分依赖、运行时懒加载或用户自定义来源。
- 不提供跳过 commit、integrity 或安全路径校验的参数。
- 不自动更新依赖，不跟随分支或浮动 tag。
- v1 不承诺 Windows 正式支持；实现不得引入不必要的 POSIX-only shell 依赖，为后续 Windows CI 保留兼容路径。
- v1 不提供完整卸载器或成功安装后的通用版本回退界面；失败补偿与崩溃恢复属于安装事务的一部分。

## 已确认决策

1. v1 只面向 Codex/ChatGPT 和公司内部用户。
2. 用户接受“一条提示语完成安装”，不要求 Marketplace 单击安装。
3. 外部 Skill 是 Pretty 的核心依赖，不能删除、内化或降级为可选项。
4. 首次安装包含全部锁定依赖。
5. 每个外部依赖锁定原始 Git URL、完整 commit、仓库子目录和 integrity；5 个 Pretty Skill 的有效来源由提示语固定的 Pretty URL 与 commit，加上锁文件中的仓库子目录和 integrity 共同确定。
6. 普通安装不自动追随上游更新；升级必须发布新锁和新提示语。
7. canonical 目标目录中同名相同内容跳过；内容不同或同名 Skill 位于非 canonical 目录时，默认整体终止。
8. 只有显式 `--replace-conflicts` 才能备份并替换冲突项。
9. 安装目标是 Codex 用户级目录 `~/.agents/skills`。
10. Node.js 与 Git 是 v1 前置条件。
11. 来源解析使用标准 Git 协议，不使用 GitLab project ID 或 GitLab/GitHub 专属下载接口。

## 方案比较

### Codex Plugin

插件适合捆绑多个自有 Skill，但当前插件合同不能声明并安装一组外部 Skill 传递依赖。Pretty 仍需第二套依赖安装流程，形成插件 scope 与用户 Skill scope 两套状态。v1 不采用此方案。

### npm CLI

版本化 npm CLI 可以提供稳定命令和跨平台分发，但内部 v1 需要额外建设或接入 npm Package Registry。Codex 已经是用户入口，因此先发布 npm CLI 增加了不必要的分发层。后续若出现无 Codex 安装或大规模机器自动化需求，可以复用同一安装模块增加 npm adapter。

### 纯自然语言提示语

纯提示语部署成本最低，但无法可靠保证每次都执行相同的预检、hash 算法、事务顺序和回滚操作。它只能提供引导式安装，不能提供可复现发布合同。

### 推荐方案：提示语 + 确定性安装模块

提示语是最小用户 interface，仓库内 Node.js 模块是深模块。删除该模块后，来源解析、完整性校验、冲突处理和恢复复杂度会重新扩散到每次 Codex 对话，因此该模块具有足够 Depth，并把变化保持在一个 Locality 中。

## 仓库布局

```text
install/
  INSTALL_PROMPT.template.md
  pretty-skills.lock.json
scripts/
  pretty-skills.mjs
  render-install-prompt.mjs
tests/
  installer/
docs/
  superpowers/specs/
    2026-08-10-pretty-skills-prompt-installer-design.md
```

`INSTALL_PROMPT.template.md` 是可测试的提示语模板，`render-install-prompt.mjs` 在 Pretty 发布 commit 产生后把仓库 URL 和该完整 commit 渲染到发布产物。渲染结果发布到内部文档或制品系统，不提交回它所引用的 commit，从而避免 Git commit 自引用。`pretty-skills.lock.json` 只包含数据，不能携带或触发任意代码。`pretty-skills.mjs` 对外提供 `install`、`verify`，仅当自动恢复失败时提供 `recover`。

## 用户 Interface

用户复制版本化提示语给 Codex。提示语必须表达以下合同：

- 在新的临时目录中，从提示语声明的内部 Git 仓库检出提示语声明的完整 commit。
- 确认实际 `origin`、`HEAD` 和干净工作树与声明的仓库 URL、commit 完全一致。
- 只使用该提交中的安装模块与锁文件，不读取当前项目提供的替代配置。
- 运行 `node scripts/pretty-skills.mjs install --global --expected-bundle-url <url> --expected-bundle-commit <commit> --json`；安装模块必须再次验证自身仓库身份，而不能只信任提示语此前的检查。
- 默认不得替换冲突；收到结构化冲突后列出全部项目，并只询问一次是否允许备份替换。
- 获得明确授权后，使用 `--replace-conflicts` 重跑。
- 安装后使用相同的 `--expected-bundle-url` 和 `--expected-bundle-commit` 运行 `node scripts/pretty-skills.mjs verify --global --json`。
- 不编辑锁文件、安装模块或用户已有 Skill 来绕过失败。
- 报告 installed、unchanged、replaced、failed 项和唯一下一步。

平台仍可能针对网络访问和用户目录写入显示权限确认；提示语不能承诺绕过宿主权限模型。

## 锁文件合同

锁文件的概念结构如下：

```ts
type PrettySkillsLock = {
  schemaVersion: 1;
  bundle: {
    name: "pretty-java-spring-full";
    version: string;
  };
  skills: Array<{
    name: string;
    role: "pretty" | "external";
    requiredBy: string[];
    source:
      | {
          kind: "bundle";
          subdir: string;
        }
      | {
          kind: "git";
          url: string;
          commit: string;
          subdir: string;
        };
    integrity: string;
  }>;
};
```

不变量：

- `name` 在整个 bundle 内唯一，并与目录名和 `SKILL.md` frontmatter 一致。
- Pretty Skill 内的 required Skill 引用必须使用锁中对应条目的 canonical `name`，不得依赖只在某个插件安装形态下存在的 qualified alias。
- 5 个 `role: "pretty"` 条目必须使用 `kind: "bundle"`；安装时将已验证的 `--expected-bundle-url` 和 `--expected-bundle-commit` 展开为其有效来源。外部条目必须使用 `kind: "git"`，并在锁内提供独立来源。
- `commit` 必须是完整不可变 Git object ID，不接受缩写、分支和浮动 tag。
- `subdir` 必须是仓库内规范化相对路径，不能逃逸、指向外部 symlink 或包含平台歧义。
- `integrity` 使用下述版本化 canonical tree hash 算法，并覆盖 Skill 目录全部受支持文件。
- 依赖闭包必须包含 5 个 Pretty Skill 引用的全部外部 Skill。
- 同一 `url + commit` 的多个 Skill 共享一次 source materialization。
- URL 只允许审核过的 HTTPS、SSH 或 SSH scp-like Git 地址，不包含 token、用户名密码或其他嵌入式凭据；认证复用宿主的 credential helper 或 SSH 配置。
- Skill 子树必须自包含；v1 拒绝 submodule 和 Git LFS pointer，不把额外的 submodule/LFS 工具加入隐式前置条件。

### Canonical tree integrity

`integrity` 的 v1 格式为 `pretty-tree-v1-sha256:<64 个小写十六进制字符>`。来源校验、staging 校验和目标 drift 校验必须调用同一实现，规则如下：

1. 递归包含 Skill 子目录中的全部普通文件，包括隐藏文件；Git 不跟踪的空目录不参与哈希。
2. 拒绝 symlink、submodule、socket、device 和其他非普通文件，不跟随其目标。
3. 相对路径转成 `/` 分隔并规范化为 Unicode NFC；拒绝绝对路径、`.`、`..`、空段、反斜杠、NUL、Unicode control character、规范化后重复路径以及 ASCII 大小写折叠后冲突的路径。
4. 按规范化路径 UTF-8 字节序排序。每个文件编码为：4 字节无符号大端路径长度、路径字节、1 字节 executable 标志、8 字节无符号大端内容长度、原始内容字节。executable 标志只表示任一执行位是否存在，其他权限位不参与哈希。
5. 对 ASCII 头 `pretty-tree-v1\0` 与全部文件编码顺序计算 SHA-256。复制时保留 executable 语义，文本换行和文件内容不做转换。

## 安装模块与内部 Seam

`pretty-skills.mjs` 暴露一个小 interface，内部隐藏以下行为：

- 锁 schema 与依赖闭包校验。
- 用户 scope 和状态目录解析。
- Git 来源按仓库去重获取。
- commit、路径、frontmatter 和 canonical tree integrity 校验。
- canonical 目标目录以及用户 Skill 根下一层目录的 frontmatter name 盘点与完整冲突计划。
- 同盘 staging、备份、durable journal、提交、回滚和崩溃恢复。
- receipt、结构化输出、凭据脱敏和临时文件清理。

Git 是 true external dependency。在内部 seam 定义最小 source port；生产使用通用 Git CLI adapter，测试使用本地 bare repository 或 fake adapter。外部仓库只获取 Git object database，再通过 NUL-safe 的 `ls-tree`/`cat-file` 读取锁定子树；不 checkout 工作树，不应用 smudge filter，不初始化 submodule，也不执行仓库内容。锁文件和 5 个 Pretty Skill 同样从 expected bundle commit 的 Git objects 读取或物化，不从可变工作树复制。GitLab 和 GitHub 都只是标准 Git URL，不各自建立 adapter。

文件系统是 local-substitutable dependency。生产使用真实用户目录，测试使用临时目录执行同一事务实现；不把庞大的文件系统 port 暴露到外部 interface。

## 状态目录

安装模块只修改锁文件声明的 canonical 目标目录，以及用户显式授权替换的同名非 canonical 目录，并把自身状态保存在：

```text
~/.agents/.pretty-ai/
  install.lock
  staging/
  transactions/
  backups/
  receipts/
```

- `install.lock` 使用原子取得的 owner/transaction identity 和 heartbeat 阻止同一用户 scope 的并发安装。活跃 owner 返回 `E_BUSY`；只有能证明 owner 已失效时才可原子隔离旧锁，并先恢复其 journal。持锁进程在每个目标写入阶段前复核 owner identity，失去所有权即停止写入。
- `staging` 与目标目录位于同一文件系统，以支持 rename 提交。
- `transactions` 保存 durable journal 和恢复进度。
- `backups` 只保存显式替换产生的可恢复内容。
- `receipts` 记录 bundle 版本、每个 Skill 的来源、commit、integrity 和最终动作。

成功替换后的 backup 与恢复清单由 receipt 引用并保留；v1 不自动清理或提供通用版本回退命令。事务失败且已经完整补偿时可以清理仅属于该失败事务的 staging，自动恢复失败时必须保留全部现场。

为防止 Codex 同时发现两个同名 Skill，盘点时允许只读取用户 Skill 根下一层现有 `SKILL.md` 的 frontmatter `name`。名称不在锁内的 Skill 不进入 receipt，目录内容不被哈希，也不被修改。若锁内名称出现在非 canonical 目录，即使内容相同也属于 `conflict`；只有 `--replace-conflicts` 才能先备份该目录，再安装到 canonical 路径。

## 安装数据流

1. 用户向 Codex 发送发布流程在 Pretty commit 产生后渲染的版本化提示语。
2. Codex 使用现有 Git 凭据，在临时目录检出 Pretty 仓库固定 commit。
3. Codex 把提示语中的 Pretty URL 和 commit 作为 expected bundle identity 运行安装模块，并按宿主要求申请网络和用户目录写权限。
4. 安装模块取得独占锁，优先恢复未完成事务。
5. 安装模块校验自身 `origin`/`HEAD`、运行环境、锁文件、依赖闭包、目标权限和 Skill 名。
6. 安装模块扫描全部 canonical 目标和用户 scope 的同名 frontmatter，分类为 `missing`、`unchanged`、`conflict`。
7. 默认模式发现任一冲突时，在下载和写入之前返回全部冲突。
8. 无冲突或已获得替换授权后，在 staging 中按 `url + commit` 获取来源。
9. 安装模块校验 commit、subdir、frontmatter 和 integrity。
10. 提交前再次扫描目标，防止计划生成后被其他进程修改。
11. 替换模式先备份冲突项并持久化 journal。
12. 安装模块通过逐目录 rename 提交，随后重新验证完整 bundle。
13. 失败时按 journal 逆序补偿；成功时写 receipt 并清理 staging。
14. Codex 运行只读 `verify`，报告结果，并在新 Skill 尚未被发现时提示重启 Codex。

## 冲突、错误与恢复

安装模块提供稳定错误码和 JSON 输出。至少包含：

- `E_PREREQUISITE`：Node.js、Git、权限或认证不可用。
- `E_BUNDLE_IDENTITY`：实际 origin、HEAD 或工作树与提示语提供的 bootstrap identity 不一致；目标未改变。
- `E_LOCK_INVALID`：schema、依赖闭包、名称或路径合同无效。
- `E_CONFLICT`：canonical 目标内容不一致，或锁内名称出现在非 canonical 目录；目标未改变。
- `E_SOURCE_FETCH`：来源不可达；目标未改变。
- `E_COMMIT_UNAVAILABLE`：锁定 commit 不可取得；目标未改变。
- `E_SOURCE_UNSUPPORTED`：来源包含 symlink、submodule、Git LFS pointer 或其他不受支持的文件；目标未改变。
- `E_INTEGRITY`：来源内容与锁不一致；目标未改变。
- `E_BUSY`：已有安装事务。
- `E_TRANSACTION`：提交失败且已恢复原状态。
- `E_ROLLBACK_FAILED`：补偿未完成，返回 journal、backup 与恢复命令。
- `E_DRIFT`：只读验证发现缺失或人工修改。

错误必须清洗 URL 和日志中的凭据。Codex 只能根据错误码解释、重试、请求替换授权或调用 `recover`；不能把校验失败解释为可以降级安装。

多目录安装无法通过一次文件系统调用完成原子切换。v1 明确提供以下事务保证：

- 所有来源和 integrity 在首次目标写入前完成验证。
- 每个目录通过同盘 rename 提交。
- journal 在目标变更前持久化。
- 同一进程失败时立即补偿。
- 进程崩溃后，下次运行先恢复再开始新安装。
- 若自动恢复无法完成，保留完整现场并停止后续写入。

## 安全规则

- 信任根是内部发布渠道提供的版本化提示语及其中的 Pretty 完整 commit。
- 外部来源只按锁文件声明的 Git URL 和 commit 获取。
- 不执行外部 Skill 包含的脚本作为安装步骤；不 checkout、运行 filter、下载 LFS object 或初始化 submodule，安装阶段只从 Git objects 物化普通文件并校验内容。
- 拒绝路径穿越、外部 symlink、重复名称和 frontmatter 名称不匹配。
- 不读取当前工作仓库的同名配置来影响用户级安装。
- 不提供 `--force`、`--skip-integrity`、`--only` 或覆盖锁内外部来源的参数；`--expected-bundle-*` 只表达发布提示语的 bootstrap identity，不能改写依赖锁。
- 替换已有内容必须由用户明确授权，并在替换前验证备份与恢复清单。

## 幂等与升级

- 目标不存在时安装。
- 目标 canonical integrity 与锁一致时跳过。
- 目标与锁不一致时视为冲突，即使它来自先前 Pretty 安装。
- 同一发布提示语重复运行得到 no-op 或补齐缺失项，不重复写入相同内容。
- 依赖升级必须更新完整锁、运行发布门禁并生成新的 Pretty 发布 commit 与提示语。
- 不提供后台更新、自动跟随上游或静默替换。

## 测试策略

测试只通过安装模块的 interface 和可观察文件结果断言，不依赖内部步骤顺序以外的实现细节。

### 静态合同测试

- 锁 schema、唯一名称、完整 commit、安全路径和 integrity 格式。
- canonical tree hash 的固定测试向量、executable 语义、路径排序和危险文件拒绝规则。
- 扫描 Pretty Skill 中的 required Skill 引用，验证依赖闭包完整、引用名等于 standalone frontmatter `name`，并拒绝 plugin-qualified alias。
- 验证提示语模板可由给定仓库 URL 和完整 commit 确定性渲染，且渲染结果包含 bootstrap identity、自校验、禁止绕过、最终 `verify` 和冲突授权要求。
- 验证锁文件不包含可执行命令和嵌入式凭据。

### 安装集成测试

- 使用临时用户目录验证首次安装和重复安装。
- 使用本地 bare Git 仓库验证多个来源和同仓库去重。
- 验证 expected bundle URL/commit 不匹配时，在任何用户目标写入前终止。
- 验证缺失项补齐、相同项跳过和冲突整体终止。
- 验证非 canonical 目录中的同名 frontmatter 会触发整体冲突，显式替换时备份原目录并消除重复发现。
- 验证显式替换前备份、替换后 receipt 与最终 integrity。
- 验证人工修改后 `verify` 返回 drift。
- 验证并发安装返回 busy，不产生第二个事务。

### 故障与恢复测试

- Git 获取失败、commit 不存在和 integrity 不匹配时目标无变化。
- staging、备份、rename、journal 和清理阶段的故障注入。
- 中途失败后的逆序补偿。
- 模拟进程崩溃后的自动恢复。
- 自动恢复失败时保留可操作现场和稳定恢复命令。

### 发布 smoke test

每个发布候选在干净 Codex 会话和干净用户 Skill 根目录中执行真实版本化提示语。smoke test 验证 Codex 能获取内部仓库、正确调用安装模块、处理权限提示并完成最终 `verify`。该测试补充确定性模块测试，但不替代它们。

v1 正式 CI 覆盖 macOS 和 Linux。实现使用 Node.js 路径与文件系统接口，不在核心事务中依赖 POSIX-only shell，为后续 Windows runner 和兼容测试保留空间。

## 发布流程

1. 审核 13 个外部 Skill 的原始仓库、子目录、使用许可、standalone name 和安装来源，并把 Pretty 中的 plugin-qualified 引用规范化为 canonical name。
2. 为每个外部依赖选择不可变 commit，并为全部 Pretty 与外部 Skill 生成 canonical tree integrity。
3. 更新锁文件和 bundle 版本。
4. 运行 Pretty 现有测试、静态合同测试、安装集成测试和故障恢复测试。
5. 创建包含安装模块、锁文件和提示语模板的不可变 Pretty 发布 commit。
6. 从该 commit 运行 renderer，把仓库 URL 和完整发布 commit 生成到临时或 CI 制品；不得把渲染结果提交回所引用的 commit。
7. 对渲染结果运行静态合同测试，并在干净环境执行发布 smoke test。
8. 将通过测试的同一份提示语制品发布到公司内部文档，并记录 Pretty bundle 版本和发布 commit。

当前已有安装元数据不能证明全部 13 个外部依赖的原始来源。发布计划必须先完成来源审计；缺少可验证来源的 Skill 不能进入锁文件和 v1 发布。

## GitHub 演进路径

安装模块只理解标准 Git URL、commit、subdir 和 integrity。后续支持 GitHub 时：

1. 将 Pretty 仓库镜像或迁移到 GitHub。
2. 使用同一模板生成固定 GitHub 仓库和完整 commit 的新版提示语。
3. 对私有仓库复用 Git credential helper、SSH 或宿主提供的 GitHub 凭据。
4. 增加 GitHub 网络 smoke test。

锁 schema、安装数据流、冲突规则和事务实现不需要修改。若未来需要 Marketplace 或 npm 分发，它们只作为新的启动 adapter，继续调用同一安装模块。

## 验收标准

- 新用户只发送一条由发布流程渲染并验证过的版本化提示语即可启动完整安装。
- 无冲突时，5 个 Pretty Skill 与全部锁定外部依赖一次安装到 `~/.agents/skills`。
- 相同版本重复执行不修改已安装内容。
- 任一冲突在默认模式下使整批在写入前停止，并一次列全。
- 显式替换始终先生成可验证备份和恢复清单。
- 来源、commit 或 integrity 校验失败时不修改目标。
- 提交失败后恢复原状态；无法恢复时保留 journal、backup 和唯一恢复命令。
- `verify` 能检测缺失、锁定 Skill 目录内的额外文件或修改，以及 integrity 漂移；无关名称的用户 Skill 不视为 drift。
- 发布锁包含完整外部依赖闭包及可验证原始来源。
- 从内部 GitLab 切换到 GitHub 不需要修改安装模块核心实现。

## 参考资料

- [OpenAI Codex Skills](https://developers.openai.com/codex/skills/)
- [OpenAI Plugin Packaging](https://developers.openai.com/plugins/build/plugins)
- [OpenAI Codex Hooks](https://developers.openai.com/codex/hooks/)
