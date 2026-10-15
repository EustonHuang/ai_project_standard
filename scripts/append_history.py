#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Append-only plan history logger (FOLDER form) — plan_003 / architecture 003.

Layout (per plan folder DIR)
----------------------------
  DIR/history/{zeroed_id}.json          one file per event
  DIR/questions/{zeroed_id}.md          one file per Q&A
  DIR/issues/{zeroed_id}/description.json + assets/
  DIR/architecture/{zeroed_ver}.md      one file per architecture version
  DIR/{category}_index.json             indexes at ROOT (siblings of category folders)
  DIR/{category}_TOC.md                 human-readable TOCs, auto-generated (4 kinds)
  DIR/.lock                             commit lock (PID + TTL), runtime only

Changes from architecture 002 (this rewrite)
---------------------------------------------
* No more `*_meta.json`: plan-level fields (plan_id/plan_title/created_at) live in
  `architecture_index.json`; non-structured notes live in each `*_index.json.notes`.
* Four auto-generated TOCs (`*_TOC.md`) via `gen-toc`; `append`/`rebuild-index`/
  `set-implemented` refresh the relevant TOC automatically.
* `show` prints only the last N briefs (`--last N`, default 50; `--last 0` = all).
* `EVENT_SCHEMA_VERSION` is now "2.0" (the "no timestamp" shape, frozen at v1.0, is
  bumped per the schema_version bump policy in references/history_schema.md).
* On `append`, `source.model` is taken from a PLATFORM-TRUSTED signal (env
  `CODEBUDDY_MODEL`); if absent it is set to "unknown" with `model_confidence=
  "unknown"` and a comment — the agent is forbidden from self-reporting "Hy3".

Usage
-----
  python append_history.py init          --plan DIR [--meta plan_id title]
  python append_history.py append        --plan DIR --event E.json [--kind history] \
                                         [--model <platform model, optional>]
  python append_history.py append        --plan DIR --kind questions --body Q.md \
                                         --question-ref Q11 --question "..." [--answer-summary "..."]
  python append_history.py append        --plan DIR --kind issue --description D.json [--assets-dir DIR]
  python append_history.py show          --plan DIR [--kind history] [--last 50]
  python append_history.py audit         --plan DIR
  python append_history.py rebuild-index --plan DIR [--kind history|questions|issues]
  python append_history.py gen-toc       --plan DIR [--kind all|history|questions|issues|architecture]
  python append_history.py migrate       --plan DIR
  python append_history.py recover       --plan DIR --issue 001
  python append_history.py set-implemented --plan DIR --version 3
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

EVENT_SCHEMA_VERSION = "2.0"
LOCK_NAME = ".lock"
DEFAULT_TTL = 30.0
DEFAULT_RETRIES = 12
DEFAULT_DELAY = 0.5
TOC_MAX_ENTRIES = 200

CATEGORY_DIR = {
    "history": "history",
    "questions": "questions",
    "issues": "issues",
    "architecture": "architecture",
    "improvement": "improvements",
}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat()


def sha256_file(path):
    if not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def zeroed(n, width=3):
    return str(int(n)).zfill(max(width, len(str(int(n)))))


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def index_hash(path):
    if not os.path.exists(path):
        return sha256_bytes(b"")
    with open(path, "rb") as f:
        return sha256_bytes(f.read())


def cat_dir(plan, kind):
    return os.path.join(plan, CATEGORY_DIR[kind])


def index_path(plan, kind):
    return os.path.join(plan, "%s_index.json" % kind)


def empty_index(kind):
    if kind == "architecture":
        return {"implemented_version": 0, "latest_version": 0, "revision": 0, "versions": []}
    return {"max_id": 0, "revision": 0, "briefs": []}


# --------------------------------------------------------------------------
# custom features (architecture 008)
#
# The framework ships NO predefined custom feature. A project registers the ones
# it needs into `custom_categories.json` (via the `register-custom-feature`
# skill / `append_history.py custom register`). That declaration list is the
# single source of truth for: which `custom/<feature>/` folders are managed,
# which index+TOC pairs exist, what `audit` checks and what the gate allows.
# --------------------------------------------------------------------------
CUSTOM_ROOT = "custom"
CUSTOM_CATEGORIES = "custom_categories.json"
# A record file MUST start with a zero-padded number; everything after it is the
# project's own business (separator + topic naming are NOT dictated).
CUSTOM_RECORD_RE = re.compile(r"^(\d+)[^/]*\.md$")


def custom_root(plan):
    return os.path.join(plan, CUSTOM_ROOT)


def custom_categories_path(plan):
    return os.path.join(plan, CUSTOM_CATEGORIES)


def custom_dir(plan, name):
    return os.path.join(custom_root(plan), name)


def custom_index_path(plan, name):
    return os.path.join(custom_root(plan), "%s_index.json" % name)


def custom_toc_path(plan, name):
    return os.path.join(custom_root(plan), "%s_TOC.md" % name)


def load_categories(plan):
    """Registered custom feature names (empty when the file is absent)."""
    data = load_json(custom_categories_path(plan))
    if not isinstance(data, dict):
        return []
    return [c.get("name") for c in (data.get("categories") or []) if c.get("name")]


def custom_records(plan, name):
    """Record files of ONE feature → [(num, rel_path, topic)], sorted by num.

    Only top-level `*.md` files that start with a number are records. A
    same-named directory (`001-spark-helloworld/`) holds auxiliary markdowns and
    is NOT a record — it is scanned by `custom_aux_files()` instead.
    """
    d = custom_dir(plan, name)
    out = []
    if not os.path.isdir(d):
        return out
    for fn in os.listdir(d):
        if not os.path.isfile(os.path.join(d, fn)):
            continue
        m = CUSTOM_RECORD_RE.match(fn)
        if not m:
            continue
        num = int(m.group(1))
        topic = fn[len(m.group(1)):].lstrip("-_ ")
        if topic.endswith(".md"):
            topic = topic[:-3]
        out.append((num, "%s/%s/%s" % (CUSTOM_ROOT, name, fn), topic))
    return sorted(out, key=lambda x: x[0])


def custom_aux_files(plan, name):
    """{record_num: [aux rel paths]} — auxiliary markdowns living in the
    same-named directory next to a record (`001-x.md` ↔ `001-x/*.md`)."""
    d = custom_dir(plan, name)
    out = {}
    if not os.path.isdir(d):
        return out
    for fn in sorted(os.listdir(d)):
        p = os.path.join(d, fn)
        if not os.path.isdir(p):
            continue
        m = CUSTOM_RECORD_RE.match(fn + ".md")
        if not m:
            continue
        num = int(m.group(1))
        aux = sorted("%s/%s/%s/%s" % (CUSTOM_ROOT, name, fn, x)
                     for x in os.listdir(p) if x.endswith(".md"))
        if aux:
            out[num] = aux
    return out


