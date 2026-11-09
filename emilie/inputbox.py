"""Interactive input.

• left/right arrows, history, long paste -> [Pasted text #1 +N lines], image -> [Image #1]
• @file autocomplete, Shift+Tab switches mode
• LIVE UI: the prompt is redrawn at ~15 fps -> the gradient rule flows, the (video) logo plays,
  and the logo can be CLICKED for a water ripple, even after the conversation has started.
"""
from . import paths
import io
import os
import re
import select
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion, merge_completers
from prompt_toolkit.filters import Condition, is_done
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.bindings.mouse import load_mouse_bindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import ConditionalContainer, Dimension, HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.output import ColorDepth
from prompt_toolkit.output.defaults import create_output
from prompt_toolkit.styles import Style

from .i18n import t as tr_, N_
from . import anim, clip, logo
from .theme import LAV, MUTED, ROSE

PH_TEXT = re.compile(r"\[Pasted text #(\d+)(?: \+\d+ lines)?\]")
PH_IMG = re.compile(r"\[Image #(\d+)\]")
PH_END = re.compile(r"\[(?:Pasted text|Image) #\d+[^\]]*\]$")
LONG_LINES, LONG_CHARS = 4, 500
CC_WINDOW = 3.0   # seconds: a second Ctrl+C within this window = exit; after it, it counts as a fresh first press
SCROLL_SENTINEL = "\x00scroll\x00"
FPS = 12          # = fps video logo; garis gradien sangat lambat jadi cukup halus

COMMANDS = {
    "/help": N_('list commands'), "/clear": N_('clear the conversation history'),
    "/language": N_('interface language: /language <code> (en, id, ...)'),
    "/mouse": N_('mouse on|off: select + copy inside Emilie, or let the terminal do it'),
    "/reply": N_('language the AI answers in: auto|en|id|ja|... (see also /language)'),
    "/persona": N_("play a character (default Emilie): on|off|show|reset - edit ~/.emilie/persona.md"),
    "/talk": N_('hands-free conversation: speak, pause to send - on|off|pause <s>|lang|model'),
    "/voice": N_('speak replies in a cloned voice: on|off|mode|lang|profile|test'),
    "/provider": N_('list providers / how to switch (emilie --setup)'),
    "/model": N_('pick a bankai model (price & grade)'), "/effort": N_('set the token-saving level (low/medium/high/max)'),
    "/compact": N_('compact history to save tokens'), "/cost": N_('token usage of this session'),
    "/context": N_('context size vs the effort limit'), "/mode": N_('switch permission mode (ask/trust/plan)'),
    "/plan": N_('toggle plan mode (read-only)'), "/trust": N_('toggle trusting this folder'),
    "/allow": N_('always allow a tool without asking: /allow mcp__browser__* | bash(git *) | rm <rule>'),
    "/deny": N_('always block a tool: /deny bash(rm *) | rm <rule>'),
    "/schedule": N_('run a prompt on a timer (Windows Task Scheduler): /schedule | add | rm | run'),
    "/export": N_('save this conversation as a markdown file: /export [file.md]'),
    "/permissions": N_('show the mode, allow/deny rules and hooks: /permissions | /permissions reset'),
    "/config": N_('see and change settings: /config | /config <name> <value> | /config <name> default'),
    "/review": N_('review code changes: /review (uncommitted) | /review <branch> | /review <PR number>'),
    "/commit": N_('write a commit message from the changes and commit (never pushes): /commit [hint]'),
    "/pr": N_('draft a pull request title and description from this branch: /pr [base branch]'),
    "/fallback": N_('backup model used when the main one keeps failing: /fallback <model> | off'),
    "/scroll": N_('tune mouse-wheel scrolling: /scroll lines <1-10> · /scroll smooth <0-300 ms> · /scroll reset'),
    "/doctor": N_('test what this model supports: chat, streaming, tools, vision'),
    "/thinking": N_('Claude extended thinking: /thinking on | off | <tokens> (Anthropic provider only)'),
    "/rewind": N_('go back to before an earlier turn that changed files: /rewind, /rewind <n> [both|files|chat]'),
    "/undo": N_('undo the file changes of the last turn'), "/todos": N_("the agent's task list"),
    "/resume": N_('resume an older session'), "/init": N_('create EMILIE.md for this project'),
    "/memory": N_('loaded memory files'), "/logo": N_('show the banner / change the logo (video/image)'),
    "/camera": N_('camera: Alt+C takes ONE photo for your next message; /camera list|device|test'),
    "/history": N_('view the whole conversation of this session'),
    "/borders": N_('animated borders on/off (Alt+B) - off saves CPU'),
    "/dev": N_('take a task through the phases: understand, plan, build, check, release, maintain'),
    "/skills": N_('list Agent Skills and custom commands (SKILL.md)'),
    "/mcp": N_('MCP servers and tools (/mcp reload)'),
    "/exit": "exit",
}
EXTRA_COMMANDS: dict[str, str] = {}      # custom skills & commands (filled in by cli)
MODE_LABEL = {"ask": N_('ask first'), "trust": "trust", "plan": N_('plan (read-only)')}


