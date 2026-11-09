"""Images: from the clipboard or from a path (drag & drop), then encoded to be sent to the model."""
import base64
import io
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from urllib.parse import unquote

from PIL import Image

EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
MAX_SIDE = 1568


def copy_text(text: str) -> bool:
    """Put text on the system clipboard (wl-copy / xclip / xsel / pbcopy). False if no tool worked."""
    if os.name == "nt":
        try:
            subprocess.run(["clip"], input=text.encode("utf-16-le"), timeout=3, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
            return True
        except Exception:
            return False
    data = text.encode()
    for cmd in (["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"], ["pbcopy"]):
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, input=data, timeout=3, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except Exception:
                continue
    return False


def _run(cmd: list[str]) -> bytes | None:
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=5)
        return r.stdout if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def grab_clipboard_image() -> bytes | None:
    if os.name == "nt":
        try:
            from PIL import ImageGrab
            img = ImageGrab.grabclipboard()
            if isinstance(img, Image.Image):
                buf = io.BytesIO()
                img.save(buf, "PNG")
                return buf.getvalue()
        except Exception:
            pass
        return None
    if shutil.which("wl-paste"):
        types = _run(["wl-paste", "--list-types"]) or b""
        if b"image/png" in types:
            return _run(["wl-paste", "--type", "image/png"])
    if shutil.which("xclip"):
        types = _run(["xclip", "-selection", "clipboard", "-t", "TARGETS", "-o"]) or b""
        if b"image/png" in types:
            return _run(["xclip", "-selection", "clipboard", "-t", "image/png", "-o"])
    return None


def parse_image_paths(text: str) -> list[Path]:
    """Every token of a paste must be an existing image path; otherwise -> []."""
    try:
        toks = shlex.split(text, posix=(os.name != "nt"))
    except ValueError:
        return []
    out = []
    for t in toks:
        t = t.strip('"\'')
        if t.startswith("file://"):
            t = unquote(t[7:])
        p = Path(t).expanduser()
        if p.suffix.lower() in EXTS and p.is_file():
            out.append(p)
        else:
            return []
    return out


def encode_image(data: bytes) -> tuple[str, str]:
    """Shrink if needed, returns (mime, base64)."""
    img = Image.open(io.BytesIO(data))
    img.load()
    if max(img.size) > MAX_SIDE:
        img.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    if img.mode in ("RGBA", "LA", "P"):
        img.convert("RGBA").save(buf, "PNG")
        mime = "image/png"
    else:
        img.convert("RGB").save(buf, "JPEG", quality=88)
        mime = "image/jpeg"
    return mime, base64.b64encode(buf.getvalue()).decode()