def _regen_custom_toc(plan, name, briefs=None):
    if briefs is None:
        briefs = (load_json(custom_index_path(plan, name)) or {}).get("briefs", [])
    lines = ["<!-- 自动生成，请勿手改；改动会被脚本覆盖 -->", "",
             "# %s — TOC" % name, "",
             "> 由 `append_history.py custom sync` 自动生成；记录正文见 `%s/%s/`。"
             % (CUSTOM_ROOT, name), ""]
    for b in sorted(briefs, key=lambda x: x.get("num", 0)):
        lines.append("- [%s · %s](%s)"
                     % (zeroed(b.get("num", 0)), b.get("topic", ""), b.get("file", "")))
    os.makedirs(custom_root(plan), exist_ok=True)
    with open(custom_toc_path(plan, name), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def sync_custom_feature(plan, name):
    """Rebuild ONLY this feature's index + TOC from disk (no other feature is touched).

    architecture 008 D3: a record is just a numbered md file (+ optional same-named
    aux dir). No frontmatter, no version fields — ordering is the filename number,
    so the index/TOC need only carry num / topic / aux_files / file.
    """
    os.makedirs(custom_dir(plan, name), exist_ok=True)
    recs = custom_records(plan, name)
    aux = custom_aux_files(plan, name)
    briefs = []
    for num, rel, topic in recs:
        briefs.append({
            "num": num,
            "topic": topic,
            "aux_files": aux.get(num, []),
            "file": rel,
        })
    idx = load_json(custom_index_path(plan, name)) or {}
    idx["feature"] = name
    idx["max_id"] = max([b["num"] for b in briefs], default=0)
    idx["revision"] = int(idx.get("revision", 0)) + 1
    idx["briefs"] = briefs
    write_json(custom_index_path(plan, name), idx)
    _regen_custom_toc(plan, name, briefs)
    return len(briefs), "%s/%s_index.json" % (CUSTOM_ROOT, name), "%s/%s_TOC.md" % (CUSTOM_ROOT, name)


def latest_architecture_md(plan):
    d = cat_dir(plan, "architecture")
    if not os.path.isdir(d):
        return None, None
    best, best_ver = None, -1
    for name in os.listdir(d):
        m = re.match(r"^(\d+)\.md$", name)
        if not m:
            continue
        ver = int(m.group(1))
        if ver > best_ver:
            best, best_ver = os.path.join(d, name), ver
    return best, (best_ver if best_ver >= 0 else None)


def attach_snapshot(event, plan):
    """Attach a snapshot of the latest architecture doc (replaces old hard-coded plan.md)."""
    if "plan_state_snapshot" in event:
        return
    path, ver = latest_architecture_md(plan)
    if not path:
        return
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    event["plan_state_snapshot"] = {
        "plan_md_sha256": sha256_file(path),
        "plan_md_line_count": text.count("\n") + 1 if text else 0,
        "source_doc": "architecture/%s.md" % zeroed(ver) if ver else "architecture/<latest>.md",
    }


def read_standard_version(plan):
    """IMP-003 (architecture 006): read the framework version from the project's
    `standard_version` lock file (the `standard_version=<ver>` line). Returns the
    version string (e.g. "v0.5") or "unknown" if not parseable. This is a snapshot
    of the version the event was produced under; it never changes on later upgrades.
    """
    p = os.path.join(plan, "standard_version")
    if not os.path.exists(p):
        return "unknown"
    try:
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("standard_version="):
                    val = line.split("=", 1)[1].strip()
                    return val or "unknown"
    except Exception:
        pass
    return "unknown"


def resolve_source_model(event, model_override=None):
    """Q18: prefer a PLATFORM-TRUSTED model signal; never let the agent self-report 'Hy3'.

    Priority: env CODEBUDDY_MODEL  >  --model arg  >  unknown (forbidden self-report).
    """
    src = event.get("source") or {}
    platform = os.environ.get("CODEBUDDY_MODEL") or os.environ.get("CODEBUDDY_MODEL_NAME")
    if platform:
        src["model"] = platform
        src["model_confidence"] = "confirmed"
    elif model_override:
        src["model"] = model_override
        src["model_confidence"] = "inferred"
    else:
        # No platform signal: do NOT trust an agent self-report ("Hy3").
        if src.get("model") in (None, "", "Hy3"):
            src["model"] = "unknown"
            src["model_confidence"] = "unknown"
            note = ("source.model 取自平台可信信号失败（env CODEBUDDY_MODEL 缺失且未提供 --model），"
                    "按 Q18 置 'unknown'；禁止 agent 自报 'Hy3'。")
            event["comments"] = ((event.get("comments") or "") + " " + note).strip()
        elif src.get("model_confidence") not in ("confirmed", "inferred", "unknown"):
            src["model_confidence"] = "inferred"
    event["source"] = src
    return event


# --------------------------------------------------------------------------
# TOC generation (4 kinds, auto-generated, truncated to last N)
# --------------------------------------------------------------------------
def _regen_toc(plan, kind, max_entries=TOC_MAX_ENTRIES):
    if kind == "architecture":
        idx = load_json(index_path(plan, "architecture")) or {}
        lines = ["<!-- 自动生成，请勿手改；改动会被脚本覆盖 -->", "",
                 "# Architecture — TOC", "",
                 "> 由 `append_history.py gen-toc` 自动生成；每版本正文见 `architecture/{ver}.md`。", ""]
        vers = sorted(idx.get("versions", []), key=lambda x: x.get("version", 0), reverse=True)
        if len(vers) > max_entries:
            vers = vers[:max_entries]
            lines.append("> 仅显示最近 %d 个版本；更早版本见 `architecture_index.json`。" % max_entries)
        for v in sorted(vers, key=lambda x: x.get("version", 0)):
            ver = v.get("version", 0)
            if ver == idx.get("implemented_version"):
                status = "已落地"
            elif ver == idx.get("latest_version"):
                status = "待执行（已定义未落地）"
            else:
                status = "历史"
            lines.append("- [v%s · %s](%s) — 状态：%s"
                         % (zeroed(ver), v.get("title", ""), v.get("file", ""), status))
        out = os.path.join(plan, "architecture_TOC.md")

    elif kind == "history":
        idx = load_json(index_path(plan, "history")) or {}
        lines = ["<!-- 自动生成，请勿手改；改动会被脚本覆盖 -->", "",
                 "# History — TOC", "",
                 "> 由 `append_history.py gen-toc` 自动生成；每事件正文见 `history/{id}.json`。", ""]
        briefs = sorted(idx.get("briefs", []), key=lambda x: x.get("event_id", 0), reverse=True)
        truncated = len(briefs) > max_entries
        briefs = briefs[:max_entries]
        for b in reversed(briefs):
            lines.append("- [%s · %s · %s](%s) — %s"
                         % (zeroed(b.get("event_id", 0)), b.get("event_type", ""),
                            (b.get("recorded_at") or "")[:19], b.get("file", ""),
                            (b.get("change_summary") or "")[:140]))
        if truncated:
            lines.append("")
            lines.append("> 仅显示最近 %d 条；更早记录见 `history/%s.json` 或 `history_index.json`。"
                         % (max_entries, zeroed(idx.get("max_id", 0))))
        out = os.path.join(plan, "history_TOC.md")

    elif kind == "questions":
        idx = load_json(index_path(plan, "questions")) or {}
        lines = ["<!-- 自动生成，请勿手改；改动会被脚本覆盖 -->", "",
                 "# Questions — TOC", "",
                 "> 由 `append_history.py gen-toc` 自动生成；每问答正文见 `questions/{num}.md`。", ""]
        briefs = sorted(idx.get("briefs", []), key=lambda x: x.get("num", 0), reverse=True)
        truncated = len(briefs) > max_entries
        briefs = briefs[:max_entries]
        for b in reversed(briefs):
            q = (b.get("question") or "").strip().replace("\n", " ")
            if len(q) > 140:
                q = q[:140] + "…"
            lines.append("- [%s](%s) — %s" % (b.get("question_ref", ""), b.get("file", ""), q or "(无摘要)"))
        if truncated:
            lines.append("")
            lines.append("> 仅显示最近 %d 条；更早问答见 `questions/%s.md` 或 `questions_index.json`。"
                         % (max_entries, zeroed(idx.get("max_id", 0))))
        out = os.path.join(plan, "questions_TOC.md")

    elif kind == "issues":
        idx = load_json(index_path(plan, "issues")) or {}
        lines = ["<!-- 自动生成，请勿手改；改动会被脚本覆盖 -->", "",
                 "# Issues — TOC", "",
                 "> 由 `append_history.py gen-toc` 自动生成；每故障正文见 `issues/{id}/description.json`。", ""]
        briefs = sorted(idx.get("briefs", []), key=lambda x: x.get("issue_id", 0), reverse=True)
        truncated = len(briefs) > max_entries
        briefs = briefs[:max_entries]
        for b in reversed(briefs):
            lines.append("- [%s · %s · %s](%s) — %s"
                         % (zeroed(b.get("issue_id", 0)), b.get("event_type", ""),
                            b.get("status", ""), b.get("file", ""),
                            ((b.get("description") or "")[:140])))
        if truncated:
            lines.append("")
            lines.append("> 仅显示最近 %d 条；更早故障见 `issues/%s/description.json` 或 `issues_index.json`。"
                         % (max_entries, zeroed(idx.get("max_id", 0))))
        out = os.path.join(plan, "issues_TOC.md")
    elif kind == "improvement":
        idx = load_json(index_path(plan, "improvement")) or {}
        lines = ["<!-- 自动生成，请勿手改；改动会被脚本覆盖 -->", "",
                 "# Improvements — TOC", "",
                 "> 由 `append_history.py gen-toc` 自动生成；每条改进正文见 `improvements/{id}.md`。", ""]
        status_map = {1: "Drafting", 2: "Recorded In Architect", 3: "Implemented"}
        briefs = sorted(idx.get("briefs", []), key=lambda x: x.get("id", 0), reverse=True)
        truncated = len(briefs) > max_entries
        briefs = briefs[:max_entries]
        for b in reversed(briefs):
            st = status_map.get(int(b.get("status", 1)), "Drafting")
            pr = b.get("priority", 3)
            arch = b.get("in_architecture")
            flag = (" → %s" % arch) if arch else ""
            lines.append("- [%s · P%d · %s](%s) — %s%s"
                         % (zeroed(b.get("id", 0), 3), pr, st, b.get("file", ""),
                            (b.get("title") or "")[:120], flag))
        if truncated:
            lines.append("")
            lines.append("> 仅显示最近 %d 条；更早改进见 `improvements/%s.md` 或 `improvement_index.json`。"
                         % (max_entries, zeroed(idx.get("max_id", 0))))
        out = os.path.join(plan, "improvement_TOC.md")
    else:
        return
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# --------------------------------------------------------------------------
# lock
# --------------------------------------------------------------------------
def acquire_lock(plan, ttl=DEFAULT_TTL, retries=DEFAULT_RETRIES, delay=DEFAULT_DELAY):
    lock_path = os.path.join(plan, LOCK_NAME)
    for _ in range(retries):
        try:
            os.mkdir(lock_path)
            write_json(os.path.join(lock_path, "lock.json"),
                       {"pid": os.getpid(), "acquired_at": time.time(), "ttl": ttl})
            return lock_path
        except FileExistsError:
            info_path = os.path.join(lock_path, "lock.json")
            stale = True
            info = load_json(info_path)
            if isinstance(info, dict):
                try:
                    if int(info.get("pid", -1)) == os.getpid():
                        return lock_path  # re-entrant: this process already holds the lock
                except Exception:
                    pass
                try:
                    age = time.time() - float(info.get("acquired_at", 0))
                    stale = age > float(info.get("ttl", ttl))
                except Exception:
                    stale = True
            if stale:
                try:
                    shutil.rmtree(lock_path)
                    continue
                except Exception:
                    pass
            time.sleep(delay)
    return None


def verify_lock(lock_path, pid):
    info = load_json(os.path.join(lock_path, "lock.json"))
    if not isinstance(info, dict):
        return False
    try:
        return int(info.get("pid", -1)) == int(pid)
    except Exception:
        return False


def release_lock(lock_path):
    try:
        shutil.rmtree(lock_path)
    except Exception:
        pass


# --------------------------------------------------------------------------
# issues (failure fallback)
# --------------------------------------------------------------------------
def allocate_issue_dir(plan):
    d = cat_dir(plan, "issues")
    os.makedirs(d, exist_ok=True)
    n = 1
    for name in os.listdir(d):
        m = re.match(r"^(\d+)$", name)
        if m:
            n = max(n, int(m.group(1)) + 1)
    while True:
        target = os.path.join(d, zeroed(n))
        try:
            os.makedirs(target)
            return target, n
        except FileExistsError:
            n += 1


def raise_issue(plan, issue_type, description, intended=None, intended_name=None,
                existing=None, existing_name=None, extra=None):
    """Record an anomaly; never lose the intended content."""
    issue_dir, num = allocate_issue_dir(plan)
    assets = os.path.join(issue_dir, "assets")
    os.makedirs(assets, exist_ok=True)

    assets_refs = []
    if intended is not None:
        name = intended_name or "intended.json"
        path = os.path.join(assets, name)
        if isinstance(intended, (dict, list)):
            write_json(path, intended)
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(str(intended))
        assets_refs.append(name)
    if existing is not None:
        name = existing_name or "existing.json"
        path = os.path.join(assets, name)
        if isinstance(existing, (dict, list)):
            write_json(path, existing)
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(str(existing))
        assets_refs.append(name)

    idx = load_json(index_path(plan, "history"))
    if idx is not None:
        write_json(os.path.join(assets, "index_snapshot.json"), idx)
        assets_refs.append("index_snapshot.json")

    desc = {
        "issue_id": num,
        "event_type": issue_type,
        "description": description,
        "detected_at": now_iso(),
        "intended_action": extra or {},
        "assets_refs": assets_refs,
        "status": "open",
    }
    write_json(os.path.join(issue_dir, "description.json"), desc)

    lock = acquire_lock(plan, retries=3, delay=0.2)
    updated = False
    if lock:
        try:
            iidx = load_json(index_path(plan, "issues")) or empty_index("issues")
            iidx["briefs"] = [b for b in iidx.get("briefs", []) if b.get("issue_id") != num]
            iidx["briefs"].append({
                "issue_id": num, "event_type": issue_type,
                "detected_at": desc["detected_at"], "status": "open",
                "file": "issues/%s/description.json" % zeroed(num),
            })
            iidx["max_id"] = max(int(iidx.get("max_id", 0)), num)
            iidx["revision"] = int(iidx.get("revision", 0)) + 1
            if not os.path.exists(index_path(plan, "issues")):
                write_json(index_path(plan, "issues"), empty_index("issues"))
            write_json(index_path(plan, "issues"), iidx)
            _regen_toc(plan, "issues")
            updated = True
        finally:
            release_lock(lock)
    if not updated:
        d2 = load_json(os.path.join(issue_dir, "description.json"))
        d2["comments"] = "issues_index.json 未能更新（锁不可用）；请用 audit + rebuild-index 修复。"
        write_json(os.path.join(issue_dir, "description.json"), d2)

    print("ISSUE #%s (%s) recorded at %s" % (num, issue_type, os.path.relpath(issue_dir, plan)))
    return num


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------
def cmd_init(args):
    plan = os.path.abspath(args.plan)
    os.makedirs(plan, exist_ok=True)
    for kind in ("history", "questions", "issues", "architecture", "improvement"):
        os.makedirs(cat_dir(plan, kind), exist_ok=True)
        ip = index_path(plan, kind)
        if not os.path.exists(ip):
            write_json(ip, empty_index(kind))
    if args.meta:
        a_idx = load_json(index_path(plan, "architecture")) or empty_index("architecture")
        a_idx["plan_id"] = args.meta[0]
        a_idx["plan_title"] = args.meta[1] if len(args.meta) > 1 else ""
        a_idx["created_at"] = now_iso()
        write_json(index_path(plan, "architecture"), a_idx)
    for k in ("history", "questions", "issues", "architecture", "improvement"):
        _regen_toc(plan, k)
    print("Initialized folder-form plan history at %s" % plan)


def cmd_append_history(args, plan, event):
    idx_file = index_path(plan, "history")
    if not os.path.exists(idx_file):
        sys.exit("ERROR: %s not found. Run 'init' or 'migrate' first." % idx_file)
    idx, base_hash = load_json(idx_file), index_hash(idx_file)
    next_id = int(idx.get("max_id", 0)) + 1
    target = os.path.join(cat_dir(plan, "history"), "%s.json" % zeroed(next_id))
    os.makedirs(os.path.dirname(target), exist_ok=True)

    event.setdefault("schema_version", EVENT_SCHEMA_VERSION)
    event["event_id"] = next_id
    event.setdefault("recorded_at", now_iso())
    resolve_source_model(event, getattr(args, "model", None))
    # IMP-003 (architecture 006): snapshot the framework version this event was
    # produced under. Auto-injected; never hand-filled.
    event["standard_version"] = read_standard_version(plan)
    attach_snapshot(event, plan)

    lock = acquire_lock(plan, ttl=args.ttl, retries=args.retries)
    if not lock:
        raise_issue(plan, "lock-timeout",
                    "获取提交锁超时（重试 %s 次仍未获得），本次 append 未执行。" % args.retries,
                    intended=event, intended_name="intended_%s.json" % zeroed(next_id),
                    extra={"target": os.path.relpath(target, plan), "event_id": next_id})
        sys.exit(1)
    try:
        cur_idx, cur_hash = load_json(idx_file), index_hash(idx_file)
        if cur_hash != base_hash:
            raise_issue(plan, "stale-read",
                        "提交前发现索引已被他人修改（索引哈希与本次读取时不一致），本次 append 中止。",
                        intended=event, intended_name="intended_%s.json" % zeroed(next_id),
                        existing=cur_idx, existing_name="index_now.json",
                        extra={"target": os.path.relpath(target, plan), "event_id": next_id})
            sys.exit(1)
        if os.path.exists(target):
            raise_issue(plan, "collision",
                        "目标文件已存在（索引 max_id 与实际文件不一致），本次 append 中止。",
                        intended=event, intended_name="intended_%s.json" % zeroed(next_id),
                        existing=load_json(target),
                        existing_name="existing_%s.json" % zeroed(next_id),
                        extra={"target": os.path.relpath(target, plan), "event_id": next_id})
            sys.exit(1)
        if not verify_lock(lock, os.getpid()):
            raise_issue(plan, "lock-revoked",
                        "提交前发现持锁已被抢占（锁过期被他人接管），本次 append 中止以防误写。",
                        intended=event, intended_name="intended_%s.json" % zeroed(next_id),
                        extra={"target": os.path.relpath(target, plan), "event_id": next_id})
            sys.exit(1)

        write_json(target, event)
        cur_idx["briefs"] = [b for b in cur_idx.get("briefs", []) if b.get("event_id") != next_id]
        cur_idx["briefs"].append({
            "event_id": next_id,
            "event_type": event.get("event_type"),
            "recorded_at": event.get("recorded_at"),
            "actor_type": (event.get("actor") or {}).get("type"),
            "change_summary": (event.get("operation") or {}).get("change_summary", ""),
            "is_correction": event.get("event_type") == "correction",
            "corrects_event_id": (event.get("correction") or {}).get("corrects_event_id"),
            "standard_version": event.get("standard_version"),
            "file": "history/%s.json" % zeroed(next_id),
        })
        cur_idx["max_id"] = next_id
        cur_idx["revision"] = int(cur_idx.get("revision", 0)) + 1
        write_json(idx_file, cur_idx)
        _regen_toc(plan, "history")
        print("Appended history/%s.json (event_id=%s, %s, schema=%s)"
              % (zeroed(next_id), next_id, event.get("event_type"), event.get("schema_version")))
    finally:
        release_lock(lock)


def cmd_append_questions(args, plan):
    idx_file = index_path(plan, "questions")
    idx = load_json(idx_file) or empty_index("questions")
    next_id = int(idx.get("max_id", 0)) + 1
    target = os.path.join(cat_dir(plan, "questions"), "%s.md" % zeroed(next_id))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(args.body, "r", encoding="utf-8") as f:
        body = f.read()
    if os.path.exists(target):
        raise_issue(plan, "collision", "问答目标文件已存在。", intended=body,
                    intended_name="intended_%s.md" % zeroed(next_id),
                    existing=open(target).read(), existing_name="existing_%s.md" % zeroed(next_id))
        sys.exit(1)
    with open(target, "w", encoding="utf-8") as f:
        f.write(body)
    idx["briefs"] = [b for b in idx.get("briefs", []) if b.get("num") != next_id]
    idx["briefs"].append({
        "num": next_id,
        "question_ref": args.question_ref or ("Q%d" % next_id),
        "question": args.question or "",
        "answer_summary": args.answer_summary or "",
        "file": "questions/%s.md" % zeroed(next_id),
    })
    idx["max_id"] = next_id
    idx["revision"] = int(idx.get("revision", 0)) + 1
    write_json(idx_file, idx)
    _regen_toc(plan, "questions")
    print("Appended questions/%s.md (%s)" % (zeroed(next_id), args.question_ref or next_id))


def cmd_append_improvement(args, plan):
    idx_file = index_path(plan, "improvement")
    idx = load_json(idx_file) or empty_index("improvement")
    next_id = int(idx.get("max_id", 0)) + 1
    target = os.path.join(cat_dir(plan, "improvement"), "%s.md" % zeroed(next_id))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(args.body, "r", encoding="utf-8") as f:
        body = f.read()
    if os.path.exists(target):
        raise_issue(plan, "collision", "改进目标文件已存在。", intended=body,
                    intended_name="intended_%s.md" % zeroed(next_id),
                    existing=open(target).read(), existing_name="existing_%s.md" % zeroed(next_id))
        sys.exit(1)
    with open(target, "w", encoding="utf-8") as f:
        f.write(body)
    idx["briefs"] = [b for b in idx.get("briefs", []) if b.get("id") != next_id]
    idx["briefs"].append({
        "id": next_id,
        "title": args.title or "(无标题)",
        "status": int(args.status) if args.status is not None else 1,
        "priority": int(args.priority) if args.priority is not None else 3,
        "in_architecture": None,
        "implemented_in": None,
        "file": "improvements/%s.md" % zeroed(next_id),
    })
    idx["max_id"] = next_id
    idx["revision"] = int(idx.get("revision", 0)) + 1
    write_json(idx_file, idx)
    _regen_toc(plan, "improvement")
    print("Appended improvements/%s.md (%s)" % (zeroed(next_id), args.title or next_id))


def cmd_append_issue(args, plan):
    desc = json.load(open(args.description, "r", encoding="utf-8"))
    issue_dir, num = allocate_issue_dir(plan)
    assets = os.path.join(issue_dir, "assets")
    os.makedirs(assets, exist_ok=True)
    if args.assets_dir and os.path.isdir(args.assets_dir):
        for name in os.listdir(args.assets_dir):
            src = os.path.join(args.assets_dir, name)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(assets, name))
    desc.setdefault("issue_id", num)
    desc.setdefault("detected_at", now_iso())
    desc.setdefault("status", "open")
    desc["assets_refs"] = sorted(os.listdir(assets))
    write_json(os.path.join(issue_dir, "description.json"), desc)
    _regen_toc(plan, "issues")
    print("Recorded issues/%s/ (issue_id=%s)" % (zeroed(num), num))


