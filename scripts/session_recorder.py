#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Session recorder daemon (architecture 009).

Out-of-process observer that is the SOLE writer of session traces (P1).
The agent never writes the trace (P2); hooks push events here via
recorder_feed.py over a Unix domain socket. A watcher thread passively
captures turn_gate side-effects (.turn) and cross-checks coverage, and a
spool queue guarantees no event is lost while the daemon is down (P3).

Subcommands:
  start [--foreground] [--no-watch]   idempotent: exit 0 if already alive
  stop                                SIGTERM -> drain -> flush -> cleanup
  status                              pid/uptime/trace line counts
  doctor                              coverage audit: known plans/sessions,
                                      spool backlog, ".turn state without
                                      trace" gaps (Q46)

Trace line: {"seq", "ts", "kind", "name", "plan_id", "session_id", "payload"}
routed to <trace_root>/<plan_slug>/<session_id>.jsonl (outside any plan root).
"""
import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time

HOME = os.environ.get("RECORDER_HOME") or os.path.expanduser(
    "~/.ai_project_standard")
SOCK = os.environ.get("RECORDER_SOCK") or os.path.join(HOME, "runtime",
                                                       "recorder.sock")
TRACE_ROOT = os.environ.get("RECORDER_TRACE_DIR") or os.path.join(
    HOME, "session_trace")
SPOOL_DIR = os.environ.get("RECORDER_SPOOL_DIR") or os.path.join(HOME, "spool")
RUNTIME_DIR = os.path.dirname(SOCK)
PID_FILE = os.path.join(RUNTIME_DIR, "recorder.pid")
LOG_FILE = os.path.join(RUNTIME_DIR, "recorder.log")
CONFIG_FILE = os.path.join(HOME, "config.json")

WATCH_INTERVAL = 1.0          # seconds (polling fallback; no watchdog dep)
GAP_AFTER = 600               # .turn state older than this w/o trace = gap
HOOK_SOURCE_KINDS = ("prompt", "tool_intent", "tool_call", "turn_end")


def now_iso():
    import datetime
    return datetime.datetime.now().astimezone().isoformat(timespec="milliseconds")


def plan_slug(plan_id):
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in (plan_id or "unknown-plan"))


def _trace_empty(path):
    try:
        return os.path.getsize(path) == 0
    except OSError:
        return True


def _load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def watch_paths():
    env = os.environ.get("RECORDER_WATCH_PATHS")
    if env:
        return [p for p in env.replace(";", ":").split(":") if p]
    return _load_config().get("watch_paths") or []


def transcript_path():
    return os.environ.get("RECORDER_TRANSCRIPT_PATH") or (
        _load_config().get("transcript_path") or None)


# --------------------------------------------------------------------------
# trace writing (sole writer, P1)
# --------------------------------------------------------------------------
_SEQ = {}
_SEQ_LOCK = threading.Lock()


def _count_lines(path):
    n = 0
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 16), b""):
                n += chunk.count(b"\n")
    except FileNotFoundError:
        return 0
    except Exception:
        return 0
    return n


def _trace_path(plan_id, session_id):
    d = os.path.join(TRACE_ROOT, plan_slug(plan_id))
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "%s.jsonl" % (session_id or "unknown-session"))


def append_event(ev):
    """Assign seq + default ts, append one JSON line, return seq."""
    plan_id = ev.get("plan_id") or "unknown-plan"
    session_id = ev.get("session_id") or "unknown-session"
    path = _trace_path(plan_id, session_id)
    key = (plan_slug(plan_id), session_id)
    with _SEQ_LOCK:
        if key not in _SEQ:
            _SEQ[key] = _count_lines(path)
        seq = _SEQ[key] + 1
        _SEQ[key] = seq
    ev.setdefault("ts", now_iso())
    ev["seq"] = seq
    ev["plan_id"] = plan_id
    ev["session_id"] = session_id
    line = json.dumps(ev, ensure_ascii=False)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()
    return seq


def lifecycle(msg, plan_id="unknown-plan", session_id="unknown-session"):
    try:
        append_event({"kind": "lifecycle", "name": "daemon", "payload": {"msg": msg},
                      "plan_id": plan_id, "session_id": session_id})
    except Exception:
        pass


# --------------------------------------------------------------------------
# event routing (incl. P4 companion "hook" event)
# --------------------------------------------------------------------------
def route(ev):
    if not isinstance(ev, dict):
        return
    seq = append_event(ev)
    # P4: every hook-sourced event also yields an explicit "hook" marker so
    # hook firings themselves are first-class entries in the trace.
    if ev.get("kind") in HOOK_SOURCE_KINDS:
        meta = {}
        payload = ev.get("payload")
        if isinstance(payload, dict):
            meta = payload.get("_hook_meta") or {}
        append_event({"kind": "hook", "name": ev.get("name") or ev.get("kind"),
                      "payload": {"hook": ev.get("kind"), "exit": 0,
                                  "ms": meta.get("ms")},
                      "plan_id": ev.get("plan_id"),
                      "session_id": ev.get("session_id")})
    return seq


# --------------------------------------------------------------------------
# spool (P3): drain on startup; bad lines skipped with a lifecycle warning
# --------------------------------------------------------------------------
def spool_drain():
    if not os.path.isdir(SPOOL_DIR):
        return 0, 0
    names = sorted(n for n in os.listdir(SPOOL_DIR) if n.endswith(".jsonl"))
    total, bad = 0, 0
    for name in names:
        path = os.path.join(SPOOL_DIR, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception:
            continue
        ok = 0
        for ln in lines:
            ln = ln.strip()
            if not ln:
                continue
            try:
                ev = json.loads(ln)
            except Exception:
                bad += 1
                continue
            try:
                route(ev)
                ok += 1
            except Exception:
                bad += 1
        if bad == 0 or ok > 0:
            try:
                os.remove(path)
            except OSError:
                pass
        total += ok
    if total or bad:
        lifecycle("spool drained: %d events replayed, %d bad lines skipped"
                  % (total, bad))
    return total, bad


# --------------------------------------------------------------------------
# watcher thread (D3): .turn side-effects + coverage census + transcript tail
# --------------------------------------------------------------------------
class Watcher(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name="watcher")
        self.stop_flag = threading.Event()
        self._turn_seen = {}     # path -> (size, mtime)
        self._gap_reported = set()
        self._transcript_size = None

    def run(self):
        while not self.stop_flag.is_set():
            try:
                self._scan_turn()
                self._scan_transcript()
            except Exception:
                pass
            self.stop_flag.wait(WATCH_INTERVAL)

    # -- .turn: ground truth of "sessions that existed" (turn_gate L45-46) --
    def _scan_turn(self):
        now = time.time()
        for root in watch_paths():
            turn_dir = os.path.join(root, ".codebuddy", "hooks", ".turn")
            if not os.path.isdir(turn_dir):
                continue
            plan_id = os.path.basename(os.path.normpath(root))
            try:
                names = sorted(os.listdir(turn_dir))
            except OSError:
                continue
            for name in names:
                if not name.endswith(".json") or name.endswith(".tmp"):
                    continue
                path = os.path.join(turn_dir, name)
                try:
                    st = os.stat(path)
                except OSError:
                    continue
                sig = (st.st_size, st.st_mtime)
                if self._turn_seen.get(path) == sig:
                    continue
                self._turn_seen[path] = sig
                sid = name[:-len(".json")]
                append_event({"kind": "watcher", "name": "turn_state",
                              "plan_id": plan_id, "session_id": sid,
                              "payload": {"file": path, "size": st.st_size,
                                          "mtime": st.st_mtime}})
                # coverage census: only age-checked to avoid startup races
                if now - st.st_mtime > GAP_AFTER:
                    trace = _trace_path(plan_id, sid)
                    if _trace_empty(trace) and sid not in self._gap_reported:
                        self._gap_reported.add(sid)
                        append_event({"kind": "watcher", "name": "coverage_gap",
                                      "plan_id": plan_id, "session_id": sid,
                                      "payload": {
                                          "reason": "turn state without trace",
                                          "file": path}})

    # -- transcript tail (only when configured; §7-4 decides availability) --
    def _scan_transcript(self):
        tp = transcript_path()
        if not tp or not os.path.isfile(tp):
            return
        size = os.path.getsize(tp)
        if self._transcript_size is None:
            self._transcript_size = size     # start from now, no backfill
            return
        if size <= self._transcript_size:
            return
        try:
            with open(tp, "rb") as f:
                f.seek(self._transcript_size)
                delta = f.read(8192)
        except OSError:
            return
        self._transcript_size = size
        append_event({"kind": "watcher", "name": "transcript_delta",
                      "payload": {"path": tp, "offset": self._transcript_size,
                                  "delta": delta.decode("utf-8", "replace")}})


# --------------------------------------------------------------------------
# daemon core
# --------------------------------------------------------------------------
_STOP = threading.Event()
_SERVER_SOCK = None


def _sig_handler(signum, frame):
    _STOP.set()
    try:
        if _SERVER_SOCK is not None:
            _SERVER_SOCK.close()
    except Exception:
        pass


def _socket_alive():
    """True if a live daemon is listening on SOCK (residue probe, Q45)."""
    if not os.path.exists(SOCK):
        return False
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(0.5)
        s.connect(SOCK)
        s.close()
        return True
    except Exception:
        return False


def _cleanup_socket():
    try:
        if os.path.exists(SOCK):
            os.unlink(SOCK)
    except OSError:
        pass


def _serve():
    global _SERVER_SOCK
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    if _socket_alive():
        return 0  # idempotent start
    _cleanup_socket()
    spool_drain()
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(SOCK)
    srv.listen(16)
    srv.settimeout(0.5)
    _SERVER_SOCK = srv
    signal.signal(signal.SIGTERM, _sig_handler)
    signal.signal(signal.SIGINT, _sig_handler)
    with open(PID_FILE, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    lifecycle("daemon started pid=%d sock=%s" % (os.getpid(), SOCK))
    watcher = None
    if "--no-watch" not in sys.argv:
        watcher = Watcher()
        watcher.start()
    try:
        while not _STOP.is_set():
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            conn.settimeout(2.0)
            buf = b""
            try:
                while True:
                    try:
                        chunk = conn.recv(65536)
                    except socket.timeout:
                        break
                    if not chunk:
                        break
                    buf += chunk
                    if len(buf) > (1 << 22):
                        break
            except OSError:
                pass
            finally:
                try:
                    conn.close()
                except OSError:
                    pass
            for ln in buf.split(b"\n"):
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    route(json.loads(ln.decode("utf-8")))
                except Exception:
                    pass
    finally:
        lifecycle("daemon stopped pid=%d" % os.getpid())
        try:
            srv.close()
        except OSError:
            pass
        _cleanup_socket()
        try:
            os.remove(PID_FILE)
        except OSError:
            pass
    return 0


def _daemonize():
    if os.fork() > 0:
        time.sleep(0.2)  # let the child bind before the parent exits
        return 0
    os.setsid()
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.close()
        except Exception:
            pass
    sys.stdin = open(os.devnull, "rb")
    log = open(LOG_FILE, "ab", buffering=0)
    sys.stdout = log
    sys.stderr = log
    return _serve()


def _read_pid():
    try:
        with open(PID_FILE, "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except Exception:
        return None


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def cmd_start(args):
    if _socket_alive():
        print("session_recorder: already running (sock=%s)" % SOCK)
        return 0
    if args.foreground:
        return _serve()
    return _daemonize()


def cmd_stop(args):
    pid = _read_pid()
    if pid is None or not _pid_alive(pid):
        print("session_recorder: not running (cleaning stale socket)")
        _cleanup_socket()
        return 0
    os.kill(pid, signal.SIGTERM)
    for _ in range(50):
        if not _pid_alive(pid):
            break
        time.sleep(0.1)
    print("session_recorder: stopped (pid=%s)" % pid)
    return 0


def _trace_stats():
    rows = []
    if not os.path.isdir(TRACE_ROOT):
        return rows
    for plan in sorted(os.listdir(TRACE_ROOT)):
        pdir = os.path.join(TRACE_ROOT, plan)
        if not os.path.isdir(pdir):
            continue
        for name in sorted(os.listdir(pdir)):
            if not name.endswith(".jsonl"):
                continue
            path = os.path.join(pdir, name)
            rows.append((plan, name[:-len(".jsonl")], _count_lines(path),
                         os.path.getsize(path)))
    return rows


def cmd_status(args):
    pid = _read_pid()
    alive = pid is not None and _pid_alive(pid) and _socket_alive()
    print("daemon: %s (pid=%s, sock=%s)" %
          ("running" if alive else "not running", pid, SOCK))
    if not alive:
        return 0
    total = 0
    for plan, sid, n, size in _trace_stats():
        print("  trace %s/%s: %d lines (%d bytes)" % (plan, sid, n, size))
        total += n
    print("  total events: %d" % total)
    return 0


def cmd_doctor(args):
    """Coverage audit (Q46 mechanism 4): gaps are machine-checkable."""
    print("== session recorder doctor ==")
    spool_files = 0
    spool_lines = 0
    if os.path.isdir(SPOOL_DIR):
        for n in os.listdir(SPOOL_DIR):
            if n.endswith(".jsonl"):
                spool_files += 1
                spool_lines += _count_lines(os.path.join(SPOOL_DIR, n))
    print("spool backlog: %d files / %d events" % (spool_files, spool_lines))
    print("-- known traces --")
    for plan, sid, n, size in _trace_stats():
        print("  %s/%s: %d lines" % (plan, sid, n))
    gaps = []
    print("-- coverage census (.turn vs trace) --")
    for root in watch_paths():
        turn_dir = os.path.join(root, ".codebuddy", "hooks", ".turn")
        plan_id = os.path.basename(os.path.normpath(root))
        if not os.path.isdir(turn_dir):
            continue
        for name in sorted(os.listdir(turn_dir)):
            if not name.endswith(".json") or name.endswith(".tmp"):
                continue
            sid = name[:-len(".json")]
            trace = _trace_path(plan_id, sid)
            if _trace_empty(trace):
                gaps.append((plan_id, sid, os.path.join(turn_dir, name)))
    if gaps:
        for plan_id, sid, state in gaps:
            print("  GAP: %s session %s has .turn state but no trace (%s)"
                  % (plan_id, sid, state))
        print("result: %d gap(s) found" % len(gaps))
        return 1
    print("  no gaps")
    print("result: OK")
    return 0


def main():
    p = argparse.ArgumentParser(description="session recorder daemon (arch 009)")
    sub = p.add_subparsers(dest="cmd", required=True)
    ps = sub.add_parser("start")
    ps.add_argument("--foreground", action="store_true")
    ps.add_argument("--no-watch", action="store_true")
    sub.add_parser("stop")
    sub.add_parser("status")
    sub.add_parser("doctor")
    args = p.parse_args()
    os.makedirs(TRACE_ROOT, exist_ok=True)
    os.makedirs(SPOOL_DIR, exist_ok=True)
    {"start": cmd_start, "stop": cmd_stop, "status": cmd_status,
     "doctor": cmd_doctor}[args.cmd](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
