#!/usr/bin/env python3
"""Find what is not tested: public functions/classes no test mentions, files without a test file, and coverage gaps.

Usage: python find_gaps.py [path] [--top 15] [--coverage FILE] [--json]

Heuristic, read-only, stdlib only:
  * Python (exact, via ast): public functions, methods and classes; a symbol counts as "referenced by a test" when its name
    appears as a whole word in any test file. Ranked by size x complexity, so the big untested logic comes first.
  * JS/TS/Go/Java/Rust/Ruby/PHP/C#: top-level symbols by regex, same whole-word rule (rougher).
  * Coverage: if --coverage points to a coverage.py XML (coverage.xml), an lcov file (lcov.info) or a Cobertura/JaCoCo-style
    XML, the lowest-covered files and their missing line ranges are listed. Generate one with your test runner first.

"Referenced" is NOT "well tested": a name mentioned in a test may only be imported. Use this list to decide where to look,
then read the tests. Limits: dynamic dispatch, fixtures that call code indirectly and names shared by many modules produce
false positives and negatives.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "env", "dist", "build", "out", ".next", "target", "vendor", "site-packages", ".tox", ".mypy_cache", ".pytest_cache", "coverage", "migrations", ".idea", ".vscode", "docs"}
CODE_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".go", ".java", ".kt", ".rs", ".rb", ".php", ".cs"}
TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec|e2e|cypress)(/|$)|\.(test|spec)\.[a-z]+$|_test\.(go|py|rb|rs)$|(^|/)test_[^/]*\.py$|Tests?\.(java|kt|cs)$|_spec\.rb$", re.I)
RX = {
    ".js": r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)|^\s*(?:export\s+)?(?:const|let)\s+(\w+)\s*=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*=>|^\s*(?:export\s+)?class\s+(\w+)",
    ".go": r"^func\s+(?:\([^)]*\)\s*)?([A-Z]\w*)\s*\(",
    ".java": r"^\s*(?:public|protected)\s+(?:static\s+)?(?:final\s+)?[\w<>\[\], ?]+\s+(\w+)\s*\([^;{]*\)\s*(?:throws [\w, .]+)?\s*\{",
    ".rs": r"^\s*pub\s+(?:async\s+)?fn\s+(\w+)",
    ".rb": r"^\s*def\s+(?:self\.)?([a-z]\w*[?!]?)",
    ".php": r"^\s*public\s+(?:static\s+)?function\s+(\w+)",
    ".cs": r"^\s*public\s+(?:static\s+)?(?:async\s+)?[\w<>\[\], ?]+\s+(\w+)\s*\(",
}
RX[".jsx"] = RX[".ts"] = RX[".tsx"] = RX[".mjs"] = RX[".js"]
RX[".kt"] = RX[".java"]
GENERIC_NAMES = {"main", "run", "get", "set", "init", "new", "create", "update", "delete", "handle", "execute", "setup", "close", "open", "start", "stop", "parse", "load", "save", "build", "index", "default", "constructor", "render", "to_string", "toString", "__init__", "__repr__", "__str__"}


def files(root: Path):
    if root.is_file():
        yield root
        return
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in SKIP_DIRS and not d.startswith(".")]
        for f in fn:
            p = Path(dp) / f
            if p.suffix in CODE_EXT and not f.endswith((".min.js", ".d.ts", "_pb2.py")):
                try:
                    if p.stat().st_size <= 1_000_000:
                        yield p
                except OSError:
                    pass


def py_symbols(text: str):
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []
    out = []

    def branches(n):
        c = 1
        for x in ast.walk(n):
            if isinstance(x, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.IfExp, ast.Assert, ast.comprehension)):
                c += 1
            elif isinstance(x, ast.BoolOp):
                c += len(x.values) - 1
        return c

    def visit(body, owner=""):
        for n in body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if n.name.startswith("_"):
                    continue
                size = (n.end_lineno or n.lineno) - n.lineno + 1
                out.append({"name": n.name, "qual": f"{owner}.{n.name}" if owner else n.name, "line": n.lineno, "size": size, "complexity": branches(n), "kind": "method" if owner else "function"})
            elif isinstance(n, ast.ClassDef) and not n.name.startswith("_"):
                size = (n.end_lineno or n.lineno) - n.lineno + 1
                out.append({"name": n.name, "qual": n.name, "line": n.lineno, "size": size, "complexity": 1, "kind": "class"})
                visit(n.body, n.name)
    visit(tree.body)
    return out


def rx_symbols(text: str, ext: str):
    rx = re.compile(RX[ext], re.M)
    out = []
    for m in rx.finditer(text):
        name = next((g for g in m.groups() if g), None)
        if name and name not in ("if", "for", "while", "switch", "catch", "return"):
            line = text.count("\n", 0, m.start()) + 1
            out.append({"name": name, "qual": name, "line": line, "size": 10, "complexity": 1, "kind": "function"})
    return out


def parse_coverage(path: Path):
    """Return {file: (percent, [missing line ranges])} from coverage.xml (Cobertura) or lcov."""
    text = path.read_text(encoding="utf-8", errors="replace")
    res: dict[str, tuple[float, list[tuple[int, int]]]] = {}

    def ranges(lines):
        lines = sorted(set(lines))
        out, start = [], None
        for i, n in enumerate(lines):
            if start is None:
                start = prev = n
            elif n == prev + 1:
                prev = n
            else:
                out.append((start, prev))
                start = prev = n
        if start is not None:
            out.append((start, prev))
        return out
    if text.lstrip().startswith("<"):
        root = ET.fromstring(text)
        for cls in root.iter("class"):
            fn = cls.get("filename", "")
            lines = [(int(l.get("number")), int(l.get("hits", "0"))) for l in cls.iter("line")]
            if lines:
                missing = [n for n, h in lines if h == 0]
                res[fn] = (100.0 * (len(lines) - len(missing)) / len(lines), ranges(missing))
    else:
        cur, hits = None, {}
        for line in text.splitlines():
            if line.startswith("SF:"):
                cur, hits = line[3:], {}
            elif line.startswith("DA:") and cur:
                n, h = line[3:].split(",")[:2]
                hits[int(n)] = int(h)
            elif line.startswith("end_of_record") and cur:
                if hits:
                    missing = [n for n, h in hits.items() if h == 0]
                    res[cur] = (100.0 * (len(hits) - len(missing)) / len(hits), ranges(missing))
                cur = None
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", nargs="?", default=".")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--coverage")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    root = Path(a.path).resolve()
    if not root.exists():
        print(f"error: {a.path} not found", file=sys.stderr)
        return 1
    base = root if root.is_dir() else root.parent
    src, tests = {}, {}
    for p in files(root):
        rel = p.relative_to(base).as_posix()
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        (tests if TEST_PATH.search(rel) else src)[rel] = text
    if not src:
        print("No source files found.")
        return 0
    test_blob = "\n".join(tests.values())
    words = set(re.findall(r"[A-Za-z_]\w*", test_blob))
    gaps = []
    total_syms = 0
    for rel, text in src.items():
        ext = Path(rel).suffix
        syms = py_symbols(text) if ext == ".py" else (rx_symbols(text, ext) if ext in RX else [])
        for s in syms:
            if s["name"] in GENERIC_NAMES and s["kind"] != "class":
                continue
            total_syms += 1
            if s["name"] not in words:
                gaps.append({**s, "file": rel, "score": s["size"] * s["complexity"]})
    gaps.sort(key=lambda x: -x["score"])
    stems = {Path(t).stem.lower().replace("test_", "").replace("_test", "").replace(".test", "").replace(".spec", "").replace("test", "") for t in tests}
    no_test_file = sorted(r for r in src if Path(r).stem.lower() not in stems and not Path(r).stem.startswith("_") and Path(r).stem not in ("__init__", "index", "main", "setup", "conftest"))
    cov = parse_coverage(Path(a.coverage)) if a.coverage and Path(a.coverage).is_file() else None
    result = {
        "source_files": len(src), "test_files": len(tests), "symbols_checked": total_syms, "untested_symbols": len(gaps),
        "top_gaps": [{k: g[k] for k in ("file", "qual", "line", "kind", "size", "complexity")} for g in gaps[: a.top]],
        "files_without_test_file": no_test_file[: a.top],
        "coverage": ({f: {"percent": round(p, 1), "missing": m[:6]} for f, (p, m) in sorted(cov.items(), key=lambda kv: kv[1][0])[: a.top]} if cov else None),
    }
    if a.json:
        print(json.dumps(result, indent=2))
        return 0
    print(f"Source files: {len(src)}  |  test files: {len(tests)}  |  public symbols checked: {total_syms}  |  not mentioned by any test: {len(gaps)}\n")
    if not tests:
        print("NO TEST FILES FOUND. Look for tests outside the scanned paths, or this project has none.\n")
    print("Biggest untested symbols (size x branches):")
    for g in gaps[: a.top]:
        print(f"  {g['file']}:{g['line']}  {g['qual']} ({g['kind']}, {g['size']} lines, {g['complexity']} branches)")
    if not gaps:
        print("  none (every public name is mentioned in a test)")
    print("\nSource files with no matching test file name:")
    for r in no_test_file[: a.top]:
        print(f"  {r}")
    if not no_test_file:
        print("  none")
    if cov:
        print("\nLowest coverage (from the coverage report):")
        for f, (pct, miss) in sorted(cov.items(), key=lambda kv: kv[1][0])[: a.top]:
            ms = ", ".join(f"{a_}-{b}" if a_ != b else str(a_) for a_, b in miss[:6]) + (" ..." if len(miss) > 6 else "")
            print(f"  {pct:5.1f}%  {f}   missing: {ms}")
    elif a.coverage:
        print(f"\n(coverage file {a.coverage} not found)")
    print("\n'Mentioned in a test' is not 'tested'. Read the tests for the top items before deciding what to write.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
