"""One session of the desktop app, in its own process:  python -X utf8 -m emilie.desktop.worker

The hub (hub.py) starts one worker per open session, so several sessions can run at the same time, each in its own
folder (the agent works in the process's current directory). The CLI core runs here UNCHANGED (cli.make_core): every
slash command, skill, MCP server, permission rule and the agent loop are exactly the CLI's. Only the display is
replaced:

    console.print(...)      -> DesktopConsole -> "item" events (blocks.py turns panels/tables into JSON)
    console.tui             -> Desk: ask_permission / choose / mark_running / talk_toggle / live, like the TUI
    StreamView              -> DesktopStreamView: text deltas instead of a terminal spinner
    ui.tool_header/result   -> "item" / "tool_end" events with the full output and a real diff

Protocol, one JSON object per line:
    stdin  <- {"cmd": "init" | "send" | "stop" | "answer" | "set" | "call" | "talk" | ..., "rid": n (when a reply is wanted)}
    stdout -> {"t": "warm" | "ready" | "item" | "delta" | "tool_end" | "request" | "status" | "reply" | ...}
Anything else the code prints goes to stderr (the hub writes it to ~/.emilie/desktop/desktop.log).
"""
from __future__ import annotations

import base64
import ctypes
import io
import itertools
import json
import os
import queue
import re
import sys
import threading
import time
import traceback
from urllib.parse import urlparse

from .stdio import private_stdio  # noqa: E402

_IN, _OUT = private_stdio()       # the protocol channel; stray prints and child processes only see stderr

from rich.console import Console  # noqa: E402
from rich.text import Text  # noqa: E402

from .. import agent as agent_mod  # noqa: E402
from .. import cli, clip, effort as eff, i18n, paths, session, stream, talk, tools, ui, voice  # noqa: E402
from ..i18n import t as tr_  # noqa: E402
from ..inputbox import COMMANDS, EXTRA_COMMANDS, PH_TEXT, Submission  # noqa: E402
from ..policy import MODES  # noqa: E402
from . import blocks, convert  # noqa: E402

_wlock = threading.Lock()
_ids = itertools.count(1)
_RUN = os.urandom(3).hex()               # this process's own part of every id (see nid)
META_DIR = paths.HOME_DIR / "desktop" / "sessions"
from . import TERMINAL_ONLY  # noqa: E402,F401  (kept importable from here)


def nid(prefix: str) -> str:
    """A new id for an item, a message or a request. The page updates the item with a known id in place, so ids must
    stay unique when a session is opened again in a NEW process (Restart after a provider change, reopening the app):
    a plain counter started again at "x1", and a new /doctor answer overwrote an old card far up the conversation
    while nothing appeared under the new command."""
    return f"{prefix}{_RUN}{next(_ids)}"


def _voice_phase(p: str) -> None:
    emit("voice_phase", phase=p)


voice.VOICE.on_phase = _voice_phase        # the page shows what the voice is doing (making it / speaking)


def emit(t: str, **kw) -> None:
    kw["t"] = t
    line = json.dumps(kw, ensure_ascii=True, default=str)
    with _wlock:
        try:
            _OUT.write(line + "\n")
            _OUT.flush()
        except (OSError, ValueError):
            os._exit(0)                          # the hub is gone


def log(msg: str) -> None:
    try:
        sys.stderr.write(f"[worker {os.getpid()}] {msg}\n")
        sys.stderr.flush()
    except Exception:
        pass


DESK: "Desk | None" = None


# ====================================================================== console + stream
class DesktopConsole(Console):
    """The console the CLI core prints to. Nothing reaches a terminal: every print becomes a transcript item."""

    def __init__(self, desk: "Desk"):
        super().__init__(file=io.StringIO(), width=100, force_terminal=False, color_system="truecolor",
                         legacy_windows=False, highlight=False)
        self.tui = desk

    def print(self, *objects, **kw):  # noqa: A003
        self.tui.on_print(objects, kw)

    def log(self, *objects, **kw):
        self.tui.on_print(objects, kw)

    def status(self, status="", **kw):
        return _Activity(self.tui, status)


class _Activity:
    """console.status("compacting…"): shown in the UI's working line while the block runs."""

    def __init__(self, desk, status):
        self.desk, self.text = desk, blocks.plain((status,)).strip()

    def __enter__(self):
        emit("activity", text=self.text)
        return self

    def __exit__(self, *exc):
        emit("activity", text=None)
        return False

    def update(self, status="", **kw):
        emit("activity", text=blocks.plain((status,)).strip())


def _draft_field(args: str, key: str) -> str:
    """A string field from a tool call's JSON that is still arriving (it may be cut anywhere)."""
    m = re.search(r'"%s"\s*:\s*"((?:[^"\\]|\\.)*)' % key, args)
    if not m:
        return ""
    try:
        return json.loads('"' + m.group(1).rstrip("\\") + '"')
    except ValueError:
        return m.group(1)


def draft_activity(name: str, args: str) -> str:
    """Working-line text for a tool call the model is still writing. The UI picks an icon from the first word."""
    path = _draft_field(args, "path") or _draft_field(args, "file_path")
    base = os.path.basename(path.replace("\\", "/")) if path else ""
    if name == "write_file":
        n = args.count("\\n")
        return f"Writing {base or 'a file'}" + (f" · {n:,} lines" if n else "") + "…"
    if name in ("edit_file", "notebook_edit", "docx_edit", "xlsx_write"):
        return f"Editing {base or 'a file'}…"
    if name in ("bash", "bash_bg"):
        return "Preparing a command…"
    if name in ("read_file", "docx_read", "xlsx_read", "pptx_read"):
        return f"Reading {base or 'a file'}…"
    if name in ("grep", "glob"):
        return "Searching the project…"
    if name == "web_search":
        return "Searching the web…"
    if name == "web_fetch":
        return "Fetching a page…"
    if name == "docx_create":
        return f"Writing {base or 'a document'}…"
    if name == "todo_write":
        return "Planning the tasks…"
    if name in ("task", "tasks"):
        return "Briefing a helper…"
    if name == "exit_plan_mode":
        return "Writing the plan…"
    return f"Preparing {convert.label(name)}…" if name else ""


