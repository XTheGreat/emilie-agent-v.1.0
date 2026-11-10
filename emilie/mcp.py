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
                parts.append(c.get("text", "") if c.get("type") == "text" else f"[{c.get('type', 'data')}]")
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


def _configs(cwd: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
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
        threading.Thread(target=srv.start, daemon=True).start()


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