def cmd_append(args):
    plan = os.path.abspath(args.plan)
    kind = args.kind
    if kind == "history":
        if args.event == "-":
            event = json.load(sys.stdin)
        else:
            event = json.load(open(args.event, "r", encoding="utf-8"))
        cmd_append_history(args, plan, event)
    elif kind == "questions":
        cmd_append_questions(args, plan)
    elif kind == "issue":
        cmd_append_issue(args, plan)
    elif kind == "improvement":
        cmd_append_improvement(args, plan)
    else:
        sys.exit("ERROR: unknown --kind %s" % kind)


def cmd_show(args):
    plan = os.path.abspath(args.plan)
    kind = args.kind
    if kind == "architecture":
        idx = load_json(index_path(plan, "architecture")) or {}
        print("implemented_version=%s  latest_version=%s"
              % (idx.get("implemented_version"), idx.get("latest_version")))
        for v in idx.get("versions", []):
            print("  v%-3s %s" % (v.get("version"), v.get("file")))
        return
    idx = load_json(index_path(plan, kind))
    if idx is None:
        print("No index at %s" % index_path(plan, kind))
        return
    print("kind=%s max_id=%s revision=%s" % (kind, idx.get("max_id"), idx.get("revision")))
    key = "num" if kind == "questions" else ("issue_id" if kind == "issues" else "event_id")
    briefs = sorted(idx.get("briefs", []), key=lambda x: x.get(key, 0))
    last = getattr(args, "last", None)
    if last and last > 0:
        briefs = briefs[-last:]
    for b in briefs:
        if kind == "history":
            extra = ""
            if b.get("is_correction"):
                extra = " -> corrects #%s" % b.get("corrects_event_id")
            print("#%-3s %-18s @%s actor=%-5s%s"
                  % (b.get("event_id"), b.get("event_type"), b.get("recorded_at"),
                     b.get("actor_type"), extra))
        elif kind == "questions":
            print("Q%-3s %s" % (b.get("num"), (b.get("question") or "")[:70]))
        else:
            print("#%-3s %-16s %s" % (b.get("issue_id"), b.get("event_type"), b.get("status")))


