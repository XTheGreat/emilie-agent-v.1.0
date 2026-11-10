"""FULL-SCREEN interface (like Claude Code):

  ┌ header: animated VIDEO logo + info, PINNED at the top (keeps moving during the conversation)
  ├ conversation: its own scroll area (mouse wheel / PageUp / PageDown), follows the bottom automatically
  ├ status: spinner while the agent works / permission choices / Ctrl+C hint
  ├ gradient rule + input box
  └ footer: model · folder · mode · effort · context

The agent runs in a separate thread so the screen stays alive; Ctrl+C stops it.
All Rich output is captured as 'entries' and re-rendered to the window width
(the window grows/shrinks -> the conversation adapts, nothing breaks).
"""
from . import paths, camera
import ctypes
import io
import math
import os
import platform
import queue
import re
import select
import shutil
import sys
import textwrap
import threading
import time
from dataclasses import dataclass, field

import numpy as np
from PIL import Image
from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.completion import merge_completers
from prompt_toolkit.data_structures import Point
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import ANSI, to_formatted_text
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.bindings.mouse import load_mouse_bindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.mouse_events import MouseButton, MouseEventType
from prompt_toolkit.utils import get_cwidth
from prompt_toolkit.layout import ConditionalContainer, Dimension, Float, FloatContainer, HSplit, Layout, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl, UIContent, UIControl
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.layout.processors import BeforeInput, Processor, Transformation
from prompt_toolkit.layout.utils import explode_text_fragments
from prompt_toolkit.output import ColorDepth
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.control import Control
from rich.text import Text

from .i18n import t as tr_
from . import ptfast
from . import anim, clip, logo, ui
from . import talk, trust, voice
from .inputbox import (LONG_CHARS, LONG_LINES, PH_END, PH_IMG, PH_TEXT, MentionCompleter, SlashCompleter,
                       Submission, steady_output)
from .theme import ERR, LAV, MUTED, ROSE, WARN, flow_hex

ptfast.install()

FPS = 12
FPS_CHOICES = (8, 12, 18, 24, 30)
SMOOTH_TAU = 0.075       # smooth-scroll time constant (seconds): smaller = snappier, larger = floatier
CALM_FREEZE = False      # True: freeze animations when idle for CALM_SECS (static screen -> native Shift+drag selection)
CALM_SECS = 2.0         # no key/mouse activity and agent idle for this long -> banner/border/cursor animations freeze
CC_WINDOW = 3.0          # seconds: a second Ctrl+C inside this window = exit
MAX_ENTRIES = 5000
SPRITE_COLS = 16         # minimum logo width (cells); the real size automatically follows the terminal height


class _Null:
    """Fake file for the app's Console: nothing is printed to the terminal directly."""

    def write(self, s):
        return len(s)

    def flush(self):
        pass

    def isatty(self):
        return True


@dataclass
class Entry:
    args: tuple
    kwargs: dict
    cache: dict = field(default_factory=dict)     # width -> (fragments, line_count)
    blink: bool = False                           # True: the bullet of this line blinks (a tool is running)


def _merge(frags) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for item in frags:
        st, tx = item[0], item[1]
        if out and out[-1][0] == st:
            out[-1] = (st, out[-1][1] + tx)
        else:
            out.append((st, tx))
    return out


def render_frags(args: tuple, kwargs: dict, width: int, blink: bool = False) -> tuple[list[tuple[str, str]], int]:
    """Render a Rich renderable -> (prompt_toolkit fragments, line count) at a given width."""
    buf = io.StringIO()
    c = Console(file=buf, force_terminal=True, color_system="truecolor", width=width, legacy_windows=False)
    try:
        c.print(*args, **kwargs)
    except Exception as e:                      # one broken entry must not break the screen
        buf = io.StringIO()
        c = Console(file=buf, force_terminal=True, color_system="truecolor", width=width)
        c.print(tr_('(render failed: {e})', e=e))
    s = buf.getvalue()
    frags = _merge(to_formatted_text(ANSI(s)))
    out: list[tuple[str, str]] = []
    for st, tx in frags:                          # bullet "●" -> dynamic style (blinking, see TUI._style)
        if blink and "●" in tx:
            parts = tx.split("●")
            for i, part in enumerate(parts):
                if i:
                    out.append(("class:wg-bullet bold", "●"))
                if part:
                    out.append((st, part))
        else:
            out.append((st, tx))
    return out, s.count("\n")


def to_lines(frags) -> list[list[tuple]]:
    """Split a list of fragments into lines (once per entry, not every frame)."""
    lines: list[list[tuple]] = [[]]
    for item in frags:
        st, tx = item[0], item[1]
        rest = item[2:]
        parts = tx.split("\n")
        for i, part in enumerate(parts):
            if i:
                lines.append([])
            if part:
                lines[-1].append((st, part, *rest))
    if lines and not lines[-1]:                   # the trailing "\n" is not an extra line
        lines.pop()
    return lines


def render_lines(args: tuple, kwargs: dict, width: int, blink: bool = False) -> tuple[list[list[tuple]], int]:
    frags, _ = render_frags(args, kwargs, width, blink)
    lines = to_lines(frags)
    return lines, len(lines)


def _cells(ch: str) -> int:
    return max(0, get_cwidth(ch))


def cell_slice(text: str, c0: int, c1: int) -> str:
    """The part of `text` that sits in terminal cells [c0, c1) (wide characters count as 2 cells)."""
    out, pos = [], 0
    for ch in text:
        w = _cells(ch)
        if pos >= c1:
            break
        if pos + w > c0:
            out.append(ch)
        pos += w
    return "".join(out)


def highlight(frags, c0: int, c1: int) -> list:
    """Same line, with the cells [c0, c1) drawn in reverse video (the selection)."""
    out, pos = [], 0
    for item in frags:
        st, tx = item[0], item[1]
        run, cur = [], None
        for ch in tx:
            w = _cells(ch)
            inside = c0 <= pos < c1
            if cur is not None and inside != cur and run:
                out.append((st + " reverse" if cur else st, "".join(run)))
                run = []
            cur = inside
            run.append(ch)
            pos += w
        if run:
            out.append((st + " reverse" if cur else st, "".join(run)))
    return out


class LinesControl(UIControl):
    """Conversation control based on a LIST OF READY-MADE LINES.

    The default FormattedTextControl splits ALL fragments into lines on every render (~6x per frame) and
    that is O(conversation length) -> scrolling & streaming get heavy in a long conversation. Here the lines are
    prepared per entry; get_line(i) only fetches one line, so the cost per frame ~ the number of
    VISIBLE lines, not the whole conversation.
    """

    def __init__(self, tui):
        self.tui = tui

    def is_focusable(self) -> bool:
        return False

    def create_content(self, width: int, height: int | None):
        tui = self.tui
        lines = tui._conv_lines()
        blink = tui._blink_idx
        if blink:
            on = "bold fg:#d9689a" if tui._bullet_on() else "bold fg:#f4bfd6"

            def get_line(i: int):
                ln = lines[i]
                if i in blink:
                    return [(on if st.startswith("class:wg-bullet") else st, tx) for st, tx, *_ in ln]
                return ln
        else:
            get_line = lines.__getitem__
        sel = tui._sel_range()
        if sel:
            inner, (r0, c0, r1, c1) = get_line, sel

            def get_line(i: int):
                ln = inner(i)
                if r0 <= i <= r1:
                    return highlight(ln, c0 if i == r0 else 0, (c1 + 1) if i == r1 else 10 ** 6)
                return ln
        return UIContent(get_line=get_line, line_count=len(lines), show_cursor=False,
                         cursor_position=Point(0, tui._top_line()))

    def mouse_handler(self, mouse_event):
        """Click on the logo in the banner (per-cell handler) -> water ripple."""
        full = self.tui._banner_full
        y, x = mouse_event.position.y, mouse_event.position.x
        if 0 <= y < len(full):
            n = 0
            for item in full[y]:
                n += len(item[1])
                if n > x:
                    if len(item) >= 3:
                        return item[2](mouse_event)
                    break
        return NotImplemented


class FakeCursor(Processor):
    """Fake cursor (inverted block) + its own 1 Hz blink. The real terminal cursor is moved around on every
    animation frame so its blink phase keeps being reset (it looks like a fast/uneven blink)."""

    def __init__(self, tui):
        self.tui = tui

    def apply_transformation(self, ti):
        if ti.lineno != ti.document.cursor_position_row:
            return Transformation(ti.fragments)
        pos = ti.source_to_display(ti.document.cursor_position_col)
        frags = explode_text_fragments(ti.fragments)
        if self.tui.cursor_on():
            if pos < len(frags):
                frags[pos] = ((frags[pos][0] + " reverse").strip(), frags[pos][1])
            else:
                frags.append(("reverse", " "))
        return Transformation(frags)


