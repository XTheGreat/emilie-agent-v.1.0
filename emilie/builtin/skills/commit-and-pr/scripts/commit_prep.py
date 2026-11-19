#!/usr/bin/env python3
"""Pre-commit brief (read-only): what is staged/unstaged/untracked, risky lines, and a suggested commit type.

Usage: python commit_prep.py [path] [--all]   (--all inspects unstaged changes too)
"""
from __future__ import annotations
import re, subprocess, sys
from pathlib import Path

def git(root, *a):
    r = subprocess.run(["git", "-C", str(root), *a], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""

SECRET = re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b|\bgh[pousr]_[A-Za-z0-9]{30,}\b|\bsk-[A-Za-z0-9_-]{32,}\b|-----BEGIN [A-Z ]*PRIVATE KEY-----|(?i:(password|secret|token|api[_-]?key)\s*[:=]\s*['\"][^'\"\s]{8,}['\"])")
LEFT = re.compile(r"\bconsole\.log\(|\bdebugger\b|\bprint\(\s*['\"]DEBUG|\bbreakpoint\(\)|\bpdb\.set_trace|\bTODO\b|\bFIXME\b|<<<<<<<|>>>>>>>")
BAD_FILES = re.compile(r"(^|/)(\.env[\w.]*|id_rsa|.*\.pem|.*\.key|.*\.p12|node_modules/|__pycache__/|.*\.pyc|.*\.log|\.DS_Store)$")

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    root = Path(args[0] if args else ".")
    if not git(root, "rev-parse", "--git-dir"): print("not a git repository"); return 1
    print("branch:", git(root, "branch", "--show-current").strip())
    status = git(root, "status", "--porcelain").splitlines()
    staged = [l[3:] for l in status if l[0] not in " ?"]
    unstaged = [l[3:] for l in status if l[1] not in " ?" ]
    untracked = [l[3:] for l in status if l.startswith("??")]
    print(f"staged {len(staged)}, unstaged {len(unstaged)}, untracked {len(untracked)}")
    diff = git(root, "diff", "--cached") + (git(root, "diff") if "--all" in sys.argv else "")
    stat = git(root, "diff", "--cached", "--shortstat").strip()
    print("size:", stat or "nothing staged")
    cur, n, findings = "", 0, []
    for line in diff.splitlines():
        if line.startswith("+++ b/"): cur = line[6:]
        elif line.startswith("@@"):
            m = re.search(r"\+(\d+)", line); n = int(m.group(1)) - 1 if m else 0
        elif line.startswith("+") and not line.startswith("+++"):
            n += 1
            if SECRET.search(line): findings.append(f"SECRET  {cur}:{n} (value hidden)")
            elif LEFT.search(line): findings.append(f"LEFTOVER {cur}:{n} {line[1:].strip()[:70]}")
        elif not line.startswith("-"): n += 1
    for f in staged + untracked:
        if BAD_FILES.search(f): findings.append(f"FILE    {f} should probably not be committed")
    print("\n".join(findings) if findings else "no risky lines found")
    files = staged or unstaged
    kind = "docs" if files and all(re.search(r"\.(md|rst|txt)$|^docs?/", f) for f in files) else \
           "test" if files and all(re.search(r"test", f) for f in files) else \
           "ci" if files and all(f.startswith((".github/", ".gitlab")) for f in files) else "feat/fix/refactor (read the diff)"
    print("suggested type:", kind)
    tops = {f.split("/")[0] for f in files}
    if len(tops) > 3: print("hint: touches", len(tops), "top-level areas - consider splitting into several commits")
    print("recent style:\n" + git(root, "log", "-5", "--pretty=  %s").rstrip())
    return 0

if __name__ == "__main__": sys.exit(main())