def _fs_ids(d, pattern):
    ids = []
    if not os.path.isdir(d):
        return ids
    for name in os.listdir(d):
        m = re.match(pattern, name)
        if m:
            ids.append(int(m.group(1)))
    return sorted(ids)


def cmd_audit(args):
    plan = os.path.abspath(args.plan)
    problems = []
    notes = []

    # history
    idx = load_json(index_path(plan, "history"))
    if idx is None:
        problems.append("history_index.json 缺失")
    else:
        ids = _fs_ids(cat_dir(plan, "history"), r"^(\d+)\.json$")
        max_id = int(idx.get("max_id", 0))
        if not ids:
            problems.append("history/ 为空")
        else:
            expected = list(range(1, max(ids) + 1))
            if ids != expected:
                problems.append("history/ ID 不连续或缺口：%s" % ids)
            if max(ids) != max_id:
                problems.append("history 索引 max_id=%s 与实际文件最大 id=%s 不一致" % (max_id, max(ids)))
        for b in idx.get("briefs", []):
            eid = b.get("event_id")
            if eid is None:
                continue
            p = os.path.join(plan, "history", "%s.json" % zeroed(eid))
            if not os.path.exists(p):
                problems.append("索引含 event_id=%s 但文件不存在" % eid)
                continue
            ev = load_json(p)
            if ev and ev.get("event_type") != b.get("event_type"):
                problems.append("event #%s 索引 event_type 与文件不符" % eid)
            if ev and ev.get("recorded_at") != b.get("recorded_at"):
                problems.append("event #%s 索引 recorded_at 与文件不符" % eid)

    # questions
    qidx = load_json(index_path(plan, "questions"))
    if qidx is not None:
        ids = _fs_ids(cat_dir(plan, "questions"), r"^(\d+)\.md$")
        if ids and max(ids) != int(qidx.get("max_id", 0)):
            problems.append("questions 索引 max_id 与实际不一致")

    # issues
    iidx = load_json(index_path(plan, "issues"))
    if iidx is not None:
        ids = _fs_ids(cat_dir(plan, "issues"), r"^(\d+)$")
        if ids and max(ids) != int(iidx.get("max_id", 0)):
            problems.append("issues 索引 max_id 与实际不一致")

    # improvement
    impidx = load_json(index_path(plan, "improvement"))
    if impidx is None:
        problems.append("improvement_index.json 缺失")
    else:
        ids = _fs_ids(cat_dir(plan, "improvement"), r"^(\d+)\.md$")
        if ids and max(ids) != int(impidx.get("max_id", 0)):
            problems.append("improvement 索引 max_id 与实际不一致")

    # architecture
    aidx = load_json(index_path(plan, "architecture"))
    if aidx is None:
        problems.append("architecture_index.json 缺失")
    else:
        vers = _fs_ids(cat_dir(plan, "architecture"), r"^(\d+)\.md$")
        imp, lat = aidx.get("implemented_version"), aidx.get("latest_version")
        if not vers:
            if lat:
                problems.append("architecture/ 为空（索引声明了版本但缺文档）")
        else:
            if lat != max(vers):
                problems.append("architecture latest_version=%s 与实际最大版本=%s 不一致" % (lat, max(vers)))
            if imp not in vers:
                problems.append("architecture implemented_version=%s 不在实际版本中 %s" % (imp, vers))
        if imp != lat:
            # 进行中的正常状态（目标版本已定义、尚未落地），非数据不一致
            notes.append("架构版本 %s 已定义但尚未落地（implemented=%s, latest=%s）" % (lat, imp, lat))

    # custom features (architecture 008) — only what is registered is checked
    for nm in load_categories(plan):
        if not os.path.isdir(custom_dir(plan, nm)):
            problems.append("custom/%s/ 缺失（已注册但无目录）" % nm)
        if not os.path.exists(custom_index_path(plan, nm)):
            problems.append("custom/%s_index.json 缺失（应由 custom sync 生成）" % nm)
        if not os.path.exists(custom_toc_path(plan, nm)):
            problems.append("custom/%s_TOC.md 缺失（应由 custom sync 生成）" % nm)
        cidx = load_json(custom_index_path(plan, nm))
        if cidx is not None:
            fids = [r[0] for r in custom_records(plan, nm)]
            if fids and max(fids) != int(cidx.get("max_id", 0)):
                problems.append("custom/%s 索引 max_id=%s 与实际记录最大号=%s 不一致"
                                % (nm, cidx.get("max_id"), max(fids)))
            for b in cidx.get("briefs", []):
                if b.get("file") and not os.path.exists(os.path.join(plan, b["file"])):
                    problems.append("custom/%s 索引含 %s 但文件不存在" % (nm, b["file"]))

    # meta files must be gone
    for kind in ("history", "questions", "issues", "architecture"):
        mp = os.path.join(plan, "%s_meta.json" % kind)
        if os.path.exists(mp):
            problems.append("遗留 %s_meta.json（architecture 003 已删除，不应存在）" % kind)
    for legacy in ("plan_001.md", "plan_002.md"):
        if os.path.exists(os.path.join(plan, legacy)):
            problems.append("遗留 %s（architecture 003 已删除，不应存在）" % legacy)
    # TOCs must exist
    for kind in ("history", "questions", "issues", "architecture", "improvement"):
        if not os.path.exists(os.path.join(plan, "%s_TOC.md" % kind)):
            problems.append("%s_TOC.md 缺失（应由 gen-toc 生成）" % kind)

    for n in notes:
        print("NOTE: " + n)
    if problems:
        print("AUDIT FAILED (%d):" % len(problems))
        for p in problems:
            print("  - " + p)
        sys.exit(1)
    print("AUDIT OK — 各文件夹与索引一致。")


