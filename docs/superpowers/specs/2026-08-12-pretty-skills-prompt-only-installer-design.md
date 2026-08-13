# Pretty Skills Prompt-Only Installer Design

## Status

Approved design, revised on 2026-08-12 after user review. This document
supersedes the repository-based Node installer design dated 2026-08-10 and its
2026-08-11 implementation plan.

## Goal

Give an internal Codex user one Chinese prompt that installs the five Pretty
Skills and their thirteen required external Skills.

The default choice is the directory where the user launched Codex:
`$CWD/.agents/skills`. The user may instead choose the global user directory
`$HOME/.agents/skills`.

The prompt remains the product. The repository does not contain a custom
installer, source lock, hash checker, lease, journal, transaction engine, or
recovery CLI.

## Confirmed decisions

- Install the complete 5 + 13 dependency closure. External Skills remain core
  dependencies and are neither internalized nor optional.
- Use `npx skills@1.5.22` as the installation mechanism.
- Ask the user to confirm the installation scope before any repository fetch or
  filesystem write.
- Present the current directory as the default and recommended choice. Project
  installation uses `$CWD/.agents/skills` and does not pass `--global`.
- Offer `$HOME/.agents/skills` as the global user alternative. Global
  installation passes `--global`.
- A displayed default is not consent. Only an explicit project or global
  selection starts installation. An empty, ambiguous, or cancel response makes
  no changes.
- Do not specify a commit, tag, branch, or other Git ref for any repository.
  Every installation resolves the latest commit of the repository's remote
  default branch at execution time.
- If a target name already exists in the selected scope, skip it by default and
  report it. Do not claim that a skipped Skill matches the latest source.
- Ask separately before replacing existing same-name targets. Only an explicit
  affirmative answer authorizes backup and replacement.
- Internal distribution comes first. A later GitHub move changes only the Pretty
  repository URL, not the installation flow.

## Deliverables

The implementation is intentionally small:

- `install/CODEX_INSTALL_PROMPT.template.md`: the complete Chinese prompt.
- `README.md`: a short explanation and internal distribution instructions.
- `tests/test_pretty_install_prompt.py`: a lightweight static contract covering
  the source closure, scope confirmation, latest-source policy, conflict policy,
  installer version, and verification instructions.

No custom installation runtime or dependency lock is added. A native
`skills-lock.json` created by `npx skills` during project installation is owned
by that external CLI and is not parsed or managed by this prompt.

## Source catalog

The prompt embeds only the repository-to-Skill mapping. None of the repository
URLs includes a commit, tag, branch, or ref suffix.

| Repository | Skills |
|---|---|
| `git@gitlab-inner.haidilao.com:zhangy114/pretty-ai-harness.git` | `pretty-java-spring-core`, `pretty-writing-prd`, `pretty-writing-design`, `pretty-writing-plan`, `pretty-executing-plan` |
| `https://github.com/mattpocock/skills.git` | `domain-modeling`, `grilling`, `design-an-interface`, `tdd` |
| `https://github.com/jabrena/cursor-rules-java.git` | `121-java-object-oriented-design`, `122-java-type-design` |
| `https://github.com/florianbuetow/claude-code.git` | `solid-principles` |
| `https://github.com/github/awesome-copilot.git` | `refactor` |
| `https://github.com/affaan-m/everything-claude-code.git` | `springboot-tdd` |
| `https://github.com/amelnagdy/guard-skills.git` | `clean-code-guard` |
| `https://github.com/decebals/claude-code-java.git` | `design-patterns`, `java-code-review` |
| `https://github.com/obra/superpowers.git` | `verification-before-completion` |

For this design, “latest” means the HEAD of the default branch returned when
`npx skills@1.5.22` fetches the repository during that installation. Different
runs may therefore install different source content. Reproducible commit
pinning is explicitly outside this design.

## Prompt workflow

### 1. Read-only preflight and scope confirmation

Codex records the absolute original `$CWD` and checks that `git`, `node`, `npm`,
and `npx` are available. It then shows the complete 5 + 13 installation intent
and asks the user to select exactly one option:

```text
1. 当前目录：<original-CWD>/.agents/skills（默认，推荐）
2. 全局用户目录：$HOME/.agents/skills
3. 取消
```

Only an explicit, unambiguous selection of option 1 or option 2 continues.
Pressing Enter without a choice, giving an ambiguous answer, selecting cancel,
or not responding stops without fetching a repository or writing a file. The
scope prompt itself is the only interaction before source fetching; the CLI is
run with `--yes` only after this confirmation and the separate conflict decision
has been completed.

The selected scope remains fixed for the whole run:

| Selection | Target root | `npx skills add` scope flag |
|---|---|---|
| Current directory | `<original-CWD>/.agents/skills` | none |
| Global user | `$HOME/.agents/skills` | `--global` |

This confirmation authorizes installation of missing Skills only. It does not
authorize replacing an existing target.

### 2. Conflict handling in the selected scope

Codex checks the eighteen exact paths below the selected target root. A file,
directory, or symlink at one of those paths counts as an existing same-name
target. The unselected scope is not modified.

If targets already exist, Codex lists their names and asks once whether to back
up and replace them:

- No, an ambiguous response, or no response: exclude all existing names from
  the install commands, report them as `skipped-existing`, and continue with
  missing names only.
