#!/usr/bin/env python3
"""Find refactoring candidates: complex functions, big files, duplicated blocks, and churn hotspots.

Usage: python hotspots.py [path] [--top N] [--since "12 months ago"] [--min-dup 8] [--json]

What it measures (read-only, stdlib only):
  * Python files (exact, via ast): per-function length, parameter count,
    nesting depth and cyclomatic complexity.
  * All text source files: size in lines, and duplicated blocks of at least
    --min-dup consecutive non-trivial lines (whitespace-normalized).
  * Git history: how often each file changed in the period (churn). A file
    that is both complex and frequently changed is the best place to refactor;
    complex code nobody touches can usually wait.

Thresholds are rules of thumb, not laws: function > 50 lines, > 5 parameters,
nesting > 4, cyclomatic > 10, file > 500 lines. Limits: non-Python languages
get size, duplication and churn only (no per-function metrics); generated and
vendored folders are skipped; duplicates are textual, not semantic.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "env", "dist", "build", "out", ".next", "target", "vendor", "site-packages", "coverage", ".tox", ".mypy_cache", ".pytest_cache", "migrations"}
EXTS = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".java", ".kt", ".go", ".rs", ".rb", ".php", ".cs", ".c", ".cc", ".cpp", ".h", ".hpp", ".swift", ".scala"}
LIMITS = {"length": 50, "params": 5, "nesting": 4, "cyclomatic": 10, "file": 500}
TRIVIAL = {"", "{", "}", "});", "};", ")", "]", "end", "else:", "else {", "} else {", "try:", "pass", "return", "break", "continue", "*/", "/*"}


def source_files(root: Path):
    if root.is_file():
        yield root
        return
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in SKIP_DIRS and not d.startswith(".")]
        for f in fn:
            p = Path(dp) / f
            if p.suffix in EXTS and not f.endswith((".min.js", ".d.ts", "_pb2.py", ".generated.ts")):
                try:
                    if p.stat().st_size <= 1_000_000:
                        yield p
                except OSError:
                    pass


def py_metrics(path: Path, text: str):
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []
    out = []
    branch = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.IfExp, ast.Assert)
    nest_nodes = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith)

    def depth(node, d=0):
        best = d
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                continue
            is_elif = isinstance(node, ast.If) and isinstance(ch, ast.If) and len(node.orelse) == 1 and node.orelse[0] is ch
            best = max(best, depth(ch, d + 1 if isinstance(ch, nest_nodes) and not is_elif else d))
        return best

    def cyclo(fn):
        c = 1
        stack = list(ast.iter_child_nodes(fn))
        while stack:
            n = stack.pop()
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            if isinstance(n, branch):
                c += 1
            elif isinstance(n, ast.BoolOp):
                c += len(n.values) - 1
            elif isinstance(n, ast.comprehension):
                c += 1 + len(n.ifs)
            elif hasattr(ast, "match_case") and isinstance(n, ast.match_case):
                c += 1
            stack.extend(ast.iter_child_nodes(n))
        return c

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = node.args
            names = [x.arg for x in a.posonlyargs + a.args + a.kwonlyargs]
            params = len([n for n in names if n not in ("self", "cls")]) + bool(a.vararg) + bool(a.kwarg)
            out.append({
                "name": node.name, "line": node.lineno, "length": (node.end_lineno or node.lineno) - node.lineno + 1,
                "params": params, "nesting": depth(node), "cyclomatic": cyclo(node),
            })
    return out


def norm_lines(text: str):
    res = []
    for i, line in enumerate(text.splitlines(), 1):
        s = " ".join(line.strip().split())
        if s in TRIVIAL or s.startswith(("#", "//", "import ", "from ", "using ", "package ", "use ", "require", "@")) or len(s) < 4:
            continue
        res.append((i, s))
    return res


def find_duplicates(files: dict[Path, str], min_len: int):
    W = min_len
    index: dict[str, list[tuple[Path, int]]] = defaultdict(list)
    seqs: dict[Path, list[tuple[int, str]]] = {}
    for p, text in files.items():
        seq = norm_lines(text)
        seqs[p] = seq
        for i in range(len(seq) - W + 1):
            h = hashlib.md5("\n".join(s for _, s in seq[i : i + W]).encode()).hexdigest()
            index[h].append((p, i))
    seen = set()
    blocks = []
    for h, occ in index.items():
        if len(occ) < 2:
            continue
        for a in range(len(occ)):
            for b in range(a + 1, len(occ)):
                (pa, ia), (pb, ib) = occ[a], occ[b]
                if pa == pb and abs(ia - ib) < W:
                    continue
                if (pa, ia - 1, pb, ib - 1) in seen:
                    continue  # part of a block already extended from an earlier start
                length = W
                while ia + length < len(seqs[pa]) and ib + length < len(seqs[pb]) and seqs[pa][ia + length][1] == seqs[pb][ib + length][1]:
                    length += 1
                for k in range(length - W + 1):
                    seen.add((pa, ia + k, pb, ib + k))
                blocks.append({
                    "lines": length,
                    "a": (pa, seqs[pa][ia][0], seqs[pa][ia + length - 1][0]),
                    "b": (pb, seqs[pb][ib][0], seqs[pb][ib + length - 1][0]),
                })
    blocks.sort(key=lambda x: -x["lines"])
    uniq, covered = [], set()
    for bl in blocks:
        key = (bl["a"][0], bl["a"][1], bl["b"][0], bl["b"][1])
        rkey = (bl["b"][0], bl["b"][1], bl["a"][0], bl["a"][1])
        if key in covered or rkey in covered:
            continue
        covered.add(key)
        uniq.append(bl)
    return uniq


def churn(root: Path, since: str):
    base = root if root.is_dir() else root.parent
    try:
        r = subprocess.run(["git", "-C", str(base), "log", f"--since={since}", "--name-only", "--format=", "--no-renames"],
                           capture_output=True, text=True, timeout=60)
        top = subprocess.run(["git", "-C", str(base), "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None, None
    if r.returncode != 0 or not top:
        return None, None
    c = Counter(l.strip() for l in r.stdout.splitlines() if l.strip())
    return c, Path(top)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", nargs="?", default=".")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--since", default="12 months ago")
    ap.add_argument("--min-dup", type=int, default=8)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    root = Path(a.path).resolve()
    if not root.exists():
        print(f"error: {a.path} not found", file=sys.stderr)
        return 1
    texts: dict[Path, str] = {}
    for p in source_files(root):
        try:
            texts[p] = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass
    if not texts:
        print("No source files found.")
        return 0

    funcs, files = [], []
    for p, t in texts.items():
        n = t.count("\n") + 1
        files.append({"file": p, "lines": n})
        if p.suffix == ".py":
            for m in py_metrics(p, t):
                m["file"] = p
                funcs.append(m)
    ch, top = churn(root, a.since)

    def rel(p: Path) -> str:
        try:
            return p.relative_to(root if root.is_dir() else root.parent).as_posix()
        except ValueError:
            return str(p)

    def churn_of(p: Path) -> int:
        if not ch or not top:
            return 0
        try:
            return ch.get(p.relative_to(top).as_posix(), 0)
        except ValueError:
            return 0

    flagged = []
    for f in funcs:
        why = [f"{k} {f[k]}" for k in ("length", "params", "nesting", "cyclomatic") if f[k] > LIMITS[k]]
        if why:
            flagged.append({**f, "why": why, "score": f["cyclomatic"] + f["length"] / 10 + f["nesting"]})
    flagged.sort(key=lambda x: -x["score"])
    big = sorted([f for f in files if f["lines"] > LIMITS["file"]], key=lambda x: -x["lines"])
    dups = find_duplicates(texts, a.min_dup)
    # hotspot = churn x complexity-ish size
    comp: dict[Path, float] = defaultdict(float)
    for f in funcs:
        comp[f["file"]] += f["cyclomatic"]
    for f in files:
        if f["file"].suffix != ".py":
            comp[f["file"]] = f["lines"] / 20
    hot = sorted(((churn_of(p), p, comp[p]) for p in texts if churn_of(p) and comp[p]), key=lambda x: -(x[0] * x[2]))

    if a.json:
        print(json.dumps({
            "complex_functions": [{**{k: v for k, v in f.items() if k != "file"}, "file": rel(f["file"])} for f in flagged[: a.top]],
            "large_files": [{"file": rel(f["file"]), "lines": f["lines"]} for f in big[: a.top]],
            "duplicates": [{"lines": d["lines"], "a": [rel(d["a"][0]), d["a"][1], d["a"][2]], "b": [rel(d["b"][0]), d["b"][1], d["b"][2]]} for d in dups[: a.top]],
            "hotspots": [{"file": rel(p), "changes": c, "complexity": round(k, 1)} for c, p, k in hot[: a.top]],
        }, indent=2))
        return 0

    print(f"Scanned {len(texts)} source files, {len(funcs)} Python functions. Churn period: {a.since if ch is not None else 'n/a (no git history)'}.\n")
    print("Hotspots (changed often AND complex - refactor these first):")
    if hot:
        for c, p, k in hot[: a.top]:
            print(f"  {c:4d} changes  complexity {k:6.1f}  {rel(p)}")
    else:
        print("  none (no git history, or nothing changed in the period)")
    print("\nComplex functions (Python):")
    for f in flagged[: a.top]:
        print(f"  {rel(f['file'])}:{f['line']}  {f['name']}()  " + ", ".join(f["why"]))
    if not flagged:
        print("  none over the thresholds" + ("" if funcs else " (no Python files: no per-function metrics for other languages)"))
    print("\nLarge files (> %d lines):" % LIMITS["file"])
    for f in big[: a.top]:
        print(f"  {f['lines']:5d}  {rel(f['file'])}")
    if not big:
        print("  none")
    print(f"\nDuplicated blocks (>= {a.min_dup} similar lines):")
    for d in dups[: a.top]:
        print(f"  {d['lines']:3d} lines: {rel(d['a'][0])}:{d['a'][1]}-{d['a'][2]}  ~  {rel(d['b'][0])}:{d['b'][1]}-{d['b'][2]}")
    if not dups:
        print("  none")
    print("\nThese are leads, not orders. Before refactoring: make sure tests cover the code (or add characterization tests first).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
