#!/usr/bin/env python3
"""Lint a Dockerfile for common problems (read-only, standard library only).

Usage: python docker_lint.py [Dockerfile ...]   (default: ./Dockerfile)
"""
from __future__ import annotations
import re, sys
from pathlib import Path

def lint(path: Path):
    lines = path.read_text(errors="ignore").splitlines()
    out, user, health, from_n, copy_all_at, dep_at = [], None, False, 0, None, None
    for i, raw in enumerate(lines, 1):
        l = raw.strip()
        if not l or l.startswith("#"): continue
        u = l.upper()
        if u.startswith("FROM "):
            from_n += 1; img = l.split()[1]
            if img.lower() != "scratch" and (":" not in img or img.endswith(":latest")) and "$" not in img and "@" not in img:
                out.append((i, "WARN", f"base image '{img}' is unpinned or :latest"))
        elif u.startswith("USER "): user = l.split()[1]
        elif u.startswith("HEALTHCHECK"): health = True
        elif u.startswith("ADD ") and re.search(r"https?://", l): out.append((i, "WARN", "ADD from URL; use curl with checksum verification"))
        elif u.startswith(("ENV ", "ARG ")) and re.search(r"(?i)(password|secret|token|api[_-]?key)\s*=?\s*\S{6,}", l): out.append((i, "HIGH", "secret in ENV/ARG ends up in image layers"))
        if re.match(r"(COPY|ADD)\s+(--\S+\s+)*\.\s+\S+", l) and copy_all_at is None: copy_all_at = i
        if re.search(r"\b(pip install|npm (ci|install)|yarn install|pnpm i|bundle install|go mod download|cargo fetch)\b", l) and dep_at is None: dep_at = i
        if re.search(r"apt-get install", l) and "--no-install-recommends" not in l: out.append((i, "INFO", "apt-get install without --no-install-recommends"))
        if re.search(r"apt-get install", l) and "rm -rf /var/lib/apt/lists" not in l: out.append((i, "INFO", "clean apt lists in the same RUN to keep layers small"))
        if re.search(r"\bcurl\b[^|]*\|\s*(sudo\s+)?(ba)?sh", l): out.append((i, "WARN", "curl | sh runs unverified code"))
        if re.search(r"chmod\s+(-R\s+)?777", l): out.append((i, "WARN", "chmod 777"))
        if u.startswith("CMD ") and not l.split(None, 1)[1].lstrip().startswith("["): out.append((i, "INFO", "shell-form CMD: app will not receive SIGTERM; use exec form"))
    if user in (None, "root", "0"): out.append((0, "WARN", "container runs as root; add a non-root USER"))
    if not health: out.append((0, "INFO", "no HEALTHCHECK (fine if the orchestrator probes instead)"))
    if copy_all_at and dep_at and copy_all_at < dep_at: out.append((copy_all_at, "WARN", "COPY . before dependency install breaks layer caching; copy manifests first"))
    di = path.parent / ".dockerignore"
    if not di.exists(): out.append((0, "WARN", "no .dockerignore next to the Dockerfile"))
    elif ".git" not in di.read_text(errors="ignore") or ".env" not in di.read_text(errors="ignore"): out.append((0, "INFO", ".dockerignore should list .git and .env*"))
    return out

def main():
    paths = [Path(a) for a in sys.argv[1:]] or [Path("Dockerfile")]
    bad = 0
    for p in paths:
        if not p.is_file(): print(f"{p}: not found"); bad = 1; continue
        res = lint(p)
        print(f"{p}: {len(res)} finding(s)")
        for ln, sev, msg in sorted(res): print(f"  {sev:5} {p}:{ln or '-'} {msg}")
    return bad

if __name__ == "__main__": sys.exit(main())
