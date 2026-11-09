"""Bankai model list: grade + price multiplier, and the interactive picker (/model)."""
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .i18n import t as tr_
from . import ui
from .theme import ERR, LAV, MUTED, OK, ROSE, WARN

# name -> (grade | None, price multiplier | None). Source: the bankai dashboard.
BANKAI: dict[str, tuple[str | None, float | None]] = {
    "auto": ("B", 1.0),
    "deepseek-v4-flash": ("B", 2.0), "deepseek-v4-flash-0731": ("B", 2.0),
    "deepseek-v4-flash-vision-exp": ("B", 2.5), "deepseek-v4-mod": ("B", 3.0),
    "deepseek-v4-pro": ("B", 1.15), "deepseek-v4-pro-0813": ("B", 1.8),
    "deepseek-v4.1-flash": ("A", 2.56), "deepseek-v4.1-flash-1017": ("A", 3.0),
    "deepseek-v4.1-flash-1017-mod": ("A", 3.5), "deepseek-v4.1-flash-mod": ("A", 3.2),
    "glm-5.2": ("B", 1.25), "glm-5.2-mod": ("B", 3.0), "glm-5.3": ("B", 2.0),
    "glm-5.3-flash": ("B", 2.0), "glm-5.3-flash-mod": ("B", 3.5),
    "glm-5.3-flashx": (None, 3.0), "glm-5.3-flashx-mod": (None, 5.0), "glm-5.3-mod": ("B", 3.2),
    "gpt-5.6-sol": ("B", 25.0), "gpt-5.6-terra": ("B", 10.0), "gpt-6-luna": ("B", 8.0),
    "mimo-v2.5-pro": ("B", 1.4), "mimo-v2.6-flash": ("B", 2.0), "mimo-v2.6-pro": (None, None),
    # --- listed on the dashboard (some may not be live yet; that only shows when you send a message) ---
    "claude-opus-5": ("B", 20.0), "claude-opus-5-5": ("B", 32.0), "claude-sonnet-5": ("B", 10.0),
    "gemini-4-argon": ("B", 60.0),
    "gpt-5.6": ("B", 5.0), "gpt-5.6-luna": ("B", 5.0),
    "gpt-6-astra": ("B", 42.0), "gpt-6-sol": ("B", 30.0),
    "hy3": ("B", 1.0), "hy4": ("B", 1.4),
    "kimi-k2.5": ("B", 1.0), "kimi-k2.6": ("B", 1.0), "kimi-k2.7-code": ("B", 1.0),
    "kimi-k2.7-code-highspeed": ("B", 1.5), "kimi-k2.8": ("B", 2.0),
    "kimi-k3": ("B", 6.0), "kimi-k3-mod": ("B", 8.0),
}

# models the dashboard marks as accepting images (used when the live list has no vision flag)
BANKAI_VISION = {"claude-opus-5", "claude-opus-5-5", "claude-sonnet-5", "gemini-4-argon", "gpt-5.6", "gpt-5.6-luna",
                 "gpt-5.6-sol", "gpt-5.6-terra", "gpt-6-astra", "gpt-6-luna", "gpt-6-sol", "kimi-k2.8"}


def multiplier(name: str) -> float | None:
    return BANKAI.get(name, (None, None))[1]


def fetch_live(client) -> dict[str, dict]:
    """Live status from GET /models (available/vision/grade). Empty on failure."""
    try:
        out = {}
        for m in client.models.list():
            extra = getattr(m, "model_extra", None) or {}
            out[m.id] = {"available": extra.get("available", True) and extra.get("enabled", True),
                         "vision": bool(extra.get("vision")), "grade": extra.get("grade"),
                         "pp": _per_million(extra.get("pricing"))}
        return out
    except Exception:
        return {}


def _per_million(pr) -> tuple[float, float] | None:
    """OpenRouter-style pricing {prompt, completion} (USD per token) -> (in, out) USD per 1M tokens."""
    try:
        return float(pr["prompt"]) * 1e6, float(pr["completion"]) * 1e6
    except (TypeError, KeyError, ValueError):
        return None


def price_label(r: dict) -> str:
    if r.get("mult") is not None:
        return f"×{r['mult']:g}"
    pp = r.get("pp")
    if pp is None:
        return "?"
    if pp[0] < 0 or pp[1] < 0:
        return "varies"
    return "FREE" if pp[0] == 0 and pp[1] == 0 else f"${pp[0]:g}/${pp[1]:g}"


def _cost(r: dict) -> float:
    if r.get("mult") is not None:
        return r["mult"]
    pp = r.get("pp")
    return float("inf") if pp is None or pp[0] < 0 else pp[0] + pp[1]


def _is_bankai() -> bool:
    from . import config
    return "bankai" in (config.BASE_URL or "")


