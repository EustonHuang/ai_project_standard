# history/ Schema Specification (folder form, architecture 003)

Every plan folder MUST carry its history as a **folder of per-event files**
(architecture 002). The old single-file `history.json` array was architecture 001 and
has been migrated away.

The log is **append-only**: writing a new event means writing a **new file**. Existing
event files are never edited. Mistakes are corrected by appending a new `correction`
event (see §4).

> **`schema_version` bump 策略（Q18）**
> - **MAJOR**（如 `1.0 → 2.0`）：删除字段、重命名字段、或改变既有字段的语义/形态。
> - **MINOR**（如 `2.0 → 2.1`）：仅新增**可选**字段，旧事件仍有效。
> - 事件级 `schema_version` 随每次形态变更而 bump；常量 `EVENT_SCHEMA_VERSION` 在脚本中同步升版。
> - **形态 lineage**：`1.0` = 含 `timestamp` 字段（事件 #1–#14）；`2.0` = 无 `timestamp`、且
>   `source.model` 必须来自平台可信信号（旧事件 #15–#33 因历史原因仍标 `1.0`，属已知失真，**不回改**，
>   由 `history/028.json` 的 `comment_added` 标注 lineage）。

---

## 1. Layout

```
<plan or adopted project>/
  history/001.json, 002.json …        one file per event
  questions/001.md, 002.md …          one file per Q&A
  issues/001/{description.json, assets/} …
  improvements/001.md, 002.md …       one file per improvement proposal (architecture 004)
  architecture/001.md, 002.md …       one file per architecture / standard version
  skills/                             built-in skills: install-standard / update-standard / check-standard
  scripts/  references/  assets/
  # indexes live at the PLAN ROOT (siblings of the category folders)
  history_index.json  questions_index.json  issues_index.json
  improvement_index.json  architecture_index.json
  #   architecture_index.json 还承载 plan 级字段 plan_id/plan_title/created_at 与 notes
  # TOCs (5 类，均由脚本自动生成，请勿手改)
  architecture_TOC.md  history_TOC.md  questions_TOC.md  issues_TOC.md  improvement_TOC.md
  standard_version                     lock file: standard_version=vX.Y, pinned=... (architecture 004)
  .codebuddy/settings.json            hooks point to scripts/turn_gate.py (per adopter)
  .lock                               commit lock (runtime only)
```

- Zero-padded 3-digit IDs (`001`–`999`). If the count exceeds `999`, re-pad lower files
  to 4 digits before writing `1000.json` (keeps directory listing in order).
- **Indexes are NEVER placed inside the category folders** — they sit at the plan root so
  they stay findable when a category folder grows large.
- **`*_meta.json` 已取消（architecture 003）**：四个 `*_meta.json` 已删除；plan 级字段并入
  `architecture_index.json` 顶部，非结构化说明并入各 `*_index.json` 的 `notes`。
- `improvements/` (architecture 004) is a parallel, append-only category: each file is an
  improvement proposal; `improvement_index.json` records `max_id`/`revision`/`briefs`
  (`id`, `title`, `status`, `priority`, `in_architecture`, `implemented_in`); `improvement_TOC.md`
  is auto-generated. Status: `1 Drafting` / `2 Recorded In Architect` / `3 Implemented` (frozen).
- The five `*_TOC.md` are auto-generated from the indexes; never hand-edit them.

---

## 2. Event file (`history/{zeroed_id}.json`)

```json
{
  "schema_version": "2.0",
  "event_id": 1,
  "event_type": "plan_modified",
  "actor": { "type": "ai", "identity": "CodeBuddy agent", "detail": "..." },
  "source": { "user_prompt": "...", "model": "<platform signal, else 'unknown'>", "model_confidence": "confirmed", "tool": "CodeBuddy" },
  "operation": { "target_files": ["..."], "change_summary": "...", "sections_affected": [] },
  "correction": null,
  "comments": "...",
  "recorded_by": "ai",
  "recorded_at": "2026-10-03T14:56:00.585966+08:00",
  "plan_state_snapshot": { "plan_md_sha256": "...", "source_doc": "architecture/002.md" }
}
```

