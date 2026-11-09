"""History viewer (scrollback) for the alternate screen.

The alternate screen has no terminal scrollback. This viewer replaces it: opened with the
mouse wheel up / PageUp at the prompt (or /history), then scroll with the wheel, up/down, PgUp/PgDn,
Home/End; q / Esc goes back.
"""
import os
import re
import select
import shutil
import sys
import termios
import tty

MOUSE = re.compile(rb"\x1b\[<(\d+);(\d+);(\d+)([Mm])")
CSI = re.compile(rb"\x1b\[[0-9;?<]*[A-Za-z~]")


_CTRL = re.compile(r"\x1b\[\?\d+[hl]|\x1b\[\d*[ABCDEFGHJKSTf]|\x1b\[\d*;\d*[Hf]|\r")


def clean(text: str) -> str:
    """Strip cursor control codes (leftovers of the spinner/Live) so they do not overwrite a line when it is printed again."""
    return _CTRL.sub("", text)


def _w(s: str) -> None:
    sys.stdout.write(s)
    sys.stdout.flush()


def view(text: str, title: str = "history") -> None:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return
    lines = clean(text).rstrip("\n").split("\n")
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    top: int | None = None
    last_size, dirty, buf = None, True, b""
    try:
        tty.setcbreak(fd)
        _w("\x1b[?1000h\x1b[?1006h\x1b[?25l\x1b[?7l\x1b[2J")   # mouse, hide the cursor, no auto-wrap
        while True:
            cols, rows = shutil.get_terminal_size()
            body = max(1, rows - 1)
            maxtop = max(0, len(lines) - body)
            if top is None:
                top = maxtop                      # start from the newest part
            top = min(max(top, 0), maxtop)
            if dirty or (cols, rows) != last_size:
                out = [f"\x1b[{i + 1};1H{lines[top + i] if top + i < len(lines) else ''}\x1b[0m\x1b[K"
                       for i in range(body)]
                end = min(top + body, len(lines))
                pos = "akhir" if top >= maxtop else f"{top + 1}-{end}/{len(lines)}"
                out.append(f"\x1b[{rows};1H\x1b[7m {title} · {pos} · mouse wheel / ↑↓ / PgUp PgDn · \x1b[1mq / Esc / Enter = back to the input\x1b[22m \x1b[K\x1b[0m")
                _w("".join(out))
                last_size, dirty = (cols, rows), False
            if not select.select([fd], [], [], 0.3)[0]:
                continue
            buf += os.read(fd, 256)
            while buf:
                m = MOUSE.match(buf)
                if m:
                    btn = int(m.group(1))
                    buf = buf[m.end():]
                    if btn == 64:
                        top -= 3
                    elif btn == 65:
                        top += 3
                    else:
                        continue
                    dirty = True
                    continue
                if buf.startswith(b"\x1b["):
                    m2 = CSI.match(buf)
                    if not m2:
                        if len(buf) < 24:
                            break
                        buf = b""
                        break
                    seq, buf = m2.group(0), buf[m2.end():]
                    dirty = True
                    if seq == b"\x1b[A":
                        top -= 1
                    elif seq == b"\x1b[B":
                        top += 1
                    elif seq == b"\x1b[5~":
                        top -= body
                    elif seq == b"\x1b[6~":
                        top += body
                    elif seq in (b"\x1b[H", b"\x1b[1~"):
                        top = 0
                    elif seq in (b"\x1b[F", b"\x1b[4~"):
                        top = maxtop
                    else:
                        dirty = False
                    continue
                if buf == b"\x1b":
                    return
                ch, buf = buf[:1], buf[1:]
                dirty = True
                if ch in (b"q", b"Q", b"\x03", b"\r", b"\n"):
                    return
                elif ch in (b"k",):
                    top -= 1
                elif ch in (b"j",):
                    top += 1
                elif ch == b" ":
                    top += body
                elif ch == b"b":
                    top -= body
                elif ch == b"g":
                    top = 0
                elif ch == b"G":
                    top = maxtop
                else:
                    dirty = False
    finally:
        _w("\x1b[?7h\x1b[?25h\x1b[?1006l\x1b[?1000l\x1b[0m\x1b[2J\x1b[H")
        termios.tcflush(fd, termios.TCIFLUSH)       # buang sisa event mouse
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def tail(text: str, rows_reserved: int = 14) -> str:
    """The end of the history, to be redrawn on screen after the viewer closes."""
    n = max(5, shutil.get_terminal_size().lines - rows_reserved)
    return "\n".join(clean(text).rstrip("\n").split("\n")[-n:]) + "\x1b[0m\n\n"
