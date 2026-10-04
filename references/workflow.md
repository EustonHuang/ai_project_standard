# Workflow: When & How to Record (folder form)

This skill enforces a **fully traceable, append-only** revision history for any plan.

## 0. Locate or create the plan history

A plan folder contains the architecture doc (`architecture/`) and its history lives
alongside it: `history/` (one file per event), `questions/`, `issues/`, with indexes
and metas at the **plan root**.

```bash
python scripts/append_history.py init --plan <plan_folder>
# optionally attach plan-level meta (written into architecture_index.json, NOT a *_meta.json):
python scripts/append_history.py init --plan <plan_folder> --meta <plan_id> "<title>"
```

Migrating a legacy plan (single `history.json` array + `questions.md`):
```bash
python scripts/append_history.py migrate --plan <plan_folder>
python scripts/append_history.py audit  --plan <plan_folder>
# then remove the legacy history.json / questions.md
```

## 1. Event emission rules

| Trigger | Emit | `actor.type` |
|---------|------|--------------|
| Plan folder + architecture doc created | `plan_created` (preceded by `history_initialized`) | whoever created it |
| AI rewrites/extends the plan per a user prompt | `plan_modified` | `ai` |
| Plan changed since last event but no AI prompt exists | `plan_modified` | `human` |
| User says "accept / approved / freeze" | `plan_accepted` | per `source` |
| User says "reject / redo" | `plan_rejected` | per `source` |
| Accepted plan reopened | `plan_reopened` | per `source` |
| Wrong/uncertain prior record found | `correction` (new file, never an edit) | per `source` |
| Annotation without plan change | `comment_added` | per `source` |
| User asks a question during plan work | `qna_recorded` | per `source` |

## 2. Capturing provenance (do not skip)

For every `ai` event fill `source` completely: `user_prompt` (**full verbatim**),
`model`, `model_confidence`, `tool`. Unknown → `unknown` + explain in `comments`.
For `human` events: `source.user_prompt = "(manual edit - no prompt available)"`,
`model = "n/a"`, and note the detection method in `comments`.

## 3. Appending an event

```bash
python scripts/append_history.py append --plan <plan_folder> --event event.json
# or: ... --event -   (JSON from stdin)
```

The script:
- reads `history_index.json` (`max_id`) and captures the index version (content hash),
- assigns `event_id = max_id + 1` → target `history/{zeroed_id}.json`,
- fills `schema_version` (**`"2.0"`** for new events), `recorded_at`, resolves
  `source.model` from a **platform-trusted signal** (env `CODEBUDDY_MODEL`; otherwise
  `"unknown"` + `model_confidence="unknown"`, never self-reported `"Hy3"`), and attaches
  a snapshot of the latest architecture doc,
- commits **under a lock**: re-checks the index version, checks the target does not
  exist, and verifies it still owns the lock,
- writes `history/{id}.json`, updates `history_index.json` (max_id, revision, brief), and
  **auto-regenerates `history_TOC.md`**.

> **TOC is auto-generated.** After any `append`/`rebuild-index`/`set-implemented`, the
> matching `*_TOC.md` is refreshed by the script. To rebuild all four at once:
> `python scripts/append_history.py gen-toc --plan <plan_folder> --kind all`.
> Browse recent activity with `show --last N` (default 50; `--last 0` = all) — it reads
> only the index, never every file, so context cost stays constant.
Any anomaly aborts and records an issue under `issues/{n}/` with the intended content
preserved (see `references/history_schema.md` §5). **Never** hand-edit an event file.

## 4. Immutability & correction (critical)

- Append-only: a new event is a **new file**. Never edit an existing event file.
- To fix a record, append a `correction` event referencing `corrects_event_id`.
- Corrections are authoritative over the referenced event for disputed fields.

## 5. Human–machine separation (critical)

Set `actor.type` truthfully: `ai` (prompt-driven) vs `human` (manual edit). This is
what makes "数据来源有迹可循" verifiable.

## 6. Validation checklist before finishing a turn

- [ ] `history/` exists and contains `{zeroed_id}.json` for every event id, no gaps.
- [ ] Every change this turn produced at least one event file.
- [ ] `actor.type` and full `source` are populated.
- [ ] `recorded_at` present (script stamps it); no `timestamp` field.
- [ ] `history_index.json` at the plan root is up to date (briefs match files).
- [ ] Uncertainties noted in `comments`, not hidden.
- [ ] No existing event was edited; corrections are new files.
- [ ] 本轮所有 plan 文件改动已被 Stop hook（`turn_gate.py end`）强检覆盖——未覆盖时 hook 会 `exit 2` 强制回头补记；这是对「任何改动都要进 history」的机械兜底（Q15–Q17）。
- [ ] `python scripts/append_history.py audit --plan <plan_folder>` passes.

## 7. Recording questions & answers (Q&A)

When the user asks a question during plan work:

1. Write the Q&A as `questions/{zeroed_num}.md` (e.g. `questions/011.md`):
   ```bash
   python scripts/append_history.py append --plan <plan_folder> --kind questions \
     --body question.md --question-ref Q11 --question "<the question>" \
     --answer-summary "<short answer>"
   ```
   This writes the file, updates `questions_index.json`, and regenerates
   `questions_TOC.md` (both at the plan root).
2. Append a `qna_recorded` event to `history/` with:
   - `operation.target_files`: `["questions/011.md"]`
   - `qna`: `{ question_ref, question, answer_summary, answer_location }`
   - full provenance in `source`.

The verbatim Q&A lives in `questions/`; the history event provides the audit trail.
**双录是强制的**：写 `questions/{n}.md` 与追加 `qna_recorded` 事件二者缺一不可——缺一不可视为漏记（会触发 Stop hook 强检）。
