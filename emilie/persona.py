"""Persona: lets the agent play a character (e.g. Emilie) instead of a plain assistant.

The text lives in ~/.emilie/persona.md (edit it with any editor; changes apply on the next message).
A project can override it with ./.emilie/persona.md. Switch with /persona on|off.
"""
from . import paths
import os
from pathlib import Path

from .i18n import t as tr_
from . import effort

HOME_FILE = paths.HOME_DIR / "persona.md"

BUILTIN = Path(__file__).parent / "builtin" / "persona.md"     # ships with the repo, so a fresh clone has the personality


def _builtin() -> str:
    try:
        return BUILTIN.read_text(encoding="utf-8")
    except OSError:
        return "# Who you are\nYou are Emilie, a warm, gentle and cheerful companion. Reply in the user's language."


DEFAULT = _builtin()


def _file() -> Path | None:
    for d in (".emilie",):
        proj = Path(os.getcwd()) / d / "persona.md"
        if proj.exists():
            return proj
    return HOME_FILE if HOME_FILE.exists() else None


def enabled() -> bool:
    return bool(effort.load_settings().get("persona", True))   # on by default; /persona off turns it off


def set_enabled(on: bool) -> str:
    if on and not HOME_FILE.exists():
        HOME_FILE.parent.mkdir(parents=True, exist_ok=True)
        HOME_FILE.write_text(DEFAULT, encoding="utf-8")
    effort.save_settings(persona=on)
    return f"persona {'on' if on else 'off'}" + (tr_(' - edit {HOME_FILE} to change who she is', HOME_FILE=HOME_FILE) if on else "")


def reset() -> str:
    HOME_FILE.parent.mkdir(parents=True, exist_ok=True)
    HOME_FILE.write_text(DEFAULT, encoding="utf-8")
    return tr_('persona reset to the default Emilie ({HOME_FILE})', HOME_FILE=HOME_FILE)


def text() -> str:
    f = _file()
    try:
        return f.read_text(encoding="utf-8").strip() if f else DEFAULT.strip()
    except (OSError, UnicodeDecodeError):
        return DEFAULT.strip()


def section() -> str:
    if not enabled():
        return ""
    return ("# Persona (roleplay)\nThe user wants you to play the character below for the whole conversation. "
            "It changes your voice and personality, not your tools or safety rules.\n\n" + text())
