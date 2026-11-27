"""The Tests panel: the project's test suites (pytest, unittest, Vitest, Jest, go test, cargo test, or a plain
`npm test`), run as a background job and read back test by test: its name, file and line, how it ended, how long it
took and, when it failed, why. Pytest, Vitest and Jest write machine-readable reports (JUnit XML / JSON) that are
read after the run; go test streams JSON; unittest and cargo print lines that are read as they are."""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from .projkit import node_bin, norm, project_dirs, pythons, read_json, read_toml, rel, run_full

MARKERS = ("package.json", "pyproject.toml", "setup.py", "setup.cfg", "pytest.ini", "tox.ini", "conftest.py",
           "requirements.txt", "Cargo.toml", "go.mod", "tests", "test")
_HAS_PYTEST: dict[str, tuple[float, bool]] = {}


def _has_pytest(py: str, d: Path) -> bool:
    k = norm(py)
    c = _HAS_PYTEST.get(k)
    if c and time.time() - c[0] < 120:
        return c[1]
    code, _o, _e = run_full([py, "-c", "import pytest"], str(d), 20)
    _HAS_PYTEST[k] = (time.time(), code == 0)
    return code == 0


def _py_tests(d: Path) -> bool:
    if any((d / m).exists() for m in ("pytest.ini", "conftest.py")):
        return True
    t = read_toml(d / "pyproject.toml") if (d / "pyproject.toml").is_file() else {}
    if "pytest" in (t.get("tool") or {}):
        return True
    for sub in ("tests", "test"):
        if (d / sub).is_dir() and any(n.startswith("test") and n.endswith(".py") for n in _names(d / sub)):
            return True
    return any(n.startswith("test_") and n.endswith(".py") for n in _names(d))


def _names(d: Path) -> list[str]:
    try:
        return os.listdir(d)
    except OSError:
        return []


def _deps(pkg: dict) -> dict:
    out: dict = {}
    for k in ("dependencies", "devDependencies"):
        if isinstance(pkg.get(k), dict):
            out.update(pkg[k])
    return out


def detect(root: str, python: str = "") -> dict:
    """{suites: [{id, kind, label, dir, cmd}], pythons: [...]} for this project."""
    if not root or not os.path.isdir(root):
        return {"suites": [], "pythons": []}
    base = Path(root)
    suites: list[dict] = []
    pys = pythons(root)
    py = python or (pys[0]["path"] if pys else "python")
    for r in project_dirs(root, MARKERS, depth=2, limit=12):
        d = base / r
        where = f" · {r}" if r else ""
        if _py_tests(d) and not any(s["kind"] in ("pytest", "unittest") and (not s["dir"] or r.startswith(s["dir"] + "/")) for s in suites):
            if _has_pytest(py, d):
                suites.append({"id": f"pytest:{r}", "kind": "pytest", "label": "pytest" + where, "dir": r, "cmd": "python -m pytest"})
            else:
                start = "tests" if (d / "tests").is_dir() else "test" if (d / "test").is_dir() else "."
                suites.append({"id": f"unittest:{r}", "kind": "unittest", "label": "unittest" + where, "dir": r,
                               "cmd": f"python -m unittest discover -s {start}"})
        pkg = read_json(d / "package.json") if (d / "package.json").is_file() else {}
        deps = _deps(pkg)
        if "vitest" in deps and node_bin(d, base, "vitest"):
            suites.append({"id": f"vitest:{r}", "kind": "vitest", "label": "Vitest" + where, "dir": r, "cmd": "vitest run"})
        elif "jest" in deps and node_bin(d, base, "jest"):
            suites.append({"id": f"jest:{r}", "kind": "jest", "label": "Jest" + where, "dir": r, "cmd": "jest"})
        else:
            test = str((pkg.get("scripts") or {}).get("test") or "")
            if test and "no test specified" not in test:
                suites.append({"id": f"npm:{r}", "kind": "npm", "label": "npm test" + where, "dir": r, "cmd": test})
        if (d / "go.mod").is_file() and shutil.which("go"):
            suites.append({"id": f"go:{r}", "kind": "go", "label": "go test" + where, "dir": r, "cmd": "go test ./..."})
        if (d / "Cargo.toml").is_file() and shutil.which("cargo"):
            suites.append({"id": f"cargo:{r}", "kind": "cargo", "label": "cargo test" + where, "dir": r, "cmd": "cargo test"})
    return {"suites": suites, "pythons": pys}


# ---------------------------------------------------------------------------------------------------- one result
def _t(tid: str, name: str, suite: str, file: str, abs_: str, line: int, status: str, secs: float, message: str = "",
       output: str = "") -> dict:
    return {"id": tid, "name": name, "suite": suite, "file": file, "abs": abs_, "line": line or 0, "status": status,
            "secs": round(secs or 0, 3), "message": message[:20000], "output": output[-20000:]}


