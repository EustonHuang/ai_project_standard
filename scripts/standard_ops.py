#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Built-in skills for the AI Project Standard framework (architecture 004).

Provides three subcommands used by the `install-standard` / `update-standard` /
`check-standard` skills:

  install  --version <vX.Y|latest> --project <path> [--framework <path>] [--self] [--pinned latest|<ver>]
      Adopt the standard into a project:
        * self mode  (project == framework repo): the repo adopts itself; the gate
          watches the repo and the engine is the repo's own scripts/.
        * copy mode  (default): the engine (scripts/ references/ assets/) is copied
          into <project>/.plan-standard/ and hooks point there, so the project is
          self-contained and the gate watches <project> (via PLAN_HISTORY_ROOT).
      Writes <project>/standard_version lock file + <project>/.codebuddy/settings.json
      hooks + scaffolds history/ questions/ issues/ improvements/ architecture/.

  update   --project <path> [--to latest|<vX.Y>] [--framework <path>] [--confirm-breaking]
      Upgrade the adopter's standard_version. Same major => auto. Cross major
      (breaking) => requires --confirm-breaking + prints a breaking-change review.

  check    --project <path> [--framework <path>]
      Print current / latest / behind / unimplemented-improvement count.

The framework repo is discovered as the parent of this file's directory.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

FRAMEWORK_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE_DIRS = ("scripts", "references", "assets")
ENGINE_FILES = ("README.md",)  # copied so the always-apply rule's README reference resolves
HOOK_TIMEOUTS = {"UserPromptSubmit": 20, "PostToolUse": 20, "Stop": 30}
RULE_DIR_NAME = "ai-project-standard"  # namespace for the always-apply rule under .codebuddy/rules/


# --------------------------------------------------------------------------
# version helpers
# --------------------------------------------------------------------------
def parse_version(s):
    m = re.match(r"^v?(\d+)\.(\d+)$", (s or "").strip())
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)))


def latest_tag(framework_repo):
    """Return (tag, (major, minor)) of the latest vX.Y tag, or None."""
    try:
        out = subprocess.run(["git", "-C", framework_repo, "tag"],
                             capture_output=True, text=True)
    except Exception:
        return None
    if out.returncode != 0:
        return None
    best = None
    for t in out.stdout.splitlines():
        t = t.strip()
        v = parse_version(t)
        if v and (best is None or v > best[1]):
            best = (t, v)
    return best


def tag_by_int(framework_repo, n):
    """Map an architecture integer version (001->v0.1 ...) to its git tag if present."""
    lt = latest_tag(framework_repo)
    # prefer a tag whose minor equals n and major smallest; fall back to latest
    try:
        out = subprocess.run(["git", "-C", framework_repo, "tag"],
                             capture_output=True, text=True).stdout.splitlines()
    except Exception:
        out = []
    for t in out:
        v = parse_version(t)
        if v and v[1] == n:
            return t
    return lt[0] if lt else None


# --------------------------------------------------------------------------
# lock file (key=value at <project>/standard_version)
# --------------------------------------------------------------------------
def read_lock(project):
    p = os.path.join(project, "standard_version")
    if not os.path.exists(p):
        return None
    d = {}
    for line in open(p, "r", encoding="utf-8"):
        line = line.strip()
        if not line or "=" not in line:
            continue
        k, v = line.split("=", 1)
        d[k.strip()] = v.strip()
    return d


def write_lock(project, d):
    p = os.path.join(project, "standard_version")
    lines = ["%s=%s" % (k, d[k]) for k in
             ("standard_version", "pinned", "framework_repo", "install_mode")]
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# --------------------------------------------------------------------------
# engine copy
# --------------------------------------------------------------------------
def _engine_script(framework_repo):
    return os.path.join(framework_repo, "scripts", "append_history.py")


