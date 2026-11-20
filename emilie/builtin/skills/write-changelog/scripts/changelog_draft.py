#!/usr/bin/env python3
"""Draft changelog entries from git history (read-only).

Usage: python changelog_draft.py [--since TAG] [--until REF] [--version X.Y.Z] [--repo PATH]
Groups Conventional Commit subjects into Keep-a-Changelog sections; commits that do not parse are listed under "Needs review".
"""
from __future__ import annotations
import argparse, datetime, re, subprocess, sys

SECTIONS = {"feat": "Added", "fix": "Fixed", "perf": "Changed", "revert": "Changed", "deprecate": "Deprecated", "security": "Security"}
SKIP = {"chore", "ci", "build", "test", "style", "docs", "refactor"}

def git(repo, *a):
    r = subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since"); ap.add_argument("--until", default="HEAD"); ap.add_argument("--version", default="Unreleased"); ap.add_argument("--repo", default=".")
    a = ap.parse_args()
    since = a.since or git(a.repo, "describe", "--tags", "--abbrev=0")
    rng = f"{since}..{a.until}" if since else a.until
    log = git(a.repo, "log", rng, "--no-merges", "--pretty=%h%x09%s%x09%b%x1e")
    groups, breaking, review, skipped = {}, [], [], 0
    for rec in filter(None, (r.strip() for r in log.split("\x1e"))):
        parts = rec.split("\t", 2)
        h, subj, body = parts[0], parts[1], parts[2] if len(parts) > 2 else ""
        m = re.match(r"(\w+)(?:\(([^)]*)\))?(!)?:\s*(.+)", subj)
        if not m:
            review.append(f"{subj} ({h})"); continue
        typ, scope, bang, text = m.groups()
        line = (f"**{scope}:** " if scope else "") + text[0].upper() + text[1:] + f" ({h})"
        if bang or "BREAKING CHANGE" in body:
            breaking.append(line); continue
        if typ in SECTIONS: groups.setdefault(SECTIONS[typ], []).append(line)
        elif typ in SKIP: skipped += 1
        else: review.append(f"{subj} ({h})")
    date = datetime.date.today().isoformat()
    print(f"## [{a.version}] - {date}\n")
    if breaking:
        print("### Breaking\n" + "\n".join(f"- {l}" for l in breaking) + "\n")
    for sec in ("Added", "Changed", "Deprecated", "Fixed", "Security"):
        if sec in groups: print(f"### {sec}\n" + "\n".join(f"- {l}" for l in groups[sec]) + "\n")
    if review: print("### Needs review (not conventional)\n" + "\n".join(f"- {l}" for l in review) + "\n")
    print(f"<!-- range {rng}; {skipped} internal commits omitted; rewrite each line for users -->")
    return 0

if __name__ == "__main__": sys.exit(main())
