"""Minimal MCP (Model Context Protocol) client: local programs over stdio, and remote servers over HTTP.

Configuration (Claude-compatible format): ./.mcp.json or ~/.emilie/mcp.json
  {"mcpServers": {
      "browser": {"command": "npx", "args": ["-y", "server"], "env": {"KEY": "v"}},
      "remote":  {"url": "https://example.com/mcp", "headers": {"Authorization": "Bearer ${MY_TOKEN}"}}}}
`${NAME}` in a header is replaced by that environment variable, so a token need not be written into the file.
Remote servers use the Streamable HTTP transport (answers as JSON or as an event stream). Servers that need an
OAuth login in the browser are not supported: use one that accepts a token header.
Servers run in the background; their tools are registered as mcp__<server>__<tool> and ALWAYS
ask for permission before use (the effect is unknown), unless 'always' was chosen.
"""
from . import paths
import atexit
import json
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from .i18n import t as tr_
from . import tools
from .effort import load_settings

PROTOCOL = "2024-11-05"            # stdio
HTTP_PROTOCOL = "2025-03-26"       # Streamable HTTP


def _expand(value: str) -> str:
    """${NAME} -> the environment variable NAME ('' if unset)."""
    return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", lambda m: os.environ.get(m.group(1), ""), str(value))


def _sse_message(resp, want_id) -> dict | None:
    """Read a text/event-stream body until the JSON-RPC response with id `want_id` has arrived."""
    data: list[str] = []
    for raw in resp:
        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        if line.startswith("data:"):
            data.append(line[5:].lstrip())
        elif line == "" and data:
            try:
                msg = json.loads("\n".join(data))
            except ValueError:
                msg = None
            data = []
            if isinstance(msg, dict) and msg.get("id") == want_id and "method" not in msg:
                return msg
    if data:
        try:
            msg = json.loads("\n".join(data))
            if isinstance(msg, dict) and msg.get("id") == want_id:
                return msg
        except ValueError:
            pass
    return None


