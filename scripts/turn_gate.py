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
import re
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# PLAN_ROOT defaults to the folder that owns this script's `scripts/` dir. Adopting
# projects install the engine under `<project>/.plan-standard/scripts/` and set
# PLAN_HISTORY_ROOT to the project root so the gate watches the project, not `.plan-standard`.
PLAN_ROOT = os.environ.get("PLAN_HISTORY_ROOT") or os.path.dirname(SCRIPT_DIR)
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
# D1 (architecture 007): .turngateignore — project-level, gitignore-flavored
# scratch/exclude rules the turn gate should NOT book or gate on.
# --------------------------------------------------------------------------
def load_turngateignore_lines():
    """Return non-comment, non-empty lines of <plan>/.turngateignore (empty if absent)."""
    p = os.path.join(PLAN_ROOT, ".turngateignore")
    if not os.path.exists(p):
        return []
    out = []
    try:
        with open(p, "r", encoding="utf-8") as f:
            for raw in f.read().splitlines():
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                out.append(line)
    except Exception:
        return []
    return out


def _glob_translate(pat):
    """Translate one gitignore pattern (trailing-slash handled by caller) to regex."""
    res = []
    i, n = 0, len(pat)
    while i < n:
        c = pat[i]
        if pat[i:i + 2] == "**":
            res.append(".*")
            i += 2
            if i < n and pat[i] == "/":
                i += 1
            continue
        if c == "*":
            res.append("[^/]*")
            i += 1
            continue
        if c == "?":
            res.append("[^/]")
            i += 1
            continue
        if c in ".+^${}()|[]\\":
            res.append("\\" + c)
        else:
            res.append(c)
        i += 1
    return "".join(res)


def _pattern_matches(pat, rel):
    """Match rel (normalized, '/'-sep) against one gitignore pattern."""
    dir_only = pat.endswith("/")
    clean = pat.rstrip("/")
    anchored = "/" in clean
    if clean.startswith("/"):
        clean = clean[1:]
        anchored = True
    rx = _glob_translate(clean)
    if anchored:
        regex = "^" + rx
        regex += "(/.*)?$" if dir_only else "$"
        return re.match(regex, rel, re.DOTALL) is not None
    # Unanchored: match the whole rel, or any single path component.
    if re.match("^" + rx + "$", rel, re.DOTALL):
        return True
    for comp in rel.split("/"):
        if re.fullmatch(rx, comp):
            return True
    return False


def is_ignored(rel):
    """True if rel is covered by .turngateignore (gitignore-flavored, supports !negation)."""
    if rel.startswith("./"):
        rel = rel[2:]
    for rule in load_turngateignore_lines():
        neg = rule.startswith("!")
        pat = rule[1:] if neg else rule
        if _pattern_matches(pat, rel):
            return not neg
    return False


# --------------------------------------------------------------------------
# D2 (architecture 007): managed allowlist — the ONLY in-plan paths the
# PreToolUse hard block permits. Everything else is rejected unless it also
# matches .turngateignore. Mirrors README MANDATORY + workflow.md managed set.
# --------------------------------------------------------------------------
MANAGED_PREFIXES = (
    "architecture/", "questions/", "history/", "issues/", "improvements/",
    "references/", "scripts/", "skills/", "assets/", ".codebuddy/",
    # architecture 008: registered custom features live here. The declaration
    # list (custom_categories.json) decides which of them are really managed.
    "custom/",
)
MANAGED_FILES = (
    "architecture_index.json", "architecture_TOC.md",
    "questions_index.json", "questions_TOC.md",
    "history_index.json", "history_TOC.md",
    "issues_index.json", "issues_TOC.md",
    "improvement_index.json", "improvement_TOC.md",
    "standard_version", ".turngateignore", ".gitignore", "README.md",
    "custom_categories.json",
)


def in_managed_allowlist(rel):
    if rel in MANAGED_FILES:
        return True
    for pre in MANAGED_PREFIXES:
        base = pre.rstrip("/")
        if rel == base or rel.startswith(pre):
            return True
    return False


# --------------------------------------------------------------------------
# D4 (architecture 008): per-feature index/TOC sync for custom features.
# A write under custom/<feature>/ rebuilds ONLY that feature's
# <feature>_index.json + <feature>_TOC.md — never the other features.
# --------------------------------------------------------------------------
CUSTOM_ROOT = "custom"
CUSTOM_CATEGORIES = "custom_categories.json"


def custom_feature_of(rel):
    """'custom/topic_plan/001-x.md' -> 'topic_plan'; else None."""
    parts = rel.replace(os.sep, "/").split("/")
    if len(parts) >= 2 and parts[0] == CUSTOM_ROOT:
        return parts[1]
    return None


def registered_custom_features():
    p = os.path.join(PLAN_ROOT, CUSTOM_CATEGORIES)
    if not os.path.exists(p):
        return []
    try:
        data = json.load(open(p, "r", encoding="utf-8"))
        return [c.get("name") for c in (data.get("categories") or []) if c.get("name")]
    except Exception:
        return []


