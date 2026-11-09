"""Tool definitions (schema) and implementation."""
import json
import os
import re
import shutil
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
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
PENDING_IMAGES: list[str] = []          # image files read_file wants the model to SEE; the agent attaches them next


def _page_range(spec: str, total: int) -> list[int]:
    """'3', '2-5', '1,4-6' -> 0-based page indexes inside 0..total-1 (empty spec = first 20 pages)."""
    if not (spec or "").strip():
        return list(range(min(total, 20)))
    out: list[int] = []
    for part in spec.replace(" ", "").split(","):
        a, _, b = part.partition("-")
        if not a.isdigit() or (b and not b.isdigit()):
            raise ValueError(f"bad pages '{spec}': use e.g. 3, 2-5 or 1,4-6")
        lo, hi = int(a), int(b or a)
        out += [p - 1 for p in range(max(1, lo), min(total, hi) + 1)]
    return out


def _read_pdf(p: Path, pages: str) -> str:
    try:
        import logging
        from pypdf import PdfReader
        logging.getLogger("pypdf").setLevel(logging.CRITICAL)      # its warnings would be printed over the screen
    except ImportError:
        return "ERROR: reading PDFs needs the 'pypdf' package: run  pip install pypdf  (or reinstall Emilie)"
    try:
        reader = PdfReader(str(p))
        if reader.is_encrypted:
            return "ERROR: this PDF is password protected"
        total = len(reader.pages)
        idx = _page_range(pages, total)
        parts, empty = [], 0
        for i in idx:
            text = (reader.pages[i].extract_text() or "").strip()
            empty += 0 if text else 1
            parts.append(f"--- page {i + 1} of {total} ---\n{text}")
    except ValueError as e:
        return f"ERROR: {e}"
    except Exception as e:
        return f"ERROR: could not read the PDF: {type(e).__name__}: {e}"
    body = "\n\n".join(parts)
    if idx and empty == len(idx):
        return (f"(no text found on pages {idx[0] + 1}-{idx[-1] + 1} of {total}: this looks like a scanned PDF made of "
                "images, which cannot be read as text)")
    if len(idx) >= total:
        more = ""
    elif not (pages or "").strip():
        more = f"\n\n[showing the first {len(idx)} of {total} pages; pass pages=\"{len(idx) + 1}-{min(total, len(idx) + 20)}\" for the next ones]"
    else:
        more = f"\n\n[showing {len(idx)} of {total} pages]"
    return _clip(body) + more


def _read_notebook(p: Path) -> str:
    try:
        nb = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        cells = nb.get("cells", [])
    except (ValueError, AttributeError) as e:
        return f"ERROR: not a valid notebook: {e}"
    out = []
    for i, c in enumerate(cells, 1):
        src = "".join(c.get("source", [])) if isinstance(c.get("source"), list) else str(c.get("source", ""))
        out.append(f"--- cell {i} [{c.get('cell_type', '?')}] ---\n{src}")
        for o in (c.get("outputs") or [])[:3]:
            txt = o.get("text") or (o.get("data") or {}).get("text/plain") or ""
            txt = "".join(txt) if isinstance(txt, list) else str(txt)
            if txt.strip():
                out.append(f"[output]\n{txt.strip()[:1500]}")
    note = "\n\n[cells are numbered from 1; change them with notebook_edit and run them with notebook_run, not edit_file]"
    return (_clip("\n\n".join(out)) or "(empty notebook)") + note


