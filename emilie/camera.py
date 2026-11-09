"""Camera: ONE photo on demand (Alt+C), never a live feed.

The camera is opened only for the moment of the shot (ffmpeg, ~1 s), then closed again, so the camera light is
on just then. The photo is not written to disk: it goes straight into the message as an [Image #n].
Linux (video4linux2) via ffmpeg. Device: the `camera` setting (e.g. /dev/video0), otherwise the first one that works.
"""
import glob
import importlib.util
import io
import os
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

from . import effort

WARMUP_FRAMES = 10          # webcams need a few frames for exposure / white balance; the 10th frame is kept
TIMEOUT = 12


def available() -> bool:
    return bool(shutil.which("ffmpeg")) and bool(devices())


def devices() -> list[str]:
    return sorted(glob.glob("/dev/video*"), key=lambda p: int("".join(c for c in p if c.isdigit()) or 0))


def configured() -> str | None:
    v = effort.load_settings().get("camera")
    return str(v) if v else None


def set_device(path: str | None) -> None:
    effort.save_settings(camera=path or None)


def _shoot(dev: str) -> bytes | None:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "v4l2", "-i", dev,
           "-vf", f"select=gte(n\\,{WARMUP_FRAMES - 1})", "-frames:v", "1", "-f", "mjpeg", "-"]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=TIMEOUT, stdin=subprocess.DEVNULL)
    except (subprocess.TimeoutExpired, OSError):
        return None
    return r.stdout if r.returncode == 0 and len(r.stdout) > 1000 else None


def grab() -> tuple[bytes | None, str]:
    """-> (jpeg bytes or None, message). Tries the configured device first, then the others in order."""
    if not shutil.which("ffmpeg"):
        return None, "ffmpeg is not installed"
    devs = devices()
    if not devs:
        return None, "no camera found (/dev/video*)"
    first = configured()
    order = ([first] if first else []) + [d for d in devs if d != first]
    for d in order:
        if not os.path.exists(d):
            continue
        data = _shoot(d)
        if data:
            if _is_black(data):
                return None, f"the photo from {d} is completely black: lens cover or privacy shutter closed? (Fn camera key?)"
            return data, d
    return None, "could not take a photo (is the camera in use by another app, or blocked?)"


def _is_black(jpeg: bytes) -> bool:
    try:
        return Image.open(io.BytesIO(jpeg)).convert("L").getextrema()[1] <= 3
    except Exception:
        return False


# ====================================================================== video call mode (Alt+V)
import atexit
import collections
import tempfile
import threading
import time

import numpy as np

STREAM_W, STREAM_H, STREAM_FPS = 320, 180, 10
CLIP_SECONDS = 4
BLACK_AFTER = 25            # frames: if the first ones are all black, report it instead of showing a black window
_streams: "list[Stream]" = []


def _input_args(dev: str | None) -> list[str]:
    """ffmpeg input. EMILIE_CAMERA_SOURCE=lavfi:<filter> gives a test picture without hardware (used by the tests)."""
    src = paths_env("CAMERA_SOURCE")
    if src and src.startswith("lavfi:"):
        return ["-re", "-f", "lavfi", "-i", src[6:]]
    return ["-f", "v4l2", "-framerate", str(STREAM_FPS), "-video_size", "640x480", "-i", dev or ""]


def paths_env(name: str) -> str | None:
    from . import paths
    return paths.env(name)