class DesktopStreamView(stream.StreamView):
    """One model answer: the text goes to the UI as deltas (flushed every 50 ms by Desk._ticker)."""

    def __init__(self, console):
        super().__init__(console)
        self.desk: Desk = console.tui
        self.sid = nid("s")
        self.full = ""
        self.pending = ""
        self.plock = threading.Lock()
        self.closed = False
        self.vo = False                          # voice on: the words are held back and appear together with the voice

    def start(self):
        self.t0 = time.time()
        self.vo = bool(voice.VOICE.enabled or getattr(voice.VOICE, "story", False))
        self.desk.live = self
        self.desk.stream_id, self.desk.stream_text = self.sid, ""
        self.desk.flush_quiet()                  # a model answer: the command that asked for it belongs in the conversation
        emit("stream_start", id=self.sid, voice=self.vo)
        return self

    def text(self, text: str) -> None:
        self.think(text)
        self.full += text
        if not self.swallow and stream.is_quota_error(self.full):
            self.swallow = True                  # the provider's 'quota exhausted' answer is not a real reply
            emit("stream_discard", id=self.sid)
        if not self.swallow and not self.vo:
            with self.plock:
                self.pending += text

    _DRAFT_T = 0.0

    def tool_draft(self, name: str, args_so_far: str) -> None:
        """While the model writes a long tool call (a whole web page for write_file) nothing else moves on screen:
        show what is being written and how far it got, at most 4 times a second."""
        now = time.time()
        if now - self._DRAFT_T < 0.25:
            return
        self._DRAFT_T = now
        text = draft_activity(name, args_so_far)
        if text and text != getattr(self, "_draft_text", None):
            self._draft_text = text
            emit("activity", text=text)

    def push(self) -> None:
        with self.plock:
            chunk, self.pending = self.pending, ""
        if chunk:
            self.desk.stream_text += chunk
            emit("delta", id=self.sid, text=chunk)

    def _close(self, aborted: bool, tokens: int | None = None) -> None:
        if self.closed:
            return
        self.closed = True
        self.push()
        if getattr(self, "_draft_text", None):
            emit("activity", text=None)          # the call is written: its own row takes over from here
        if self.desk.live is self:
            self.desk.live = None
        V = voice.VOICE
        held = self.vo and not self.swallow and bool(self.full.strip())
        ended = []

        def reveal(_shown=None) -> None:
            """The words go on screen (with the voice when it is on), and only then is the answer closed."""
            if ended:
                return
            ended.append(1)
            if held:
                emit("delta", id=self.sid, text=self.full)
            emit("stream_end", id=self.sid, aborted=aborted, discarded=self.swallow,
                 tokens=int(tokens if tokens is not None else self.tokens), exact=tokens is not None,
                 secs=round(time.time() - self.t0, 2))
            self.desk.stream_text, self.desk.stream_id = "", None

        handed = False                          # the voice has the words and will show them
        if not self.swallow and self.full.strip() and (V.enabled or getattr(V, "story", False)) and not (held and aborted):
            try:                                # same speech as the CLI: <say> lines or the whole reply
                if hasattr(V, "present"):
                    V.present(self.full, reveal if held else (lambda _shown: None))
                    handed = held
                    getattr(V, "flush", lambda: None)()
                else:
                    V.handle(self.full)
            except Exception as e:
                log(f"voice: {e}")
                handed = False
        if not handed:
            reveal()                            # no voice for it (off, aborted, failed): the words go on screen now

    def abort(self) -> None:
        self._close(True)

    def finish(self, tokens: int | None = None) -> None:
        self._close(False, tokens)


# ====================================================================== ui.* display hooks
def _h_tool_header(console, name: str, args: dict) -> None:
    D = DESK
    if D.tool_running and D.cur_tool is not None:          # a sub-agent's call inside task / tasks
        child = {"label": convert.label(name), "target": convert.target(name, args)[:240]}
        D.cur_tool.setdefault("children", []).append(child)
        emit("tool_child", id=D.cur_tool["id"], child=child)
        return
    D.flush_quiet()
    it = convert.tool_item(name, args, D.tool_use_id(name, args) or nid("t"))
    if name in convert.DIFF_TOOLS:
        it["diff"] = convert.diff_for(name, args)
    D.cur_tool = it
    emit("item", item=it)


def _h_tool_result(console, name: str, out: str, dt: float | None = None) -> None:
    D = DESK
    it, D.cur_tool = D.cur_tool, None
    if it is None:
        D.flush_quiet()
        it = convert.tool_item(name, {}, nid("t"))
        emit("item", item=it)
    convert.finish_tool(it, out, convert.OUT_LIVE, dt)
    emit("tool_end", id=it["id"], patch={k: it[k] for k in ("status", "summary", "output", "secs", "images") if k in it})
    D.status_soon()


def _h_print_todos(console, todos) -> None:
    emit("todos", items=todos or [])
    DESK.status_soon()


def _h_denied(console, name: str, reason: str) -> None:
    DESK.add_item({"kind": "denied", "label": convert.label(name), "reason": str(reason)})


def _h_stopped(console, kept: int) -> None:
    """A stopped turn, the way Claude shows it: a quiet grey "Stopped" line, no card, no red icon."""
    DESK.stop_noted = True                     # cli.run swallows the interrupt: the turn must still end as stopped
    DESK.add_item({"kind": "note", "level": "stopped", "text": tr_("Stopped"), "detail": ui.stopped_detail(kept)})


def _h_replay(console, messages, updated=None, limit: int = 400) -> None:
    DESK.check_session()
    DESK.send_snapshot("resume")


DESKTOP_STYLE = """

# Where your replies are shown
You are running in the Emilie desktop app, a window like the Claude Code desktop app, not in a terminal. Your replies
are rendered as Markdown in a chat view with a proportional font. Write for that:
- Plain, well-formed Markdown: short paragraphs, `-` lists, **bold** only for the key point, ### headings only in long
  answers, fenced code blocks with a language tag, and real Markdown tables (| a | b |) when the data is tabular.
- Never draw with box-drawing or block characters (│ ─ ┌ ┐ └ ┘ ├ ═ ║ ⎿ █ ▸), never line up columns with spaces, never
  use ANSI colour codes, and never decorate lines with ❯ ● ✓ ✗ or ASCII art.
- Your tool calls (commands, reads, edits, searches) are already shown to the user as compact rows they can open, with
  the full output and the diff. Do not paste command output, file contents or diffs back into your text: say what
  matters and name the file as `path/to/file` in backticks.
- No terminal key hints (Ctrl+C, press Enter, scroll up): the user clicks in the window.
- Lead with the answer or the result, then only the details the user needs.
- browser_open(url) shows a web page in the Browser panel beside the conversation (use it after you start a dev server,
  or to show the user a page). It only shows the page: you cannot read or click it. To read, test or drive a page
  yourself use the browser MCP tools, or web_fetch for plain HTML."""


