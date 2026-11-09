"""Terminal image output for terminals that support the kitty graphics protocol with
Unicode placeholders (kitty, Ghostty). The picture is transmitted out-of-band as PNG; in the
text grid it is just placeholder characters, so it scrolls and redraws like any other text."""
from . import paths
import atexit
import base64
import glob
import io
import os
import sys
import time

import numpy as np
from PIL import Image

# row/column diacritics from the kitty spec (rowcolumn-diacritics.txt, 297 entries)
DIAC = [
    0x0305, 0x030D, 0x030E, 0x0310, 0x0312, 0x033D, 0x033E, 0x033F,
    0x0346, 0x034A, 0x034B, 0x034C, 0x0350, 0x0351, 0x0352, 0x0357,
    0x035B, 0x0363, 0x0364, 0x0365, 0x0366, 0x0367, 0x0368, 0x0369,
    0x036A, 0x036B, 0x036C, 0x036D, 0x036E, 0x036F, 0x0483, 0x0484,
    0x0485, 0x0486, 0x0487, 0x0592, 0x0593, 0x0594, 0x0595, 0x0597,
    0x0598, 0x0599, 0x059C, 0x059D, 0x059E, 0x059F, 0x05A0, 0x05A1,
    0x05A8, 0x05A9, 0x05AB, 0x05AC, 0x05AF, 0x05C4, 0x0610, 0x0611,
    0x0612, 0x0613, 0x0614, 0x0615, 0x0616, 0x0617, 0x0657, 0x0658,
    0x0659, 0x065A, 0x065B, 0x065D, 0x065E, 0x06D6, 0x06D7, 0x06D8,
    0x06D9, 0x06DA, 0x06DB, 0x06DC, 0x06DF, 0x06E0, 0x06E1, 0x06E2,
    0x06E4, 0x06E7, 0x06E8, 0x06EB, 0x06EC, 0x0730, 0x0732, 0x0733,
    0x0735, 0x0736, 0x073A, 0x073D, 0x073F, 0x0740, 0x0741, 0x0743,
    0x0745, 0x0747, 0x0749, 0x074A, 0x07EB, 0x07EC, 0x07ED, 0x07EE,
    0x07EF, 0x07F0, 0x07F1, 0x07F3, 0x0816, 0x0817, 0x0818, 0x0819,
    0x081B, 0x081C, 0x081D, 0x081E, 0x081F, 0x0820, 0x0821, 0x0822,
    0x0823, 0x0825, 0x0826, 0x0827, 0x0829, 0x082A, 0x082B, 0x082C,
    0x082D, 0x0951, 0x0953, 0x0954, 0x0F82, 0x0F83, 0x0F86, 0x0F87,
    0x135D, 0x135E, 0x135F, 0x17DD, 0x193A, 0x1A17, 0x1A75, 0x1A76,
    0x1A77, 0x1A78, 0x1A79, 0x1A7A, 0x1A7B, 0x1A7C, 0x1B6B, 0x1B6D,
    0x1B6E, 0x1B6F, 0x1B70, 0x1B71, 0x1B72, 0x1B73, 0x1CD0, 0x1CD1,
    0x1CD2, 0x1CDA, 0x1CDB, 0x1CE0, 0x1DC0, 0x1DC1, 0x1DC3, 0x1DC4,
    0x1DC5, 0x1DC6, 0x1DC7, 0x1DC8, 0x1DC9, 0x1DCB, 0x1DCC, 0x1DD1,
    0x1DD2, 0x1DD3, 0x1DD4, 0x1DD5, 0x1DD6, 0x1DD7, 0x1DD8, 0x1DD9,
    0x1DDA, 0x1DDB, 0x1DDC, 0x1DDD, 0x1DDE, 0x1DDF, 0x1DE0, 0x1DE1,
    0x1DE2, 0x1DE3, 0x1DE4, 0x1DE5, 0x1DE6, 0x1DFE, 0x20D0, 0x20D1,
    0x20D4, 0x20D5, 0x20D6, 0x20D7, 0x20DB, 0x20DC, 0x20E1, 0x20E7,
    0x20E9, 0x20F0, 0x2CEF, 0x2CF0, 0x2CF1, 0x2DE0, 0x2DE1, 0x2DE2,
    0x2DE3, 0x2DE4, 0x2DE5, 0x2DE6, 0x2DE7, 0x2DE8, 0x2DE9, 0x2DEA,
    0x2DEB, 0x2DEC, 0x2DED, 0x2DEE, 0x2DEF, 0x2DF0, 0x2DF1, 0x2DF2,
    0x2DF3, 0x2DF4, 0x2DF5, 0x2DF6, 0x2DF7, 0x2DF8, 0x2DF9, 0x2DFA,
    0x2DFB, 0x2DFC, 0x2DFD, 0x2DFE, 0x2DFF, 0xA66F, 0xA67C, 0xA67D,
    0xA6F0, 0xA6F1, 0xA8E0, 0xA8E1, 0xA8E2, 0xA8E3, 0xA8E4, 0xA8E5,
    0xA8E6, 0xA8E7, 0xA8E8, 0xA8E9, 0xA8EA, 0xA8EB, 0xA8EC, 0xA8ED,
    0xA8EE, 0xA8EF, 0xA8F0, 0xA8F1, 0xAAB0, 0xAAB2, 0xAAB3, 0xAAB7,
    0xAAB8, 0xAABE, 0xAABF, 0xAAC1, 0xFE20, 0xFE21, 0xFE22, 0xFE23,
    0xFE24, 0xFE25, 0xFE26, 0x10A0F, 0x10A38, 0x1D185, 0x1D186, 0x1D187,
    0x1D188, 0x1D189, 0x1D1AA, 0x1D1AB, 0x1D1AC, 0x1D1AD, 0x1D242, 0x1D243,
    0x1D244,
]
PLACEHOLDER = "\U0010EEEE"
Q = "0" if paths.env("GFX_DEBUG") else "2"   # debug: let the terminal answer (errors become visible)
RING = 4                      # image ids rotate so the picture being shown is never deleted mid-frame
MAX_PX = 480                  # longest side of the transmitted picture (keeps each PNG small)

