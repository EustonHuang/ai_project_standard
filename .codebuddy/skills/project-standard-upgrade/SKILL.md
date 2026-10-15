---
name: project-standard-upgrade
description: >-
  Global orchestrator that upgrades installed AI Project Standard projects in
  batch: lists projects behind the latest version and upgrades them (all, or
  specified project(s) at an optional explicit version). Use when asked
  "把落后规范的项目都升上去/批量升级规范/哪些项目该升级".
---

# Project Standard Upgrade

Repo-local ops skill for **this framework repo only** (not distributed to adopters).
It is the multi-project orchestrator around `update-standard`: discovery + batch
driving; the real upgrade still runs through `scripts/standard_ops.py update`.

## Usage

```bash
# default: list only — projects whose version != latest
python3 .codebuddy/skills/project-standard-upgrade/upgrade.py --list

# upgrade every behind project to latest
python3 .codebuddy/skills/project-standard-upgrade/upgrade.py --all

# upgrade one project to latest
python3 .codebuddy/skills/project-standard-upgrade/upgrade.py --target /path/to/projA

# multiple, some pinned
python3 .codebuddy/skills/project-standard-upgrade/upgrade.py \
  --target /path/to/projA=v0.8 --target /path/to/projB

# allow cross-major updates (otherwise breaking review is printed and skipped)
python3 .codebuddy/skills/project-standard-upgrade/upgrade.py --all --confirm-breaking

# print planned commands without changing anything
python3 .codebuddy/skills/project-standard-upgrade/upgrade.py --all --dry-run
```

`--target` repeats; form is `<project>=<version>`, version omitted means latest.

## Underlying command

```bash
python3 <framework>/scripts/standard_ops.py update --project <proj> --to <version> [--confirm-breaking]
```

Same path `update-standard` uses.

## Notes

- In-major upgrades run automatically; cross-major (breaking) needs `--confirm-breaking`.
- Upgrades rewrite each target's `standard_version` lock and `.codebuddy` rules/hooks —
  **start a new session in each target project for the rules to take effect**.
- Target discovery comes from `project-standard-monitor/scan.py --json`, whose scope is
  set by `project-standard-monitor/projects.config.json` `scan_roots`.
