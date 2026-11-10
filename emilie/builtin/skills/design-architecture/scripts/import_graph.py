#!/usr/bin/env python3
"""Measure a project's internal import structure (Python, JavaScript, TypeScript).

Usage: python import_graph.py <project-root> [--top N] [--json]

Reports module count, import cycles, high fan-in and fan-out modules, and
coupling between top-level packages. Read-only; standard library only.

Limits (printed with the report): dynamic imports, path aliases (tsconfig
"paths", webpack aliases), generated code and non-relative JS specifiers that
resolve to local folders are only partly visible.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv", "env",
    ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build", "out",
    ".next", ".nuxt", ".cache", "coverage", "target", ".idea", ".vscode", "vendor",
    "site-packages", ".eggs", ".gradle",
}
PY_EXT = {".py"}
JS_EXT = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"}
MAX_FILE = 1_500_000
JS_IMPORT = re.compile(
    r"""(?:import\s+(?:[^'"()]*?\s+from\s+)?|export\s+[^'"()]*?\s+from\s+|require\(\s*|import\(\s*)['"]([^'"]+)['"]"""
)


def walk(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            p = Path(dirpath) / name
            if p.suffix in PY_EXT | JS_EXT:
                try:
                    if p.stat().st_size <= MAX_FILE:
                        yield p
                except OSError:
                    pass


def py_module_name(root: Path, p: Path) -> str:
    """Dotted name as Python would import it: climb while __init__.py exists.

    Handles src/ layouts (src/pkg/a.py -> pkg.a). Files outside any package
    keep their root-relative dotted path so same-named scripts do not collide.
    """
    parts = [p.stem] if p.stem != "__init__" else []
    d = p.parent
    top_reached = False
    while d != root and (d / "__init__.py").exists():
        parts.insert(0, d.name)
        d = d.parent
        top_reached = True
    if top_reached or d == root:
        return ".".join(parts)
    rel = p.relative_to(root).with_suffix("")
    rp = list(rel.parts)
    if rp[-1] == "__init__":
        rp = rp[:-1]
    return ".".join(rp)


def py_imports(p: Path, modname: str, known: set[str]) -> set[str]:
    try:
        tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, ValueError):
        return set()
    is_pkg = p.name == "__init__.py"
    pkg_parts = modname.split(".") if modname else []
    base = pkg_parts if is_pkg else pkg_parts[:-1]
    out: set[str] = set()

    def add(name: str):
        # Longest known prefix: "a.b.c" -> a.b.c, a.b or a
        parts = name.split(".")
        while parts:
            cand = ".".join(parts)
            if cand in known:
                out.add(cand)
                return
            parts.pop()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                up = base[: len(base) - (node.level - 1)] if node.level - 1 <= len(base) else []
                target = ".".join(up + ([node.module] if node.module else []))
            else:
                target = node.module or ""
            if not target and not node.level:
                continue
            for a in node.names:
                sub = f"{target}.{a.name}" if target else a.name
                if sub in known:
                    out.add(sub)
                else:
                    add(target)
    return out


def js_resolve(root: Path, src: Path, spec: str, files: set[Path]) -> Path | None:
    if not spec.startswith("."):
        return None
    base = (src.parent / spec).resolve()
    cands = [base]
    for ext in sorted(JS_EXT):
        cands.append(Path(str(base) + ext))
    for ext in sorted(JS_EXT):
        cands.append(base / ("index" + ext))
    # TS often imports "./x.js" for x.ts
    if base.suffix in {".js", ".jsx", ".mjs", ".cjs"}:
        stem = base.with_suffix("")
        for ext in (".ts", ".tsx", ".mts", ".cts"):
            cands.append(Path(str(stem) + ext))
    for c in cands:
        if c in files:
            return c
    return None


def tarjan(graph: dict[str, set[str]]) -> list[list[str]]:
    index = 0
    stack: list[str] = []
    on: set[str] = set()
    idx: dict[str, int] = {}
    low: dict[str, int] = {}
    sccs: list[list[str]] = []
    # iterative to avoid recursion limits
    for start in graph:
        if start in idx:
            continue
        work = [(start, iter(graph.get(start, ())))]
        idx[start] = low[start] = index
        index += 1
        stack.append(start)
        on.add(start)
        while work:
            v, it = work[-1]
            advanced = False
            for w in it:
                if w not in graph:
                    continue
                if w not in idx:
                    idx[w] = low[w] = index
                    index += 1
                    stack.append(w)
                    on.add(w)
                    work.append((w, iter(graph.get(w, ()))))
                    advanced = True
                    break
                elif w in on:
                    low[v] = min(low[v], idx[w])
            if advanced:
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[v])
            if low[v] == idx[v]:
                comp = []
                while True:
                    w = stack.pop()
                    on.discard(w)
                    comp.append(w)
                    if w == v:
                        break
                if len(comp) > 1 or v in graph.get(v, ()):
                    sccs.append(sorted(comp))
    return sorted(sccs, key=len, reverse=True)


def top_package(name: str, lang: str) -> str:
    if lang == "py":
        return name.split(".")[0] if name else "(root)"
    parts = name.split("/")
    return parts[0] if len(parts) > 1 else "(root)"


def build(root: Path):
    files = list(walk(root))
    graph: dict[str, set[str]] = {}
    lang_of: dict[str, str] = {}

    py_files = [p for p in files if p.suffix in PY_EXT]
    known = {py_module_name(root, p) for p in py_files}
    known.discard("")
    for p in py_files:
        m = py_module_name(root, p)
        if not m:
            continue
        graph[m] = py_imports(p, m, known) - {m}
        lang_of[m] = "py"

    js_files = [p for p in files if p.suffix in JS_EXT]
    jset = {p.resolve() for p in js_files}

    def jname(p: Path) -> str:
        return p.resolve().relative_to(root.resolve()).with_suffix("").as_posix()

    for p in js_files:
        n = jname(p)
        deps: set[str] = set()
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for spec in JS_IMPORT.findall(text):
            r = js_resolve(root, p, spec, jset)
            if r is not None:
                d = jname(r)
                if d != n:
                    deps.add(d)
        graph[n] = deps
        lang_of[n] = "js"
    return graph, lang_of


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    root = Path(a.root)
    if not root.is_dir():
        print(f"error: {a.root} is not a directory", file=sys.stderr)
        return 1
    root = root.resolve()
    graph, lang_of = build(root)
    if not graph:
        print("No Python or JavaScript/TypeScript source files found.")
        return 0

    fan_out = {m: len(d) for m, d in graph.items()}
    fan_in: dict[str, int] = defaultdict(int)
    importers: dict[str, list[str]] = defaultdict(list)
    for m, ds in graph.items():
        for d in ds:
            fan_in[d] += 1
            importers[d].append(m)
    cycles = tarjan(graph)

    pkg_edges: dict[tuple[str, str], int] = defaultdict(int)
    for m, ds in graph.items():
        for d in ds:
            pa, pb = top_package(m, lang_of[m]), top_package(d, lang_of[d])
            if pa != pb:
                pkg_edges[(pa, pb)] += 1
    pkg_pairs_mutual = sorted(
        {tuple(sorted(k)) for k in pkg_edges if (k[1], k[0]) in pkg_edges}
    )

    edges = sum(fan_out.values())
    result = {
        "modules": len(graph),
        "edges": edges,
        "languages": sorted(set(lang_of.values())),
        "cycles": cycles,
        "top_fan_in": sorted(((m, c) for m, c in fan_in.items()), key=lambda x: -x[1])[: a.top],
        "top_fan_out": sorted(fan_out.items(), key=lambda x: -x[1])[: a.top],
        "package_edges": [
            {"from": k[0], "to": k[1], "imports": v}
            for k, v in sorted(pkg_edges.items(), key=lambda kv: -kv[1])
        ],
        "mutual_package_pairs": [list(p) for p in pkg_pairs_mutual],
        "isolated": sorted(m for m in graph if not graph[m] and fan_in.get(m, 0) == 0)[: a.top],
    }
    if a.json:
        print(json.dumps(result, indent=2))
        return 0

    print(f"Project: {root}")
    print(f"Modules: {result['modules']} ({', '.join(result['languages'])}); internal imports: {edges}")
    print()
    print(f"Import cycles: {len(cycles)}")
    for c in cycles[: a.top]:
        shown = ", ".join(c[:8]) + (f", ... (+{len(c) - 8})" if len(c) > 8 else "")
        print(f"  - {len(c)} modules: {shown}")
    if not cycles:
        print("  none found")
    print()
    print("Most depended on (fan-in) - changes here ripple outward:")
    for m, c in result["top_fan_in"]:
        if c:
            print(f"  {c:4d}  {m}")
    print()
    print("Depends on the most (fan-out) - likely orchestrators or tangled code:")
    for m, c in result["top_fan_out"]:
        if c:
            print(f"  {c:4d}  {m}")
    print()
    if result["package_edges"]:
        print("Coupling between top-level packages (imports across the boundary):")
        for e in result["package_edges"][: a.top]:
            print(f"  {e['from']} -> {e['to']}: {e['imports']}")
    if pkg_pairs_mutual:
        print()
        print("Packages that import each other (boundary is not one-way):")
        for p in pkg_pairs_mutual[: a.top]:
            print(f"  {p[0]} <-> {p[1]}")
    print()
    print(
        "Limits: static imports only. Dynamic imports, path aliases (tsconfig paths, webpack),\n"
        "bare JS specifiers that map to local folders, and generated code are not followed."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
