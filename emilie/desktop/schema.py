"""The desktop Settings page, described as data, and the one place that validates and saves a setting.

The UI draws every field from build(), so adding a setting is one F(...) line here. Anything added to
config_cmds.KEYS (the CLI's /config list) appears under "Advanced" by itself, with no UI work at all.

Field types: toggle, select, segmented, number, text, password, textarea, and custom:<name> for the panels that need
their own widget (provider, MCP servers, skills, ...). Every value lives in ~/.emilie/settings.json, the same file the
terminal version reads, so both always agree.
"""
from __future__ import annotations

import getpass
from pathlib import Path

from .. import config_cmds, effort as eff, i18n, language, logo


def F(key: str, type_: str, label: str, desc: str = "", **kw) -> dict:
    return {"key": key, "type": type_, "label": label, "desc": desc, **kw}


def _ch(*pairs) -> list[dict]:
    return [{"value": v, "label": l} for v, l in pairs]


ICON_MODES = ("video", "image", "ascii", "pixel")

# settings the app stores but does not show as a field
HIDDEN = {
    "desktop_recent": "list",          # folders opened from the folder picker, newest first
    "desktop_sidebar": "bool",         # sidebar open
    "desktop_collapsed": "list",       # folder groups folded in the sidebar
    "desktop_pane_w": "number",        # width of the side pane
    "desktop_sidebar_width": "number", # width of the sidebar
    "desktop_browser_url": "text",     # last address in the Browser pane
    "desktop_onboarded": "bool",
    "desktop_pane_tabs": "list",       # tabs open in the side pane
    "desktop_pinned": "list",          # sessions pinned to the top of the sidebar
    "desktop_pinned_projects": "list", # project folders pinned on the Projects page
    "desktop_code_light": "text",      # code colour theme in light mode (Appearance > Code)
    "desktop_code_dark": "text",       # ... and in dark mode
    "desktop_code_font": "text",       # monospace font for code and the terminal (empty = default)
    "desktop_code_size": "number",     # code font size in px (0 / empty = default)
}


