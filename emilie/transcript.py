"""Display history for the scrollback viewer (the alternate screen has no terminal scrollback).

Recorded SEPARATELY from the main Console: Rich splices the Live display (spinner + leftover text) into every
print while a Live is active; with Console(record=True) that splice is recorded too and pollutes the
history. Here each print is re-rendered by a recording console of its own (without Live).
"""
import io

from rich.console import Console
from rich.control import Control

_parts: list[str] = []
_size = 0
MAX_CHARS = 3_000_000


def add(text: str) -> None:
    global _size
    _parts.append(text)
    _size += len(text)
    while _size > MAX_CHARS and len(_parts) > 1:        # drop the oldest
        _size -= len(_parts.pop(0))


def add_line(text: str, style_ansi: str = "") -> None:
    add(f"{style_ansi}{text}\x1b[0m\n")


def text() -> str:
    return "".join(_parts)


def clear() -> None:
    global _size
    _parts.clear()
    _size = 0


def attach(console: Console) -> None:
    """Attach the recorder to console.print (real content only; Live controls are ignored)."""
    orig = console.print

    def tee(*args, **kwargs):
        orig(*args, **kwargs)
        if any(isinstance(a, Control) for a in args):
            return
        buf = io.StringIO()
        rec = Console(file=buf, force_terminal=True, color_system="truecolor",
                      width=console.width, legacy_windows=False)
        try:
            rec.print(*args, **kwargs)
        except Exception:
            return
        add(buf.getvalue())

    console.print = tee  # type: ignore[method-assign]
