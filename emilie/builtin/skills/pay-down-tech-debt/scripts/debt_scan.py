#!/usr/bin/env python3
"""Technical debt hotspot scan (read-only, standard library).

Usage: python debt_scan.py [path] [--top 15] [--days 180]
Reports: biggest files, longest functions, markers (TODO/FIXME/HACK/XXX), skipped tests, commented-out code, git churn, and big+churning hotspots.
"""
from __future__ import annotations
import argparse, ast, re, subprocess, sys
from collections import Counter
from pathlib import Path

SKIP = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", "vendor", "target", ".next", "coverage"}
EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".java", ".kt", ".rb", ".php", ".rs", ".cs", ".c", ".cpp", ".swift", ".vue"}
MARK = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b")
SKIPPED = re.compile(r"@pytest\.mark\.skip|@unittest\.skip|\b(it|test|describe)\.skip\(|\bxit\(|\bxdescribe\(|t\.Skip\(|#\[ignore\]")
COMMENTED = re.compile(r"^\s*(#|//)\s*(def |class |if |for |while |return |import |from |const |let |var |function |\w+\s*=\s*\w+\(|\w+\(.*\);?$)")

def files(root):
    for p in root.rglob("*"):
        if p.suffix in EXT and p.is_file() and not (set(p.relative_to(root).parts) & SKIP): yield p

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("path", nargs="?", default="."); ap.add_argument("--top", type=int, default=15); ap.add_argument("--days", type=int, default=180)
    a = ap.parse_args(); root = Path(a.path).resolve()
    size, marks, skips, comm, longf = {}, Counter(), Counter(), Counter(), []
    for p in files(root):
        try: txt = p.read_text(errors="ignore")
        except OSError: continue
        lines = txt.splitlines(); rel = str(p.relative_to(root)); size[rel] = len(lines)
        for l in lines:
            if MARK.search(l): marks[rel] += 1
            if SKIPPED.search(l): skips[rel] += 1
            if COMMENTED.match(l): comm[rel] += 1
        if p.suffix == ".py":
            try:
                for n in ast.walk(ast.parse(txt)):
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.end_lineno - n.lineno > 60: longf.append((n.end_lineno - n.lineno, rel, n.lineno, n.name))
            except SyntaxError: pass
    print(f"files scanned: {len(size)}, lines: {sum(size.values())}")
    print("\nlargest files:"); [print(f"  {n:6} {f}") for f, n in sorted(size.items(), key=lambda x: -x[1])[:a.top]]
    print("\nlongest functions (>60 lines, python):"); [print(f"  {n:4} {f}:{ln} {nm}") for n, f, ln, nm in sorted(longf, reverse=True)[:a.top]] if longf else print("  none")
    print(f"\nmarkers: {sum(marks.values())} in {len(marks)} files; skipped tests: {sum(skips.values())}; commented-out code lines: {sum(comm.values())}")
    for f, n in marks.most_common(5): print(f"  markers {n:3} {f}")
    for f, n in skips.most_common(5): print(f"  skipped {n:3} {f}")
    r = subprocess.run(["git", "-C", str(root), "log", f"--since={a.days} days ago", "--name-only", "--pretty=format:"], capture_output=True, text=True)
    if r.returncode == 0:
        churn = Counter(l for l in r.stdout.splitlines() if l in size)
        print(f"\nmost changed files (last {a.days} days):"); [print(f"  {n:4} {f}") for f, n in churn.most_common(a.top)]
        hot = [(churn[f] * size[f] ** 0.5, f) for f in churn if size[f] > 300 and churn[f] >= 3]
        print("\nHOTSPOTS (big and changing - best payoff):"); [print(f"  {f}  ({churn[f]} changes, {size[f]} lines)") for _, f in sorted(hot, reverse=True)[:a.top]] if hot else print("  none")
    else: print("\n(no git history: churn analysis skipped)")
    return 0

if __name__ == "__main__": sys.exit(main())
