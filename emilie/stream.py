"""Streaming view: finished markdown blocks are printed upwards,
while the part still being written + the spinner stay alive below."""
import random
import re
import time

from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.text import Text

from .i18n import t as tr_
from . import voice
from .theme import MUTED, ROSE, gradient_hex

VERBS = ["Cooking", "Tangling", "Baking", "Whisking", "Simmering", "Pondering",
         "Brewing", "Conjuring", "Noodling", "Marinating", "Frosting", "Kneading",
         "Sprinkling", "Caramelizing", "Percolating", "Daydreaming"]
# One glyph that changes shape, like a flower opening and closing: seed -> bud -> petals -> full bloom -> back.
# All are single-width characters (no emoji, no ambiguous-width ones, so nothing shifts in any terminal).
FRAMES = ["∘", "✢", "✥", "✤", "❀", "✿", "✾", "❁", "❋", "❁", "✾", "✿", "❀", "✤", "✥", "✢"]
FRAME_FPS = 8                                                       # a full bloom-and-close takes 2 s


def fmt_tokens(n: float) -> str:
    n = int(n)
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


def fmt_time(s: float) -> str:
    s = int(s)
    return f"{s}s" if s < 60 else f"{s // 60}m {s % 60}s"


def is_quota_error(text: str) -> bool:
    """Quota-exhausted message from the provider (sent as an 'answer'). Deliberately narrow: it must start
    with a typical provider sentence, or be a short message formatted like 'API key status ... Quota ...'. A normal answer
    that happens to discuss 'quota exceeded' (e.g. explaining an error code) does NOT match."""
    t = text.lstrip().lower()
    if t.startswith(("your quota is exhausted", "quota exhausted", "quota exceeded")):
        return True
    return len(t) < 700 and "api key status" in t and "quota" in t


SHOW_DELAY = 1.0   # seconds: the spinner/word only appears if the answer has not started after this pause


class StreamView:
    def __init__(self, console: Console):
        self.console = console
        self.verbs = random.sample(VERBS, len(VERBS))
        self.t0 = time.time()
        self.tokens = 0.0
        self.buf = ""
        self.swallow = False          # True -> this text is a provider error, it is not printed
        self.live: Live | None = None
        self.tui = None

    def start(self) -> "StreamView":
        self.t0 = time.time()
        tui = getattr(self.console, "tui", None)
        if tui is not None:                 # full screen: the spinner is drawn by the app, not Live
            self.tui = tui
            tui.live = self
            return self
        self.live = Live(console=self.console, get_renderable=self._render,
                         refresh_per_second=12, transient=True)
        self.live.start()
        return self

    # --- input from the stream ---
    def think(self, text: str) -> None:
        self.tokens += len(text) / 4  # estimasi kasar: ~4 char per token

    def text(self, text: str) -> None:
        self.think(text)
        self.buf += text
        if not self.swallow and is_quota_error(self.buf):
            self.swallow = True
        if not self.swallow:
            self._flush_blocks()

    # --- blok markdown ---
    def _block_end(self) -> int | None:
        i = self.buf.find("\n\n")
        while i != -1:
            if self.buf[:i].count("```") % 2 == 0:  # not inside a code fence
                return i
            i = self.buf.find("\n\n", i + 2)
        return None

    def _flush_blocks(self) -> None:
        while (i := self._block_end()) is not None:
            block, self.buf = self.buf[:i], self.buf[i:].lstrip("\n")
            if block.strip():
                self.console.print(Markdown(voice.VOICE.handle(block)))
                self.console.print()

    def _render(self):
        el = time.time() - self.t0
        if el < SHOW_DELAY and not self.buf.strip():
            return Text("")
        line = Text()
        col = gradient_hex(-el * 0.22)            # the colour changes slowly
        line.append(FRAMES[int(el * FRAME_FPS) % len(FRAMES)] + " ", style=f"bold {col}")
        line.append(self.verbs[int(el / 2.5) % len(self.verbs)] + "…", style=col)
        line.append(tr_(' ({0} · ↓ {1} tokens · ctrl+c to stop)', fmt_time(el), fmt_tokens(self.tokens)),
                    style=MUTED)
        if self.swallow or not self.buf.strip():
            return line
        keep = max(3, self.console.height - 6)
        tail = "\n".join(self.buf.splitlines()[-keep:])
        return Group(Text(tail), Text(""), line)

    # --- finished ---
    def status_fragments(self) -> list[tuple[str, str]]:
        """Status line for the full-screen app: spinner + word + time + tokens."""
        el = time.time() - self.t0
        if el < SHOW_DELAY:
            return []                       # give it time first; if the answer is quick there is no need for "cooking…"
        col = gradient_hex(-el * 0.22)
        return [(f"bold {col}", FRAMES[int(el * FRAME_FPS) % len(FRAMES)] + " "),
                (col, self.verbs[int(el / 2.5) % len(self.verbs)] + "…"),
                (MUTED, tr_(" ({0} · ↓ {1} tokens", fmt_time(el), fmt_tokens(self.tokens))
                        + (tr_(" · {0} tok/s", f"{self.tokens / el:.0f}") if el >= 1.5 and self.tokens else "")
                        + tr_(' · ctrl+c to stop)'))]

    def _stop_and_flush(self) -> None:
        if self.tui is not None and self.tui.live is self:
            self.tui.live = None
        if self.live:
            self.live.stop()
            self.live = None
        if self.buf.strip() and not self.swallow:
            self.console.print(Markdown(voice.VOICE.handle(self.buf)))
        self.buf = ""

    def abort(self) -> None:
        self._stop_and_flush()

    def finish(self, tokens: int | None = None) -> None:
        was_error = self.swallow
        self._stop_and_flush()
        if was_error:
            return
        n = tokens if tokens is not None else self.tokens
        mark = "" if tokens is not None else "~"
        self.console.print(
            tr_('[{MUTED}]✾ done in {0} · ↓ {mark}{1} tokens[/]', fmt_time(time.time() - self.t0), fmt_tokens(n), MUTED=MUTED, mark=mark),
            highlight=False)