def sync_custom_feature(name):
    script = os.path.join(SCRIPT_DIR, "append_history.py")
    if not os.path.exists(script):
        return False
    try:
        out = subprocess.run(
            [sys.executable, script, "custom", "sync", "--plan", PLAN_ROOT, "--name", name],
            capture_output=True, text=True, timeout=20)
    except Exception as e:
        print("turn_gate record: custom sync 调用失败：%s" % e, file=sys.stderr)
        return False
    if out.returncode != 0:
        print("turn_gate record: custom sync 失败（%s）：%s"
              % (name, (out.stderr or "").strip()[:200]), file=sys.stderr)
        return False
    return True


def custom_side_files(rel):
    """Declared paths that must also land in history when a custom record changes."""
    feat = custom_feature_of(rel)
    if not feat or feat not in registered_custom_features():
        return []
    return ["%s/%s_index.json" % (CUSTOM_ROOT, feat),
            "%s/%s_TOC.md" % (CUSTOM_ROOT, feat)]


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
    rel = None
    if fp and in_plan(fp):
        rel = norm_rel(fp)
        if is_ignored(rel):
            # D1 (architecture 007): ignored scratch — do not book, do not gate.
            print("turn_gate record: %s ignored by .turngateignore; not booked." % rel)
        elif rel not in state["declared"]:
            state["declared"].append(rel)
            added = True
    # architecture 008 D4: a write under custom/<feature>/ rebuilds ONLY that
    # feature's index+TOC; both must then be covered by this turn's history event.
    if rel is not None:
        feat = custom_feature_of(rel)
        if feat and feat in registered_custom_features():
            if sync_custom_feature(feat):
                for side in custom_side_files(rel):
                    if side not in state["declared"]:
                        state["declared"].append(side)
                        added = True
                print("turn_gate record: 已同步 custom/%s 的 index+TOC（须在本轮 history 事件中留痕）。"
                      % feat)
    if added:
        save_state(state)
        print("turn_gate record: declared += %s (total %d)"
              % (norm_rel(fp) if fp else fp, len(state["declared"])))
        # IMP-001 (architecture 006): mechanically lint managed architecture docs
        # when they are written. Non-blocking warning — the hard gate (history
        # coverage) is still enforced by `end`/`check`.
        if rel.startswith("architecture/") and rel.endswith(".md"):
            _run_structure_lint(fp)
    else:
        print("turn_gate record: no in-plan file to book.")


def _run_structure_lint(path):
    """Run scripts/structure_lint.py on a single architecture md (warning only)."""
    lint = os.path.join(SCRIPT_DIR, "structure_lint.py")
    if not os.path.exists(lint):
        return
    try:
        out = subprocess.run([sys.executable, lint, PLAN_ROOT, "--file", path],
                             capture_output=True, text=True, timeout=20)
    except Exception as e:
        print("turn_gate record: structure_lint 调用失败：%s" % e, file=sys.stderr)
        return
    if out.returncode != 0:
        print("⚠ structure_lint 警告（非阻断）：", file=sys.stderr)
        for line in out.stdout.splitlines():
            print("    " + line, file=sys.stderr)


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

    declared = [d for d in state.get("declared", []) if in_plan(d) and not is_ignored(d)]
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


def cmd_prewrite(args):
    """D2 (architecture 007): PreToolUse hard block.

    Allow the write iff the target is (a) out-of-plan, (b) ignored by
    .turngateignore, or (c) in the managed allowlist. Otherwise block (non-zero
    exit) so scratch never lands in the plan root outside .tmp/ or other ignored
    paths. The soft `end` gate remains the last-ditch fallback.
    """
    fp = args.file
    if fp is None:
        payload = read_stdin_json()
        if payload is not None:
            fp = extract_filepath(payload)
    if fp is None:
        fp = os.environ.get("CODEBUDDY_FILE_PATH")
    # Cannot see a target -> allow (do not block what we cannot reason about).
    if not fp:
        print("turn_gate prewrite: no target file; allow.")
        sys.exit(0)
    if not in_plan(fp):
        print("turn_gate prewrite: out-of-plan; allow.")
        sys.exit(0)
    rel = norm_rel(fp)
    if is_ignored(rel):
        print("turn_gate prewrite: %s ignored by .turngateignore; allow." % rel)
        sys.exit(0)
    if in_managed_allowlist(rel):
        print("turn_gate prewrite: %s is a managed file; allow." % rel)
        sys.exit(0)
    print("turn_gate prewrite: BLOCKED — %s is neither a managed file nor ignored "
          "by .turngateignore. Put scratch under .tmp/ (or another ignored path)."
          % rel, file=sys.stderr)
    sys.exit(1)


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
    pp = sub.add_parser("prewrite")
    pp.add_argument("--file", help="explicit file path (else read hook stdin/env)")

    args = p.parse_args()
    {"begin": cmd_begin, "record": cmd_record, "end": cmd_end,
     "check": cmd_check, "prewrite": cmd_prewrite}[args.cmd](args)


if __name__ == "__main__":
    main()
