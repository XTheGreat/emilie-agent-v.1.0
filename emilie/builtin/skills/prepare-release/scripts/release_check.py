#!/usr/bin/env python3
"""Release readiness brief (read-only): git state, last tag, commits since, version files, changelog, CI.

Usage: python release_check.py [path] [--json]
"""
from __future__ import annotations
import json, re, subprocess, sys
from pathlib import Path

def git(root, *a):
    r = subprocess.run(["git", "-C", str(root), *a], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""

VERSION_FILES = {
    "pyproject.toml": r'(?m)^version\s*=\s*"([^"]+)"', "setup.py": r'version\s*=\s*["\']([^"\']+)',
    "package.json": r'"version"\s*:\s*"([^"]+)"', "Cargo.toml": r'(?m)^version\s*=\s*"([^"]+)"',
    "VERSION": r'^\s*(\S+)', "composer.json": r'"version"\s*:\s*"([^"]+)"',
}

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    root = Path(args[0] if args else ".").resolve()
    out = {"root": str(root)}
    if not git(root, "rev-parse", "--git-dir"):
        print("not a git repository"); return 1
    out["branch"] = git(root, "branch", "--show-current")
    out["dirty_files"] = [l for l in git(root, "status", "--porcelain").splitlines()]
    out["upstream"] = git(root, "rev-list", "--left-right", "--count", "@{u}...HEAD") or "no upstream"
    tag = git(root, "describe", "--tags", "--abbrev=0")
    out["last_tag"] = tag or None
    rng = f"{tag}..HEAD" if tag else "HEAD"
    commits = git(root, "log", rng, "--pretty=%h %s").splitlines()
    kinds, breaking = {}, []
    for c in commits:
        m = re.match(r"\w+ (\w+)(\([^)]*\))?(!)?:", c)
        k = m.group(1) if m else "other"
        kinds[k] = kinds.get(k, 0) + 1
        if (m and m.group(3)) or "BREAKING" in c:
            breaking.append(c)
    out.update(commits_since=len(commits), by_type=kinds, breaking=breaking)
    vs = {}
    for f, rx in VERSION_FILES.items():
        p = root / f
        if p.is_file():
            m = re.search(rx, p.read_text(errors="ignore"))
            if m: vs[f] = m.group(1)
    out["versions"] = vs
    out["versions_agree"] = len(set(vs.values())) <= 1
    out["changelog"] = next((n for n in ("CHANGELOG.md", "CHANGELOG", "HISTORY.md", "NEWS.md") if (root / n).is_file()), None)
    out["ci"] = [str(p.relative_to(root)) for p in list((root / ".github/workflows").glob("*.y*ml")) + [root / ".gitlab-ci.yml"] if p.exists()]
    hint = "major" if breaking else "minor" if kinds.get("feat") else "patch" if commits else "nothing to release"
    out["suggested_bump"] = hint
    problems = []
    if out["dirty_files"]: problems.append("working tree not clean")
    if not out["versions_agree"]: problems.append("version files disagree")
    if not commits: problems.append("no commits since last tag")
    out["blockers"] = problems
    if "--json" in sys.argv: print(json.dumps(out, indent=2)); return 0
    for k, v in out.items(): print(f"{k}: {v}")
    print("\nVERDICT:", "NO-GO - " + "; ".join(problems) if problems else "ready for the test gate")
    return 0

if __name__ == "__main__": sys.exit(main())
