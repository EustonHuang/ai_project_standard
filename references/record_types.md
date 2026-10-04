# Event Types & Enumerations (folder form)

## 1. `event_type` (string, required)

| Value | Meaning | Typical `actor.type` |
|-------|---------|----------------------|
| `history_initialized` | The plan history (`history/` + index) was created. | `ai` / `human` |
| `plan_created` | The plan (architecture doc) and supporting files were first created. | `ai` / `human` |
| `plan_modified` | The plan or related files were changed. | `ai` / `human` |
| `plan_accepted` | The plan was approved/frozen by the user. | `ai` / `human` |
| `plan_rejected` | The plan (or a revision) was rejected. | `ai` / `human` |
| `plan_reopened` | A previously accepted plan was reopened for edits. | `ai` / `human` |
| `correction` | Correction of a prior event (new file; never edits in place). | `ai` / `human` |
| `comment_added` | Standalone annotation clarifying prior events (no plan change). | `ai` / `human` |
| `qna_recorded` | A question was asked and answered; Q&A written to `questions/` and logged here. | `ai` / `human` |

Notes:
- `plan_modified` covers both AI rewrites and detected human manual edits; distinguish
  via `actor.type`.
- A manual human edit later *detected* by the AI is still `plan_modified` with
  `actor.type="human"` and `source.user_prompt="(manual edit - no prompt available)"`.
- `qna_recorded` SHOULD carry the optional `qna` object (`question_ref`, `question`,
  `answer_summary`, `answer_location`) and list the question file in
  `operation.target_files`.

## 2. Issue `event_type` (in `issues/{n}/description.json`)

These are **not** history events; they classify failure records:

| Value | Meaning |
|-------|---------|
| `history_append` | A history append failed or was rejected. |
| `questions_append` | A questions append failed or was rejected. |
| `index_desync` | An index did not match the files on disk. |
| `lock-timeout` | Could not acquire the commit lock within retries. |
| `lock-revoked` | The held lock was stolen (TTL expired) before commit. |
| `stale-read` | The index changed between read and commit. |
| `collision` | The target file already existed (index lagging behind disk). |

## 3. `actor.type` (string, required)

| Value | Meaning |
|-------|---------|
| `ai` | Change produced by an AI agent (e.g. CodeBuddy) acting on a user prompt. |
| `human` | Change made directly by a person (manual editor / terminal), no AI prompt. |

## 4. `source.model_confidence` (required when `actor.type="ai"`)

| Value | Meaning |
|-------|---------|
| `confirmed` | Model known for certain (reported by the environment). |
| `inferred` | Model inferred but not certain. |
| `unknown` | Could not be determined; set `model="unknown"` and explain in `comments`. |

## 5. `source.tool` (string, optional)

| Value | Meaning |
|-------|---------|
| `CodeBuddy` | Change driven through the CodeBuddy agent. |
| `manual_editor` | Changed directly in an editor (human). |
| `unknown` | Not determined. |

## 6. `recorded_by` (string, required)

Who wrote *this history record* (`ai` | `human`). Usually equals `actor.type`.

## 7. `schema_version` (string, required per event)

Event-level, carried inside every event object (default `"1.0"`, auto-assigned).
Denotes the event's own field schema — there is **no file-level `schema_version`**.
The legacy `timestamp` field remains **removed**; the write time is `recorded_at`.
