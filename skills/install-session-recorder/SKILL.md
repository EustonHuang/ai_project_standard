---
name: install-session-recorder
description: >-
  Opt-in installer for the session recorder (architecture 009): wires four
  recorder_feed hooks into .codebuddy/settings.json (alongside turn_gate, never
  replacing it), writes a launchd LaunchAgent / systemd user unit so the daemon
  survives reboots, adds this project to the watcher's watch_paths, and starts
  the daemon. Fully idempotent — re-running detects existing wiring and does
  nothing. Without it, nothing changes: the recorder is strictly opt-in.
---

# Install Session Recorder

Installs the out-of-process session recorder for **this project**. After
installation every session in this project is traced automatically (prompt,
tool calls incl. skill/web/command, hook firings, turn ends, `.turn`
side-effects) into `~/.ai_project_standard/session_trace/<plan>/<session>.jsonl`.
The agent itself never writes the trace — no log-the-log loop.

## Steps

1. **Engine scripts** — confirm `recorder_feed.py` and `session_recorder.py`
   are reachable:
   - self mode: `$CODEBUDDY_PROJECT_DIR/scripts/`
   - copy mode: `$CODEBUDDY_PROJECT_DIR/.plan-standard/scripts/`
2. **Wire hooks (idempotent)** — in `.codebuddy/settings.json`, APPEND one
   group per event (keep every existing turn_gate entry untouched). A group is
   already installed iff its command contains `recorder_feed`:
   - `UserPromptSubmit` → `recorder_feed.py --kind prompt`
   - `PreToolUse` (matcher `write_to_file|replace_in_file|delete_file`) →
     `--kind tool_intent`
   - `PostToolUse` (matcher `write_to_file|replace_in_file|delete_file|Write|Edit`)
     → `--kind tool_call`
   - `Stop` → `--kind turn_end`
   Each command: `PLAN_HISTORY_ROOT="$CODEBUDDY_PROJECT_DIR" python3
   "$CODEBUDDY_PROJECT_DIR/<engine>/scripts/recorder_feed.py" --kind <kind>`,
   timeout `5`.
3. **Register watch path** — append the project root to
   `~/.ai_project_standard/config.json`:
   `{"watch_paths": ["/abs/project/root"], "transcript_path": null}`
   (merge, don't clobber other entries; `transcript_path` stays null until
   architecture 009 §7-4 verifies CodeBuddy persists a session transcript).
4. **Persistence unit (recommended)** — write
   `~/Library/LaunchAgents/com.ai-project-standard.recorder.plist`
   (macOS) with `RunAtLoad=true`, `KeepAlive=true`, program args
   `python3 <engine>/scripts/session_recorder.py start --foreground`, then
   `launchctl load` it. Linux: systemd user unit
   `~/.config/systemd/user/ai-project-standard-recorder.service` +
   `systemctl --user enable --now`. Skip silently if the user declines.
5. **Start daemon** — `python3 <engine>/scripts/session_recorder.py start`,
   then verify with `status` (running) and `doctor` (coverage audit).

## Verification

- `session_recorder.py status` → running.
- Send any prompt in a new session → `session_trace/<plan>/<session>.jsonl`
  gains `prompt` / `tool_intent` / `tool_call` / `hook` / `turn_end` events.
- `session_recorder.py doctor` → no gaps (or explains the gap).

## Uninstall

Remove the four recorder groups from `settings.json`, the project entry from
`config.json`, the LaunchAgent/unit, then `session_recorder.py stop`.
`install-standard`/`update-standard` preserve recorder wiring (the merge in
`write_hooks` keeps any group whose command contains `recorder_feed`).
