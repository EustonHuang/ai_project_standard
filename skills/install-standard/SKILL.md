---
name: install-standard
description: >-
  Adopt the AI Project Standard framework into a project: copies the engine into
  .plan-standard/, writes the standard_version lock file, configures the
  turn_gate hooks, and scaffolds history/ questions/ issues/ improvements/
  architecture/. Use for self-adoption (the framework repo) or for any project.
---

# Install Standard

Adopt the AI Project Standard into `<project>`. The framework is a metastandard,
not a skill — adopters hold only a version pointer (lock file), not a copy of the
rules.

## Usage

```bash
# adopt a specific version (copies engine into <project>/.plan-standard/)
python3 <framework>/scripts/standard_ops.py install --version v0.4 --project <project>

# self-adoption: the framework repo adopts itself (no engine copy; gate watches repo)
python3 scripts/standard_ops.py install --self --project .
```

- `--version vX.Y | latest` — framework version to adopt (default `latest`).
- `--self` — `<project>` IS the framework repo; gate watches the repo, skip engine copy.
- `--framework <path>` — framework git repo (default: the repo containing this skill).
- `--pinned latest | <ver>` — whether to auto-follow latest (default `latest`).

## What it does
1. **copy mode**: copies `scripts/ references/ assets/` **and `README.md`** into
   `<project>/.plan-standard/`, pinned to the requested tag via `git archive` (README.md
   is included so the always-apply rule's "read `.plan-standard/README.md`" reference resolves).
2. writes `<project>/standard_version` lock file (`standard_version`, `pinned`,
   `framework_repo`, `install_mode`).
3. writes `<project>/.codebuddy/settings.json` hooks — `UserPromptSubmit`→`begin`,
   `PostToolUse`→`record`, `Stop`→`end` — targeting `turn_gate.py`, scoped to the
   project via `PLAN_HISTORY_ROOT=$CODEBUDDY_PROJECT_DIR`.
4. scaffolds `<project>/{history,questions,issues,improvements,architecture}/` + indexes + TOCs.
5. writes `<project>/.codebuddy/rules/ai-project-standard/RULE.mdc` — an **always-apply
   rule** (`alwaysApply: true`) that injects the standard's context at every new
   session start, instructing the agent to read `<project>/.plan-standard/README.md`
   (self mode: `<project>/README.md`) + `references/workflow.md` and follow the
   "any change must land in history" gate. Name collision → **force replace**
   (single-version truth; no prompt/backup).

## After install
Record the adoption as a `plan_modified` event in the project's `history/` so it is
covered by the gate. Verify with `check-standard`.
**生效提示**：规则仅在**新会话开始**注入——安装/升级后请**新建对话会话**使其生效；
`hooks` 是否被 IDE 执行属平台未公开背书项，请实测（改受管文件看是否 `exit 2` 拦截）。
