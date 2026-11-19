#!/usr/bin/env python3
"""Structural outline of a source file or folder (read-only).

Usage: python code_outline.py <file|dir> [--max-files 30]
Python: classes, functions, methods, docstring first line, line numbers, imports, __main__ guard. Other languages: regex-based declarations.
"""
from __future__ import annotations
import argparse, ast, re, sys
from pathlib import Path

SKIP = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", "vendor", "target"}
GENERIC = {
    ".js": r"^\s*(export\s+)?(async\s+)?(function\s+\w+|class\s+\w+|const\s+\w+\s*=\s*(async\s*)?\([^)]*\)\s*=>)", ".ts": None, ".tsx": None, ".jsx": None,
    ".go": r"^(func\s+(\([^)]*\)\s*)?\w+|type\s+\w+\s+(struct|interface))", ".rs": r"^\s*(pub\s+)?(fn|struct|enum|trait|impl)\s+\w+",
    ".java": r"^\s*(public|private|protected)?\s*(static\s+)?(class|interface|enum|[\w<>\[\]]+\s+\w+\s*\()", ".rb": r"^\s*(def|class|module)\s+\w+", ".php": r"^\s*(function|class|interface|trait)\s+\w+",
}
GENERIC[".ts"] = GENERIC[".tsx"] = GENERIC[".jsx"] = GENERIC[".js"]

def outline_py(p: Path):
    txt = p.read_text(errors="ignore")
    try: tree = ast.parse(txt)
    except SyntaxError as e: print(f"  syntax error line {e.lineno}"); return
    print(f"  lines: {len(txt.splitlines())}")
    imps = sorted({(n.module or "").split(".")[0] if isinstance(n, ast.ImportFrom) else a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in (n.names if isinstance(n, ast.Import) else [n])})
    print("  imports:", ", ".join(i for i in imps if i)[:200])
    def doc(n):
        d = ast.get_docstring(n); return f" - {d.splitlines()[0][:80]}" if d else ""
    def args(n): return ", ".join(a.arg for a in n.args.args)
    for n in tree.body:
        if isinstance(n, ast.ClassDef):
            print(f"  class {n.name} (L{n.lineno}){doc(n)}")
            for m in n.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)): print(f"    def {m.name}({args(m)}) L{m.lineno}-{m.end_lineno}{doc(m)}")
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            print(f"  {'async ' if isinstance(n, ast.AsyncFunctionDef) else ''}def {n.name}({args(n)}) L{n.lineno}-{n.end_lineno}{doc(n)}")
        elif isinstance(n, ast.If) and "__name__" in ast.dump(n.test): print(f"  entry point: if __name__ == '__main__' (L{n.lineno})")

def outline_generic(p: Path, rx):
    lines = p.read_text(errors="ignore").splitlines(); print(f"  lines: {len(lines)}")
    for i, l in enumerate(lines, 1):
        if re.match(rx, l): print(f"  L{i}: {l.strip()[:100]}")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("target"); ap.add_argument("--max-files", type=int, default=30); a = ap.parse_args()
    t = Path(a.target)
    if not t.exists(): print("not found:", t); return 1
    files = [t] if t.is_file() else sorted(p for p in t.rglob("*") if p.is_file() and p.suffix in ({".py"} | set(GENERIC)) and not (set(p.relative_to(t).parts) & SKIP))
    for p in files[:a.max_files]:
        print(f"\n{p}")
        if p.suffix == ".py": outline_py(p)
        elif p.suffix in GENERIC: outline_generic(p, GENERIC[p.suffix])
        else: print("  (unsupported type; read it directly)")
    if len(files) > a.max_files: print(f"\n... {len(files) - a.max_files} more files; narrow the target")
    return 0

if __name__ == "__main__": sys.exit(main())
