"""Sixel output (Windows Terminal 1.22+, WezTerm, foot, mlterm...): real pixels on terminals without the kitty protocol.

Standalone on purpose: `python -m emilie.sixel [seconds] [size] [colours]` (or `bench`) plays the logo video as real pixels, so you can check
that your terminal renders Sixel before anything else depends on it. Nothing else imports this module yet."""
from __future__ import annotations

import os
import sys
import time

import numpy as np
from PIL import Image

ESC = "\x1b"


def encode(rgb: np.ndarray, colors: int = 48, mask: np.ndarray | None = None) -> str:
    """uint8 HxWx3 -> a complete Sixel string (DCS ... ST). Palette is quantised per frame (no dithering = no shimmer).
    mask (bool HxW, True = draw): pixels outside it stay transparent (the terminal's own background shows through)."""
    h, w = rgb.shape[:2]
    if mask is not None and mask.any() and not mask.all():
        rgb = rgb.copy()
        rgb[~mask] = rgb[mask].mean(axis=0).astype(np.uint8)       # hidden pixels must not use up palette entries
    q = Image.fromarray(rgb).quantize(colors=colors, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
    idx = np.asarray(q, dtype=np.uint8).copy()
    if mask is not None:
        idx[~mask] = 255
    pal = np.asarray(q.getpalette()[:colors * 3], dtype=np.uint8).reshape(-1, 3)
    out = [f'{ESC}P0;1;q"1;1;{w};{h}']                      # P2=1: untouched pixels stay transparent
    for i, (r, g, b) in enumerate(pal):                       # palette: percentages 0..100
        out.append(f"#{i};2;{int(r) * 100 // 255};{int(g) * 100 // 255};{int(b) * 100 // 255}")
    pad = (-h) % 6
    if pad:
        idx = np.vstack([idx, np.full((pad, w), 255, np.uint8)])    # 255 = no colour (never matches a palette entry)
    for y0 in range(0, idx.shape[0], 6):
        band = idx[y0:y0 + 6]
        used = np.unique(band)
        parts = []
        for c in used:
            if c == 255:
                continue
            bits = np.zeros(w, np.uint8)
            for r in range(6):
                bits |= ((band[r] == c).astype(np.uint8) << r)
            parts.append(f"#{int(c)}" + _rle(bits))
        out.append("$".join(parts) + "-")                      # $ = back to the band start for the next colour, - = next band
    out.append(f"{ESC}\\")
    return "".join(out)


def _rle(bits: np.ndarray) -> str:
    chars = (bits + 63).tobytes().decode("ascii")
    s, n, i = [], len(chars), 0
    while i < n:
        j = i + 1
        while j < n and chars[j] == chars[i]:
            j += 1
        run = j - i
        s.append(f"!{run}{chars[i]}" if run > 3 else chars[i] * run)
        i = j
    return "".join(s)


def supported() -> bool:
    """Opt-in guess: Windows Terminal (WT_SESSION) or EMILIE_SIXEL=on. EMILIE_SIXEL=off always wins."""
    force = os.environ.get("EMILIE_SIXEL", "").lower()
    if force in ("0", "off", "no", "false"):
        return False
    if not sys.stdout.isatty():
        return False
    return force in ("1", "on", "yes", "true") or bool(os.environ.get("WT_SESSION") or os.environ.get("WEZTERM_EXECUTABLE"))


MAX_PX = int(os.environ.get("EMILIE_SIXEL_PX", "") or 220)   # longest side of the picture: Sixel cannot be scaled, so this also caps the logo size
_cell: tuple[int, int] | None = None


def init_cell_px() -> None:
    """Ask the terminal for its cell size (CSI 16 t -> CSI 6;h;w t). Must run BEFORE the full-screen UI owns stdin.
    EMILIE_CELL=WxH overrides; if the terminal stays silent we assume 10x20."""
    global _cell
    try:
        w, h = os.environ.get("EMILIE_CELL", "").lower().split("x")
        _cell = (int(w), int(h))
        return
    except ValueError:
        pass
    _cell = (10, 20)
    if os.name != "nt" or not sys.stdin.isatty():
        return
    try:
        import msvcrt
        sys.stdout.write(f"{ESC}[16t")
        sys.stdout.flush()
        buf, end = "", time.monotonic() + 0.4
        while time.monotonic() < end and not buf.endswith("t"):
            if msvcrt.kbhit():
                buf += msvcrt.getwch()
            else:
                time.sleep(0.005)
        if buf.endswith("t") and buf.startswith(f"{ESC}[6;"):
            hh, ww = buf[4:-1].split(";")[:2]
            if int(ww) >= 4 and int(hh) >= 8:
                _cell = (int(ww), int(hh))
    except Exception:
        pass


def cell_px() -> tuple[int, int]:
    return _cell or (10, 20)


class View:
    """Same shape as gfx.View (cols, rows, cells, send, style) so Sprite.render_hd drives it unchanged.
    The picture is NOT in the text grid: carrier() returns the escape that pt writes once per new frame."""
    COLORS = 48

    def __init__(self, cols: int, rows: int):
        self.cols, self.rows = cols, rows
        self.cells = [" " * cols for _ in range(rows)]
        self.esc = ""
        self.n = 0

    def send(self, rgba: np.ndarray) -> None:
        self.esc = encode(np.ascontiguousarray(rgba[..., :3]), self.COLORS, rgba[..., 3] > 127)
        self.n += 1

    def style(self) -> str:
        return ""

    def carrier(self) -> list[tuple[str, str]]:
        """Goes in ONE cell just after the last logo row (outside the picture). Its colour is the frame number, so every new
        frame (and only a new frame) makes prompt_toolkit redraw that cell, and it emits the escape then: save cursor, jump to the logo's top-left cell,
        draw the picture, restore the cursor."""
        if not self.esc:
            return [("", " ")]
        jump = (f"{ESC}[{self.rows - 1}A" if self.rows > 1 else "") + f"{ESC}[{self.cols}D"
        return [("[ZeroWidthEscape]", f"{ESC}7{jump}{self.esc}{ESC}8"), (f"fg:#{self.n & 0xFFFFFF:06x}", " ")]


def _play(frames, src_fps: float, secs: float, fps: float, colors: int) -> float:
    """Play for `secs` seconds, return the fps the terminal actually managed (frames are skipped, never queued)."""
    t0, shown, last = time.monotonic(), 0, -1
    while time.monotonic() - t0 < secs:
        i = int((time.monotonic() - t0) * src_fps) % len(frames)
        if i != last:
            sys.stdout.write(f"{ESC}[3;1H" + encode(frames[i], colors))
            sys.stdout.flush()
            shown, last = shown + 1, i
        time.sleep(0.001)
    return shown / (time.monotonic() - t0)


def _demo() -> None:
    from . import logo
    a = sys.argv[1:]
    bench = bool(a) and a[0] == "bench"
    if bench:
        a = a[1:]
    secs = float(a[0]) if a else (3.0 if bench else 15.0)
    side = int(a[1]) if len(a) > 1 else 192
    colors = int(a[2]) if len(a) > 2 else 48
    if not supported():
        print("Sixel is not enabled for this terminal. Windows Terminal 1.22+ sets WT_SESSION; "
              "otherwise force it with EMILIE_SIXEL=on (PowerShell: $env:EMILIE_SIXEL='on').")
        return
    p = logo.find_logo()
    if p is None:
        print("no logo file found")
        return
    src = logo.Source(p)
    cfgs = [(192, 48), (160, 32), (128, 32), (128, 16), (96, 16)] if bench else [(side, colors)]
    res = []
    sys.stdout.write(f"{ESC}[?1049h{ESC}[?25l{ESC}[2J")
    try:
        for sd, co in cfgs:
            frames = [np.asarray(Image.fromarray(f).resize((sd, int(sd * src.aspect)), Image.LANCZOS)) for f in src.raw]
            sys.stdout.write(f"{ESC}[2J{ESC}[1;1H{sd}px / {co} colours   (Ctrl+C to quit)")
            res.append((sd, co, _play(frames, src.fps if src.is_video else 1, secs, 0, co)))
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write(f"{ESC}[?25h{ESC}[?1049l")
        for sd, co, f in res:
            print(f"size {sd:>3}px  colours {co:>2}  ->  {f:4.1f} fps")


if __name__ == "__main__":
    _demo()
