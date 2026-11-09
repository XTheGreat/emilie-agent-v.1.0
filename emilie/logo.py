"""HD logo for the terminal.

Source : video (mp4/webm/mov/gif) OR image. A video loops.
Render : half-block "▀" + truecolor -> 2 pixels per cell (HD, not braille dots).
Effects: intro (diagonal sweep from top-left to bottom-right) and a WATER RIPPLE simulated
         with a real wave equation (damping + reflection at the edges).
"""
from . import paths
import hashlib
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps, ImageSequence
from rich.text import Text

from .i18n import t as tr_
from .effort import HOME_DIR, load_settings

ASSETS = Path(__file__).resolve().parent.parent / "assets"
VIDEO_EXTS = {".mp4", ".webm", ".mov", ".mkv", ".gif", ".avi", ".m4v"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
CACHE = HOME_DIR / "cache"

DECODE_SIDE = 192      # longest side of the decoded frame (enough for a terminal size)
DECODE_FPS = 30.0      # decoded once at 30 fps; playback speed stays real-time, the display fps is set separately
MAX_SECONDS = 20.0
INTRO = 1.4            # seconds: diagonal sweep when it first appears
FLASH = 0.35           # seconds: sparkle at the drop point
SMOOTH = 0.5           # weight of the current frame in the temporal blend (1.0 = off); removes codec noise
HOLD = 12              # a cell keeps its previous colour while every channel changes by less than this (anti-flicker)


# ------------------------------------------------------------------ sumber
def find_logo() -> Path | None:
    """EMILIE_LOGO -> /logo setting -> assets/logo.<video> -> assets/logo.<image>."""
    cands: list[Path] = []
    if paths.env("LOGO"):
        cands.append(Path(paths.env("LOGO")).expanduser())
    if load_settings().get("logo"):
        cands.append(Path(load_settings()["logo"]).expanduser())
    files = [p for p in sorted(ASSETS.glob("logo*")) if p.is_file()]
    cands += [p for p in files if p.suffix.lower() in VIDEO_EXTS]
    cands += [p for p in files if p.suffix.lower() in IMAGE_EXTS]
    for p in cands:
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS | IMAGE_EXTS:
            return p
    return None


def find_still() -> Path | None:
    """Still image for the low-CPU mode: assets/icon.* then assets/logo.<image>; None -> first video frame."""
    for pat in ("icon*", "logo*"):
        for p in sorted(ASSETS.glob(pat)):
            if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
                return p
    return None


HD_SIDE = 360          # decoded size for the image-protocol (HD) mode
HD_FPS = 15.0          # PNG per frame, so fewer frames than the half-block mode


def _fit(img: Image.Image, side: int = DECODE_SIDE) -> Image.Image:
    img = img.convert("RGB")
    img.thumbnail((side, side), Image.LANCZOS)
    return img


def _decode_gif(path: Path, side: int = DECODE_SIDE, fps: float = DECODE_FPS) -> list[Image.Image]:
    im = Image.open(path)
    frames, times, t = [], [], 0.0
    for fr in ImageSequence.Iterator(im):
        times.append(t)
        t += (fr.info.get("duration", 100) or 100) / 1000
        frames.append(_fit(fr, side))
    total = min(t, MAX_SECONDS)
    idx = np.searchsorted(times, np.arange(0, total, 1 / fps), side="right") - 1
    return [frames[max(0, int(i))] for i in idx]


def _decode_av(path: Path, side: int = DECODE_SIDE, fps: float = DECODE_FPS) -> list[Image.Image]:
    try:
        import av
    except ImportError as e:
        raise RuntimeError(tr_("playing video needs the 'av' package (pip install av)")) from e
    out, next_t = [], 0.0
    with av.open(str(path)) as c:
        s = c.streams.video[0]
        for fr in c.decode(s):
            t = float(fr.pts * s.time_base) if fr.pts is not None else len(out) / fps
            if t > MAX_SECONDS:
                break
            if t + 1e-6 >= next_t:
                out.append(_fit(fr.to_image(), side))
                next_t += 1 / fps
    if not out:
        raise RuntimeError(tr_('empty video / could not be decoded'))
    return out


def _cache_file(path: Path, side: int, fps: float) -> Path:
    st = path.stat()
    key = hashlib.sha1(f"{path.resolve()}|{st.st_mtime_ns}|{st.st_size}|{side}|{fps}|{MAX_SECONDS}".encode()).hexdigest()[:16]
    return CACHE / f"{key}.npy"


def needs_decode(path: Path, hd: bool = False) -> bool:
    """True if this video was never decoded before (no cache yet) -> the very first launch is slower."""
    if path.suffix.lower() in IMAGE_EXTS:
        return False
    return not _cache_file(path, HD_SIDE if hd else DECODE_SIDE, HD_FPS if hd else DECODE_FPS).exists()


def load_frames(path: Path, hd: bool = False) -> tuple[np.ndarray, float]:
    """-> (uint8 [n,h,w,3], fps). The video is cached in ~/.emilie/cache so the next launch is instant.
    hd=True decodes larger frames at a lower fps (memory-mapped from the cache)."""
    side, fps = (HD_SIDE, HD_FPS) if hd else (DECODE_SIDE, DECODE_FPS)
    ext = path.suffix.lower()
    if ext in IMAGE_EXTS:
        return np.asarray(_fit(Image.open(path), side))[None], 1.0
    cf = _cache_file(path, side, fps)
    try:
        return np.load(cf, mmap_mode="r" if hd else None), fps
    except (OSError, ValueError):
        pass
    imgs = _decode_gif(path, side, fps) if ext == ".gif" else _decode_av(path, side, fps)
    arr = np.stack([np.asarray(i) for i in imgs])
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        np.save(cf, arr)
    except OSError:
        pass
    return arr, fps


class Source:
    def __init__(self, path: Path, hd: bool = False):
        self.path = path
        self.hd = hd
        self.raw, self.fps = load_frames(path, hd)
        self.aspect = min(max(self.raw.shape[1] / self.raw.shape[2], 0.6), 1.6)
        self.is_video = len(self.raw) > 1
        self._cache: dict[tuple[int, int], list[np.ndarray]] = {}

    def make_still(self) -> "Source":
        """Turn this source into a single still image (the first frame)."""
        self.raw = np.asarray(self.raw[:1])
        self.is_video = False
        self._cache.clear()
        return self

    def frames_at(self, w: int, h: int) -> list[np.ndarray]:
        if (w, h) not in self._cache:
            fr = [np.asarray(ImageOps.fit(Image.fromarray(f), (w, h), Image.LANCZOS, centering=(0.5, 0.35)),
                             dtype=np.float32) for f in self.raw]
            if len(fr) > 2 and SMOOTH < 1.0:          # blend with the neighbouring frames (loops around)
                side = (1 - SMOOTH) / 2
                fr = [SMOOTH * fr[i] + side * (fr[i - 1] + fr[(i + 1) % len(fr)]) for i in range(len(fr))]
            self._cache[(w, h)] = fr
        return self._cache[(w, h)]


# ------------------------------------------------------------------ air
class Water:
    """2D wave equation on the pixel grid: h' = 2h - h_prev + c²∇²h, then damped.
    The edges reflect the wave; a drop = a gaussian impulse."""
    HZ, C2, DAMP = 60.0, 0.24, 0.98

    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        self.cur = np.zeros((h, w), np.float32)
        self.prev = np.zeros((h, w), np.float32)
        self.yy, self.xx = np.mgrid[0:h, 0:w].astype(np.float32)
        self.t: float | None = None

    @property
    def active(self) -> bool:
        return bool(np.abs(self.cur).max() > 0.05)

    def drop(self, x: float, y: float, strength: float = 1.1) -> None:
        d2 = (self.xx + 0.5 - x) ** 2 + (self.yy + 0.5 - y) ** 2
        self.cur -= strength * np.exp(-d2 / (2 * 1.3 ** 2))

    def advance(self, t: float) -> None:
        if self.t is None:
            self.t = t
            return
        n = int((t - self.t) * self.HZ)
        if n > 8:                       # not rendered for a long time -> just jump
            n, self.t = 8, t - 8 / self.HZ
        for _ in range(n):
            p = np.pad(self.cur, 1, mode="edge")
            lap = p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:] - 4 * self.cur
            self.cur, self.prev = (2 * self.cur - self.prev + self.C2 * lap) * self.DAMP, self.cur
        self.t += n / self.HZ
        if not self.active:
            self.cur[:] = 0
            self.prev[:] = 0


