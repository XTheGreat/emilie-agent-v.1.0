"""What the CLI prints (Rich renderables) -> small JSON blocks the desktop UI draws with its own widgets.

    {"t": "text",  "html": "..."}                                   styled text (inline spans, may span lines)
    {"t": "md",    "md": "..."}                                     markdown, rendered by the UI
    {"t": "panel", "title": html, "subtitle": html, "color": css, "body": [blocks]}
    {"t": "table", "head": [html] | None, "rows": [[html]], "title": html}
    {"t": "rule",  "title": html}
    {"t": "pre",   "html": "..."}                                   anything else, as fixed-width text

Unknown renderables still show up (as "pre"), so a new CLI command never needs desktop code to be visible.
"""
from __future__ import annotations

import io
import re
from html import escape

from rich.console import Console, Group
from rich.control import Control
from rich.markdown import Markdown
from rich.padding import Padding
from rich.panel import Panel
from rich.rule import Rule
from rich.style import Style
from rich.table import Table
from rich.text import Text

_C = Console(file=io.StringIO(), width=110, force_terminal=True, color_system="truecolor", legacy_windows=False,
             highlight=False, emoji=False)


def _hex(color, foreground: bool = True) -> str | None:
    if color is None or color.is_default:
        return None
    try:
        return color.get_truecolor(foreground=foreground).hex
    except Exception:
        return None


def style_css(st: Style | None) -> str:
    if not st:
        return ""
    css = []
    fg, bg = _hex(st.color), _hex(st.bgcolor, False)
    if st.reverse:
        fg, bg = bg or "var(--bg-main)", fg or "var(--text)"
    if fg:
        css.append(f"color:{fg}")
    if bg:
        css.append(f"background:{bg}")
    if st.bold:
        css.append("font-weight:600")
    if st.italic:
        css.append("font-style:italic")
    deco = [d for d, on in (("underline", st.underline), ("line-through", st.strike)) if on]
    if deco:
        css.append("text-decoration:" + " ".join(deco))
    if st.dim:
        css.append("opacity:.7")
    return ";".join(css)


def _spans(segments) -> str:
    out, cur_css, buf = [], None, []

    def flush():
        if buf:
            txt = escape("".join(buf))
            out.append(f'<span style="{cur_css}">{txt}</span>' if cur_css else txt)
            buf.clear()
    for seg in segments:
        if seg.control:
            continue
        css = style_css(seg.style)
        if css != cur_css:
            flush()
            cur_css = css
        buf.append(seg.text)
    flush()
    return "".join(out)


def text_of(obj, markup: bool = True) -> Text:
    if isinstance(obj, Text):
        return obj
    if isinstance(obj, str):
        if markup:
            try:
                return Text.from_markup(obj, emoji=False)
            except Exception:
                return Text(obj)
        return Text(obj)
    return Text(str(obj))


def inline_html(obj, markup: bool = True) -> str:
    """One renderable as inline HTML (for titles and table cells)."""
    if obj is None or obj == "":
        return ""
    if isinstance(obj, (str, Text)):
        return _spans(text_of(obj, markup).render(_C, end=""))
    if isinstance(obj, Markdown):
        return escape(obj.markup)
    try:
        return _spans(_C.render(obj, _C.options.update_width(110))).rstrip("\n")
    except Exception:
        return escape(str(obj))


def _border(style) -> str | None:
    try:
        st = Style.parse(style) if isinstance(style, str) else style
        return _hex(st.color) if st else None
    except Exception:
        return None


def to_blocks(obj, markup: bool = True) -> list[dict]:
    if obj is None or isinstance(obj, Control):
        return []
    if isinstance(obj, (str, Text)):
        t = text_of(obj, markup)
        if not t.plain.strip():
            return []
        return [{"t": "text", "html": inline_html(t)}]
    if isinstance(obj, Markdown):
        return [{"t": "md", "md": obj.markup}]
    if isinstance(obj, Panel):
        return [{"t": "panel", "title": inline_html(obj.title), "subtitle": inline_html(obj.subtitle),
                 "color": _border(obj.border_style), "body": to_blocks(obj.renderable, markup)}]
    if isinstance(obj, Table):
        cols = obj.columns
        rows = [[inline_html(c._cells[i]) if i < len(c._cells) else "" for c in cols] for i in range(obj.row_count)]
        head = [inline_html(c.header) for c in cols] if obj.show_header and any(str(c.header) for c in cols) else None
        return [{"t": "table", "head": head, "rows": rows, "title": inline_html(obj.title)}]
    if isinstance(obj, Rule):
        return [{"t": "rule", "title": inline_html(obj.title)}]
    if isinstance(obj, Group):
        return [b for r in obj.renderables for b in to_blocks(r, markup)]
    if isinstance(obj, Padding):
        return to_blocks(obj.renderable, markup)
    try:
        html = _spans(_C.render(obj, _C.options.update_width(110)))
    except Exception:
        html = escape(str(obj))
    return [{"t": "pre", "html": html.rstrip("\n")}] if html.strip() else []


def printed(objects: tuple, markup: bool = True) -> list[dict]:
    """console.print(*objects) -> blocks. Several plain strings/Texts in one call stay on one line, like in a terminal."""
    if all(isinstance(o, (str, Text)) for o in objects):
        t = Text(" ").join(text_of(o, markup) for o in objects)
        return to_blocks(t)
    return [b for o in objects for b in to_blocks(o, markup)]


def plain(objects: tuple, markup: bool = True) -> str:
    out = []
    for o in objects:
        if isinstance(o, (str, Text)):
            out.append(text_of(o, markup).plain)
        elif isinstance(o, Markdown):
            out.append(o.markup)
        elif isinstance(o, Panel):
            out.append(plain((o.renderable,), markup))
    return " ".join(out)


# ---------------------------------------------------------------- prompt_toolkit fragments (pickers)
_HEX = re.compile(r"#[0-9a-fA-F]{6}")


def frags_html(frags) -> str:
    out = []
    for item in frags or []:
        style, txt = (item[0], item[1]) if len(item) >= 2 else ("", str(item))
        css, s = [], str(style or "")
        for tok in s.split():
            if tok == "bold":
                css.append("font-weight:600")
            elif tok == "italic":
                css.append("font-style:italic")
            elif tok.startswith("bg:") and _HEX.fullmatch(tok[3:]):
                css.append(f"background:{tok[3:]}")
            elif tok.startswith("fg:") and _HEX.fullmatch(tok[3:]):
                css.append(f"color:{tok[3:]}")
            elif _HEX.fullmatch(tok):
                css.append(f"color:{tok}")
        txt = escape(str(txt))
        out.append(f'<span style="{";".join(css)}">{txt}</span>' if css else txt)
    return "".join(out)


def frags_text(frags) -> str:
    return "".join(str(item[1]) for item in frags or [] if len(item) >= 2)