Field reference (unchanged from architecture 001):

- **`schema_version`** — event-level, inside each event. Auto-assigned if absent.
- **`event_id`** — sequential integer; also the filename (`history/001.json`). Assigned
  by the script from `history_index.json.max_id + 1`. Never reused.
- **`event_type`**, **`actor`**, **`source`**, **`operation`**, **`qna`** — see
  `references/record_types.md` and the previous semantics.
- **`correction`** — `null` normally; for `event_type == "correction"` populate
  `corrects_event_id`, `reason`, `detail` (see §4).
- **`plan_state_snapshot`** — snapshot of the **latest architecture doc**
  (`architecture/<latest>.md`). The old hard-coded `plan.md` dependency is gone.
- **`recorded_at`** — ISO-8601 real wall-clock stamped by the script. **No `timestamp`
  field** (removed in architecture 001, still absent).
- **`standard_version`** — (architecture 006 / IMP-003) string, **auto-injected** by the
  script from the project's `standard_version` lock file at record time. A **snapshot** of
  the framework version that produced this event; written once and never changed on later
  framework upgrades, so each history event is traceable to the exact standard version.
  **Forbidden to hand-fill** — the script owns it (mirrored into `history_index.json` briefs).
  Does not alter the `standard_version` file's own "current lock" semantics.

---

## 3. Index files (at plan root)

`history_index.json`:
```json
{ "max_id": 16, "revision": 16,
  "briefs": [ { "event_id": 1, "event_type": "history_initialized",
                "recorded_at": "...", "actor_type": "ai",
                "change_summary": "...", "is_correction": false,
                "file": "history/001.json" } ] }
```

- `max_id` — highest allocated event id. `revision` — commit counter (increments on
  each successful commit); the index content hash is used as the version guard.
- `briefs` — compact per-event summary so callers can `show` **without reading every
  file**. Built from existing authored fields (`change_summary`, `actor.type`) — no
  extra AI summarisation cost.
- `questions_index.json` / `issues_index.json` follow the same shape (`max_id`,
  `revision`, `briefs`).
- `architecture_index.json` instead carries `implemented_version`, `latest_version`,
  `revision`, `versions[]`. `implemented_version == latest_version` means the target
  architecture is fully executed. It also carries the **plan-level fields**
  `plan_id` / `plan_title` / `created_at` (formerly in `architecture_meta.json`) and an
  optional `notes` string/array. Each `*_index.json` may carry a `notes` field for
  non-structured说明 (e.g. `issues_index.json.notes`, `questions_index.json.notes`).

---

## 4. Correction protocol

1. Do **not** edit the erroneous event file.
2. Append a **new** event file whose `event_type` is `correction` and whose
   `correction` object references `corrects_event_id`.
3. Readers MUST treat a correction as authoritative over the referenced event for any
   disputed field.

---

## 5. Concurrency & failure fallback

`append` commits under a mutual-exclusion lock (`.lock`, PID + TTL) **plus** an index
version guard (content hash captured at read time, re-checked under the lock):

| Anomaly | Result |
|---------|--------|
| Index hash changed since read (`stale-read`) | abort; record `issues/{n}/` |
| Target file already exists (`collision`) | abort; record `issues/{n}/` |
| Lock busy beyond retries (`lock-timeout`) | abort; record `issues/{n}/` |
| Lock revoked (TTL stolen) (`lock-revoked`) | abort; record `issues/{n}/` |

Each `issues/{n}/description.json` stores `event_type`, `description`, `detected_at`,
`intended_action`, `assets_refs`, `status`; `assets/` keeps the **intended content**
(`intended_*.json`), the conflicting existing content, and an index snapshot — so
nothing is lost and `recover` can replay it once the root cause is fixed.

---

## 6. Migration from the old single-file array

`python scripts/append_history.py migrate --plan <plan_folder>`:
reads the old `history.json` array, writes one file per event into `history/`, rebuilds
`history_index.json`, splits `questions.md` into `questions/*.md` (+ index and TOC),
then the old files are removed after `audit` passes. This is a one-time container
change and does not violate event-level append-only.
