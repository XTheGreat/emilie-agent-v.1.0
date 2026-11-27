"""The Search panel: plain text searched in every file of a project, the matches grouped by file."""
from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path

MAX_FILE = 1_000_000        # bigger files are left out (bundles, data dumps)
MAX_MATCHES = 600           # in all ...
MAX_PER_FILE = 50           # ... and per file
MAX_SECONDS = 8.0
BEFORE, AFTER = 40, 160     # how much of a long line is sent around the match


def _git_files(cwd: str) -> list[str] | None:
    """Tracked and untracked files minus the ignored ones, or None when this is not a git repository."""
    try:
        r = subprocess.run(["git", "-C", cwd, "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                           capture_output=True, timeout=15, stdin=subprocess.DEVNULL,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return sorted({f for f in r.stdout.decode("utf-8", errors="replace").split("\0") if f}, key=str.lower)


def _walk_files(cwd: str, skip: set[str]):
    for root, dirs, files in os.walk(cwd):
        dirs[:] = sorted((d for d in dirs if d not in skip and not d.startswith(".")), key=str.lower)
        for f in sorted(files, key=str.lower):
            yield os.path.relpath(os.path.join(root, f), cwd).replace("\\", "/")


def _snippet(line: str, start: int, end: int) -> dict:
    pre = line[:start].lstrip()
    if len(pre) > BEFORE:
        pre = "…" + pre[-BEFORE:]
    post = line[end:end + AFTER].rstrip()
    return {"pre": pre, "hit": line[start:end], "post": post + ("…" if len(line) > end + AFTER else "")}


def search(cwd: str, query: str, case: bool = False, word: bool = False, skip: set[str] = frozenset()) -> dict:
    """{files: [{rel, abs, matches: [{line, pre, hit, post}], more}], total, truncated}. One match is one line."""
    out: list[dict] = []
    total, truncated = 0, False
    if not query.strip():
        return {"files": out, "total": total, "truncated": truncated}
    pat = re.escape(query)
    if word:
        pat = rf"(?<!\w){pat}(?!\w)"
    rx = re.compile(pat, 0 if case else re.IGNORECASE)
    names = _git_files(cwd)
    deadline = time.monotonic() + MAX_SECONDS
    for rel in names if names is not None else _walk_files(cwd, skip):
        if total >= MAX_MATCHES or time.monotonic() > deadline:
            truncated = True
            break
        p = Path(cwd) / rel
        try:
            if p.is_symlink() or not p.is_file() or p.stat().st_size > MAX_FILE:
                continue
            data = p.read_bytes()
        except OSError:
            continue
        if b"\x00" in data[:8192]:
            continue
        text = data.decode("utf-8-sig", errors="replace")
        if not rx.search(text):
            continue
        matches, more = [], 0
        # split on "\n" only, so the numbers are the ones the file viewer shows
        for n, line in enumerate(text.split("\n"), 1):
            line = line.rstrip("\r")
            m = rx.search(line)
            if not m:
                continue
            if len(matches) < MAX_PER_FILE and total < MAX_MATCHES:
                matches.append({"line": n, **_snippet(line, m.start(), m.end())})
                total += 1
            else:
                more += 1
        if matches:
            out.append({"rel": rel, "abs": str(p), "matches": matches, "more": more})
            truncated = truncated or more > 0
    return {"files": out, "total": total, "truncated": truncated}