@dataclass
class Submission:
    text: str
    raw: str = ""                                    # the text as typed (whole placeholder)
    scroll: bool = False                             # True -> the user asked to see the history (mouse wheel/PageUp)
    draft: str = ""                                  # typing that was pending when the history was opened
    images: list = field(default_factory=list)       # [(mime, b64)]
    pastes: list = field(default_factory=list)       # [(n, teks)]
    image_meta: list = field(default_factory=list)   # [(n, (w, h), bytes)]


class SlashCompleter(Completer):
    def get_completions(self, document, complete_event):
        t = document.text_before_cursor
        if t.startswith("/") and " " not in t:
            for c, desc in {**COMMANDS, **EXTRA_COMMANDS}.items():
                if c.startswith(t):
                    yield Completion(c, start_position=-len(t), display_meta=tr_(desc))


class MentionCompleter(Completer):
    """@path -> list of files/folders in the working folder."""

    def get_completions(self, document, complete_event):
        word = document.get_word_before_cursor(WORD=True)
        if not word.startswith("@"):
            return
        frag = word[1:]
        base = os.path.dirname(frag)
        try:
            names = sorted(os.listdir(os.path.expanduser(base) if base else "."))
        except OSError:
            return
        pre = os.path.basename(frag)
        n = 0
        for name in names:
            if not name.startswith(pre) or (name.startswith(".") and not pre.startswith(".")):
                continue
            if name in {"node_modules", "__pycache__", ".git", ".venv"}:
                continue
            path = os.path.join(base, name) if base else name
            isdir = os.path.isdir(os.path.expanduser(path))
            yield Completion("@" + path + ("/" if isdir else ""), start_position=-len(word),
                             display_meta="folder" if isdir else "file")
            n += 1
            if n >= 40:
                return


def steady_output():
    """Terminal output for the animated UI.

    By default prompt_toolkit hides and then shows the cursor (+ blink reset `?12l`) on EVERY
    frame -> with a 15 fps animation the cursor blinks 15x/second. Here hide/show is disabled, and each
    frame is wrapped in a 'synchronized update' (DEC 2026) so it is drawn atomically without the cursor jumping.
    """
    out = create_output()
    if not hasattr(out, "_buffer"):
        return out
    out.hide_cursor = lambda: None
    out.show_cursor = lambda: None
    raw_flush = out.flush

    def flush() -> None:
        if out._buffer:
            out._buffer.insert(0, "\x1b[?2026h")
            out._buffer.append("\x1b[?2026l")
        raw_flush()
    out.flush = flush
    return out