def desktop_system(base: str) -> str:
    """The CLI's system prompt, told that it is shown in a window (so the model stops writing for a terminal)."""
    base = base.replace("You are Emilie, a coding companion in the terminal.",
                        "You are Emilie, a coding companion in the Emilie desktop app.")
    return base if "Where your replies are shown" in base else base + DESKTOP_STYLE


def _has_tool_call(m: dict) -> bool:
    """An assistant message that asks for tools (Anthropic tool_use blocks or OpenAI tool_calls)."""
    if m.get("tool_calls"):
        return True
    c = m.get("content")
    return isinstance(c, list) and any(isinstance(p, dict) and p.get("type") == "tool_use" for p in c)


def _is_tool_result(m: dict) -> bool:
    if m.get("role") == "tool":
        return True
    c = m.get("content")
    return m.get("role") == "user" and isinstance(c, list) and any(isinstance(p, dict) and p.get("type") == "tool_result" for p in c)


def _full_extras() -> dict[str, str]:
    """Skills and custom commands for /help and the / menu with their whole description: the window wraps long
    text, while the terminal version cuts it at 60 characters to fit its autocomplete."""
    from .. import skills as skills_mod
    out = {f"/{n}": f"[skill] {s.description}" for n, s in skills_mod.SKILLS.items()}
    out.update({f"/{n}": f"[command] {c.description}" for n, c in skills_mod.COMMANDS.items()})
    return out


def install_hooks() -> None:
    from .. import skills as skills_mod
    skills_mod.extras = _full_extras
    # a /command that changes a setting (/logo size 40, /model, …) tells the window, so it follows at once
    save = eff.save_settings

    def save_and_tell(**kv) -> None:
        save(**kv)
        for k, v in kv.items():
            emit("settings", key=k, value=v)
    eff.save_settings = save_and_tell
    agent_mod.BASE_SYSTEM = desktop_system(agent_mod.BASE_SYSTEM)
    agent_mod.StreamView = DesktopStreamView
    ui.tool_header = _h_tool_header
    ui.tool_result = _h_tool_result
    ui.print_preview = lambda *a, **k: None          # the diff already travels with the tool item
    ui.print_todos = _h_print_todos
    ui.denied = _h_denied
    ui.stopped = _h_stopped
    ui.show_submission = lambda *a, **k: None        # the UI shows attachments itself
    ui.replay_history = _h_replay


class DesktopHooks:
    """The `hooks` the CLI core calls for things that depend on the interface (logo, scrolling, ...)."""

    def __init__(self, desk: "Desk"):
        self.desk = desk

    def _icon(self, mode: str, msg: str) -> str:
        eff.save_settings(desktop_icon=mode)
        emit("prefs", key="desktop_icon", value=mode)
        return msg

    def load_logo(self):
        emit("prefs", key="logo", value=eff.load_settings().get("logo"))
        return None

    def clear(self):
        self.desk.check_session()

    def set_fps(self, n):
        eff.save_settings(fps=int(n))
        return tr_('logo fps -> {0}', n)

    def set_still(self, still):
        return self._icon("image" if still else "video", "Emilie icon -> " + ("image" if still else "video"))

    def set_ascii(self, on):
        return self._icon("ascii" if on else "video", "Emilie icon -> " + ("ASCII (CLI)" if on else "video"))

    def set_sixel(self, on):
        return self._icon("pixel" if on else "video", "Emilie icon -> " + ("pixel" if on else "video"))

    def refresh_language(self):
        emit("prefs", key="ui_lang", value=i18n.current())

    def set_mouse(self, on):
        return "mouse settings apply to the terminal UI only"

    def set_scroll(self, **kw):
        return "scroll settings apply to the terminal UI only"

    def set_borders(self, on):
        return "animated borders apply to the terminal UI only"

    def history(self):
        self.desk.note("The whole conversation is shown here: scroll up to read it.", "muted")

    def show_banner(self):
        emit("show_logo")