- Explicit yes: create one unique backup directory in the selected scope:
  `<original-CWD>/.agents/.pretty-backups/<run-id>/` for a project installation,
  or `$HOME/.agents/.pretty-backups/<run-id>/` for a global installation. Move
  the existing targets there before reinstalling their names. If a backup move
  fails, restore targets already moved during this run and stop before
  installation.

Backups are retained and reported. The prompt never silently deletes or
overwrites an existing Skill.

### 3. Install from the latest sources

Codex runs the appropriate command from the original `$CWD` for each repository
that still has at least one Skill to install. It passes the repository URL
without a Git ref and explicitly lists only the missing or authorized
replacement names.

```text
# Current-directory scope (default; no --global)
npx skills@1.5.22 add <repository-url> --agent universal --copy --full-depth --yes --skill <name...>

# Global-user scope (only when explicitly selected)
npx skills@1.5.22 add <repository-url> --global --agent universal --copy --full-depth --yes --skill <name...>
```

With no ref in `<repository-url>`, `npx skills` fetches the remote default
branch's latest commit for that invocation. The prompt does not clone sources
itself, check out a commit, or reuse a previous checkout.

In `skills@1.5.22`, the `universal` target is the CLI name for
`.agents/skills`: without `--global` it writes to `$CWD/.agents/skills`, and
with `--global` it writes to `$HOME/.agents/skills`. This target is used because
those are the current repository and user locations documented for Codex.

`--copy` ensures the installation does not depend on a temporary checkout.
`--full-depth` discovers Skills in nested or hidden directories. Explicit
`--skill` names prevent unrelated Skills from the same repository being
installed.

If a command fails, Codex stops and reports the selected scope, source URL,
installed names, skipped names, missing names, and retained backup path. It does
not substitute a different source or dependency set.

### 4. Verify and report

Codex directly verifies all eighteen expected directories below the selected
target root, verifies each `SKILL.md`, and checks that its frontmatter `name`
matches the expected directory name. Direct target inspection is authoritative.

It also runs the list command matching the confirmed scope from the original
`$CWD`:

```text
# Current-directory scope
npx skills@1.5.22 list --agent universal --json

# Global-user scope
npx skills@1.5.22 list --global --agent universal --json
```

Success requires all eighteen names to be present in the selected target root.
The final report includes the selected scope, absolute target root, latest
default-branch source policy, all source URLs, the retained backup path when
applicable, and separate lists for:

- `installed`
- `replaced`
- `skipped-existing`
- `missing-or-failed`

Skipped existing Skills satisfy presence only; they are not asserted to match
the latest remote source. If Codex does not discover newly installed Skills
immediately, the prompt recommends restarting Codex once.

## Error policy

An empty, ambiguous, or cancel response to the scope question ends the run
without changes. After explicit confirmation, the prompt stops and reports the
failing command when:

- a prerequisite is missing;
- a repository or npm package is unreachable;
- Git credentials are unavailable;
- a repository's remote default branch cannot be fetched;
- `npx skills@1.5.22` cannot find a requested Skill;
- backup or installation fails; or
- final verification finds a missing or mismatched name.

There is no custom error-code taxonomy, transaction journal, background retry,
commit pin, or automatic source substitution.

## Testing

The static Python contract verifies that the prompt contains:

- exactly the five Pretty and thirteen external Skill names;
- all nine source URLs and no fixed Git object ID, ref suffix, or release commit
  placeholder;
- direct repository-URL installation and the latest-default-branch policy;
- `npx skills@1.5.22` install and list commands;
- the three scope choices, current-directory default, global-user alternative,
  and the rule that no fetch or write occurs before explicit confirmation;
- `universal` as the target agent, a project command without `--global`, and a
  global command with `--global`;
- selected-scope conflict checks, default skip, separate replacement consent,
  retained backup, and final eighteen-name verification; and
- no custom installer, hash checker, lease, journal, or transaction-recovery
  mechanism.

A contributor smoke check runs:

```text
npx skills@1.5.22 add . --list --full-depth
```

It confirms that the Pretty repository exposes exactly the five Pretty names
without writing to the contributor's project or user scope.

Before internal distribution, test the prompt with a disposable current
directory and a disposable user home, covering both scope choices. Publishing
or pushing remains a separate release action.

## GitHub migration

When Pretty is available on GitHub, update only its repository URL and repeat
the two disposable-scope smoke tests. The dependency catalog,
latest-default-branch policy, conflict policy, commands, and scope choices do
not change.

## Acceptance criteria

- An internal user sends one prompt to Codex.
- Before any fetch or write, Codex presents current directory as the default and
  global user as the alternative, then proceeds only after an explicit scope
  selection.
- Missing members of the 5 + 13 closure are installed into the confirmed target:
  `<original-CWD>/.agents/skills` or `$HOME/.agents/skills`.
- Every repository is fetched from its remote default branch without a commit,
  tag, branch, or other ref specification.
- Existing same-name targets in the selected scope are skipped and reported by
  default.
- Replacement occurs only after a separate explicit affirmative answer and
  retains a backup.
- Final output accounts for all eighteen names in the selected scope.
- No custom installer runtime exists in the repository.

## Reference

- [OpenAI Codex Skills](https://developers.openai.com/codex/skills/): Codex
  loads repository Skills from `$CWD/.agents/skills` and user Skills from
  `$HOME/.agents/skills`, and detects changes automatically.
