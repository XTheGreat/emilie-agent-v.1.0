#!/usr/bin/env python3
"""Size a migration and track its progress by counting old vs new API usage.

Usage:
  python usage_inventory.py --old PATTERN [--old PATTERN ...] [--new PATTERN ...]
                            [path] [--literal] [--ext .py,.js] [--samples 3] [--top 15] [--json]

  --old / --new   regex (or plain text with --literal) matched per line.
                  Repeat the flag for several patterns.
  path            folder to scan (default: current directory)

Prints: total hits and files for the OLD pattern(s), the distinct forms found
(the matched text, grouped), the files with the most hits, a few sample lines,
and - when --new is given - the share already migrated. Re-run it after each
batch of work to see progress; a migration is done when OLD reaches 0 (and the
last run shows no hits in tests, docs and config too).

Read-only, stdlib only. Textual search: it cannot see dynamic access (getattr,
string-built names, reflection), generated code or usages in files outside the
scanned extensions, so search those by hand before declaring the old API gone.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "env", "dist", "build", "out", ".next", "target", "vendor", "site-packages", ".tox", ".mypy_cache", ".pytest_cache", "coverage", ".idea", ".vscode"}
DEFAULT_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte", ".java", ".kt", ".go", ".rs", ".rb", ".php", ".cs", ".swift", ".scala", ".c", ".cc", ".cpp", ".h", ".hpp",
               ".html", ".htm", ".css", ".scss", ".sql", ".json", ".yaml", ".yml", ".toml", ".md", ".txt", ".cfg", ".ini", ".xml", ".gradle", ".sh", ".ps1"}


def compile_all(pats: list[str], literal: bool, flags: int):
    out = []
    for p in pats:
        try:
            out.append(re.compile(re.escape(p) if literal else p, flags))
        except re.error as e:
            print(f"error: bad pattern {p!r}: {e}", file=sys.stderr)
            sys.exit(1)
    return out


def classify(rel: str) -> str:
    low = rel.lower()
    if re.search(r"(^|/)(tests?|__tests__|spec|e2e)(/|$)|\.(test|spec)\.|_test\.", low):
        return "tests"
    if low.endswith((".md", ".txt", ".rst")) or low.startswith("docs/"):
        return "docs"
    if low.endswith((".json", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".xml", ".gradle", ".lock")):
        return "config"
    return "source"


def scan(root: Path, olds, news, exts):
    res = {"old": defaultdict(list), "new": defaultdict(list)}
    forms = {"old": Counter(), "new": Counter()}
    scanned = 0
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in SKIP_DIRS and not d.startswith(".")]
        for f in fn:
            p = Path(dp) / f
            if p.suffix.lower() not in exts or f.endswith((".min.js", ".lock", "-lock.json")) or f == "package-lock.json":
                continue
            try:
                if p.stat().st_size > 1_500_000:
                    continue
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            scanned += 1
            rel = p.relative_to(root).as_posix()
            for i, line in enumerate(text.splitlines(), 1):
                for kind, pats in (("old", olds), ("new", news)):
                    for rx in pats:
                        m = rx.search(line)
                        if m:
                            res[kind][rel].append((i, line.strip()[:140]))
                            forms[kind][m.group(0)[:60]] += 1
                            break
    return res, forms, scanned


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", nargs="?", default=".")
    ap.add_argument("--old", action="append", default=[])
    ap.add_argument("--new", action="append", default=[])
    ap.add_argument("--literal", action="store_true")
    ap.add_argument("--ignore-case", "-i", action="store_true")
    ap.add_argument("--ext", default="")
    ap.add_argument("--samples", type=int, default=3)
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if not a.old:
        ap.error("give at least one --old pattern")
    root = Path(a.path).resolve()
    if not root.is_dir():
        print(f"error: {a.path} is not a directory", file=sys.stderr)
        return 1
    exts = {e if e.startswith(".") else "." + e for e in a.ext.split(",") if e} or DEFAULT_EXT
    flags = re.I if a.ignore_case else 0
    res, forms, scanned = scan(root, compile_all(a.old, a.literal, flags), compile_all(a.new, a.literal, flags), exts)
    old_hits = sum(len(v) for v in res["old"].values())
    new_hits = sum(len(v) for v in res["new"].values())
    by_class = Counter()
    for rel, hits in res["old"].items():
        by_class[classify(rel)] += len(hits)

    if a.json:
        print(json.dumps({
            "scanned_files": scanned, "old_hits": old_hits, "old_files": len(res["old"]), "new_hits": new_hits, "new_files": len(res["new"]),
            "old_by_kind": dict(by_class), "forms": forms["old"].most_common(a.top),
            "files": {r: len(h) for r, h in sorted(res["old"].items(), key=lambda kv: -len(kv[1]))[: a.top]},
        }, indent=2))
        return 0

    print(f"Scanned {scanned} files under {root}\n")
    print(f"OLD usage: {old_hits} hit(s) in {len(res['old'])} file(s)" + (f"   [{', '.join(f'{k} {v}' for k, v in by_class.most_common())}]" if old_hits else ""))
    if a.new:
        print(f"NEW usage: {new_hits} hit(s) in {len(res['new'])} file(s)")
        tot = old_hits + new_hits
        if tot:
            print(f"Progress: {100 * new_hits / tot:.0f}% of occurrences use the new form ({old_hits} left)")
    if old_hits:
        print("\nDistinct forms of the old usage (each may need its own replacement rule):")
        for text, n in forms["old"].most_common(a.top):
            print(f"  {n:5d}  {text}")
        print("\nFiles with the most old usage:")
        ranked = sorted(res["old"].items(), key=lambda kv: -len(kv[1]))
        for rel, hits in ranked[: a.top]:
            print(f"  {len(hits):4d}  {rel}")
            for ln, txt in hits[: a.samples]:
                print(f"          {ln}: {txt}")
        if len(ranked) > a.top:
            print(f"  ... and {len(ranked) - a.top} more file(s)")
    else:
        print("\nNo old usage found in the scanned files. Before calling it done, also check: dynamic access (getattr, string-built names),")
        print("generated code, files with other extensions, build configs, docs and deployment scripts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
