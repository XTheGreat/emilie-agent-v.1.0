#!/usr/bin/env python3
"""Estimate the blast radius of a change: what it touches, who depends on it, what is untested, what usually changes with it.

Usage:
  python change_impact.py                 # working tree vs HEAD
  python change_impact.py --staged
  python change_impact.py main...HEAD [--history 300] [--top 15] [--json] [--cwd DIR]

For every changed file it finds the changed symbols (functions, methods, classes - exact for Python via ast, from git's hunk
context for other languages), then searches the repository for those names: callers, tests, other mentions. It also reads the git
history: files that usually change together with the changed ones but are NOT in this change, how often the changed files were
touched by fix/revert commits, and how many authors touch them.

Output feeds a deep review: a list of the riskiest symbols (many callers, no test mention), files to read next, and "did you forget
to change X?" prompts. Read-only (git diff / git grep / git log), standard library only.

Limits: name-based search finds mentions, not real call relationships (common names give false hits; dynamic dispatch and
reflection are invisible). History heuristics need enough commits to mean anything.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec|e2e|cypress)(/|$)|\.(test|spec)\.[a-z]+$|_test\.(go|py|rb|rs)$|(^|/)test_[^/]*\.py$|Tests?\.(java|kt|cs)$|_spec\.rb$", re.I)
CODE_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".go", ".java", ".kt", ".rs", ".rb", ".php", ".cs", ".c", ".cc", ".cpp", ".h", ".hpp", ".swift", ".scala"}
NAME_RX = re.compile(r"(?:function\*?\s+|def\s+|class\s+|fn\s+|func\s+(?:\([^)]*\)\s*)?|interface\s+|struct\s+|impl\s+|(?:public|private|protected|static|async|final)\s+[\w<>\[\], ?]*?\s)(\w+)\s*[(<{:]|(\w+)\s*[:=]\s*(?:async\s*)?(?:function|\([^)]*\)\s*=>)")
GENERIC = {"main", "run", "get", "set", "init", "new", "create", "update", "delete", "handle", "setup", "close", "open", "start", "stop", "parse", "load", "save", "build", "index", "default", "constructor", "render", "test", "call", "apply", "process", "execute", "__init__", "if", "for", "while", "switch", "return", "catch"}


def git(args: list[str], cwd: str | None) -> tuple[int, str]:
    try:
        r = subprocess.run(["git", *args], capture_output=True, cwd=cwd, timeout=180)
    except (OSError, subprocess.SubprocessError) as e:
        return 127, str(e)
    return r.returncode, r.stdout.decode("utf-8", errors="replace")


def parse(diff: str):
    """{path: {"changed": [new line numbers], "ctx": [hunk context strings], "status": ...}}"""
    out: dict[str, dict] = {}
    cur = None
    ln = 0
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            m = re.match(r"diff --git a/.* b/(.*)$", line)
            cur = out.setdefault(m.group(1), {"changed": [], "ctx": [], "status": "modified", "removed": 0}) if m else None
        elif cur is None:
            continue
        elif line.startswith("new file mode"):
            cur["status"] = "added"
        elif line.startswith("deleted file mode"):
            cur["status"] = "deleted"
        elif line.startswith("@@"):
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@\s*(.*)$", line)
            if m:
                ln = int(m.group(1))
                if m.group(3):
                    cur["ctx"].append(m.group(3))
        elif line.startswith("+") and not line.startswith("+++"):
            cur["changed"].append(ln)
            ln += 1
        elif line.startswith("-") and not line.startswith("---"):
            cur["removed"] += 1
    return out


def py_symbols_at(text: str, lines: list[int]) -> set[str]:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return set()
    spans = []
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            spans.append((n.lineno, n.end_lineno or n.lineno, n.name))
    found: set[str] = set()
    for ln in lines:
        inner = [s for s in spans if s[0] <= ln <= s[1]]
        if inner:
            found.add(min(inner, key=lambda s: s[1] - s[0])[2])          # innermost enclosing def/class
    return found


def symbols_from_context(ctx: list[str]) -> set[str]:
    out = set()
    for c in ctx:
        m = NAME_RX.search(c)
        if m:
            out.add(next(g for g in m.groups() if g))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("range", nargs="?", default="")
    ap.add_argument("--staged", action="store_true")
    ap.add_argument("--history", type=int, default=300)
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--cwd", default=None)
    a = ap.parse_args()
    rc, top = git(["rev-parse", "--show-toplevel"], a.cwd)
    if rc != 0:
        print("error: not inside a git repository", file=sys.stderr)
        return 1
    root = top.strip()
    base = ["diff", "-U0", "--no-color", "--no-ext-diff", "--find-renames"]
    if a.range:
        args = base + [a.range]
    elif a.staged:
        args = base + ["--cached"]
    else:
        rc, _ = git(["rev-parse", "--verify", "HEAD"], root)
        args = base + (["HEAD"] if rc == 0 else ["--cached"])
    rc, text = git(args, root)
    if rc != 0:
        print("error: git diff failed", file=sys.stderr)
        return 1
    changes = parse(text)
    if not changes:
        print("No changes found.")
        return 0
    changed_files = set(changes)

    # ---- symbols per file
    sym_by_file: dict[str, set[str]] = {}
    for f, d in changes.items():
        if Path(f).suffix not in CODE_EXT or d["status"] == "deleted":
            continue
        syms = set()
        if f.endswith(".py"):
            try:
                src = (Path(root) / f).read_text(encoding="utf-8", errors="replace")
                syms = py_symbols_at(src, d["changed"])
            except OSError:
                pass
        syms |= symbols_from_context(d["ctx"])
        sym_by_file[f] = {s for s in syms if s not in GENERIC and len(s) > 2}

    # ---- mentions of each symbol
    usage = []
    for f, syms in sym_by_file.items():
        for s in sorted(syms):
            rc, out = git(["grep", "-n", "-w", "-I", "-e", s, "--", "."], root)
            callers, tests, other = set(), set(), set()
            for hit in out.splitlines():
                p = hit.split(":", 2)
                if len(p) < 3:
                    continue
                path = p[0]
                if path == f and re.match(r"\s*(def|class|function|fn|func)\b", p[2]):
                    continue
                if TEST_PATH.search(path):
                    tests.add(path)
                elif path == f:
                    other.add(path)
                elif Path(path).suffix in CODE_EXT:
                    callers.add(path)
                else:
                    other.add(path)
            usage.append({"file": f, "symbol": s, "caller_files": sorted(callers), "test_files": sorted(tests), "other": sorted(other)})
    usage.sort(key=lambda u: (-(len(u["caller_files"]) * (2 if not u["test_files"] else 1)), u["file"]))

    # ---- history
    rc, log = git(["log", f"-n{a.history}", "--name-only", "--format=%x00%H%x01%an%x01%s", "--no-renames"], root)
    commits = []
    for chunk in log.split("\x00"):
        if not chunk.strip():
            continue
        head, _, files = chunk.partition("\n")
        parts = head.split("\x01")
        if len(parts) < 3:
            continue
        commits.append({"author": parts[1], "subject": parts[2], "files": {x.strip() for x in files.splitlines() if x.strip()}})
    touches = Counter()
    pair = Counter()
    fixes = Counter()
    authors = defaultdict(set)
    for c in commits:
        fs = c["files"] & changed_files
        for f in fs:
            touches[f] += 1
            authors[f].add(c["author"])
            if re.search(r"\b(fix|bug|hotfix|revert|regress|crash|patch)\w*", c["subject"], re.I):
                fixes[f] += 1
        if len(c["files"]) <= 40:
            for f in fs:
                for g in c["files"] - changed_files:
                    pair[(f, g)] += 1
    partners = []
    for (f, g), n in pair.items():
        if touches[f] >= 3 and n >= 3 and n / touches[f] >= 0.4 and (Path(root) / g).exists():
            partners.append({"changed": f, "usually_with": g, "together": n, "of": touches[f]})
    partners.sort(key=lambda x: (-x["together"] / x["of"], -x["together"]))
    risky = [{"file": f, "commits": touches[f], "fix_commits": fixes[f], "authors": len(authors[f])} for f in changes if touches[f]]
    risky.sort(key=lambda r: (-(r["fix_commits"] * 2 + r["commits"]), r["file"]))

    kinds = Counter("tests" if TEST_PATH.search(f) else "source" for f in changed_files)
    result = {"files": len(changed_files), "kinds": dict(kinds), "symbols": usage[: a.top * 2], "partners": partners[: a.top],
              "history": risky[: a.top], "history_commits": len(commits)}
    if a.json:
        print(json.dumps(result, indent=2))
        return 0

    print(f"Change impact: {len(changed_files)} file(s) ({kinds.get('source', 0)} source, {kinds.get('tests', 0)} test); history window: {len(commits)} commits\n")
    print("Changed symbols and where they are mentioned (callers = other source files; sorted by risk):")
    if not usage:
        print("  no named symbols found (config/docs only, or a language without recognizable definitions)")
    for u in usage[: a.top]:
        flag = "  <-- NO TEST MENTIONS" if not u["test_files"] and u["caller_files"] else ""
        print(f"  {u['symbol']:<28} {u['file']}\n      callers: {len(u['caller_files'])} file(s)  tests: {len(u['test_files'])} file(s){flag}")
        for c in u["caller_files"][:4]:
            print(f"        - {c}")
        if len(u["caller_files"]) > 4:
            print(f"        ... {len(u['caller_files']) - 4} more")
    if len(usage) > a.top:
        print(f"  ... {len(usage) - a.top} more symbol(s)")
    print("\nUsually changed together with these files, but NOT in this change (forgotten update?):")
    for p in partners[: a.top]:
        print(f"  {p['changed']}  ->  {p['usually_with']}   ({p['together']} of {p['of']} commits)")
    if not partners:
        print("  none found")
    print("\nHistory of the changed files (recent commits; fix = subject mentions fix/bug/revert/...):")
    for r in risky[: a.top]:
        print(f"  {r['file']}: {r['commits']} commits, {r['fix_commits']} fix-like, {r['authors']} author(s)")
    if not risky:
        print("  no history for these files (new files or a very young repository)")
    print("\nNext: read the callers listed above, check the untested symbols first, then the partner files. This is a map: confirm by reading the code.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