def read_file(path: str, offset: int = 1, limit: int = 0, pages: str = "") -> str:
    p = Path(path).expanduser()
    ext = p.suffix.lower()
    if ext == ".pdf":
        return _read_pdf(p, pages)
    if ext == ".ipynb":
        return _read_notebook(p)
    if ext in (".docx", ".xlsx", ".xlsm", ".pptx"):         # zip packages: reading them as text would return binary noise
        from . import office_docx, office_xlsx
        if ext == ".docx":
            return office_docx.docx_read(path, offset, limit)
        return office_xlsx.pptx_read(path) if ext == ".pptx" else office_xlsx.xlsx_read(path)
    if ext in IMAGE_EXTS:
        if not p.is_file():
            return f"ERROR: {p} not found"
        try:
            from PIL import Image
            with Image.open(p) as im:
                w, h = im.size
        except Exception as e:
            return f"ERROR: not a readable image: {e}"
        PENDING_IMAGES.append(str(p))
        return f"Image {p.name} ({w}x{h}, {p.stat().st_size // 1024} KB) is attached below as a picture for you to look at."
    lines = p.read_text(errors="replace").splitlines()
    total = len(lines)
    offset = max(1, int(offset or 1))
    limit = min(int(limit or LIMITS["read_lines"]), LIMITS["read_lines"])
    chunk = lines[offset - 1: offset - 1 + limit]
    body = _clip("\n".join(f"{i:>5}\t{l}" for i, l in enumerate(chunk, offset)))
    if offset > 1 or offset - 1 + len(chunk) < total:
        body += (f"\n...[lines {offset}-{offset + len(chunk) - 1} of {total}; "
                 f"use offset/limit for other parts]")
    return body


def _read_text(p: Path) -> tuple[str, str]:
    """(text with \\n newlines, the file's own newline). Reading with newline='' keeps CRLF files CRLF on Windows."""
    with open(p, encoding="utf-8", errors="replace", newline="") as f:
        raw = f.read()
    eol = "\r\n" if "\r\n" in raw else "\n"
    return (raw.replace("\r\n", "\n") if eol == "\r\n" else raw), eol


def _write_text(p: Path, text: str, eol: str) -> None:
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(text.replace("\n", eol) if eol != "\n" else text)


def write_file(path: str, content: str, append: bool = False) -> str:
    """Write a file, or with append=True add to its end (to build a big file in several small calls)."""
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    old, eol = _read_text(p) if p.is_file() else ("", "\n")      # overwriting keeps the file's line endings
    body = content.replace("\r\n", "\n")
    if append and old:
        body = old + body
    _write_text(p, body, eol)
    return f"{'Appended' if append else 'Wrote'} {len(content)} chars to {p}"


def compute_edit(path: str, old_string: str = "", new_string: str = "", replace_all: bool = False,
                 edits: list | None = None) -> tuple[str, str, str, str | None]:
    """Apply one edit (old_string/new_string[/replace_all]) or several in order (edits=[{old_string,new_string,
    replace_all}]) in memory. Returns (old_text, new_text, eol, error). Nothing is written, so a failing edit in a
    batch leaves the file untouched."""
    p = Path(path).expanduser()
    if not p.is_file():
        return "", "", "\n", f"ERROR: {p} is not a file"
    text, eol = _read_text(p)
    todo = edits if edits else [{"old_string": old_string, "new_string": new_string, "replace_all": replace_all}]
    if not isinstance(todo, list) or not all(isinstance(e, dict) for e in todo):
        return text, text, eol, "ERROR: edits must be a list of {old_string, new_string, replace_all}"
    cur = text
    for i, e in enumerate(todo, 1):
        old = str(e.get("old_string", "")).replace("\r\n", "\n")
        new = str(e.get("new_string", "")).replace("\r\n", "\n")
        tag = f"edit {i}: " if len(todo) > 1 else ""
        if not old:
            return text, text, eol, f"ERROR: {tag}old_string is empty"
        if old == new:
            return text, text, eol, f"ERROR: {tag}old_string and new_string are identical"
        n = cur.count(old)
        if n == 0:
            return text, text, eol, f"ERROR: {tag}old_string not found"
        if n > 1 and not e.get("replace_all"):
            return text, text, eol, f"ERROR: {tag}old_string appears {n} times: add more context or set replace_all"
        cur = cur.replace(old, new)
    return text, cur, eol, None