def _find_line(p: Path, name: str) -> int:
    """The line a test function is defined on (unittest gives none)."""
    try:
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if re.match(rf"\s*(?:async\s+)?def\s+{re.escape(name)}\s*\(", line):
                return i
    except OSError:
        pass
    return 0


# ---------------------------------------------------------------------------------------------------- pytest
def parse_junit(xml_text: str, root: Path, d: Path) -> list[dict]:
    res = []
    try:
        tree = ET.fromstring(xml_text)
    except ET.ParseError:
        return res
    for tc in tree.iter("testcase"):
        name = tc.get("name", "")
        cls = tc.get("classname", "")
        file = tc.get("file", "")
        status, message = "passed", ""
        for tag, st in (("failure", "failed"), ("error", "failed"), ("skipped", "skipped")):
            el = tc.find(tag)
            if el is not None:
                status = st
                message = ((el.get("message") or "") + "\n\n" + (el.text or "")).strip()
                break
        out = "\n".join(x.text or "" for x in (tc.find("system-out"), tc.find("system-err")) if x is not None).strip()
        if file:
            mod = file[:-3].replace("/", ".").replace("\\", ".") if file.endswith(".py") else ""
            rest = cls[len(mod) + 1:] if mod and cls.startswith(mod + ".") else ""
            node = "::".join([file.replace("\\", "/")] + ([rest.replace(".", "::")] if rest else []) + [name])
        else:
            parts = cls.split(".")
            node = cls + "::" + name
            file = "/".join(parts[:-1]) + ".py" if len(parts) > 1 else ""
            rest = parts[-1] if len(parts) > 1 else ""
        ab = Path(os.path.normpath(str(d / file))) if file else d
        try:
            line = int(tc.get("line") or 0) + 1 if tc.get("line") else 0
        except ValueError:
            line = 0
        res.append(_t(node, name, rest or Path(file).stem, rel(root, ab) if file else "", str(ab) if file else "", line, status,
                      float(tc.get("time") or 0), message, out))
    return res


# ---------------------------------------------------------------------------------------------------- unittest
_UT_LINE = re.compile(r"^(\w+) \(([\w.]+)\)(?:\n.*?)? \.\.\. (ok|FAIL|ERROR|skipped.*|expected failure|unexpected success)$", re.M)
_UT_FAIL = re.compile(r"^(FAIL|ERROR): (\w+) \(([\w.]+)\)\n(?:[^\n]*\n)?-{60,}\n(.*?)(?=\n={60,}\n|\n-{60,}\nRan |\Z)", re.M | re.S)


def parse_unittest(out: str, root: Path, d: Path, start: str = ".") -> list[dict]:
    """start: the folder discovery ran in. When it is not a package its modules are top level ("test_x.Case.test_y")
    and are looked for in it."""
    tests: dict[str, dict] = {}
    for m in _UT_LINE.finditer(out):
        name, where, verdict = m.group(1), m.group(2), m.group(3)
        tid = where if where.endswith("." + name) else f"{where}.{name}"
        status = "passed" if verdict in ("ok", "expected failure") else "skipped" if verdict.startswith("skipped") else "failed"
        tests[tid] = {"name": name, "status": status, "message": verdict[8:].strip(" '\"") if status == "skipped" else ""}
    for m in _UT_FAIL.finditer(out):
        name, where = m.group(2), m.group(3)
        tid = where if where.endswith("." + name) else f"{where}.{name}"
        t = tests.setdefault(tid, {"name": name, "status": "failed", "message": ""})
        t["status"] = "failed"
        t["message"] = m.group(4).strip()
    res = []
    for tid, t in tests.items():
        parts = tid.split(".")
        mod_parts = parts[:-2] if len(parts) > 2 else parts[:-1]
        cls = parts[-2] if len(parts) > 2 else ""
        p = d.joinpath(*mod_parts).with_suffix(".py") if mod_parts else d
        if mod_parts and not p.is_file():
            p = (d / start).joinpath(*mod_parts).with_suffix(".py")
        line = _find_line(p, t["name"]) if p.is_file() else 0
        res.append(_t(tid, t["name"], cls or (mod_parts[-1] if mod_parts else ""), rel(root, p) if p.is_file() else "",
                      str(p) if p.is_file() else "", line, t["status"], 0, t["message"]))
    return res


