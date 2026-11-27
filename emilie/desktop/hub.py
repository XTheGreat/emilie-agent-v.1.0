"""The desktop app's local server: python -X utf8 -m emilie.desktop

    GET  /                      the UI (web/, built from desktop/ui with `npm run build`)
    GET  /api/events            one server-sent-event stream with everything that happens, in every session
    *    /api/...               JSON API (see ROUTES at the bottom)
    GET  /media/...             the Emilie icon (video / image) and local files for previews

Listens on 127.0.0.1 only; every /api and /media request needs the random token the launcher passes in the URL,
and the Host header must be the loopback address (no DNS rebinding). Each open session runs in its own worker
process (worker.py); one spare worker is kept warm so a new session starts at once.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import itertools
import json
import mimetypes
import os
import queue
import re
import shutil
import string
import subprocess
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from .. import __version__, effort as eff, paths, persona, providers, session, trust
from ..i18n import t as tr_
from . import desktop_commands, schema, search
from . import checks, gitops, netkit, notes, projkit, sqlview, testrun
from . import scripts as pscripts

PKG = Path(__file__).resolve().parent
WEB = PKG / "web"
ROOT = PKG.parent.parent                     # the folder that holds the emilie package (repository or installed copy)
DATA = paths.HOME_DIR / "desktop"
META_DIR = DATA / "sessions"
LOG = DATA / "desktop.log"
IS_WIN = os.name == "nt"
NO_WINDOW = {"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WIN else {}
MAX_WORKERS = 16
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache", ".pytest_cache", ".next", "dist",
             "build", ".idea", ".vscode", "target", ".gradle"}
MIME = {".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css", ".html": "text/html",
        ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp", ".ico": "image/x-icon",
        ".woff2": "font/woff2", ".woff": "font/woff", ".ttf": "font/ttf", ".mp4": "video/mp4", ".webm": "video/webm",
        ".mov": "video/quicktime", ".m4v": "video/mp4", ".mkv": "video/x-matroska", ".avi": "video/x-msvideo",
        ".pdf": "application/pdf", ".txt": "text/plain", ".md": "text/plain", ".map": "application/json"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".ico"}


def scratch_dir() -> Path:
    """Where 'no folder' (chat) sessions work: ~/Documents/Emilie."""
    docs = Path.home() / "Documents"
    return (docs if docs.is_dir() else Path.home()) / "Emilie"


def _run(args: list[str], cwd: str | None = None, timeout: float = 20) -> tuple[int, str]:
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout, stdin=subprocess.DEVNULL, **NO_WINDOW)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)


def _kill_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if IS_WIN:
        _run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], timeout=10)
    else:
        proc.kill()


class ApiError(Exception):
    def __init__(self, msg: str, status: int = 400):
        super().__init__(msg)
        self.status = status


# ====================================================================== workers
class WorkerProc:
    """One worker process and what the hub knows about it."""

    _wids = itertools.count(1)

    def __init__(self, hub: "Hub"):
        self.hub = hub
        self.wid = f"w{next(self._wids)}"
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1", EMILIE_DESKTOP="1")
        env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        self.proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "emilie.desktop.worker"], cwd=str(ROOT),
                                     env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     text=True, encoding="utf-8", errors="replace", bufsize=1, **NO_WINDOW)
        self.wlock = threading.Lock()
        self.warm_ev, self.ready_ev = threading.Event(), threading.Event()
        self.ready: dict = {}
        self.session_id: str | None = None
        self.cwd: str | None = None
        self.status: dict = {}
        self.title = ""
        self.request: dict | None = None
        self.stale = False                     # the provider changed after this worker started
        self.closing = False
        self.used = time.time()
        self._rid = itertools.count(1)
        self.pending: dict[int, list] = {}
        threading.Thread(target=self._read_out, daemon=True).start()
        threading.Thread(target=self._read_err, daemon=True).start()

    def alive(self) -> bool:
        return self.proc.poll() is None

    def send(self, obj: dict) -> None:
        line = json.dumps(obj, ensure_ascii=True)
        with self.wlock:
            try:
                self.proc.stdin.write(line + "\n")
                self.proc.stdin.flush()
            except (OSError, ValueError) as e:
                raise ApiError(f"the session process is gone ({e})", 410)

    def call(self, cmd: str, timeout: float = 30, **kw):
        rid = next(self._rid)
        slot = [threading.Event(), None, None]
        self.pending[rid] = slot
        try:
            self.send({"cmd": cmd, "rid": rid, **kw})
            if not slot[0].wait(timeout):
                raise ApiError(f"the session did not answer '{cmd}' in time", 504)
        finally:
            self.pending.pop(rid, None)
        if slot[2]:
            raise ApiError(str(slot[2]), 500)
        return slot[1]

    def _read_out(self) -> None:
        for line in self.proc.stdout:
            try:
                ev = json.loads(line)
            except ValueError:
                self.hub.log(f"[{self.wid}] bad line: {line[:200]}")
                continue
            try:
                self.hub.on_event(self, ev)
            except Exception:
                self.hub.log(f"[{self.wid}] event failed: {traceback.format_exc()}")
        for slot in list(self.pending.values()):            # the process ended: release everyone waiting
            slot[2] = "the session process ended"
            slot[0].set()
        self.hub.on_exit(self)

    def _read_err(self) -> None:
        for line in self.proc.stderr:
            self.hub.log(f"[{self.wid}] {line.rstrip()}")

    def describe(self) -> dict:
        return {"wid": self.wid, "session_id": self.session_id, "cwd": self.cwd, "status": self.status,
                "title": self.title, "stale": self.stale, "request": self.request}

    def shutdown(self) -> None:
        self.closing = True
        try:
            self.send({"cmd": "shutdown"})
            self.proc.wait(4)
        except Exception:
            pass
        _kill_tree(self.proc)


class Term:
    """A command run from the Terminal pane (output streamed as events)."""

    def __init__(self, hub: "Hub", tid: str, cwd: str, command: str, name: str = ""):
        from .. import tools
        self.tid, self.command, self.cwd, self.name = tid, command, cwd, name
        self.started = time.time()
        self.tail: list[str] = []                     # the last lines, for a window that was reloaded (/api/term/list)
        cmd = tools._shell_cmd(command) if IS_WIN else ["bash", "-lc", command]
        extra = {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP} if IS_WIN \
            else {"start_new_session": True}
        self.proc = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", **extra)

        def pump():
            for line in self.proc.stdout:
                line = line.rstrip("\r\n")
                self.tail.append(line)
                if len(self.tail) > 1200:
                    del self.tail[:200]
                hub.broadcast({"t": "term", "tid": tid, "line": line})
            hub.broadcast({"t": "term_end", "tid": tid, "code": self.proc.wait()})
            hub.terms.pop(tid, None)
        threading.Thread(target=pump, daemon=True).start()

    def describe(self) -> dict:
        return {"tid": self.tid, "cwd": self.cwd, "command": self.command, "name": self.name,
                "started": self.started, "lines": self.tail[-800:]}

    def kill(self) -> None:
        from .. import tools
        tools._kill_group(self.proc)


# ====================================================================== hub
class Hub:
    def __init__(self, token: str):
        self.token = token
        self.port = 0
        self.lock = threading.RLock()
        self.workers: dict[str, WorkerProc] = {}
        self.warm: WorkerProc | None = None
        self.clients: list[queue.Queue] = []
        self.idx_cache: dict[str, tuple] = {}
        self.meta_cache: dict[str, tuple] = {}
        self.models_cache: dict[tuple, tuple] = {}
        self.files_cache: dict[str, tuple] = {}
        self.art_cache: dict[str, tuple] = {}
        self.terms: dict[str, Term] = {}
        self._tids = itertools.count(1)
        DATA.mkdir(parents=True, exist_ok=True)
        try:
            if LOG.exists() and LOG.stat().st_size > 2_000_000:
                LOG.replace(LOG.with_suffix(".old.log"))
        except OSError:
            pass
        self.log_fh = open(LOG, "a", encoding="utf-8", errors="replace")
        self.log(f"--- hub start {time.strftime('%Y-%m-%d %H:%M:%S')} python {sys.version.split()[0]} root {ROOT}")
        self.spawn_warm()

    # ------------------------------------------------------------ logging / events
    def log(self, msg: str) -> None:
        try:
            self.log_fh.write(msg + "\n")
            self.log_fh.flush()
        except Exception:
            pass

    def broadcast(self, ev: dict) -> None:
        data = json.dumps(ev, ensure_ascii=False, default=str)
        with self.lock:
            for q in list(self.clients):
                if q.qsize() > 20000:                         # a client that stopped reading
                    self.clients.remove(q)
                    continue
                q.put(data)

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        with self.lock:
            self.clients.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self.lock:
            if q in self.clients:
                self.clients.remove(q)

    def on_event(self, w: WorkerProc, ev: dict) -> None:
        t = ev.get("t")
        if t == "reply":
            slot = w.pending.get(ev.get("rid"))
            if slot:
                slot[1], slot[2] = ev.get("data"), ev.get("error")
                slot[0].set()
            return
        if t == "warm":
            w.warm_ev.set()
            return
        if t == "ready":
            w.session_id, w.cwd = ev.get("session_id"), ev.get("cwd")
            w.status = ev.get("status") or {}
            w.ready = ev
            w.ready_ev.set()
        elif t == "status":
            w.status = ev.get("status") or {}
            if w.status.get("session_id"):
                w.session_id = w.status["session_id"]
        elif t == "session_changed":
            w.session_id = ev.get("new")
            for other in list(self.workers.values()):        # /resume opened a session another window has open
                if other is not w and other.session_id == w.session_id and not other.status.get("busy"):
                    threading.Thread(target=self.close_worker, args=(other,), daemon=True).start()
        elif t == "title":
            w.title = ev.get("title") or ""
        elif t == "request":
            w.request = {"id": ev.get("id"), **(ev.get("request") or {})}
        elif t == "request_done":
            w.request = None
        elif t == "prefs":
            pass
        w.used = time.time()
        ev["wid"], ev["sid"] = w.wid, w.session_id
        self.broadcast(ev)

    def on_exit(self, w: WorkerProc) -> None:
        with self.lock:
            self.workers.pop(w.wid, None)
            if self.warm is w:
                self.warm = None
        if not w.closing and w.ready_ev.is_set():
            self.log(f"[{w.wid}] exited with code {w.proc.poll()}")
            self.broadcast({"t": "worker_exit", "wid": w.wid, "sid": w.session_id, "code": w.proc.poll()})

    # ------------------------------------------------------------ worker pool
    def spawn_warm(self) -> None:
        def go():
            try:
                with self.lock:
                    if self.warm is not None and self.warm.alive():
                        return
                    if len(self.workers) >= MAX_WORKERS:
                        return
                    self.warm = WorkerProc(self)
            except Exception as e:
                self.log(f"warm worker failed: {e}")
        threading.Thread(target=go, daemon=True).start()

    def take_worker(self) -> WorkerProc:
        with self.lock:
            w, self.warm = self.warm, None
        if w is None or not w.alive():
            w = WorkerProc(self)
        if not w.warm_ev.wait(90):
            _kill_tree(w.proc)
            raise ApiError("a new session process did not start (see ~/.emilie/desktop/desktop.log)", 500)
        with self.lock:
            self.workers[w.wid] = w
        self.trim_workers()
        self.spawn_warm()
        return w

    def trim_workers(self) -> None:
        """Close the least recently used idle sessions when too many are open (their state is saved on disk)."""
        with self.lock:
            idle = sorted((w for w in self.workers.values() if not w.status.get("busy") and not w.request),
                          key=lambda w: w.used)
            extra = len(self.workers) - (MAX_WORKERS - 2)
        for w in idle[:max(0, extra)]:
            threading.Thread(target=self.close_worker, args=(w,), daemon=True).start()

    def worker(self, wid: str) -> WorkerProc:
        w = self.workers.get(str(wid))
        if w is None or not w.alive():
            raise ApiError("this session is not open any more: open it again from the sidebar", 410)
        return w

    def close_worker(self, w: WorkerProc) -> None:
        with self.lock:
            self.workers.pop(w.wid, None)
        w.shutdown()
        self.broadcast({"t": "closed", "wid": w.wid, "sid": w.session_id})

    def open_session(self, b: dict) -> dict:
        sid = b.get("id") or None
        cwd = b.get("cwd") or None
        if b.get("chat") or not cwd:
            cwd = str(scratch_dir())
        cwd = os.path.abspath(os.path.expanduser(str(cwd)))
        if sid:
            for w in list(self.workers.values()):
                if w.session_id == sid and w.alive():
                    w.used = time.time()
                    return self._opened(w, w.call("snapshot"), w.call("commands"))
            if not os.path.isdir(cwd):
                raise ApiError(f"the folder of this session does not exist any more: {cwd}", 404)
        elif not os.path.isdir(cwd):
            if cwd == str(scratch_dir()):
                os.makedirs(cwd, exist_ok=True)
            else:
                raise ApiError(f"folder not found: {cwd}", 404)
        made = None
        if b.get("worktree") and not sid:
            cwd, made = self.make_worktree(cwd)
        if not sid:
            self.remember_folder(cwd)
        w = self.take_worker()
        mode = b.get("mode") or eff.load_settings().get("desktop_mode") or "ask"
        try:
            w.call("init", timeout=120, cwd=cwd, resume=sid, mode=mode, model=b.get("model") or None,
                   effort=b.get("effort") or None)
        except ApiError:
            self.close_worker(w)
            raise
        if not w.ready_ev.wait(10):
            self.close_worker(w)
            raise ApiError("the session did not get ready", 500)
        r = w.ready
        out = self._opened(w, r.get("snapshot"), r.get("commands"))
        if made:
            out["worktree"] = made                       # the page tells what was (not) carried over
        return out

    def _opened(self, w: WorkerProc, snapshot, commands) -> dict:
        return {**w.describe(), "snapshot": snapshot, "commands": commands}

    def make_worktree(self, cwd: str) -> tuple[str, dict]:
        """A new worktree on its own branch. Returns (the folder the session should open in: the same sub-folder of the
        worktree as the one picked, {branch, dirty: the checkout had uncommitted changes that are NOT in it})."""
        code, top = _run(["git", "-C", cwd, "rev-parse", "--show-toplevel"])
        if code != 0:
            raise ApiError("Worktree needs a git repository: this folder is not one", 400)
        top = os.path.normpath(top.strip())
        _c, st = _run(["git", "-C", top, "status", "--porcelain"])
        base = Path(top).parent / (Path(top).name + "-worktrees")
        stamp = "emilie-" + time.strftime("%m%d-%H%M%S")
        name, n = stamp, 1
        while (base / name).exists() or _run(["git", "-C", top, "rev-parse", "--verify", "--quiet", f"refs/heads/emilie/{name}"])[0] == 0:
            n += 1
            name = f"{stamp}-{n}"                         # two sessions in the same second
        dest = base / name
        code, out = _run(["git", "-C", top, "worktree", "add", "-b", f"emilie/{name}", str(dest)], timeout=120)
        if code != 0:
            raise ApiError(f"git worktree add failed: {out.strip()[:300]}", 500)
        rel = os.path.relpath(os.path.normpath(cwd), top)
        inside = dest if rel in (".", "") or rel.startswith("..") else dest / rel
        return str(inside if inside.is_dir() else dest), {"branch": f"emilie/{name}", "dirty": bool(st.strip())}

    def worktree_info(self, q: dict) -> dict:
        """Is this folder a linked git worktree (not the main checkout)? With its branch, main checkout and state."""
        cwd = q.get("cwd") or ""
        code, out = _run(["git", "-C", cwd, "rev-parse", "--path-format=absolute", "--git-dir", "--git-common-dir", "--show-toplevel"])
        lines = out.strip().splitlines()
        if code != 0 or len(lines) < 3:
            return {"is": False}
        gd, cd, top = (os.path.normcase(os.path.normpath(x)) for x in lines[:3])
        if gd == cd:
            return {"is": False}
        _c, br = _run(["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"])
        _c, st = _run(["git", "-C", top, "status", "--porcelain"])
        main = os.path.dirname(os.path.normpath(lines[1])) if os.path.basename(os.path.normpath(lines[1])) == ".git" else ""
        return {"is": True, "top": os.path.normpath(lines[2]), "main": main, "branch": br.strip(), "dirty": bool(st.strip())}

    def worktree_remove(self, b: dict) -> dict:
        """Delete a linked worktree (and its emilie/ branch when nothing in it is unmerged). Sessions in it are closed first."""
        info = self.worktree_info({"cwd": b.get("cwd") or ""})
        if not info.get("is") or not info.get("main"):
            raise ApiError("This folder is not a git worktree", 400)
        if info["dirty"] and not b.get("force"):
            return {"ok": False, "dirty": True}
        top = info["top"]
        norm = lambda p: os.path.normcase(os.path.normpath(p))
        with self.lock:
            inside = [w for w in self.workers.values() if norm(w.cwd or "").startswith(norm(top))]
        for w in inside:
            self.close_worker(w)
        code, out = _run(["git", "-C", info["main"], "worktree", "remove", "--force", top], timeout=60)
        if code != 0:
            raise ApiError(f"git worktree remove failed: {out.strip()[:300]}", 500)
        kept = True
        if info["branch"].startswith("emilie/"):
            kept = _run(["git", "-C", info["main"], "branch", "-d", info["branch"]])[0] != 0   # -d: refuses an unmerged branch
        return {"ok": True, "branch": info["branch"], "branch_kept": kept}

    def remember_folder(self, cwd: str) -> None:
        if os.path.normcase(cwd) == os.path.normcase(str(scratch_dir())):
            return
        rec = [p for p in eff.load_settings().get("desktop_recent") or [] if isinstance(p, str)]
        rec = [cwd] + [p for p in rec if os.path.normcase(p) != os.path.normcase(cwd)]
        eff.save_settings(desktop_recent=rec[:20])

    def provider_changed(self) -> None:
        with self.lock:
            warm, self.warm = self.warm, None
            for w in self.workers.values():
                w.stale = True
        if warm is not None:
            threading.Thread(target=warm.shutdown, daemon=True).start()
        self.models_cache.clear()
        self.spawn_warm()
        self.broadcast({"t": "provider_changed"})

    def shutdown(self) -> None:
        for w in list(self.workers.values()) + ([self.warm] if self.warm else []):
            try:
                w.shutdown()
            except Exception:
                pass
        for t in list(self.terms.values()):
            try:
                t.kill()
            except Exception:
                pass
        projkit.stop_all_jobs()

    def own_pids(self) -> dict[int, str]:
        """Emilie's own processes (the Ports panel must not offer to stop them)."""
        own = {os.getpid(): "Emilie's background process", os.getppid(): "the Emilie window"}
        for w in list(self.workers.values()) + ([self.warm] if self.warm else []):
            try:
                own[w.proc.pid] = "an Emilie session"
            except Exception:
                pass
        return own

    # ------------------------------------------------------------ sessions on disk
    def _meta(self, sid: str) -> dict:
        p = META_DIR / f"{sid}.json"
        try:
            st = p.stat()
        except OSError:
            return {}
        c = self.meta_cache.get(sid)
        if c and c[0] == st.st_mtime_ns:
            return c[1]
        try:
            d = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            d = {}
        m = {"title": d.get("title") or ""}
        self.meta_cache[sid] = (st.st_mtime_ns, m)
        return m

    def sessions(self) -> list[dict]:
        out: dict[str, dict] = {}
        for f in session.ROOT.glob("*/*.json"):
            if f.parent.name.startswith("."):              # .trash: deleted sessions must not come back in the list
                continue
            try:
                st = f.stat()
            except OSError:
                continue
            key = str(f)
            c = self.idx_cache.get(key)
            if not c or c[0] != (st.st_mtime_ns, st.st_size):
                try:
                    d = json.loads(f.read_text(encoding="utf-8", errors="replace"))
                except (OSError, ValueError):
                    continue
                meta = {"id": d.get("id") or f.stem, "cwd": d.get("cwd") or "", "title": d.get("title") or "",
                        "updated": d.get("updated") or st.st_mtime, "created": d.get("created") or 0,
                        "n": len(d.get("messages") or []), "model": d.get("model") or ""}
                c = ((st.st_mtime_ns, st.st_size), meta)
                self.idx_cache[key] = c
            meta = dict(c[1])
            meta["title"] = self._meta(meta["id"]).get("title") or self._clean_title(meta["title"])
            out[meta["id"]] = meta
        scratch = os.path.normcase(str(scratch_dir()))
        for w in list(self.workers.values()):
            if not w.session_id:
                continue
            m = out.setdefault(w.session_id, {"id": w.session_id, "cwd": w.cwd or "", "title": "", "n": 0,
                                              "updated": w.used, "created": w.used, "model": ""})
            m.update(live=True, wid=w.wid, busy=bool(w.status.get("busy")), waiting=bool(w.request))
            if w.title:
                m["title"] = w.title
        for m in out.values():
            m["chat"] = os.path.normcase(m.get("cwd") or "") == scratch
        return sorted(out.values(), key=lambda m: m.get("updated") or 0, reverse=True)

    @staticmethod
    def _clean_title(t: str) -> str:
        """Titles the terminal saved from its own notes ('[System note: ...] hi') -> what the user typed."""
        t = (t or "").strip()
        if t.startswith("[Automatic camera glance"):
            return "Video call"
        if t.startswith(("[Summary of the earlier", "[Ringkasan")):
            return "Continued conversation"
        if (t.startswith("[System note:") and "]" not in t) or (t.startswith("(While the user was silent") and ")" not in t):
            return "Continued conversation"
        t = re.sub(r"^\[System note:[^\]]*\]\s*", "", t)
        t = re.sub(r"^\(While the user was silent[^)]*\)\s*", "", t)
        t = re.sub(r'^<skill name="([^"]+)".*', r"/\1", t)
        t = re.sub(r"\s*\(The attached video is a short clip.*$", "", t)
        t = re.sub(r"\s*\[Image #\d+(:[^\]]*)?\]?", "", t)
        return t.strip() or "Untitled"

    def session_file(self, cwd: str, sid: str) -> Path:
        if not re.fullmatch(r"[\w.-]+", sid or ""):
            raise ApiError("session not found", 404)
        p = session.ROOT / hashlib.sha1(str(Path(cwd).resolve()).encode()).hexdigest()[:10] / f"{sid}.json"
        if p.is_file():
            return p
        # the folder was deleted, moved or now resolves to another path: find the session by its id instead
        for q in session.ROOT.glob(f"*/{sid}.json"):
            if not q.parent.name.startswith("."):
                return q
        raise ApiError("session not found", 404)

    def delete_session(self, b: dict) -> dict:
        sid, cwd = str(b.get("id") or ""), str(b.get("cwd") or "")
        for w in list(self.workers.values()):
            if w.session_id == sid:
                self.close_worker(w)
        try:
            p = self.session_file(cwd, sid)
        except ApiError:                                   # nothing on disk (already deleted): it is gone, as asked
            self.broadcast({"t": "sessions_changed"})
            return {"ok": True, "moved_to": None}
        trash = session.ROOT / ".trash"
        trash.mkdir(parents=True, exist_ok=True)
        p.replace(trash / p.name)                          # recoverable: moved, not deleted
        self.broadcast({"t": "sessions_changed"})
        return {"ok": True, "moved_to": str(trash / p.name)}

    def delete_all_sessions(self, b: dict) -> dict:
        """Permanently delete EVERY saved conversation (and the trash of deleted ones, and their titles). Settings,
        keys, memory and skills are not touched. Needs {"confirm": "DELETE"} so a stray call cannot wipe the history."""
        if b.get("confirm") != "DELETE":
            raise ApiError("confirmation missing", 400)
        for w in list(self.workers.values()):
            self.close_worker(w)
        n = 0
        for f in list(session.ROOT.glob("*/*.json")) + list(META_DIR.glob("*.json")):
            try:
                f.unlink()
                n += 1
            except OSError:
                pass
        for d in session.ROOT.glob("*"):                   # folders left empty
            try:
                if d.is_dir():
                    d.rmdir()
            except OSError:
                pass
        self.broadcast({"t": "sessions_changed"})
        return {"ok": True, "deleted": n}

    def plugins_call(self, what: str, b: dict) -> dict:
        from .. import plugins
        try:
            extra: dict = {}
            if what == "install":
                extra = plugins.install(str(b.get("source") or ""))
            elif what == "toggle":
                plugins.set_enabled(str(b.get("id") or ""), bool(b.get("enabled")))
            elif what == "remove":
                plugins.remove(str(b.get("id") or ""))
        except plugins.PluginError as e:
            raise ApiError(str(e), 400)
        return {"ok": True, "items": plugins.listing(), **extra}

    def rename_session(self, b: dict) -> dict:
        sid, title = str(b.get("id") or ""), str(b.get("title") or "").strip()[:80]
        for w in list(self.workers.values()):
            if w.session_id == sid and w.alive():
                w.send({"cmd": "set", "title": title})
                return {"ok": True}
        if not re.fullmatch(r"[\w.-]+", sid):
            raise ApiError("bad session id")
        META_DIR.mkdir(parents=True, exist_ok=True)
        p = META_DIR / f"{sid}.json"
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            d = {}
        d["title"] = title
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        self.broadcast({"t": "sessions_changed"})
        return {"ok": True}

    def folders(self) -> list[dict]:
        seen, out = set(), []
        rec = [p for p in eff.load_settings().get("desktop_recent") or [] if isinstance(p, str)]
        for p in rec + [s["cwd"] for s in self.sessions() if s.get("cwd") and not s.get("chat")]:
            k = os.path.normcase(p)
            if k in seen:
                continue
            seen.add(k)
            out.append({"path": p, "name": Path(p).name or p, "exists": os.path.isdir(p)})
        return out[:30]

    # ------------------------------------------------------------ provider, models
    @staticmethod
    def _client(r: dict, timeout: float = 30):
        if r["kind"] == "openai":
            from openai import OpenAI
            return OpenAI(api_key=r["key"], base_url=r["base"], timeout=timeout, max_retries=0)
        import anthropic
        kw = {"base_url": r["base"]} if r.get("base") else {}
        return anthropic.Anthropic(api_key=r["key"], timeout=timeout, max_retries=0, **kw)

    def providers_info(self) -> dict:
        r = providers.resolve()
        keys = providers.load_keys()
        presets = []
        for pid, p in providers.PRESETS.items():
            saved = keys.get(pid, {})
            presets.append({"id": pid, "label": tr_(p["label"]), "kind": p["kind"], "base": p.get("base"),
                            "model": p.get("model"), "hint": tr_(p.get("hint") or ""), "nokey": bool(p.get("nokey")),
                            "has_key": bool(saved.get("key") or (p.get("env") and os.environ.get(p["env"]))
                                            or p.get("nokey")),
                            "saved_model": saved.get("model"), "saved_base": saved.get("base")})
        return {"current": r["id"], "kind": r["kind"], "base": r["base"], "has_key": bool(r["key"]),
                "model": eff.load_settings().get("model") or r["model"], "default_model": r["model"],
                "presets": presets}

    def set_provider(self, b: dict) -> dict:
        pid = str(b.get("id") or "")
        p = providers.PRESETS.get(pid)
        if p is None:
            raise ApiError(f"unknown provider '{pid}'")
        key = str(b.get("key") or "").strip() or None
        base = str(b.get("base") or "").strip() or None
        model = str(b.get("model") or "").strip() or None
        if pid == "custom" and not (base or providers.load_keys().get(pid, {}).get("base")):
            raise ApiError("a custom provider needs its base URL")
        if not key and not p.get("nokey") and not providers.load_keys().get(pid, {}).get("key") and \
                not (p.get("env") and os.environ.get(p["env"])):
            if pid == "custom":
                key = "none"
            else:
                raise ApiError("paste the API key for this provider")
        providers.save_provider(pid, key, base, model)
        self.provider_changed()
        return self.providers_info()

    ANTHROPIC_MODELS = ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-fable-5-2"]

    def models_list(self, refresh: bool = False) -> dict:
        from .. import models as mdl
        r = providers.resolve()
        current = eff.load_settings().get("model") or r["model"]
        if not r["key"]:
            return {"models": [], "current": current, "error": "no API key yet"}
        ck = (r["id"], r["base"], r["kind"])
        c = self.models_cache.get(ck)
        if c and not refresh and time.time() - c[0] < 900:
            rows, err = c[1], c[2]
        else:
            rows, err = [], None
            try:
                client = self._client(r, 20)
                if r["kind"] == "openai":
                    live = mdl.fetch_live(client)
                    bankai = "bankai" in (r["base"] or "")
                    names = list(live) + ([n for n in mdl.BANKAI if n not in live] if bankai else [])
                    for n in names:
                        lv = live.get(n, {})
                        g, mult = mdl.BANKAI.get(n, (None, None)) if bankai else (None, None)
                        row = {"id": n, "vision": bool(lv.get("vision") or n in mdl.BANKAI_VISION or "vision" in n
                                                         or "-vl" in n.lower()),
                               "grade": lv.get("grade") or g, "mult": mult, "pp": lv.get("pp")}
                        row["price"] = mdl.price_label(row) if (mult is not None or row["pp"]) else ""
                        rows.append(row)
                    if not live:
                        err = "the provider did not return a model list"
                else:
                    try:
                        ids = [m.id for m in client.models.list(limit=100)]
                    except Exception:
                        ids = []
                    for n in ids or self.ANTHROPIC_MODELS:
                        rows.append({"id": n, "vision": True, "price": "", "grade": None})
            except Exception as e:
                err = f"{type(e).__name__}: {e}"[:300]
            self.models_cache[ck] = (time.time(), rows, err)
        ids = {x["id"] for x in rows}
        if current and current not in ids:
            rows = [{"id": current, "vision": False, "price": "", "grade": None}] + rows
        return {"models": rows, "current": current, "default": r["model"], "provider": r["id"], "error": err,
                "fallback": eff.load_settings().get("fallback_model")}

    def provider_test(self, b: dict) -> dict:
        from .. import doctor
        r = providers.resolve()
        if not r["key"]:
            raise ApiError("no API key yet")
        model = str(b.get("model") or eff.load_settings().get("model") or r["model"])
        client = self._client(r, 120)

        def prog(res):
            self.broadcast({"t": "doctor", "row": {"key": res.key, "label": res.label, "ok": res.ok,
                                                    "detail": res.detail, "secs": round(res.secs, 1)}})
        results = doctor.run_all(client, r["kind"], model, prog)
        doctor.save_profile(r["id"], model, results)
        return {"model": model, "rows": [{"key": x.key, "label": x.label, "ok": x.ok, "detail": x.detail,
                                          "secs": round(x.secs, 1)} for x in results],
                "advice": doctor.advice(results)}

    # ------------------------------------------------------------ files
    @staticmethod
    def _abs(cwd: str | None, path: str | None) -> Path:
        p = Path(os.path.expanduser(path or ""))
        if not p.is_absolute():
            p = Path(cwd or Path.home()) / p
        return p.resolve()

    def fs_list(self, q: dict) -> dict:
        cwd = q.get("cwd") or str(Path.home())
        p = self._abs(cwd, q.get("path"))
        if not p.is_dir():
            raise ApiError("not a folder", 404)
        out = []
        try:
            it = list(os.scandir(p))
        except OSError as e:
            raise ApiError(str(e), 403)
        for e in sorted(it, key=lambda e: (not e.is_dir(follow_symlinks=False), e.name.lower())):
            if e.name in (".git",):
                continue
            try:
                d = e.is_dir()
                size = 0 if d else e.stat().st_size
            except OSError:
                continue
            try:
                rel = str(Path(e.path).resolve().relative_to(Path(cwd).resolve()))
            except ValueError:
                rel = e.path
            out.append({"name": e.name, "path": rel, "abs": e.path, "dir": d, "size": size,
                        "dim": e.name in SKIP_DIRS or e.name.startswith(".")})
        return {"path": str(p), "entries": out[:3000]}

    def fs_read(self, q: dict) -> dict:
        p = self._abs(q.get("cwd"), q.get("path"))
        if not p.is_file():
            raise ApiError("file not found", 404)
        size = p.stat().st_size
        ext = p.suffix.lower()
        url = f"/media/file?path={quote(str(p))}&token={self.token}"
        if ext in IMAGE_EXTS:
            return {"kind": "image", "path": str(p), "url": url, "size": size}
        if ext in (".mp4", ".webm", ".mov", ".m4v"):
            return {"kind": "video", "path": str(p), "url": url, "size": size}
        if ext == ".pdf":
            return {"kind": "pdf", "path": str(p), "url": url, "size": size}
        try:  # head=N: only the first N bytes (the Artifacts page's card previews)
            head = max(0, min(int(q.get("head") or 0), 65536))
        except ValueError:
            head = 0
        if size > 2_000_000 and not head:
            return {"kind": "large", "path": str(p), "size": size}
        if head:
            with p.open("rb") as fh:
                data = fh.read(head)
        else:
            data = p.read_bytes()
        if b"\x00" in data[:8192]:
            return {"kind": "binary", "path": str(p), "size": size}
        return {"kind": "text", "path": str(p), "size": size, "ext": ext.lstrip("."),
                "text": data.decode("utf-8", errors="replace")}

    def _all_files(self, cwd: str) -> list[str]:
        c = self.files_cache.get(cwd)
        if c and time.time() - c[0] < 20:
            return c[1]
        out: list[str] = []
        base = Path(cwd)
        for root, dirs, files in os.walk(base):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
            rel = Path(root).relative_to(base)
            for d in dirs:
                out.append(str(rel / d).replace("\\", "/") + "/")
            for f in sorted(files):
                out.append(str(rel / f).replace("\\", "/"))
            if len(out) > 20000:
                break
        out = [x[2:] if x.startswith("./") else x for x in out]
        self.files_cache[cwd] = (time.time(), out)
        return out

    def fs_complete(self, q: dict) -> dict:
        cwd = q.get("cwd") or ""
        if not os.path.isdir(cwd):
            return {"items": []}
        needle = (q.get("q") or "").lower().replace("\\", "/")
        items = []
        for path in self._all_files(cwd):
            low = path.lower()
            name = low.rstrip("/").rsplit("/", 1)[-1]
            if not needle:
                score = 1 if "/" not in low.rstrip("/") else 0
            elif name.startswith(needle):
                score = 4
            elif needle in name:
                score = 3
            elif needle in low:
                score = 2
            else:
                it = iter(low)
                score = 1 if all(ch in it for ch in needle) else 0
            if score:
                items.append((score, len(path), path))
        items.sort(key=lambda x: (-x[0], x[1]))
        return {"items": [{"path": p, "dir": p.endswith("/")} for _s, _l, p in items[:40]]}

    def fs_dirs(self, q: dict) -> dict:
        path = q.get("path") or ""
        if not path:
            roots = []
            if IS_WIN:
                for d in string.ascii_uppercase:
                    if os.path.exists(f"{d}:\\"):
                        roots.append({"name": f"{d}:", "path": f"{d}:\\"})
            else:
                roots.append({"name": "/", "path": "/"})
            home = Path.home()
            places = [{"name": "Home", "path": str(home)}] + [
                {"name": n, "path": str(home / n)} for n in ("Desktop", "Documents", "Downloads") if (home / n).is_dir()]
            return {"path": "", "parent": None, "dirs": places + roots}
        p = Path(os.path.expanduser(path))
        try:
            dirs = sorted((e for e in os.scandir(p) if e.is_dir() and not e.name.startswith((".", "$"))),
                          key=lambda e: e.name.lower())
        except OSError as e:
            raise ApiError(str(e), 403)
        parent = str(p.parent) if p.parent != p else ""
        return {"path": str(p), "parent": parent, "dirs": [{"name": e.name, "path": e.path} for e in dirs[:2000]]}

    def fs_attach(self, b: dict) -> dict:
        out = []
        for raw in b.get("paths") or []:
            p = Path(str(raw))
            if not p.is_file():
                continue
            ext = p.suffix.lower()
            if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"} and p.stat().st_size < 30_000_000:
                mime = MIME.get(ext, "image/png") if ext != ".bmp" else "image/bmp"
                out.append({"kind": "image", "name": p.name, "path": str(p), "mime": mime,
                            "b64": base64.b64encode(p.read_bytes()).decode()})
            else:
                out.append({"kind": "file", "name": p.name, "path": str(p), "size": p.stat().st_size})
        return {"items": out}

    def fs_search(self, q: dict) -> dict:
        cwd = q.get("cwd") or ""
        if not os.path.isdir(cwd):
            raise ApiError("not a folder", 404)
        return search.search(cwd, (q.get("q") or "")[:500], case=q.get("case") == "1", word=q.get("word") == "1",
                             skip=SKIP_DIRS)

    # ------------------------------------------------------------ git
    def git_status(self, q: dict) -> dict:
        cwd = q.get("cwd") or ""
        if not os.path.isdir(cwd):
            return {"repo": False}
        code, top = _run(["git", "-C", cwd, "rev-parse", "--show-toplevel"])
        if code != 0:
            return {"repo": False}
        _c, branch = _run(["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"])
        _c, num = _run(["git", "-C", cwd, "diff", "--numstat", "HEAD"])
        add = rem = files = 0
        for line in num.splitlines():
            parts = line.split("\t")
            if len(parts) >= 3:
                files += 1
                add += int(parts[0]) if parts[0].isdigit() else 0
                rem += int(parts[1]) if parts[1].isdigit() else 0
        _c, untracked = _run(["git", "-C", cwd, "ls-files", "--others", "--exclude-standard"])
        nu = len([l for l in untracked.splitlines() if l.strip()])
        remote = ""                                        # the GitHub page of this repo (https), when origin is on GitHub
        rc, url = _run(["git", "-C", cwd, "remote", "get-url", "origin"])
        m = re.match(r"^(?:https://(?:[^@/]+@)?|git@|ssh://git@)github\.com[:/]+([\w.-]+/[\w.-]+?)(?:\.git)?/?$", url.strip()) if rc == 0 else None
        if m:
            remote = f"https://github.com/{m.group(1)}"
        return {"repo": True, "root": top.strip(), "branch": branch.strip(), "added": add, "removed": rem,
                "files": files + nu, "untracked": nu, "remote": remote}

    # --- git: what the Changes panel shows -------------------------------------------------------------------------
    _REF = re.compile(r"^[A-Za-z0-9_./@^~+-]{1,200}$")

    @classmethod
    def _ref_ok(cls, r: str) -> bool:
        return bool(r) and bool(cls._REF.match(r)) and not r.startswith("-")

    @staticmethod
    def _default_branch(cwd: str, branches: list[str] | None = None) -> str:
        """The branch changes are compared with: the remote's default, else main / master, else HEAD."""
        code, out = _run(["git", "-C", cwd, "symbolic-ref", "--short", "refs/remotes/origin/HEAD"])
        if code == 0 and out.strip():
            return out.strip().splitlines()[0].split("/", 1)[-1]
        if branches is None:
            _c, br = _run(["git", "-C", cwd, "for-each-ref", "--format=%(refname:short)", "refs/heads"])
            branches = [x for x in br.split("\n") if x.strip()]
        for name in ("main", "master"):
            if name in branches:
                return name
        return "HEAD"

    @staticmethod
    def _name_status(out: str) -> dict[str, dict]:
        """`git diff --name-status -z` -> {path: {path, status}} (A new, M changed, D deleted, R renamed)."""
        files: dict[str, dict] = {}
        parts = out.lstrip("\n").split("\0")
        i = 0
        while i < len(parts):
            st = parts[i].strip()
            i += 1
            if not st:
                continue
            if st[0] in "RC" and i + 1 < len(parts):
                path = parts[i + 1]
                i += 2
            elif i < len(parts):
                path = parts[i]
                i += 1
            else:
                break
            files[path] = {"path": path, "status": "A" if st[0] == "A" else "D" if st[0] == "D" else "R" if st[0] == "R" else "M"}
            if len(files) >= 3000:
                break
        return files

    def git_info(self, q: dict) -> dict:
        cwd = q.get("cwd") or ""
        code, out = _run(["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"])
        if code != 0:
            return {"branch": "", "branches": [], "default": "", "commits": []}
        branch = out.strip().splitlines()[0] if out.strip() else ""
        _c, br = _run(["git", "-C", cwd, "for-each-ref", "--format=%(refname:short)", "--sort=-committerdate", "refs/heads"])
        branches = [x.strip() for x in br.split("\n") if x.strip()]
        _c, lg = _run(["git", "-C", cwd, "log", "-n", "30", "--format=%h%x1f%s%x1f%an%x1f%cr"])
        commits = []
        for line in lg.splitlines():
            f = line.split("\x1f")
            if len(f) == 4:
                commits.append({"hash": f[0], "subject": f[1], "author": f[2], "when": f[3]})
        return {"branch": branch, "branches": branches, "default": self._default_branch(cwd, branches), "commits": commits}

    def git_diff(self, q: dict) -> dict:
        """mode: "all" (the working tree against `base`, default the default branch), "uncommitted" (against HEAD) or
        "commit" (what one commit changed)."""
        cwd = q.get("cwd") or ""
        mode = q.get("mode") or "all"
        files: dict[str, dict] = {}
        if mode == "commit":
            c = q.get("commit") or ""
            if not self._ref_ok(c):
                return {"diff": "", "files": []}
            _c, diff = _run(["git", "-C", cwd, "show", "-m", "--first-parent", "--no-color", "--no-ext-diff", "--format=", c], timeout=30)
            _c, ns = _run(["git", "-C", cwd, "show", "-m", "--first-parent", "--name-status", "--format=", "-z", c])
            text = diff.strip()
            if len(text) > 3_000_000:
                text = text[:3_000_000] + "\n… (diff cut)"
            return {"diff": text, "files": list(self._name_status(ns).values())}
        ref = "HEAD"
        if mode == "all":
            b = q.get("base") or self._default_branch(cwd)
            if self._ref_ok(b):
                ref = b
        code, diff = _run(["git", "-C", cwd, "diff", ref, "--no-color", "--no-ext-diff"], timeout=30)
        if code != 0:
            code, diff = _run(["git", "-C", cwd, "diff", "--no-color", "--no-ext-diff"], timeout=30)
            ref = ""
        # Every changed path with its status, also the ones with no text diff (images, video, files too large): the
        # Changes pane lists those too, as a name with no diff under it.
        _c, ns = _run(["git", "-C", cwd, "diff", "--name-status", "-z"] + ([ref] if ref else []))
        files = self._name_status(ns)
        _c, untracked = _run(["git", "-C", cwd, "ls-files", "--others", "--exclude-standard"])
        extra = []
        for rel in [l for l in untracked.splitlines() if l.strip()][:3000]:
            files.setdefault(rel, {"path": rel, "status": "A"})
        for rel in [l for l in untracked.splitlines() if l.strip()][:60]:
            p = Path(cwd) / rel
            try:
                if p.stat().st_size > 300_000:
                    files[rel]["nodiff"] = "Too large to show"
                    continue
                txt = p.read_text(encoding="utf-8")
            except OSError:
                continue
            except UnicodeDecodeError:
                files[rel]["nodiff"] = "Binary file"
                continue
            lines = txt.splitlines()
            extra.append(f"diff --git a/{rel} b/{rel}\nnew file mode 100644\n--- /dev/null\n+++ b/{rel}\n"
                         f"@@ -0,0 +1,{len(lines)} @@\n" + "\n".join("+" + l for l in lines))
        text = (diff.rstrip("\n") + "\n" + "\n".join(extra)).strip()
        if len(text) > 3_000_000:
            text = text[:3_000_000] + "\n… (diff cut)"
        return {"diff": text, "files": list(files.values())}

    # ------------------------------------------------------------ misc
    def state(self) -> dict:
        from ..inputbox import COMMANDS
        r = providers.resolve()
        p = providers.PRESETS.get(r["id"] or "", {})
        import getpass
        return {"version": __version__, "platform": sys.platform, "home": str(Path.home()), "user": getpass.getuser(),
                "has_key": bool(r["key"]), "provider": {"id": r["id"], "label": tr_(p.get("label") or (r["id"] or "")),
                                                        "kind": r["kind"],
                                                        "model": eff.load_settings().get("model") or r["model"]},
                "settings": eff.load_settings(), "folders": self.folders(), "scratch": str(scratch_dir()),
                "root": str(ROOT), "python": sys.executable, "pid": os.getpid(), "log": str(LOG),
                "data_dir": str(paths.HOME_DIR), "settings_file": str(eff.SETTINGS),
                "commands": desktop_commands(COMMANDS, tr_),
                "efforts": [{"name": n, "desc": tr_(e.desc), "max_output": e.max_output} for n, e in eff.LEVELS.items()],
                "workers": [w.describe() for w in self.workers.values()]}

    def whats_new(self) -> dict:
        code, out = _run(["git", "-C", str(ROOT), "log", "-25", "--date=short", "--pretty=format:%h%x09%ad%x09%s"])
        rows = []
        if code == 0:
            for line in out.splitlines():
                parts = line.split("\t", 2)
                if len(parts) == 3:
                    rows.append({"hash": parts[0], "date": parts[1], "subject": parts[2]})
        return {"version": __version__, "commits": rows}

    def open_path(self, b: dict) -> dict:
        p = os.path.expanduser(str(b.get("path") or ""))
        if not os.path.exists(p):
            raise ApiError("not found", 404)
        if b.get("reveal"):
            if IS_WIN:
                subprocess.Popen(["explorer", "/select,", os.path.normpath(p)])
            else:
                subprocess.Popen(["xdg-open", os.path.dirname(p)])
        elif IS_WIN:
            os.startfile(p)                                    # noqa: S606 - the user's own file, opened on request
        else:
            subprocess.Popen(["xdg-open", p])
        return {"ok": True}

    def logo_file(self, kind: str) -> Path | None:
        from .. import logo
        if kind == "still":
            custom = eff.load_settings().get("logo")
            if custom and Path(custom).suffix.lower() in logo.IMAGE_EXTS and Path(custom).is_file():
                return Path(custom)
            p = logo.find_still()
            if p:
                return p
            f = logo.find_logo()
            return f if f and f.suffix.lower() in logo.IMAGE_EXTS else None
        return logo.find_logo()

    def persona_info(self) -> dict:
        proj = Path(os.getcwd()) / ".emilie" / "persona.md"
        return {"enabled": persona.enabled(), "text": persona.text(), "file": str(persona.HOME_FILE),
                "default": persona.DEFAULT.strip(), "project_file": str(proj) if proj.exists() else None}

    def set_persona(self, b: dict) -> dict:
        if b.get("reset"):
            persona.reset()
        if "text" in b:
            persona.HOME_FILE.parent.mkdir(parents=True, exist_ok=True)
            persona.HOME_FILE.write_text(str(b["text"]).strip() + "\n", encoding="utf-8")
        if "enabled" in b:
            persona.set_enabled(bool(b["enabled"]))
        return self.persona_info()

    def mcp_config(self, q: dict) -> dict:
        def read(p: Path) -> dict:
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                return d.get("mcpServers") or d.get("servers") or {}
            except (OSError, ValueError):
                return {}
        user = paths.HOME_DIR / "mcp.json"
        out = {"user": {"path": str(user), "servers": read(user), "exists": user.exists()}}
        cwd = q.get("cwd")
        if cwd and os.path.isdir(cwd):
            proj = Path(cwd) / ".mcp.json"
            out["project"] = {"path": str(proj), "servers": read(proj), "exists": proj.exists()}
        return out

    def set_mcp_config(self, b: dict) -> dict:
        servers = b.get("servers")
        if not isinstance(servers, dict):
            raise ApiError("servers must be an object")
        for name, cfg in servers.items():
            if not re.fullmatch(r"[\w.-]{1,60}", str(name)) or not isinstance(cfg, dict):
                raise ApiError(f"bad server '{name}'")
            if not (cfg.get("command") or cfg.get("url")):
                raise ApiError(f"server '{name}' needs a command or a url")
        if b.get("scope") == "project":
            cwd = str(b.get("cwd") or "")
            if not os.path.isdir(cwd):
                raise ApiError("no project folder")
            p = Path(cwd) / ".mcp.json"
        else:
            p = paths.HOME_DIR / "mcp.json"
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        data["mcpServers"] = servers
        data.pop("servers", None)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return self.mcp_config({"cwd": b.get("cwd")})

    def schedule_info(self) -> dict:
        from .. import schedule
        return {"supported": schedule.supported(), "rows": schedule.listing() if schedule.supported() else []}

    def schedule_action(self, b: dict) -> dict:
        from .. import schedule
        a = b.get("action")
        if a == "add":
            res = schedule.add(str(b.get("name") or ""), str(b.get("kind") or "daily").lower(), str(b.get("at") or ""),
                               str(b.get("prompt") or ""), str(b.get("folder") or ""), trust=bool(b.get("trust")))
        elif a in ("rm", "run"):
            res = (schedule.remove if a == "rm" else schedule.run_now)(str(b.get("name") or ""))
        else:
            raise ApiError("action: add | rm | run")
        if res.startswith("ERROR"):
            raise ApiError(res[6:].strip() or res)
        return {"message": res, **self.schedule_info()}

    def camera_info(self) -> dict:
        from .. import camera
        return {"available": camera.available(), "devices": camera.devices(), "configured": camera.configured()}

    def camera_photo(self) -> dict:
        from .. import camera
        if not camera.available():
            raise ApiError("no camera found (needs ffmpeg: winget install Gyan.FFmpeg)")
        data, msg = camera.grab()
        if not data:
            raise ApiError(f"camera: {msg}")
        return {"mime": "image/jpeg", "b64": base64.b64encode(data).decode(), "name": "camera.jpg"}

    def companion_info(self, b: dict | None = None) -> dict:
        from .. import companion
        if b and b.get("forget"):
            companion.forget()
        return {"lines": companion.describe(companion.load())}

    def trusted(self) -> dict:
        return {"folders": trust._load()}

    def skills_info(self, q: dict) -> dict:
        """Skills and custom commands as a session in `cwd` would see them (built-in, ~/.emilie, the project)."""
        from .. import skills
        cwd = q.get("cwd") or str(Path.home())
        try:                                  # "Open skills folder" must have a folder to open: the shell does nothing for a missing one
            (paths.HOME_DIR / "skills").mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        with self.lock:
            skills.load(cwd if os.path.isdir(cwd) else str(Path.home()))
            items = []
            for n, sk in skills.SKILLS.items():
                res = skills.resources(sk)
                items.append({"name": n, "description": sk.description, "phase": sk.phase, "kind": "skill",
                              "phase_label": skills.phase_label(sk.phase) if sk.phase else "", "source": sk.source,
                              "path": str(sk.path), "refs": len(res.get("references", [])),
                              "scripts": len(res.get("scripts", []))})
            for n, cm in skills.COMMANDS.items():
                items.append({"name": n, "description": cm.description, "source": cm.source, "kind": "command",
                              "path": str(getattr(cm, "path", "")), "phase": "", "phase_label": ""})
            return {"items": items, "skipped": list(skills.SKIPPED), "cwd": cwd,
                    "phases": [{"id": p, "label": skills.phase_label(p)} for p, _ in skills.PHASES],
                    "folders": [str(paths.HOME_DIR / "skills"), str(Path(cwd) / ".emilie" / "skills")]}

    WRITE_NAMES = {"write_file", "edit_file", "docx_create", "docx_edit", "xlsx_write", "notebook_edit"}

    def artifacts(self) -> dict:
        """Files Emilie wrote or edited, found in the saved sessions (newest first)."""
        out: dict[str, dict] = {}
        for f in session.ROOT.glob("*/*.json"):
            if f.parent.name.startswith("."):              # files of deleted sessions are not listed
                continue
            try:
                st = f.stat()
            except OSError:
                continue
            c = self.art_cache.get(str(f))
            if not c or c[0] != st.st_mtime_ns:
                try:
                    d = json.loads(f.read_text(encoding="utf-8", errors="replace"))
                except (OSError, ValueError):
                    continue
                found = []
                for m in d.get("messages") or []:
                    if m.get("role") != "assistant":
                        continue
                    calls = []
                    if isinstance(m.get("content"), list):
                        calls += [(b_.get("name"), b_.get("input") or {}) for b_ in m["content"]
                                  if isinstance(b_, dict) and b_.get("type") == "tool_use"]
                    for tc in m.get("tool_calls") or []:
                        fn = tc.get("function") or {}
                        try:
                            args = json.loads(fn.get("arguments") or "{}")
                        except ValueError:
                            args = {}
                        calls.append((fn.get("name"), args))
                    found += [(n, str(a["path"])) for n, a in calls
                              if n in self.WRITE_NAMES and isinstance(a, dict) and a.get("path")]
                c = (st.st_mtime_ns, {"sid": d.get("id") or f.stem, "cwd": d.get("cwd") or "",
                                      "updated": d.get("updated") or st.st_mtime, "title": d.get("title") or "",
                                      "files": found})
                self.art_cache[str(f)] = c
            info = c[1]
            for name, path in info["files"]:
                p = Path(path)
                p = p if p.is_absolute() else Path(info["cwd"]) / p
                k = os.path.normcase(str(p))
                e = out.get(k)
                if e is None or e["updated"] < info["updated"]:
                    out[k] = {"path": str(p), "name": p.name, "tool": name, "session": info["sid"], "cwd": info["cwd"],
                              "title": self._meta(info["sid"]).get("title") or info["title"],
                              "updated": info["updated"], "exists": p.exists()}
        return {"files": sorted(out.values(), key=lambda r: r["updated"], reverse=True)[:500]}

    def voice_test(self, b: dict) -> dict:
        from .. import voice
        voice.VOICE.speak(str(b.get("text") or "Hello, this is Emilie."))
        return {"ok": True, "status": voice.VOICE.status_lines()}


