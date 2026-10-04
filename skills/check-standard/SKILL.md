---
name: check-standard
description: >-
  Report a project's adopted AI Project Standard version vs the latest available,
  whether it is behind, and how many improvements are not yet implemented.
---

# Check Standard

Report the framework version an adopter project is on versus the latest.

## Usage

```bash
python3 <framework>/scripts/standard_ops.py check --project <project>
```

- `--framework <path>` — framework git repo (default: from the project's lock file).

## Output
- `current standard_version` — from `<project>/standard_version` (or "(未安装)").
- `latest standard_version` — latest `vX.Y` git tag in the framework repo.
- `状态` — 最新 / 落后（有可用更新）.
- `未实施改进 (status<3)` — count of open improvements in the project's
  `improvement_index.json` (if present).

Use this to warn an adopter that it is running an outdated standard before edits.
