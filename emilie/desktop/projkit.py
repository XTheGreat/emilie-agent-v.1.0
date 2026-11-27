"""What the project panels share (Git, Scripts, Problems, Tests, Notes, Database): running a command, finding the
project's own tools (its virtualenv, node_modules/.bin), the sub-projects of a folder ("desktop/" with its own
package.json), and background jobs: a long command (a test run, a type check, git push) runs in a thread, its output
is kept line by line, and the panel asks for the new lines until it is done. A job can be stopped."""
from __future__ import annotations

import collections
import itertools
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

IS_WIN = os.name == "nt"
NO_WINDOW = {"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WIN else {}
SKIP = {".git", "node_modules", "__pycache__", ".venv", "venv", "env", ".idea", ".vscode", "dist", "build", "out",
        ".next", ".nuxt", ".cache", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", "target", ".gradle",
        ".turbo", "coverage", ".parcel-cache", "site-packages", ".svelte-kit", "vendor", "bower_components"}
VENVS = (".venv", "venv", "env", ".env")
MAX_OUTPUT = 6_000_000          # characters of a job command's output kept for parsing (the start is dropped first)


# ---------------------------------------------------------------------------------------------------- commands
def run_full(args: list[str], cwd: str, timeout: float = 30, input: str | None = None,
             env: dict | None = None) -> tuple[int, str, str]:
    """Run a command: (exit code, stdout, stderr). A missing program or a timeout is an exit code, never an exception."""
    kw: dict = {"input": input} if input is not None else {"stdin": subprocess.DEVNULL}
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout, env=env, **kw, **NO_WINDOW)
        return r.returncode, r.stdout or "", r.stderr or ""
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {int(timeout)}s"
    except (OSError, subprocess.SubprocessError) as e:
        return 127, "", str(e)


def run(args: list[str], cwd: str, timeout: float = 30, input: str | None = None, env: dict | None = None) -> tuple[int, str]:
    """run_full with stdout and stderr together."""
    code, out, err = run_full(args, cwd, timeout, input, env)
    return code, out + err


def kill_tree(proc: subprocess.Popen) -> None:
    """Stop a process and everything it started."""
    if proc.poll() is not None:
        return
    if IS_WIN:
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, timeout=10, **NO_WINDOW)
        except Exception:
            proc.kill()
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            proc.kill()


# ---------------------------------------------------------------------------------------------------- the project
def norm(p: str | Path) -> str:
    return os.path.normcase(os.path.abspath(str(p)))


def inside(root: str | Path, p: str | Path) -> bool:
    """p is root or under it (after resolving '..')."""
    r, x = norm(root), norm(p)
    return x == r or x.startswith(r.rstrip("\\/") + os.sep)


def rel(root: str | Path, p: str | Path) -> str:
    """p relative to root with forward slashes, or p itself when it is elsewhere."""
    try:
        return Path(os.path.abspath(str(p))).relative_to(os.path.abspath(str(root))).as_posix()
    except ValueError:
        return str(p).replace("\\", "/")


def project_dirs(root: str, markers: tuple[str, ...], depth: int = 2, limit: int = 12) -> list[str]:
    """The folders holding one of the marker files: root itself first ("" ), then up to `depth` levels down
    ("desktop", "apps/web"), as paths relative to root. Dependency and build folders are not entered."""
    out: list[str] = []
    seen = [0]
    base = Path(root)

    def walk(p: Path, d: int, r: str) -> None:
        if len(out) >= limit or seen[0] > 600:
            return
        seen[0] += 1
        try:
            entries = list(os.scandir(p))
        except OSError:
            return
        names = {e.name for e in entries}
        if any(m in names for m in markers):
            out.append(r)
        if d >= depth:
            return
        for e in sorted(entries, key=lambda e: e.name.lower()):
            if e.name in SKIP or e.name.startswith(".") or e.name.endswith(".egg-info"):
                continue
            try:
                if e.is_dir(follow_symlinks=False):
                    walk(Path(e.path), d + 1, f"{r}/{e.name}" if r else e.name)
            except OSError:
                continue

    walk(base, 0, "")
    return out