@dataclass
class Server:
    name: str
    command: str = ""
    args: list = field(default_factory=list)
    env: dict = field(default_factory=dict)
    url: str = ""                     # set for a remote server (Streamable HTTP); then command is unused
    headers: dict = field(default_factory=dict)
    status: str = "starting"          # starting | ready | failed
    error: str = ""
    tool_names: list = field(default_factory=list)
    proc: subprocess.Popen | None = None
    session_id: str | None = None
    _id: int = 0
    _pending: dict = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    # ---------------------------------------------------------------- HTTP transport
    def _http(self, obj: dict, timeout: float) -> dict | None:
        """POST one JSON-RPC message. Returns the response message, or None for a notification (HTTP 202)."""
        import urllib.error
        import urllib.request
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   "MCP-Protocol-Version": HTTP_PROTOCOL, **{k: _expand(v) for k, v in self.headers.items()}}
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        req = urllib.request.Request(self.url, data=json.dumps(obj).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                self.session_id = r.headers.get("Mcp-Session-Id") or self.session_id
                if r.status == 202 or "id" not in obj:
                    return None
                if "text/event-stream" in r.headers.get("Content-Type", ""):
                    return _sse_message(r, obj["id"]) or {"error": {"message": "the server closed the stream without an answer"}}
                body = r.read()
                return json.loads(body) if body.strip() else {"result": {}}
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise RuntimeError(f"HTTP {e.code}: the server wants authorization. Add a header in mcp.json, e.g. "
                                   '"headers": {"Authorization": "Bearer ${MY_TOKEN}"} and set that variable') from None
            raise RuntimeError(f"HTTP {e.code} from {self.url}") from None
        except urllib.error.URLError as e:
            raise RuntimeError(f"cannot reach {self.url}: {e.reason}") from None

    # ---------------------------------------------------------------- transport
    def _send(self, obj: dict) -> None:
        assert self.proc and self.proc.stdin
        self.proc.stdin.write((json.dumps(obj) + "\n").encode())
        self.proc.stdin.flush()

    def _reader(self) -> None:
        assert self.proc and self.proc.stdout
        for line in self.proc.stdout:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            mid = msg.get("id")
            if mid is not None and "method" not in msg:            # respons
                with self._lock:
                    slot = self._pending.get(mid)
                if slot:
                    slot["msg"] = msg
                    slot["ev"].set()
            elif "method" in msg and mid is not None:              # request from the server: not supported
                self._send({"jsonrpc": "2.0", "id": mid,
                            "error": {"code": -32601, "message": tr_('not supported by this client')}})
        # the process ended: wake up everything that is waiting
        with self._lock:
            for slot in self._pending.values():
                slot.setdefault("msg", {"error": {"message": tr_('server exited')}})
                slot["ev"].set()

    def request(self, method: str, params: dict | None = None, timeout: float = 30.0) -> dict:
        if self.url:
            with self._lock:
                self._id += 1
                mid = self._id
            msg = self._http({"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}}, timeout) or {}
            if "error" in msg:
                raise RuntimeError(msg["error"].get("message", str(msg["error"])))
            return msg.get("result", {})
        with self._lock:
            self._id += 1
            mid = self._id
            slot = {"ev": threading.Event()}
            self._pending[mid] = slot
        self._send({"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}})
        end = time.time() + timeout
        try:
            while not slot["ev"].wait(0.2):                       # short polling: Ctrl+C can get in
                if time.time() > end:
                    raise TimeoutError(tr_('{0}: {method} timed out', self.name, method=method))
        finally:
            with self._lock:
                self._pending.pop(mid, None)
        msg = slot["msg"]
        if "error" in msg:
            raise RuntimeError(msg["error"].get("message", str(msg["error"])))
        return msg.get("result", {})

    # ---------------------------------------------------------------- siklus hidup
    def start(self) -> None:
        if self.url:
            try:
                self.request("initialize", {"protocolVersion": HTTP_PROTOCOL, "capabilities": {},
                                            "clientInfo": {"name": "emilie", "version": "0.1.0"}}, timeout=20)
                self._http({"jsonrpc": "2.0", "method": "notifications/initialized"}, 20)
                for t in self.request("tools/list", timeout=20).get("tools", []):
                    self._register(t)
                self.status = "ready"
            except Exception as e:  # noqa: BLE001
                self.status, self.error = "failed", f"{type(e).__name__}: {e}"
                self.stop()
            return
        try:
            env = {**os.environ, **{k: str(v) for k, v in self.env.items()}}
            cmd = [self.command, *map(str, self.args)]
            if os.name == "nt":
                # npx / npm / uvx are .cmd shims on Windows: resolve them (Popen without a shell does not find them)
                cmd[0] = shutil.which(self.command, path=env.get("PATH")) or self.command
                extra = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
            else:
                extra = {"start_new_session": True}
            self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.DEVNULL, env=env, **extra)
            threading.Thread(target=self._reader, daemon=True).start()
            self.request("initialize", {"protocolVersion": PROTOCOL, "capabilities": {},
                                        "clientInfo": {"name": "emilie", "version": "0.1.0"}}, timeout=20)
            self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            listed = self.request("tools/list", timeout=20).get("tools", [])
            for t in listed:
                self._register(t)
            self.status = "ready"
        except Exception as e:  # noqa: BLE001
            self.status, self.error = "failed", f"{type(e).__name__}: {e}"
            self.stop()

    def _register(self, t: dict) -> None:
        safe = lambda s: re.sub(r"[^A-Za-z0-9_-]", "_", s)
        fname = f"mcp__{safe(self.name)}__{safe(t['name'])}"[:64]
        schema = t.get("inputSchema") or {"type": "object", "properties": {}}
        tools.register(fname, self._make_call(t["name"]), {
            "name": fname, "description": f"[MCP {self.name}] {t.get('description', '')}"[:900],
            "input_schema": schema}, "mcp")
        self.tool_names.append(fname)

    def _make_call(self, tool_name: str):
        def fix_refs(o):
            # Playwright MCP wants "e34", but snapshots show "[ref=e34]" and models copy the prefix
            if isinstance(o, dict):
                return {k: (v[4:] if k in ("target", "ref") and isinstance(v, str) and v.startswith("ref=")
                            else fix_refs(v)) for k, v in o.items()}
            if isinstance(o, list):
                return [fix_refs(v) for v in o]
            return o

        def call(**args):
            args = fix_refs(args)
            res = self.request("tools/call", {"name": tool_name, "arguments": args}, timeout=120)
            parts = []
            for c in res.get("content", []):
                kind = c.get("type")
                if kind == "text":
                    parts.append(c.get("text", ""))
                elif kind == "image" and c.get("data"):
                    # a screenshot or picture: keep it (the model sees it next, the app shows it) instead of dropping it
                    saved = _save_image(self.name, c["data"], c.get("mimeType") or "image/png")
                    parts.append(f"[image saved: {saved}]" if saved else "[image]")
                else:
                    parts.append(f"[{kind or 'data'}]")
            out = "\n".join(p for p in parts if p) or "(empty)"
            return ("ERROR: " + out) if res.get("isError") else out
        return call

    def stop(self) -> None:
        for n in self.tool_names:
            tools.unregister(n)
        self.tool_names.clear()
        if self.proc and self.proc.poll() is None:
            if os.name == "nt":      # kill the whole tree (npx starts node as a child)
                try:
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)], capture_output=True, timeout=10)
                except Exception:
                    self.proc.kill()
                return
            try:
                os.killpg(self.proc.pid, 9)
            except (ProcessLookupError, PermissionError):
                self.proc.kill()


SERVERS: dict[str, Server] = {}

# How each server's tools reach the model (the "mcp_modes" setting, {server: mode}):
#   always    - every tool definition is sent with every request
#   on_demand - (default) only the server's name is listed; the load_mcp tool adds its tools to the conversation
#   off       - the server is not started at all
MODES = ("always", "on_demand", "off")


def mode_of(name: str) -> str:
    m = (load_settings().get("mcp_modes") or {}).get(name)
    return m if m in MODES else "on_demand"


def server_of(tool_name: str) -> str | None:
    return next((s.name for s in list(SERVERS.values()) if tool_name in s.tool_names), None)


def visible(schemas: list[dict], loaded: set[str]) -> list[dict]:
    """The tool definitions to send: an on-demand server's tools only once it is loaded."""
    servers = list(SERVERS.values())
    hidden = {t for s in servers if s.name not in loaded and mode_of(s.name) != "always" for t in s.tool_names}
    if not any(s.status != "off" and mode_of(s.name) == "on_demand" for s in servers):
        hidden.add("load_mcp")                                   # nothing to load: do not offer the tool
    return [x for x in schemas if x["name"] not in hidden]


def apply_modes(cwd: str) -> None:
    """After the setting changed: stop the servers that are now off, start the ones that are on again."""
    for name, s in list(SERVERS.items()):
        off = mode_of(name) == "off"
        if off and s.status != "off":
            s.stop()
            s.status, s.error = "off", ""
        elif not off and s.status == "off":
            reconnect(name, cwd)

_IMG_EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/webp": ".webp", "image/gif": ".gif"}


def _save_image(server: str, data_b64: str, mime: str) -> str | None:
    """An image an MCP tool returned (e.g. a browser screenshot): saved in ~/.emilie/images and queued so the model
    SEES it after this round of tool calls (like read_file on a picture). Returns the file path, or None."""
    import base64
    try:
        raw = base64.b64decode(data_b64)
        paths.IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9_-]", "_", server)[:24]
        p = paths.IMAGES_DIR / f"{safe}-{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 1000000:06d}{_IMG_EXT.get(mime.lower(), '.png')}"
        p.write_bytes(raw)
    except Exception:  # noqa: BLE001 - a broken image must not break the tool call
        return None
    tools.PENDING_IMAGES.append(str(p))
    return str(p)