def cmd_rebuild_index(args):
    plan = os.path.abspath(args.plan)
    kind = args.kind
    if kind == "history":
        ids = _fs_ids(cat_dir(plan, "history"), r"^(\d+)\.json$")
        briefs = []
        for i in ids:
            ev = load_json(os.path.join(cat_dir(plan, "history"), "%s.json" % zeroed(i)))
            if not ev:
                continue
            briefs.append({
                "event_id": i,
                "event_type": ev.get("event_type"),
                "recorded_at": ev.get("recorded_at"),
                "actor_type": (ev.get("actor") or {}).get("type"),
                "change_summary": (ev.get("operation") or {}).get("change_summary", ""),
                "is_correction": ev.get("event_type") == "correction",
                "corrects_event_id": (ev.get("correction") or {}).get("corrects_event_id"),
                "file": "history/%s.json" % zeroed(i),
            })
        write_json(index_path(plan, "history"),
                   {"max_id": max(ids) if ids else 0,
                    "revision": len(ids), "briefs": briefs})
        print("Rebuilt history_index.json (%d events)" % len(ids))
    elif kind == "questions":
        idx = load_json(index_path(plan, "questions")) or empty_index("questions")
        ids = _fs_ids(cat_dir(plan, "questions"), r"^(\d+)\.md$")
        idx["max_id"] = max(ids) if ids else 0
        idx["briefs"] = [b for b in idx.get("briefs", []) if b.get("num") in ids]
        idx["revision"] = int(idx.get("revision", 0)) + 1
        write_json(index_path(plan, "questions"), idx)
        print("Rebuilt questions_index.json (%d questions)" % len(ids))
    elif kind == "issues":
        ids = _fs_ids(cat_dir(plan, "issues"), r"^(\d+)$")
        write_json(index_path(plan, "issues"),
                   {"max_id": max(ids) if ids else 0, "revision": len(ids), "briefs": []})
        print("Rebuilt issues_index.json (%d issues)" % len(ids))
    elif kind == "improvement":
        idx = load_json(index_path(plan, "improvement")) or empty_index("improvement")
        ids = _fs_ids(cat_dir(plan, "improvement"), r"^(\d+)\.md$")
        briefs = []
        for i in ids:
            md = os.path.join(cat_dir(plan, "improvement"), "%s.md" % zeroed(i))
            title = ""
            try:
                with open(md, "r", encoding="utf-8") as f:
                    title = f.readline().strip().lstrip("#").strip()
            except Exception:
                pass
            briefs.append({"id": i, "title": title, "status": 1, "priority": 3,
                           "in_architecture": None, "implemented_in": None,
                           "file": "improvements/%s.md" % zeroed(i)})
        write_json(index_path(plan, "improvement"),
                   {"max_id": max(ids) if ids else 0, "revision": len(ids), "briefs": briefs})
        print("Rebuilt improvement_index.json (%d improvements)" % len(ids))
    _regen_toc(plan, kind)


