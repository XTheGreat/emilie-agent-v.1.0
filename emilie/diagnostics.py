"""Syntax check after every file change: a broken edit is reported in the same step, not three steps later.

Breaking a file with an edit (a lost indent, a missing comma, bracket or closing tag) is the most common way a coding
agent goes wrong, and without a check the model only finds out much later, when a test, a build or the user trips over
it. After write_file / edit_file the agent calls report(): the new text is parsed at once and a syntax error goes back
to the model inside the same tool result, with the lines around it, so it is fixed before anything else.

Checked in-process (standard library only): Python, JSON (comments and trailing commas allowed where the tools that read
the file allow them: tsconfig.json, .vscode/*.json, *.jsonc, ...), TOML and XML (SVG, .csproj, ...). With a program that
is already installed: YAML (PyYAML), JavaScript and TypeScript (the project's own TypeScript from node_modules, which
also understands JSX/TSX; otherwise `node --check` for plain .js), PowerShell and, outside Windows, shell scripts
(`bash -n`). Only a parse: nothing is executed and types are not checked, so it costs milliseconds in-process and well
under a second for an external parser.

No checker for a file type, a parser that is not installed or one that fails: no report. So silence means "nothing
found", never "verified". An error that was already in the file before the change is mentioned in one short line, so a
file that never parsed (a Helm template, a work in progress) does not drown the model in repeats.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import warnings
from dataclasses import dataclass, field
from pathlib import Path

MAX_CHARS = 2_000_000           # bigger files are not checked
TIMEOUT = 20                    # seconds for an external parser (TypeScript's first load is slow on a cold disk)
SNIPPET = 2                     # lines shown above and below an error
IS_WIN = os.name == "nt"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass
class Problem:
    line: int                   # 1-based, 0 = unknown
    col: int                    # 1-based, 0 = unknown
    msg: str


@dataclass
class Result:
    lang: str                   # what parsed the file, named in the message: "Python 3.12", "JSON", "TypeScript 5.6" ...
    problems: list[Problem] = field(default_factory=list)


def _run(cmd: list[str], text: str | None = None, env: dict | None = None) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(cmd, input=text, stdin=None if text is not None else subprocess.DEVNULL,
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT,
                              env=env, creationflags=_NO_WINDOW)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


# Jinja / Helm / Handlebars / cookiecutter markers: such a file is a template, not YAML or JSON yet.
# GitHub Actions' ${{ ... }} is plain YAML and does not count.
_TEMPLATE = re.compile(r"(?<!\$)\{\{|\{%")


# ------------------------------------------------------------------ Python
def _python(path: Path, text: str) -> Result:
    lang = f"Python {sys.version_info.major}.{sys.version_info.minor}"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")              # a SyntaxWarning (an invalid escape) is not an error
        try:
            # a full compile, not just ast.parse: 'return' outside a function, a duplicate argument, a misplaced
            # nonlocal ... are only found by the compiler, and Python refuses to run the file for them all the same
            compile(text, str(path), "exec", dont_inherit=True)
        except SyntaxError as e:                     # also IndentationError and TabError
            return Result(lang, [Problem(e.lineno or 0, e.offset or 0, e.msg or str(e))])
        except ValueError as e:                      # null bytes in the source
            return Result(lang, [Problem(0, 0, str(e))])
    return Result(lang)


# ------------------------------------------------------------------ JSON / JSONC
_STR_OR_COMMENT = re.compile(r'"(?:\\.|[^"\\\n])*"|//[^\n]*|/\*.*?\*/', re.S)
_TRAILING_COMMA = re.compile(r",(?=\s*[}\]])")
_JSONC_NAMES = re.compile(r"(tsconfig|jsconfig)[\w.-]*\.json|\.eslintrc\.json|\.?devcontainer\.json|\.?babelrc\.json|"
                          r"deno\.json|biome\.json|tslint\.json|typedoc\.json|api-extractor\.json", re.I)


def _jsonc_by_name(path: Path) -> bool:
    """Files whose readers accept comments and trailing commas (TypeScript, VS Code, ESLint, Deno, ...)."""
    return (path.suffix.lower() in (".jsonc", ".code-workspace") or path.parent.name.lower() in (".vscode", ".devcontainer")
            or bool(_JSONC_NAMES.fullmatch(path.name)))


def _strip_jsonc(text: str) -> str:
    """Comments and trailing commas become spaces (line breaks kept), so the positions in an error stay right."""
    s = _STR_OR_COMMENT.sub(lambda m: m.group(0) if m.group(0).startswith('"') else re.sub(r"[^\n]", " ", m.group(0)), text)
    return _TRAILING_COMMA.sub(" ", s)


def _json_problem(text: str) -> Problem | None:
    try:
        json.loads(text)
    except json.JSONDecodeError as e:
        return Problem(e.lineno, e.colno, e.msg)
    return None


def _json(path: Path, text: str, jsonc: bool | None = None) -> Result | None:
    if text.startswith("﻿"):
        text = " " + text[1:]                        # a BOM: readers skip it; a space keeps the columns right
    if jsonc is None:
        jsonc = _jsonc_by_name(path)
    err = _json_problem(_strip_jsonc(text) if jsonc else text)
    if err and _TEMPLATE.search(_STR_OR_COMMENT.sub("", text)):
        return None                                  # template markers outside strings: not JSON until rendered
    return Result("JSONC" if jsonc else "JSON", [err] if err else [])


def _is_jsonc_text(text: str) -> bool:
    """The text uses comments or trailing commas: strict JSON fails, the tolerant parse succeeds."""
    t = " " + text[1:] if text.startswith("﻿") else text
    return _json_problem(t) is not None and _json_problem(_strip_jsonc(t)) is None


# ------------------------------------------------------------------ TOML, YAML, XML
def _toml(path: Path, text: str) -> Result | None:
    try:
        import tomllib
    except ImportError:                              # Python 3.10
        try:
            import tomli as tomllib                  # type: ignore[no-redef]
        except ImportError:
            return None
    try:
        tomllib.loads(text.lstrip("﻿"))
    except tomllib.TOMLDecodeError as e:
        if _TEMPLATE.search(text):
            return None
        s = str(e)
        m = re.search(r"\(at line (\d+), column (\d+)\)", s)
        line = getattr(e, "lineno", None) or (int(m.group(1)) if m else 0)
        col = getattr(e, "colno", None) or (int(m.group(2)) if m else 0)
        msg = getattr(e, "msg", None) or re.sub(r"\s*\(at (line \d+, column \d+|end of document)\)\s*$", "", s)
        return Result("TOML", [Problem(line, col, str(msg))])
    return Result("TOML")


def _yaml(path: Path, text: str) -> Result | None:
    try:
        import yaml                                  # PyYAML is optional
    except ImportError:
        return None
    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    try:
        for _ in yaml.compose_all(text, Loader=loader):    # compose, not load: custom tags (!Ref, !reference) are fine
            pass
    except yaml.MarkedYAMLError as e:
        if _TEMPLATE.search(text):
            return None
        mark = e.problem_mark or e.context_mark
        msg = ": ".join(str(x) for x in (e.context, e.problem) if x) or str(e).splitlines()[0]
        return Result("YAML", [Problem(mark.line + 1 if mark else 0, mark.column + 1 if mark else 0, msg)])
    except yaml.YAMLError as e:
        return Result("YAML", [Problem(0, 0, (str(e).splitlines() or ["invalid YAML"])[0])])
    return Result("YAML")


def _xml(path: Path, text: str) -> Result | None:
    import xml.etree.ElementTree as ET
    try:
        ET.fromstring(text)
    except ET.ParseError as e:
        msg = re.sub(r":\s*line \d+, column \d+$", "", str(e))
        if "encoding" in msg.lower() or _TEMPLATE.search(text):
            return None                              # a declared encoding we cannot honour here, or a template
        line, col = getattr(e, "position", (0, -1))
        return Result("XML", [Problem(line, col + 1, msg)])
    return Result("XML")


# ------------------------------------------------------------------ JavaScript / TypeScript
# transpileModule reports the parse errors only (no type checking, no imports resolved); the file name's extension
# tells it whether JSX is allowed. Source on stdin, one JSON line out. Single quotes only: it travels as an argument.
_TS_SCRIPT = (
    "const ts=require(process.argv[1]);const name=process.argv[2];const chunks=[];"
    "process.stdin.on('data',c=>chunks.push(c));process.stdin.on('end',()=>{"
    "const src=Buffer.concat(chunks).toString('utf8');"
    "const r=ts.transpileModule(src,{fileName:name,reportDiagnostics:true,compilerOptions:{jsx:ts.JsxEmit.Preserve,"
    "target:ts.ScriptTarget.ESNext,module:ts.ModuleKind.ESNext}});"
    "const problems=(r.diagnostics||[]).filter(d=>d.file&&d.start!==undefined).map(d=>{"
    "const p=d.file.getLineAndCharacterOfPosition(d.start);"
    "return {line:p.line+1,col:p.character+1,msg:ts.flattenDiagnosticMessageText(d.messageText,' ')}});"
    "process.stdout.write(JSON.stringify({v:ts.version,problems})+'\\n')});"
)
_TS_EXT = {".ts", ".tsx", ".mts", ".cts"}
_JS_EXT = {".js", ".mjs", ".cjs", ".jsx"}
_PLAIN_JS = {".js", ".mjs", ".cjs"}


def _global_node_modules() -> list[Path]:
    if IS_WIN:
        return [Path(os.environ["APPDATA"]) / "npm" / "node_modules"] if os.environ.get("APPDATA") else []
    out = [Path(os.environ["NVM_BIN"]).parent / "lib" / "node_modules"] if os.environ.get("NVM_BIN") else []
    return out + [Path.home() / ".npm-global" / "lib" / "node_modules", Path("/usr/local/lib/node_modules"),
                  Path("/opt/homebrew/lib/node_modules"), Path("/usr/lib/node_modules")]


def find_typescript(start: Path) -> Path | None:
    """The TypeScript compiler of the project the file belongs to (the nearest node_modules up the tree), else a
    globally installed one."""
    for d in [start, *start.parents]:
        f = d / "node_modules" / "typescript" / "lib" / "typescript.js"
        if f.is_file():
            return f
    for g in _global_node_modules():
        f = g / "typescript" / "lib" / "typescript.js"
        if f.is_file():
            return f
    return None


def _node_check(node: str, suffix: str, text: str) -> Result | None:
    """`node --check` on a copy in an empty folder: no package.json "type" there, so Node decides CommonJS or ES module
    from the code itself, the way a bundler would see it."""
    with tempfile.TemporaryDirectory(prefix="emilie-check-") as d:
        f = Path(d) / ("check" + suffix)
        f.write_text(text, encoding="utf-8")
        r = _run([node, "--check", str(f)])
    if r is None:
        return None
    lang = "JavaScript (node --check)"
    if r.returncode == 0:
        return Result(lang)
    err = r.stderr or ""
    m = re.search(r"^\w*Error: (.+)$", err, re.M)
    if not m:
        return None                                  # node failed for another reason: no verdict
    msg = m.group(1).strip()
    if "Unexpected token '<'" in msg:
        return None                                  # most likely JSX, which only a JSX-aware parser can judge
    if suffix == ".js" and re.search(r"Cannot use import statement|Unexpected token 'export'|await is only valid", msg):
        return _node_check(node, ".mjs", text)       # an older Node that does not detect ES modules by itself
    lines = err.splitlines()
    lm = re.search(r":(\d+)\s*$", lines[0]) if lines else None
    caret = next((l for l in lines[1:4] if re.fullmatch(r"\s*\^+\s*", l)), "")
    return Result(lang, [Problem(int(lm.group(1)) if lm else 0, caret.index("^") + 1 if caret else 0, msg)])


def _js(path: Path, text: str) -> Result | None:
    node = shutil.which("node")
    if not node:
        return None
    ts = find_typescript(path.resolve().parent)
    if ts:
        r = _run([node, "-e", _TS_SCRIPT, str(ts), path.name], text)
        if r is not None and r.returncode == 0:
            try:
                d = json.loads(r.stdout.strip().splitlines()[-1])
                return Result(f"TypeScript {d.get('v', '')}".strip(),
                              [Problem(int(p["line"]), int(p["col"]), str(p["msg"])) for p in d.get("problems", [])])
            except (ValueError, KeyError, IndexError, TypeError):
                pass                                 # a TypeScript too old or broken: try node below
    if path.suffix.lower() not in _PLAIN_JS:
        return None                                  # JSX and TypeScript need the TypeScript parser
    return _node_check(node, path.suffix.lower(), text)


# ------------------------------------------------------------------ PowerShell, shell
_PS_SCRIPT = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
              "$t=[IO.File]::ReadAllText($env:EMILIE_CHECK_FILE,[Text.Encoding]::UTF8); $e=$null; "
              "[void][System.Management.Automation.Language.Parser]::ParseInput($t,[ref]$null,[ref]$e); "
              "foreach($x in $e){ '{0}|{1}|{2}' -f $x.Extent.StartLineNumber,$x.Extent.StartColumnNumber,$x.Message }")


def _powershell(path: Path, text: str) -> Result | None:
    exe = shutil.which("pwsh") or (shutil.which("powershell") if IS_WIN else None)
    if not exe:
        return None
    with tempfile.TemporaryDirectory(prefix="emilie-check-") as d:
        f = Path(d) / "check.ps1"
        f.write_text(text, encoding="utf-8")         # read back as UTF-8 by the script: no quoting, no code page
        r = _run([exe, "-NoProfile", "-NonInteractive", "-Command", _PS_SCRIPT],
                 env={**os.environ, "EMILIE_CHECK_FILE": str(f)})
    if r is None or r.returncode != 0:
        return None
    probs = []
    for line in r.stdout.splitlines():
        parts = line.split("|", 2)
        if len(parts) == 3 and parts[0].strip().isdigit():
            probs.append(Problem(int(parts[0]), int(parts[1]) if parts[1].strip().isdigit() else 0, parts[2].strip()))
    return Result("PowerShell", probs)


def _shell(path: Path, text: str) -> Result | None:
    if IS_WIN:
        return None                                  # 'bash' there is often WSL's launcher, not a bash for this file
    first = text.split("\n", 1)[0]
    if first.startswith("#!") and re.search(r"\b(zsh|fish|ksh|csh|tcsh)\b", first):
        return None                                  # another shell's syntax
    sh = shutil.which("bash")
    r = _run([sh, "-n"], text) if sh else None
    if r is None:
        return None
    if r.returncode == 0:
        return Result("bash -n")
    probs = [Problem(int(m.group(1)), 0, m.group(2).strip()) for m in
             (re.search(r"line (\d+): (.*(?:syntax error|unexpected).*)$", l) for l in r.stderr.splitlines()) if m]
    return Result("bash -n", probs) if probs else None


# ------------------------------------------------------------------ dispatch
_EXT = {}
for _exts, _fn in (((".py", ".pyw", ".pyi"), _python),
                   ((".json", ".jsonc", ".code-workspace", ".geojson", ".webmanifest", ".ipynb", ".har"), _json),
                   ((".toml",), _toml), ((".yaml", ".yml"), _yaml),
                   ((".xml", ".svg", ".xsd", ".xsl", ".xslt", ".xaml", ".csproj", ".vbproj", ".fsproj", ".vcxproj",
                     ".props", ".targets", ".resx", ".nuspec", ".plist", ".rss", ".atom", ".wsdl"), _xml),
                   (tuple(_JS_EXT | _TS_EXT), _js), ((".ps1", ".psm1", ".psd1"), _powershell), ((".sh", ".bash"), _shell)):
    _EXT.update(dict.fromkeys(_exts, _fn))
del _exts, _fn


def checkable(path: str | Path) -> bool:
    return Path(str(path)).suffix.lower() in _EXT


def _read(p: Path) -> str | None:
    try:
        if p.stat().st_size > MAX_CHARS * 2:
            return None
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def read_before(path: str | Path) -> str | None:
    """The file's text before a change, kept to tell a new error from one that was already there. None when the file
    does not exist yet or its type is not checked."""
    p = Path(str(path)).expanduser()
    return _read(p) if checkable(p) and p.is_file() else None


def check(path: str | Path, text: str | None = None, jsonc: bool | None = None) -> Result | None:
    """Parse `text` (default: the file on disk) the way the file's type demands. None = this type is not checked,
    its parser is not installed or gave no verdict. Never raises."""
    p = Path(str(path)).expanduser()
    fn = _EXT.get(p.suffix.lower())
    if fn is None:
        return None
    if text is None:
        text = _read(p)
    if text is None or len(text) > MAX_CHARS:
        return None
    try:
        return fn(p, text, jsonc) if fn is _json else fn(p, text)
    except Exception:                                # RecursionError on absurd nesting, a parser bug: no verdict
        return None


# ------------------------------------------------------------------ the note for the model
def _where(q: Problem) -> str:
    return f", line {q.line}" + (f", column {q.col}" if q.col else "") if q.line > 0 else ""


def _line_text(text: str, n: int) -> str:
    lines = text.splitlines()
    return lines[n - 1].strip() if 0 < n <= len(lines) else ""


def _snippet(text: str, q: Problem) -> list[str]:
    """The lines around the error, numbered, with a caret under the column."""
    lines = text.splitlines()
    if q.line <= 0 or not lines:
        return []
    at = min(q.line, len(lines))                     # "unexpected end of file" points one past the last line
    out = []
    for i in range(max(1, at - SNIPPET), min(len(lines), at + SNIPPET) + 1):
        src = lines[i - 1].expandtabs(4)
        out.append(f"{'>' if i == q.line else ' '} {i:>5} | {src[:160]}")
        if i == q.line and q.col > 0:
            vis = len(lines[i - 1][:q.col - 1].expandtabs(4))
            if vis < 160:
                out.append(f"  {'':>5} | {' ' * vis}^")
    return out


def report(path: str | Path, before: str | None, was_broken: bool = False) -> tuple[str, bool]:
    """After a successful write/edit: (note to append to the tool result, is the file broken now?).

    before: the file's text before the change (read_before), None for a new file. was_broken: the previous report on
    this file found an error, so a clean parse now is worth a line. Never raises."""
    try:
        return _report(Path(str(path)).expanduser(), before, was_broken)
    except Exception:
        return "", False


def _report(p: Path, before: str | None, was_broken: bool) -> tuple[str, bool]:
    text = _read(p)
    if text is None:
        return "", False
    jsonc = True if (_EXT.get(p.suffix.lower()) is _json and before is not None and not _jsonc_by_name(p)
                     and _is_jsonc_text(before)) else None     # it had comments before: it is a JSONC file
    after = check(p, text, jsonc)
    if after is None:
        return "", False
    if not after.problems:
        if not was_broken:
            return "", False
        return f"\n\n<diagnostics>\n✓ syntax OK: {p.name} parses again ({after.lang}).\n</diagnostics>", False
    old = check(p, before, jsonc) if before is not None else None
    seen_before = old.problems if old is not None else []
    new = [q for q in after.problems
           if not any(o.msg == q.msg and _line_text(before or "", o.line) == _line_text(text, q.line) for o in seen_before)]
    if not new:                                      # the same error as before the change: one short line
        q = after.problems[0]
        return (f"\n\n<diagnostics>\n⚠ still a syntax error in {p.name} ({after.lang}){_where(q)}: {q.msg} "
                f"(it was already there before this change)\n</diagnostics>"), True
    q = new[0]
    body = [f"⚠ syntax error in {p.name} after this change ({after.lang}){_where(q)}: {q.msg}"]
    body += _snippet(text, q)
    if len(new) > 1:
        body.append("Also: " + "; ".join(f"{_where(o).lstrip(', ') or 'somewhere'}: {o.msg}" for o in new[1:4])
                    + (f" (+{len(new) - 4} more)" if len(new) > 4 else ""))
    if seen_before:
        body.append("(The file already had a syntax error before this change too.)")
    body.append("The file was saved as written, but it no longer parses. Fix this first, before any other step.")
    return "\n\n<diagnostics>\n" + "\n".join(body) + "\n</diagnostics>", True


def headline(out: str) -> str | None:
    """The first line of a <diagnostics> note in a tool result (for the one-line display under the tool call)."""
    m = re.search(r"<diagnostics>\n([^\n]*)", out or "")
    return m.group(1).strip() if m else None