# What each well-known server is for, so the model knows when to reach for it (used by inventory()).
PURPOSE = {
    "browser": "a real web browser: open pages, click, type, fill forms, upload files, take screenshots",
    "playwright": "a real web browser: open pages, click, type, fill forms, upload files, take screenshots",
    "chrome-devtools": "debug a web page in Chrome: console errors, network requests, performance traces, screenshots",
    "context7": "up-to-date documentation and code examples for libraries and frameworks",
    "thinking": "step-by-step reasoning for hard problems and plans",
    "memory": "long-term memory (a knowledge graph of facts and preferences)",
    "deepwiki": "documentation and answers about any public GitHub repository",
    "github": "GitHub: repositories, issues, pull requests, code search",
}


def wait_ready(timeout: float = 30.0) -> list[str]:
    """Wait up to `timeout` seconds for servers that are still starting. Returns the names still starting."""
    end = time.time() + timeout
    while time.time() < end:
        if not any(s.status == "starting" for s in SERVERS.values()):
            return []
        time.sleep(0.25)
    return [s.name for s in SERVERS.values() if s.status == "starting"]


def inventory() -> str:
    """For the system prompt, every request: the MCP servers connected right now, so the model knows what it can do (it
    once told the user it had no browser while the browser server was connected). An on-demand server gets one line
    that does not change when it is loaded, so the cached start of the request stays the same."""
    active = [s for s in list(SERVERS.values()) if s.status != "off"]
    if not active:
        return ""
    lines = ["", "", "# MCP servers connected right now",
             "Check this list before telling the user you cannot do something (open or test a web page, take a "
             "screenshot, look up docs, remember things). For a server marked 'on demand', first call load_mcp with "
             "its name: its tools (mcp__<server>__<tool>) are then in your tool list. Load only what the task needs."]
    for s in active:
        purpose = PURPOSE.get(s.name.lower(), "")
        head = f"- {s.name}" + (f" ({purpose})" if purpose else "")
        if s.status == "failed":
            lines.append(f"{head}: failed to start ({(s.error or 'unknown error')[:140]}). If the user needs it, say so.")
        elif mode_of(s.name) == "on_demand":
            if not purpose and s.tool_names:                     # an unknown server: a few tool names say what it does
                head += " (tools such as " + ", ".join(t.split("__")[-1] for t in s.tool_names[:4]) + ")"
            lines.append(f"{head}: on demand")
        elif s.status == "ready" and s.tool_names:
            names = ", ".join(s.tool_names[:12]) + (f" … ({len(s.tool_names)} tools in all)" if len(s.tool_names) > 12 else "")
            lines.append(f"{head}: {names}")
        elif s.status == "starting":
            lines.append(f"{head}: still starting, its tools appear in a moment. Do not tell the user it is missing.")
    return "\n".join(lines)