def cmd_gen_toc(args):
    plan = os.path.abspath(args.plan)
    kinds = (["history", "questions", "issues", "architecture", "improvement"]
             if args.kind == "all" else [args.kind])
    for k in kinds:
        _regen_toc(plan, k)
        print("Generated %s_TOC.md" % k)
    if args.kind == "all":
        for nm in load_categories(plan):
            _regen_custom_toc(plan, nm)
            print("Generated %s/%s_TOC.md" % (CUSTOM_ROOT, nm))


# --------------------------------------------------------------------------
# custom feature commands (architecture 008)
# --------------------------------------------------------------------------
def cmd_custom_register(args):
    """Register ONE custom feature. Idempotent: refuses when already registered."""
    plan = os.path.abspath(args.plan)
    name = (args.name or "").strip()
    if not re.match(r"^[A-Za-z0-9_-]+$", name or ""):
        sys.exit("ERROR: custom feature 名只允许字母/数字/下划线/连字符，实际：%r" % args.name)
    data = load_json(custom_categories_path(plan)) or {"categories": []}
    cats = data.setdefault("categories", [])
    if any(c.get("name") == name for c in cats):
        print("custom feature '%s' 已注册（见 %s）。未做任何改动，终止。"
              % (name, CUSTOM_CATEGORIES))
        sys.exit(2)
    entry = {"name": name}
    if args.description:
        entry["description"] = args.description
    cats.append(entry)
    write_json(custom_categories_path(plan), data)
    n, idx_rel, toc_rel = sync_custom_feature(plan, name)
    print("registered custom feature '%s'：%s 已更新，%s/ 已建，%s + %s 已生成（%d 条记录）。"
          % (name, CUSTOM_CATEGORIES, "%s/%s" % (CUSTOM_ROOT, name), idx_rel, toc_rel, n))