# ---------------------------------------------------------------------------------------------------- vitest / jest
def parse_jest_json(data: dict, root: Path, d: Path) -> list[dict]:
    res = []
    for f in data.get("testResults") or []:
        fname = f.get("name") or f.get("testFilePath") or ""
        ab = Path(os.path.normpath(fname)) if fname else d
        file = rel(root, ab) if fname else ""
        assertions = f.get("assertionResults") or []
        for a in assertions:
            st = a.get("status")
            status = "passed" if st == "passed" else "failed" if st == "failed" else "skipped"
            full = a.get("fullName") or " ".join([*(a.get("ancestorTitles") or []), a.get("title") or ""]).strip()
            loc = a.get("location") or {}
            msg = "\n\n".join(_strip_ansi(str(x)) for x in a.get("failureMessages") or [])
            res.append(_t(f"{file}::{full}", a.get("title") or full, " › ".join(a.get("ancestorTitles") or []) or Path(file).name,
                          file, str(ab), int(loc.get("line") or 0), status, (a.get("duration") or 0) / 1000, msg))
        if not assertions and f.get("status") == "failed":          # the file did not even load
            res.append(_t(f"{file}::(file)", "(could not run this file)", Path(file).name, file, str(ab), 0, "failed", 0,
                          _strip_ansi(str(f.get("message") or f.get("failureMessage") or ""))))
    return res


_ANSI = re.compile(r"\x1b\[[\d;?]*[A-Za-z]")


def _strip_ansi(s: str) -> str:
    return _ANSI.sub("", s)


# ---------------------------------------------------------------------------------------------------- go / cargo
def parse_go_json(out: str, root: Path, d: Path) -> list[dict]:
    tests: dict[str, dict] = {}
    order: list[str] = []
    for line in out.splitlines():
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        name, pkg = ev.get("Test"), ev.get("Package") or ""
        if not name:
            continue
        key = f"{pkg}::{name}"
        if key not in tests:
            tests[key] = {"pkg": pkg, "name": name, "status": "passed", "secs": 0.0, "output": []}
            order.append(key)
        t = tests[key]
        act = ev.get("Action")
        if act == "output":
            t["output"].append(ev.get("Output") or "")
        elif act in ("pass", "fail", "skip"):
            t["status"] = {"pass": "passed", "fail": "failed", "skip": "skipped"}[act]
            t["secs"] = float(ev.get("Elapsed") or 0)
    res = []
    for key in order:
        t = tests[key]
        text = "".join(t["output"])
        m = re.search(r"([\w./-]+_test\.go):(\d+):", text)
        ab = None
        if m:
            cand = list(d.rglob(Path(m.group(1)).name))[:1] if not (d / m.group(1)).exists() else [d / m.group(1)]
            ab = cand[0] if cand else None
        res.append(_t(key, t["name"], t["pkg"].rsplit("/", 1)[-1], rel(root, ab) if ab else "", str(ab) if ab else "",
                      int(m.group(2)) if m and ab else 0, t["status"], t["secs"],
                      text.strip() if t["status"] == "failed" else "", text))
    return res


_CARGO_LINE = re.compile(r"^test (\S+) \.\.\. (ok|FAILED|ignored)", re.M)
_CARGO_FAIL = re.compile(r"^---- (\S+) stdout ----\n(.*?)(?=\n---- \S+ stdout ----\n|\n\nfailures:\n|\Z)", re.M | re.S)


def parse_cargo(out: str, root: Path, d: Path) -> list[dict]:
    fails = {m.group(1): m.group(2).strip() for m in _CARGO_FAIL.finditer(out)}
    res = []
    for m in _CARGO_LINE.finditer(out):
        name, verdict = m.group(1), m.group(2)
        status = {"ok": "passed", "FAILED": "failed", "ignored": "skipped"}[verdict]
        msg = fails.get(name, "")
        loc = re.search(r"([\w./\\-]+\.rs):(\d+):\d+", msg)
        ab = (d / loc.group(1)) if loc and (d / loc.group(1)).exists() else None
        res.append(_t(name, name.rsplit("::", 1)[-1], name.rsplit("::", 1)[0] if "::" in name else "", rel(root, ab) if ab else "",
                      str(ab) if ab else "", int(loc.group(2)) if loc and ab else 0, status, 0, msg))
    return res


# ---------------------------------------------------------------------------------------------------- running
def _summary(tests: list[dict], secs: float) -> dict:
    s = {"passed": 0, "failed": 0, "skipped": 0}
    for t in tests:
        s[t["status"]] = s.get(t["status"], 0) + 1
    return {**s, "total": len(tests), "secs": round(secs, 2)}


def _rx(names: list[str]) -> str:
    return "^(" + "|".join(re.escape(n) for n in names) + ")$"


