"""/schedule: run an Emilie prompt on a timer, using the Windows Task Scheduler (no Emilie process stays resident).

Each task is three small files in ~/.emilie/scheduled/: <name>.prompt.txt (what to do), <name>.cmd (the launcher the
scheduler runs: it changes to the folder, then `emilie -p` with the prompt on stdin) and <name>.log (the output).
The task is registered under the folder "Emilie" in the scheduler, so /schedule can list and remove only its own.

SAFETY: a scheduled run has nobody to answer permission questions. By default it is READ-ONLY (anything that would ask is
denied). Only `--trust` lets it edit files and run commands, and you have to type that yourself.
Windows only for now; on Linux use cron with the same `emilie -p "..."` command.
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

from . import paths

DIR = paths.HOME_DIR / "scheduled"
KINDS = {"daily": "DAILY", "weekly": "WEEKLY", "hourly": "HOURLY", "once": "ONCE"}
NAME_RE = re.compile(r"[A-Za-z0-9_-]{1,40}")
TIME_RE = re.compile(r"([01]?\d|2[0-3]):([0-5]\d)")


def supported() -> bool:
    return os.name == "nt" and shutil.which("schtasks") is not None


def validate(name: str, kind: str, at: str, prompt: str, folder: str) -> str | None:
    """An error text, or None when everything is acceptable."""
    if not NAME_RE.fullmatch(name or ""):
        return "name: use letters, digits, - and _ (up to 40 characters)"
    if kind not in KINDS:
        return f"kind must be one of: {', '.join(KINDS)}"
    if not TIME_RE.fullmatch(at or ""):
        return "time must look like 09:30 (24-hour clock)"
    if not (prompt or "").strip():
        return "the prompt is empty"
    if not Path(folder).is_dir():
        return f"folder not found: {folder}"
    return None


def launcher_script(name: str, folder: str, emilie_cmd: str, trust: bool) -> str:
    """The .cmd the scheduler runs. The prompt travels in a file (piped in), so quotes and symbols in it are safe."""
    flags = "--trust-folder" + (" --trust" if trust else "")
    return ("@echo off\r\n"
            f'cd /d "{folder}"\r\n'
            f'echo === %date% %time% >> "{DIR / (name + ".log")}"\r\n'
            f'type "{DIR / (name + ".prompt.txt")}" | "{emilie_cmd}" -p "Do what the input says." {flags}'
            f' >> "{DIR / (name + ".log")}" 2>&1\r\n')


def create_args(name: str, kind: str, at: str, script: Path) -> list[str]:
    args = ["schtasks", "/Create", "/F", "/TN", f"Emilie\\{name}", "/SC", KINDS[kind], "/ST", at.zfill(5),
            "/TR", f'"{script}"']
    if kind == "weekly":
        args += ["/D", "MON"]
    return args


def _run(args: list[str]) -> tuple[int, str]:
    r = subprocess.run(args, capture_output=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return r.returncode, (r.stdout + r.stderr).decode("oem", errors="replace").strip()


def add(name: str, kind: str, at: str, prompt: str, folder: str, trust: bool = False) -> str:
    if not supported():
        return "ERROR: scheduled tasks need Windows (use cron on Linux: emilie -p \"...\" --trust-folder)"
    err = validate(name, kind, at, prompt, folder)
    if err:
        return f"ERROR: {err}"
    emilie_cmd = shutil.which("emilie") or str(Path(os.environ.get("LOCALAPPDATA", "")) / "Emilie" / "bin" / "emilie.cmd")
    DIR.mkdir(parents=True, exist_ok=True)
    (DIR / f"{name}.prompt.txt").write_text(prompt.strip() + "\n", encoding="utf-8")
    script = DIR / f"{name}.cmd"
    script.write_text(launcher_script(name, str(Path(folder).resolve()), emilie_cmd, trust), encoding="ascii", errors="replace")
    code, out = _run(create_args(name, kind, at, script))
    if code != 0:
        return f"ERROR: the scheduler refused: {out[:200]}"
    return (f"scheduled '{name}' {kind} at {at} in {Path(folder).resolve()} "
            + ("(may edit files and run commands: --trust)" if trust else "(read-only: it cannot change anything)")
            + f". Output goes to {DIR / (name + '.log')}")


def remove(name: str) -> str:
    if not supported():
        return "ERROR: scheduled tasks need Windows"
    if not NAME_RE.fullmatch(name or ""):
        return "ERROR: bad name"
    code, out = _run(["schtasks", "/Delete", "/F", "/TN", f"Emilie\\{name}"])
    for ext in (".cmd", ".prompt.txt"):
        (DIR / f"{name}{ext}").unlink(missing_ok=True)
    return f"removed '{name}'" if code == 0 else f"ERROR: {out[:200]}"


def run_now(name: str) -> str:
    if not supported():
        return "ERROR: scheduled tasks need Windows"
    if not NAME_RE.fullmatch(name or ""):
        return "ERROR: bad name"
    code, out = _run(["schtasks", "/Run", "/TN", f"Emilie\\{name}"])
    return f"started '{name}'; the output is appended to {DIR / (name + '.log')}" if code == 0 else f"ERROR: {out[:200]}"


def listing() -> list[str]:
    """One line per task of ours: name · next run · status."""
    if not supported():
        return ["scheduled tasks need Windows"]
    _code, out = _run(["schtasks", "/Query", "/FO", "CSV", "/NH"])
    rows = []
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 3 and parts[0].lstrip("\\").lower().startswith("emilie\\"):
            rows.append(f"{parts[0].lstrip(chr(92)).split(chr(92), 1)[1]}  ·  next: {parts[1]}  ·  {parts[2]}")
    return rows or ["no scheduled tasks (add one: /schedule add <name> daily 09:00 \"prompt\" [--trust])"]
