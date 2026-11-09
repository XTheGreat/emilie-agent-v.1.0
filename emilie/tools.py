"""Tool definitions (schema) and implementation."""
import os
import re
import signal
import subprocess
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

# reset by /effort (see Agent.set_effort)
LIMITS = {"out": 20_000, "read_lines": 2000}
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache",
             ".pytest_cache", "dist", "build", ".next", ".cache"}


def _clip(s: str) -> str:
    n = LIMITS["out"]
    return s if len(s) <= n else s[:n] + f"\n...[truncated, {len(s)} chars total]"


def _skipped(p: Path) -> bool:
    return any(part in SKIP_DIRS for part in p.parts)


# ------------------------------------------------------------------ file
def read_file(path: str, offset: int = 1, limit: int = 0) -> str:
    lines = Path(path).expanduser().read_text(errors="replace").splitlines()
    total = len(lines)
    offset = max(1, int(offset or 1))
    limit = min(int(limit or LIMITS["read_lines"]), LIMITS["read_lines"])
    chunk = lines[offset - 1: offset - 1 + limit]
    body = _clip("\n".join(f"{i:>5}\t{l}" for i, l in enumerate(chunk, offset)))
    if offset > 1 or offset - 1 + len(chunk) < total:
        body += (f"\n...[lines {offset}-{offset + len(chunk) - 1} of {total}; "
                 f"use offset/limit for other parts]")
    return body


def write_file(path: str, content: str) -> str:
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return f"Wrote {len(content)} chars to {p}"


def edit_file(path: str, old_string: str, new_string: str) -> str:
    p = Path(path).expanduser()
    text = p.read_text()
    n = text.count(old_string)
    if n == 0:
        return "ERROR: old_string not found"
    if n > 1:
        return f"ERROR: old_string appears {n} times, give more unique context"
    p.write_text(text.replace(old_string, new_string))
    return f"Edited {p}"


# ------------------------------------------------------------------ cari
def grep(pattern: str, path: str = ".") -> str:
    try:
        rx = re.compile(pattern)
    except re.error as e:
        return f"ERROR: invalid regex: {e}"
    hits = []
    root = Path(path).expanduser()
    files = [root] if root.is_file() else root.rglob("*")
    for f in files:
        if not f.is_file() or _skipped(f) or any(x.startswith(".") and x not in {".", ".."} for x in f.parts):
            continue
        try:
            for i, line in enumerate(f.read_text().splitlines(), 1):
                if rx.search(line):
                    hits.append(f"{f}:{i}: {line.strip()[:200]}")
        except (UnicodeDecodeError, OSError):
            pass
        if len(hits) > 200:
            break
    return _clip("\n".join(hits) or "no matches")


def glob(pattern: str, path: str = ".") -> str:
    root = Path(path).expanduser()
    files = [p for p in root.glob(pattern) if p.is_file() and not _skipped(p)]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    out = "\n".join(str(p) for p in files[:200])
    return _clip(out + (f"\n...[+{len(files) - 200} more files]" if len(files) > 200 else "")) or "no matches"


