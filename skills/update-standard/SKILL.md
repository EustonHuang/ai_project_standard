---
name: update-standard
description: >-
  Upgrade a project's adopted AI Project Standard version. Same major => auto
  upgrade; cross major (breaking) => requires --confirm-breaking and a human
  breaking-change review before hooks/lock are touched.
---

# Update Standard

Upgrade the framework version an adopter project uses.

## Usage

```bash
# upgrade to latest
python3 <framework>/scripts/standard_ops.py update --project <project>

# upgrade to a specific version
python3 <framework>/scripts/standard_ops.py update --project <project> --to v0.5

# cross-major upgrade needs an explicit confirmation + human review
python3 <framework>/scripts/standard_ops.py update --project <project> --to v1.0 --confirm-breaking
```

- `--to latest | <vX.Y>` — target version (default `latest`).
- `--framework <path>` — framework git repo (default: from the project's lock file).
- `--confirm-breaking` — REQUIRED when crossing a major version; prints the
  breaking-change review and only then updates hooks + lock.

## Behavior
- Reads `<project>/standard_version` for the current version + framework repo.
- **Same major** (e.g. v0.4 → v0.5): backward-compatible, auto-upgrade engine + lock.
- **Cross major** (e.g. v0.4 → v1.0): non-backward-compatible. Without
  `--confirm-breaking` it only prints the breaking-change review (per `architecture/NNN.md`
  `breaking: true` + `breaking_items`) and exits without changing anything. With
  `--confirm-breaking` it applies the upgrade after the review output is acknowledged.

## After update
Record the upgrade as a `plan_modified` event. Verify with `check-standard`.