def _rows(live: dict[str, dict], current: str) -> list[dict]:
    bankai = _is_bankai() or not live
    names = list(live) or list(BANKAI)
    if live and bankai:                         # bankai models not live yet are still listed like the others
        names += [n for n in BANKAI if n not in names]
    if current not in names:
        names.append(current)
    rows = []
    for n in names:
        g, m = BANKAI.get(n, (None, None)) if bankai else (None, None)
        lv = live.get(n, {})
        rows.append({"name": n, "grade": lv.get("grade") or g, "mult": m,
                     "vision": lv.get("vision", n in BANKAI_VISION or "vision" in n),
                     "ok": True,                # no "unavailable" marking: the real status shows when a message is sent
                     "pp": lv.get("pp")})
    return rows


def _mult_style(m: float | None, r: dict | None = None) -> str:
    if m is None and r is not None and r.get("pp") is not None:
        c = _cost(r)
        return OK if c == 0 else WARN if c <= 3 else ERR      # per-1M USD in+out
    return MUTED if m is None else OK if m <= 2 else WARN if m <= 5 else ERR


def _pick_model_tui(tui, current: str, live: dict[str, dict]) -> str | None:
    base = _rows(live, current)
    by_price, name = False, current
    while True:
        rows = sorted(base, key=_cost) if by_price else base
        idx = next((i for i, r in enumerate(rows) if r["name"] == name), 0)
        frs = []
        for r in rows:
            price = price_label(r)
            frs.append([(OK, ("● " if r["name"] == current else "  ")),
                        ("" if r["ok"] else MUTED, f"{r['name']:<31}"), (MUTED, f"{(r['grade'] or '-'):<4}"),
                        (_mult_style(r["mult"], r), f"{price:<12}"),
                        (MUTED, ("vision  " if r["vision"] else "") + ("" if r["ok"] else "unavailable"))])
        res = tui.choose(tr_('pick a model'), frs, idx,
                         hint=tr_('↑↓ select · Enter use · s sort by price · Esc cancel') + (tr_(' · sorted by price') if by_price else ""),
                         keys=("s",))
        if res is None:
            return None
        key, i = res
        name = rows[i]["name"]
        if key == "s":
            by_price = not by_price
            continue
        return name


def pick_model(console: Console, current: str, live: dict[str, dict]) -> str | None:
    """Interactive picker: up/down select, Enter use, s sort by price, Esc cancel."""
    if getattr(console, "tui", None) is not None:
        return _pick_model_tui(console.tui, current, live)
    base = _rows(live, current)
    by_price = False
    idx = next((i for i, r in enumerate(base) if r["name"] == current), 0)

    def ordered() -> list[dict]:
        return sorted(base, key=_cost) if by_price else base

    def render():
        rows = ordered()
        win = 14
        start = max(0, min(idx - win // 2, len(rows) - win))
        t = Table(box=None, padding=(0, 2), header_style=f"bold {LAV}")
        for c in ("", tr_("model"), tr_("grade"), tr_("price"), tr_("note")):
            t.add_column(c)
        for i in range(start, min(len(rows), start + win)):
            r, sel = rows[i], i == idx
            cur = "●" if r["name"] == current else " "
            name = Text(("▸ " if sel else "  ") + r["name"], style=f"bold {ROSE}" if sel else ("" if r["ok"] else MUTED))
            price = Text(price_label(r), style=_mult_style(r["mult"], r))
            note = ("vision  " if r["vision"] else "") + ("" if r["ok"] else "unavailable")
            t.add_row(Text(cur, style=OK), name, r["grade"] or "-", price, Text(note, style=MUTED))
        more = f"{idx + 1}/{len(rows)}" + (tr_('  ·  sorted by price') if by_price else "")
        return Panel(t, title=tr_('[bold {ROSE}]pick a model[/]', ROSE=ROSE), title_align="left", border_style=MUTED,
                     subtitle=tr_('[{MUTED}]↑↓ select · Enter use · s sort by price · Esc cancel · {more}[/]', MUTED=MUTED, more=more),
                     padding=(1, 2))

    chosen = None
    with Live(render(), console=console, transient=True, auto_refresh=False) as lv:
        while True:
            k = ui.read_key()
            n = len(base)
            if k in ("up", "k"):
                idx = (idx - 1) % n
            elif k in ("down", "j"):
                idx = (idx + 1) % n
            elif k == "pgup":
                idx = max(0, idx - 10)
            elif k == "pgdn":
                idx = min(n - 1, idx + 10)
            elif k == "s":
                name = ordered()[idx]["name"]
                by_price = not by_price
                idx = next(i for i, r in enumerate(ordered()) if r["name"] == name)
            elif k == "enter":
                chosen = ordered()[idx]["name"]
                break
            elif k in ("esc", "ctrl-c", "q"):
                break
            lv.update(render(), refresh=True)
    return chosen