def cmd_custom_sync(args):
    """Rebuild index+TOC for ONE feature (or --all). Never touches other features."""
    plan = os.path.abspath(args.plan)
    if args.all:
        names = load_categories(plan)
    elif args.name:
        names = [args.name]
    else:
        sys.exit("ERROR: custom sync 需要 --name 或 --all")
    for nm in names:
        n, idx_rel, toc_rel = sync_custom_feature(plan, nm)
        print("synced %s：%d 条记录 → %s + %s" % (nm, n, idx_rel, toc_rel))


def cmd_custom_list(args):
    plan = os.path.abspath(args.plan)
    names = load_categories(plan)
    if not names:
        print("(未注册任何 custom feature；见 %s)" % CUSTOM_CATEGORIES)
        return
    for nm in names:
        print("%-20s %d 条记录" % (nm, len(custom_records(plan, nm))))


def cmd_migrate(args):
    plan = os.path.abspath(args.plan)
    old_hist = os.path.join(plan, "history.json")
    if not os.path.exists(old_hist):
        print("No history.json to migrate (skipped).")
    else:
        with open(old_hist, "r", encoding="utf-8") as f:
            old = json.load(f)
        events = old.get("events", []) if isinstance(old, dict) else old
        if not isinstance(events, list):
            sys.exit("ERROR: history.json 既非数组也无 events 键。")
        hdir = cat_dir(plan, "history")
        os.makedirs(hdir, exist_ok=True)
        written = 0
        for i, ev in enumerate(events, start=1):
            if not isinstance(ev, dict):
                continue
            ev.setdefault("schema_version", EVENT_SCHEMA_VERSION)
            ev.setdefault("event_id", i)
            write_json(os.path.join(hdir, "%s.json" % zeroed(i)), ev)
            written += 1
        print("Migrated %d events -> history/*.json" % written)
    cmd_rebuild_index(argparse.Namespace(plan=args.plan, kind="history"))

    old_q = os.path.join(plan, "questions.md")
    if not os.path.exists(old_q):
        print("No questions.md to migrate (skipped).")
    else:
        with open(old_q, "r", encoding="utf-8") as f:
            text = f.read()
        parts = re.split(r"(?m)^## Q(\d+)\b", text)
        qdir = cat_dir(plan, "questions")
        os.makedirs(qdir, exist_ok=True)
        briefs, written = [], 0
        for j in range(1, len(parts), 2):
            num = int(parts[j])
            body = "## Q%d%s" % (num, parts[j + 1])
            body = body.rstrip() + "\n"
            with open(os.path.join(qdir, "%s.md" % zeroed(num)), "w", encoding="utf-8") as f:
                f.write(body)
            q = ""
            for line in body.splitlines()[1:]:
                s = line.strip()
                if not s or s.startswith("---"):
                    continue
                m = re.match(r"^\*\*[^*]*\*\*\s*[:：]?\s*(.*)$", s)
                cand = (m.group(1).strip() if m else s.lstrip("#* ").strip())
                if cand:
                    q = cand
                    break
            briefs.append({"num": num, "question_ref": "Q%d" % num, "question": q,
                           "answer_summary": "", "file": "questions/%s.md" % zeroed(num)})
            written += 1
        ids = [b["num"] for b in briefs]
        write_json(index_path(plan, "questions"),
                   {"max_id": max(ids) if ids else 0, "revision": len(ids),
                    "briefs": sorted(briefs, key=lambda x: x["num"])})
        print("Migrated %d questions -> questions/*.md" % written)
    print("MIGRATE done. 旧 history.json / questions.md 请在 audit 通过后删除。")