class InputBox:
    def __init__(self, get_status, get_banner=None, on_cycle_mode=None, **session_kwargs):
        self.get_status = get_status
        self.get_banner = get_banner
        self.pastes: dict[int, str] = {}
        self.images: dict[int, tuple[str, str]] = {}
        self.image_meta: dict[int, tuple[tuple[int, int], int]] = {}
        self.image_paths: dict[int, str | None] = {}
        self._nt = self._ni = 0

        # ---- animated logo (video / image) ----
        self.t0 = time.monotonic()
        self.big = self.mini = None
        self.logo_error: str | None = None
        self.load_logo()
        self.show_banner = True       # the big banner only on the first prompt (or after /logo)
        self._banner_on = False
        self._memo: dict = {}
        self.cc_at = 0.0               # time of the first Ctrl+C (for the 'press once more' window)
        self.scrollback_enabled = True
        self.scroll_block_until = 0.0  # ignore the wheel/PageUp for a moment after the viewer closes (trackpad momentum)

        kb = KeyBindings()

        @kb.add(Keys.BracketedPaste)
        def _(event):
            self._on_paste(event.current_buffer, event.data)

        @kb.add("c-v")
        def _(event):
            data = clip.grab_clipboard_image()
            if data:
                self._add_image(event.current_buffer, data)

        @kb.add("enter")
        def _(event):
            # Terminal without bracketed paste: newlines of a paste arrive as Enter.
            # If more typing follows right behind, treat it as part of the paste -> newline.
            if self._more_input_pending(event):
                event.current_buffer.insert_text("\n")
            else:
                event.current_buffer.validate_and_handle()

        @kb.add("escape", "enter")
        @kb.add("c-j")
        def _(event):
            event.current_buffer.insert_text("\n")

        @kb.add("c-c")
        def _(event):
            b = event.current_buffer
            now = time.monotonic()
            if b.text:
                b.reset()                  # there is text -> just clear it
                self.cc_at = 0.0
            elif now - self.cc_at < CC_WINDOW:   # second Ctrl+C, still inside the time window -> exit
                event.app.exit(exception=KeyboardInterrupt, style="class:aborting")
            else:                          # first press (or the window has passed): show a temporary hint
                self.cc_at = now

        # ---- scroll to the history: mouse wheel up / PageUp (the alternate screen has no scrollback) ----
        default_mouse = load_mouse_bindings().bindings[0].handler

        @kb.add(Keys.Vt100MouseEvent)
        def _(event):
            m = re.match(r"\x1b\[<(\d+);", event.data)
            if m and int(m.group(1)) == 64:                                      # wheel up
                if not self.scrollback_enabled or time.monotonic() < self.scroll_block_until:
                    return None                  # trackpad momentum: swallow it, do not reopen
                event.app.exit(result=SCROLL_SENTINEL + event.current_buffer.text)
                return None
            return default_mouse(event)         # klik logo dll. tetap lewat jalur bawaan

        @kb.add("pageup")
        def _(event):
            if self.scrollback_enabled and time.monotonic() >= self.scroll_block_until:
                event.app.exit(result=SCROLL_SENTINEL + event.current_buffer.text)

        @kb.add("s-tab")
        def _(event):
            if on_cycle_mode:
                on_cycle_mode()
            event.app.invalidate()

        @kb.add("backspace")
        def _(event):  # the placeholder was deleted as a whole
            b = event.current_buffer
            m = PH_END.search(b.document.text_before_cursor)
            b.delete_before_cursor(len(m.group(0)) if m else 1)

        hist = paths.HISTORY
        session_kwargs.setdefault("history", FileHistory(str(hist)))
        session_kwargs.setdefault("refresh_interval", 1 / FPS)
        session_kwargs.setdefault("mouse_support", True)
        session_kwargs.setdefault("reserve_space_for_menu", 0)   # floating menu; do not leave empty space
        if "output" not in session_kwargs and sys.stdout.isatty():
            session_kwargs["output"] = steady_output()
        if os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit"):
            session_kwargs.setdefault("color_depth", ColorDepth.TRUE_COLOR)   # logo HD butuh 24-bit
        self.session = PromptSession(
            key_bindings=kb,
            completer=merge_completers([SlashCompleter(), MentionCompleter()]),
            complete_while_typing=True,
            enable_history_search=True,
            style=Style.from_dict({
                "bottom-toolbar": "noreverse bg:default #8a8a8a",
                "completion-menu.completion": "bg:default #8a8a8a",
                "completion-menu.completion.current": f"bg:default bold {ROSE}",
                "completion-menu.meta.completion": "bg:default #8a8a8a",
                "completion-menu.meta.completion.current": "bg:default #8a8a8a",
            }),
            **session_kwargs,
        )
        # typing anything cancels the 'press Ctrl+C once more' window
        self.session.default_buffer.on_text_changed += lambda _b: setattr(self, "cc_at", 0.0)
        # attach the banner as a window above the prompt layout
        banner_win = ConditionalContainer(
            Window(FormattedTextControl(self._banner_frags), dont_extend_height=True),
            filter=Condition(lambda: self._banner_on))
        status_win = ConditionalContainer(
            Window(FormattedTextControl(self._toolbar), dont_extend_height=True, style="class:bottom-toolbar"),
            filter=~is_done)
        # the input area has a limited height: without this it stretches to the bottom of the screen and the toolbar is thrown far away
        input_area = HSplit([self.session.layout.container], height=self._input_height)
        layout = Layout(HSplit([banner_win, input_area, status_win]),
                        focused_element=self.session.layout.current_window)
        self.session.layout = layout
        self.session.app.layout = layout

    def _input_height(self) -> Dimension:
        """Height of the input area = number of its lines (including wrapped lines), max 10."""
        cols = max(20, shutil.get_terminal_size().columns)
        text = self.session.default_buffer.text
        n = sum(max(1, -(-(len(line) + (2 if i == 0 else 0)) // cols)) for i, line in enumerate(text.split("\n")))
        n = min(11, max(1, n) + 1)            # +1 = the gradient rule above the input (part of the prompt message)
        return Dimension(min=n, preferred=n, max=n)

    # ------------------------------------------------------------ logo
    def load_logo(self) -> None:
        self.big = self.mini = None
        self.logo_error = None
        p = logo.find_logo()
        if not p:
            return
        try:
            src = logo.Source(p)
            self.big, self.mini = logo.Sprite(src, 28), logo.Sprite(src, 16)
        except Exception as e:           # broken video / the av package is missing -> keep running without the logo
            self.logo_error = f"{type(e).__name__}: {e}"

    def can_banner(self) -> bool:
        cols, rows = shutil.get_terminal_size()
        return bool(self.big and self.get_banner and cols >= 70 and rows >= anim.banner_height_estimate() + 12)

    def _t(self) -> float:
        return time.monotonic() - self.t0

    def _memoized(self, name: str, build):
        """prompt_toolkit calls the callable several times per render -> compute once per ~1/30 s."""
        key = int(self._t() * 30)
        hit = self._memo.get(name)
        if hit and hit[0] == key:
            return hit[1]
        val = build()
        self._memo[name] = (key, val)
        return val

    def _message(self):
        def build():
            t, cols = self._t(), shutil.get_terminal_size().columns
            fr: list = []
            fr += anim.rule_fragments(cols, t)
            fr.append(("", "\n"))
            fr.append(anim.prompt_arrow(t))
            return fr
        return self._memoized("msg", build)

    def _banner_frags(self):
        """Banner in a SEPARATE window (not in the prompt message): prompt_toolkit drops the mouse
        handlers of a multi-line message fragment, so a click on the logo would never be detected."""
        def build():
            return anim.banner_fragments(self.big, self._t(),
                                         min(shutil.get_terminal_size().columns, 100), self.get_banner())
        return self._memoized("banner", build)

    def _toolbar(self):
        def build():
            rows = shutil.get_terminal_size().lines
            compact = self._banner_on or self.mini is None or rows < 26
            hint = tr_('press Ctrl+C again to exit') if (time.monotonic() - self.cc_at) < CC_WINDOW else None
            return anim.toolbar_fragments(self.mini, self._t(), self.get_status(), compact, hint)
        return self._memoized("tb", build)

    @staticmethod
    def _more_input_pending(event) -> bool:
        if event.app.key_processor.input_queue:
            return True
        try:  # a big paste can be cut between reads: wait a moment
            fd = event.app.input.fileno()
            return bool(select.select([fd], [], [], 0.03)[0])
        except Exception:
            return False

    # ------------------------------------------------------------ paste
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

    def _on_paste(self, buf, text: str) -> None:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
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

    # ------------------------------------------------------------ submit
    def ask(self, default: str = "") -> Submission:
        self._banner_on = self.show_banner and self.can_banner()
        self._memo.clear()
        try:
            raw = self.session.prompt(self._message, default=default)
        finally:
            self.show_banner = False
            self._banner_on = False
        if raw.startswith(SCROLL_SENTINEL):        # do not clear the pastes/images: the draft will be shown again
            return Submission(text="", scroll=True, draft=raw[len(SCROLL_SENTINEL):])
        self.cc_at = 0.0
        used_p = [int(n) for n in PH_TEXT.findall(raw) if int(n) in self.pastes]
        used_i = [int(n) for n in PH_IMG.findall(raw) if int(n) in self.images]
        sub = Submission(
            raw=raw,
            text=clip.with_paths(PH_TEXT.sub(lambda m: self.pastes.get(int(m.group(1)), m.group(0)), raw),
                                 self.image_paths, PH_IMG).strip(),
            images=[self.images[n] for n in used_i],
            pastes=[(n, self.pastes[n]) for n in used_p],
            image_meta=[(n, *self.image_meta[n]) for n in used_i],
        )
        self.pastes.clear(); self.images.clear(); self.image_meta.clear(); self.image_paths.clear(); self._nt = self._ni = 0
        return sub
