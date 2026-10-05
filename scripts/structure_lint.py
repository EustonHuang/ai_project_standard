#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Structure-consistency / anti-redundancy lint for managed architecture docs.

Implements IMP-001 (architecture 006 / v0.6). Validates every
`architecture/*.md` against two mechanical rules so that "改了留痕" is upgraded
to "改了且改得合规":

  1. Top-level section numbering must be contiguous starting at 0
     (`## 0.`, `## 1.`, ... `## N.`) with NO gaps, NO duplicates, and NO
     unnumbered floating `##` sections breaking the `§0–§N` sequence.
  2. No document-structure self-referential wording (e.g. "本节属于本版本",
     "不属于 §X", "§9 已不含"). Such meta-comments restate facts the document
     body already establishes and are pure noise.

Matches inside inline code spans (`` `...` ``) and 「...」 / 『...』 quotations
are stripped first, because architecture/006.md itself *describes* these banned
phrases as examples — those occurrences are illustrative, not violations.

Exit code 0 = clean; non-zero = at least one violation (for turn_gate to warn/block).

Usage
-----
  python structure_lint.py <plan> [--file PATH]
    <plan>   plan root (architecture/ lives under it)
    --file   lint a single architecture md instead of all of them
"""

import argparse
import os
import re
import sys

# A section heading: exactly two hashes, optional leading spaces, then either a
# numbered "N." section or an unnumbered one.
SECTION_RE = re.compile(r"^##\s+(.*)$")
NUMBERED_RE = re.compile(r"^(\d+)\.\s")


def _strip_illustrative(text):
    """Remove inline code spans and 「」/『』 quotations — those are examples, not claims."""
    text = re.sub(r"`[^`]*`", "", text)            # `code`
    text = re.sub(r"[「『][^」』]*[」』]", "", text)  # 「...」 / 『...』
    return text


# Self-referential document-structure claims. Deliberately precise: we match a
# section/version subject combined with a membership/exclusion verb, not bare
# keywords (e.g. "后续" alone is temporal and legitimate).
SELF_REF_PATTERNS = [
    # 本节/本章/本文/本文档/本文件 + 属于/不属于/包含/不含/已移除/...
    re.compile(r"(本节|本章|本方案|本文|本文档|本文件)\s*"
               r"(属于|不属于|归入|不归入|包含|不含|已含|已不含|已移除|已删除|已不|不在|位于)"),
    # 归入/属于 + 本版本/vN/版本N
    re.compile(r"(属于|不属于|归入|不归入|归为|划入|划为)\s*(本版本|本版|v\d|版本\s*\d)"),
    # §N 已不含/已移除/已删除/不再包含/不再属于/已不在 ...
    re.compile(r"§\s*\d+\s*(已?不含|已?移除|已?删除|不再包含|不再属于|已不在|已去除)"),
]


def lint_file(path):
    """Return list of violation strings for one architecture md (empty = clean)."""
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    violations = []

    # ---- rule 1: numbering ----
    numbers = []
    for ln, raw in enumerate(lines, start=1):
        m = SECTION_RE.match(raw)
        if not m:
            continue
        body = m.group(1).strip()
        nm = NUMBERED_RE.match(body)
        if nm:
            numbers.append((int(nm.group(1)), ln))
        else:
            violations.append(
                "L%d: 未编号浮动小节「%s」打断 §0–§N 序列（新增顶层小节必须编号）"
                % (ln, body[:40]))

    if numbers:
        seen = {}
        for num, ln in numbers:
            seen.setdefault(num, []).append(ln)
        nums = sorted(seen)
        # contiguous from 0 with no gaps
        expected = list(range(0, nums[-1] + 1))
        if nums != expected:
            missing = [n for n in expected if n not in seen]
            violations.append(
                "顶层章节序号不连续：实际 %s，缺 %s（必须从 0 连续）"
                % (nums, missing))
        dups = [n for n, ls in seen.items() if len(ls) > 1]
        if dups:
            violations.append(
                "顶层章节序号重复：%s" % [(n, seen[n]) for n in dups])

    # ---- rule 2: self-referential wording ----
    cleaned = _strip_illustrative("".join(lines))
    for pat in SELF_REF_PATTERNS:
        for m in pat.finditer(cleaned):
            start = max(0, m.start() - 20)
            snippet = cleaned[start:m.end() + 20].replace("\n", " ")
            violations.append("自指元注释命中「%s」：…%s…" % (m.group(0), snippet))

    return violations


def main():
    p = argparse.ArgumentParser(description="Structure lint for architecture/*.md.")
    p.add_argument("plan", help="plan root directory")
    p.add_argument("--file", help="lint a single architecture md (else all of them)")
    args = p.parse_args()

    if args.file:
        targets = [args.file]
    else:
        arch_dir = os.path.join(args.plan, "architecture")
        if not os.path.isdir(arch_dir):
            print("NO architecture/ dir at %s" % arch_dir)
            sys.exit(1)
        targets = [os.path.join(arch_dir, n)
                   for n in sorted(os.listdir(arch_dir))
                   if re.match(r"^\d+\.md$", n)]

    all_violations = {}
    for t in targets:
        v = lint_file(t)
        if v:
            all_violations[t] = v

    if not all_violations:
        print("STRUCTURE LINT OK — 无违规（%d 文件）" % len(targets))
        sys.exit(0)

    print("STRUCTURE LINT FAILED — 命中 %d 处违规："
          % sum(len(v) for v in all_violations.values()))
    for t, v in all_violations.items():
        print("  == %s ==" % os.path.relpath(t, args.plan))
        for line in v:
            print("    - " + line)
    sys.exit(1)


if __name__ == "__main__":
    main()
