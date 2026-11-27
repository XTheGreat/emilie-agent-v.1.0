"""The Notes panel: a Markdown scratchpad for each project, kept outside the project (~/.emilie/desktop/notes, so it
never ends up in a commit), and the TODO / FIXME / HACK / XXX / BUG comments found in the project's files."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

from .. import paths
from .projkit import norm, project_files

NOTES = paths.HOME_DIR / "desktop" / "notes"
MAX_NOTE = 2_000_000
TAGS = ("TODO", "FIXME", "HACK", "XXX", "BUG")
# a tag inside a comment: after #, //, /*, *, <!--, --, ; or %
_TODO = re.compile(r"(?:#|//|/\*|^\s*\*|<!--|--|;|%)\s*@?(TODO|FIXME|HACK|XXX|BUG)\b\s*(?:\(([^)]{0,40})\))?\s*[:\-]?\s*(.*)$")
SKIP_EXT = (".min.js", ".min.css", ".map", ".lock", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf",
            ".woff", ".woff2", ".ttf", ".zip", ".gz", ".exe", ".dll", ".so", ".pyc", ".mp4", ".mp3", ".wav")
SKIP_NAMES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Cargo.lock", "go.sum", "uv.lock"}


def _file(cwd: str) -> Path:
    return NOTES / (hashlib.sha1(norm(cwd).encode("utf-8")).hexdigest()[:20] + ".md")


def get(cwd: str) -> dict:
    if not cwd:
        raise ValueError("no folder")
    p = _file(cwd)
    try:
        return {"text": p.read_text(encoding="utf-8"), "updated": p.stat().st_mtime, "path": str(p)}
    except OSError:
        return {"text": "", "updated": 0, "path": str(p)}


def save(cwd: str, text: str) -> dict:
    if not cwd:
        raise ValueError("no folder")
    text = str(text or "")
    if len(text) > MAX_NOTE:
        raise ValueError("The note is too long (2 MB at most).")
    p = _file(cwd)
    p.parent.mkdir(parents=True, exist_ok=True)
    index = p.parent / "index.json"                 # which folder each note belongs to (for a person browsing ~/.emilie)
    try:
        idx = json.loads(index.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        idx = {}
    if idx.get(p.name) != cwd:
        idx[p.name] = cwd
        try:
            index.write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass
    tmp = p.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(p)
    return {"ok": True, "updated": time.time()}


def todos(cwd: str) -> dict:
    """{files: [{rel, abs, items: [{line, tag, who, text}]}], total, truncated}."""
    if not cwd or not os.path.isdir(cwd):
        raise ValueError("not a folder")
    out, total, truncated = [], 0, False
    deadline = time.monotonic() + 10
    for rel in project_files(cwd, limit=20000):
        if total >= 2000 or time.monotonic() > deadline:
            truncated = True
            break
        low = rel.lower()
        if low.endswith(SKIP_EXT) or rel.rsplit("/", 1)[-1] in SKIP_NAMES:
            continue
        p = Path(cwd) / rel
        try:
            if p.stat().st_size > 1_000_000:
                continue
            data = p.read_bytes()
        except OSError:
            continue
        if b"\x00" in data[:4096] or not any(t.encode() in data for t in TAGS):
            continue
        items = []
        for n, line in enumerate(data.decode("utf-8", errors="replace").split("\n"), 1):
            if len(line) > 600:
                continue
            m = _TODO.search(line)
            if m:
                text = re.sub(r"\s*(\*/|-->)\s*$", "", m.group(3)).strip()
                items.append({"line": n, "tag": m.group(1), "who": (m.group(2) or "").strip(), "text": text[:300]})
                total += 1
        if items:
            out.append({"rel": rel, "abs": str(p), "items": items[:200]})
    return {"files": out, "total": total, "truncated": truncated}
