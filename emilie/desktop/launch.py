"""`emilie app`: open the desktop app.

With Electron installed (install-desktop.ps1, or `npm install` in desktop/) Emilie opens in her own window.
Without it the same interface opens in the default browser (`emilie app --browser` forces that).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from .. import paths

ROOT = Path(__file__).resolve().parent.parent.parent


def _desktop_dirs() -> list[Path]:
    """Where the window may be: the folder install-desktop.ps1 recorded, then next to this copy of the code."""
    out = []
    try:
        rec = json.loads((paths.HOME_DIR / "desktop" / "app.json").read_text(encoding="utf-8-sig")).get("desktop")
        if rec:
            out.append(Path(rec))
    except (OSError, ValueError):
        pass
    out.append(ROOT / "desktop")
    return out


def electron_cmd() -> list[str] | None:
    for d in _desktop_dirs():
        exe = d / "node_modules" / "electron" / "dist" / ("electron.exe" if os.name == "nt" else "electron")
        if exe.is_file() and (d / "electron" / "main.cjs").is_file():
            return [str(exe), str(d)]
    return None


def launch(argv: list[str]) -> int:
    cmd = None if "--browser" in argv else electron_cmd()
    if cmd:
        env = dict(os.environ, EMILIE_PYTHON=sys.executable)
        env.pop("ELECTRON_RUN_AS_NODE", None)
        if os.name == "nt":
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            subprocess.Popen(cmd, env=env, creationflags=flags, close_fds=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(cmd, env=env, start_new_session=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("Emilie is opening in her own window.")
        return 0
    if "--browser" not in argv:
        print("The desktop window is not installed yet (run install-desktop.ps1 in Emilie's folder).")
        print("Opening Emilie in your browser instead...")
    from .__main__ import main
    return main(["--open", "browser"])