def copy_engine(framework_repo, dest, version):
    """Copy the engine (scripts/ references/ assets/) into dest, pinned to `version`.

    Prefers `git archive <tag>` so the copied engine matches the requested tag;
    falls back to a plain copy of the current tree.
    """
    os.makedirs(dest, exist_ok=True)
    tag = tag_by_int(framework_repo, _int_of_version(version)) or version
    archived = False
    try:
        p1 = subprocess.run(
            ["git", "-C", framework_repo, "archive", tag] + list(ENGINE_DIRS) + list(ENGINE_FILES),
            capture_output=True)
        if p1.returncode == 0 and p1.stdout:
            subprocess.run(["tar", "-x", "-C", dest], input=p1.stdout)
            archived = True
    except Exception:
        archived = False
    if not archived:
        for d in ENGINE_DIRS:
            src = os.path.join(framework_repo, d)
            if os.path.isdir(src):
                shutil.copytree(src, os.path.join(dest, d), dirs_exist_ok=True)
        for f in ENGINE_FILES:
            src = os.path.join(framework_repo, f)
            if os.path.isfile(src):
                shutil.copy(src, os.path.join(dest, f))


def _int_of_version(version):
    v = parse_version(version)
    return v[1] if v else 0


# --------------------------------------------------------------------------
# hooks
# --------------------------------------------------------------------------
def _hook_command(install_mode):
    if install_mode == "self":
        return 'PLAN_HISTORY_ROOT="$CODEBUDDY_PROJECT_DIR" python3 "$CODEBUDDY_PROJECT_DIR/scripts/turn_gate.py"'
    return 'PLAN_HISTORY_ROOT="$CODEBUDDY_PROJECT_DIR" python3 "$CODEBUDDY_PROJECT_DIR/.plan-standard/scripts/turn_gate.py"'


def build_hooks(install_mode):
    cmd = _hook_command(install_mode)
    return {
        "hooks": {
            "UserPromptSubmit": [{"hooks": [{"type": "command", "command": cmd + " begin",
                                             "timeout": HOOK_TIMEOUTS["UserPromptSubmit"]}]}],
            "PostToolUse": [{"matcher": "write_to_file|replace_in_file|delete_file|Write|Edit",
                             "hooks": [{"type": "command", "command": cmd + " record",
                                        "timeout": HOOK_TIMEOUTS["PostToolUse"]}]}],
            "Stop": [{"hooks": [{"type": "command", "command": cmd + " end",
                                 "timeout": HOOK_TIMEOUTS["Stop"]}]}],
        }
    }


def write_hooks(project, install_mode, engine_dest):
    settings_dir = os.path.join(project, ".codebuddy")
    settings_path = os.path.join(settings_dir, "settings.json")
    settings = {}
    if os.path.exists(settings_path):
        try:
            settings = json.load(open(settings_path, "r", encoding="utf-8"))
        except Exception:
            settings = {}
    settings["hooks"] = build_hooks(install_mode)["hooks"]
    os.makedirs(settings_dir, exist_ok=True)
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------
# always-apply rule (CodeBuddy Rules: .codebuddy/rules/<name>/RULE.mdc)
# --------------------------------------------------------------------------
def _rule_content(install_mode, version):
    """Build the always-apply rule file (RULE.mdc) for CodeBuddy Rules.

    README path is mode-aware: copy mode points at the installed engine
    (.plan-standard/README.md); self mode points at the repo-root README.md.
    """
    readme = "README.md" if install_mode == "self" else ".plan-standard/README.md"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    front = (
        '---\n'
        'description: "AI Project Standard (ai-project-standard) %s — 本项目采用的项目规范框架；凡改动受管文件前必须先读其 README/workflow 并按“任何改动进 history”强制门记录。Use when editing architecture/、*_index.json、questions/、issues/、improvements/、README.md、references/、scripts/、skills/、assets/、standard_version、.codebuddy/settings.json。"\n'
        'alwaysApply: true\n'
        'enabled: true\n'
        'updatedAt: %s\n'
        'provider:\n'
        '---\n'
    ) % (version, now)
    body = (
        '<system_reminder>\n'
        '**本项目采用 AI Project Standard (ai-project-standard) %s（由 install-standard 写入此规则）。**\n\n'
        '## 受管文件（任何改动必须留痕）\n'
        '`architecture/`、 `*_index.json`、 `*_TOC.md`、 `questions/`、 `issues/`、 `improvements/`、 `README.md`、 `references/`、 `scripts/`、 `skills/`、 `assets/`、 `standard_version`、 `.codebuddy/settings.json`。\n\n'
        '## 必读与必做\n'
        '1. 改动上述任何文件前，先读 `<project>/%s` 的「MANDATORY」节与 `references/workflow.md`。\n'
        '2. 任何改动**必须**在 `history/` 留痕（双录：提问写 `questions/` + 追加 `qna_recorded`；改进进 `improvements/`）。\n'
        '3. 本规则在**新会话开始**自动注入；若刚安装/升级，请**新建对话会话**使其生效。\n'
        '</system_reminder>\n'
    ) % (version, readme)
    return front + body


