#!/usr/bin/env python3
"""Find documentation gaps (read-only): README sections, undocumented public Python API, undocumented CLI flags / env vars, broken links.

Usage: python doc_gaps.py [path]
"""
from __future__ import annotations
import ast, re, sys
from pathlib import Path

SKIP = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", "vendor", "tests", "test"}

def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    docs = [p for p in root.rglob("*.md") if not (set(p.relative_to(root).parts) & SKIP)] + [p for p in root.rglob("*.rst") if not (set(p.relative_to(root).parts) & SKIP)]
    doc_text = "\n".join(p.read_text(errors="ignore") for p in docs)
    readme = next((p for p in root.glob("README*")), None)
    print("README:", readme.name if readme else "MISSING")
    if readme:
        t = readme.read_text(errors="ignore").lower()
        for sec, kws in {"install": ("install", "setup"), "usage": ("usage", "quick start", "getting started"), "configuration": ("config", "environment"), "development": ("develop", "contribut", "test"), "license": ("license",)}.items():
            if not any(k in t for k in kws): print(f"  missing section: {sec}")
        print(f"  length: {len(t.splitlines())} lines")
    undocumented, flags, envs = [], set(), set()
    for p in root.rglob("*.py"):
        if set(p.relative_to(root).parts) & SKIP: continue
        txt = p.read_text(errors="ignore")
        for m in re.finditer(r"""add_argument\(\s*['"](--[\w-]+)""", txt): flags.add(m.group(1))
        for m in re.finditer(r"""(?:environ(?:\.get)?\s*[\[(]|getenv\()\s*['"]([A-Z][A-Z0-9_]{2,})""", txt): envs.add(m.group(1))
        try: tree = ast.parse(txt)
        except SyntaxError: continue
        for n in tree.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not n.name.startswith("_") and not ast.get_docstring(n):
                undocumented.append(f"{p.relative_to(root)}:{n.lineno} {n.name}")
    print(f"\nundocumented public functions/classes: {len(undocumented)}"); [print("  " + u) for u in undocumented[:15]]
    mf = sorted(f for f in flags if f not in doc_text); me = sorted(e for e in envs if e not in doc_text)
    print(f"\nCLI flags not in docs ({len(mf)}/{len(flags)}):", mf[:20]); print(f"env vars not in docs ({len(me)}/{len(envs)}):", me[:20])
    broken = []
    for p in docs:
        for m in re.finditer(r"\]\((?!https?://|#|mailto:)([^)\s#]+)", p.read_text(errors="ignore")):
            if not (p.parent / m.group(1)).exists(): broken.append(f"{p.relative_to(root)} -> {m.group(1)}")
    print(f"\nbroken relative links: {len(broken)}"); [print("  " + b) for b in broken[:15]]
    return 0

if __name__ == "__main__": sys.exit(main())
