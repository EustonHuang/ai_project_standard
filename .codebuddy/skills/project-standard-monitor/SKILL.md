---
name: project-standard-monitor
description: >-
  Global scan of which projects have installed the AI Project Standard and at
  which version, plus the latest available version. Use when asked "哪个项目装了规范/装了什么版本/谁落后了/全局扫一遍".
---

# Project Standard Monitor

Repo-local ops skill for **this framework repo only** (not distributed to adopters).

## Usage

```bash
python3 .codebuddy/skills/project-standard-monitor/scan.py            # table
python3 .codebuddy/skills/project-standard-monitor/scan.py --json     # JSON (consumed by upgrade)
python3 .codebuddy/skills/project-standard-monitor/scan.py --max-depth 3
```

## Config

`.codebuddy/skills/project-standard-monitor/projects.config.json`:

```json
{
  "scan_roots": ["/Users/euston/personal"],
  "exclude": ["node_modules", ".git", "__pycache__", ".venv", "venv", ".codebuddy", ".plan-standard", "dist", "build"],
  "max_depth": 4
}
```

- `scan_roots` — list of roots to walk.
- `exclude` — directory names skipped.
- `max_depth` — max levels below each root.

## Output

Per project: path, installed version, status (已最新 / 落后), plus the latest
standard version (highest `vX.Y` git tag in the framework repo, same as `check-standard`).

## Notes

- A project is detected by the presence of a `standard_version` lock file; once found,
  the walker stops descending into it.
- Pairs with `project-standard-upgrade`, which parses `--json` output to pick targets.