class Sprite:
    """One logo view `cols` cells wide (the height follows the source aspect ratio)."""

    def __init__(self, src: Source, cols: int, gfx: bool = False):
        h = max(2, round(cols * src.aspect))
        self.w, self.h = cols, h + h % 2
        self.src = src
        self._frames: list[np.ndarray] | None = None     # half-block frames, built on first use
        self.view = None                                  # gfx.View when the image protocol is used
        self._hd_key = None
        self._mask_cache: tuple | None = None
        if gfx:
            try:
                from . import gfx as _gfx
                cw, ch = _gfx.cell_px()
                pw, ph = self.w * cw, (self.h // 2) * ch
                k = min(1.0, _gfx.MAX_PX / max(pw, ph), src.raw.shape[2] / pw, src.raw.shape[1] / ph)
                self.px = (max(8, int(pw * k)), max(8, int(ph * k)))
                self.view = _gfx.View(self.w, self.h // 2)
            except Exception:
                self.view = None
        self.water = Water(self.w, self.h)
        yy, xx = np.mgrid[0:self.h, 0:self.w].astype(np.float32)
        self.xx, self.yy = xx + 0.5, yy + 0.5
        r = 0.09 * min(self.w, self.h)                    # rounded corners
        qx = np.abs(self.xx - self.w / 2) - (self.w / 2 - r)
        qy = np.abs(self.yy - self.h / 2) - (self.h / 2 - r)
        d = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r
        self.vis_base = (0.5 - d / 1.2) > 0.5
        self.t0: float | None = None
        self.last_t = 0.0
        self.flashes: list[tuple[float, float, float]] = []
        self._prev: np.ndarray | None = None

    @property
    def frames(self) -> list[np.ndarray]:
        if self._frames is None:
            self._frames = self.src.frames_at(self.w, self.h)
        return self._frames

    @property
    def rows(self) -> int:
        return self.h // 2

    def drop(self, x: float, y: float) -> None:
        """Drop a water drop at pixel coordinates (x, y)."""
        if 0 <= x < self.w and 0 <= y < self.h:
            self.water.drop(x, y)
            self.flashes.append((x, y, self.last_t))

    @property
    def animating(self) -> bool:
        return self.src.is_video or self.water.active or bool(self.flashes) or \
            (self.t0 is not None and self.last_t - self.t0 < INTRO)

    def render(self, t: float) -> tuple[np.ndarray, np.ndarray]:
        """-> (uint8 HxWx3, bool HxW visible) at time t (seconds; any clock, but monotonic)."""
        if self.t0 is None:
            self.t0 = t
        self.last_t = t
        lt = t - self.t0
        base = self.frames[int(lt * self.src.fps) % len(self.frames)] if self.src.is_video else self.frames[0]
        w = self.water
        w.advance(t)
        img = base
        if w.active:
            gy, gx = np.gradient(w.cur)
            k = max(self.w, self.h) / 8.0                 # refraction strength (scaled with size)
            xs = np.clip(np.rint(self.xx - 0.5 + gx * k), 0, self.w - 1).astype(np.intp)
            ys = np.clip(np.rint(self.yy - 0.5 + gy * k), 0, self.h - 1).astype(np.intp)
            light = -(gx + gy) * 0.7                       # light from the top-left
            img = base[ys, xs] * (1 + np.clip(w.cur * 0.40, -0.40, 0.22))[..., None] \
                + (np.clip(light, 0, None) * 120)[..., None]   # sparkle on the crest side of the wave
        self.flashes = [f for f in self.flashes if t - f[2] < FLASH]
        for x, y, t0 in self.flashes:                      # sparkle at the drop point
            f = 1 - (t - t0) / FLASH
            img = img + (np.exp(-((self.xx - x) ** 2 + (self.yy - y) ** 2) / (2 * 1.6 ** 2)) * 110 * f)[..., None]
        vis = self.vis_base
        if lt < INTRO:                                     # diagonal sweep from top-left -> bottom-right
            u = (self.xx / self.w + self.yy / self.h) / 2
            p = (lt / INTRO) * 1.25
            edge = np.clip(1 - (p - u) / 0.25, 0, 1) * (u < p)
            img = img + (edge * 90)[..., None]
            vis = vis & (u < p)
        out = np.clip(img, 0, 255).astype(np.uint8)
        if self.src.is_video:                              # hysteresis: tiny colour changes don't flicker
            prev = self._prev
            if prev is not None and prev.shape == out.shape:
                same = np.abs(out.astype(np.int16) - prev).max(axis=2) < HOLD
                out = np.where(same[..., None], prev, out)
            self._prev = out
        return out, vis


    # ---------------------------------------------------------- HD (image protocol)
    def _hd_mask(self, pw: int, ph: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        if self._mask_cache is None or self._mask_cache[0] != (pw, ph):
            yy, xx = np.mgrid[0:ph, 0:pw].astype(np.float32)
            xx, yy = xx + 0.5, yy + 0.5
            r = 0.09 * min(pw, ph)
            qx = np.abs(xx - pw / 2) - (pw / 2 - r)
            qy = np.abs(yy - ph / 2) - (ph / 2 - r)
            d = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r
            self._mask_cache = ((pw, ph), np.clip(0.5 - d, 0, 1), xx, yy)
        return self._mask_cache[1:]

    def render_hd(self, t: float) -> None:
        """Send the current HD frame (PNG, rounded corners, ripple, intro sweep) when it changed."""
        if self.t0 is None:
            self.t0 = t
        self.last_t = t
        lt = t - self.t0
        w = self.water
        w.advance(t)
        self.flashes.clear()
        n = len(self.src.raw)
        idx = int(lt * self.src.fps) % n if self.src.is_video else 0
        intro = lt < INTRO
        if not w.active and not intro and self._hd_key == idx:
            return                                           # nothing changed -> reuse the picture on screen
        pw, ph = self.px
        pil = ImageOps.fit(Image.fromarray(np.asarray(self.src.raw[idx])), (pw, ph), Image.LANCZOS,
                           centering=(0.5, 0.35))
        alpha, xx, yy = self._hd_mask(pw, ph)
        alpha = alpha.copy()
        add = None                                               # additive light (HD float), None = none
        gain = None
        if w.active:
            gy, gx = np.gradient(w.cur)
            k = max(self.w, self.h) / 8.0 * (pw / self.w)        # same refraction as the half-block mode, in HD pixels
            pad = lambda a: np.pad(a, 1, mode="edge")
            node = lambda a: (lambda q: (q[:-1, :-1] + q[1:, :-1] + q[:-1, 1:] + q[1:, 1:]) / 4)(pad(a))
            nx, ny = node(gx) * k, node(gy) * k                  # displacement on the (h+1)x(w+1) grid nodes
            ex = np.rint(np.linspace(0, pw, self.w + 1)).astype(int)
            ey = np.rint(np.linspace(0, ph, self.h + 1)).astype(int)
            sxn = np.clip(ex[None, :] + nx, 0, pw - 1)
            syn = np.clip(ey[:, None] + ny, 0, ph - 1)
            ci = list(range(0, self.w, 2)) + [self.w]            # mesh every 2nd node: displacement is smooth,
            ri = list(range(0, self.h, 2)) + [self.h]            # and fewer quads = less Python overhead
            ci = sorted(set(ci))
            ri = sorted(set(ri))
            mesh = []
            for a_, b_ in zip(ri[:-1], ri[1:]):
                for c_, d_ in zip(ci[:-1], ci[1:]):
                    mesh.append(((ex[c_], ey[a_], ex[d_], ey[b_]),
                                 (sxn[a_, c_], syn[a_, c_], sxn[b_, c_], syn[b_, c_],
                                  sxn[b_, d_], syn[b_, d_], sxn[a_, d_], syn[a_, d_])))
            pil = pil.transform((pw, ph), Image.MESH, mesh, Image.BILINEAR)
            up = lambda a: np.asarray(Image.fromarray(a.astype(np.float32), "F").resize((pw, ph), Image.BILINEAR))
            gxu, gyu, cu = up(gx), up(gy), up(w.cur)
            gain = (1 + np.clip(cu * 0.40, -0.40, 0.22))[..., None]
            add = (np.clip(-(gxu + gyu) * 0.7, 0, None) * 120)[..., None]
        img = np.asarray(pil, dtype=np.float32)
        if gain is not None:
            img = img * gain + add
        if intro:
            u = (xx / pw + yy / ph) / 2
            p = (lt / INTRO) * 1.25
            edge = np.clip(1 - (p - u) / 0.25, 0, 1) * (u < p)
            img = img + (edge * 90)[..., None]
            alpha = alpha * np.clip((p - u) * 40, 0, 1)
        rgba = np.dstack([np.clip(img, 0, 255), alpha * 255]).astype(np.uint8)
        self.view.send(np.ascontiguousarray(rgba))
        self._hd_key = idx


# ------------------------------------------------------------------ rich (banner statis)
def to_rich_text(img: np.ndarray, vis: np.ndarray) -> Text:
    out = Text()
    for y in range(0, img.shape[0], 2):
        for x in range(img.shape[1]):
            tv, bv, tr, br = vis[y, x], vis[y + 1, x], img[y, x], img[y + 1, x]
            if tv and bv:
                out.append("▀", style=f"#{tr[0]:02x}{tr[1]:02x}{tr[2]:02x} on #{br[0]:02x}{br[1]:02x}{br[2]:02x}")
            elif tv:
                out.append("▀", style=f"#{tr[0]:02x}{tr[1]:02x}{tr[2]:02x}")
            elif bv:
                out.append("▄", style=f"#{br[0]:02x}{br[1]:02x}{br[2]:02x}")
            else:
                out.append(" ")
        out.append("\n")
    out.rstrip()
    return out


def static_logo(cols: int) -> Text | None:
    p = find_logo()
    if not p:
        return None
    try:
        sp = Sprite(Source(p), cols)
    except Exception:
        return None
    sp.t0 = -100.0                                   # lewati animasi intro
    return to_rich_text(*sp.render(0.0))
