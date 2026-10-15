#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Global monitor for AI Project Standard adoption.

Scans the `scan_roots` from projects.config.json, finds every project that has
installed the standard (detected by a `standard_version` lock file), reports each
project's installed version + whether it is behind, and finally prints the latest
available standard version (highest `vX.Y` git tag in the framework repo).
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_EXCLUDE = {"node_modules", ".git", "__pycache__", ".venv", "venv",
                   ".codebuddy", ".plan-standard", "dist", "build"}


def _find_framework_root():
    """Walk up from this file until we hit the framework repo root."""
    p = HERE
    for _ in range(8):
        if os.path.isfile(os.path.join(p, "standard_version")) and \
           os.path.isdir(os.path.join(p, "scripts")):
            return p
        p = os.path.dirname(p)
    return os.path.dirname(os.path.dirname(os.path.dirname(HERE)))


FRAMEWORK_ROOT = _find_framework_root()
sys.path.insert(0, os.path.join(FRAMEWORK_ROOT, "scripts"))
from standard_ops import parse_version, latest_tag, read_lock  # noqa: E402


def find_projects(roots, max_depth, exclude):
    """Walk each root up to max_depth; return [(path, version, lock_dict)].

    Once a directory is detected as an installed project, stop descending into it.
    """
    results = []
    seen = set()
    for root in roots:
        root = os.path.abspath(root)
        if not os.path.isdir(root):
            print("WARN: scan root 不存在: %s" % root, file=sys.stderr)
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            if dirpath[len(root):].count(os.sep) > max_depth:
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames if d not in exclude]
            if "standard_version" in filenames:
                lock = read_lock(dirpath)
                if dirpath not in seen:
                    results.append((dirpath, (lock or {}).get("standard_version"), lock))
                    seen.add(dirpath)
                dirnames[:] = []
    return results


def main():
    ap = argparse.ArgumentParser(description="全局扫描已安装项目规范的项目与版本")
    ap.add_argument("--config", default=os.path.join(HERE, "projects.config.json"))
    ap.add_argument("--framework", default=FRAMEWORK_ROOT, help="框架仓库根（默认本仓库）")
    ap.add_argument("--max-depth", type=int, default=None, help="覆盖配置里的 max_depth")
    ap.add_argument("--json", action="store_true", help="输出 JSON 而非表格")
    args = ap.parse_args()

    cfg = {}
    if os.path.exists(args.config):
        try:
            cfg = json.load(open(args.config, "r", encoding="utf-8"))
        except Exception as e:
            print("ERROR: 无法解析 config %s: %s" % (args.config, e), file=sys.stderr)
            sys.exit(1)
    roots = cfg.get("scan_roots", [])
    if not roots:
        print("ERROR: config 无 scan_roots: %s" % args.config, file=sys.stderr)
        sys.exit(1)
    exclude = DEFAULT_EXCLUDE | set(cfg.get("exclude", []))
    max_depth = args.max_depth if args.max_depth is not None else cfg.get("max_depth", 4)

    lt = latest_tag(os.path.abspath(args.framework))
    latest = lt[0] if lt else None
    latest_v = parse_version(latest) if latest else None

    out = []
    for path, ver, lock in find_projects(roots, max_depth, exclude):
        v = parse_version(ver) if ver else None
        out.append({
            "project": path,
            "version": ver,
            "behind": bool(latest_v and v and latest_v > v),
            "framework_repo": (lock or {}).get("framework_repo"),
            "install_mode": (lock or {}).get("install_mode"),
        })

    if args.json:
        print(json.dumps({"latest": latest, "projects": out}, ensure_ascii=False, indent=2))
        return

    print("扫描根: %s" % ", ".join(roots))
    print("最新项目规范版本: %s" % (latest or "(未知)"))
    print("")
    print("%-58s %-9s %s" % ("项目文件夹", "已装版本", "状态"))
    print("-" * 88)
    for o in sorted(out, key=lambda x: x["project"]):
        status = "落后" if o["behind"] else ("已最新" if o["version"] else "未知")
        print("%-58s %-9s %s" % (o["project"][:58], o["version"] or "-", status))
    print("")
    print("共发现 %d 个已安装项目，其中 %d 个落后最新版本。"
          % (len(out), sum(1 for o in out if o["behind"])))


if __name__ == "__main__":
    main()
