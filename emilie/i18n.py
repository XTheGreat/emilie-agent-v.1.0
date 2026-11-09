"""UI translation (/language). No UI text is hardcoded per language: the code holds the English text and
`tr_("English text {0}", value)` looks it up in a language file.

Language files are JSON:  {"_meta": {"name": "Bahasa Indonesia"}, "strings": {"English text": "Terjemahan"}}
  * built in:   emilie/locales/<code>.json
  * your own:   ~/.emilie/locales/<code>.json   (add a language without touching the code)
Placeholders ({0}, {name}) and Rich markup ([bold], [/]) must be kept as they are in the translation.
A missing key simply falls back to the English text, so a partial translation is fine.
Make a template for a new language with:  python -m emilie.i18n template <code>
"""
from . import paths
import json
import os
from pathlib import Path

DIRS = [Path(__file__).parent / "locales", paths.HOME_DIR / "locales"]
_lang: str | None = None
_cat: dict[str, str] = {}


def _read(code: str) -> dict:
    data: dict = {"strings": {}, "_meta": {}}
    for d in DIRS:                                  # the user's folder is read last and wins
        f = d / f"{code}.json"
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        data["strings"].update(j.get("strings", {}))
        data["_meta"].update(j.get("_meta", {}))
    return data


def available() -> dict[str, str]:
    """{code: native name}, English always included."""
    out = {"en": "English"}
    for d in DIRS:
        try:
            for f in sorted(d.glob("*.json")):
                out[f.stem] = _read(f.stem)["_meta"].get("name", f.stem)
        except OSError:
            pass
    return out


def current() -> str:
    global _lang
    if _lang is None:
        code = paths.env("LANG")
        if not code:
            try:
                from . import effort
                code = effort.load_settings().get("ui_lang", "en")
            except Exception:
                code = "en"
        set_lang(code, save=False)
    return _lang or "en"


def set_lang(code: str, save: bool = True) -> str:
    global _lang, _cat
    code = (code or "en").strip().lower()
    if code != "pseudo" and code != "en" and code not in available():
        return f"unknown language '{code}'. Available: " + ", ".join(f"{k} ({v})" for k, v in available().items())
    _lang = code
    _cat = {} if code in ("en", "pseudo") else _read(code)["strings"]
    if save:
        from . import effort
        effort.save_settings(ui_lang=code)
    return ""


def t(msg: str, /, *args, **kw) -> str:
    """Translate `msg` (the English source text) and fill its placeholders."""
    lang = current()
    s = _cat.get(msg, msg) if lang != "en" else msg
    if args or kw:
        try:
            s = s.format(*args, **kw)
        except (IndexError, KeyError, ValueError):       # a broken translation must never crash the UI
            s = msg.format(*args, **kw)
    return f"«{s}»" if lang == "pseudo" else s


def N_(msg: str) -> str:
    """Marks a module-level string for extraction; translate it at display time with tr_(value)."""
    return msg


def _keys() -> list[str]:
    """Every English source string passed to t(...) in the package."""
    import ast
    keys: dict[str, None] = {}
    for f in sorted(Path(__file__).parent.glob("*.py")):
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Call) and getattr(n.func, "id", "") in ("t", "tr_", "N_") and n.args \
                    and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                keys[n.args[0].value] = None
    return list(keys)


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3 and sys.argv[1] == "template":
        code = sys.argv[2]
        old = _read(code)["strings"]
        out = {"_meta": {"name": code}, "strings": {k: old.get(k, "") for k in _keys()}}
        target = DIRS[1] / f"{code}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{len(out['strings'])} strings -> {target}  (fill in the empty ones)")
    else:
        print(f"{len(_keys())} translatable strings; languages: {available()}")