_live: set[int] = set()


def supported() -> bool:
    """kitty graphics + Unicode placeholders: kitty and Ghostty. EMILIE_GFX=off|on forces it."""
    force = paths.env("GFX", "").lower()
    if force in ("0", "off", "no", "false", "none"):
        return False
    if not sys.stdout.isatty():
        return False
    if force in ("1", "on", "yes", "true", "kitty"):
        return True
    env = os.environ
    if env.get("TMUX") or env.get("STY") or env.get("SSH_CONNECTION"):      # passthrough / slow link -> half-block
        return False
    if env.get("COLORTERM", "").lower() not in ("truecolor", "24bit"):     # the image id is carried in the fg colour
        return False
    return bool(env.get("KITTY_WINDOW_ID") or env.get("TERM", "") in ("xterm-kitty", "xterm-ghostty")
                or env.get("TERM_PROGRAM", "").lower() == "ghostty")


def cell_px() -> tuple[int, int]:
    """Size of one terminal cell in pixels (fallback 10x20)."""
    try:
        import fcntl
        import struct
        import termios
        r, c, xp, yp = struct.unpack("HHHH", fcntl.ioctl(1, termios.TIOCGWINSZ, b"\0" * 8))
        if xp and yp and c and r:
            return max(4, xp // c), max(8, yp // r)
    except Exception:
        pass
    return 10, 20


def _write(data: bytes) -> None:
    fd, mv = 1, memoryview(data)
    while mv:
        try:
            n = os.write(fd, mv)
        except BlockingIOError:
            import select
            select.select([], [fd], [], 0.2)
            continue
        mv = mv[n:]


def _delete(i: int) -> None:
    _write(f"\x1b_Ga=d,d=I,i={i},q={Q}\x1b\\".encode())
    _live.discard(i)


def cleanup() -> None:
    for f in glob.glob(f"/dev/shm/emilie-{os.getpid()}-*"):
        try:
            os.unlink(f)
        except OSError:
            pass
    for i in list(_live):
        try:
            _delete(i)
        except Exception:
            pass


atexit.register(cleanup)


class View:
    """One picture shown on a cols x rows block of placeholder cells."""
    _next = 0

    def __init__(self, cols: int, rows: int):
        if cols > len(DIAC) or rows > len(DIAC):
            raise ValueError("image too large for placeholders")
        self.cols, self.rows = cols, rows
        View._next += 1
        base = 0x100000 + ((os.getpid() & 0xFFF) << 8) + View._next * RING
        self.ids = [base + k for k in range(RING)]
        self.n = 0
        self.cur = self.ids[0]
        self._shm_seq = 0
        # shared memory only for kitty itself (verified in its protocol docs); others get PNG over the tty
        self._shm_ok = bool(os.environ.get("KITTY_WINDOW_ID")) and os.path.isdir("/dev/shm") \
            and paths.env("GFX_SHM", "1") != "0"
        self.cells = ["".join(PLACEHOLDER + chr(DIAC[r]) + chr(DIAC[c]) for c in range(cols)) for r in range(rows)]

    def send(self, rgba: np.ndarray) -> None:
        """Transmit a new picture under the next id; delete the one before the previous (no blank flash)."""
        mode = paths.env("GFX_MODE", "fresh")   # fresh | ring | nodelete (debug)
        if mode == "fresh":                       # a new id every frame: an id is never deleted and reused right after
            i = self.ids[0] + 16 + (self.n % 0x40000)
        else:
            i = self.ids[self.n % RING]
        self.n += 1
        place = f"a=T,i={i},p=1,U=1,c={self.cols},r={self.rows},q={Q}"
        h, w = rgba.shape[:2]
        if self._shm_ok:
            try:
                self._send_shm(place, rgba, w, h)
            except OSError:
                self._shm_ok = False
        if not self._shm_ok:
            self._send_png(place, rgba)
        _live.add(i)
        if mode == "fresh":
            if self.n > RING:
                _delete(self.ids[0] + 16 + ((self.n - 1 - RING) % 0x40000))
        elif mode != "nodelete" and self.n >= RING:   # delete the id from RING-1 frames ago, never one that may be on screen
            old = self.ids[self.n % RING]
            if old in _live:
                _delete(old)
        self.cur = i

    def _send_shm(self, place: str, rgba: np.ndarray, w: int, h: int) -> None:
        """Local kitty: raw RGBA through POSIX shared memory (no PNG encode, almost nothing through the tty)."""
        self._shm_seq += 1
        if self._shm_seq % 90 == 0:               # sweep files kitty never picked up (never one that may still be read)
            now = time.time()
            for f in glob.glob(f"/dev/shm/emilie-{os.getpid()}-*"):
                try:
                    if now - os.stat(f).st_mtime > 5:
                        os.unlink(f)
                except OSError:
                    pass
        name = f"/emilie-{os.getpid()}-{self.ids[0]:x}-{self._shm_seq}"   # unique name: kitty may still be reading the last one
        fd = os.open("/dev/shm" + name, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        try:
            os.write(fd, rgba.tobytes())
        finally:
            os.close(fd)
        ctl = f"{place},f=32,s={w},v={h},t=s"
        _write(b"\x1b_G" + ctl.encode() + b";" + base64.standard_b64encode(name.encode()) + b"\x1b\\")

    def _send_png(self, place: str, rgba: np.ndarray) -> None:
        buf = io.BytesIO()
        Image.fromarray(rgba, "RGBA").save(buf, "PNG", compress_level=1)
        b64 = base64.standard_b64encode(buf.getvalue())
        out, pos = [], 0
        while pos < len(b64):
            chunk, pos = b64[pos:pos + 4096], pos + 4096
            more = 1 if pos < len(b64) else 0
            ctl = f"{place},f=100,m={more}" if not out else f"m={more},q=2"
            out.append(b"\x1b_G" + ctl.encode() + b";" + chunk + b"\x1b\\")
        _write(b"".join(out))

    def style(self) -> str:
        return f"fg:#{self.cur:06x}"
