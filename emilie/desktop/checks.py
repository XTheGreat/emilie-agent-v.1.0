"""The Problems panel: the project's own type checkers and linters (TypeScript, ESLint, Ruff, mypy, Pyright, Flake8,
cargo check, go vet, plus a built-in Python syntax check that needs nothing installed), found from its files and
run as one background job. Each tool's report is read into one list: file, line, column, severity, message, rule."""
from __future__ import annotations

import ast
import json
import os
import re
import time
import warnings
from pathlib import Path

from .projkit import Stopped, inside, project_dirs, project_files, read_jsonc, read_toml, rel, tool

MARKERS = ("package.json", "tsconfig.json", "pyproject.toml", "setup.cfg", "setup.py", "requirements.txt", "tox.ini",
           "ruff.toml", ".ruff.toml", "mypy.ini", ".flake8", "pyrightconfig.json", "Cargo.toml", "go.mod")
ESLINT_CONFIGS = ("eslint.config.js", "eslint.config.mjs", "eslint.config.cjs", "eslint.config.ts", "eslint.config.mts",
                  ".eslintrc", ".eslintrc.js", ".eslintrc.cjs", ".eslintrc.json", ".eslintrc.yml", ".eslintrc.yaml")
MAX_PROBLEMS = 3000


def _ini_has(p: Path, section: str) -> bool:
    try:
        return f"[{section}]" in p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def _has_py(d: Path) -> bool:
    if any((d / m).exists() for m in ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt")):
        return True
    try:
        return any(n.endswith(".py") for n in os.listdir(d))
    except OSError:
        return False


def detect(root: str) -> list[dict]:
    """The checkers this project can run: [{id, kind, label, dir, cmd}]."""
    if not root or not os.path.isdir(root):
        return []
    base = Path(root)
    out: list[dict] = []

    def add(kind: str, label: str, r: str, args: list[str] | None) -> None:
        out.append({"id": f"{kind}:{r}", "kind": kind, "label": label, "dir": r,
                    "cmd": " ".join(Path(args[0]).name if i == 0 else a for i, a in enumerate(args)) if args else "built in"})

    for r in project_dirs(root, MARKERS, depth=2, limit=12):
        d = base / r
        a = _args(base, d)
        if a.get("tsc"):
            add("tsc", "TypeScript", r, a["tsc"])
        if a.get("eslint"):
            add("eslint", "ESLint", r, a["eslint"])
        if a.get("ruff"):
            add("ruff", "Ruff", r, a["ruff"])
        if a.get("mypy"):
            add("mypy", "mypy", r, a["mypy"])
        if a.get("pyright"):
            add("pyright", "Pyright", r, a["pyright"])
        if a.get("flake8"):
            add("flake8", "Flake8", r, a["flake8"])
        # one syntax check covers the folders under it
        if _has_py(d) and not any(c["kind"] == "pysyntax" and (not c["dir"] or r.startswith(c["dir"] + "/")) for c in out):
            add("pysyntax", "Python syntax", r, None)
        if a.get("cargo"):
            add("cargo", "cargo check", r, a["cargo"])
        if a.get("govet"):
            add("govet", "go vet", r, a["govet"])
    return out


def _args(root: Path, d: Path) -> dict[str, list[str]]:
    """The command line of each checker that applies in folder d."""
    out: dict[str, list[str]] = {}
    pkg = d / "package.json"
    if (d / "tsconfig.json").is_file():
        tsc = tool(d, root, "tsc", node=True)
        if tsc:
            cfg = read_jsonc(d / "tsconfig.json")
            only_refs = bool(cfg.get("references")) and cfg.get("files") == [] and not cfg.get("include")
            out["tsc"] = [tsc, "-b", "--pretty", "false"] if only_refs else [tsc, "--noEmit", "--pretty", "false", "-p", "tsconfig.json"]
    if any((d / c).exists() for c in ESLINT_CONFIGS) or (pkg.is_file() and '"eslintConfig"' in _text(pkg)):
        es = tool(d, root, "eslint", node=True)
        if es and "node_modules" in es:
            out["eslint"] = [es, ".", "-f", "json"]
    py = read_toml(d / "pyproject.toml") if (d / "pyproject.toml").is_file() else {}
    pytool = py.get("tool") or {}
    ruff = tool(d, root, "ruff", python=True)
    if ruff and ("ruff" in pytool or (d / "ruff.toml").exists() or (d / ".ruff.toml").exists() or inside(root, ruff)):
        out["ruff"] = [ruff, "check", "--output-format", "json", "--no-cache", "."]
    if "mypy" in pytool or (d / "mypy.ini").exists() or (d / ".mypy.ini").exists() or _ini_has(d / "setup.cfg", "mypy"):
        mypy = tool(d, root, "mypy", python=True)
        if mypy:
            files = bool((pytool.get("mypy") or {}).get("files")) if isinstance(pytool.get("mypy"), dict) else False
            out["mypy"] = [mypy, "--no-color-output", "--no-error-summary", "--show-column-numbers", "--no-pretty"] + ([] if files else ["."])
    if (d / "pyrightconfig.json").exists() or "pyright" in pytool:
        pr = tool(d, root, "pyright", node=True, python=True)
        if pr:
            out["pyright"] = [pr, "--outputjson"]
    if (d / ".flake8").exists() or _ini_has(d / "setup.cfg", "flake8") or _ini_has(d / "tox.ini", "flake8"):
        f8 = tool(d, root, "flake8", python=True)
        if f8:
            out["flake8"] = [f8]
    if (d / "Cargo.toml").is_file():
        cargo = tool(d, root, "cargo")
        if cargo:
            out["cargo"] = [cargo, "check", "--message-format=short", "--all-targets"]
    if (d / "go.mod").is_file():
        go = tool(d, root, "go")
        if go:
            out["govet"] = [go, "vet", "./..."]
    return out


def _text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


# ---------------------------------------------------------------------------------------------------- reports
def _p(root: Path, d: Path, file: str, line, col, sev: str, msg: str, code: str, source: str) -> dict:
    f = Path(file)
    ab = f if f.is_absolute() else (d / f)
    ab = Path(os.path.normpath(str(ab)))
    try:
        line = int(line or 0)
    except (TypeError, ValueError):
        line = 0
    try:
        col = int(col or 0)
    except (TypeError, ValueError):
        col = 0
    return {"file": rel(root, ab), "abs": str(ab), "line": max(line, 0), "col": max(col, 0),
            "severity": sev if sev in ("error", "warning", "info") else "error", "message": msg.strip(),
            "code": str(code or ""), "source": source}


_TSC = re.compile(r"^(.+?)\((\d+),(\d+)\): (error|warning|message) (TS\d+): (.*)$")


def parse_tsc(out: str, root: Path, d: Path) -> list[dict]:
    res: list[dict] = []
    for line in out.splitlines():
        m = _TSC.match(line.strip("\r"))
        if m:
            sev = {"message": "info"}.get(m.group(4), m.group(4))
            res.append(_p(root, d, m.group(1), m.group(2), m.group(3), sev, m.group(6), m.group(5), "TypeScript"))
        elif res and line.startswith("  ") and line.strip():
            res[-1]["message"] += "\n" + line.strip()
    return res


def _json_after(out: str, start: str):
    """The JSON value a tool printed, ignoring anything it printed before it."""
    i = out.find(start)
    while i >= 0:
        try:
            return json.JSONDecoder().raw_decode(out[i:])[0]
        except ValueError:
            i = out.find(start, i + 1)
    return None


def parse_eslint(out: str, root: Path, d: Path) -> list[dict]:
    data = _json_after(out, "[")
    res = []
    for f in data if isinstance(data, list) else []:
        for m in f.get("messages") or []:
            sev = "error" if m.get("severity") == 2 or m.get("fatal") else "warning"
            res.append(_p(root, d, f.get("filePath", ""), m.get("line"), m.get("column"), sev, m.get("message", ""),
                          m.get("ruleId") or "", "ESLint"))
    return res


def parse_ruff(out: str, root: Path, d: Path) -> list[dict]:
    data = _json_after(out, "[")
    res = []
    for m in data if isinstance(data, list) else []:
        loc = m.get("location") or {}
        code = m.get("code") or ""
        sev = "error" if not code or code.startswith(("E9", "F82", "F63", "F7")) or "syntax" in str(m.get("message", "")).lower() else "warning"
        res.append(_p(root, d, m.get("filename", ""), loc.get("row"), loc.get("column"), sev, m.get("message", ""), code, "Ruff"))
    return res


_MYPY = re.compile(r"^(.+?):(\d+):(?:(\d+):)? (error|warning|note): (.*?)(?:  \[([\w-]+)\])?$")


def parse_mypy(out: str, root: Path, d: Path) -> list[dict]:
    res = []
    for line in out.splitlines():
        m = _MYPY.match(line.strip("\r"))
        if m:
            sev = "info" if m.group(4) == "note" else m.group(4)
            if sev == "info" and res and res[-1]["file"] == rel(root, d / m.group(1)) and res[-1]["line"] == int(m.group(2)):
                res[-1]["message"] += "\n" + m.group(5)
                continue
            res.append(_p(root, d, m.group(1), m.group(2), m.group(3), sev, m.group(5), m.group(6) or "", "mypy"))
    return res


def parse_pyright(out: str, root: Path, d: Path) -> list[dict]:
    data = _json_after(out, "{")
    res = []
    for m in (data or {}).get("generalDiagnostics") or [] if isinstance(data, dict) else []:
        st = ((m.get("range") or {}).get("start") or {})
        sev = {"information": "info"}.get(m.get("severity"), m.get("severity") or "error")
        res.append(_p(root, d, m.get("file", ""), (st.get("line") or 0) + 1, (st.get("character") or 0) + 1, sev,
                      m.get("message", ""), m.get("rule") or "", "Pyright"))
    return res


_FLAKE8 = re.compile(r"^(.+?):(\d+):(\d+): ([A-Z]+\d+) (.*)$")


def parse_flake8(out: str, root: Path, d: Path) -> list[dict]:
    res = []
    for line in out.splitlines():
        m = _FLAKE8.match(line.strip("\r"))
        if m:
            sev = "error" if m.group(4).startswith(("E9", "F82", "F63", "F7")) else "warning"
            res.append(_p(root, d, m.group(1), m.group(2), m.group(3), sev, m.group(5), m.group(4), "Flake8"))
    return res


_GENERIC = re.compile(r"^(?:vet: )?((?:[A-Za-z]:)?[^\s:][^:]*?\.\w+):(\d+):(?:(\d+):)?\s*(?:(error|warning|note)(?:\[(\w+)\])?:\s*)?(.+)$")


def parse_generic(out: str, root: Path, d: Path, source: str) -> list[dict]:
    """path:line:col: [error|warning[CODE]:] message (cargo --message-format=short, go vet, compilers)."""
    res = []
    for line in out.splitlines():
        m = _GENERIC.match(line.strip("\r"))
        if m and not m.group(1).startswith(("http", "#")):
            sev = {"note": "info"}.get(m.group(4) or "", m.group(4) or "error")
            res.append(_p(root, d, m.group(1), m.group(2), m.group(3), sev, m.group(6), m.group(5) or "", source))
    return res


def python_syntax(root: Path, d: Path, job=None) -> list[dict]:
    """Every .py file of the project compiled (not run): what would stop it from even starting."""
    res = []
    files = project_files(str(d), (".py", ".pyw"), limit=8000)
    for i, f in enumerate(files):
        if job is not None and job.stopped:
            raise Stopped()
        p = d / f
        try:
            if p.stat().st_size > 2_000_000:
                continue
            src = p.read_bytes()
        except OSError:
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                compile(src, str(p), "exec", ast.PyCF_ONLY_AST, dont_inherit=True)
        except SyntaxError as e:
            res.append(_p(root, d, f, e.lineno or 1, e.offset or 1, "error", e.msg or "invalid syntax", type(e).__name__, "Python"))
        except (ValueError, TypeError) as e:
            res.append(_p(root, d, f, 1, 1, "error", str(e), "ValueError", "Python"))
    if job is not None:
        job.say(f"{len(files)} Python files compiled, {len(res)} with errors")
    return res


PARSERS = {"tsc": parse_tsc, "eslint": parse_eslint, "ruff": parse_ruff, "mypy": parse_mypy, "pyright": parse_pyright,
           "flake8": parse_flake8}


def run_checks(job, root: str, ids: list[str]) -> dict:
    """Run the chosen checkers one after the other; the job's result grows as each one finishes."""
    base = Path(root)
    known = {c["id"]: c for c in detect(root)}
    chosen = [known[i] for i in ids if i in known] or list(known.values())
    results: list[dict] = []
    job.result = {"results": results, "pending": [c["id"] for c in chosen]}
    total = 0
    for c in chosen:
        if job.stopped:
            raise Stopped()
        d = base / c["dir"]
        job.say(f"▸ {c['label']}{' · ' + c['dir'] if c['dir'] else ''}")
        t0 = time.time()
        entry = {"id": c["id"], "kind": c["kind"], "label": c["label"], "dir": c["dir"], "problems": [], "code": 0,
                 "secs": 0.0, "tail": "", "error": ""}
        try:
            if c["kind"] == "pysyntax":
                entry["problems"] = python_syntax(base, d, job)
            else:
                args = _args(base, d).get(c["kind"])
                if not args:
                    entry["error"] = "The tool is no longer there."
                else:
                    code, out = job.run(args, cwd=str(d), timeout=900)
                    entry["code"] = code
                    parse = PARSERS.get(c["kind"])
                    probs = parse(out, base, d) if parse else parse_generic(out, base, d, c["label"])
                    entry["problems"] = probs
                    entry["tail"] = out[-6000:]
                    if code not in (0, 1) and not probs:
                        entry["error"] = f"{c['label']} stopped with exit code {code} and reported nothing it found: see its output."
                    elif code == 1 and not probs and c["kind"] in ("tsc", "eslint", "ruff", "pyright", "mypy"):
                        entry["error"] = f"{c['label']} failed (exit code 1) without a readable report: see its output."
        except Stopped:
            raise
        except Exception as e:
            entry["error"] = f"{type(e).__name__}: {e}"
        entry["problems"] = entry["problems"][:MAX_PROBLEMS]
        total += len(entry["problems"])
        entry["secs"] = round(time.time() - t0, 2)
        results.append(entry)
        job.result = {"results": results, "pending": [x["id"] for x in chosen[len(results):]]}
        job.say(f"  {len(entry['problems'])} problem{'s' if len(entry['problems']) != 1 else ''} · {entry['secs']}s")
    return {"results": results, "pending": [], "at": time.time()}
