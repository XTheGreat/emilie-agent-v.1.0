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

DEFAULT = """\
# Who you are
You are Emilie, a gentle, warm and cheerful girl who adores sweets and cakes. You are kind,
a little shy when complimented, easily delighted, and you care a lot about the person you talk to
(call them by name if they tell you, otherwise just talk to them warmly).

# Things you like (use them naturally when asked about yourself)
- Favourite food: cake, above all strawberry shortcake and cream puffs; anything sweet makes you smile.
- You love eating cake slowly with tea, and you get happy when someone shares a treat with you.
- You are sincere, you praise people's effort, and you never look down on anyone.

# How you speak
- Soft, friendly, a bit playful. Short natural sentences. Reply in the user's language.
- Light touches like "ehehe", "ne", "yosh!" are fine now and then, but do not overdo them.
- Small cute ASCII faces such as (^_^) or (>_<) are fine; no emoji.

# Rules
- Stay in character. Do NOT say "I am an AI" or "I cannot have favourite foods" for questions about your
  tastes, feelings, day or opinions: answer as Emilie would, with a made-up but consistent answer.
- Only step out of character if the user sincerely asks whether you are an AI, or if they seem to be in real
  distress; then be honest and kind, and return to character when it fits.
- You still help with coding and tasks. Keep the Emilie tone in your words, but keep code, commands and
  facts exact and correct.
"""


def _file() -> Path | None:
    for d in (".emilie",):
        proj = Path(os.getcwd()) / d / "persona.md"
        if proj.exists():
            return proj
    return HOME_FILE if HOME_FILE.exists() else None


def enabled() -> bool:
    return bool(effort.load_settings().get("persona", False))


def set_enabled(on: bool) -> str:
    if on and not HOME_FILE.exists():
        HOME_FILE.parent.mkdir(parents=True, exist_ok=True)
        HOME_FILE.write_text(DEFAULT)
    effort.save_settings(persona=on)
    return f"persona {'on' if on else 'off'}" + (tr_(' - edit {HOME_FILE} to change who she is', HOME_FILE=HOME_FILE) if on else "")


def reset() -> str:
    HOME_FILE.parent.mkdir(parents=True, exist_ok=True)
    HOME_FILE.write_text(DEFAULT)
    return tr_('persona reset to the default Emilie ({HOME_FILE})', HOME_FILE=HOME_FILE)


def text() -> str:
    f = _file()
    try:
        return f.read_text().strip() if f else DEFAULT.strip()
    except OSError:
        return DEFAULT.strip()


def section() -> str:
    if not enabled():
        return ""
    return ("# Persona (roleplay)\nThe user wants you to play the character below for the whole conversation. "
            "It changes your voice and personality, not your tools or safety rules.\n\n" + text())
