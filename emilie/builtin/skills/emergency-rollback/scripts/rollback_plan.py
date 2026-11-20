#!/usr/bin/env python3
"""Gather facts for a rollback decision (read-only): recent tags, commits since the last tag, migrations, dependency/config changes.

Usage: python rollback_plan.py [path] [--since REF]
"""
from __future__ import annotations
import re, subprocess, sys
from pathlib import Path

def git(root, *a):
    r = subprocess.run(["git", "-C", str(root), *a], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""

def main():
    argv = sys.argv[1:]; since = None
    if "--since" in argv: i = argv.index("--since"); since = argv[i + 1]; del argv[i:i + 2]
    root = Path(argv[0] if argv else ".")
    if not git(root, "rev-parse", "--git-dir"): print("not a git repository"); return 1
    print("HEAD:", git(root, "log", "-1", "--pretty=%h %s (%cr)"))
    tags = git(root, "tag", "--sort=-creatordate").splitlines()[:6]
    print("recent tags:", tags or "none")
    cur = git(root, "describe", "--tags", "--exact-match") or git(root, "describe", "--tags", "--abbrev=0")
    base = since or (tags[1] if len(tags) > 1 and cur == tags[0] else cur) or "HEAD~10"
    print(f"candidate last-good: {base}")
    files = git(root, "diff", "--name-status", f"{base}..HEAD").splitlines()
    print(f"\ncommits since {base}:\n" + (git(root, "log", f"{base}..HEAD", "--pretty=  %h %s (%an, %cr)", "--max-count=25") or "  none"))
    mig = [l for l in files if re.search(r"(migrat|alembic|flyway|db/|schema)", l, re.I)]
    dep = [l for l in files if re.search(r"(package(-lock)?\.json|requirements|poetry\.lock|pyproject|go\.(mod|sum)|Cargo\.(toml|lock)|Gemfile|pom\.xml)", l)]
    cfg = [l for l in files if re.search(r"(\.env|config|settings|\.ya?ml|Dockerfile|\.tf$|helm|k8s)", l, re.I)]
    for name, lst in (("MIGRATIONS (check reversibility before reverting code)", mig), ("dependency changes", dep), ("config/infra changes", cfg)):
        print(f"\n{name}: {len(lst)}"); [print("  " + l) for l in lst[:15]]
    destructive = [l for l in mig if l.startswith("D") or True]
    dropped = []
    for l in mig:
        f = l.split("\t")[-1]
        p = root / f
        if p.is_file() and re.search(r"(?i)\bdrop\s+(table|column)|rename\s+(column|to)|alter\s+column.*type|\.drop_column|\.remove_field", p.read_text(errors="ignore")): dropped.append(f)
    if dropped: print("\nDESTRUCTIVE-LOOKING migrations:", dropped, "-> rollback needs data owner approval")
    print("\nsuggested: revert to", base, "unless destructive migrations or irreversible data writes apply; show commands to the user before running.")
    return 0

if __name__ == "__main__": sys.exit(main())
