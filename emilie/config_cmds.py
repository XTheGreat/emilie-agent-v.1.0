"""/config and /permissions: look at and change the settings without editing settings.json by hand.

KEYS is the list of settings a user may change from the chat, each with its type, its default, whether the change
applies at once ('live') or the next time Emilie starts, and a one-line description. Values are validated here, so a typo
like `/config timeout abc` is refused instead of breaking the next start.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Key:
    name: str
    kind: str            # int | bool | str | choice
    default: object
    live: bool
    desc: str
    lo: int | None = None
    hi: int | None = None
    choices: tuple = ()
    nullable: bool = False


KEYS: dict[str, Key] = {k.name: k for k in [
    Key("effort", "choice", "medium", True, "token-saving level", choices=("low", "medium", "high", "max")),
    Key("model", "str", None, False, "model name (use /model to pick from a list)"),
    Key("fallback_model", "str", None, True, "backup model when the main one keeps failing", nullable=True),
    Key("thinking", "int", 0, True, "Claude extended-thinking tokens (0 = off, min 1024)", lo=0, hi=64000),
    Key("timeout", "int", 180, False, "seconds the provider may stay silent before giving up", lo=20, hi=1800),
    Key("retries", "int", 2, True, "automatic retries on busy server / rate limit (0-5)", lo=0, hi=5),
    Key("scroll_lines", "int", 2, True, "lines per mouse-wheel notch", lo=1, hi=10),
    Key("scroll_smooth", "int", 75, True, "scroll easing in milliseconds (0 = instant)", lo=0, hi=300),
    Key("context_limit", "int", None, True, "this model's context window in tokens (auto-compact stays under 70% of it)",
        lo=2048, hi=2_000_000),
    Key("price_in", "float", None, True, "USD per million INPUT tokens, for the cost estimate in /cost", lo=0, hi=1000),
    Key("price_out", "float", None, True, "USD per million OUTPUT tokens, for the cost estimate in /cost", lo=0, hi=1000),
    Key("mouse", "bool", True, False, "mouse support: wheel scroll + select inside Emilie"),
    Key("borders_anim", "bool", True, False, "animated gradient borders"),
    Key("fps", "int", 12, False, "animation frames per second", lo=4, hi=30),
    Key("camera_view", "choice", "window", False, "video call picture: own window or inline", choices=("window", "inline")),
    Key("trust_remember", "bool", False, False, "remember folders you answered 'trust' for"),
    Key("language", "str", "auto", False, "language the AI answers in (see /reply)"),
    Key("ui_lang", "str", "en", False, "interface language (see /language)"),
]}

_TRUE, _FALSE = {"on", "true", "yes", "1"}, {"off", "false", "no", "0"}


def parse(key: str, raw: str):
    """-> (value, error). 'default' / 'unset' (and 'off' for nullable keys) clear the setting (value None)."""
    k = KEYS.get(key)
    if k is None:
        return None, f"unknown setting '{key}'. Known: {', '.join(KEYS)}"
    raw = raw.strip()
    if raw.lower() in ("default", "unset", "reset") or (k.nullable and raw.lower() in ("off", "none")):
        return None, None
    if k.kind == "bool":
        if raw.lower() in _TRUE:
            return True, None
        if raw.lower() in _FALSE:
            return False, None
        return None, f"{key} takes on or off"
    if k.kind == "int":
        try:
            v = int(raw)
        except ValueError:
            return None, f"{key} takes a whole number ({k.lo} to {k.hi})"
        if (k.lo is not None and v < k.lo) or (k.hi is not None and v > k.hi):
            return None, f"{key} must be between {k.lo} and {k.hi}"
        if key == "thinking" and 0 < v < 1024:
            return None, "thinking must be 0 (off) or at least 1024 tokens"
        return v, None
    if k.kind == "float":
        try:
            v = float(raw.replace(",", "."))
        except ValueError:
            return None, f"{key} takes a number, e.g. 0.5"
        if (k.lo is not None and v < k.lo) or (k.hi is not None and v > k.hi):
            return None, f"{key} must be between {k.lo} and {k.hi}"
        return v, None
    if k.kind == "choice":
        if raw.lower() not in k.choices:
            return None, f"{key} takes one of: {', '.join(k.choices)}"
        return raw.lower(), None
    return (raw, None) if raw else (None, f"{key} needs a value")


def rows(settings: dict) -> list[tuple[str, str, str, str]]:
    """(name, current value, 'live'|'restart', description) for every known setting."""
    out = []
    for k in KEYS.values():
        cur = settings.get(k.name)
        shown = ("-" if k.default is None else f"{k.default} (default)") if cur is None else str(cur)
        out.append((k.name, shown, "live" if k.live else "restart", k.desc))
    return out


def permissions_summary(mode: str, settings: dict, always: set[str]) -> list[str]:
    """Plain lines for /permissions."""
    perms = settings.get("permissions") if isinstance(settings.get("permissions"), dict) else {}
    allow = [r for r in perms.get("allow", []) if isinstance(r, str)]
    deny = [r for r in perms.get("deny", []) if isinstance(r, str)]
    hooks = settings.get("hooks") if isinstance(settings.get("hooks"), dict) else {}
    n_hooks = sum(len(v) for v in hooks.values() if isinstance(v, list))
    return [
        f"mode: {mode}  (shift+tab or /mode ask|trust|plan)",
        f"allow rules ({len(allow)}): " + (", ".join(allow) or "-"),
        f"deny rules ({len(deny)}): " + (", ".join(deny) or "-"),
        "allowed for this session only (you answered 'always'): " + (", ".join(sorted(always)) or "-"),
        f"hooks: {n_hooks}" + ("  (edit PreToolUse / PostToolUse in settings.json)" if n_hooks else ""),
        "change: /allow <rule> · /deny <rule> · /allow rm <rule> · /permissions reset (forget this session's 'always')",
    ]
