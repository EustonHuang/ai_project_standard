---
name: register-custom-feature
description: >-
  Register a project-specific custom feature (e.g. topic_plan) into custom_categories.json so it
  gets custom/<feature>/ plus custom/<feature>_index.json and custom/<feature>_TOC.md, and becomes
  managed (history gate + per-feature sync). Idempotent — prints a notice and stops when the
  feature is already registered. Use when a project needs a record category beyond
  history/questions/issues/improvements/architecture (topic plans, code plans, review notes...).
---

# Register Custom Feature

Every project has domain artifacts the standard cannot ship in advance. Instead of hardcoding
them, a project **registers** what it needs. Registration is the only way a `custom/<feature>/`
folder becomes managed — nothing under `custom/` is predefined by the framework.

## Usage

```bash
# self mode (the framework repo itself)
python3 scripts/append_history.py custom register --plan . --name topic_plan

# copy mode (an adopting project: engine lives in .plan-standard/)
python3 .plan-standard/scripts/append_history.py custom register --plan . --name topic_plan
```

- `--name` (required) — the feature folder name; letters/digits/`_`/`-` only (e.g. `topic_plan`).
- `--description` — optional one-liner.

## What it does

1. Reads `<project>/custom_categories.json` (the declaration list).
2. **Already registered → prints a notice and stops. Nothing is changed (exit 2).**
3. Otherwise: appends the feature to the list, creates `custom/<name>/`, and generates
   `custom/<name>_index.json` + `custom/<name>_TOC.md`.

## Record conventions under `custom/<name>/`

The standard dictates exactly two things — everything else is the project's own business:

- A record file **must start with a zero-padded number**:
  `001-spark-helloworld.md`, `002-rdd.md`. The separator and the topic wording are free
  (`001_spark_helloworld.md` is equally valid).
- Extra explanation files for a record live in the **same-named directory**:
  `001-spark-helloworld/spark-introduction.md`. The pairing is by name, so it is always clear
  which record the extra files belong to.

Revising a record = appending a **NEW numbered file** (the old one is frozen). The standard
prescribes no frontmatter and no version fields — ordering is guaranteed by the filename
number, so what changed simply goes in the new file's body. Never rewrite a record in place.

## After registering

- Every write under `custom/<name>/` rebuilds **only** `custom/<name>_index.json` and
  `custom/<name>_TOC.md` (PostToolUse hook). Other features are never touched.
- Those two files are managed: the turn's history event must list the changed record **and**
  the regenerated index/TOC in `operation.target_files`, or the turn gate blocks.