class Stream:
    """The camera, open only while the video call mode is on. Keeps the newest frame (for the little window) and the last
    CLIP_SECONDS of frames in memory (for the clip that goes with a message). Nothing is written to disk."""

    def __init__(self):
        self.w, self.h, self.fps = STREAM_W, STREAM_H, STREAM_FPS
        self.latest: np.ndarray | None = None
        self.seq = 0
        self.frames: collections.deque = collections.deque(maxlen=CLIP_SECONDS * STREAM_FPS)
        self.error: str | None = None
        self.device = ""
        self.started = time.monotonic()
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._stop = False
        self._black = 0
        self.viewer: subprocess.Popen | None = None      # the separate call window, when there is one
        self.viewer_closed = False                       # True once the user closed that window
        self._feed_buf: bytes | None = None
        self._feed_ev = threading.Event()
        self._viewer_mpv = False
        self._viewer_t0 = 0.0

    def start(self) -> str | None:
        """-> error text, or None when ffmpeg is running."""
        if not shutil.which("ffmpeg"):
            return "ffmpeg is not installed"
        src = paths_env("CAMERA_SOURCE")
        dev = None
        if not (src and src.startswith("lavfi:")):
            devs = devices()
            if not devs:
                return "no camera found (/dev/video*)"
            first = configured()
            dev = first if first and os.path.exists(first) else devs[0]
        self.device = dev or "test source"
        vf = f"scale={self.w}:{self.h}:force_original_aspect_ratio=increase,crop={self.w}:{self.h}"
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", *_input_args(dev), "-vf", vf,
               "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
        try:
            self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL)
        except OSError as e:
            return str(e)
        _streams.append(self)
        threading.Thread(target=self._read, daemon=True).start()
        return None

    def _read(self) -> None:
        n = self.w * self.h * 3
        out = self._proc.stdout
        while not self._stop:
            buf = out.read(n)
            if len(buf) < n:
                break
            fr = np.frombuffer(buf, np.uint8).reshape(self.h, self.w, 3)
            if self.viewer is not None:
                self._feed_buf = buf
                self._feed_ev.set()
            with self._lock:
                self.latest = fr
                self.seq += 1
                self.frames.append(buf)
                if self.seq <= BLACK_AFTER:
                    self._black += 1 if fr.max() <= 3 else 0
                    if self.seq == BLACK_AFTER and self._black >= BLACK_AFTER:
                        self.error = "the camera image is black: lens cover / privacy shutter closed? (Fn camera key?)"
        if not self._stop and self.error is None:
            err = b""
            try:
                err = self._proc.stderr.read(400) if self._proc.stderr else b""
            except Exception:
                pass
            self.error = (err.decode(errors="replace").strip().splitlines() or ["the camera stopped"])[-1][:120]

    def open_viewer(self) -> bool:
        """Show the camera in its own window (a child process): mpv when installed (draws natively on Wayland and X11),
        otherwise a small Tk window. False if neither is possible here."""
        if not viewer_available():
            return False
        if not self._spawn_viewer(prefer_mpv=True):
            return False
        threading.Thread(target=self._feed_loop, daemon=True).start()
        return True

    def _spawn_viewer(self, prefer_mpv: bool) -> bool:
        cmd: list[str] | None = None
        self._viewer_mpv = False
        if prefer_mpv and shutil.which("mpv") and paths_env("CAMERA_VIEWER") != "tk":     # EMILIE_CAMERA_VIEWER=tk forces Tk
            self._viewer_mpv = True
            cmd = ["mpv", "--no-config", "--really-quiet", "--force-window=immediate", "--title=Emilie - video call",
                   "--ontop", "--autofit=420", "--geometry=-24-90", "--no-osc", "--osd-level=0", "--keep-open=no",
                   "--untimed", "--no-cache", "--profile=low-latency", "--demuxer=rawvideo",
                   f"--demuxer-rawvideo-w={self.w}", f"--demuxer-rawvideo-h={self.h}",
                   "--demuxer-rawvideo-mp-format=rgb24", f"--demuxer-rawvideo-fps={self.fps}", "-"]
        elif importlib.util.find_spec("tkinter") is not None:
            cmd = [sys.executable, "-m", "emilie.callwindow", str(self.w), str(self.h)]
        if cmd is None:
            return False
        try:
            self.viewer = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                           cwd=str(Path(__file__).resolve().parent.parent))
        except OSError:
            self.viewer = None
            return False
        self._viewer_t0 = time.monotonic()
        return True

    _DOT = None

    def _decorate(self, buf: bytes) -> bytes:
        """mpv shows the frame as is, so mirror it (like a call) and draw the red 'recording' dot here."""
        fr = np.frombuffer(buf, np.uint8).reshape(self.h, self.w, 3)[:, ::-1].copy()
        if Stream._DOT is None:
            yy, xx = np.mgrid[0:11, 0:11]
            Stream._DOT = (yy - 5) ** 2 + (xx - 5) ** 2 <= 25
        fr[8:19, 8:19][Stream._DOT] = (255, 85, 119)
        return fr.tobytes()

    def _feed_loop(self) -> None:
        """Pass the newest frame to the window; a slow window just skips frames. If mpv dies right at the start
        (no display for it, bad build...), fall back to the Tk window once."""
        while not self._stop and self.viewer is not None:
            v = self.viewer
            if not self._feed_ev.wait(0.5):
                if v.poll() is not None:
                    if not self._retry_tk(v):
                        break
                continue
            self._feed_ev.clear()
            buf = self._feed_buf
            try:
                v.stdin.write(self._decorate(buf) if self._viewer_mpv else buf)
                v.stdin.flush()
            except (BrokenPipeError, OSError, ValueError):
                if not self._retry_tk(v):
                    break
        if not self._stop:
            self.viewer_closed = True

    def _retry_tk(self, dead: subprocess.Popen) -> bool:
        if self._viewer_mpv and time.monotonic() - self._viewer_t0 < 3.0 and not self._stop:
            return self._spawn_viewer(prefer_mpv=False)
        return False

    def frame(self) -> tuple[np.ndarray | None, int]:
        with self._lock:
            return self.latest, self.seq

    def clip_mp4(self, seconds: float = CLIP_SECONDS) -> bytes | None:
        """The last `seconds` as a small H.264 mp4 (encoded in /dev/shm and deleted at once)."""
        with self._lock:
            frs = list(self.frames)[-int(seconds * self.fps):]
        if len(frs) < 3:
            return None
        fd, path = tempfile.mkstemp(suffix=".mp4", dir="/dev/shm" if os.path.isdir("/dev/shm") else None)
        os.close(fd)
        try:
            cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                   "-s", f"{self.w}x{self.h}", "-framerate", str(self.fps), "-i", "-", "-c:v", "libx264",
                   "-preset", "ultrafast", "-crf", "30", "-pix_fmt", "yuv420p", path]
            r = subprocess.run(cmd, input=b"".join(frs), capture_output=True, timeout=20)
            if r.returncode:
                return None
            with open(path, "rb") as f:
                return f.read()
        except (subprocess.TimeoutExpired, OSError):
            return None
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    def jpeg(self) -> bytes | None:
        """The newest frame as JPEG (for providers that cannot take video)."""
        fr, _ = self.frame()
        if fr is None:
            return None
        b = io.BytesIO()
        Image.fromarray(fr).save(b, "JPEG", quality=88)
        return b.getvalue()

    def stop(self, wait: bool = False) -> None:
        """Close the camera at once: SIGTERM, then SIGKILL after 0.6 s (the camera light must go off). Never blocks the UI
        unless wait=True (used at exit)."""
        self._stop = True
        if self in _streams:
            _streams.remove(self)
        p = self._proc
        if not p or p.poll() is not None:
            if self.viewer is not None:
                try:
                    self.viewer.stdin.close()
                except Exception:
                    pass
            return

        def reap() -> None:
            v = self.viewer
            if v is not None:
                try:
                    v.stdin.close()
                    v.wait(timeout=1)
                except Exception:
                    try:
                        v.kill()
                    except Exception:
                        pass
            try:
                p.terminate()
                p.wait(timeout=0.6)
            except Exception:
                try:
                    p.kill()
                    p.wait(timeout=2)
                except Exception:
                    pass
            for f in (p.stdout, p.stderr):
                try:
                    f and f.close()
                except Exception:
                    pass
        if wait:
            reap()
        else:
            threading.Thread(target=reap, daemon=True).start()


def viewer_available() -> bool:
    """A separate window needs a graphical session and mpv or Tk."""
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return False
    return bool(shutil.which("mpv")) or importlib.util.find_spec("tkinter") is not None


def view_mode() -> str:
    """'window' (separate window, default when possible) or 'inline' (small picture inside the terminal)."""
    v = str(effort.load_settings().get("camera_view") or paths_env("CAMERA_VIEW") or "window")
    return "window" if v == "window" and viewer_available() else "inline"


def _cleanup() -> None:
    for s in list(_streams):
        s.stop(wait=True)


atexit.register(_cleanup)