def _configs(cwd: str) -> dict[str, dict]:
    from . import plugins
    out: dict[str, dict] = dict(plugins.mcp_configs())          # plugins first: your own mcp.json wins on a clash
    for f in (paths.HOME_DIR / "mcp.json", Path(cwd) / ".mcp.json"):
        try:
            data = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        out.update(data.get("mcpServers") or data.get("servers") or {})
    return out


def start_all(cwd: str) -> None:
    """Start all servers from the configuration in the background (does not hold up startup)."""
    stop_all()
    for name, cfg in _configs(cwd).items():
        if cfg.get("url") and not cfg.get("command"):
            srv = Server(name, url=str(cfg["url"]), headers=cfg.get("headers") or {})
            if str(cfg.get("type", "")).lower() == "sse":          # the older two-endpoint transport
                srv.status, srv.error = "failed", "the old SSE transport is not supported: use a Streamable HTTP url"
                SERVERS[name] = srv
                continue
        elif cfg.get("command"):
            srv = Server(name, cfg["command"], cfg.get("args", []), cfg.get("env", {}))
        else:
            continue
        SERVERS[name] = srv
        _launch(srv)


def _launch(srv: Server) -> None:
    if mode_of(srv.name) == "off":
        srv.status = "off"
        return
    threading.Thread(target=srv.start, daemon=True).start()


def reconnect(name: str, cwd: str) -> bool:
    """Stop one server and start it again from the configuration (the rest stay as they are). False: not configured."""
    cfg = _configs(cwd).get(name)
    old = SERVERS.pop(name, None)
    if old:
        old.stop()
    if not cfg:
        return False
    if cfg.get("url") and not cfg.get("command"):
        srv = Server(name, url=str(cfg["url"]), headers=cfg.get("headers") or {})
    elif cfg.get("command"):
        srv = Server(name, cfg["command"], cfg.get("args", []), cfg.get("env", {}))
    else:
        return False
    SERVERS[name] = srv
    _launch(srv)
    return True


def stop_all() -> None:
    for s in list(SERVERS.values()):
        s.stop()
    SERVERS.clear()


atexit.register(stop_all)


def summary() -> str:
    if not SERVERS:
        return "none"
    n_tools = sum(len(s.tool_names) for s in SERVERS.values())
    st = ", ".join(f"{s.name}:{s.status}" for s in SERVERS.values())
    return tr_('{0} server(s), {n_tools} tools  ({st})', len(SERVERS), n_tools=n_tools, st=st)