def run_tests(job, root: str, suite_id: str, python: str = "", only: list[str] | None = None) -> dict:
    """Run one suite (all of it, or only the tests whose ids are given)."""
    base = Path(root)
    info = detect(root, python)
    suite = next((s for s in info["suites"] if s["id"] == suite_id), None)
    if not suite:
        raise ValueError("That test suite is no longer found in this project.")
    d = base / suite["dir"]
    py = python or (info["pythons"][0]["path"] if info["pythons"] else "python")
    only = [o for o in (only or []) if isinstance(o, str) and o and not o.startswith("-")]
    tmp = tempfile.mkdtemp(prefix="emilie-tests-")
    t0 = time.time()
    kind = suite["kind"]
    tests: list[dict] = []
    try:
        if kind == "pytest":
            xml = os.path.join(tmp, "report.xml")
            args = [py, "-m", "pytest", "-q", "--color=no", "-o", "junit_family=xunit1", f"--junitxml={xml}", *only]
            job.say("$ " + " ".join(["python", *args[1:3], *only]))
            code, out = job.run(args, cwd=str(d))
            if os.path.exists(xml):
                tests = parse_junit(Path(xml).read_text(encoding="utf-8", errors="replace"), base, d)
        elif kind == "unittest":
            start = "tests" if (d / "tests").is_dir() else "test" if (d / "test").is_dir() else "."
            # a test folder that is a package is imported from the project folder ("tests.test_x"); one that is not,
            # from itself ("test_x"): -t would make discovery fail there
            top = ["-t", "."] if start == "." or (d / start / "__init__.py").exists() else []
            args = [py, "-m", "unittest", "discover", "-v", "-s", start, *top]
            for o in only:                                   # run some: their ids as name patterns
                args += ["-k", o]
            job.say("$ python " + " ".join(args[1:]))
            code, out = job.run(args, cwd=str(d))
            tests = parse_unittest(out, base, d, start)
        elif kind in ("vitest", "jest"):
            report = os.path.join(tmp, "report.json")
            files = sorted({o.split("::", 1)[0] for o in only})
            names = [o.split("::", 1)[1] for o in only if "::" in o and not o.endswith("::(file)")]
            files = [str(Path(os.path.normpath(str(base / f)))) for f in files if f]
            binp = node_bin(d, base, kind)
            if not binp:
                raise ValueError(f"{kind} is not installed in node_modules: run the package manager's install first.")
            if kind == "vitest":
                args = [binp, "run", "--reporter=default", "--reporter=json", f"--outputFile.json={report}", *files]
            else:
                args = [binp, "--json", f"--outputFile={report}", "--testLocationInResults", "--ci", *files]
            if names:
                args += ["-t", _rx(names)]
            job.say(f"$ {kind} " + " ".join(a for a in args[1:] if not a.startswith(("--output", "--reporter=json"))))
            code, out = job.run(args, cwd=str(d), env=dict(os.environ, FORCE_COLOR="0", CI="1"))
            if os.path.exists(report):
                try:
                    tests = parse_jest_json(json.loads(Path(report).read_text(encoding="utf-8", errors="replace")), base, d)
                except ValueError:
                    tests = []
        elif kind == "go":
            pkgs = sorted({o.split("::", 1)[0] for o in only}) or ["./..."]
            names = sorted({o.split("::", 1)[1].split("/", 1)[0] for o in only if "::" in o})
            args = ["go", "test", "-json", *(["-run", _rx(names)] if names else []), *pkgs]
            job.say("$ " + " ".join(a for a in args if a != "-json"))
            code, out = job.run(args, cwd=str(d))
            tests = parse_go_json(out, base, d)
        elif kind == "cargo":
            args = ["cargo", "test", "--no-fail-fast"] + ([only[0], "--", "--exact"] if len(only) == 1 else [])
            job.say("$ " + " ".join(args))
            code, out = job.run(args, cwd=str(d))
            tests = parse_cargo(out, base, d)
        else:                                                # npm test: one verdict for the whole run
            pkg = read_json(d / "package.json")
            from .scripts import _pm
            pm = _pm(d, pkg)
            exe = shutil.which(pm) or pm
            job.say(f"$ {pm} test")
            code, out = job.run([exe, "test"], cwd=str(d), env=dict(os.environ, CI="1", FORCE_COLOR="0"))
            tests = [_t("npm-test", f"{pm} test", suite["dir"] or Path(root).name, "package.json" if not suite["dir"] else f"{suite['dir']}/package.json",
                        str(d / "package.json"), 0, "passed" if code == 0 else "failed", time.time() - t0,
                        _strip_ansi(out[-8000:]) if code else "")]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    secs = time.time() - t0
    err = ""
    if not tests and code not in (0, 5):                   # pytest's 5: no tests collected
        err = f"The run ended with exit code {code} and no test results: see the output."
    return {"suite": suite_id, "kind": kind, "tests": tests, "summary": _summary(tests, secs), "code": code,
            "tail": _strip_ansi(out[-8000:]), "error": err, "only": bool(only), "at": time.time()}
