"""Trusted folders (like Claude Code's "do you trust this folder?").

Emilie does not load anything from a project folder (skills, commands, MCP servers, EMILIE.md) until the
user has said that folder can be trusted. By default the question is asked EVERY time Emilie starts (after
Ctrl+C and coming back, it asks again). To remember the answer set "trust_remember": true in
~/.emilie/settings.json; the folders are then kept in ~/.emilie/trusted.json (a folder is trusted if it, or
one of its parents, was accepted).
"""
from . import paths
import json
import os
import time
from pathlib import Path

FILE = paths.HOME_DIR / "trusted.json"


def _load() -> dict:
    try:
        d = json.loads(FILE.read_text())
        return d.get("folders", {}) if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _norm(path: str) -> str:
    return os.path.realpath(os.path.expanduser(path))


def remember_enabled() -> bool:
    try:
        from . import effort
        return bool(effort.load_settings().get("trust_remember", False))
    except Exception:
        return False


def is_trusted(path: str | None = None) -> bool:
    if paths.env("TRUST_FOLDER") == "1":
        return True
    p = Path(_norm(path or os.getcwd()))
    folders = _load()
    return any(str(q) in folders for q in (p, *p.parents))


def needed(argv: list[str], path: str | None = None) -> bool:
    """True when the "trust this folder?" question must be asked before loading the project."""
    if "--trust-folder" in argv or "--banner" in argv or paths.env("TRUST_FOLDER") == "1":
        return False
    return not (remember_enabled() and is_trusted(path))


def add(path: str | None = None) -> None:
    folders = _load()
    folders[_norm(path or os.getcwd())] = time.strftime("%Y-%m-%d %H:%M:%S")
    FILE.parent.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps({"folders": folders}, indent=2))


def remove(path: str | None = None) -> bool:
    folders = _load()
    hit = folders.pop(_norm(path or os.getcwd()), None) is not None
    if hit:
        FILE.write_text(json.dumps({"folders": folders}, indent=2))
    return hit


def is_risky(path: str | None = None) -> bool:
    """Home folder or filesystem root: trusting it would cover far more than one project."""
    p = _norm(path or os.getcwd())
    return p in (_norm("~"), "/")