class TUI:
    def __init__(self):
        self.entries: list[Entry] = []
        self.version = 0
        self.lock = threading.RLock()
        self.app: Application | None = None
        self.core = None
        self.queue: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        self.busy = False
        self._running = None
        self.live = None                         # the StreamView that is running (spinner + text tail)
        self.overlay: dict | None = None         # picker (model/session)
        self.perm: dict | None = None            # permission prompt waiting for a key
        self.cc_at = 0.0
        self.cam: camera.Stream | None = None    # video call mode (Alt+V): the camera is open only while this is set
        self._cam_view = None
        self._cam_sent = -1
        self._cam_started = 0.0
        self._last_chat = time.monotonic()       # end of the last turn / glance: the video-call companion waits after it
        self._cam_dims = (24, 6)                 # (cols, rows) of the inline picture, fixed while the call is on
        self.last_edit = 0.0
        self.last_key = 0.0                      # last real key press (not mouse)
        self.follow, self.scroll, self._total = True, 0, 0
        self.last_act, self._frz, self._skew = time.monotonic(), None, 0.0
        self._tgt = None                         # smooth-scroll target line (None = idle)
        self._scroll_ev = threading.Event()
        self._wheel_t, self._wheel_v = 0.0, 3.0
        self._lines, self._lines_key = [], None
        self._body, self._body_key, self._body_blink = [], None, set()
        self._body_users: list = []
        self._tail_lines, self._tail_key = [], None
        self._blink_idx: set = set()
        self._banner_lines, self._banner_full = [], []
        self._banner_cache, self._banner_tick, self._banner_cols, self._banner_rows = None, -1, 0, 8
        self._memo: dict = {}
        self.t0 = time.monotonic()
        self.sprite = None
        self._logo_auto = True
        from .effort import load_settings as _ls
        self.fps = int(_ls().get("fps") or FPS)
        self.ascii = bool(_ls().get("logo_ascii"))
        self.still = bool(_ls().get("logo_still")) and not self.ascii
        self.borders_anim = _ls().get("borders_anim", True) is not False
        self.logo_error: str | None = None
        self.sel: dict | None = None             # text selection: {"a": (row, col), "b": (row, col), "active": bool, "w": width}
        self._click = (-1, -1, 0.0, 0)           # last click (row, col, time, count) for double/triple click
        self._edge = 0                           # -1 / 1: a drag is parked at the top / bottom edge (auto-scroll)
        self.mouse_on = bool(_ls().get("mouse", True))
        self.pastes: dict[int, str] = {}
        self.images: dict[int, tuple[str, str]] = {}
        self.image_meta: dict[int, tuple[tuple[int, int], int]] = {}
        self.image_paths: dict[int, str | None] = {}
        self._nt = self._ni = 0
        self.console = self._make_console()
        self.load_logo()

    # ================================================================ console → entri
    def _make_console(self) -> Console:
        c = Console(file=_Null(), force_terminal=True, color_system="truecolor", width=100, legacy_windows=False)
        c.tui = self                             # ui.py / models.py / stream.py recognise this mode through this attribute

        def tee(*args, **kwargs):
            if any(isinstance(a, Control) for a in args):      # Live/status controls: ignore
                return
            self.add_entry(args, kwargs)
        c.print = tee                            # type: ignore[method-assign]
        return c

    def mark_running(self, running: bool) -> None:
        """The bullet of the LAST tool line blinks while the tool runs; it stops when it finishes."""
        with self.lock:
            if running:
                if self.entries:
                    self._running = self.entries[-1]
                    self._running.blink = True
                    self._running.cache = {}
            elif getattr(self, "_running", None) is not None:
                self._running.blink = False
                self._running.cache = {}
                self._running = None
            self.version += 1
        self._invalidate()

    def add_entry(self, args: tuple, kwargs: dict) -> None:
        with self.lock:
            self.entries.append(Entry(args, kwargs))
            if len(self.entries) > MAX_ENTRIES:
                del self.entries[: len(self.entries) - MAX_ENTRIES]
            self.version += 1
        self._invalidate()

    def clear(self) -> None:
        with self.lock:
            self.entries.clear()
            self.version += 1
        self.follow = True
        self._invalidate()

    def _invalidate(self) -> None:
        if self.app is not None:
            try:
                self.app.invalidate()
            except Exception:
                pass

    def load_logo(self) -> None:
        self.sprite, self.logo_error = None, None
        p = logo.find_logo()
        if not p:
            return
        try:
            from .effort import load_settings
            rows = self._cols_rows()[1]
            fixed = load_settings().get("logo_cols")
            self._logo_auto = not fixed
            cols = int(fixed or self._auto_logo_cols(rows))
            from . import gfx
            hd = gfx.supported() and not paths.env("LOGO_LOWRES") and not self.ascii   # ASCII needs the cell grid, not real pixels
            if logo.needs_decode(p, hd) and not getattr(self, "_announced", False):
                self._announced = True
                sys.stdout.write(tr_('\x1b[2m(=^.^=) preparing the logo video (first run only, a few seconds)...\x1b[0m\n'))
                sys.stdout.flush()
            if self.still:
                sp = logo.find_still()
                src = logo.Source(sp, hd) if sp else logo.Source(p, hd).make_still()
            else:
                src = logo.Source(p, hd)
            self.sprite = logo.Sprite(src, cols, gfx=hd)
            self.sprite.ascii = self.ascii
        except Exception as e:
            self.logo_error = f"{type(e).__name__}: {e}"

    def _reload_logo_keep_time(self) -> None:
        t0 = self.sprite.t0 if self.sprite else None
        self.load_logo()
        if self.sprite:
            self.sprite.t0 = t0 if t0 is not None else -100.0
        self._banner_cache = None
        self._invalidate()

    def set_fps(self, n: int) -> str:
        from .effort import save_settings
        self.fps = max(4, min(60, int(n)))
        save_settings(fps=self.fps)
        self._banner_cache = None
        self._invalidate()
        return tr_('logo fps -> {0}', self.fps)

    def cycle_fps(self) -> str:
        nxt = next((c for c in FPS_CHOICES if c > self.fps), FPS_CHOICES[0])
        return self.set_fps(nxt)

    def set_still(self, still: bool) -> str:
        from .effort import save_settings
        self.still, self.ascii = still, False
        save_settings(logo_still=still, logo_ascii=False)
        self._reload_logo_keep_time()
        return tr_('logo -> still image (low CPU)') if still else tr_('logo -> video')

    def set_ascii(self, on: bool) -> str:
        from .effort import save_settings
        self.ascii, self.still = on, False
        save_settings(logo_ascii=on, logo_still=False)
        self._reload_logo_keep_time()
        return tr_('logo -> ASCII video') if on else tr_('logo -> video')

    def cycle_logo_mode(self) -> str:
        """Alt+I: video -> still -> ASCII -> video."""
        if self.ascii:
            return self.set_still(False)
        if self.still:
            return self.set_ascii(True)
        return self.set_still(True)

    # ================================================================ helpers
    @staticmethod
    def _auto_logo_cols(rows: int) -> int:
        return min(44, max(SPRITE_COLS, int(rows * 0.8)))
    def _ft(self) -> float:
        """Time for the border/gradient effect. Disabled -> 0 (static colours), so no redraw is needed."""
        return self._t() if self.borders_anim else 0.0

    # ================================================================ own text selection (no Shift needed)
    def _sel_range(self):
        """Normalised selection (row0, col0, row1, col1) or None. Dropped if the window width changed (lines re-wrapped)."""
        s = self.sel
        if not s:
            return None
        if s["w"] != self._conv_width():
            self.sel = None
            return None
        a, b = s["a"], s["b"]
        if a > b:
            a, b = b, a
        return a[0], a[1], b[0], b[1]

    def _sel_text(self) -> str:
        r = self._sel_range()
        if not r:
            return ""
        r0, c0, r1, c1 = r
        lines = self._lines
        out = []
        for i in range(r0, min(r1, len(lines) - 1) + 1):
            tx = "".join(it[1] for it in lines[i])
            a = c0 if i == r0 else 0
            b = (c1 + 1) if i == r1 else 10 ** 6
            out.append(cell_slice(tx, a, b).rstrip())
        return "\n".join(out).strip("\n")

    def copy_selection(self) -> bool:
        text = self._sel_text()
        if not text:
            return False
        ok = clip.copy_text(text)
        try:                                      # also OSC 52: works over ssh and in terminals without xclip/wl-copy
            import base64
            if len(text) < 100_000 and self.app is not None:
                self.app.output.write_raw("\x1b]52;c;" + base64.b64encode(text.encode()).decode() + "\x07")
                self.app.output.flush()
                ok = True
        except Exception:
            pass
        self.flash(tr_("copied {0} characters", len(text)) if ok else tr_("could not copy (install xclip or wl-clipboard)"))
        return ok

    def _word_cols(self, row: int, col: int) -> tuple[int, int]:
        tx = "".join(it[1] for it in self._lines[row])
        pos, start, end = 0, 0, 0
        spans = []
        for ch in tx:
            w = _cells(ch)
            spans.append((pos, pos + w, ch))
            pos += w
        hit = next((i for i, (a, b, _c) in enumerate(spans) if a <= col < b), None)
        if hit is None or spans[hit][2].isspace():
            return col, col
        i = j = hit
        while i > 0 and not spans[i - 1][2].isspace():
            i -= 1
        while j < len(spans) - 1 and not spans[j + 1][2].isspace():
            j += 1
        return spans[i][0], spans[j][1] - 1

    def _on_float(self, y: int, x: int) -> bool:
        """Is screen cell (y, x) on the sticky prompt bar or the 'Jump to bottom' button (they have their own click)?"""
        vh, cols = self._conv_vh(), self._cols_rows()[0]
        if y == 0 and self._sticky_msg() is not None:
            return True
        if y == vh - 1 and self._scrolled_up():
            w = len(tr_(" Jump to bottom (ctrl+End) ↓ "))
            return (cols - w) // 2 <= x < (cols - w) // 2 + w
        return False

    def _selection_event(self, b: int, x: int, y: int, kind: str) -> bool:
        """Mouse selection from RAW screen coordinates (0-based x, y). Returns True if the event was used.

        The library's own position is not used on purpose: on an EMPTY line it reports (0, 0), which made a drag
        across a blank row look like a jump to the top of the conversation."""
        vh, nb, n, s = self._conv_vh(), len(self._banner_lines), len(self._lines), self.sel
        if kind == "M" and b == 0:                                    # left button pressed
            top = self._top_line()
            if y >= vh or self._on_float(y, x) or not (nb <= top + y < n):
                if y < vh:
                    self.sel = None                                    # a click on the banner/logo: not a selection
                return False
            row = top + y
            now = time.monotonic()
            last = self._click
            count = last[3] + 1 if (now - last[2] < 0.45 and (last[0], last[1]) == (row, x)) else 1
            self._click = (row, x, now, min(count, 3))
            w = self._conv_width()
            if count == 2:
                c0, c1 = self._word_cols(row, x)
                self.sel = {"a": (row, c0), "b": (row, c1), "active": True, "w": w}
            elif count >= 3:
                self.sel = {"a": (row, 0), "b": (row, 10 ** 6), "active": True, "w": w}
            else:
                self.sel = {"a": (row, x), "b": (row, x), "active": True, "w": w, "moved": False}
            self._edge = 0
            self._invalidate()
            return True
        if not (s and s.get("active")):
            return False
        if kind == "M" and (b & 32) and (b & 3) == 0 and not (b & 64):   # dragging with the left button held
            top = self._top_line()
            self._edge = -1 if y <= 0 else (1 if y >= vh - 1 else 0)      # at/over an edge: the scroller thread takes over
            row = top + min(max(y, 0), vh - 1)
            s["b"] = (max(nb, min(n - 1, row)), x)
            s["moved"] = True
            self._invalidate()
            return True
        if kind == "m":                                               # button released (anywhere, even over the input box)
            self._edge = 0
            self._finish_selection()
            return True
        return kind == "M" and b in (35, 34)                          # motion without a button: ignore

    def _autoscroll_loop(self) -> None:
        """While a drag is parked at the top/bottom edge, keep scrolling and extending the selection."""
        while True:
            time.sleep(0.05)
            s = self.sel
            if not (s and s.get("active")) or not self._edge:
                continue
            vh, nb, n = self._conv_vh(), len(self._banner_lines), len(self._lines)
            self.scroll_by(self._edge, smooth=False)
            top = self._top_line()
            row = top + (0 if self._edge < 0 else vh - 1)
            s["b"] = (max(nb, min(n - 1, row)), s["b"][1])
            self._invalidate()

    def _finish_selection(self) -> None:
        s = self.sel
        if not s or not s.get("active"):
            return
        s["active"] = False
        if s["a"] == s["b"] and not s.get("moved") and self._click[3] == 1:
            self.sel = None                       # a plain click selects nothing
        elif self._sel_text():
            self.copy_selection()
        self._invalidate()

    def refresh_language(self) -> None:
        """After /language: rebuild the banner and re-render every cached entry."""
        self._banner_cache = None
        self._lines_key = None
        self._body_key = None
        with self.lock:
            for e in self.entries:
                e.cache = {}
            self.version += 1
        self._invalidate()

    def set_mouse(self, on: bool) -> str:
        from .effort import save_settings
        self.mouse_on = on
        self.sel = None
        save_settings(mouse=on)
        self._invalidate()
        return (tr_("mouse ON: wheel scrolls, drag selects and copies inside the app")
                if on else tr_("mouse OFF: the terminal selects text natively; scroll with PageUp / PageDown"))

    def set_borders(self, on: bool) -> str:
        from .effort import save_settings
        self.borders_anim = on
        save_settings(borders_anim=on)
        self._banner_cache = None
        self._lines_key = None
        self._invalidate()
        return tr_('animated borders ON (more CPU)') if on else tr_('animated borders OFF (saves CPU)')

    def _bullet_on(self) -> bool:
        """The tool bullet blinks at 1 Hz."""
        return int(self._t() * 2) % 2 == 0

    def cursor_on(self) -> bool:
        """Stays lit for a moment after typing, then blinks at 1 Hz."""
        now = self._t()
        return (now - self.last_edit) < 0.6 or int(now * 2) % 2 == 0
    def _calm(self, now: float | None = None) -> bool:
        """True when nothing is going on: the user is not typing/moving the mouse and the agent is idle.
        Then every animation freezes, so the screen stops changing and native Shift+drag selection works."""
        if not CALM_FREEZE:
            return False
        now = time.monotonic() if now is None else now
        return (not self.busy and self.overlay is None and self.perm is None and self.cam is None
                and now - self.last_act > CALM_SECS)

    def touch(self) -> None:
        """Register user activity (key / mouse): animations resume."""
        self.last_act = time.monotonic()

    def _t(self) -> float:
        """Animation clock. Stops while calm and resumes seamlessly (the paused time is skipped)."""
        now = time.monotonic()
        if self._calm(now):
            if self._frz is None:
                self._frz = now
            return self._frz - self.t0 - self._skew
        if self._frz is not None:
            self._skew += now - self._frz
            self._frz = None
        return now - self.t0 - self._skew

    def _memoized(self, name: str, build):
        key = int(self._t() * 30)
        hit = self._memo.get(name)
        if hit and hit[0] == key:
            return hit[1]
        val = build()
        self._memo[name] = (key, val)
        return val

    @staticmethod
    def _cols_rows() -> tuple[int, int]:
        s = shutil.get_terminal_size()
        return s.columns, s.lines

    # ================================================================ banner (part of the scrolled content)
    ART_CREDIT = [("art by: ", "buro moon"), ("animated by: ", "mikarileaf")]     # shown at the right end of the banner
    ART_CREDIT_W = 1 + max(len(a) + len(b) for a, b in ART_CREDIT)

    def _build_banner(self) -> list:
        """Banner = video logo + info + ASCII art. Scrolls together with the conversation."""
        t = self._t()
        cols, rows = self._cols_rows()
        if self.sprite and self._logo_auto and abs(self._auto_logo_cols(rows) - self.sprite.w) >= 4:
            old_t0 = self.sprite.t0
            self.load_logo()                     # the window was resized -> the logo adapts
            if self.sprite:
                self.sprite.t0 = old_t0 if old_t0 is not None else -100.0
        info, st = self.core.banner_info(), self.core.status()
        mult = f" x{st['mult']:g}" if st.get("mult") else ""
        title = [(f"bold {ROSE}", "(=^.^=) Emilie Agent"), (MUTED, f" v{info['version']}")]
        out: list[tuple] = []
        if self.sprite and cols >= 60:
            n = self.sprite.rows
            ag = self.core.agent
            from urllib.parse import urlparse
            from . import config, models as _models
            grade, mult_v = _models.BANKAI.get(st["model"], (None, None))
            host = urlparse(config.BASE_URL or "").netloc or config.PROVIDER
            ctx, lim = st["ctx"], ag.effort.compact_at
            filled = min(10, round(ctx / 10))
            cc = "#3fa66b" if ctx < 60 else "#d99a2b" if ctx < 90 else "#d9534f"
            tg = ", ".join(info["tools"])
            ntools = sum(len(v) for v in info["tools"].values())
            mem = ", ".join(f.name for f in ag.memory_files) or "none"
            vis = config.VISION_MODEL or "-"
            term = "truecolor" if os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit") else "256-color"
            fps = tr_('video @ {0}fps', self.fps) if self.sprite.src.is_video else tr_('still image')
            if self.ascii:
                fps = "ASCII " + fps
            if self.sprite.view is not None:
                term, fps = "kitty-gfx HD", (f"{self.sprite.src.fps:g}fps" if self.sprite.src.is_video else fps)

            from . import mcp as _mcp, skills as _skills
            sk_names = list(_skills.SKILLS)
            sk_txt = (f"{len(sk_names)}  ({', '.join(sk_names[:3])}{', ...' if len(sk_names) > 3 else ''})"
                      if sk_names else tr_('0  (add .emilie/skills/<name>/SKILL.md)'))
            up = int(time.monotonic() - self.t0)

            def kv(k, v, vs=""):
                return [(LAV, f"{k:<9}"), (vs, v)]

            def hdr(text: str, w: int = 34):
                """=-=-=-= judul =-=-=-=  (simetris; sisi kanan adalah cermin sisi kiri)"""
                side = max(3, (w - len(text) - 2) // 2)
                pat = ("=-" * side)[:side]
                return [(MUTED, pat + " "), (f"bold {LAV}", text), (MUTED, " " + pat[::-1])]
            ident = [
                title,
                [(f"bold {ROSE}", f"{st['model']}{mult}")],
                kv(tr_('grade'), tr_('{0}   price {1}', grade or '-', ('x%g' % mult_v) if mult_v else '?')),
                kv(tr_('vision'), vis),
                kv(tr_('folder'), st["cwd"]),
                kv(tr_('session'), info["session"]),
            ]
            keys = [
                [(ROSE, "shift+tab"), (MUTED, " mode   "), (ROSE, "@file"), (MUTED, " attach   "), (ROSE, "!cmd"), (MUTED, " shell")],
                [(ROSE, "ctrl+v/alt+p"), (MUTED, " image   "), (ROSE, "/model"), (MUTED, " model   "), (ROSE, "/skills"), (MUTED, " skills")],
                [(ROSE, "alt +/-"), (MUTED, " size  "), (ROSE, "f"), (MUTED, " fps  "), (ROSE, "i"), (MUTED, " still  "), (ROSE, "b"), (MUTED, " glow  "), (ROSE, "c"), (MUTED, " camera  "), (ROSE, "v"), (MUTED, " call")],
                [(ROSE, "ctrl+c"), (MUTED, " stop   "), (ROSE, "pgup/pgdn"), (MUTED, " scroll   "), (ROSE, "/help"), (MUTED, " all")],
            ]
            credit = self._credit_box(self._ft())
            sys_rows = [
                kv(tr_('provider'), host),
                kv(tr_('effort'), tr_('{0}  ({1:,} out, {2} rounds)', st['effort'], ag.effort.max_output, ag.effort.max_rounds)),
                [(LAV, f"{'context':<9}"), (cc, "#" * filled), (MUTED, "." * (10 - filled)), ("", f" {ctx}%  of {lim // 1000}k")],
                kv(tr_('mode'), st["mode_label"], "bold #d99a2b" if st["mode"] == "plan" else ""),
            ]
            ext_rows = [
                kv(tr_('tools'), f"{ntools}  ({tg})"),
                kv(tr_('skills'), sk_txt),
                kv("mcp", _mcp.summary()),
                kv(tr_('memory'), mem),
            ]
            tele_rows = [
                kv(tr_('render'), f"{term}, {fps}"),
                kv(tr_('display'), tr_('{cols}x{rows}  logo {0}x{1}px', self.sprite.w, self.sprite.h, cols=cols, rows=rows)),
                kv(tr_('history'), tr_('{0} messages  ({1} entries)', len(ag.messages), len(self.entries))),
                kv(tr_('tokens'), f"{ag.usage.inp:,} in / {ag.usage.out:,} out" + ("" if ag.usage.exact else " (est.)")),
                kv(tr_('runtime'), tr_('python {0}  pid {1}  up {2}m{3:02d}s', platform.python_version(), os.getpid(), up // 60, up % 60)),
            ]
            left = ident + [hdr("controls")] + keys + [[]] + credit
            right = [hdr("runtime")] + sys_rows + [hdr("extensions")] + ext_rows + [hdr("telemetry")] + tele_rows

            def fit(lines: list, limit: int, keep: int = 5) -> list:
                """Trim to fit; the credit box (keep the last line) is ALWAYS kept.
                Blank lines are dropped first, then shortcuts from the bottom (the identity at the top is kept)."""
                head, tail = list(lines[:-keep]), list(lines[-keep:])
                limit -= keep
                for i in range(len(head) - 1, -1, -1):
                    if len(head) <= limit:
                        break
                    if not head[i]:
                        del head[i]
                i = len(head) - 1
                while len(head) > limit and i >= 2:
                    del head[i]
                    i -= 1
                return head + tail
            avail = max(20, cols - self.sprite.w - 6)
            cat = cols >= 100 and avail - self.ART_CREDIT_W >= 80      # only when it does not cost the second column
            catw = self.ART_CREDIT_W if cat else 0
            twocol = avail - catw >= 80
            colw = (avail - catw) // 2 if twocol else avail - catw
            if not twocol:                       # single column: identity + important runtime info, then keys, then the credit
                left, right = ident + sys_rows + ext_rows + keys + credit, []
            left = fit(left, n)
            right = right[:n]
            for i, row in enumerate(anim.sprite_rows(self.sprite, t, col0=1)):
                out.append(("", " "))
                out += row
                out.append(("", "   "))
                # the left column is filled evenly to follow the logo height (leftover lines are blanked neatly)
                L = left[i] if i < len(left) else []
                out += anim._clip(L, colw)
                if twocol:
                    R = right[i] if i < len(right) else []
                    out += anim._clip(R, colw)
                if cat and 1 <= i <= len(self.ART_CREDIT):
                    label, who = self.ART_CREDIT[i - 1]
                    out += [("", " "), (MUTED, label), (f"bold {ROSE}", who)]
                out.append(("", "\n"))
        else:                                    # narrow terminal: compact banner
            out += [("", " ")] + title + [(MUTED, f"  {st['model']}{mult}")] + [("", "\n")]
            out += [("", " "), (MUTED, "Develop By "), (f"bold {ROSE}", "SecretByEnumb"), ("", "\n")]
        out += anim.rule_fragments(cols, self._ft())
        out.append(("", "\n"))
        from . import mcp as _m, skills as _s
        nt = sum(len(v) for v in info["tools"].values())
        pl = lambda n, w: f"{n} {w}" + ("" if n == 1 else "s")
        out += [("", " "), (f"bold {ROSE}", pl(nt, "tool")), (MUTED, " · "), (f"bold {ROSE}", pl(len(_s.SKILLS), "skill")),
                (MUTED, " · "), (f"bold {ROSE}", pl(len(_s.COMMANDS), "command")), (MUTED, " · "),
                (f"bold {ROSE}", f"{len(_m.SERVERS)} MCP"), (MUTED, tr_(' · /help for commands')), ("", "\n")]
        self._banner_rows = sum(f[1].count("\n") for f in out)
        return out

    def _credit_box(self, t: float, w: int = 34) -> list:
        """Credit box: ASCII cat (blinking eyes) + a gradient-coloured name; the box border flows."""
        blink = self.borders_anim and (t % 4.5) > 4.25
        eyes = "-.-" if blink else "o.o"
        cat = [r" /\_/\ ", f"( {eyes} )", r" > ^ < "]

        def border(chars: str, x0: int = 0):
            return [(f"fg:{flow_hex(x0 + i, t, scale=0.03, speed=0.18)}", c) for i, c in enumerate(chars)]
        inner = w - 2
        name = "SecretByEnumb"
        rows = []
        rows.append(border("╭" + "─" * inner + "╮"))
        texts = [
            [(MUTED, "Develop By")],
            [(f"bold fg:{flow_hex(i, t, scale=0.08, speed=0.35)}", ch) for i, ch in enumerate(name)],
            [(MUTED, "github/SecretByEnumb")],
        ]
        for i in range(3):
            body = [(f"fg:{ROSE}", cat[i]), ("", "  ")] + texts[i]
            body = anim._clip(body, inner - 1)
            rows.append(border("│", 0) + [("", " ")] + body + border("│", w - 1))
        rows.append(border("╰" + "─" * inner + "╯"))
        return rows

    # ================================================================ conversation
    def _tail_text(self) -> str:
        lv = self.live
        if lv is not None and lv.buf.strip():
            return re.sub(r"</?say>", "", "\n".join(lv.buf.splitlines()[-40:]), flags=re.I)
        return ""

    def _conv_width(self) -> int:
        w = self.conv_win.render_info
        return max(20, w.window_width) if w else self._cols_rows()[0]

    def _conv_vh(self) -> int:
        w = self.conv_win.render_info
        return max(1, w.window_height) if w else max(5, self._cols_rows()[1] - 10)

    def banner_visible(self) -> bool:
        return self._top_line() < self._banner_rows

    def _conv_lines(self) -> list:
        """All conversation lines (banner + entries + streaming tail). Built incrementally & cached."""
        width = self._conv_width()
        # --- body: rebuilt only when entries/width change (not every frame / every scroll) ---
        bkey = (self.version, width)
        if bkey != self._body_key:
            with self.lock:
                entries = list(self.entries)
            lines: list = []
            blink: set = set()
            users: list = []
            for e in entries:
                a0 = e.args[0] if e.args else None
                if isinstance(a0, Text) and a0.plain.startswith("❯ "):
                    users.append((len(lines), a0.plain[2:]))          # (first line, text) of the user message
                hit = e.cache.get(width)
                if hit is None:
                    hit = render_lines(e.args, e.kwargs, width, e.blink)
                    e.cache = {width: hit}           # keep only the latest width (saves memory)
                if e.blink:
                    blink.update(range(len(lines), len(lines) + hit[1]))
                lines.extend(hit[0])
            self._body, self._body_blink, self._body_key = lines, blink, bkey
            self._body_users = users
            self.console.width = width
        # --- streaming tail (small): re-rendered only when its text changes ---
        tail = self._tail_text()
        if tail != self._tail_key:
            self._tail_lines = render_lines((Text(tail),), {}, width)[0] if tail else []
            self._tail_key = tail
        # --- banner: redrawn ONLY when visible; off-screen its animation stops (saves CPU) ---
        cols = self._cols_rows()[0]
        if self._banner_cache is None or self._banner_cols != cols or self.banner_visible():
            rate = self.fps if (self.sprite is not None and self.sprite.animating) else (4 if self.borders_anim else 1)
            tick = int(self._t() * rate)
            if self._banner_cache is None or self._banner_cols != cols or tick != self._banner_tick:
                self._banner_cache, self._banner_tick, self._banner_cols = self._build_banner(), tick, cols
                self._banner_full = to_lines(self._banner_cache)                    # with click handlers
                self._banner_lines = [[(i[0], i[1]) for i in ln] for ln in self._banner_full]
        key = (bkey, self._tail_key, self._banner_tick, self._banner_cols)
        if key != self._lines_key:
            nb = len(self._banner_lines)
            self._lines = self._banner_lines + self._body + self._tail_lines
            self._blink_idx = {nb + i for i in self._body_blink}
            self._lines_key = key
        self._total = len(self._lines)
        return self._lines

    def _sticky_msg(self):
        """(text, line) of the last user message above the viewport, only once scrolled up."""
        mx = max(0, self._total - self._conv_vh())
        if self.follow or mx <= 0 or self.overlay is not None:
            return None
        top = self._top_line()
        if top >= mx:
            return None
        nb = len(self._banner_lines)
        marks = [(nb + a, t) for a, t in getattr(self, "_body_users", [])]
        above = [m for m in marks if m[0] < top]
        if above:
            return above[-1][1], above[-1][0]
        if marks and top >= self._banner_rows:
            return marks[-1][1], marks[-1][0]
        return None

    def _sticky_frags(self):
        m = self._sticky_msg()
        if not m:
            return []
        w = max(10, self._conv_width())
        txt = " ".join(m[0].split())
        room = w - 4
        if len(txt) > room:
            txt = txt[: max(1, room - 1)] + "…"
        line = m[1]
        def go(me, ln=line):
            if me.event_type == MouseEventType.MOUSE_UP:
                self._tgt = None
                self.scroll, self.follow = max(0, ln), False
                self._invalidate()
        return [(f"bold {ROSE}", " ❯ ", go), (MUTED, txt.ljust(w - 3), go)]

    def _jump_frags(self):
        def go(me):
            if me.event_type == MouseEventType.MOUSE_UP:
                self._tgt = None
                self.follow = True
                self._invalidate()
        return [("bold #e6e6e6", tr_(' Jump to bottom (ctrl+End) ↓ '), go)]

    def _scrolled_up(self) -> bool:
        mx = max(0, self._total - self._conv_vh())
        return (not self.follow) and mx > 0 and self._top_line() < mx and self.overlay is None

    def _top_line(self) -> int:
        mx = max(0, self._total - self._conv_vh())
        return mx if self.follow else min(self.scroll, mx)

    def talk_busy(self) -> bool:
        return self.busy or self.perm is not None or self.overlay is not None or voice.VOICE.speaking()

    def talk_toggle(self) -> str:
        return talk.TALK.toggle(self.submit_spoken, self.talk_busy, self._invalidate,
                                lambda m: self.console.print(f"[{MUTED}]{m}[/]"))

    def submit_spoken(self, text: str) -> None:
        """A turn spoken in talk mode: shown and sent exactly like a typed message."""
        self.touch()                         # speaking counts as being there (the call does not time out)
        sub = self._make_submission(text)
        self.console.print()
        self.console.print(Text.assemble(("❯ ", f"bold {ROSE}"), (text[:600], "bold")))
        self.follow = True
        self.queue.put(sub)

    def scroll_by(self, n: int, smooth: bool = True) -> None:
        """Scroll n lines. smooth=True: set a target, the animator thread eases toward it (no jumps)."""
        mx = max(0, self._total - self._conv_vh())
        if not smooth:
            self._tgt = None
            new = max(0, min(mx, self._top_line() + n))
            self.scroll, self.follow = new, new >= mx
            self._invalidate()
            return
        base = self._tgt if self._tgt is not None else self._top_line()
        self._tgt = max(0, min(mx, base + n))
        if self.follow and self._tgt < mx:        # leave "follow" now, but stay on the same line (no jump)
            self.scroll, self.follow = self._top_line(), False
        self._scroll_ev.set()

    def _wheel(self, direction: int) -> None:
        """Mouse wheel tick with mild acceleration: slow flicks = 2 lines, a fast spin ramps up to 8."""
        now = time.monotonic()
        gap = now - self._wheel_t
        self._wheel_t = now
        self._wheel_v = min(12.0, self._wheel_v + 1.5) if gap < 0.09 else 3.0
        self.scroll_by(direction * int(self._wheel_v))

    def _smooth_loop(self) -> None:
        """Time-based exponential ease-out on a FLOAT position (sub-line precision), drawn as whole lines.
        Speed depends on real elapsed time (dt), not on frame count, so a slow frame never makes the motion
        stutter or slow down; a redraw is only requested when the visible line actually changes."""
        tau, poll = SMOOTH_TAU, 1 / 120
        while True:
            self._scroll_ev.wait()
            self._scroll_ev.clear()
            pos, last = float(self._top_line()), time.monotonic()
            while self._tgt is not None:
                if self.follow:                   # something else (submit, ctrl+End, ...) took over -> stop easing
                    self._tgt = None
                    break
                now = time.monotonic()
                dt, last = min(0.05, now - last), now
                mx = max(0, self._total - self._conv_vh())
                want = self._tgt
                tgt = min(want, mx)
                if abs(self.scroll - round(pos)) > 1:          # position was moved from outside: resync
                    pos = float(self._top_line())
                pos += (tgt - pos) * (1.0 - math.exp(-dt / tau))
                if abs(tgt - pos) < 0.5:                       # landed
                    pos = float(tgt)
                    if self._tgt == want:                      # no new wheel input arrived meanwhile
                        self._tgt = None
                        if tgt >= mx:
                            self.follow = True
                line = int(round(pos))
                if line != self.scroll or self._tgt is None:
                    self.scroll = line
                    self._invalidate()
                time.sleep(poll)

    # ================================================================ status / input / footer
    def flash(self, msg: str, secs: float = 2.5) -> None:
        """Short message on the status row (e.g. the result of Alt+F)."""
        self._flash = (msg, time.monotonic() + secs)
        self._invalidate()

    def _status_frags(self):
        fl = getattr(self, "_flash", None)
        if fl and time.monotonic() < fl[1] and self.perm is None and self.live is None:
            return [("", " "), (f"bold {ROSE}", fl[0])]
        if self.perm is not None:
            return [("", " ")] + self.perm["frags"]
        if self.live is not None:
            return [("", " ")] + self.live.status_fragments()
        if time.monotonic() - self.cc_at < CC_WINDOW:
            return [("", " "), ("bold #d99a2b", tr_('press Ctrl+C again to exit'))]
        if self.busy:
            return [("", " "), (MUTED, tr_('working… (Ctrl+C stops)'))]
        if talk.TALK.on:
            st = talk.TALK.state
            txt, col = {"hearing": (tr_('(o_o) hearing you…'), f"bold {ROSE}"),
                        "transcribing": (tr_("(._.) understanding…"), f"bold {ROSE}"),
                        "paused": ("(^_^) …", MUTED)}.get(st, (tr_('(o_o) listening… just talk, pause to send'), f"bold {ROSE}"))
            return [("", " "), (col, txt), (MUTED, tr_('   · /talk off to stop'))]
        return [("", " ")]

    def _rule_frags(self):
        return anim.rule_fragments(self._cols_rows()[0], self._ft())

    def _prompt_frags(self):
        return [anim.prompt_arrow(self._ft())]

    def _input_height(self) -> Dimension:
        cols = max(20, self._cols_rows()[0])
        n = sum(max(1, -(-(len(line) + (2 if i == 0 else 0)) // cols))
                for i, line in enumerate(self.buf.text.split("\n")))
        n = min(8, max(1, n))
        return Dimension(min=n, preferred=n, max=n)

    @staticmethod
    def _git_branch() -> str | None:
        d = os.getcwd()
        while True:
            h = os.path.join(d, ".git", "HEAD")
            if os.path.isfile(h):
                try:
                    ref = open(h).read().strip()
                except OSError:
                    return None
                return ref.split("/")[-1] if ref.startswith("ref:") else ref[:7]
            parent = os.path.dirname(d)
            if parent == d:
                return None
            d = parent

    def _footer_frags(self):
        def build():
            st = self.core.status()
            ag = self.core.agent
            mult = f" x{st['mult']:g}" if st.get("mult") else ""
            mode_cls = "bold #d99a2b" if st["mode"] == "plan" else ""
            alt = (LAV, " | ")
            up = int(time.monotonic() - self.t0)
            branch = self._git_branch()
            segs = [[("", " "), (f"bold {ROSE}", "(^_^) "), ("", f"{st['model']}{mult}")],
                    [(MUTED, st["cwd"])] + ([(LAV, f"  git:{branch}")] if branch else []),
                    [(mode_cls, st["mode_label"])],
                    [("", f"effort {st['effort']}")],
                    [("", f"ctx {st['ctx']}%")],
                    [(MUTED, f"tok {ag.usage.inp + ag.usage.out:,}")],
                    [(MUTED, f"up {up // 60}m")]]
            width = self._cols_rows()[0] - 2
            out, used = [], 0
            for i, sg in enumerate(segs):            # the last segment is dropped first when narrow
                ln = sum(len(x[1]) for x in sg) + (3 if i else 0)
                if used + ln > width and i >= 3:
                    break
                out += ([alt] if i else []) + sg
                used += ln
            return out
        return self._memoized("footer", build)

    # ================================================================ overlay (picker)
    def _overlay_frags(self):
        o = self.overlay
        if o is None:
            return []
        cols, rows = self._cols_rows()
        W = min(cols - 4, 100)
        inner = W - 4
        t = self._t()
        n = len(o["rows"])
        win = max(3, min(n, rows - 10, 16))
        start = max(0, min(o["idx"] - win // 2, n - win))
        out: list[tuple] = []
        t = self._ft()

        def border(ch, x):
            return (f"fg:{flow_hex(x, t)}", ch)
        title = f" {o['title']} "
        for x in range(W):
            out.append(border("╭" if x == 0 else "╮" if x == W - 1 else
                              (title[x - 2] if 2 <= x < 2 + len(title) else "─"), x))
        out.append(("", "\n"))
        for i in range(start, start + win):
            sel = i == o["idx"]
            segs = [(("bold " + st) if sel and st else ("bold" if sel else st), tx) for st, tx in o["rows"][i]]
            segs = [(f"bold {ROSE}", "▸ " if sel else "  ")] + segs
            out.append(border("│", 0))
            out.append(("", " "))
            out += anim._clip(segs, inner)
            out.append(("", " "))
            out.append(border("│", W - 1))
            out.append(("", "\n"))
        for x in range(W):
            out.append(border("╰" if x == 0 else "╯" if x == W - 1 else "─", x))
        out.append(("", "\n"))
        out.append((MUTED, (f" {o['hint']}  ({o['idx'] + 1}/{n})")[:W]))
        return out

    def choose(self, title: str, rows: list, idx: int = 0, hint: str | None = None,
               keys: tuple = ()):
        """Modal picker; CALLED from the worker thread. Returns None (cancelled) or (key, index)."""
        hint = hint or tr_('↑↓ select · Enter ok · Esc cancel')
        ev = threading.Event()
        st = {"title": title, "rows": rows, "idx": idx, "hint": hint, "keys": set(keys), "result": None, "ev": ev}
        self.overlay = st
        self._invalidate()
        try:
            while not ev.wait(0.1):
                pass
        finally:
            self.overlay = None
            self._invalidate()
        return st["result"]

    # ================================================================ izin
    def ask_permission(self, name: str, args: dict, reason: str) -> str:
        panel, opts = ui.permission_panel(name, args, reason)
        self.console.print(panel)
        frags = []
        for span_text, style in _text_segments(opts):
            frags.append((style, span_text))
        ev = threading.Event()
        st = {"frags": frags, "reason": bool(reason), "ev": ev, "result": None}
        self.perm = st
        self._invalidate()
        try:
            while not ev.wait(0.1):
                pass
        finally:
            self.perm = None
            self._invalidate()
        if st["result"] == "interrupt":
            self.console.print(tr_('  [{MUTED}]→ stopped[/]', MUTED=MUTED))
            raise KeyboardInterrupt
        self.console.print(f"  [{MUTED}]→ {tr_(ui.ANS_LABEL[st['result']])}[/]")
        return st["result"]

    # ================================================================ paste / image
    def _add_image(self, buf, data: bytes) -> None:
        try:
            size = Image.open(io.BytesIO(data)).size
            enc = clip.encode_image(data)
        except Exception:
            return
        self._ni += 1
        self.images[self._ni] = enc
        self.image_meta[self._ni] = (size, len(data))
        self.image_paths[self._ni] = clip.save_image(data)
        buf.insert_text(f"[Image #{self._ni}] ")

    def _take_photo(self, buf) -> None:
        """Alt+C: ONE photo from the camera -> [Image #n] in the message being typed. The camera is opened only now."""
        import asyncio
        if getattr(self, "_cam_busy", False):
            return
        if not camera.available():
            self.flash(tr_("camera: no camera / ffmpeg found"), 4)
            return
        self._cam_busy = True
        self.flash(tr_("camera: taking a photo..."), 6)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        def work():
            data, msg = camera.grab()

            def done():
                self._cam_busy = False
                if data:
                    self._add_image(buf, data)
                    self.flash(tr_("camera: photo attached as [Image #{0}] - it is sent with your next message", self._ni), 4)
                else:
                    self.flash(tr_("camera: {0}", msg), 7)
            if loop is not None:
                loop.call_soon_threadsafe(done)
            else:
                done()
        threading.Thread(target=work, daemon=True).start()

    # ================================================================ video call mode (Alt+V)
    CAM_IDLE_SECS = 600                          # the call ends by itself after 10 minutes without any key / mouse

    def _cam_cells(self) -> tuple[int, int]:
        """(columns, rows) of the picture inside the little window; ~16:9 using the real cell size."""
        cols = self._cols_rows()[0]
        w = 32 if cols >= 110 else 24 if cols >= 80 else 16
        from . import gfx
        cw, ch = gfx.cell_px()
        return w, max(4, round(w * cw * 9 / 16 / ch))

    def _toggle_call(self) -> None:
        if self.cam is not None:
            self._stop_call(tr_("video call: off - the camera is closed"))
            return
        cam = camera.Stream()
        err = cam.start()
        if err:
            self.flash(tr_("camera: {0}", err), 6)
            return
        from . import gfx
        self._cam_view, self._cam_sent = None, -1
        self._cam_dims = self._cam_cells()       # fixed now: window and picture must always agree, even after a resize
        windowed = camera.view_mode() == "window" and cam.open_viewer()      # its own OS window, else inline
        if not windowed:
            w, h = self._cam_dims
            self._cam_view = gfx.View(w, h) if gfx.supported() else None
        self.cam = cam
        self.touch()
        self._last_chat = time.monotonic()
        self.core.agent.call_begin()
        threading.Thread(target=self._companion_loop, args=(cam,), daemon=True).start()
        self.flash(tr_("video call: ON - your messages include the last seconds of video. Alt+V to stop"), 5)
        self._invalidate()

    def _stop_call(self, msg: str = "", reason: str = "user") -> None:
        cam, self.cam = self.cam, None
        if cam is not None:
            cam.stop()
            self._end_thread = threading.Thread(target=self._finish_call, args=(self.core.agent, reason), daemon=True)
            self._end_thread.start()
        self._cam_view = None
        if msg:
            self.flash(msg, 4)
        self._invalidate()

    # ---- she talks first: while the call is on, now and then she looks at the camera and may say something
    COMPANION_SECS = 45                          # default pause between two glances

    def _companion_ready(self) -> bool:
        """True when speaking up would not interrupt anything: nobody is typing or talking, nothing is running."""
        if self.busy or self.overlay is not None or self.perm is not None or not self.queue.empty():
            return False
        if voice.VOICE.speaking() or talk.TALK.state in ("hearing", "transcribing"):
            return False
        if self.buf.text.strip():                              # a message is being typed
            return False
        return time.monotonic() - self.last_key > 6            # a key a moment ago = the user is busy (the mouse does not count)

    def _companion_loop(self, cam) -> None:
        from . import effort
        import random
        time.sleep(4)                                          # let the camera settle (exposure, first frames)
        first, fails, nxt = True, 0, 0.0
        while self.cam is cam and not cam.error:
            time.sleep(1)
            cfg = effort.load_settings()
            if cfg.get("companion", True) is False:
                continue
            try:
                every = max(15, min(600, int(cfg.get("companion_secs", self.COMPANION_SECS))))
            except (TypeError, ValueError):
                every = self.COMPANION_SECS
            ag = self.core.agent
            every = max(8, every * ag.pace())                   # sooner while she waits for an answer, rarely once she gave up
            now = time.monotonic()
            if not first and now < max(nxt, self._last_chat + every):
                continue
            if not self._companion_ready():
                continue
            try:
                imgs = self._call_attachment()
                spoke = self.core.agent.glance(imgs, first=first) if imgs and self.cam is cam else False
                fails, first = 0, False
            except Exception as e:                             # network / quota: never crash the call
                fails += 1
                if fails >= 3 or type(e).__name__ == "QuotaExhausted":
                    self.console.print(tr_("[{MUTED}]video call: she stops starting the conversation ({0}). Alt+V twice to try again[/]",
                                           str(e)[:100] or type(e).__name__, MUTED=MUTED))
                    return
                nxt = time.monotonic() + 10
                continue
            self._last_chat = time.monotonic()
            nxt = self._last_chat + every * random.uniform(0.8, 1.3) if spoke else self._last_chat + every * 0.6
            if spoke:
                self._invalidate()

    def _finish_call(self, ag, reason: str) -> None:
        """Background: she says goodbye and writes down what she learned (the camera is already closed)."""
        try:
            ag.call_end(reason, farewell=reason != "exit")
        except Exception:
            pass
        self._last_chat = time.monotonic()
        self._invalidate()

    def _cam_watchdog(self) -> None:
        """Runs on the refresh thread: end the call when the user is gone or the camera died."""
        if self.cam is None:
            return
        if self.cam.viewer_closed:
            self._stop_call(tr_("video call: ended (the call window was closed)"), "window")
        elif time.monotonic() - self.last_act > self.CAM_IDLE_SECS:
            self._stop_call(tr_("video call: ended (no activity for 10 minutes)"), "idle")

    def _cam_size(self) -> tuple[int, int]:
        """Size of the little window: exactly the picture (w x h) plus one title row."""
        w, h = self._cam_dims
        return w, h + 1

    def _cam_frags(self):
        """The little call window: a title row + the live picture (kitty/Ghostty: real pixels, otherwise half-blocks)."""
        cam = self.cam
        if cam is None:
            return []
        w, h = self._cam_dims
        hint = tr_("Alt+V = end")
        title = [("bold fg:#ff5577", " ● "), ("bold", "On")]
        if 7 + len(hint) + 2 <= w:                # the title must fit on ONE row, or the picture below shifts
            title.append((MUTED, "  " + hint))
        title.append(("", "\n"))
        if cam.error:
            lines = textwrap.wrap(cam.error, w)[:h] or [""]
            return title + sum(([(f"fg:{WARN}", ln), ("", "\n")] for ln in lines), [])
        fr, seq = cam.frame()
        if fr is None:
            return title + [(MUTED, " " + tr_("starting the camera..."))]
        mirrored = fr[:, ::-1]                                    # like a video call: you see yourself mirrored
        view = self._cam_view
        if view is not None:
            try:
                if seq != self._cam_sent:
                    rgba = np.dstack([mirrored, np.full(mirrored.shape[:2], 255, np.uint8)])
                    view.send(np.ascontiguousarray(rgba))
                    self._cam_sent = seq
                st = view.style()
                out = list(title)
                for line in view.cells:
                    out += [(st, line), ("", "\n")]
                return out
            except Exception:
                self._cam_view = None                              # fall back to half-blocks
        img = np.asarray(Image.fromarray(np.ascontiguousarray(mirrored)).resize((w, h * 2), Image.BILINEAR))
        out = list(title)
        for y in range(0, h * 2, 2):
            for x in range(w):
                t, b = img[y, x], img[y + 1, x]
                out.append((f"fg:#{t[0]:02x}{t[1]:02x}{t[2]:02x} bg:#{b[0]:02x}{b[1]:02x}{b[2]:02x}", "▀"))
            out.append(("", "\n"))
        return out

    def _call_attachment(self) -> list:
        """While the call is on: the last seconds of video go with the message (a still frame for providers without video)."""
        cam = self.cam
        if cam is None or cam.error:
            return []
        from . import config
        import base64
        if config.PROVIDER == "openai":
            data = cam.clip_mp4()
            if data:
                return [("video/mp4", base64.b64encode(data).decode())]
        jpg = cam.jpeg()
        return [clip.encode_image(jpg)] if jpg else []

    def _on_paste(self, buf, text: str) -> None:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if not text.strip():                      # empty paste: the clipboard may hold an image instead
            data = clip.grab_clipboard_image()
            if data:
                self._add_image(buf, data)
            return
        paths = clip.parse_image_paths(text)
        if paths:
            for p in paths:
                self._add_image(buf, p.read_bytes())
            return
        n_lines = text.rstrip("\n").count("\n") + 1
        if n_lines >= LONG_LINES or len(text) > LONG_CHARS:
            self._nt += 1
            self.pastes[self._nt] = text.rstrip("\n")
            buf.insert_text(f"[Pasted text #{self._nt} +{n_lines} lines]")
        else:
            buf.insert_text(text)

    def _make_submission(self, raw: str) -> Submission:
        used_p = [int(n) for n in PH_TEXT.findall(raw) if int(n) in self.pastes]
        used_i = [int(n) for n in PH_IMG.findall(raw) if int(n) in self.images]
        sub = Submission(
            raw=raw,
            text=clip.with_paths(PH_TEXT.sub(lambda m: self.pastes.get(int(m.group(1)), m.group(0)), raw),
                                 self.image_paths, PH_IMG).strip(),
            images=[self.images[n] for n in used_i],
            pastes=[(n, self.pastes[n]) for n in used_p],
            image_meta=[(n, *self.image_meta[n]) for n in used_i])
        self.pastes.clear(); self.images.clear(); self.image_meta.clear(); self.image_paths.clear(); self._nt = self._ni = 0
        if self.cam is not None and raw.strip():
            try:
                sub.images = list(sub.images) + self._call_attachment()
            except Exception:
                pass
        return sub

    @staticmethod
    def _more_input_pending(event) -> bool:
        if event.app.key_processor.input_queue:
            return True
        try:
            return bool(select.select([event.app.input.fileno()], [], [], 0.03)[0])
        except Exception:
            return False

    # ================================================================ thread kerja
    def _worker_loop(self) -> None:
        while True:
            try:
                sub = self.queue.get()
                if sub is None:
                    return
                self.busy = True
                self._invalidate()
                res = None
                try:
                    res = self.core.process(sub)
                except KeyboardInterrupt:
                    self.console.print(tr_('[{ERR}]stopped[/]', ERR=ERR))
                except BaseException as e:
                    self.console.print(tr_('[{ERR}]error:[/] {0}: {e}', type(e).__name__, ERR=ERR, e=e))
                finally:
                    self.busy = False
                    self.live = None
                    self._last_chat = time.monotonic()
                    self._invalidate()
                if res == "exit":
                    self.exit_app()
                    return
            except KeyboardInterrupt:           # an interrupt that arrived late (outside process)
                self.busy = False
                self.live = None

    def _refresh_loop(self) -> None:
        """Redraw trigger. Fast (12 fps) only when something moves: banner visible, agent working,
        picker open. Otherwise only 4 fps (slow gradient rule) -> CPU almost zero while the video is off-screen."""
        drawn_calm = False
        while True:
            if self._calm():
                if drawn_calm:                      # frozen frame already on screen: do not touch the terminal
                    time.sleep(0.25)
                    continue
                self._invalidate()                  # one last draw of the frozen frame
                drawn_calm = True
                time.sleep(0.25)
                continue
            drawn_calm = False
            if self.app is not None:
                ptfast.trim_renderer_caches(self.app)
            anim_on = self.sprite is not None and self.sprite.animating and self.banner_visible()
            moving = anim_on or self.busy or self.overlay is not None or self.perm is not None or self.cam is not None
            self._cam_watchdog()
            time.sleep(1 / self.fps if moving else (0.25 if self.borders_anim else 0.5))
            self._invalidate()

    def interrupt_worker(self) -> None:
        w = self.worker
        if w is not None and w.is_alive():
            ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(w.ident), ctypes.py_object(KeyboardInterrupt))

    def exit_app(self) -> None:
        app = self.app
        if app is None:
            return
        try:
            app.call_soon_threadsafe(lambda: app.exit() if app.is_running else None)
        except Exception:
            pass

    # ================================================================ key bindings
    def _bind(self) -> KeyBindings:
        kb = KeyBindings()
        ovl = Condition(lambda: self.overlay is not None)
        prm = Condition(lambda: self.perm is not None)
        free = ~ovl & ~prm

        @kb.add("c-c")
        def _(event):
            if self.sel and self._sel_text():          # like Claude Code: Ctrl+C with a selection copies it
                self.copy_selection()
                self.sel = None
                return
            voice.VOICE.stop()
            if self.overlay is not None:
                self.overlay["result"] = None
                self.overlay["ev"].set()
            elif self.perm is not None:
                self.perm["result"] = "interrupt"
                self.perm["ev"].set()
            elif self.busy:
                self.interrupt_worker()
            elif self.buf.text:
                self.buf.reset()
                self.cc_at = 0.0
            elif time.monotonic() - self.cc_at < CC_WINDOW:
                event.app.exit()
            else:
                self.cc_at = time.monotonic()

        @kb.add("c-d", filter=free)
        def _(event):
            if not self.buf.text and not self.busy:
                event.app.exit()

        # ---- conversation scroll ----
        default_mouse = load_mouse_bindings().bindings[0].handler

        @kb.add(Keys.Vt100MouseEvent)
        def _(event):
            m = re.match(r"\x1b\[<(\d+);", event.data)
            if m and int(m.group(1)) in (64, 65):
                if self.overlay is not None:
                    o = self.overlay
                    o["idx"] = max(0, min(len(o["rows"]) - 1, o["idx"] + (-1 if int(m.group(1)) == 64 else 1)))
                else:
                    self._wheel(-1 if int(m.group(1)) == 64 else 1)
                return None
            mm = re.match(r"\x1b\[<(\d+);(\d+);(\d+)([Mm])", event.data)
            if mm and self.overlay is None and self.perm is None:
                if self._selection_event(int(mm.group(1)), int(mm.group(2)) - 1, int(mm.group(3)) - 1, mm.group(4)):
                    return None                   # used for the selection (never reaches the pill / sticky bar)
            return default_mouse(event)           # logo click, pill, sticky bar, ...

        @kb.add("pageup", filter=free)
        def _(event):
            self.scroll_by(-max(3, self._conv_vh() - 2))

        @kb.add("pagedown", filter=free)
        def _(event):
            self.scroll_by(max(3, self._conv_vh() - 2))

        def resize_logo(delta: int) -> None:
            from .effort import save_settings
            if not self.sprite:
                return
            n = max(12, min(80, self.sprite.w + delta))
            save_settings(logo_cols=n)
            t0 = self.sprite.t0
            self.load_logo()
            if self.sprite:
                self.sprite.t0 = t0 if t0 is not None else -100.0
            self._banner_cache = None
            self._invalidate()

        @kb.add("escape", "=", filter=free)
        @kb.add("escape", "+", filter=free)
        def _(event):
            resize_logo(4)

        @kb.add("escape", "-", filter=free)
        def _(event):
            resize_logo(-4)

        @kb.add("escape", "f", filter=free)
        def _(event):
            self.flash(self.cycle_fps())

        @kb.add("escape", "b", filter=free)
        def _(event):
            self.flash(self.set_borders(not self.borders_anim))

        @kb.add("escape", "i", filter=free)
        def _(event):
            self.flash(self.cycle_logo_mode())

        @kb.add("escape", "c", filter=free)
        def _(event):
            self._take_photo(event.current_buffer)

        @kb.add("escape", "v", filter=free)
        def _(event):
            self._toggle_call()

        @kb.add("c-end", filter=free)
        def _(event):
            self.follow = True

        # ---- picker (overlay) ----
        def ov_move(d):
            o = self.overlay
            o["idx"] = max(0, min(len(o["rows"]) - 1, o["idx"] + d))

        @kb.add("up", filter=ovl)
        def _(event):
            ov_move(-1)

        @kb.add("down", filter=ovl)
        def _(event):
            ov_move(1)

        @kb.add("pageup", filter=ovl)
        def _(event):
            ov_move(-10)

        @kb.add("pagedown", filter=ovl)
        def _(event):
            ov_move(10)

        @kb.add("enter", filter=ovl)
        def _(event):
            o = self.overlay
            o["result"] = ("enter", o["idx"])
            o["ev"].set()

        @kb.add("escape", filter=ovl, eager=True)
        def _(event):
            self.overlay["result"] = None
            self.overlay["ev"].set()

        @kb.add(Keys.Any, filter=ovl)
        def _(event):
            o, ch = self.overlay, event.data
            if ch in o["keys"]:
                o["result"] = (ch, o["idx"])
                o["ev"].set()
            elif ch == "j":
                ov_move(1)
            elif ch == "k":
                ov_move(-1)
            elif ch == "q":
                o["result"] = None
                o["ev"].set()

        # ---- izin ----
        def perm_done(res):
            self.perm["result"] = res
            self.perm["ev"].set()

        @kb.add("enter", filter=prm)
        def _(event):
            perm_done("y")

        @kb.add("escape", filter=prm, eager=True)
        def _(event):
            perm_done("n")

        @kb.add(Keys.Any, filter=prm)
        def _(event):
            ch = event.data.lower()
            if ch == "y":
                perm_done("y")
            elif ch == "n":
                perm_done("n")
            elif ch in ("a", "t") and not self.perm["reason"]:
                perm_done(ch)

        # ---- input ----
        @kb.add(Keys.BracketedPaste, filter=free)
        def _(event):
            self._on_paste(event.current_buffer, event.data)

        @kb.add(Keys.BracketedPaste, filter=~free)
        def _(event):
            pass

        @kb.add("c-v", filter=free)
        @kb.add("escape", "p", filter=free)       # Alt+P: Windows Terminal swallows Ctrl+V when the clipboard holds an image
        def _(event):
            data = clip.grab_clipboard_image()
            if data:
                self._add_image(event.current_buffer, data)
            else:
                self.flash(tr_("no image in the clipboard (screenshot with Win+Shift+S, then Alt+P)"), 4)

        @kb.add("enter", filter=free)
        def _(event):
            if self._more_input_pending(event):       # paste without bracketed-paste -> newline
                event.current_buffer.insert_text("\n")
                return
            raw = self.buf.text
            if not raw.strip():
                return
            self.buf.append_to_history()
            self.buf.reset()
            self.cc_at = 0.0
            sub = self._make_submission(raw)
            shown = (sub.raw or sub.text).replace("\n", " ⏎ ")
            self.console.print()
            self.console.print(Text.assemble(("❯ ", f"bold {ROSE}"), (shown[:600], "bold")))
            self.follow = True
            self.queue.put(sub)

        @kb.add("escape", "enter", filter=free)
        @kb.add("c-j", filter=free)
        def _(event):
            event.current_buffer.insert_text("\n")

        @kb.add("s-tab", filter=free)
        def _(event):
            self.core.policy.cycle_mode()

        @kb.add("backspace", filter=free)
        def _(event):
            b = event.current_buffer
            m = PH_END.search(b.document.text_before_cursor)
            b.delete_before_cursor(len(m.group(0)) if m else 1)

        return kb

    # ================================================================ aplikasi
    def run(self) -> None:
        self.buf = Buffer(
            history=FileHistory(str(paths.HISTORY)),
            completer=merge_completers([SlashCompleter(), MentionCompleter()]),
            complete_while_typing=True, multiline=True, enable_history_search=True,
            on_text_changed=lambda _b: (setattr(self, "cc_at", 0.0), setattr(self, "last_edit", self._t()), setattr(self, "sel", None)))
        self.conv_win = Window(
            LinesControl(self),
            wrap_lines=False, always_hide_cursor=True, get_vertical_scroll=lambda w: self._top_line())
        input_win = Window(BufferControl(self.buf, input_processors=[BeforeInput(self._prompt_frags), FakeCursor(self)]),
                           height=self._input_height, wrap_lines=True, always_hide_cursor=True)
        overlay_win = Window(FormattedTextControl(self._overlay_frags), dont_extend_height=True)
        conv_area = FloatContainer(content=self.conv_win, floats=[
            Float(top=0, left=0, right=0, height=1, content=ConditionalContainer(
                Window(FormattedTextControl(self._sticky_frags), height=1, style="bg:#262626"),
                filter=Condition(lambda: self._sticky_msg() is not None))),
            Float(bottom=0, content=ConditionalContainer(
                Window(FormattedTextControl(self._jump_frags), height=1, dont_extend_width=True, style="bg:#3a3a3a"),
                filter=Condition(self._scrolled_up))),
        ])
        body = HSplit([
            conv_area,                                                    # banner (video) + conversation, one scroll area
            Window(FormattedTextControl(self._status_frags), height=1),
            Window(height=1),                                                 # spacing: the status row does not touch the input
            Window(FormattedTextControl(self._rule_frags), height=1),         # batas atas kotak input
            input_win,
            Window(FormattedTextControl(self._rule_frags), height=1),         # batas bawah kotak input
            Window(FormattedTextControl(self._footer_frags), height=1),
        ])
        root = FloatContainer(content=body, floats=[
            Float(xcursor=True, ycursor=True, content=CompletionsMenu(max_height=10, scroll_offset=1)),
            Float(content=ConditionalContainer(overlay_win, filter=Condition(lambda: self.overlay is not None))),
            Float(right=2, top=1, content=ConditionalContainer(
                Window(FormattedTextControl(self._cam_frags), style="bg:#141414",
                       width=lambda: self._cam_size()[0], height=lambda: self._cam_size()[1], dont_extend_width=True),
                filter=Condition(lambda: self.cam is not None and self.cam.viewer is None))),
        ])
        kw = {}
        if os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit"):
            kw["color_depth"] = ColorDepth.TRUE_COLOR
        self.app = Application(
            layout=Layout(root, focused_element=input_win), key_bindings=self._bind(), full_screen=True,
            mouse_support=Condition(lambda: self.mouse_on), output=steady_output(),
            style=Style.from_dict({
                "completion-menu.completion": "bg:default #8a8a8a",
                "completion-menu.completion.current": f"bg:default bold {ROSE}",
                "completion-menu.meta.completion": "bg:default #8a8a8a",
                "completion-menu.meta.completion.current": "bg:default #8a8a8a"}), **kw)
        _kp, _feed = self.app.key_processor, self.app.key_processor.feed_multiple
        NOT_KEYS = {Keys.Vt100MouseEvent, Keys.WindowsMouseEvent, Keys.ScrollUp, Keys.ScrollDown,
                    Keys.CPRResponse, Keys.Ignore}
        def feed_multiple(keys, first=False):          # every key / mouse event = activity
            self.touch()
            if any(k.key not in NOT_KEYS for k in keys):
                self.last_key = time.monotonic()       # the keyboard only (the mouse does not stop her from talking)
            return _feed(keys, first)
        _kp.feed_multiple = feed_multiple
        ptfast.tune_gc()
        self.worker = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker.start()
        threading.Thread(target=self._refresh_loop, daemon=True).start()
        threading.Thread(target=self._autoscroll_loop, daemon=True).start()
        threading.Thread(target=self._smooth_loop, daemon=True).start()
        sys.stdout.write("\x1b[?25l")             # the real cursor is hidden; what shows is the FakeCursor
        sys.stdout.flush()
        try:
            self.app.run()
        finally:
            if self.cam is not None:
                self._stop_call(reason="exit")
            t = getattr(self, "_end_thread", None)
            if t is not None and t.is_alive():             # let her finish writing her notes (at most 10 s)
                sys.stdout.write(tr_("\x1b[2m(saving what she learned from the call...)\x1b[0m\n"))
                sys.stdout.flush()
                t.join(10)
            talk.TALK.stop()
            voice.VOICE.stop()
            sys.stdout.write("\x1b[?25h")
            sys.stdout.flush()
            if self.busy:
                self.interrupt_worker()
                time.sleep(0.2)


def _text_segments(t: Text) -> list[tuple[str, str]]:
    """Rich Text -> [(text, prompt_toolkit style)] for the permission choice lines."""
    out, pos, plain = [], 0, t.plain
    spans = sorted(t.spans, key=lambda s: s.start)
    for sp in spans:
        if sp.start > pos:
            out.append((plain[pos:sp.start], ""))
        style = str(sp.style).replace("bold ", "bold ")
        out.append((plain[sp.start:sp.end], style))
        pos = sp.end
    if pos < len(plain):
        out.append((plain[pos:], ""))
    return out


class TuiHooks:
    def __init__(self, tui: TUI):
        self.tui = tui

    def load_logo(self):
        self.tui.load_logo()
        return self.tui.logo_error

    def clear(self):
        self.tui.clear()

    def set_fps(self, n):
        return self.tui.set_fps(n)

    def set_still(self, still):
        return self.tui.set_still(still)

    def set_ascii(self, on):
        return self.tui.set_ascii(on)

    def set_borders(self, on):
        return self.tui.set_borders(on)

    def refresh_language(self):
        self.tui.refresh_language()

    def set_mouse(self, on):
        return self.tui.set_mouse(on)

    def history(self):
        self.tui.console.print(tr_('[{MUTED}]scroll the conversation with the mouse wheel / PageUp / PageDown[/]', MUTED=MUTED))

    def show_banner(self):
        self.history()


def run_tui(argv: list[str], make_core) -> None:
    tui = TUI()
    if trust.needed(argv):                       # nothing from this folder is loaded before the user agrees
        from .gate import run_gate
        if not run_gate(tui, os.getcwd()):
            Console().print(tr_("[{MUTED}]folder not trusted - exiting[/]", MUTED=MUTED))
            return
    core = make_core(tui.console, argv, TuiHooks(tui))
    tui.core = core
    core.startup(Console())                      # the `-r` picker uses the real terminal (before full screen)
    if tui.logo_error:
        tui.console.print(tr_('[{MUTED}]could not load the logo ({0})[/]', tui.logo_error, MUTED=MUTED))
    tui.run()
    h = core.hint()
    if h:
        Console().print("(^_^)/ bye!  " + h)