# ====================================================================== HTTP
def make_handler(hub: Hub):
    class H(BaseHTTPRequestHandler):
        server_version = "Emilie"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):            # quiet; errors go to the log file
            pass

        # ------------------------------------------------ helpers
        def _ok_host(self) -> bool:
            host = (self.headers.get("Host") or "").lower()
            return host in (f"127.0.0.1:{hub.port}", f"localhost:{hub.port}")

        def _ok_token(self, q: dict) -> bool:
            tok = self.headers.get("X-Emilie-Token") or q.get("token") or ""
            return hmac.compare_digest(str(tok), hub.token)

        def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def json(self, obj, status: int = 200) -> None:
            self._send(status, json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"),
                       "application/json; charset=utf-8")

        def file(self, p: Path, cache: bool = False) -> None:
            try:
                size = p.stat().st_size
            except OSError:
                return self.json({"error": "not found"}, 404)
            ctype = MIME.get(p.suffix.lower()) or mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            start, end, status = 0, size - 1, 200
            rng = self.headers.get("Range") or ""
            m = re.fullmatch(r"bytes=(\d*)-(\d*)", rng.strip())
            if m and size:
                a, b_ = m.group(1), m.group(2)
                if a:
                    start, end = int(a), int(b_) if b_ else size - 1
                elif b_:
                    start, end = max(0, size - int(b_)), size - 1
                end = min(end, size - 1)
                if start > end:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                status = 206
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1 if size else 0))
            self.send_header("Cache-Control", "max-age=86400" if cache else "no-cache")
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            if self.command == "HEAD" or not size:
                return
            with open(p, "rb") as fh:
                fh.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = fh.read(min(256 * 1024, left))
                    if not chunk:
                        break
                    try:
                        self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                        return
                    left -= len(chunk)

        def body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n > 80_000_000:
                raise ApiError("request too large", 413)
            raw = self.rfile.read(n) if n else b""
            if not raw:
                return {}
            try:
                d = json.loads(raw.decode("utf-8"))
            except ValueError:
                raise ApiError("bad JSON")
            return d if isinstance(d, dict) else {}

        # ------------------------------------------------ verbs
        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

        def _dispatch(self, method: str) -> None:
            url = urlparse(self.path)
            q = {k: v[-1] for k, v in parse_qs(url.query).items()}
            path = url.path
            try:
                b = self.body() if method == "POST" else {}     # always read it: the connection is kept alive
            except ApiError as e:
                self.close_connection = True
                return self.json({"error": str(e)}, e.status)
            if not self._ok_host():
                return self._send(403, b"forbidden host", "text/plain")
            try:
                if path.startswith(("/api/", "/media/")):
                    if not self._ok_token(q):
                        return self.json({"error": "bad token"}, 401)
                    if path == "/api/events":
                        return self.events()
                    if path.startswith("/media/"):
                        return self.media(path, q)
                    fn = ROUTES.get((method, path))
                    if fn is None:
                        return self.json({"error": f"no route {method} {path}"}, 404)
                    return self.json(fn(hub, q, b))
                if method != "GET" and method != "HEAD":
                    return self.json({"error": "not allowed"}, 405)
                return self.static(path)
            except ApiError as e:
                return self.json({"error": str(e)}, e.status)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return
            except Exception as e:
                hub.log(f"{method} {path}: {traceback.format_exc()}")
                try:
                    return self.json({"error": f"{type(e).__name__}: {e}"}, 500)
                except Exception:
                    return

        def static(self, path: str) -> None:
            rel = path.lstrip("/") or "index.html"
            p = (WEB / rel).resolve()
            if WEB.resolve() not in p.parents and p != WEB.resolve() / "index.html" or not p.is_file():
                p = WEB / "index.html"                    # single page app
            if not p.is_file():
                msg = ("<h1>Emilie desktop UI is not built yet</h1><p>Run <code>npm install</code> and "
                       "<code>npm run build</code> in the <code>desktop</code> folder.</p>")
                return self._send(200, msg.encode(), "text/html; charset=utf-8")
            self.file(p, cache=p.name != "index.html" and "/assets/" in path)

        def media(self, path: str, q: dict) -> None:
            if path in ("/media/logo", "/media/logo-still"):
                p = hub.logo_file("still" if path.endswith("still") else "main")
                return self.file(p) if p else self.json({"error": "no logo"}, 404)
            if path == "/media/file":
                p = Path(q.get("path") or "")
                return self.file(p) if p.is_file() else self.json({"error": "not found"}, 404)
            return self.json({"error": "not found"}, 404)

        def events(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            q = hub.subscribe()
            try:
                self.wfile.write(b": hello\n\n")
                self.wfile.flush()
                while True:
                    try:
                        data = q.get(timeout=15)
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                        continue
                    chunks = [data]
                    while not q.empty() and len(chunks) < 200:          # several events in one write
                        chunks.append(q.get_nowait())
                    self.wfile.write("".join(f"data: {c}\n\n" for c in chunks).encode("utf-8"))
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                pass
            finally:
                hub.unsubscribe(q)
                self.close_connection = True
    return H


# ====================================================================== routes
def _w(h: Hub, b: dict) -> WorkerProc:
    return h.worker(b.get("wid") or "")


def _set_setting(h: Hub, q: dict, b: dict) -> dict:
    items = b.get("values") if isinstance(b.get("values"), dict) else {b.get("key"): b.get("value")}
    saved, errors = {}, {}
    for k, v in items.items():
        if not k:
            continue
        val, err = schema.apply(str(k), v)
        if err:
            errors[k] = err
        else:
            saved[k] = val
            h.broadcast({"t": "settings", "key": k, "value": val})
            for w in list(h.workers.values()):
                try:
                    w.send({"cmd": "settings_changed", "key": k})
                except ApiError:
                    pass
    if errors and not saved:
        raise ApiError("; ".join(f"{v}" for v in errors.values()))
    return {"saved": saved, "errors": errors, "values": eff.load_settings()}


def _send_msg(h: Hub, q: dict, b: dict) -> dict:
    w = _w(h, b)
    w.send({"cmd": "send", "cid": b.get("cid"), "text": b.get("text") or "", "images": b.get("images") or [],
            "files": b.get("files") or [], "pastes": b.get("pastes") or []})
    w.used = time.time()
    return {"ok": True}


def _restart(h: Hub, q: dict, b: dict) -> dict:
    w = _w(h, b)
    sid, cwd = w.session_id, w.cwd
    h.close_worker(w)
    return h.open_session({"id": sid, "cwd": cwd})


def _term_run(h: Hub, q: dict, b: dict) -> dict:
    cwd = str(b.get("cwd") or Path.home())
    cmd = str(b.get("command") or "").strip()
    if not cmd:
        raise ApiError("empty command")
    if not os.path.isdir(cwd):
        raise ApiError("folder not found")
    tid = f"term{next(h._tids)}"
    h.terms[tid] = Term(h, tid, cwd, cmd, str(b.get("name") or "")[:120])
    return {"tid": tid}


def _term_kill(h: Hub, q: dict, b: dict) -> dict:
    t = h.terms.get(str(b.get("tid")))
    if t:
        t.kill()
    return {"ok": True}


def _trust(h: Hub, q: dict, b: dict) -> dict:
    p = str(b.get("path") or "")
    if b.get("remove"):
        trust.remove(p)
    else:
        if not os.path.isdir(p):
            raise ApiError("folder not found")
        trust.add(p)
    return h.trusted()


def _mkdir(h: Hub, q: dict, b: dict) -> dict:
    p = Path(os.path.expanduser(str(b.get("path") or "")))
    if not p.is_absolute():
        raise ApiError("give a full path")
    p.mkdir(parents=True, exist_ok=True)
    return {"path": str(p)}


def _user(fn):
    """A route whose errors are the user's to read (not a crash): they come back as a plain 400 message."""
    def call(h: Hub, q: dict, b: dict):
        try:
            return fn(h, q, b)
        except (gitops.GitError, ValueError, OSError) as e:
            raise ApiError(str(e) or type(e).__name__, 400)
    return call


def _folder(q: dict, b: dict) -> str:
    cwd = str(b.get("cwd") or q.get("cwd") or "")
    if not cwd or not os.path.isdir(cwd):
        raise ApiError("folder not found", 404)
    return cwd


def _job(kind: str, fn):
    """Start fn(job, cwd, q, b) as a background job; the panel follows it with /api/job."""
    def call(h: Hub, q: dict, b: dict):
        cwd = _folder(q, b)
        return projkit.start_job(kind, cwd, lambda job: fn(job, cwd, q, b))
    return call


def _git_commit(job, cwd: str, q: dict, b: dict) -> dict:
    return gitops.commit(job, cwd, str(b.get("message") or ""), amend=bool(b.get("amend")), all_=bool(b.get("all")),
                         push=bool(b.get("push")))


def _git_sync(job, cwd: str, q: dict, b: dict) -> dict:
    return gitops.sync(job, cwd, str(b.get("action") or ""))


def _problems_run(job, cwd: str, q: dict, b: dict) -> dict:
    return checks.run_checks(job, cwd, [str(x) for x in b.get("ids") or []])


def _tests_run(job, cwd: str, q: dict, b: dict) -> dict:
    return testrun.run_tests(job, cwd, str(b.get("suite") or ""), str(b.get("python") or ""),
                             [str(x) for x in b.get("only") or []])


def _ports_kill(h: Hub, q: dict, b: dict) -> dict:
    try:
        pid = int(b.get("pid") or 0)
    except (TypeError, ValueError):
        raise ApiError("bad pid")
    return netkit.kill(pid, h.own_pids())


def _term_list(h: Hub, q: dict, b: dict) -> dict:
    return {"terms": [t.describe() for t in list(h.terms.values())]}


def _usage(h: Hub, q: dict, b: dict) -> dict:
    """Settings -> Usage: tokens by provider and model, in total and per day (?days=7|30|90|0 for all time)."""
    from .. import usage_log
    try:
        days = int(q.get("days") or 30)
    except ValueError:
        days = 30
    return usage_log.LEDGER.summary(days if days > 0 else None)


ROUTES = {
    ("GET", "/api/state"): lambda h, q, b: h.state(),
    ("GET", "/api/sessions"): lambda h, q, b: {"sessions": h.sessions(), "folders": h.folders(),
                                               "scratch": str(scratch_dir())},
    ("POST", "/api/session/open"): lambda h, q, b: h.open_session(b),
    ("POST", "/api/session/send"): _send_msg,
    ("POST", "/api/session/stop"): lambda h, q, b: (_w(h, b).send({"cmd": "stop"}), {"ok": True})[1],
    ("POST", "/api/session/answer"): lambda h, q, b: (_w(h, b).send({"cmd": "answer", "id": b.get("id"),
                                                                     "value": b.get("value")}), {"ok": True})[1],
    ("POST", "/api/session/set"): lambda h, q, b: (_w(h, b).send({"cmd": "set", **{k: v for k, v in b.items()
                                                                                  if k in ("mode", "model", "effort",
                                                                                           "title")}}),
                                                   {"ok": True})[1],
    ("POST", "/api/session/snapshot"): lambda h, q, b: _w(h, b).call("snapshot"),
    ("POST", "/api/session/status"): lambda h, q, b: _w(h, b).call("status"),
    ("POST", "/api/session/commands"): lambda h, q, b: _w(h, b).call("commands"),
    ("POST", "/api/session/call"): lambda h, q, b: (_w(h, b).send({"cmd": "call", "on": bool(b.get("on"))}),
                                                    {"ok": True})[1],
    ("POST", "/api/session/talk"): lambda h, q, b: (_w(h, b).send({"cmd": "talk", "on": bool(b.get("on"))}),
                                                    {"ok": True})[1],
    ("POST", "/api/session/typing"): lambda h, q, b: (_w(h, b).send({"cmd": "typing"}), {"ok": True})[1],
    ("POST", "/api/session/voice_test"): lambda h, q, b: (_w(h, b).send({"cmd": "voice_test", "text": b.get("text")}),
                                                          {"ok": True})[1],
    ("POST", "/api/session/call/frame"): lambda h, q, b: _w(h, b).call("frame", timeout=5),
    ("POST", "/api/session/checkpoint"): lambda h, q, b: _w(h, b).call("checkpoint", timeout=15, n=b.get("n")),
    ("POST", "/api/session/bg"): lambda h, q, b: _w(h, b).call("bg", timeout=10, stop=b.get("stop"), open=b.get("open")),
    ("POST", "/api/session/mcp"): lambda h, q, b: _w(h, b).call("mcp", timeout=60, reload=bool(b.get("reload")), reconnect=b.get("reconnect") or ""),
    ("POST", "/api/session/skills"): lambda h, q, b: _w(h, b).call("skills", reload=bool(b.get("reload"))),
    ("POST", "/api/session/export"): lambda h, q, b: _w(h, b).call("export", target=b.get("target") or ""),
    ("POST", "/api/session/fork"): lambda h, q, b: _w(h, b).call("fork", mi=b.get("mi")),
    ("POST", "/api/session/close"): lambda h, q, b: (h.close_worker(_w(h, b)), {"ok": True})[1],
    ("POST", "/api/session/restart"): _restart,
    ("POST", "/api/sessions/rename"): lambda h, q, b: h.rename_session(b),
    ("GET", "/api/plugins"): lambda h, q, b: h.plugins_call("list", {}),
    ("POST", "/api/plugins/install"): lambda h, q, b: h.plugins_call("install", b),
    ("POST", "/api/plugins/toggle"): lambda h, q, b: h.plugins_call("toggle", b),
    ("POST", "/api/plugins/remove"): lambda h, q, b: h.plugins_call("remove", b),
    ("POST", "/api/sessions/delete_all"): lambda h, q, b: h.delete_all_sessions(b),
    ("POST", "/api/sessions/delete"): lambda h, q, b: h.delete_session(b),
    ("GET", "/api/settings"): lambda h, q, b: {"values": eff.load_settings(), "schema": schema.build()},
    ("POST", "/api/settings"): _set_setting,
    ("GET", "/api/providers"): lambda h, q, b: h.providers_info(),
    ("POST", "/api/providers"): lambda h, q, b: h.set_provider(b),
    ("POST", "/api/providers/test"): lambda h, q, b: h.provider_test(b),
    ("GET", "/api/models"): lambda h, q, b: h.models_list(q.get("refresh") == "1"),
    ("GET", "/api/fs/list"): lambda h, q, b: h.fs_list(q),
    ("GET", "/api/fs/read"): lambda h, q, b: h.fs_read(q),
    ("GET", "/api/fs/search"): lambda h, q, b: h.fs_search(q),
    ("GET", "/api/fs/complete"): lambda h, q, b: h.fs_complete(q),
    ("GET", "/api/fs/dirs"): lambda h, q, b: h.fs_dirs(q),
    ("POST", "/api/fs/attach"): lambda h, q, b: h.fs_attach(b),
    ("POST", "/api/fs/mkdir"): _mkdir,
    ("GET", "/api/git/status"): lambda h, q, b: h.git_status(q),
    ("GET", "/api/git/diff"): lambda h, q, b: h.git_diff(q),
    ("GET", "/api/git/info"): lambda h, q, b: h.git_info(q),
    ("GET", "/api/worktree/info"): lambda h, q, b: h.worktree_info(q),
    ("POST", "/api/worktree/remove"): lambda h, q, b: h.worktree_remove(b),
    ("POST", "/api/term/run"): _term_run,
    ("POST", "/api/term/kill"): _term_kill,
    ("GET", "/api/term/list"): _term_list,
    # the project panels (Git, Scripts, Problems, Tests, HTTP, Ports, Notes, Database) and their background jobs
    ("GET", "/api/job"): lambda h, q, b: projkit.job_info(q.get("id") or "", int(q.get("since") or 0)),
    ("POST", "/api/job/stop"): lambda h, q, b: projkit.job_stop(str(b.get("id") or "")),
    ("GET", "/api/git/scm"): _user(lambda h, q, b: gitops.status(q.get("cwd") or "")),
    ("GET", "/api/git/file"): _user(lambda h, q, b: gitops.file_diff(_folder(q, b), q.get("path") or "",
                                                                    q.get("staged") == "1", q.get("untracked") == "1")),
    ("GET", "/api/git/commit"): _user(lambda h, q, b: gitops.commit_files(_folder(q, b), q.get("hash") or "")),
    ("POST", "/api/git/init"): _user(lambda h, q, b: gitops.init(_folder(q, b))),
    ("POST", "/api/git/stage"): _user(lambda h, q, b: gitops.stage(_folder(q, b), b.get("paths"))),
    ("POST", "/api/git/unstage"): _user(lambda h, q, b: gitops.unstage(_folder(q, b), b.get("paths"))),
    ("POST", "/api/git/discard"): _user(lambda h, q, b: gitops.discard(_folder(q, b), b.get("paths"), b.get("untracked"))),
    ("POST", "/api/git/commit"): _job("git-commit", _git_commit),
    ("POST", "/api/git/sync"): _job("git-sync", _git_sync),
    ("POST", "/api/git/branch"): _user(lambda h, q, b: gitops.branch(_folder(q, b), str(b.get("action") or ""),
                                                                    str(b.get("name") or ""), str(b.get("start") or ""),
                                                                    bool(b.get("force")))),
    ("POST", "/api/git/stash"): _user(lambda h, q, b: gitops.stash(_folder(q, b), str(b.get("action") or ""),
                                                                  str(b.get("ref") or ""), str(b.get("message") or ""))),
    ("GET", "/api/project/scripts"): _user(lambda h, q, b: pscripts.detect(_folder(q, b))),
    ("POST", "/api/project/commands"): _user(lambda h, q, b: pscripts.save_custom(_folder(q, b), b.get("commands") or [])),
    ("GET", "/api/problems/checkers"): _user(lambda h, q, b: {"checkers": checks.detect(_folder(q, b))}),
    ("POST", "/api/problems/run"): _job("problems", _problems_run),
    ("GET", "/api/tests/suites"): _user(lambda h, q, b: testrun.detect(_folder(q, b), q.get("python") or "")),
    ("POST", "/api/tests/run"): _job("tests", _tests_run),
    ("POST", "/api/http/send"): _user(lambda h, q, b: netkit.send(b)),
    ("GET", "/api/ports"): _user(lambda h, q, b: netkit.ports(h.own_pids())),
    ("POST", "/api/ports/kill"): _user(_ports_kill),
    ("GET", "/api/notes"): _user(lambda h, q, b: notes.get(_folder(q, b))),
    ("POST", "/api/notes"): _user(lambda h, q, b: notes.save(_folder(q, b), str(b.get("text") or ""))),
    ("GET", "/api/notes/todos"): _user(lambda h, q, b: notes.todos(_folder(q, b))),
    ("GET", "/api/db/files"): _user(lambda h, q, b: sqlview.files(_folder(q, b))),
    ("GET", "/api/db/tables"): _user(lambda h, q, b: sqlview.tables(q.get("path") or "")),
    ("GET", "/api/db/rows"): _user(lambda h, q, b: sqlview.browse(q.get("path") or "", q.get("table") or "",
                                                                 int(q.get("offset") or 0), int(q.get("limit") or 200),
                                                                 q.get("order") or "", q.get("desc") == "1")),
    ("POST", "/api/db/query"): _user(lambda h, q, b: sqlview.query(str(b.get("path") or ""), str(b.get("sql") or ""),
                                                                  bool(b.get("write")))),
    ("GET", "/api/persona"): lambda h, q, b: h.persona_info(),
    ("POST", "/api/persona"): lambda h, q, b: h.set_persona(b),
    ("GET", "/api/mcp/config"): lambda h, q, b: h.mcp_config(q),
    ("POST", "/api/mcp/config"): lambda h, q, b: h.set_mcp_config(b),
    ("GET", "/api/schedule"): lambda h, q, b: h.schedule_info(),
    ("POST", "/api/schedule"): lambda h, q, b: h.schedule_action(b),
    ("GET", "/api/camera"): lambda h, q, b: h.camera_info(),
    ("POST", "/api/camera/device"): lambda h, q, b: (__import__("emilie.camera", fromlist=["x"]).set_device(
        b.get("device") or None), h.camera_info())[1],
    ("POST", "/api/camera/photo"): lambda h, q, b: h.camera_photo(),
    ("GET", "/api/companion"): lambda h, q, b: h.companion_info(),
    ("POST", "/api/companion"): lambda h, q, b: h.companion_info(b),
    ("GET", "/api/trust"): lambda h, q, b: {"trusted": trust.is_trusted(q.get("path") or ""),
                                            "exists": os.path.isdir(q.get("path") or ""),
                                            "risky": trust.is_risky(q.get("path") or ""), **h.trusted()},
    ("POST", "/api/trust"): _trust,
    ("GET", "/api/whatsnew"): lambda h, q, b: h.whats_new(),
    ("GET", "/api/skills"): lambda h, q, b: h.skills_info(q),
    ("POST", "/api/voice/test"): lambda h, q, b: h.voice_test(b),
    ("GET", "/api/artifacts"): lambda h, q, b: h.artifacts(),
    ("GET", "/api/usage"): _usage,
    ("POST", "/api/open"): lambda h, q, b: h.open_path(b),
}


def serve(port: int = 0, token: str | None = None, on_ready=None) -> None:
    import secrets
    hub = Hub(token or secrets.token_urlsafe(24))
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(hub))
    httpd.daemon_threads = True
    hub.port = httpd.server_address[1]
    url = f"http://127.0.0.1:{hub.port}/?token={hub.token}"
    if on_ready:
        on_ready(hub, url)
    try:
        httpd.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        hub.shutdown()
        httpd.server_close()
