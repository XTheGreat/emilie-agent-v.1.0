"""render_diagram: Mermaid and PlantUML source -> an SVG or PNG file in ./diagrams/.

Local renderers first (mmdc; plantuml + java). When they are missing and KROKI_URL is set, the code is sent to that
Kroki server instead. The answer is JSON: {"ok": true, "path": ...} or {"ok": false, "error": <the renderer's own
output>}, so the model can fix its diagram syntax and try again.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

KINDS = ("mermaid", "plantuml")
FORMATS = ("svg", "png")
OUT_DIR = "diagrams"
MAX_CODE_BYTES = 100 * 1024
MAX_OUTPUT_BYTES = 20 * 1024 * 1024          # a Kroki answer larger than this is refused
TIMEOUT = 60
PUPPETEER_CONFIG = Path(__file__).parent / "builtin" / "puppeteer.json"     # --no-sandbox, only used when needed

_RESERVED = re.compile(r"(con|prn|aux|nul|com\d|lpt\d)(\..*)?", re.I)       # Windows device names
INSTALL_HINTS = {
    "mmdc": "mmdc (Mermaid CLI) is not installed. It needs Node.js 18+:  npm install -g @mermaid-js/mermaid-cli",
    "plantuml": "plantuml is not installed. Windows: choco install plantuml ; macOS: brew install plantuml ; "
                "Linux: sudo apt install plantuml",
    "java": "java is not installed (PlantUML needs it). Windows: winget install EclipseAdoptium.Temurin.21.JRE ; "
            "macOS: brew install openjdk ; Linux: sudo apt install default-jre",
}


class RenderError(Exception):
    pass


def safe_name(filename: str, code: str, fmt: str) -> str:
    """A plain file name inside OUT_DIR: any folder part is dropped, so '../../x' becomes 'x.<fmt>'."""
    base = re.split(r"[\\/]", str(filename or "").strip())[-1]
    base = re.sub(r"\.(svg|png)$", "", base, flags=re.I)
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._-")[:80]
    if not base:
        base = "diagram-" + hashlib.sha1(code.encode("utf-8", "replace")).hexdigest()[:8]
    elif _RESERVED.fullmatch(base):
        base = "_" + base
    return f"{base}.{fmt}"


def _missing(kind: str) -> list[str]:
    need = ("mmdc",) if kind == "mermaid" else ("plantuml", "java")
    return [n for n in need if not shutil.which(n)]


def _run(cmd: list[str], cwd: str, env: dict | None = None) -> tuple[int, str]:
    """(exit code, stderr + stdout). Argument list only, never a shell; the whole process tree is stopped on timeout."""
    from . import tools
    flags = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW} if tools.IS_WIN
             else {"start_new_session": True})
    try:
        proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", **flags)
    except OSError as e:
        raise RenderError(f"could not start {cmd[0]}: {e}") from None
    deadline = time.monotonic() + TIMEOUT
    try:
        while True:                                  # short polls so Ctrl+C gets in
            try:
                out, err = proc.communicate(timeout=0.2)
                return proc.returncode, "\n".join(x.strip() for x in (err, out) if x and x.strip())
            except subprocess.TimeoutExpired:
                if time.monotonic() >= deadline:
                    raise RenderError(f"the renderer did not finish within {TIMEOUT}s and was stopped") from None
    finally:
        if proc.poll() is None:
            tools._kill_group(proc)


def _render_mermaid(code: str, fmt: str, tmp: Path) -> Path:
    (tmp / "in.mmd").write_text(code, encoding="utf-8")
    out = tmp / f"out.{fmt}"
    # Only fixed relative names are passed: on Windows mmdc is a .cmd file, which cmd.exe parses again.
    cmd = [shutil.which("mmdc"), "-i", "in.mmd", "-o", out.name]
    rc, log = _run(cmd, str(tmp))
    if rc and "sandbox" in log.lower() and PUPPETEER_CONFIG.is_file():     # root / containers / restricted Linux
        shutil.copyfile(PUPPETEER_CONFIG, tmp / "puppeteer.json")
        rc, log = _run(cmd + ["-p", "puppeteer.json"], str(tmp))
    if rc or not out.is_file():
        raise RenderError(log or f"mmdc exited with code {rc} and wrote no output")
    return out


def _render_plantuml(code: str, fmt: str, tmp: Path) -> Path:
    # '@startuml name' lets the source choose the output file name (even a path): drop whatever follows @start...
    code = re.sub(r"(?m)^([ \t]*@start[a-z]+).*$", r"\1", code)
    if not re.search(r"(?m)^[ \t]*@start", code):
        code = f"@startuml\n{code}\n@enduml\n"       # without the markers plantuml silently renders nothing
    (tmp / "in.puml").write_text(code, encoding="utf-8")
    env = dict(os.environ)
    env.setdefault("PLANTUML_SECURITY_PROFILE", "SANDBOX")      # no !include of local files or URLs
    rc, log = _run([shutil.which("plantuml"), f"-t{fmt}", "-charset", "UTF-8", "in.puml"], str(tmp), env)
    made = sorted(tmp.glob(f"*.{fmt}"))
    # On a syntax error it still draws an error picture: not a success. The Windows (Chocolatey) launcher also exits
    # with 0 then, so what it printed counts too.
    if rc or not made or re.search(r"(?m)^Error line \d+|Some diagram description contains errors", log):
        raise RenderError(log or f"plantuml exited with code {rc} and wrote no output")
    return made[0]


def _render_kroki(url: str, code: str, kind: str, fmt: str) -> bytes:
    req = urllib.request.Request(f"{url.rstrip('/')}/{kind}/{fmt}", data=code.encode("utf-8"), method="POST",
                                 headers={"Content-Type": "text/plain; charset=utf-8", "User-Agent": "EmilieAgent/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = r.read(MAX_OUTPUT_BYTES + 1)
    except urllib.error.HTTPError as e:
        with e:
            body = e.read(100_000).decode("utf-8", "replace")
        raise RenderError(f"Kroki HTTP {e.code}: {body}") from None
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise RenderError(f"Kroki request failed: {e}") from None
    if not data or len(data) > MAX_OUTPUT_BYTES:
        raise RenderError("Kroki returned an empty or oversized answer")
    return data


def _answer(**data) -> str:
    return json.dumps(data, ensure_ascii=False)


def _fail(error: str) -> str:
    from . import tools
    return _answer(ok=False, error=tools._clip(error))


def render_diagram(code: str, kind: str, fmt: str = "svg", filename: str = "") -> str:
    kind, fmt = str(kind or "").lower(), str(fmt or "svg").lower()
    if kind not in KINDS:
        return _fail(f"unknown kind '{kind}': use one of {', '.join(KINDS)}")
    if fmt not in FORMATS:
        return _fail(f"unknown fmt '{fmt}': use one of {', '.join(FORMATS)}")
    if not isinstance(code, str) or not code.strip():
        return _fail("code is empty")
    if len(code.encode("utf-8", "replace")) > MAX_CODE_BYTES:
        return _fail(f"code is larger than {MAX_CODE_BYTES // 1024} KB: split the diagram")
    missing = _missing(kind)
    kroki = os.environ.get("KROKI_URL", "").strip()
    if missing and not kroki:
        return _fail("\n".join(INSTALL_HINTS[m] for m in missing)
                     + "\nAsk the user before installing anything. (Or set KROKI_URL to render on a Kroki server.)")
    try:
        folder = Path(OUT_DIR)
        folder.mkdir(exist_ok=True)
        if folder.resolve().parent != Path.cwd().resolve():
            return _fail(f"'{OUT_DIR}' is a link that points elsewhere; not writing through it")
        dest = folder / safe_name(filename, code, fmt)
        with tempfile.TemporaryDirectory(prefix="emilie-diagram-", ignore_cleanup_errors=True) as d:
            tmp = Path(d)
            if missing:
                made = tmp / f"kroki.{fmt}"
                made.write_bytes(_render_kroki(kroki, code, kind, fmt))
            else:
                made = (_render_mermaid if kind == "mermaid" else _render_plantuml)(code, fmt, tmp)
            if dest.is_symlink():
                dest.unlink()
            shutil.copyfile(made, dest)
    except RenderError as e:
        return _fail(str(e))
    except (OSError, UnicodeError) as e:
        return _fail(f"{type(e).__name__}: {e}")
    return _answer(ok=True, path=str(dest.resolve()))


def specs(_schema, _s) -> dict:
    return {"render_diagram": (render_diagram, _schema(
        "render_diagram",
        "Render a Mermaid or PlantUML diagram to an image file in ./diagrams/. code: the diagram source; kind: "
        "mermaid|plantuml; fmt: svg (default)|png; filename: optional name (no folders). Returns "
        '{"ok":true,"path":...} or {"ok":false,"error":...}: a syntax error comes back as the renderer printed it, '
        "so fix the code and call again.",
        {"code": _s, "kind": {"type": "string", "enum": list(KINDS)},
         "fmt": {"type": "string", "enum": list(FORMATS)}, "filename": _s}, ["code", "kind"]), "file", True)}