def build() -> list[dict]:
    """Sections in the order and groups of the Claude Code settings window ("group" = the block in the left list)."""
    langs = _ch(*i18n.available().items())
    reply = [{"value": "auto", "label": "Auto (same as your message)"}] + _ch(*language.NAMES.items())
    efforts = [{"value": n, "label": n.capitalize(), "desc": eff.LEVELS[n].desc} for n in eff.LEVELS]
    sections = [
        # ---- account-like
        {"id": "general", "label": "General", "icon": "user", "group": 1, "groups": [
            {"title": "Profile", "fields": [
                F("desktop_name", "text", "What should Emilie call you?", "Shown in the sidebar.",
                  placeholder=getpass.getuser()),
            ]},
            {"title": "Language", "fields": [
                F("language", "select", "Reply language", "The language Emilie writes her answers in.",
                  choices=reply, default="auto", allow_custom=True),
                F("ui_lang", "select", "Command messages",
                  "Language of the messages slash commands print (the terminal's translations).",
                  choices=langs, default="en", live=False),
            ]},
        ]},
        {"id": "model", "label": "Model", "icon": "cpu", "group": 1, "groups": [
            {"title": "Provider", "fields": [F("provider", "custom:provider", "Provider and API key")]},
            {"title": "Model", "fields": [
                F("model", "custom:model", "Default model", "Used by new sessions; each session can switch."),
                F("fallback_model", "text", "Fallback model",
                  "Used when the main model keeps failing (busy, rate limit, timeout). Same provider.",
                  placeholder="off", nullable=True),
                F("effort", "segmented", "Effort",
                  "How much the model thinks before it answers (on models that can), and how long answers, tool "
                  "output and rounds per message may get. Ctrl+Shift+I opens it with the model picker.",
                  choices=efforts, default="medium"),
                F("thinking", "number", "Thinking budget (older Claude models)",
                  "Only for Claude models before 4.6 on the Anthropic provider; current models think by Effort. "
                  "0 = off, at least 1024.",
                  min=0, max=64000, step=1024, default=0),
            ]},
            {"title": "Requests", "fields": [
                F("timeout", "number", "Timeout (seconds)", "How long the provider may stay silent before giving up.",
                  min=20, max=1800, default=180, live=False),
                F("retries", "number", "Retries", "How often a rate-limited (429) or busy request is tried again. "
                  "The waits grow from 5 seconds to a minute, and every session waits out the same limit together.",
                  min=0, max=10, default=6),
                F("context_limit", "number", "Context window (tokens)",
                  "This model's window; automatic compaction stays under 70% of it. Empty = automatic.",
                  min=2048, max=2_000_000, nullable=True),
                F("compact_at", "number", "Auto-compact at (tokens)",
                  "Older messages are summarized once the context passes this. Lower uses fewer tokens. "
                  "Empty = the effort level's.", min=4000, max=2_000_000, step=1000, nullable=True),
            ]},
            {"title": "Usage and cost", "fields": [
                F("price_in", "number", "Input price", "USD per million input tokens, for the cost estimate (/cost).",
                  min=0, max=1000, step=0.01, nullable=True),
                F("price_out", "number", "Output price", "USD per million output tokens.", min=0, max=1000, step=0.01,
                  nullable=True),
            ]},
        ]},
        {"id": "usage", "label": "Usage", "icon": "gauge", "group": 1, "groups": [
            {"title": "", "fields": [F("usage", "custom:usage", "")]},
        ]},
        # ---- you and Emilie
        {"id": "appearance", "label": "Appearance", "icon": "palette", "group": 2, "groups": [
            {"title": "", "fields": [
                F("desktop_theme", "segmented", "Color mode", "Warm: light in cream. Eveny: a deep navy, almost black.",
                  choices=_ch(("light", "Light"), ("warm", "Warm"), ("auto", "Auto"), ("dark", "Dark"), ("eveny", "Eveny")),
                  default="dark"),
                F("desktop_font", "segmented", "Chat font",
                  choices=_ch(("default", "Default"), ("sans", "Sans"), ("system", "System"),
                              ("dyslexic", "Dyslexic friendly")), default="default"),
                F("desktop_accent", "segmented", "Accent color",
                  "Emilie's pink, or lavender. (Claude's orange is Claude's, so it is not offered.)",
                  choices=_ch(("sakura", "Original"), ("lavender", "Lavender")), default="sakura"),
            ]},
            {"title": "Code", "fields": [F("code_appearance", "custom:codeappearance", "")]},
            {"title": "Emilie icon", "fields": [
                F("desktop_show_icon", "toggle", "Show Emilie's icon",
                  "The icon above the folder list on the New session screen. Off: the screen shows only the list.", default=True),
                F("desktop_icon", "custom:icon", "Icon style",
                  "How Emilie's icon is drawn: the video, a still image, ASCII characters like the terminal, "
                  "or big pixels like the terminal's half-blocks.", choices=_ch(
                      ("video", "Video"), ("image", "Image"), ("ascii", "ASCII (CLI)"), ("pixel", "Pixel")),
                  default="video"),
                F("logo_cols", "number", "Icon size",
                  "How big Emilie's icon is on the New session screen: the same number as /logo size (12 to 80, "
                  "about 3 pixels each; the terminal's logo follows it too). Empty = automatic.",
                  min=12, max=80, step=2),
                F("logo", "custom:logo", "Icon file",
                  "A video (mp4, webm, mov, gif) or an image (png, jpg, webp). Also used by the terminal banner."),
                F("fps", "number", "Frame rate", "For the ASCII and pixel styles (and the terminal logo).",
                  min=4, max=30, step=1, default=12),
            ]},
        ]},
        {"id": "persona", "label": "Your Emilie", "icon": "sparkles", "group": 2, "groups": [
            {"title": "", "fields": [
                F("persona", "toggle", "Play the Emilie character",
                  "Her personality comes from persona.md. Turn it off for a neutral assistant.", default=True),
                F("persona_text", "custom:persona", "Character sheet"),
            ]},
        ]},
        {"id": "capabilities", "label": "Capabilities", "icon": "mic", "group": 2, "groups": [
            {"title": "Voice", "fields": [
                F("voice", "toggle", "Speak replies", "Needs a running Voicebox server.", default=False),
                F("voice_mode", "segmented", "What she says",
                  choices=_ch(("say", "A short spoken line"), ("full", "The whole reply")), default="say"),
                F("voice_lang", "select", "Voice language", choices=_ch(("ja", "Japanese"), ("en", "English"),
                                                                         ("id", "Indonesian"), ("ms", "Malay"),
                                                                         ("ko", "Korean"), ("zh", "Chinese")),
                  default="ja", allow_custom=True),
                F("voice_profile", "text", "Voice profile", default="Emilie", placeholder="Emilie"),
                F("voice_url", "text", "Voicebox server", default="http://127.0.0.1:17493",
                  placeholder="http://127.0.0.1:17493"),
                F("voice_test", "custom:voice-test", "Test"),
            ]},
            {"title": "Talk (hands-free)", "fields": [
                F("talk_pause", "number", "Pause that sends your turn (seconds)", min=0.4, max=5, step=0.1,
                  default=1.0),
                F("talk_lang", "text", "Speech language", "Empty = detect automatically.", placeholder="auto"),
                F("talk_model", "text", "Speech model", default="base", placeholder="base"),
            ]},
            {"title": "Camera and video call", "fields": [
                F("camera", "custom:camera", "Camera device"),
                F("companion", "toggle", "During a video call she may start talking", default=True),
                F("companion_secs", "number", "How often she looks (seconds)", min=15, max=600, default=45),
                F("companion_memory", "toggle", "Remember things between calls",
                  "Short notes about you, kept as text on this computer only.", default=True),
                F("companion_notes", "custom:companion", "What she remembers"),
            ]},
        ]},
        {"id": "notifications", "label": "Notifications", "icon": "bell", "group": 2, "groups": [
            {"title": "", "fields": [
                F("desktop_notify", "toggle", "Desktop notifications",
                  "Tell me when Emilie finishes or needs permission while the window is in the background.",
                  default=True),
            ]},
        ]},
        {"id": "privacy", "label": "Privacy", "icon": "shield", "group": 2, "groups": [
            {"title": "Permissions", "fields": [
                F("desktop_mode", "segmented", "Default mode for new sessions",
                  "Ask first: Emilie asks before changing files or running commands. Trust: she works on her own. "
                  "Plan: she may only read and then proposes a plan.",
                  choices=_ch(("ask", "Ask first"), ("trust", "Trust"), ("plan", "Plan")), default="ask"),
                F("permissions", "custom:rules", "Allow and deny rules"),
            ]},
            {"title": "Trusted folders", "fields": [
                F("trusted", "custom:trusted", "Folders you trusted"),
                F("trust_remember", "toggle", "Terminal: remember trusted folders",
                  "The terminal version asks on every start unless this is on. The app always remembers.",
                  default=False),
            ]},
            {"title": "Hooks", "fields": [F("hooks", "custom:hooks", "Tool hooks")]},
        ]},
        # ---- working with code
        {"id": "customize", "label": "Customize", "icon": "case", "group": 3, "groups": [
            {"title": "Skills", "fields": [F("skills", "custom:skills", "")]},
            {"title": "Connectors", "fields": [F("mcp", "custom:mcp", "")]},
        ]},
        {"id": "code", "label": "Code", "icon": "code", "group": 3, "groups": [
            {"title": "Sessions", "fields": [
                F("desktop_auto_title", "toggle", "Name new sessions automatically",
                  "After the first answer Emilie writes a short title (one tiny extra model call).", default=True),
                F("desktop_env_panel", "toggle", "Show the environment panel",
                  "The panel on the right of a session: folder, branch, context, connectors, outputs and changes.",
                  default=True),
            ]},
            {"title": "Scheduled tasks", "fields": [F("schedule", "custom:schedule", "")]},
        ]},
        # ---- the app
    ]
    shown = {f["key"] for s in sections for g in s["groups"] for f in g["fields"]}
    adv = [_from_key(k) for k in config_cmds.KEYS.values() if k.name not in shown]
    sections.append({"id": "desktop", "label": "Desktop app", "icon": "monitor", "group": 4, "groups": [
        {"title": "About", "fields": [F("about", "custom:about", "")]},
        {"title": "Files", "fields": [F("files", "custom:files", "")]},
        {"title": "Your data", "fields": [F("history", "custom:history", "")]},
        {"title": "Terminal and other settings", "fields": adv},
    ]})
    return sections


