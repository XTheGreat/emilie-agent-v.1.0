"""python -m emilie.desktop [--port N] [--token T] [--open browser|none] [--watch-stdin]

Starts the desktop app's local server. The Electron window (desktop/main.js) runs this itself and reads the first
line of stdout, a JSON object with the port and the URL. `--open browser` opens the UI in the default browser
instead (no Electron needed).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import webbrowser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if os.name == "nt" and not sys.flags.utf8_mode:       # same as the CLI: files and pipes in UTF-8 on Windows
        return subprocess.call([sys.executable, "-X", "utf8", "-m", "emilie.desktop", *argv])
    ap = argparse.ArgumentParser(prog="python -m emilie.desktop", description="Emilie desktop app server")
    ap.add_argument("--port", type=int, default=0, help="0 = any free port")
    ap.add_argument("--token", default=None, help="access token (random when omitted)")
    ap.add_argument("--open", choices=("browser", "none"), default="none")
    ap.add_argument("--watch-stdin", action="store_true", help="exit when stdin closes (the window is gone)")
    a = ap.parse_args(argv)
    if a.watch_stdin:                                # launched by the window: keep its pipes away from child processes
        from .stdio import private_stdio
        inp, out = private_stdio(True)
    else:
        inp, out = None, sys.stdout
    from .hub import serve

    def ready(hub, url):
        out.write(json.dumps({"ready": True, "port": hub.port, "url": url}) + "\n")
        out.flush()
        if a.open == "browser":
            sys.stderr.write(f"Emilie is running at {url}\n(keep this window open; Ctrl+C stops it)\n")
            webbrowser.open(url)
        if inp is not None:
            def watch():
                try:
                    inp.read()
                except Exception:
                    pass
                hub.shutdown()
                os._exit(0)
            threading.Thread(target=watch, daemon=True).start()
    serve(a.port, a.token, ready)
    return 0


if __name__ == "__main__":
    sys.exit(main())