def edit_file(path: str, old_string: str = "", new_string: str = "", replace_all: bool = False,
              edits: list | None = None) -> str:
    _, new, eol, err = compute_edit(path, old_string, new_string, replace_all, edits)
    if err:
        return err
    p = Path(path).expanduser()
    _write_text(p, new, eol)
    k = len(edits) if edits else 1
    return f"Edited {p}" + (f" ({k} changes)" if k > 1 else "")


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
IS_WIN = os.name == "nt"
PLATFORM_NOTE = ("OS: Windows. The bash tool runs commands in PowerShell, NOT bash: use PowerShell syntax. "
                 "Chain with ';' (a '&&' is translated for you, '||' is not available); there is no tail/head/grep/wc/cat -n/sed/awk "
                 "(use Select-Object -Last/-First N, Select-String, Measure-Object, Get-Content); do not append '2>&1 | ...' to "
                 "native programs; paths may use '/' or a backslash. For a long install or build pass timeout=<seconds> (up to 900) "
                 "or use bash_bg; for another folder pass cwd=<dir> instead of 'cd x && ...'." if IS_WIN else "")


def _split_and(command: str) -> list[str]:
    """Split on a top-level '&&' (outside quotes). Used to make bash-style chains work in Windows PowerShell 5.1."""
    parts, cur, q, i = [], [], None, 0
    while i < len(command):
        ch = command[i]
        if q:
            cur.append(ch)
            if ch == q:
                q = None
        elif ch in "'\"":
            q = ch
            cur.append(ch)
        elif command.startswith("&&", i):
            parts.append("".join(cur).strip())
            cur = []
            i += 1
        else:
            cur.append(ch)
        i += 1
    parts.append("".join(cur).strip())
    return parts


def _ps_chain(command: str) -> str:
    """'a && b && c'  ->  'a; if ($?) { b; if ($?) { c } }'  (PowerShell 5.1 has no '&&')."""
    parts = _split_and(command)
    if len(parts) < 2 or not all(parts):
        return command
    out = parts[-1]
    for p in reversed(parts[:-1]):
        out = f"{p}; if ($?) {{ {out} }}"
    return out


def _shell_cmd(command: str) -> list[str]:
    """Windows: PowerShell (pwsh if present), UTF-8 output."""
    exe = shutil.which("pwsh") or shutil.which("powershell") or "powershell"
    if not shutil.which("pwsh"):
        command = _ps_chain(command)           # Windows PowerShell 5.1 has no '&&'
    prefix = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; $ProgressPreference='SilentlyContinue'; "
    return [exe, "-NoProfile", "-NonInteractive", "-Command", prefix + command]


def _kill_group(proc: subprocess.Popen) -> None:
    """Kill the WHOLE process tree (shell + its children), not just the shell."""
    if IS_WIN:
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, timeout=10)
        except Exception:
            proc.kill()
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass


