#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Turn-end history gate (Q15–Q17, architecture 003).

Designed to be driven by CodeBuddy Hooks:
  UserPromptSubmit -> begin   (records baseline_max_id for this turn)
  PostToolUse      -> record  (books every file this turn's edit tools touch)
  Stop             -> end     (hard gate: if this turn touched plan files, a new
                              history event MUST cover them, else exit 2)

State is kept per session so concurrent turns do not cross-talk, and only files
INSIDE the plan root are gated (non-plan files are ignored). No full-directory
mtime scan — cost is O(num files touched this turn).

The plan root is this skill folder (where the script lives, one level up from
scripts/). History lives at <plan root>/history/.
"""

import argparse
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PLAN_ROOT = os.path.dirname(SCRIPT_DIR)
TURN_DIR = os.path.join(PLAN_ROOT, ".codebuddy", "hooks", ".turn")
HISTORY_INDEX = os.path.join(PLAN_ROOT, "history_index.json")
EDIT_MATCHERS = ("write_to_file", "replace_in_file", "delete_file", "Write", "Edit")


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def session_id():
    return (os.environ.get("CODEBUDDY_SESSION_ID")
            or os.environ.get("CODEBUDDY_CONVERSATION_ID")
            or ("local-%d" % os.getpid()))


def state_path():
    return os.path.join(TURN_DIR, "%s.json" % session_id())


def load_state():
    p = state_path()
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p, "r", encoding="utf-8"))
    except Exception:
        return None


def save_state(state):
    os.makedirs(TURN_DIR, exist_ok=True)
    tmp = state_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, state_path())


def baseline_max_id():
    if os.path.exists(HISTORY_INDEX):
        try:
            idx = json.load(open(HISTORY_INDEX, "r", encoding="utf-8"))
            return int(idx.get("max_id", 0))
        except Exception:
            return 0
    return 0


def norm_rel(path):
    """Return path relative to PLAN_ROOT if inside it, else its basename."""
    ap = os.path.abspath(path)
    rp = os.path.relpath(ap, PLAN_ROOT)
    if rp.startswith(".."):
        return os.path.basename(ap)
    return rp.replace(os.sep, "/")


def in_plan(path):
    ap = os.path.abspath(path)
    rp = os.path.relpath(ap, PLAN_ROOT)
    return not rp.startswith("..")


def read_stdin_json():
    try:
        data = sys.stdin.read().strip()
        if not data:
            return None
        return json.loads(data)
    except Exception:
        return None


def extract_filepath(payload):
    if not isinstance(payload, dict):
        return None
    for key in ("filePath", "file_path", "path", "file"):
        if payload.get(key):
            return payload[key]
    # nested under tool_input (some hook payloads nest it)
    ti = payload.get("tool_input") or payload.get("input")
    if isinstance(ti, dict):
        for key in ("filePath", "file_path", "path", "file"):
            if ti.get(key):
                return ti[key]
    return None


# --------------------------------------------------------------------------
# sub-commands
# --------------------------------------------------------------------------
def cmd_begin(args):
    state = {
        "session_id": session_id(),
        "baseline_max_id": baseline_max_id(),
        "declared": [],
        "ts": __import__("time").time(),
    }
    save_state(state)
    print("turn_gate begin: baseline_max_id=%s (session=%s)"
          % (state["baseline_max_id"], state["session_id"]))


def cmd_record(args):
    state = load_state()
    if state is None:
        # No begin seen this turn (e.g. hook fired before begin); start fresh.
        state = {"session_id": session_id(), "baseline_max_id": baseline_max_id(),
                 "declared": [], "ts": __import__("time").time()}

    # Prefer explicit --file, then stdin JSON (hook payload), then env.
    fp = args.file
    if fp is None:
        payload = read_stdin_json()
        if payload is not None:
            fp = extract_filepath(payload)
    if fp is None:
        fp = os.environ.get("CODEBUDDY_FILE_PATH")

    added = False
    if fp and in_plan(fp):
        rel = norm_rel(fp)
        if rel not in state["declared"]:
            state["declared"].append(rel)
            added = True
    if added:
        save_state(state)
        print("turn_gate record: declared += %s (total %d)"
              % (norm_rel(fp) if fp else fp, len(state["declared"])))
    else:
        print("turn_gate record: no in-plan file to book.")


def _new_event_targets(baseline):
    """Return set of target_files (normalized) from events with id > baseline."""
    targets = set()
    if not os.path.isdir(os.path.join(PLAN_ROOT, "history")):
        return targets
    for name in sorted(os.listdir(os.path.join(PLAN_ROOT, "history"))):
        if not name.endswith(".json"):
            continue
        try:
            eid = int(name[:-5])
        except Exception:
            continue
        if eid <= baseline:
            continue
        try:
            ev = json.load(open(os.path.join(PLAN_ROOT, "history", name), "r", encoding="utf-8"))
        except Exception:
            continue
        for tf in (ev.get("operation") or {}).get("target_files", []) or []:
            targets.add(norm_rel(tf))
    return targets


def cmd_end(args):
    state = load_state()
    if state is None:
        # Nothing was booked for this turn -> nothing to gate.
        print("turn_gate end: no turn state; nothing to gate.")
        sys.exit(0)

    declared = [d for d in state.get("declared", []) if in_plan(d)]
    if not declared:
        print("turn_gate end: no in-plan files changed this turn; gate passed.")
        sys.exit(0)

    baseline = state.get("baseline_max_id", 0)
    targets = _new_event_targets(baseline)
    declared_set = set(norm_rel(d) for d in declared)
    uncovered = sorted(declared_set - targets)

    if uncovered:
        print("turn_gate end: FAILED — this turn changed plan files but history was "
              "not updated to cover them:", file=sys.stderr)
        for u in uncovered:
            print("  - %s" % u, file=sys.stderr)
        print("  (new events must have event_id > %d and list these in "
              "operation.target_files)" % baseline, file=sys.stderr)
        sys.exit(2)

    print("turn_gate end: gate passed (%d in-plan file(s) covered by new history)."
          % len(declared_set))
    sys.exit(0)


def cmd_check(args):
    changed = args.changed or []
    in_plan_files = [c for c in changed if in_plan(c)]
    if not in_plan_files:
        print("turn_gate check: no in-plan files in --changed; nothing to verify.")
        sys.exit(0)
    # Default baseline = tip before the most recent append, so the latest event is
    # treated as "this turn's recording" (mirrors `end` with a begin baseline).
    tip = baseline_max_id()
    baseline = args.since if args.since is not None else max(0, tip - 1)
    targets = _new_event_targets(baseline)
    declared_set = set(norm_rel(c) for c in in_plan_files)
    uncovered = sorted(declared_set - targets)
    if uncovered:
        print("turn_gate check: UNCOVERED (not yet recorded in history):")
        for u in uncovered:
            print("  - %s" % u)
        sys.exit(2)
    print("turn_gate check: all %d changed in-plan file(s) covered "
          "(events > #%d)." % (len(declared_set), baseline))
    sys.exit(0)


def main():
    p = argparse.ArgumentParser(description="Turn-end history gate (Q15–Q17).")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("begin")
    pr = sub.add_parser("record")
    pr.add_argument("--file", help="explicit file path (else read hook stdin/env)")
    pe = sub.add_parser("end")
    pc = sub.add_parser("check")
    pc.add_argument("--changed", nargs="+", help="files changed this turn (declarative)")
    pc.add_argument("--since", type=int, default=None,
                    help="baseline event id; events with id > since are checked (default: tip-1)")

    args = p.parse_args()
    {"begin": cmd_begin, "record": cmd_record, "end": cmd_end, "check": cmd_check}[args.cmd](args)


if __name__ == "__main__":
    main()
