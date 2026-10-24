#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Session recorder feeder (architecture 009).

External command run by the IDE as a hook (NOT an agent tool call). Reads the
hook payload from stdin (or --text), ships one JSON event line to the daemon
socket. Failure chain (P3, Q45): fallback-launch the daemon once, then spool,
then SILENT exit 0 — a broken recorder must never disturb the session.

Identity mirrors turn_gate.py: plan root from CODEBUDDY_PROJECT_DIR, session
from CODEBUDDY_SESSION_ID / CODEBUDDY_CONVERSATION_ID.
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import time

HOME = os.environ.get("RECORDER_HOME") or os.path.expanduser(
    "~/.ai_project_standard")
SOCK = os.environ.get("RECORDER_SOCK") or os.path.join(HOME, "runtime",
                                                       "recorder.sock")
SPOOL_DIR = os.environ.get("RECORDER_SPOOL_DIR") or os.path.join(HOME, "spool")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DAEMON = os.path.join(SCRIPT_DIR, "session_recorder.py")


def now_iso():
    import datetime
    return datetime.datetime.now().astimezone().isoformat(timespec="milliseconds")


def session_id():
    return (os.environ.get("CODEBUDDY_SESSION_ID")
            or os.environ.get("CODEBUDDY_CONVERSATION_ID")
            or ("local-%d" % os.getpid()))


def plan_id():
    root = os.environ.get("CODEBUDDY_PROJECT_DIR") or os.getcwd()
    return os.path.basename(os.path.normpath(root)) or "unknown-plan"


def build_event(kind, name, text):
    payload = None
    if text is not None:
        payload = text
    elif not sys.stdin.isatty():
        raw = sys.stdin.read()
        if raw.strip():
            try:
                payload = json.loads(raw)
            except Exception:
                payload = raw
    if payload is None:
        payload = {}
    ev = {"kind": kind, "ts": now_iso(), "plan_id": plan_id(),
          "session_id": session_id(), "payload": payload}
    if name:
        ev["name"] = name
    else:
        tool = payload.get("tool_name") or payload.get("tool") if isinstance(payload, dict) else None
        if tool:
            ev["name"] = tool
    return ev


def send(line, timeout_s):
    start = time.time()
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout_s)
    s.connect(SOCK)
    s.sendall(line.encode("utf-8"))
    s.close()
    return (time.time() - start) * 1000.0


def spool(line):
    os.makedirs(SPOOL_DIR, exist_ok=True)
    path = os.path.join(SPOOL_DIR, "%d-%d.jsonl" % (int(time.time() * 1000),
                                                    os.getpid()))
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def fallback_launch():
    try:
        subprocess.Popen(
            [sys.executable, DAEMON, "start", "--no-watch"],
            start_new_session=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL)
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser(description="session recorder feeder (arch 009)")
    ap.add_argument("--kind", required=True,
                    choices=["prompt", "tool_intent", "tool_call", "turn_end",
                             "reasoning", "answer", "hook", "watcher",
                             "lifecycle"])
    ap.add_argument("--name", default=None)
    ap.add_argument("--text", default=None)
    ap.add_argument("--timeout-ms", type=int, default=200)
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 on delivery failure (debug only)")
    args = ap.parse_args()

    ev = build_event(args.kind, args.name, args.text)
    line = json.dumps(ev, ensure_ascii=False)
    timeout_s = max(args.timeout_ms, 50) / 1000.0
    delivered, ms = False, None
    try:
        ms = send(line, timeout_s)
        delivered = True
    except Exception:
        # Q45 fallback: launch the daemon once, then retry, then spool (P3).
        fallback_launch()
        time.sleep(0.3)
        try:
            ms = send(line, timeout_s + 0.3)
            delivered = True
        except Exception:
            try:
                spool(line)
            except Exception:
                pass
    if not delivered and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)  # P3: never disturb the session