def write_rules(project, install_mode, version):
    """Write (force-replace) the always-apply rule under .codebuddy/rules/.

    Default on name collision is force replace (single-version truth): if the
    namespace directory already exists it is overwritten without prompt/backup.
    """
    rules_dir = os.path.join(project, ".codebuddy", "rules", RULE_DIR_NAME)
    os.makedirs(rules_dir, exist_ok=True)
    path = os.path.join(rules_dir, "RULE.mdc")
    with open(path, "w", encoding="utf-8") as f:
        f.write(_rule_content(install_mode, version))
    return path


# --------------------------------------------------------------------------
# scaffold project history
# --------------------------------------------------------------------------
def scaffold(project, framework_repo):
    script = _engine_script(framework_repo)
    if not os.path.exists(script):
        return
    subprocess.run([sys.executable, script, "init", "--plan", project],
                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# --------------------------------------------------------------------------
# breaking-change review
# --------------------------------------------------------------------------
def _read_arch_header(path):
    ver = None
    breaking = False
    items = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i > 30:
                    break
                m = re.match(r"^version:\s*(.+)$", line)
                if m:
                    ver = parse_version(m.group(1).strip())
                m = re.match(r"^breaking:\s*(true|false)$", line.strip(), re.I)
                if m:
                    breaking = m.group(1).lower() == "true"
                m = re.match(r"^breaking_items:\s*(.+)$", line)
                if m:
                    raw = m.group(1).strip()
                    items = [x.strip().strip("[]()\"'") for x in re.split(r"[,\n]", raw) if x.strip()]
    except Exception:
        pass
    return ver, breaking, items


def print_breaking_review(framework_repo, cur, tgt):
    a_idx = os.path.join(framework_repo, "architecture_index.json")
    if not os.path.exists(a_idx):
        print("  (无 architecture_index.json，无法列出破坏性项)")
        return
    idx = json.load(open(a_idx, "r", encoding="utf-8"))
    print("跨 major 破坏性变更评审（current=%s → target=%s）：" % (cur, tgt))
    found = False
    for v in idx.get("versions", []):
        ver = parse_version("v0.%d" % v.get("version", 0))  # N -> v0.N
        if ver is None or not (cur < ver <= tgt):
            continue
        fpath = os.path.join(framework_repo, v.get("file", ""))
        av, breaking, items = _read_arch_header(fpath)
        if not breaking:
            continue
        found = True
        print("  - %s (%s): breaking_items=%s" % (v.get("file"), v.get("title", ""), items or "—"))
    if not found:
        print("  (两版本间无标 breaking 的 architecture 版本)")


# --------------------------------------------------------------------------
# sub-commands
# --------------------------------------------------------------------------
def cmd_install(args):
    framework_repo = os.path.abspath(args.framework) if args.framework else FRAMEWORK_ROOT
    version = args.version or "latest"
    if version == "latest":
        lt = latest_tag(framework_repo)
        if lt is None:
            sys.exit("ERROR: 无法解析 latest（%s 无 vX.Y tag）" % framework_repo)
        version = lt[0]
    project = os.path.abspath(args.project)
    self_mode = bool(args.self) or os.path.realpath(project) == os.path.realpath(framework_repo)
    os.makedirs(project, exist_ok=True)

    if self_mode:
        install_mode = "self"
        engine_dest = None
    else:
        engine_dest = os.path.join(project, ".plan-standard")
        copy_engine(framework_repo, engine_dest, version)
        install_mode = "copy"

    write_lock(project, {
        "standard_version": version,
        "pinned": args.pinned or "latest",
        "framework_repo": framework_repo,
        "install_mode": install_mode,
    })
    write_hooks(project, install_mode, engine_dest)
    scaffold(project, framework_repo)
    write_rules(project, install_mode, version)

    print("installed standard %s into %s (mode=%s)" % (version, project, install_mode))
    print("  lock: %s/standard_version" % project)
    print("  hooks: %s/.codebuddy/settings.json" % project)
    print("  rule: %s/.codebuddy/rules/%s/RULE.mdc (alwaysApply)" % (project, RULE_DIR_NAME))
    if not self_mode:
        print("  engine copied to: %s" % engine_dest)
    print("  提示：请【新建对话会话】使规则生效；hooks 是否触发请实测（改受管文件看是否 exit 2 拦截）。")


def cmd_update(args):
    project = os.path.abspath(args.project)
    lock = read_lock(project)
    if lock is None:
        sys.exit("ERROR: %s 未安装标准（无 standard_version 锁文件）" % project)
    current = lock.get("standard_version")
    framework_repo = os.path.abspath(args.framework) if args.framework else lock.get("framework_repo", FRAMEWORK_ROOT)
    lt = latest_tag(framework_repo)
    target = args.to or "latest"
    if target == "latest":
        if lt is None:
            sys.exit("ERROR: 无法解析 latest（%s 无 vX.Y tag）" % framework_repo)
        target = lt[0]
    cur = parse_version(current)
    tgt = parse_version(target)
    if cur is None or tgt is None:
        sys.exit("ERROR: 版本解析失败 current=%s target=%s" % (current, target))
    if tgt <= cur:
        print("已是最新（current=%s，target=%s）" % (current, target))
        return
    cross = tgt[0] > cur[0]
    if cross and not args.confirm_breaking:
        print_breaking_review(framework_repo, cur, tgt)
        print("\n跨 major 变更：需带 --confirm-breaking 并人工 review 上述输出后才会更新 hook/锁文件。")
        sys.exit(0)
    if lock.get("install_mode") == "copy":
        copy_engine(framework_repo, os.path.join(project, ".plan-standard"), target)
        write_hooks(project, "copy", os.path.join(project, ".plan-standard"))
    write_lock(project, dict(lock, standard_version=target))
    write_rules(project, lock.get("install_mode") or "copy", target)
    if cross:
        print_breaking_review(framework_repo, cur, tgt)
        print("已确认跨 major 更新。")
    print("已从 %s → %s" % (current, target))
    print("  规则已重写：%s/.codebuddy/rules/%s/RULE.mdc（alwaysApply，强制替代；请新建会话生效）。"
          % (project, RULE_DIR_NAME))


def cmd_check(args):
    project = os.path.abspath(args.project)
    lock = read_lock(project)
    framework_repo = os.path.abspath(args.framework) if args.framework else (
        lock.get("framework_repo") if lock else FRAMEWORK_ROOT)
    lt = latest_tag(framework_repo)
    current = lock.get("standard_version") if lock else None
    latest = lt[0] if lt else None
    print("project: %s" % project)
    print("current standard_version: %s" % (current or "(未安装)"))
    print("latest standard_version : %s" % (latest or "(未知)"))
    if current and latest:
        cur = parse_version(current)
        tgt = parse_version(latest)
        if cur and tgt and tgt > cur:
            print("状态: 落后（有可用更新）")
        else:
            print("状态: 最新")
    # unimplemented improvements count
    imp_idx = os.path.join(project, "improvement_index.json")
    if os.path.exists(imp_idx):
        idx = json.load(open(imp_idx, "r", encoding="utf-8"))
        n = sum(1 for b in idx.get("briefs", []) if int(b.get("status", 1)) < 3)
        print("未实施改进 (status<3): %d 条" % n)


def main():
    p = argparse.ArgumentParser(description="AI Project Standard — install/update/check.")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("install")
    pi.add_argument("--version", default="latest")
    pi.add_argument("--project", required=True)
    pi.add_argument("--framework", default=None)
    pi.add_argument("--self", action="store_true")
    pi.add_argument("--pinned", default="latest")

    pu = sub.add_parser("update")
    pu.add_argument("--project", required=True)
    pu.add_argument("--to", default="latest")
    pu.add_argument("--framework", default=None)
    pu.add_argument("--confirm-breaking", action="store_true")

    pc = sub.add_parser("check")
    pc.add_argument("--project", required=True)
    pc.add_argument("--framework", default=None)

    args = p.parse_args()
    {"install": cmd_install, "update": cmd_update, "check": cmd_check}[args.cmd](args)


if __name__ == "__main__":
    main()
