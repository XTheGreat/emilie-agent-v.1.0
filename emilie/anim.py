"""Animated UI components for prompt_toolkit: banner, mascot toolbar, gradient rules.
All functions return 'fragments' [(style, text[, mouse_handler])] that are redrawn
every frame (PromptSession(refresh_interval=...)).
"""
import numpy as np
from prompt_toolkit.mouse_events import MouseEventType

from .i18n import t as tr_
from .logo import Sprite
from .theme import MUTED, ROSE, LAV, flow_hex
from .tools import shorten as _shorten_tools

_H = [f"{i:02x}" for i in range(256)]


def _hx(px) -> str:
    return "#" + _H[px[0]] + _H[px[1]] + _H[px[2]]


# ------------------------------------------------------------------ sprite → fragments
def _click_handler(sprite: Sprite, col0: int, y_px: float, per: int = 1):
    """per = characters per cell: prompt_toolkit reports the CHARACTER index of the click, and in the image mode
    each cell is several characters (placeholder + 2 diacritics)."""
    def handler(ev):
        if ev.event_type == MouseEventType.MOUSE_DOWN:
            sprite.drop((ev.position.x - col0) // per + 0.5, y_px)
            return None
        return NotImplemented
    return handler


ASCII_RAMP = " .,:;-=+*#%@"


def sprite_rows(sprite: Sprite, t: float, col0: int) -> list[list[tuple]]:
    """Fragment lines (each cell = 1 fragment) + click handler -> water drop."""
    if sprite.view is not None and not getattr(sprite.view, "hidden", False):   # image protocol: the picture is sent separately, the grid holds placeholders
        try:
            sprite.render_hd(t)
            st = sprite.view.style()
            return [[(st, line, _click_handler(sprite, col0, r * 2 + 1.0, len(line) // sprite.view.cols))] for r, line in enumerate(sprite.view.cells)]
        except Exception:
            sprite.view = None                        # something went wrong -> fall back to half-block for good
    img, vis = sprite.render(t)
    rows = []
    if getattr(sprite, "ascii", False):               # ASCII mode: one character per cell, picked by brightness, tinted with the real colour
        ramp = ASCII_RAMP
        lum_all = (img.astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)) / 255
        seen = lum_all[vis]
        lo, hi = (np.percentile(seen, 4), np.percentile(seen, 96)) if seen.size else (0.0, 1.0)   # stretch contrast per frame
        span = max(hi - lo, 0.12)
        for y in range(0, sprite.h, 2):
            h = _click_handler(sprite, col0, y + 1.0)
            row = []
            for x in range(sprite.w):
                tv, bv = vis[y, x], vis[y + 1, x]
                if not (tv or bv):
                    row.append(("", " ", h))
                    continue
                px = [p for p, v in ((img[y, x], tv), (img[y + 1, x], bv)) if v]
                c = sum(int(q[0]) for q in px) / len(px), sum(int(q[1]) for q in px) / len(px), sum(int(q[2]) for q in px) / len(px)
                lum = min(1.0, max(0.0, ((lum_all[y, x] + lum_all[y + 1, x]) / 2 - lo) / span))
                ch = ramp[min(len(ramp) - 1, int(lum * len(ramp)))]
                col = "#%02x%02x%02x" % tuple(min(255, int(v * 1.25 + 20)) for v in c)
                row.append((f"fg:{col}", ch, h))
            rows.append(row)
        return rows
    for y in range(0, sprite.h, 2):
        h = _click_handler(sprite, col0, y + 1.0)
        row = []
        for x in range(sprite.w):
            tv, bv = vis[y, x], vis[y + 1, x]
            if tv and bv:
                row.append((f"fg:{_hx(img[y, x])} bg:{_hx(img[y + 1, x])}", "▀", h))
            elif tv:
                row.append((f"fg:{_hx(img[y, x])}", "▀", h))
            elif bv:
                row.append((f"fg:{_hx(img[y + 1, x])}", "▄", h))
            else:
                row.append(("", " ", h))
        rows.append(row)
    return rows


# ------------------------------------------------------------------ teks / klip
def _clip(segs: list[tuple[str, str]], width: int) -> list[tuple[str, str]]:
    out, n = [], 0
    for st, tx in segs:
        if n >= width:
            break
        tx = tx[: width - n]
        out.append((st, tx))
        n += len(tx)
    if n < width:
        out.append(("", " " * (width - n)))
    return out


def rule_fragments(width: int, t: float) -> list[tuple]:
    """Gradient divider line that flows left -> right."""
    return [(f"fg:{flow_hex(x, t)}", "─") for x in range(width)]


def prompt_arrow(t: float) -> tuple[str, str]:
    return (f"bold fg:{flow_hex(0, t)}", "❯ ")


# ------------------------------------------------------------------ banner
def banner_height_estimate() -> int:
    return 25


def banner_fragments(sprite: Sprite, t: float, width: int, info: dict) -> list[tuple]:
    """Banner panel with a flowing gradient border. info: version, model, cwd, effort, mode,
    session, tools{group:[name]}."""
    W = max(60, width)
    lw = sprite.w
    rw = W - 2 - 2 - lw - 3 - 2          # border, pad kiri, kolom logo, jarak, pad kanan

    logo_rows = sprite_rows(sprite, t, col0=1 + 2)
    left: list[list[tuple]] = [list(r) for r in logo_rows]
    left.append([("", " " * lw)])
    for st, tx in [(f"bold {ROSE}", info["model"]), (LAV, info["cwd"]),
                   (MUTED, f"effort {info['effort']} · {info['mode']}"), (MUTED, f"Session: {info['session']}")]:
        if len(tx) > lw:
            tx = "…" + tx[-(lw - 1):]
        left.append(_clip([(st, tx)], lw))

    right: list[list[tuple[str, str]]] = [
        [(f"bold {ROSE}", "Welcome!")],
        [(MUTED, tr_('Tell me what we are building today.'))],
        [],
        [(f"bold {LAV}", "Tools")],
    ]
    for g, names in info["tools"].items():
        right.append([(LAV, f"  {g:<7}"), ("", ", ".join(_shorten_tools(names)))])
    right += [[], [(f"bold {LAV}", "Tips")]]
    for k, v in [(tr_('shift+tab'), tr_('switch mode ask/trust/plan')), ("@file", tr_('include a file')),
                 ("!command", tr_('run a shell command')), ("ctrl+v", tr_('paste an image')),
                 ("/model", tr_('pick a model')), ("/effort", tr_('token saving level')),
                 ("Develop By", "SecretByEnumb"), ("/help", tr_('all commands'))]:
        right.append([(ROSE, f"  {k:<10}"), (MUTED, v)])

    n = max(len(left), len(right))
    left += [[("", " " * lw)] for _ in range(n - len(left))]
    right += [[] for _ in range(n - len(right))]

    def border(ch: str, x: int, bold: bool = False) -> tuple[str, str]:
        return (("bold " if bold else "") + f"fg:{flow_hex(x, t)}", ch)

    out: list[tuple] = []
    # --- atas: ╭─ (=^.^=) Emilie Agent vX ────╮
    title = f" Emilie Agent v{info['version']} "
    for x in range(W):
        if x == 0:
            out.append(border("╭", x))
        elif x == W - 1:
            out.append(border("╮", x))
        elif 2 <= x < 2 + len(title):
            out.append(border(title[x - 2], x, bold=True))
        else:
            out.append(border("─", x))
    out.append(("", "\n"))
    blank = [border("│", 0), ("", " " * (W - 2)), border("│", W - 1), ("", "\n")]
    out += blank
    for i in range(n):
        out.append(border("│", 0))
        out.append(("", "  "))
        out += [c if len(c) == 3 else (c[0], c[1]) for c in left[i]]
        out.append(("", "   "))
        out += _clip(right[i], rw)
        out.append(("", "  "))
        out.append(border("│", W - 1))
        out.append(("", "\n"))
    out += blank
    for x in range(W):
        out.append(border("╰" if x == 0 else "╯" if x == W - 1 else "─", x))
    return out


# ------------------------------------------------------------------ toolbar
def toolbar_fragments(sprite: Sprite | None, t: float, s: dict, compact: bool, hint: str | None = None) -> list[tuple]:
    """Bottom toolbar: animated mascot on the left + status on the right (or 1 line when compact)."""
    mult = f" ×{s['mult']:g}" if s.get("mult") else ""
    ctx = s["ctx"]
    bar_n = 10
    filled = min(bar_n, round(ctx / 100 * bar_n))
    ctx_color = "#3fa66b" if ctx < 60 else "#d99a2b" if ctx < 90 else "#d9534f"
    mode_cls = "bold #d99a2b" if s["mode"] == "plan" else ""

    lines: list[list[tuple]] = [
        [(f"bold fg:{flow_hex(0, t)}", "Emilie"), ("", "  "), ("", f"{s['model']}{mult}")],
        [(MUTED, s["cwd"])],
        [(mode_cls, s["mode_label"]), (MUTED, "  ·  "), ("", f"effort {s['effort']}")],
        [("", "ctx "), (f"fg:{ctx_color}", "█" * filled), (MUTED, "░" * (bar_n - filled)), ("", f" {ctx}%")],
        [(MUTED, tr_('shift+tab mode · @file · !cmd · /help'))],
        [(MUTED, tr_('Develop By: SecretByEnumb · Mouse wheel/PgUp: scroll'))],
    ]
    if hint:                                   # temporary hint (expires automatically)
        lines[4] = [("bold #d99a2b", hint)]
    if compact or sprite is None:
        if hint:
            return [("", " "), ("bold #d99a2b", hint)]
        one: list[tuple] = []
        for i, seg in enumerate([lines[0], lines[2], lines[3]]):
            if i:
                one.append((LAV, "  │  "))
            one += seg
        return [("", " ")] + one

    rows = sprite_rows(sprite, t, col0=1)
    out: list[tuple] = []
    for i, row in enumerate(rows):
        out.append(("", " "))
        out += row
        out.append(("", "   "))
        if i < len(lines):
            out += lines[i]
        if i < len(rows) - 1:
            out.append(("", "\n"))
    return out
