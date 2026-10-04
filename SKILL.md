---
name: plan-history-recorder
description: >-
  Records an append-only, fully-traceable revision history for any plan/design
  document. Every operation — including the full user prompt, the model that
  produced the result, and human-vs-AI authorship — is logged as one file per event
  under history/, one file per Q&A under questions/, and one folder per failure under
  issues/. Indexes and metas live at the plan root. Existing records are never edited;
  errors are corrected by appending a new correction event.
---

# Plan History Recorder

## Purpose
Keep a verifiable audit trail of how a plan evolved: every create / modify / accept
operation is recorded with full provenance, and the log is append-only so the history
itself is trustworthy ("数据来源有迹可循").

## Layout (architecture 003)

```
<plan>/
  history/001.json …            one file per event
  questions/001.md …            one file per Q&A
  issues/001/{description.json, assets/} …
  architecture/001.md …         one file per architecture version
  # indexes at the PLAN ROOT (never inside the category folders)
  history_index.json  questions_index.json  issues_index.json  architecture_index.json
  #   architecture_index.json 还承载 plan 级字段 plan_id/plan_title/created_at 与 notes
  # TOCs (4 类，均由脚本自动生成，请勿手改)
  architecture_TOC.md  history_TOC.md  questions_TOC.md  issues_TOC.md
  .lock                          commit lock (runtime only)
```

> **`*_meta.json` 已取消（architecture 003）**：四个 `*_meta.json` 已删除；原 plan 级字段
> (`plan_id`/`plan_title`/`created_at`) 并入 `architecture_index.json` 顶部，非结构化说明并入各
> `*_index.json` 的 `notes` 字段。索引仍是**可重建的派生缓存**。

Writing a new event = writing a **new file**, so append-only is filesystem-native.
`architecture_index.json` records `implemented_version` vs `latest_version`, which is
how you tell whether a plan has actually been executed.

## MANDATORY — 任何改动都要进 history

> ⚠️ **高亮规则（不可豁免）**：本 skill 记录的是「计划如何演进」，**任何对 plan 文件的改动都必须登记进 `history/`**，不得以「只是登记索引 / 只是生成物 / 待执行再补 / 只是文档」等理由豁免。漏记会被 Stop hook（`turn_gate.py end`）强制拦截（exit 2）。
>
> - **受管文件清单（包含但不仅限于，非穷举）**：`architecture/*.md`、`*_index.json`、`*_TOC.md`、`questions/*`、`issues/*`、`SKILL.md`、`references/*`、`scripts/*`、`assets/*`、`<workspace>/.codebuddy/settings.json`、以及任何本 skill 目录下的工程文件。
> - **事件类型映射（仅为举例、非穷举）**：架构/索引/脚本/文档改动 → `plan_modified`；用户提问 → `qna_recorded`（问答双录：写 `questions/` + 记事件）；错漏/失真 → `correction`；不确定用什么时 → `plan_modified` + `comments` 说明。**不要因为没有现成枚举就不记。**

## When to use
- Creating a new plan / architecture doc.
- Rewriting or extending an existing plan.
- Accepting, rejecting, or reopening a plan.
- Detecting that the user manually edited the plan outside the agent.
- Discovering a wrong/uncertain prior history record (append a `correction`).
- The user asks a question during plan work (record in `questions/` + `qna_recorded`).
- Any append anomaly (stale read / collision / lock problems) → `issues/`.

## How to use
1. Ensure the folder structure exists:
   `python scripts/append_history.py init --plan <plan_folder>`
   (migrating a legacy plan: `migrate --plan <plan_folder>` then `audit`).
2. Build an event object (schema in `references/history_schema.md`; types in
   `references/record_types.md`; template in `assets/history.template.json`).
3. Append it:
   `python scripts/append_history.py append --plan <plan_folder> --event event.json`
   The script assigns `event_id`, stamps `recorded_at`, attaches an architecture
   snapshot, and commits under a lock + index-version guard.
4. Questions: `append --plan <plan_folder> --kind questions --body q.md \
   --question-ref Q11 --question "..." --answer-summary "..."`.
5. Verify: `python scripts/append_history.py audit --plan <plan_folder>` and
   `show --plan <plan_folder>` (show reads only the root index, never every file).
6. Follow `references/workflow.md`, especially:
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

## Bundled resources
- `scripts/append_history.py` — folder-form logger: `init`, `append`, `show`, `audit`,
  `rebuild-index`, `gen-toc`, `migrate`, `recover`, `set-implemented`.
- `scripts/turn_gate.py` — turn-end forced gate (Q15–Q17): `begin`/`record`/`end`/`check`,
  driven by CodeBuddy Hooks to guarantee every plan change is recorded in `history/`.
- `references/history_schema.md` — field spec, index format, concurrency + issues.
- `references/record_types.md` — event types and issue type enumerations.
- `references/workflow.md` — step-by-step when/how to record + checklist.
- `assets/history.template.json` — starter template for one event file.
- `questions/` — Q&A log (this skill records its own questions here too).

## Notes
- Indexes stay at the plan root so they remain findable as `history/`, `questions/` etc.
  grow. The four `*_TOC.md` are auto-generated from the indexes and must not be hand-edited.
- To activate this as a loadable CodeBuddy skill, copy/move this folder into
  `.codebuddy/skills/plan-history-recorder/` (project) or
  `~/.codebuddy/skills/plan-history-recorder/` (user).
