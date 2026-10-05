---
name: ai-project-standard
description: >-
  A cross-project standard framework (metastandard) that defines how any project
  keeps an append-only, fully-traceable revision history: every create / modify /
  accept / reject / question / issue / improvement is logged as one file per event
  under history/, one file per Q&A under questions/, one folder per failure under
  issues/, and one file per improvement under improvements/. Indexes and metas live
  at the plan root. Existing records are never edited; errors are corrected by
  appending a new correction event. Dogfoods itself.
---

# AI Project Standard (formerly "Plan History Recorder")

> **This is a project standard framework (a metastandard), not a CodeBuddy skill.**
> Each of your projects may *adopt* it (you should adopt it for your own projects;
> others may use their own framing). Adopters hold only a version pointer
> (`standard_version` lock file) — not a copy of the framework. Use
> `skills/install-standard` to adopt, `skills/update-standard` to upgrade, and
> `skills/check-standard` to see whether you are behind.

## Purpose
Keep a verifiable audit trail of how a plan / design evolved: every create / modify
/ accept operation is recorded with full provenance, and the log is append-only so
the history itself is trustworthy ("数据来源有迹可循"). This is the **framework's
own spec**; the framework repo dogfoods it (it adopts itself — see `standard_version`).

## Two version axes (do not confuse)
- **Axis A — `standard_version`** (e.g. `v0.4`): the version of *this framework* an
  adopter uses. Declared in the adopter's lock file (`standard_version`).
- **Axis B — project's own version axis**: the adopter's *domain* iterations (e.g. a
  wiki schema version, a product release). Tracked in the adopter's
  `architecture_index.json` `implemented/latest_version`.
- In **this framework repo**, the two axes coincide: `architecture/001..NNN.md` is
  both the framework's standard version (Axis A) and its domain content (Axis B).

## Layout (architecture 004)

```
<standard repo or adopted project>/
  history/001.json …            one file per event
  questions/001.md …            one file per Q&A
  issues/001/{description.json, assets/} …
  improvements/001.md …         one file per improvement proposal
  architecture/001.md …         one file per architecture / standard version
  skills/                       built-in skills: install-standard / update-standard / check-standard
  scripts/                      append_history.py, turn_gate.py, standard_ops.py
  references/  assets/
  # indexes at the ROOT (never inside the category folders)
  history_index.json  questions_index.json  issues_index.json
  improvement_index.json  architecture_index.json
  # TOCs (all auto-generated, do not hand-edit)
  architecture_TOC.md  history_TOC.md  questions_TOC.md  issues_TOC.md  improvement_TOC.md
  standard_version                 lock file: standard_version=vX.Y, pinned=...
  .codebuddy/settings.json         hooks point to scripts/turn_gate.py (per adopter)
  .lock                            commit lock (runtime only)
```

> **`*_meta.json` removed (architecture 003):** plan-level fields
> (`plan_id`/`plan_title`/`created_at`) live in `architecture_index.json`; loose notes
> live in each `*_index.json` `notes`. Indexes are **rebuildable derived caches**.

Writing a new event = writing a **new file**, so append-only is filesystem-native.
`architecture_index.json` records `implemented_version` vs `latest_version`, telling
you whether a plan has actually been executed.

## MANDATORY — any change must land in history

> ⚠️ **Highlight rule (non-waivable):** this framework records how a plan evolves;
> **any modification to a plan file must be logged in `history/`** — no exemption for
> "just updating an index / just a generated file / will backfill after execution /
> just docs". Omissions are force-blocked by the `Stop` hook (`turn_gate.py end`,
> `exit 2`).
>
> - **Managed files (inclusive, non-exhaustive):** `architecture/*.md`,
>   `*_index.json`, `*_TOC.md`, `questions/*`, `issues/*`, `improvements/*`,
>   `README.md`, `references/*`, `scripts/*`, `skills/*`, `assets/*`,
>   `standard_version`, `.codebuddy/settings.json`, and any engineering file under
>   this repo.
> - **Event-type mapping (examples, non-exhaustive):** architecture/index/script/doc
>   change → `plan_modified`; user question → `qna_recorded` (dual-record: write
>   `questions/` + emit event); error/distortion → `correction`; unsure →
>   `plan_modified` + `comments`. **Do not skip recording just because no enum fits.**

## When to use
- Creating / extending / accepting / rejecting / reopening a plan or standard version.
- Detecting that the user manually edited the plan outside the agent.
- Discovering a wrong/uncertain prior history record (append a `correction`).
- The user asks a question during plan work (record in `questions/` + `qna_recorded`).
- A follow-up question arises → **open a NEW question** (do not append "补充追问" to an
  existing one; see `references/workflow.md`).
- An improvement idea is not yet actionable → file it in `improvements/` (see §5 of
  `architecture/004.md`).
- Any append anomaly (stale read / collision / lock problems) → `issues/`.

## How to use
1. Ensure structure exists:
   `python scripts/append_history.py init --plan <plan_folder>`
   (migrating a legacy plan: `migrate --plan <plan_folder>` then `audit`).
