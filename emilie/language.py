"""/reply: which language the AI answers in (the interface language is /language, see i18n.py).

Setting `language` in ~/.emilie/settings.json: "auto" (default: follow the user's language) or a language
code / name such as en, id, ja, "Spanish". It is added to the system prompt, so nothing is hardcoded.
"""
from .i18n import t as tr_
from . import effort

NAMES = {"en": "English", "id": "Indonesian", "ja": "Japanese", "ms": "Malay", "ko": "Korean", "zh": "Chinese",
         "es": "Spanish", "fr": "French", "de": "German", "pt": "Portuguese", "ru": "Russian", "ar": "Arabic",
         "hi": "Hindi", "it": "Italian", "nl": "Dutch", "tr": "Turkish", "th": "Thai", "vi": "Vietnamese"}


def current() -> str:
    return str(effort.load_settings().get("language", "auto"))


def display(v: str | None = None) -> str:
    v = v or current()
    return tr_('auto (follows your language)') if v == "auto" else NAMES.get(v.lower(), v)


def set_language(value: str) -> str:
    v = value.strip()
    if not v or v.lower() == "auto":
        effort.save_settings(language="auto")
        return tr_('language: auto (the agent answers in the language you write in)')
    code = v.lower() if v.lower() in NAMES else next((k for k, n in NAMES.items() if n.lower() == v.lower()), None)
    effort.save_settings(language=code or v)
    return tr_('language: {0} (applies from your next message)', NAMES.get(code, v))


def prompt_section() -> str:
    v = current()
    if v == "auto":                 # explicit, so a leftover non-English hint elsewhere in the prompt cannot win
        return ("# Reply language\nReply in the same language as the user's latest message (English message -> English "
                "reply, Indonesian message -> Indonesian reply, and so on). Code, commands, file names and identifiers "
                "stay as they are.")
    return (f"# Reply language\nAlways write your replies in {NAMES.get(v.lower(), v)}, even if the user writes in "
            "another language. Code, commands, file names and identifiers stay as they are.")
