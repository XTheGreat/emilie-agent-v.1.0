"""Plugins: a folder in ~/.emilie/plugins/<id>/ that bundles skills, slash commands and MCP servers (like Claude Code's).

    <id>/plugin.json        {"name", "version", "description", "author"}   (optional: the folder name is used otherwise)
    <id>/skills/<name>/SKILL.md      skills (the same format as ~/.emilie/skills)
    <id>/commands/<name>.md          slash commands
    <id>/.mcp.json                   MCP servers ({"mcpServers": {...}}), started with Emilie's others

An enabled plugin is just one more root for skills.py and mcp.py. state.json next to the folders lists the disabled ones.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from . import paths

ROOT = paths.HOME_DIR / "plugins"
STATE = ROOT / "state.json"


class PluginError(Exception):
    pass


def _disabled() -> set[str]:
    try:
        return set(json.loads(STATE.read_text(encoding="utf-8")).get("disabled") or [])
    except (OSError, ValueError):
        return set()


def _save_disabled(s: set[str]) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"disabled": sorted(s)}), encoding="utf-8")


def _manifest(d: Path) -> dict:
    for f in (d / "plugin.json", d / ".claude-plugin" / "plugin.json"):
        try:
            m = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(m, dict):
                return m
        except (OSError, ValueError):
            pass
    return {}


def _mcp_file(d: Path) -> dict:
    try:
        data = json.loads((d / ".mcp.json").read_text(encoding="utf-8"))
        return data.get("mcpServers") or data.get("servers") or {}
    except (OSError, ValueError):
        return {}


def _dirs() -> list[Path]:
    try:
        return sorted(p for p in ROOT.iterdir() if p.is_dir() and not p.name.startswith("."))
    except OSError:
        return []


def listing() -> list[dict]:
    off = _disabled()
    out = []
    for d in _dirs():
        m = _manifest(d)
        skills = len(list((d / "skills").glob("*/SKILL.md"))) if (d / "skills").is_dir() else 0
        cmds = len(list((d / "commands").glob("*.md"))) if (d / "commands").is_dir() else 0
        a = m.get("author")
        out.append({"id": d.name, "name": str(m.get("name") or d.name), "version": str(m.get("version") or ""),
                    "description": str(m.get("description") or ""),
                    "author": a.get("name") if isinstance(a, dict) else str(a or ""),
                    "path": str(d), "enabled": d.name not in off, "skills": skills, "commands": cmds,
                    "mcp": sorted(_mcp_file(d))})
    return out


def enabled_roots() -> list[Path]:
    """Folders of the enabled plugins (skills.py reads <root>/skills and <root>/commands)."""
    off = _disabled()
    return [d for d in _dirs() if d.name not in off]


def mcp_configs() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for d in enabled_roots():
        out.update(_mcp_file(d))
    return out


def _id(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", s).strip("-.")[:60]


def _looks_like_plugin(d: Path) -> bool:
    return ((d / "skills").is_dir() or (d / "commands").is_dir() or (d / ".mcp.json").is_file()
            or (d / "plugin.json").is_file() or (d / ".claude-plugin" / "plugin.json").is_file())


def install(source: str) -> dict:
    """Install from a local folder or an https git address. Returns the plugin's entry. Same id: it is replaced."""
    source = (source or "").strip().strip('"')
    if not source:
        raise PluginError("give a folder or a GitHub address")
    ROOT.mkdir(parents=True, exist_ok=True)
    tmp = ROOT / ".incoming"
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        if re.match(r"^(https://|git@)", source) or source.endswith(".git"):
            if not re.match(r"^https://[\w.-]+/[\w./~-]+$", source):
                raise PluginError("only plain https:// git addresses are accepted")
            r = subprocess.run(["git", "clone", "--depth", "1", source, str(tmp)],
                               capture_output=True, text=True, timeout=180)
            if r.returncode:
                raise PluginError("git clone failed: " + (r.stderr or r.stdout).strip()[-300:])
            shutil.rmtree(tmp / ".git", ignore_errors=True)
            base = _id(source.rstrip("/").split("/")[-1].removesuffix(".git"))
        else:
            src = Path(source).expanduser()
            if not src.is_dir():
                raise PluginError(f"{source} is not a folder")
            shutil.copytree(src, tmp, ignore=shutil.ignore_patterns(".git", "node_modules"))
            base = _id(src.name)
        if not _looks_like_plugin(tmp):
            # a "marketplace": a repo that holds many plugins, one per sub-folder (awesome-claude-plugins and the like)
            kids = [k for k in sorted(tmp.iterdir()) if k.is_dir() and not k.name.startswith(".") and _looks_like_plugin(k)]
            if not kids:
                raise PluginError("this is not a plugin: it has no skills/, commands/, .mcp.json or plugin.json")
            s = _disabled()
            ids = []
            for k in kids:                                  # each one becomes its own plugin, OFF until you switch it on
                kid = _id(str(_manifest(k).get("name") or k.name)) or k.name
                shutil.rmtree(ROOT / kid, ignore_errors=True)
                shutil.copytree(k, ROOT / kid)
                s.add(kid)
                ids.append(kid)
            _save_disabled(s)
            return {"many": ids}
        pid = _id(str(_manifest(tmp).get("name") or base)) or base or "plugin"
        dest = ROOT / pid
        shutil.rmtree(dest, ignore_errors=True)
        tmp.replace(dest)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    s = _disabled()
    s.discard(pid)
    _save_disabled(s)
    return {"plugin": next(p for p in listing() if p["id"] == pid)}


def set_enabled(pid: str, on: bool) -> None:
    if not re.fullmatch(r"[\w.-]+", pid or "") or not (ROOT / pid).is_dir():
        raise PluginError("plugin not found")
    s = _disabled()
    (s.discard if on else s.add)(pid)
    _save_disabled(s)


def remove(pid: str) -> None:
    d = ROOT / pid
    if not re.fullmatch(r"[\w.-]+", pid or "") or not d.is_dir():
        raise PluginError("plugin not found")
    shutil.rmtree(d)
    s = _disabled()
    s.discard(pid)
    _save_disabled(s)