def venv_python(*dirs: Path) -> str | None:
    """The Python of a virtualenv in one of these folders (the first found)."""
    for d in dirs:
        for v in VENVS:
            exe = d / v / ("Scripts/python.exe" if IS_WIN else "bin/python")
            if exe.is_file():
                return os.path.abspath(str(exe))
    return None


def pythons(root: str, sub: str = "") -> list[dict]:
    """The Python interpreters a project could mean: its virtualenv, the one on PATH, and Emilie's own."""
    out: list[dict] = []
    d = Path(root) / sub
    v = venv_python(d, Path(root))
    if v:
        out.append({"path": v, "label": f"{rel(root, Path(v).parent.parent)} (project virtualenv)"})
    for name in ("python", "python3") if not IS_WIN else ("python",):
        w = shutil.which(name)
        if w and "WindowsApps" not in w and not any(norm(w) == norm(x["path"]) for x in out):
            out.append({"path": w, "label": f"{w} (PATH)"})
            break
    if not any(norm(sys.executable) == norm(x["path"]) for x in out):
        out.append({"path": sys.executable, "label": f"{sys.executable} (Emilie's)"})
    return out


def node_bin(d: Path, root: Path, name: str) -> str | None:
    """A package's command from node_modules/.bin, looked for from d up to root (hoisted in a monorepo)."""
    cur = d
    while True:
        b = cur / "node_modules" / ".bin" / (name + (".cmd" if IS_WIN else ""))
        if b.is_file():
            return os.path.abspath(str(b))              # the command runs in another folder: never relative
        if norm(cur) == norm(root) or cur.parent == cur:
            return None
        cur = cur.parent


def tool(d: Path, root: Path, name: str, node: bool = False, python: bool = False) -> str | None:
    """Where the project's own copy of a tool is (node_modules/.bin, its virtualenv), else the one on PATH."""
    if node:
        b = node_bin(d, root, name)
        if b:
            return b
    if python:
        for base in (d, root):
            for v in VENVS:
                exe = base / v / ("Scripts" if IS_WIN else "bin") / (name + (".exe" if IS_WIN else ""))
                if exe.is_file():
                    return os.path.abspath(str(exe))
    return shutil.which(name)