def _from_key(k: config_cmds.Key) -> dict:
    """A /config setting as a field (used for every key the sections above do not place)."""
    base = {"default": k.default, "live": k.live, "nullable": k.nullable or k.default is None}
    label = k.name.replace("_", " ").capitalize()
    if k.kind == "bool":
        return F(k.name, "toggle", label, k.desc, **base)
    if k.kind in ("int", "float"):
        return F(k.name, "number", label, k.desc, min=k.lo, max=k.hi, step=1 if k.kind == "int" else 0.01, **base)
    if k.kind == "choice":
        return F(k.name, "segmented", label, k.desc, choices=_ch(*((c, c) for c in k.choices)), **base)
    return F(k.name, "text", label, k.desc, **base)


def _fields() -> dict[str, dict]:
    return {f["key"]: f for s in build() for g in s["groups"] for f in g["fields"]}


def apply(key: str, value) -> tuple[object, str | None]:
    """Validate and save one setting. -> (saved value or None when reset to default, error or None)."""
    if key in config_cmds.KEYS:
        k = config_cmds.KEYS[key]
        if value is None or value == "":
            raw = "default"
        elif k.kind == "bool":
            raw = "on" if value else "off"
        else:
            raw = str(value)
        v, err = config_cmds.parse(key, raw)
        if err:
            return None, err
        if v is None:
            eff.unset_settings(key)
        else:
            eff.save_settings(**{key: v})
        return v, None
    if key == "permissions":                     # {"allow": [rule], "deny": [rule]}, the same rules as /allow and /deny
        if not isinstance(value, dict):
            return None, "permissions must be an object with allow and deny lists"
        clean = {k: [str(r).strip() for r in value.get(k) or [] if str(r).strip()][:200] for k in ("allow", "deny")}
        eff.save_settings(permissions=clean)
        return clean, None
    if key == "mcp_modes":                        # {server: "always" | "on_demand" | "off"} (mcp.py)
        if not isinstance(value, dict):
            return None, "mcp_modes must be an object"
        clean = {str(k): v for k, v in value.items() if v in ("always", "on_demand", "off")}
        eff.save_settings(mcp_modes=clean)
        return clean, None
    if key in HIDDEN:
        kind = HIDDEN[key]
        if kind == "list" and not isinstance(value, list):
            return None, f"{key} takes a list"
        if kind == "bool":
            value = bool(value)
        if kind == "number":
            try:
                value = float(value)
            except (TypeError, ValueError):
                return None, f"{key} takes a number"
        if kind == "text":
            value = str(value or "")[:2000]
        eff.save_settings(**{key: value})
        return value, None
    f = _fields().get(key)
    if f is None or f["type"] in ("custom:provider", "custom:rules", "custom:trusted", "custom:hooks", "custom:mcp",
                                  "custom:skills", "custom:schedule", "custom:files", "custom:about", "custom:usage",
                                  "custom:persona", "custom:voice-test", "custom:companion", "custom:camera"):
        return None, f"'{key}' cannot be set here"
    t = f["type"]
    if value is None or (isinstance(value, str) and not value.strip() and t not in ("toggle",)):
        eff.unset_settings(key)
        return None, None
    if t == "toggle":
        v = bool(value)
    elif t == "number":
        try:
            v = float(value)
        except (TypeError, ValueError):
            return None, f"{f['label']}: give a number"
        if f.get("min") is not None and v < f["min"] or f.get("max") is not None and v > f["max"]:
            return None, f"{f['label']}: between {f.get('min')} and {f.get('max')}"
        if float(f.get("step") or 1).is_integer() and v.is_integer():
            v = int(v)
    elif t in ("select", "segmented", "custom:icon"):
        v = str(value)
        if not f.get("allow_custom") and v not in {c["value"] for c in f.get("choices", [])}:
            return None, f"{f['label']}: unknown choice '{v}'"
    elif t == "custom:logo":
        p = Path(str(value)).expanduser()
        if not p.is_file() or p.suffix.lower() not in logo.VIDEO_EXTS | logo.IMAGE_EXTS:
            return None, "pick a video (mp4, webm, mov, gif) or an image (png, jpg, webp)"
        v = str(p.resolve())
    else:
        v = str(value).strip()
    eff.save_settings(**{key: v})
    return v, None
