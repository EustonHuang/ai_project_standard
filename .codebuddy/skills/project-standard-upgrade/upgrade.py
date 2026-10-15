#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Global orchestrator to upgrade installed AI Project Standard projects.

Default behaviour (`--list`, or no targets): list every project in the monitor
config whose installed version is NOT the latest.

Upgrade behaviour: drive `standard_ops.py update` for one or many target projects,
optionally with an explicit target version per project. Omitted version -> latest.
This is the multi-project wrapper around the same `update` command that
`update-standard` runs for a single project.
"""

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILLS_DIR = os.path.dirname(HERE)                       # <repo>/.codebuddy/skills


def _find_framework_root():
    p = HERE
    for _ in range(8):
        if os.path.isfile(os.path.join(p, "standard_version")) and \
           os.path.isdir(os.path.join(p, "scripts")):
            return p
        p = os.path.dirname(p)
    return os.path.dirname(os.path.dirname(os.path.dirname(HERE)))


FRAMEWORK_ROOT = _find_framework_root()
MONITOR = os.path.join(SKILLS_DIR, "project-standard-monitor", "scan.py")
STDOPS = os.path.join(FRAMEWORK_ROOT, "scripts", "standard_ops.py")


def parse_target(s):
    """'<path>=<version>' or '<path>' (version omitted -> latest)."""
    if "=" in s:
        p, v = s.split("=", 1)
        return p.strip(), v.strip() or None
    return s.strip(), None


def get_behind():
    """Return (latest_tag, [behind_project_dicts]) from the monitor's JSON output."""
    r = subprocess.run([sys.executable, MONITOR, "--json"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        sys.exit(1)
    data = json.loads(r.stdout)
    return data.get("latest"), [p for p in data.get("projects", []) if p.get("behind")]


def resolve_targets(args):
    targets = [(os.path.abspath(p), v) for p, v in (parse_target(t) for t in (args.target or []))]
    if args.all:
        _, behind = get_behind()
        targets += [(p["project"], None) for p in behind]  # None -> latest
    return targets


def main():
    ap = argparse.ArgumentParser(description="全局升级已安装项目规范（orchestrator）")
    ap.add_argument("--list", action="store_true",
                    help="仅列出配置中版本 != 最新的项目（默认行为）")
    ap.add_argument("--target", action="append",
                    help="<project>=<version> 或 <project>（缺版本=最新），可多次")
    ap.add_argument("--all", action="store_true", help="升级所有落后项目到最新")
    ap.add_argument("--confirm-breaking", action="store_true",
                    help="跨 major 也确认更新（否则仅打印 breaking review 不实际更新）")
    ap.add_argument("--dry-run", action="store_true", help="只打印将执行的命令，不实际改动")
    ap.add_argument("--framework", default=FRAMEWORK_ROOT)
    args = ap.parse_args()

    if args.list or (not args.target and not args.all):
        latest, behind = get_behind()
        print("最新项目规范版本: %s" % (latest or "(未知)"))
        if not behind:
            print("没有项目落后最新版本。")
            return
        print("以下项目落后最新版本：")
        for p in behind:
            print("  - %s  当前=%s" % (p["project"], p["version"]))
        print("\n使用 --target <project> 升级到最新，--all 全部升级，"
              "或 --target <project>=<version> 指定版本。")
        return

    targets = resolve_targets(args)
    if not targets:
        print("无目标项目。")
        return

    print("将执行 %d 个升级：" % len(targets))
    for p, v in targets:
        print("  - %s -> %s" % (p, v or "latest"))
    if args.dry_run:
        return

    for p, v in targets:
        cmd = [sys.executable, STDOPS, "update", "--project", p]
        if v:
            cmd += ["--to", v]
        if args.confirm_breaking:
            cmd += ["--confirm-breaking"]
        print("\n=== %s -> %s ===" % (p, v or "latest"))
        r = subprocess.run(cmd)
        if r.returncode != 0:
            print("  ! 失败 (exit %d)，继续下一个。" % r.returncode, file=sys.stderr)


if __name__ == "__main__":
    main()