def cmd_recover(args):
    plan = os.path.abspath(args.plan)
    issue_dir = os.path.join(cat_dir(plan, "issues"), zeroed(int(args.issue)))
    assets = os.path.join(issue_dir, "assets")
    if not os.path.isdir(assets):
        sys.exit("ERROR: 无 assets: %s" % assets)
    intended = None
    for name in sorted(os.listdir(assets)):
        if name.startswith("intended_") and name.endswith(".json"):
            intended = load_json(os.path.join(assets, name))
            break
    if intended is None:
        sys.exit("ERROR: assets 中未找到 intended_*.json")
    ev = dict(intended)
    ev.pop("event_id", None)
    ev.pop("recorded_at", None)
    cmd_append_history(argparse.Namespace(ttl=DEFAULT_TTL, retries=DEFAULT_RETRIES, model=None),
                       plan, ev)
    desc = load_json(os.path.join(issue_dir, "description.json")) or {}
    desc["status"] = "resolved"
    desc["resolved_at"] = now_iso()
    write_json(os.path.join(issue_dir, "description.json"), desc)


def _git(plan, *cmd, check=True):
    """Run a git command in the plan root; raises on failure unless check=False."""
    return subprocess.run(["git", "-C", plan] + list(cmd),
                          capture_output=True, text=True, check=check)


def cmd_set_implemented(args):
    plan = os.path.abspath(args.plan)
    idx = load_json(index_path(plan, "architecture")) or empty_index("architecture")
    ver = int(args.version)
    idx["implemented_version"] = ver
    idx["revision"] = int(idx.get("revision", 0)) + 1
    write_json(index_path(plan, "architecture"), idx)
    _regen_toc(plan, "architecture")
    print("architecture implemented_version -> %s" % args.version)

    # ---- IMP-002 (architecture 006): mandatory publish chain ----
    # The ONLY trigger for commit/push/tag is implementing an architecture
    # (this command). Bookkeeping (improvements/corrections/Q&A) must never commit.
    # The chain is forced, connected, and never split: add -> commit -> push ->
    # tag -> push --tags. The tag version equals the implemented architecture
    # version. NOTE: we use `v0.{version}` (not the plan's literal `v{NNN}`),
    # because check-standard's parse_version only accepts `vX.Y` and the repo's
    # existing tags are v0.3/v0.4/v0.5 — `v6` would break version reporting.
    title = ""
    for v in idx.get("versions", []):
        if int(v.get("version", 0)) == ver:
            title = v.get("title", "")
            break
    tag = "v0.%d" % ver
    commit_msg = "implement architecture/%s: %s" % (zeroed(ver), title)
    try:
        _git(plan, "add", "-A")
        _git(plan, "commit", "-m", commit_msg)
    except subprocess.CalledProcessError as e:
        print("PUBLISH FAILED at commit: %s" % (e.stderr or e).strip(), file=sys.stderr)
        sys.exit(1)
    try:
        _git(plan, "push")
    except subprocess.CalledProcessError as e:
        # roll back the local commit so we never leave a partial publish
        _git(plan, "reset", "--soft", "HEAD~1", check=False)
        print("PUBLISH FAILED at push (local commit rolled back): %s"
              % (e.stderr or e).strip(), file=sys.stderr)
        sys.exit(1)
    try:
        _git(plan, "tag", tag)
        _git(plan, "push", "--tags")
    except subprocess.CalledProcessError as e:
        print("PUBLISH WARNING at tag/push --tags: %s (tag %s created locally)"
              % ((e.stderr or e).strip(), tag), file=sys.stderr)
        sys.exit(1)
    print("PUBLISH OK: committed + pushed + tagged %s + pushed tags" % tag)


def main():
    p = argparse.ArgumentParser(description="Append-only plan history logger (folder form).")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("init")
    pi.add_argument("--plan", required=True)
    pi.add_argument("--meta", nargs="*")

    pa = sub.add_parser("append")
    pa.add_argument("--plan", required=True)
    pa.add_argument("--kind", default="history",
                    choices=["history", "questions", "issue", "improvement"])
    pa.add_argument("--event", help="event JSON path, or '-' for stdin (kind=history)")
    pa.add_argument("--body", help="markdown body (kind=questions|improvement)")
    pa.add_argument("--question-ref")
    pa.add_argument("--question")
    pa.add_argument("--answer-summary")
    pa.add_argument("--title", help="improvement title (kind=improvement)")
    pa.add_argument("--priority", type=int, default=3, help="improvement priority 1-5 (kind=improvement)")
    pa.add_argument("--status", type=int, default=1, help="improvement status 1-3 (kind=improvement)")
    pa.add_argument("--description", help="description.json (kind=issue)")
    pa.add_argument("--assets-dir")
    pa.add_argument("--model", help="platform-provided model (overrides env fallback)")
    pa.add_argument("--ttl", type=float, default=DEFAULT_TTL)
    pa.add_argument("--retries", type=int, default=DEFAULT_RETRIES)

    ps = sub.add_parser("show")
    ps.add_argument("--plan", required=True)
    ps.add_argument("--kind", default="history",
                    choices=["history", "questions", "issues", "architecture"])
    ps.add_argument("--last", type=int, default=50, help="print only the last N briefs (0=all)")

    pu = sub.add_parser("audit")
    pu.add_argument("--plan", required=True)

    pr = sub.add_parser("rebuild-index")
    pr.add_argument("--plan", required=True)
    pr.add_argument("--kind", default="history", choices=["history", "questions", "issues", "improvement"])

    pg = sub.add_parser("gen-toc")
    pg.add_argument("--plan", required=True)
    pg.add_argument("--kind", default="all",
                    choices=["all", "history", "questions", "issues", "architecture", "improvement"])

    pm = sub.add_parser("migrate")
    pm.add_argument("--plan", required=True)

    pc = sub.add_parser("recover")
    pc.add_argument("--plan", required=True)
    pc.add_argument("--issue", required=True)

    pk = sub.add_parser("set-implemented")
    pk.add_argument("--plan", required=True)
    pk.add_argument("--version", required=True)

    # custom features (architecture 008)
    pcf = sub.add_parser("custom")
    cfsub = pcf.add_subparsers(dest="custom_cmd", required=True)
    pcr = cfsub.add_parser("register")
    pcr.add_argument("--plan", required=True)
    pcr.add_argument("--name", required=True)
    pcr.add_argument("--description")
    pcs = cfsub.add_parser("sync")
    pcs.add_argument("--plan", required=True)
    pcs.add_argument("--name")
    pcs.add_argument("--all", action="store_true")
    pcl = cfsub.add_parser("list")
    pcl.add_argument("--plan", required=True)

    args = p.parse_args()
    if args.cmd == "custom":
        {"register": cmd_custom_register, "sync": cmd_custom_sync,
         "list": cmd_custom_list}[args.custom_cmd](args)
        return
    {
        "init": cmd_init, "append": cmd_append, "show": cmd_show, "audit": cmd_audit,
        "rebuild-index": cmd_rebuild_index, "gen-toc": cmd_gen_toc, "migrate": cmd_migrate,
        "recover": cmd_recover, "set-implemented": cmd_set_implemented,
    }[args.cmd](args)


if __name__ == "__main__":
    main()