# ------------------------------------------------------------------ shell
def _kill_group(proc: subprocess.Popen) -> None:
    """Kill the WHOLE process group (shell + its children), not just the shell."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        proc.kill()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass


def bash(command: str) -> str:
    """Run a command; short polling so an interrupt (Ctrl+C) can get in and child processes are stopped too."""
    proc = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, start_new_session=True)
    waited = 0.0
    try:
        while True:
            try:
                out, err = proc.communicate(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                waited += 0.2
                if waited >= 120:
                    _kill_group(proc)
                    return "ERROR: timeout 120s"
    except BaseException:           # KeyboardInterrupt etc.: do not leave an orphan process
        _kill_group(proc)
        raise
    return _clip(f"exit={proc.returncode}\n{out}{err}")


# ------------------------------------------------------------------ web
class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head"}

    def __init__(self):
        super().__init__()
        self.out, self.depth = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.depth += 1
        elif tag in {"p", "br", "li", "h1", "h2", "h3", "h4", "tr", "div"}:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.depth:
            self.depth -= 1

    def handle_data(self, data):
        if not self.depth:
            self.out.append(data)


def web_fetch(url: str) -> str:
    u = urlparse(url)
    if u.scheme not in {"http", "https"} or not u.netloc:
        return "ERROR: only http/https URLs"
    req = urllib.request.Request(url, headers={"User-Agent": "EmilieAgent/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read(2_000_000)
            ctype = r.headers.get("Content-Type", "")
    except (urllib.error.URLError, OSError, ValueError) as e:
        return f"ERROR: {e}"
    text = raw.decode("utf-8", errors="replace")
    if "html" in ctype.lower() or text.lstrip().startswith("<"):
        p = _Text()
        p.feed(text)
        text = "".join(p.out)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return _clip(text or "(empty)")


def todo_write(todos: list) -> str:
    if not isinstance(todos, list):
        return "ERROR: todos must be a list"
    for t in todos:
        if not isinstance(t, dict) or t.get("status") not in {"pending", "in_progress", "completed"} \
                or not t.get("content"):
            return "ERROR: each item needs content and a status (pending|in_progress|completed)"
    return f"Todo list updated ({len(todos)} items)"


# ------------------------------------------------------------------ registry
def _schema(name, desc, props, required):
    return {"name": name, "description": desc,
            "input_schema": {"type": "object", "properties": props, "required": required}}


_s = {"type": "string"}
_i = {"type": "integer"}
_todo_item = {"type": "object", "properties": {
    "content": _s, "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]}},
    "required": ["content", "status"]}

# nama → (fungsi, schema, grup, dangerous-legacy)
TOOLS = {
    "read_file": (read_file, _schema(
        "read_file", "Read a file; output is line-numbered as 'number<TAB>content' (do not include the numbers when editing). "
                     "Use offset/limit for large files.",
        {"path": _s, "offset": _i, "limit": _i}, ["path"]), "file", False),
    "write_file": (write_file, _schema("write_file", "Write/overwrite a file", {"path": _s, "content": _s},
                                       ["path", "content"]), "file", True),
    "edit_file": (edit_file, _schema("edit_file", "Replace one unique string in a file",
                                     {"path": _s, "old_string": _s, "new_string": _s},
                                     ["path", "old_string", "new_string"]), "file", True),
    "grep": (grep, _schema("grep", "Search files with a regex", {"pattern": _s, "path": _s}, ["pattern"]),
             "search", False),
    "glob": (glob, _schema("glob", "Find files by glob pattern, e.g. **/*.py", {"pattern": _s, "path": _s},
                           ["pattern"]), "search", False),
    "bash": (bash, _schema("bash", "Run a shell command", {"command": _s}, ["command"]), "shell", True),
    "web_fetch": (web_fetch, _schema("web_fetch", "Fetch the text of a web page", {"url": _s}, ["url"]),
                  "web", False),
    "todo_write": (todo_write, _schema(
        "todo_write", "Record/update the task list for multi-step work (send the whole list).",
        {"todos": {"type": "array", "items": _todo_item}}, ["todos"]), "plan", False),
}

SCHEMAS = [v[1] for v in TOOLS.values()]


def register(name: str, fn, schema: dict, group: str) -> None:
    """Register a tool at runtime (skill, MCP). SCHEMAS is updated in place."""
    TOOLS[name] = (fn, schema, group, False)
    SCHEMAS[:] = [v[1] for v in TOOLS.values()]


def unregister(name: str) -> None:
    if TOOLS.pop(name, None) is not None:
        SCHEMAS[:] = [v[1] for v in TOOLS.values()]


def groups() -> dict[str, list[str]]:
    g: dict[str, list[str]] = {}
    for name, (_, _, group, _) in TOOLS.items():
        g.setdefault(group, []).append(name)
    return g