# ====================================================================== the session
class Desk:
    """For the CLI core this is what the full-screen TUI is (console.tui)."""

    def __init__(self):
        self.core = self.agent = self.policy = None
        self.cwd = ""
        self.console = DesktopConsole(self)
        self.jobs: queue.Queue = queue.Queue()
        self.thread: threading.Thread | None = None
        self.busy = False
        self.stop_noted = False                # this turn was stopped (the "Stopped" note was shown)
        self.live = None                       # StreamView of the answer being written (TUI protocol)
        self.req: dict | None = None           # the question waiting for the user (permission / picker)
        self.lock = threading.RLock()
        self.cur_tool: dict | None = None
        self.tool_running = False
        self.stream_text, self.stream_id = "", None
        self.extras: list = []                 # [message count when shown, item]: what agent.messages does not keep
        self.aliases: dict = {}                # message index -> the /command the user typed for it
        self.title = ""
        self.known_sid = None
        self.turn_t0 = 0.0
        self.used_ids: set = set()
        self.snap_in_turn = False
        self._status_due = 0.0
        self._last_progress = 0.0
        self.cam = None
        self._last_chat = time.monotonic()
        self.last_input = time.monotonic()
        threading.Thread(target=self._ticker, daemon=True).start()

    # ------------------------------------------------------------ TUI protocol used by the CLI code
    def mark_running(self, running: bool) -> None:
        self.tool_running = running

    def ask_permission(self, name: str, args: dict, reason: str) -> str:
        if name == "exit_plan_mode":
            payload = {"kind": "plan", "plan": str(args.get("plan", ""))}
        else:
            payload = {"kind": "permission", "name": name, "label": convert.label(name),
                       "target": convert.target(name, args)[:2500], "reason": str(reason or ""),
                       "diff": convert.diff_for(name, args) if name in convert.DIFF_TOOLS else None,
                       "input": convert.clip_args(args), "can_always": not reason}
        res = self.request(payload)
        if res == "interrupt":
            raise KeyboardInterrupt
        if res not in ("y", "a", "t", "n"):
            res = "n"
        if res == "n":
            self.add_item({"kind": "denied", "label": "Plan" if name == "exit_plan_mode" else convert.label(name),
                           "target": "" if name == "exit_plan_mode" else payload.get("target", "")[:200],
                           "reason": "kept planning" if name == "exit_plan_mode" else "you denied it"})
        if res == "t":
            emit("prefs", key="mode", value="trust")
        self.status_soon()
        return res

    def choose(self, title: str, rows: list, idx: int = 0, hint: str | None = None, keys: tuple = ()):
        payload = {"kind": "choose", "title": str(title), "rows": [blocks.frags_html(r) for r in rows],
                   "plain": [blocks.frags_text(r) for r in rows], "idx": int(idx or 0), "hint": hint or "",
                   "keys": list(keys or ())}
        res = self.request(payload)
        if not isinstance(res, list) or len(res) != 2:
            return None
        try:
            return str(res[0]), int(res[1])
        except (TypeError, ValueError):
            return None

    def talk_toggle(self) -> str:
        return talk.TALK.toggle(self.submit_spoken, self.talk_busy, self.status_soon,
                                lambda m: self.note(str(m), "muted"))

    def talk_busy(self) -> bool:
        return self.busy or self.req is not None or voice.VOICE.speaking()

    def submit_spoken(self, text: str) -> None:
        self.last_input = time.monotonic()
        self.enqueue({"text": text, "cid": nid("v"), "spoken": True})

    # ------------------------------------------------------------ questions for the user
    def request(self, payload: dict):
        self.flush_quiet()
        rid = nid("r")
        ev = threading.Event()
        r = {"id": rid, "payload": payload, "ev": ev, "result": None}
        with self.lock:
            self.req = r
        emit("request", id=rid, request=payload)
        try:
            while not ev.wait(0.1):
                pass
        finally:
            with self.lock:
                if self.req is r:
                    self.req = None
            emit("request_done", id=rid)
        return r["result"]

    def answer(self, rid: str, value) -> None:
        with self.lock:
            r = self.req
            if r is not None and r["id"] == rid:
                r["result"] = value
                r["ev"].set()

    # ------------------------------------------------------------ quiet commands
    # A /command that does not call the model and answers with a line or two (/voice, /scroll, /language ...) is not
    # worth a place in the conversation: its short answer is shown as a popup and the typed command goes away. While one
    # runs, what it prints is held here; the moment the model starts (a stream, a tool, a question) or the answer turns out
    # long, everything is put in the conversation as usual.
    quiet: dict | None = None

    def flush_quiet(self) -> None:
        q, self.quiet = self.quiet, None
        if not q:
            return
        self.add_item(q["user"], keep=True)
        for it, keep in q["items"]:
            self.add_item(it, keep)

    def settle_quiet(self, cid: str) -> None:
        q, self.quiet = self.quiet, None
        if not q:
            return
        items = q["items"]
        small = (len(items) <= 3 and all(it.get("kind") == "note" or (it.get("kind") == "notice" and it.get("level") == "line")
                                         for it, _ in items)
                 and sum(len(str(it.get("text", ""))) for it, _ in items) <= 220)
        if not small:                                   # long or rich (a table, a panel): worth reading in the conversation
            self.add_item(q["user"], keep=True)
            for it, keep in items:
                self.add_item(it, keep)
            return
        emit("drop_user", cid=cid)
        for it, _ in items:
            text = str(it.get("text", "")).strip()
            if text:
                emit("toast", text=text[:220], level="error" if it.get("level") == "error" else "info")

    # ------------------------------------------------------------ printed output
    def on_print(self, objects: tuple, kw: dict) -> None:
        if not objects:
            return
        markup = kw.get("markup")
        markup = True if markup is None else bool(markup)
        if len(objects) == 1 and isinstance(objects[0], Text) and objects[0].plain.startswith("✿ "):
            # a remark she made on her own (video call): it is stored in agent.messages, so not kept as an extra
            self.add_item({"kind": "assistant", "text": objects[0].plain[2:].strip(), "spontaneous": True}, keep=False)
            return
        text = blocks.plain(objects, markup).strip()
        if self.tool_running and self.cur_tool is not None and text:
            child = {"label": "", "target": text[:240]}           # e.g. "sub-agent: ..." while a task runs
            self.cur_tool.setdefault("children", []).append(child)
            emit("tool_child", id=self.cur_tool["id"], child=child)
            return
        bl = blocks.printed(objects, markup)
        if not bl:
            return
        for b in bl:                                           # the terminal's "⎿" lead-in means nothing in the app
            if b.get("t") == "text" and isinstance(b.get("html"), str):
                b["html"] = re.sub(r"^((?:<[^>]+>|\s|&nbsp;)*)⎿\s?", r"\g<1>", b["html"])
        text = re.sub(r"^\s*⎿\s?", "", text)
        rich = any(b["t"] in ("panel", "table", "md", "rule", "pre") for b in bl)
        self.add_item({"kind": "notice", "blocks": bl, "level": "panel" if rich else "line", "text": text[:400]})

    def add_item(self, item: dict, keep: bool = True) -> None:
        item.setdefault("id", nid("x"))
        q = self.quiet
        if q is not None:
            if item.get("kind") in ("note", "notice"):
                q["items"].append((item, keep))
                return
            self.flush_quiet()                          # something that belongs in the conversation: the command was one too
        if keep:
            with self.lock:
                n = len(self.agent.messages) if self.agent else 0
                self.extras.append([n, item])
                if len(self.extras) > 300:
                    del self.extras[: len(self.extras) - 300]
        emit("item", item=item)

    def note(self, text: str, level: str = "muted") -> None:
        self.add_item({"kind": "note", "text": str(text), "level": level})

    # ------------------------------------------------------------ status
    def status(self) -> dict:
        a, p = self.agent, self.policy
        if a is None:
            return {}
        try:
            ctx, lim = a.ctx_tokens(), a.compact_limit()
        except Exception:
            ctx, lim = 0, 1
        try:
            parts = a.ctx_breakdown()                # the Context panel: what fills it, by kind
        except Exception as e:
            log(f"ctx_breakdown: {e}")
            parts = None
        from .. import config
        cps = []
        for n, ck in enumerate(reversed(a.checkpoints), 1):
            cps.append({"n": n, "label": getattr(ck, "label", ""), "mark": getattr(ck, "mark", None),
                        "files": [os.path.relpath(f) if f.startswith(self.cwd) else f for f in list(ck)[:6]],
                        "nfiles": len(ck), "at": getattr(ck, "at", 0)})
        return {"session_id": a.session_id, "cwd": self.cwd, "title": self.title or session._title(a.messages),
                "model": a.model, "active_model": a.active_model, "mode": p.mode, "effort": a.effort.name,
                "busy": self.busy, "queued": self.jobs.qsize(), "ctx_tokens": ctx, "ctx_limit": lim,
                "ctx_pct": min(999, ctx * 100 // max(1, lim)), "ctx_parts": parts, "messages": len(a.messages),
                "usage": {"in": a.usage.inp, "out": a.usage.out, "calls": a.usage.calls, "exact": a.usage.exact},
                "todos": a.todos, "checkpoints": cps, "talk": talk.TALK.state, "call": self.cam is not None,
                "voice": bool(voice.VOICE.enabled), "provider": config.PROVIDER_ID or config.PROVIDER,
                "salvaged": a.salvaged, "memory": [str(f) for f in a.memory_files],
                "request": self.req["payload"] | {"id": self.req["id"]} if self.req else None}

    def status_now(self) -> None:
        self._status_due = 0.0
        try:
            emit("status", status=self.status())
        except Exception as e:
            log(f"status: {e}")

    def status_soon(self, *_a) -> None:
        if not self._status_due:
            self._status_due = time.time() + 0.25

    def _ticker(self) -> None:
        while True:
            time.sleep(0.05)
            try:
                v = self.live
                if isinstance(v, DesktopStreamView):
                    v.push()
                    if time.time() - self._last_progress > 0.5:
                        self._last_progress = time.time()
                        emit("progress", tokens=int(v.tokens), secs=round(time.time() - v.t0, 1))
                if self._status_due and time.time() >= self._status_due:
                    self.status_now()
            except Exception as e:
                log(f"ticker: {e}")

    # ------------------------------------------------------------ transcript snapshot
    def tool_use_id(self, name: str, args: dict) -> str | None:
        """The model's id for the call now starting, so live items and snapshots agree."""
        for m in reversed(self.agent.messages[-3:]):
            if m.get("role") != "assistant":
                continue
            cands = []
            if isinstance(m.get("content"), list):
                cands += [(b.get("id"), b.get("name"), b.get("input")) for b in m["content"]
                          if isinstance(b, dict) and b.get("type") == "tool_use"]
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function") or {}
                try:
                    inp = json.loads(fn.get("arguments") or "{}")
                except ValueError:
                    inp = None
                cands.append((tc.get("id"), fn.get("name"), inp))
            for cid, n, inp in cands:
                if cid and n == name and cid not in self.used_ids and (inp is None or inp == args):
                    self.used_ids.add(cid)
                    return cid
            return None
        return None

    def snapshot(self) -> dict:
        a = self.agent
        with self.lock:
            msgs = list(a.messages)
            extras = sorted(self.extras, key=lambda e: e[0])
            aliases = dict(self.aliases)
        items = convert.items_from_messages(msgs, aliases, live=self.busy)
        out, ei = [], 0
        for it in items:
            while ei < len(extras) and extras[ei][0] <= it["mi"]:
                out.append(extras[ei][1])
                ei += 1
            out.append(it)
        out += [e[1] for e in extras[ei:]]
        if self.busy and self.stream_text:
            out.append({"kind": "assistant", "id": self.stream_id or "stream", "text": self.stream_text, "streaming": True})
        if self.busy:
            self.snap_in_turn = True
        return {"session_id": a.session_id, "items": out, "todos": a.todos, "busy": self.busy,
                "stream_id": self.stream_id if self.busy else None,
                "request": self.req["payload"] | {"id": self.req["id"]} if self.req else None}

    def send_snapshot(self, reason: str = "") -> None:
        emit("snapshot", reason=reason, snapshot=self.snapshot(), status=self.status())

    # ------------------------------------------------------------ per-session desktop data (title, commands typed)
    def _meta_path(self, sid: str):
        return META_DIR / f"{sid}.json"

    def load_meta(self) -> None:
        try:
            data = json.loads(self._meta_path(self.agent.session_id).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        self.title = str(data.get("title") or "")
        self.aliases = data.get("aliases") if isinstance(data.get("aliases"), dict) else {}
        self.extras = data.get("extras") if isinstance(data.get("extras"), list) else []
        seen: set = set()                        # saved by an older version: the same id twice (see nid)
        for e in self.extras:
            it = e[1] if isinstance(e, list) and len(e) == 2 and isinstance(e[1], dict) else None
            if it is not None:
                if not it.get("id") or it["id"] in seen:
                    it["id"] = nid("x")
                seen.add(it["id"])

    def has_meta(self, sid: str) -> bool:
        return self._meta_path(sid).is_file()

    def fork(self, mi) -> dict:
        """'Fork from here': a new session holding the conversation up to message `mi` (all of it when None), with the
        command outputs and titles shown before that point. The current session is left as it is."""
        a = self.agent
        with self.lock:
            msgs = list(a.messages)
            cut = len(msgs) if mi is None else max(1, min(len(msgs), int(mi) + 1))
            # never stop between a tool call and its result: the provider would refuse that history
            while cut < len(msgs) and (_has_tool_call(msgs[cut - 1]) or _is_tool_result(msgs[cut])):
                cut += 1
            extras = [e for e in self.extras if e[0] <= cut]
            aliases = {k: v for k, v in self.aliases.items() if str(k).isdigit() and int(k) < cut}
            title = self.title
        if not msgs[:cut]:
            raise ValueError("there is nothing to fork yet")
        sid = session.new_id()
        session.save(self.cwd, sid, msgs[:cut], a.model, time.time())
        new_title = f"{title} (fork)" if title else ""
        try:
            META_DIR.mkdir(parents=True, exist_ok=True)
            meta = {"title": new_title, "cwd": self.cwd, "aliases": aliases, "extras": extras}
            (META_DIR / f"{sid}.json").write_text(json.dumps(meta, ensure_ascii=False, default=str), encoding="utf-8")
        except OSError as e:
            log(f"fork meta: {e}")
        return {"sid": sid, "cwd": self.cwd, "title": new_title}

    def save_meta(self) -> None:
        a = self.agent
        if a is None or not (a.messages or self.extras):      # commands alone (/doctor) are kept too: see init
            return
        try:
            META_DIR.mkdir(parents=True, exist_ok=True)
            p = self._meta_path(a.session_id)
            tmp = p.with_suffix(".tmp")
            with self.lock:
                data = {"title": self.title, "cwd": self.cwd, "aliases": self.aliases, "extras": self.extras[-200:]}
            tmp.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")
            tmp.replace(p)
        except OSError as e:
            log(f"meta: {e}")

    def check_session(self) -> None:
        """The agent switched to another session (/clear, /resume): reset what belongs to the old one."""
        a = self.agent
        if a is None or a.session_id == self.known_sid:
            return
        old, self.known_sid = self.known_sid, a.session_id
        with self.lock:
            self.extras, self.aliases, self.title = [], {}, ""
        if a.messages:
            self.load_meta()
        emit("session_changed", old=old, new=a.session_id)

    def maybe_title(self) -> None:
        """A short title for the sidebar after the first answer (setting desktop_auto_title, on by default)."""
        a = self.agent
        if self.title or not eff.load_settings().get("desktop_auto_title", True):
            return
        users = [m for m in a.messages if a._is_plain_user(m)]
        if not users or len(users) > 3 or getattr(self, "_titling", False):
            return                                   # a title skipped during a rate limit is tried after the next answers
        c = users[0].get("content")
        raw = c if isinstance(c, str) else " ".join(p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") == "text")
        first = convert.clean_user_text(raw)[0][:600]
        if len(first.strip()) < 3:
            return
        sid = a.session_id

        def work():
            try:
                t = a._complete("You name chat sessions. Reply with ONLY a short title of 2 to 6 words, in the same "
                                "language as the user's message. No quotes, no emoji, no punctuation at the end.",
                                first, 1500)                   # reasoning models think a few hundred tokens first
                t = re.sub(r"<think>.*?(</think>|$)", "", t or "", flags=re.S)
                t = next((l.strip(" \"'*#`.") for l in t.splitlines() if l.strip(" \"'*#`.")), "")
                t = re.sub(r"^(title|judul)\s*:\s*", "", t, flags=re.I)
                if not t:
                    log("title: the model returned no title")
                if t and len(t) <= 80 and self.agent.session_id == sid and not self.title:
                    self.title = t[:60]
                    self.save_meta()
                    emit("title", session_id=sid, title=self.title)
            except Exception as e:                   # ratelimit.CoolingDown: skipped, the next answer tries again
                log(f"title: {e}")
            finally:
                self._titling = False
        self._titling = True
        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------ input
    def make_submission(self, cmd: dict) -> Submission | None:
        text = str(cmd.get("text") or "")
        raw = text
        pastes = {}
        for p in cmd.get("pastes") or []:
            try:
                pastes[int(p["n"])] = str(p["text"])
            except (KeyError, TypeError, ValueError):
                continue
        text = PH_TEXT.sub(lambda m: pastes.get(int(m.group(1)), m.group(0)), text)
        images, metas, refs = [], [], []
        for i, im in enumerate(cmd.get("images") or [], 1):
            try:
                data = base64.b64decode(im.get("b64") or "")
                from PIL import Image
                size = Image.open(io.BytesIO(data)).size
                enc = clip.encode_image(data)
            except Exception as e:
                log(f"image: {e}")
                continue
            path = clip.save_image(data)
            images.append(enc)
            metas.append((i, size, len(data)))
            refs.append(f"[Image #{i}: {path}]" if path else f"[Image #{i}]")
        files_txt = []
        for f in cmd.get("files") or []:
            f = str(f)
            try:
                size = os.path.getsize(f)
                if size <= 200_000 and os.path.splitext(f)[1].lower() not in (".pdf", ".docx", ".xlsx", ".pptx", ".zip",
                                                                               ".exe", ".png", ".jpg", ".jpeg", ".gif",
                                                                               ".webp", ".ipynb", ".mp4", ".mp3", ".wav"):
                    body = open(f, encoding="utf-8").read()
                    files_txt.append(f'<file path="{f}">\n{body}\n</file>')
                    continue
            except (OSError, UnicodeDecodeError):
                pass
            files_txt.append(f"[Attached file: {f}]")
        if refs:
            text = (text + "\n\n" + " ".join(refs)).strip()
        if files_txt:
            text = (text + "\n\n" + "\n\n".join(files_txt)).strip()
        if not text and not images:
            return None
        if self.cam is not None and raw.strip():
            try:
                images += self._call_attachment()
            except Exception as e:
                log(f"call clip: {e}")
        return Submission(text=text, raw=raw, images=images, pastes=sorted(pastes.items()), image_meta=metas)

    def enqueue(self, cmd: dict) -> None:
        sub = self.make_submission(cmd)
        if sub is None:
            return
        cid = str(cmd.get("cid") or nid("c"))
        self.last_input = time.monotonic()
        self.jobs.put((sub, cid, cmd))
        emit("queued", cid=cid, position=self.jobs.qsize(), busy=self.busy)

    def _loop(self) -> None:
        while True:
            try:
                job = self.jobs.get()
                if job is None:
                    return
                self._run_job(*job)
            except KeyboardInterrupt:              # a stop that arrived between two jobs
                self.busy = False
                continue
            except BaseException as e:             # never let the session die
                log("job crashed: " + traceback.format_exc())
                self.busy = False
                self.note(f"internal error: {type(e).__name__}: {e}", "error")

    def _run_job(self, sub: Submission, cid: str, cmd: dict) -> None:
        a = self.agent
        n0, sid0 = len(a.messages), a.session_id
        raw = sub.raw or sub.text
        is_cmd = raw.startswith(("/", "!", "# "))
        _clean, files, _c = convert.clean_user_text(sub.text)
        user_item = {"kind": "user", "cid": cid, "text": raw if is_cmd else _clean or raw, "files": files,
                     "images": [], "n_images": len(sub.images), "spoken": bool(cmd.get("spoken")), "command": None}
        if raw.startswith("/") and not files and not sub.images:
            user_item.setdefault("id", nid("x"))
            self.quiet = {"user": user_item, "items": []}          # held until we know whether it is a quiet command
        else:
            self.add_item(user_item, keep=is_cmd)
        self.busy, self.turn_t0, self.snap_in_turn = True, time.time(), False
        self.used_ids = set()
        try:
            voice.VOICE.warm()                  # the voice warms up while the model is still thinking
        except Exception:
            pass
        emit("turn_start", cid=cid)
        self.status_now()
        stopped = False
        self.stop_noted = False
        try:
            res = self.core.process(sub)
        except KeyboardInterrupt:
            stopped, res = True, None
            if not self.stop_noted:
                _h_stopped(None, getattr(a, "salvaged", 0))
        except BaseException as e:
            res = None
            log("process: " + traceback.format_exc())
            self.note(f"error: {type(e).__name__}: {e}", "error")
        finally:
            self.busy = False
            self.live, self.cur_tool, self.tool_running = None, None, False
            self.stream_text, self.stream_id = "", None
            self.settle_quiet(cid)
        if a.session_id == sid0:
            if raw.startswith("/"):                # a /command that became a prompt: show what was typed, not the prompt
                for i in range(n0, len(a.messages)):
                    if a._is_plain_user(a.messages[i]):
                        self.aliases[str(i)] = raw
                        break
            if len(a.messages) < n0:               # /rewind or /compact moved the history: drop notes past its end
                with self.lock:
                    self.extras = [e for e in self.extras if e[0] <= len(a.messages)]
            else:
                # a turn that was removed from history (stopped before anything was done) leaves notes that point past
                # the end; pinned to the end they keep their place, instead of sorting after later notes on reopening
                n = len(a.messages)
                with self.lock:
                    for e in self.extras:
                        if isinstance(e, list) and e and isinstance(e[0], int) and e[0] > n:
                            e[0] = n
        self.check_session()
        if self.snap_in_turn:
            self.send_snapshot("turn")
        emit("turn_end", cid=cid, secs=round(time.time() - self.turn_t0, 1), stopped=stopped or self.stop_noted)
        self.save_meta()
        self.status_now()
        self._last_chat = time.monotonic()
        self.maybe_title()
        if res == "exit":
            emit("exit")

    def stop(self) -> None:
        voice.VOICE.stop()
        dropped = []
        try:
            while True:
                job = self.jobs.get_nowait()
                if job is not None:
                    dropped.append(job[1])
        except queue.Empty:
            pass
        if dropped:
            emit("unqueued", cids=dropped)
        with self.lock:
            r = self.req
        if r is not None:
            r["result"] = "interrupt"
            r["ev"].set()
            return
        if self.busy and self.thread is not None and self.thread.is_alive():
            ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(self.thread.ident),
                                                       ctypes.py_object(KeyboardInterrupt))

    # ------------------------------------------------------------ video call (same behaviour as Alt+V in the TUI)
    def call(self, on: bool) -> None:
        from .. import camera
        if on and self.cam is None:
            cam = camera.Stream()
            err = cam.start()
            if err:
                self.note(f"camera: {err}", "error")
                return
            try:
                cam.open_viewer()
            except Exception as e:
                log(f"viewer: {e}")
            self.cam = cam
            self._last_chat = time.monotonic()
            self.agent.call_begin()
            threading.Thread(target=self._companion_loop, args=(cam,), daemon=True).start()
            self.note("Video call on: Emilie can see you, and your messages include the last seconds of video.", "muted")
        elif not on and self.cam is not None:
            self.end_call("user")
        self.status_now()

    def end_call(self, reason: str) -> None:
        cam, self.cam = self.cam, None
        if cam is None:
            return
        try:
            cam.stop()
        except Exception:
            pass
        if reason != "exit":
            self.note("Video call ended", "muted")
        threading.Thread(target=lambda: self.agent.call_end(reason, farewell=reason != "exit"), daemon=True).start()

    def _call_attachment(self) -> list:
        cam = self.cam
        if cam is None or cam.error:
            return []
        from .. import config
        if config.PROVIDER == "openai":
            data = cam.clip_mp4()
            if data:
                return [("video/mp4", base64.b64encode(data).decode())]
        jpg = cam.jpeg()
        return [clip.encode_image(jpg)] if jpg else []

    def _companion_loop(self, cam) -> None:
        import random
        time.sleep(4)
        first, fails, nxt = True, 0, 0.0
        while self.cam is cam and not cam.error:
            time.sleep(1)
            if getattr(cam, "viewer_closed", False):
                self.end_call("window")
                self.status_now()
                return
            cfg = eff.load_settings()
            if cfg.get("companion", True) is False:
                continue
            try:
                every = max(15, min(600, int(cfg.get("companion_secs", 45))))
            except (TypeError, ValueError):
                every = 45
            every = max(8, every * self.agent.pace())
            now = time.monotonic()
            if not first and now < max(nxt, self._last_chat + every):
                continue
            if self.busy or self.req is not None or not self.jobs.empty() or voice.VOICE.speaking():
                continue
            if talk.TALK.state in ("hearing", "transcribing") or now - self.last_input < 6:
                continue
            try:
                imgs = self._call_attachment()
                spoke = self.agent.glance(imgs, first=first) if imgs and self.cam is cam else False
                fails, first = 0, False
            except Exception as e:
                fails += 1
                if fails >= 3 or type(e).__name__ == "QuotaExhausted":
                    self.note(f"video call: she stops starting the conversation ({str(e)[:100] or type(e).__name__})")
                    return
                nxt = time.monotonic() + 10
                continue
            self._last_chat = time.monotonic()
            nxt = self._last_chat + every * random.uniform(0.8, 1.3) if spoke else self._last_chat + every * 0.6
            if spoke:
                self.status_soon()

    # ------------------------------------------------------------ commands from the hub
    def commands(self) -> list[dict]:
        from . import desktop_commands
        out = desktop_commands(COMMANDS, tr_)
        for c, d in EXTRA_COMMANDS.items():
            kind = "skill" if d.startswith("[skill]") else "command"
            out.append({"name": c, "desc": d.split("] ", 1)[-1], "kind": kind})
        return out

    def init(self, cmd: dict) -> None:
        cwd = os.path.expanduser(str(cmd.get("cwd") or "~"))
        os.makedirs(cwd, exist_ok=True)
        os.chdir(cwd)
        self.cwd = os.getcwd()
        argv = {"trust": ["--trust"], "plan": ["--plan"]}.get(str(cmd.get("mode") or ""), [])
        self.core = cli.make_core(self.console, argv, DesktopHooks(self))
        self.agent, self.policy = self.core.agent, self.core.policy
        if cmd.get("model"):
            self.agent.model = str(cmd["model"])
        if cmd.get("effort") in eff.LEVELS:
            self.agent.set_effort(eff.LEVELS[cmd["effort"]])
        rid = cmd.get("resume")
        if rid:
            data = session.load(self.cwd, str(rid))
            if data:
                self.agent.resume(data)
                self.load_meta()
            elif self.has_meta(str(rid)):
                # only commands so far (/doctor, /cost ...): there is no conversation to load, but it is the same
                # session: keep its id and what the commands printed (Restart after a provider change lands here)
                self.agent.session_id = str(rid)
                self.load_meta()
            else:
                self.note(f"could not open the saved session {rid}", "error")
        self.known_sid = self.agent.session_id
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        emit("ready", session_id=self.agent.session_id, cwd=self.cwd, status=self.status(),
             commands=self.commands(), snapshot=self.snapshot())

    def handle(self, cmd: dict) -> None:
        c, rid = cmd.get("cmd"), cmd.get("rid")

        def reply(data=None, error=None):
            if rid is not None:
                emit("reply", rid=rid, data=data, error=error)
        if c == "init":
            self.init(cmd)
            return reply(True)
        if self.agent is None:
            return reply(error="not initialised")
        if c == "send":
            self.enqueue(cmd)
        elif c == "stop":
            self.stop()
        elif c == "answer":
            self.answer(str(cmd.get("id")), cmd.get("value"))
        elif c == "set":
            if cmd.get("mode") in MODES:
                self.policy.mode = cmd["mode"]
            if cmd.get("model"):
                self.agent.model = str(cmd["model"])
                eff.save_settings(model=self.agent.model)
            if cmd.get("effort") in eff.LEVELS:
                self.agent.set_effort(eff.LEVELS[cmd["effort"]])
                eff.save_settings(effort=cmd["effort"])
            if "title" in cmd:
                self.title = str(cmd.get("title") or "").strip()[:80]
                self.save_meta()
                emit("title", session_id=self.agent.session_id, title=self.title)
            self.status_now()
        elif c == "settings_changed":
            key = cmd.get("key")
            if key == "effort":
                self.agent.set_effort(eff.load_effort())
            elif key == "ui_lang":
                i18n.set_lang(str(eff.load_settings().get("ui_lang", "en")), save=False)
            self.status_soon()
        elif c == "snapshot":
            return reply(self.snapshot())
        elif c == "status":
            return reply(self.status())
        elif c == "commands":
            return reply(self.commands())
        elif c == "call":
            self.call(bool(cmd.get("on")))
        elif c == "talk":
            want = bool(cmd.get("on"))
            if want != talk.TALK.on:
                self.note(self.talk_toggle(), "muted")
            self.status_now()
        elif c == "voice_test":
            voice.VOICE.speak(str(cmd.get("text") or "Hello, this is Emilie."))
        elif c == "fork":
            try:
                return reply(self.fork(cmd.get("mi")))
            except Exception as e:  # noqa: BLE001 - shown to the user as the reason
                return reply(error=f"could not fork: {e}")
        elif c == "typing":
            self.last_input = time.monotonic()
        elif c == "mcp":
            from .. import mcp
            if cmd.get("reconnect"):
                mcp.reconnect(str(cmd["reconnect"]), self.cwd)
                time.sleep(1.5)
            elif cmd.get("reload"):
                mcp.start_all(self.cwd)
                time.sleep(1.5)
            return reply([{"name": s.name, "status": s.status, "error": s.error, "tools": list(s.tool_names),
                           "command": s.command, "args": [str(x) for x in s.args], "url": s.url}
                          for s in mcp.SERVERS.values()])
        elif c == "skills":
            from .. import inputbox, skills
            if cmd.get("reload"):
                skills.load(self.cwd)
                inputbox.EXTRA_COMMANDS.clear()
                inputbox.EXTRA_COMMANDS.update(skills.extras())
                emit("commands", commands=self.commands())
            items = []
            for n, s in skills.SKILLS.items():
                res = skills.resources(s)
                items.append({"name": n, "description": s.description, "phase": s.phase,
                              "phase_label": skills.phase_label(s.phase) if s.phase else "", "source": s.source,
                              "path": str(s.path), "kind": "skill",
                              "refs": len(res.get("references", [])), "scripts": len(res.get("scripts", []))})
            for n, cm in skills.COMMANDS.items():
                items.append({"name": n, "description": cm.description, "source": cm.source, "kind": "command",
                              "path": str(getattr(cm, "path", "")), "phase": "", "phase_label": ""})
            return reply({"items": items, "skipped": list(skills.SKIPPED),
                          "phases": [{"id": p, "label": skills.phase_label(p)} for p, _ in skills.PHASES]})
        elif c == "export":
            from .. import export
            p, msg = export.save(self.agent.messages, str(cmd.get("target") or ""), self.agent.model, self.cwd)
            return reply({"path": str(p) if p else None, "message": msg})
        elif c == "shutdown":
            self.shutdown()
            reply(True)
            os._exit(0)
        else:
            return reply(error=f"unknown command {c}")
        return reply(True)

    def shutdown(self) -> None:
        try:
            if self.cam is not None:
                self.end_call("exit")
            talk.TALK.stop()
            voice.VOICE.stop()
            self.save_meta()
            from .. import mcp, tools
            mcp.stop_all()
            getattr(tools, "_bg_kill_all", lambda: None)()
        except Exception as e:
            log(f"shutdown: {e}")


def _browser_open(url: str) -> str:
    """Tool: show an address in the desktop's Browser panel (the user sees it; the agent cannot read it)."""
    u = (url or "").strip()
    if not u:
        return "ERROR: give an address"
    if re.match(r"^[a-z][a-z0-9+.-]*:(?!//|\d)", u, re.I):          # javascript:, data:, mailto: ...
        return "ERROR: only http and https addresses can be opened"
    if not re.match(r"^[a-z][a-z0-9+.-]*://", u, re.I):
        u = ("http://" if re.match(r"^(localhost|127\.|\[::1\]|\d+\.\d+\.\d+\.\d+)", u, re.I) else "https://") + u
    p = urlparse(u)
    if p.scheme not in ("http", "https") or not p.netloc:
        return "ERROR: only http and https addresses can be opened"
    emit("browser", url=u)
    return (f"Opened {u} in the Browser panel next to the conversation; the user can see it. You cannot read or click "
            "that panel: use the browser MCP tools for that.")


def main() -> None:
    global DESK
    DESK = Desk()
    install_hooks()
    tools.register("browser_open", _browser_open, tools._schema(
        "browser_open", "Show a web page in the desktop app's Browser panel, beside the conversation (e.g. the dev server "
                        "you just started). It only displays the page for the user.", {"url": tools._s}, ["url"]), "web")
    emit("warm", pid=os.getpid())
    while True:
        line = _IN.readline()
        if not line:                              # the hub closed the pipe: it is gone
            break
        try:
            cmd = json.loads(line)
        except ValueError:
            continue
        try:
            DESK.handle(cmd)
        except Exception as e:
            log("command failed: " + traceback.format_exc())
            if isinstance(cmd, dict) and cmd.get("rid") is not None:
                emit("reply", rid=cmd["rid"], data=None, error=f"{type(e).__name__}: {e}")
            else:
                emit("error", message=f"{type(e).__name__}: {e}")
    if DESK.agent is not None:
        DESK.shutdown()
    os._exit(0)


if __name__ == "__main__":
    main()
