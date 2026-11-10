"""Sixel output (Windows Terminal 1.22+, WezTerm, foot, mlterm...): real pixels on terminals without the kitty protocol.

Standalone on purpose: `python -m emilie.sixel [fps] [seconds]` plays the logo video as real pixels, so you can check
that your terminal renders Sixel before anything else depends on it. Nothing else imports this module yet."""
from __future__ import annotations

import os
import sys
import time

import numpy as np
from PIL import Image

ESC = "\x1b"


def encode(rgb: np.ndarray, colors: int = 48) -> str:
    """uint8 HxWx3 -> a complete Sixel string (DCS ... ST). Palette is quantised per frame (no dithering = no shimmer)."""
    h, w = rgb.shape[:2]
    q = Image.fromarray(rgb).quantize(colors=colors, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
    idx = np.asarray(q, dtype=np.uint8)
    pal = np.asarray(q.getpalette()[:colors * 3], dtype=np.uint8).reshape(-1, 3)
    out = [f'{ESC}Pq"1;1;{w};{h}']
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


def cell_px() -> tuple[int, int]:
    """Cell size in pixels; Windows Terminal does not report it, so assume the usual 10x20 (override: EMILIE_CELL=WxH)."""
    v = os.environ.get("EMILIE_CELL", "")
    try:
        w, h = v.lower().split("x")
        return int(w), int(h)
    except ValueError:
        return 10, 20


def _demo() -> None:
    from . import logo
    fps = float(sys.argv[1]) if len(sys.argv) > 1 else 12.0
    secs = float(sys.argv[2]) if len(sys.argv) > 2 else 15.0
    if not supported():
        print("Sixel is not enabled for this terminal. Windows Terminal 1.22+ sets WT_SESSION; "
              "otherwise force it with EMILIE_SIXEL=on (PowerShell: $env:EMILIE_SIXEL='on').")
        return
    p = logo.find_logo()
    if p is None:
        print("no logo file found")
        return
    src = logo.Source(p)
    side = 200
    frames = [np.asarray(Image.fromarray(f).resize((side, int(side * src.aspect)), Image.LANCZOS)) for f in src.raw]
    sys.stdout.write(f"{ESC}[?1049h{ESC}[?25l{ESC}[2J{ESC}[1;1HSixel demo: {len(frames)} frames, Ctrl+C to quit")
    t0, shown = time.monotonic(), 0
    try:
        while time.monotonic() - t0 < secs:
            f = frames[int((time.monotonic() - t0) * (src.fps if src.is_video else 1)) % len(frames)]
            sys.stdout.write(f"{ESC}[3;1H" + encode(f))
            sys.stdout.flush()
            shown += 1
            time.sleep(max(0.0, 1.0 / fps - 0.001))
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write(f"{ESC}[?25h{ESC}[?1049l")
        print(f"{shown} frames in {time.monotonic() - t0:.1f}s = {shown / (time.monotonic() - t0):.1f} fps")


if __name__ == "__main__":
    _demo()
