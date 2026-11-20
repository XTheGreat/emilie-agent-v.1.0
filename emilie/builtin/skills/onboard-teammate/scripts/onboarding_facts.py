#!/usr/bin/env python3
"""Collect onboarding facts (read-only): stack, layout, commands, docs, CI, git conventions, active areas.

Usage: python onboarding_facts.py [path]
"""
from __future__ import annotations
import json, re, subprocess, sys
from collections import Counter
from pathlib import Path

SKIP = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", "vendor", "target"}

def git(root, *a):
    r = subprocess.run(["git", "-C", str(root), *a], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""

def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    print("project:", root.name)
    ext = Counter(p.suffix for p in root.rglob("*") if p.is_file() and p.suffix and not (set(p.relative_to(root).parts) & SKIP))
    print("top file types:", ext.most_common(6))
    print("top-level:", sorted(p.name + ("/" if p.is_dir() else "") for p in root.iterdir() if p.name not in SKIP and not p.name.startswith(".git"))[:40])
    cmds = {}
    pj = root / "package.json"
    if pj.is_file():
        try: cmds.update({f"npm run {k}": v for k, v in json.loads(pj.read_text()).get("scripts", {}).items()})
        except ValueError: pass
    mk = root / "Makefile"
    if mk.is_file(): cmds.update({f"make {t}": "Makefile target" for t in re.findall(r"(?m)^([a-zA-Z][\w-]*):", mk.read_text(errors="ignore"))[:12]})
    pp = root / "pyproject.toml"
    if pp.is_file():
        t = pp.read_text(errors="ignore")
        for m in re.finditer(r'(?m)^([\w-]+)\s*=\s*"([\w.]+:[\w.]+)"', t): cmds[f"entry point: {m.group(1)}"] = m.group(2)
        cmds["python tests"] = "pytest" if "pytest" in t or (root / "tests").is_dir() else "see docs"
    print("commands:"); [print(f"  {k}: {v}") for k, v in list(cmds.items())[:25]]
    docs = [p.name for p in root.iterdir() if re.match(r"(README|CONTRIBUTING|CHANGELOG|ARCHITECTURE|SECURITY|LICENSE|CODEOWNERS)", p.name, re.I)]
    print("docs:", docs, "| docs/ dir:", (root / "docs").is_dir(), "| env example:", any((root / n).exists() for n in (".env.example", ".env.sample", "env.example")))
    print("CI:", [str(p.relative_to(root)) for p in list((root / ".github/workflows").glob("*.y*ml")) + [q for q in (root / ".gitlab-ci.yml",) if q.exists()]] or "none")
    if git(root, "rev-parse", "--git-dir"):
        subs = git(root, "log", "-100", "--pretty=%s").splitlines()
        conv = sum(bool(re.match(r"\w+(\([^)]*\))?!?:", s)) for s in subs)
        print(f"commit style: {'Conventional Commits' if subs and conv / len(subs) > .5 else 'free-form'} ({conv}/{len(subs)} of last 100)")
        print("branches:", git(root, "branch", "-r", "--format=%(refname:short)").splitlines()[:8])
        areas = Counter()
        for l in git(root, "log", "--since=90 days ago", "--name-only", "--pretty=format:").splitlines():
            if l: areas[l.split("/")[0]] += 1
        print("most active areas (90d):", areas.most_common(6))
        print("top contributors (90d):", [n for n in git(root, "shortlog", "-sn", "--since=90 days ago", "HEAD").splitlines()[:5]])
    todo = 0
    for p in root.rglob("*"):
        if p.is_file() and p.suffix in {".py", ".js", ".ts", ".go", ".rs", ".java"} and not (set(p.relative_to(root).parts) & SKIP):
            todo += len(re.findall(r"\b(TODO|FIXME)\b", p.read_text(errors="ignore")))
    print("TODO/FIXME markers (first-task candidates):", todo)
    return 0

if __name__ == "__main__": sys.exit(main())