def read_json(p: Path) -> dict:
    try:
        d = json.loads(p.read_text(encoding="utf-8-sig", errors="replace"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def read_jsonc(p: Path) -> dict:
    """JSON with comments and trailing commas (tsconfig.json, deno.jsonc)."""
    try:
        t = p.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return {}
    t = re.sub(r'("(?:\\.|[^"\\])*")|//[^\n]*|/\*.*?\*/', lambda m: m.group(1) or "", t, flags=re.S)
    t = re.sub(r",(\s*[}\]])", r"\1", t)
    try:
        d = json.loads(t)
        return d if isinstance(d, dict) else {}
    except ValueError:
        return {}


def read_toml(p: Path) -> dict:
    try:
        import tomllib
    except ImportError:                     # Python 3.10
        return {}
    try:
        return tomllib.loads(p.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return {}


def git_files(root: str) -> list[str] | None:
    """Tracked and untracked files minus the ignored ones, or None outside a git repository."""
    code, out, _ = run_full(["git", "-C", root, "ls-files", "-z", "--cached", "--others", "--exclude-standard"], root, 20)
    if code != 0:
        return None
    return sorted({f for f in out.split("\0") if f}, key=str.lower)


def project_files(root: str, exts: tuple[str, ...] | None = None, limit: int = 20000) -> list[str]:
    """The project's files (relative, forward slashes): git's list in a repository, else a walk that skips
    dependency and build folders."""
    names = git_files(root)
    if names is None:
        names = []
        for cur, dirs, files in os.walk(root):
            dirs[:] = sorted(d for d in dirs if d not in SKIP and not d.startswith("."))
            for f in sorted(files):
                names.append(rel(root, os.path.join(cur, f)))
            if len(names) > limit:
                break
    if exts:
        names = [n for n in names if n.lower().endswith(exts)]
    return [n for n in names if not any(part in SKIP for part in n.split("/")[:-1])][:limit]


# ---------------------------------------------------------------------------------------------------- jobs
class Stopped(Exception):
    """The job was stopped from the panel."""


class Job:
    _ids = itertools.count(1)

    def __init__(self, kind: str, cwd: str):
        self.id = f"job{next(self._ids)}"
        self.kind, self.cwd = kind, cwd
        self.started = time.time()
        self.ended: float | None = None
        self.lines: collections.deque[str] = collections.deque(maxlen=4000)
        self.count = 0                       # lines ever added (the deque forgets the oldest)
        self.result: dict | None = None
        self.error = ""
        self.stopped = False
        self.proc: subprocess.Popen | None = None
        self.lock = threading.Lock()

    def say(self, line: str) -> None:
        with self.lock:
            self.lines.append(line)
            self.count += 1

    def run(self, args: list[str], cwd: str | None = None, timeout: float = 1800, env: dict | None = None) -> tuple[int, str]:
        """Run one command of this job: its output is kept as it comes (the panel shows it live) and returned whole."""
        if self.stopped:
            raise Stopped()
        extra = {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP} if IS_WIN \
            else {"start_new_session": True}
        try:
            self.proc = subprocess.Popen(args, cwd=cwd or self.cwd, env=env, stdin=subprocess.DEVNULL,
                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                         encoding="utf-8", errors="replace", **extra)
        except OSError as e:
            self.say(f"could not start {args[0]}: {e}")
            return 127, str(e)
        timer = threading.Timer(timeout, self._timeout)
        timer.daemon = True
        timer.start()
        parts: list[str] = []
        size = 0
        try:
            for line in self.proc.stdout:
                self.say(line.rstrip("\r\n"))
                parts.append(line)
                size += len(line)
                if size > MAX_OUTPUT * 2:            # keep the end: that is where summaries and errors are
                    keep = "".join(parts)[-MAX_OUTPUT:]
                    parts, size = [keep], len(keep)
            code = self.proc.wait()
        finally:
            timer.cancel()
            try:
                self.proc.stdout.close()
            except Exception:
                pass
        if self.stopped:
            raise Stopped()
        return code, "".join(parts)[-MAX_OUTPUT:]

    def _timeout(self) -> None:
        self.say("(timed out: stopped)")
        if self.proc:
            kill_tree(self.proc)

    def stop(self) -> None:
        self.stopped = True
        if self.proc:
            kill_tree(self.proc)

    def info(self, since: int = 0) -> dict:
        with self.lock:
            have = len(self.lines)
            first = self.count - have                # the number of the oldest line still kept
            start = max(since, first)
            lines = list(self.lines)[start - first:] if start < self.count else []
            n = self.count
        end = self.ended or time.time()
        return {"id": self.id, "kind": self.kind, "running": self.ended is None, "secs": round(end - self.started, 2),
                "n": n, "lines": lines, "result": self.result, "error": self.error, "stopped": self.stopped}


JOBS: dict[str, Job] = {}
_jobs_lock = threading.Lock()
KEEP_DONE = 40


def start_job(kind: str, cwd: str, fn) -> dict:
    """Run fn(job) in a thread. What it returns is the job's result; what it raises, its error."""
    job = Job(kind, cwd)
    with _jobs_lock:
        JOBS[job.id] = job
        done = [j for j in JOBS.values() if j.ended is not None]
        for j in sorted(done, key=lambda j: j.ended or 0)[:-KEEP_DONE]:
            JOBS.pop(j.id, None)

    def go() -> None:
        try:
            r = fn(job)
            if r is not None:
                job.result = r
        except Stopped:
            job.error = "Stopped"
        except Exception as e:                      # the panel shows it; the hub log gets nothing (not a crash)
            job.error = f"{type(e).__name__}: {e}"
        finally:
            job.ended = time.time()
    threading.Thread(target=go, daemon=True, name=f"job-{kind}").start()
    return {"job": job.id}


def job_info(jid: str, since: int = 0) -> dict:
    j = JOBS.get(jid)
    if not j:
        return {"id": jid, "running": False, "gone": True, "lines": [], "n": since, "result": None,
                "error": "This run is no longer known (Emilie was restarted).", "secs": 0, "stopped": False}
    return j.info(since)


def job_stop(jid: str) -> dict:
    j = JOBS.get(jid)
    if j and j.ended is None:
        j.stop()
    return {"ok": True}


def stop_all_jobs() -> None:
    for j in list(JOBS.values()):
        if j.ended is None:
            try:
                j.stop()
            except Exception:
                pass