2. Build an event object (schema in `references/history_schema.md`; types in
   `references/record_types.md`; template in `assets/history.template.json`).
3. Append it:
   `python scripts/append_history.py append --plan <plan_folder> --event event.json`
   (assigns `event_id`, stamps `recorded_at`, attaches an architecture snapshot,
   commits under a lock + index-version guard).
4. Questions: `append --plan <plan_folder> --kind questions --body q.md \
   --question-ref Q11 --question "..." --answer-summary "..."`.
5. Improvements: `append --plan <plan_folder> --kind improvement --body i.md \
   --title "..." --priority 3 --status 1`.
6. Verify: `python scripts/append_history.py audit --plan <plan_folder>` and
   `show --plan <plan_folder>`.
7. Follow `references/workflow.md`, especially:
   - **Human–machine separation**: `actor.type` = `ai` (prompt-driven) or `human`
     (manual edit). Populate `source` fully for AI events.
   - **Full provenance**: verbatim `user_prompt`, `model`, `tool`. Unknown → `unknown`
     and explain in `comments`.
   - **Append-only**: never edit an existing event file. Fix mistakes by appending a
     `correction` event referencing `corrects_event_id`.
   - **Time**: the timestamp you look at is `recorded_at` (real wall-clock, stamped by
     the script). There is no `timestamp` field.
   - **Model source (Q18)**: `source.model` MUST come from a **platform-trusted signal**
     (env `CODEBUDDY_MODEL`); when unavailable it is set to `"unknown"` with
     `model_confidence="unknown"` and a `comments` note. The agent is **forbidden** from
     self-reporting `"Hy3"`. New events use `schema_version="2.0"`.
   - **Improvements**: fileable but only-append; editable while `status<3`, frozen at
     `status=3` (implemented). See `architecture/004.md` §5.

## Bundled resources
- `scripts/append_history.py` — folder-form logger: `init`, `append`, `show`, `audit`,
  `rebuild-index`, `gen-toc`, `migrate`, `recover`, `set-implemented`.
- `scripts/turn_gate.py` — turn-end forced gate (Q15–Q17): `begin`/`record`/`end`/`check`,
  driven by CodeBuddy Hooks to guarantee every plan change is recorded in `history/`.
- `scripts/standard_ops.py` — shared helpers for the built-in skills.
- `skills/install-standard/` — adopt this standard into a project (writes `standard_version`
  lock file + hooks + scaffolds `history/ questions/ issues/ improvements/`).
- `skills/update-standard/` — upgrade an adopter's `standard_version` (breaking-change
  review across major versions).
- `skills/check-standard/` — report current vs latest framework version.
- `references/history_schema.md` — field spec, index format, concurrency + issues.
- `references/record_types.md` — event types and issue type enumerations.
- `references/workflow.md` — step-by-step when/how to record + checklist.
- `assets/history.template.json` — starter template for one event file.
- `questions/` — Q&A log (this framework records its own questions here too).

## Adopting this standard (dogfooding model)
This repo adopts itself: it holds `standard_version=v0.4` and a `.codebuddy/settings.json`
whose hooks point to its own `scripts/turn_gate.py`. To adopt it into your project:
```bash
python scripts/standard_ops.py install --version v0.4 --project /path/to/your/project
```
or via the `install-standard` skill. The hook is written per-adopter (not shared), so
each project is self-contained.

### What install writes (and a context-load guarantee)
Install (v0.5+) performs five actions: copy the engine into `.plan-standard/`, write the
`standard_version` lock, write per-project hooks, scaffold the history folders, **and
write an always-apply rule `.codebuddy/rules/ai-project-standard/RULE.mdc`**
(`alwaysApply: true`). The rule is what makes the standard's context load: at every
**new session start** CodeBuddy injects the rule text, instructing the agent to read
`README.md` + `references/workflow.md` and follow the "any change must land in history"
gate. We chose `.codebuddy/rules` over `CODEBUDDY.md` because the latter is usually
already present in projects (collision-prone), while a dedicated namespace
(`ai-project-standard`) avoids that; on the rare collision (e.g. reinstalling over an
older rule) install **force-replaces** — single-version truth, no prompt/backup.

> **Session caveat (important):** CodeBuddy injects rules only at session start. After
> `install`/`update` you must **open a new conversation** for the rule to take effect.
> The `hooks` gate is the enforcement backstop, but its execution by the IDE is **not
> documented in CodeBuddy's public docs** — verify empirically (edit a managed file and
> confirm a `turn_gate` `exit 2` block). Do not assume the gate alone guarantees
> compliance; the rule is the load guarantee, the hook is the backstop.

## Notes
- Indexes stay at the plan root so they remain findable as `history/`, `questions/` etc.
  grow. The five `*_TOC.md` are auto-generated from the indexes and must not be hand-edited.
- This framework is version-controlled: from `v0.4` on, every version bump is committed
  and pushed to the GitHub remote, and each `architecture/NNN.md` is tagged (e.g. `v0.4`).
- Repo: `git@github.com:EustonHuang/ai_project_standard.git`.