def bash(command: str, timeout: int = 120, cwd: str | None = None) -> str:
    """Run a command; short polling so an interrupt (Ctrl+C) can get in and child processes are stopped too."""
    try:
        limit = max(1, min(int(timeout), 900))
    except (TypeError, ValueError):
        limit = 120
    if cwd:
        cwd = os.path.expanduser(str(cwd))
        if not os.path.isdir(cwd):
            return f"ERROR: cwd '{cwd}' is not a directory"
    else:
        cwd = None
    if IS_WIN:
        proc = subprocess.Popen(_shell_cmd(command), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", cwd=cwd,
                                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW)
    else:
        proc = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, start_new_session=True, cwd=cwd)
    waited = 0.0
    try:
        while True:
            try:
                out, err = proc.communicate(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                waited += 0.2
                if waited >= limit:
                    _kill_group(proc)
                    return (f"ERROR: timeout {limit}s - the command was stopped. If it is just slow (network, install, build), "
                            f"run it again with a larger timeout (max 900) or start it with bash_bg and read bg_output.")
    except BaseException:           # KeyboardInterrupt etc.: do not leave an orphan process
        _kill_group(proc)
        raise
    return _clip(f"exit={proc.returncode}\n{out}{err}")


# ------------------------------------------------------------------ background tasks
class _BgTask:
    MAX_LINES = 3000

    def __init__(self, tid: int, command: str):
        import collections
        import threading
        import time
        self.id, self.command, self.started = tid, command, time.time()
        self.lines = collections.deque(maxlen=self.MAX_LINES)
        self.dropped = 0                       # lines that fell off the front of the buffer
        self.read_upto = 0                     # absolute line number the model has already seen
        self.total = 0
        self.lock = threading.Lock()
        if IS_WIN:
            self.proc = subprocess.Popen(_shell_cmd(command), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                                         creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW)
        else:
            self.proc = subprocess.Popen(command, shell=True, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT, text=True, errors="replace", start_new_session=True)
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        for line in self.proc.stdout:
            with self.lock:
                if len(self.lines) == self.lines.maxlen:
                    self.dropped += 1
                self.lines.append(line.rstrip("\r\n"))
                self.total += 1

    @property
    def running(self) -> bool:
        return self.proc.poll() is None


BG: dict[int, _BgTask] = {}


def _bg_kill_all() -> None:
    for t in BG.values():
        if t.running:
            _kill_group(t.proc)


import atexit  # noqa: E402
atexit.register(_bg_kill_all)           # never leave a dev server running after Emilie exits


def _bg_status(t: _BgTask) -> str:
    import time
    age = int(time.time() - t.started)
    return (f"running {age}s" if t.running else f"exited with code {t.proc.returncode}") + f" · {t.command[:80]}"


def bash_bg(command: str) -> str:
    """Start a long-running command (dev server, watcher, slow build) in the background and return at once."""
    if not (command or "").strip():
        return "ERROR: empty command"
    if sum(1 for t in BG.values() if t.running) >= 8:
        return "ERROR: 8 background tasks are already running; stop one with bg_stop"
    tid = max(BG, default=0) + 1
    try:
        BG[tid] = _BgTask(tid, command)
    except OSError as e:
        return f"ERROR: {e}"
    return (f"Started background task {tid}. Read its output with bg_output(id={tid}); stop it with bg_stop(id={tid}). "
            f"It is stopped automatically when Emilie exits.")


def bg_output(id: int = 0, tail: int = 60, all: bool = False) -> str:
    """Output of a background task: only the lines you have not seen yet (or the last `tail` with all=true).
    With no id, lists every background task."""
    if not id:
        return "\n".join(f"{t.id}: {_bg_status(t)}" for t in BG.values()) or "no background tasks"
    t = BG.get(int(id))
    if t is None:
        return f"ERROR: no background task {id}"
    with t.lock:
        lines = list(t.lines)
        first = t.total - len(lines)                 # absolute index of lines[0]
        start = max(first, t.total - max(1, int(tail))) if all else max(first, t.read_upto)
        chunk = lines[start - first:]
        gap = start - t.read_upto if not all and start > t.read_upto else 0
        t.read_upto = t.total
    head = f"[task {t.id}: {_bg_status(t)}]"
    if gap:
        head += f"\n[{gap} older lines were dropped from the buffer]"
    return _clip(head + "\n" + ("\n".join(chunk) if chunk else "(no new output)"))


def bg_stop(id: int) -> str:
    t = BG.get(int(id))
    if t is None:
        return f"ERROR: no background task {id}"
    if not t.running:
        return f"task {t.id} had already {_bg_status(t).split(' · ')[0]}"
    _kill_group(t.proc)
    return f"Stopped background task {t.id}"


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


def web_search(query: str, max_results: int = 8) -> str:
    """Search the web through DuckDuckGo's HTML endpoint (no API key). Returns title, url and snippet per result."""
    import html as _html
    from urllib.parse import parse_qs, quote_plus, unquote
    query = (query or "").strip()
    if not query:
        return "ERROR: empty query"
    try:
        n = max(1, min(int(max_results), 15))
    except (TypeError, ValueError):
        n = 8
    req = urllib.request.Request(
        "https://html.duckduckgo.com/html/", data=f"q={quote_plus(query)}".encode(),
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
                 "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            page = r.read(1_500_000).decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError, ValueError) as e:
        return f"ERROR: search failed: {e}"

    def clean(s: str) -> str:
        return " ".join(_html.unescape(re.sub(r"<[^>]+>", "", s)).split())

    out = []
    blocks = re.findall(r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>(.*?)(?=<a[^>]+class="result__a"|$)',
                        page, re.S)
    for href, title, rest in blocks:
        href = _html.unescape(href)
        if "uddg=" in href:
            href = unquote(parse_qs(urlparse(href if href.startswith("http") else "https:" + href).query)
                           .get("uddg", [href])[0])
        if "duckduckgo.com/y.js" in href:      # sponsored result
            continue
        snip = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', rest, re.S)
        out.append(f"{len(out) + 1}. {clean(title)}\n   {href}" + (f"\n   {clean(snip.group(1))}" if snip else ""))
        if len(out) >= n:
            break
    if not out:
        return "no results (the search engine may have blocked the request; try web_fetch on a specific URL)"
    return _clip("\n".join(out))


def todo_write(todos: list) -> str:
    if not isinstance(todos, list):
        return "ERROR: todos must be a list"
    for t in todos:
        if not isinstance(t, dict) or t.get("status") not in {"pending", "in_progress", "completed"} \
                or not t.get("content"):
            return "ERROR: each item needs content and a status (pending|in_progress|completed)"
    return f"Todo list updated ({len(todos)} items)"


# ------------------------------------------------------------------ registry
def invoke(name: str, args: dict) -> str:
    """Call a tool with the model's arguments. Models trained on other agents often add arguments we do not have
    (description, run_in_background, path ...): drop them and say so instead of failing the whole call."""
    import inspect
    fn = TOOLS[name][0]
    args = dict(args or {})
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return fn(**args)
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return fn(**args)
    extra = [k for k in args if k not in params]
    for k in extra:
        args.pop(k)
    out = fn(**args)
    if extra:
        out = f"NOTE: ignored unknown argument(s): {', '.join(extra)} (this tool accepts: {', '.join(params)}).\n{out}"
    return out


def _schema(name, desc, props, required):
    return {"name": name, "description": desc,
            "input_schema": {"type": "object", "properties": props, "required": required}}


schema = _schema      # public alias for tools registered at runtime (e.g. the sub-agent)


_s = {"type": "string"}
_i = {"type": "integer"}
_todo_item = {"type": "object", "properties": {
    "content": _s, "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]}},
    "required": ["content", "status"]}

# nama → (fungsi, schema, grup, dangerous-legacy)
TOOLS = {
    "read_file": (read_file, _schema(
        "read_file", "Read a file; output is line-numbered as 'number<TAB>content' (do not include the numbers when editing). "
                     "Use offset/limit for large files. Also reads PDFs (text; use pages like '1-5', default first 20), "
                     "Jupyter notebooks (.ipynb), Word/Excel/PowerPoint files (.docx/.xlsx/.pptx, as text) and images "
                     "(png/jpg/gif/webp/bmp: the picture is attached so you can see it).",
        {"path": _s, "offset": _i, "limit": _i, "pages": _s}, ["path"]), "file", False),
    "write_file": (write_file, _schema(
        "write_file", "Write/overwrite a file. With append=true the content is added to the END of the file instead: "
                      "use it to write a big file in several parts so one call never hits the output limit.",
        {"path": _s, "content": _s, "append": {"type": "boolean"}}, ["path", "content"]), "file", True),
    "edit_file": (edit_file, _schema(
        "edit_file", "Replace text in a file. Give old_string + new_string (old_string must be unique unless "
                     "replace_all is true, e.g. to rename a variable). For several changes to ONE file pass "
                     "edits=[{old_string,new_string,replace_all?}, ...]: they apply in order and either all succeed "
                     "or the file is left untouched.",
        {"path": _s, "old_string": _s, "new_string": _s, "replace_all": {"type": "boolean"},
         "edits": {"type": "array", "items": {"type": "object", "properties": {
             "old_string": _s, "new_string": _s, "replace_all": {"type": "boolean"}},
             "required": ["old_string", "new_string"]}}},
        ["path"]), "file", True),
    "grep": (grep, _schema("grep", "Search files with a regex", {"pattern": _s, "path": _s}, ["pattern"]),
             "search", False),
    "glob": (glob, _schema("glob", "Find files by glob pattern, e.g. **/*.py", {"pattern": _s, "path": _s},
                           ["pattern"]), "search", False),
    "bash": (bash, _schema(
        "bash", "Run a shell command (PowerShell on Windows, sh elsewhere). Optional: timeout in seconds (default 120, max 900) "
                "for slow installs/builds, cwd to run in another folder. Anything that may run for minutes or never ends "
                "(dev server, watcher) belongs in bash_bg.",
        {"command": _s, "timeout": _i, "cwd": _s}, ["command"]), "shell", True),
    "bash_bg": (bash_bg, _schema(
        "bash_bg", "Run a long-running command in the BACKGROUND (dev server, file watcher, slow build/test) and "
                   "return immediately with a task id. Use plain bash for anything that finishes quickly.",
        {"command": _s}, ["command"]), "shell", True),
    "bg_output": (bg_output, _schema(
        "bg_output", "Read new output of a background task (id), or with no id list all background tasks and whether "
                     "they still run. all=true re-reads the last `tail` lines.",
        {"id": _i, "tail": _i, "all": {"type": "boolean"}}, []), "shell", False),
    "bg_stop": (bg_stop, _schema("bg_stop", "Stop a background task and its child processes.", {"id": _i}, ["id"]),
                "shell", False),
    "web_fetch": (web_fetch, _schema("web_fetch", "Fetch the text of a web page", {"url": _s}, ["url"]),
                  "web", False),
    "web_search": (web_search, _schema(
        "web_search", "Search the web (DuckDuckGo). Returns titles, URLs and snippets; follow up with web_fetch on a "
                      "promising URL to read the page. Use it for current events, docs, prices, anything you do not know.",
        {"query": _s, "max_results": _i}, ["query"]), "web", False),
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


def repair_json(raw: str) -> dict | None:
    """Fix the small syntax slips weaker models make in tool arguments, or return None. It only repairs things that
    cannot change the meaning: a ```json fence, text around the object, trailing commas, Python True/False/None, an
    object written with single quotes, and raw newlines/tabs inside strings. It never invents missing closing brackets:
    that means the answer was cut off, which is handled separately."""
    s = (raw or "").strip()
    if not s:
        return {}
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s)
    a, b = s.find("{"), s.rfind("}")
    if a == -1 or b <= a:
        return None
    s = s[a:b + 1]
    candidates = [s, re.sub(r",\s*([}\]])", r"\1", s)]
    t = candidates[1]
    candidates.append(re.sub(r"\bTrue\b", "true", re.sub(r"\bFalse\b", "false", re.sub(r"\bNone\b", "null", t))))
    if '"' not in s and "'" in s:                       # {'a': 'b'}
        candidates.append(candidates[-1].replace("'", '"'))
    for c in candidates:
        for strict in (True, False):                     # strict=False accepts raw newlines/tabs inside strings
            try:
                v = json.loads(c, strict=strict)
            except ValueError:
                continue
            if isinstance(v, dict):
                return v
    return None


def shorten(names: list[str]) -> list[str]:
    """For display: ['mcp__browser__a', 'mcp__browser__b', 'bash'] -> ['browser (2)', 'bash']. A browser server brings
    25+ tools; listing every name made the welcome banner taller than the screen."""
    out: list[str] = []
    servers: dict[str, int] = {}
    for n in names:
        if n.startswith("mcp__") and n.count("__") >= 2:
            srv = n.split("__")[1]
            servers[srv] = servers.get(srv, 0) + 1
        else:
            out.append(n)
    return out + [f"{s} ({k})" for s, k in servers.items()]


from . import office_docx, office_nb, office_xlsx  # noqa: E402  (notebook, Word, Excel, PowerPoint tools)
TOOLS.update(office_nb.specs(_schema, _s, _i))
TOOLS.update(office_docx.specs(_schema, _s, _i))
TOOLS.update(office_xlsx.specs(_schema, _s, _i))


def groups() -> dict[str, list[str]]:
    g: dict[str, list[str]] = {}
    for name, (_, _, group, _) in TOOLS.items():
        g.setdefault(group, []).append(name)
    return g
