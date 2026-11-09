"""Jupyter notebook tools: edit cells and run a notebook. Standard library only.

notebook_edit  - list / get / replace / insert / append / delete / move cells, clear outputs, change cell type.
                 Several operations can be given as `edits`: they apply in order and either all succeed or the file is untouched.
notebook_run   - execute the notebook (all cells or a range) with the user's own Python and store the outputs in it.
"""
from __future__ import annotations

import copy
import json
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path

ACTIONS = ("list", "get", "replace", "insert", "append", "delete", "move", "clear_outputs", "set_type")
TYPES = ("code", "markdown", "raw")


def _load(path: str) -> tuple[Path, dict]:
    p = Path(path).expanduser()
    if p.suffix.lower() != ".ipynb":
        raise ValueError(f"{p.name} is not a .ipynb file")
    if not p.is_file():
        raise ValueError(f"{p} not found")
    try:
        nb = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        raise ValueError(f"not a valid notebook: {e}")
    if not isinstance(nb, dict) or not isinstance(nb.get("cells"), list):
        raise ValueError("not a valid notebook: no 'cells' list")
    if int(nb.get("nbformat", 4)) < 4:
        raise ValueError(f"nbformat {nb.get('nbformat')} is too old (convert it to version 4 first)")
    return p, nb


def _save(p: Path, nb: dict) -> None:
    """Same layout as nbformat writes (indent 1, sorted keys, UTF-8, final newline) so diffs stay small."""
    text = json.dumps(nb, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    tmp = p.with_name(p.name + ".emilie-tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, p)


def _src(cell: dict) -> str:
    s = cell.get("source", "")
    return "".join(s) if isinstance(s, list) else str(s)


def _split(text: str) -> list[str]:
    return text.splitlines(keepends=True)


def _new_id(nb: dict) -> str:
    used = {c.get("id") for c in nb["cells"]}
    while True:
        i = "%08x" % random.getrandbits(32)
        if i not in used:
            return i


def _make_cell(nb: dict, ctype: str, source: str) -> dict:
    cell: dict = {"cell_type": ctype, "metadata": {}, "source": _split(source)}
    if ctype == "code":
        cell["execution_count"] = None
        cell["outputs"] = []
    if int(nb.get("nbformat", 4)) == 4 and int(nb.get("nbformat_minor", 0)) >= 5:
        cell["id"] = _new_id(nb)
    return cell


def _clear(cell: dict) -> None:
    if cell.get("cell_type") == "code":
        cell["outputs"] = []
        cell["execution_count"] = None


def _idx(nb: dict, i, allow_end: bool = False) -> int:
    n = len(nb["cells"])
    try:
        i = int(i)
    except (TypeError, ValueError):
        raise ValueError("index must be a number (cells are numbered from 1, as read_file shows them)")
    if allow_end and i == n + 1:
        return n
    if not 1 <= i <= n:
        raise ValueError(f"cell index {i} is out of range (the notebook has {n} cells, numbered 1-{n})")
    return i - 1


def _summary(nb: dict) -> str:
    rows = []
    for i, c in enumerate(nb["cells"], 1):
        s = _src(c)
        first = next((l.strip() for l in s.splitlines() if l.strip()), "")
        extra = ""
        if c.get("cell_type") == "code":
            outs = c.get("outputs") or []
            err = any(o.get("output_type") == "error" for o in outs)
            extra = f" outputs={len(outs)}" + (" ERROR" if err else "") + (f" [{c['execution_count']}]" if c.get("execution_count") else "")
        rows.append(f"{i:>3} [{c.get('cell_type', '?')}] {len(s.splitlines())} lines{extra}: {first[:70]}")
    return "\n".join(rows) or "(no cells)"


def _apply(nb: dict, op: dict) -> str:
    a = (op.get("action") or "").strip()
    if a not in ACTIONS:
        raise ValueError(f"unknown action '{a}' (use one of: {', '.join(ACTIONS)})")
    cells = nb["cells"]
    if a == "list":
        return _summary(nb)
    if a == "get":
        i = _idx(nb, op.get("index"))
        c = cells[i]
        return f"--- cell {i + 1} [{c.get('cell_type')}] ---\n{_src(c)}"
    if a == "replace":
        i = _idx(nb, op.get("index"))
        if "source" not in op:
            raise ValueError("replace needs 'source'")
        if "\r\n" in str(op["source"]):
            op["source"] = str(op["source"]).replace("\r\n", "\n")
        cells[i]["source"] = _split(str(op["source"]))
        _clear(cells[i])           # outputs of the old code would be misleading
        if op.get("cell_type") in TYPES and op["cell_type"] != cells[i].get("cell_type"):
            return _retype(nb, i, op["cell_type"]) + f" and replaced the source of cell {i + 1}"
        return f"replaced the source of cell {i + 1} (its old outputs were cleared)"
    if a in ("insert", "append"):
        ctype = op.get("cell_type", "code")
        if ctype not in TYPES:
            raise ValueError(f"cell_type must be one of {', '.join(TYPES)}")
        if "source" not in op:
            raise ValueError(f"{a} needs 'source'")
        at = len(cells) if a == "append" else _idx(nb, op.get("index"), allow_end=True)
        cells.insert(at, _make_cell(nb, ctype, str(op["source"]).replace("\r\n", "\n")))
        return f"inserted a {ctype} cell as cell {at + 1}"
    if a == "delete":
        i = _idx(nb, op.get("index"))
        c = cells.pop(i)
        return f"deleted cell {i + 1} [{c.get('cell_type')}]"
    if a == "move":
        i = _idx(nb, op.get("index"))
        to = _idx(nb, op.get("to"))
        c = cells.pop(i)
        cells.insert(to, c)
        return f"moved cell {i + 1} to position {to + 1}"
    if a == "clear_outputs":
        if op.get("index") in (None, ""):
            n = 0
            for c in cells:
                if c.get("cell_type") == "code" and (c.get("outputs") or c.get("execution_count")):
                    n += 1
                _clear(c)
            return f"cleared the outputs of {n} cells"
        i = _idx(nb, op.get("index"))
        _clear(cells[i])
        return f"cleared the outputs of cell {i + 1}"
    if a == "set_type":
        i = _idx(nb, op.get("index"))
        t = op.get("cell_type")
        if t not in TYPES:
            raise ValueError(f"cell_type must be one of {', '.join(TYPES)}")
        return _retype(nb, i, t)
    raise AssertionError(a)


def _retype(nb: dict, i: int, t: str) -> str:
    c = nb["cells"][i]
    if c.get("cell_type") == t:
        return f"cell {i + 1} is already {t}"
    c["cell_type"] = t
    if t == "code":
        c.setdefault("outputs", [])
        c.setdefault("execution_count", None)
    else:
        c.pop("outputs", None)
        c.pop("execution_count", None)
    return f"changed cell {i + 1} to {t}"


def notebook_edit(path: str, action: str = "", index: int | None = None, source: str | None = None,
                  cell_type: str = "code", to: int | None = None, edits: list | None = None) -> str:
    try:
        p, nb = _load(path)
        ops = list(edits) if edits else [{"action": action, "index": index, "source": source, "cell_type": cell_type, "to": to}]
        if not edits and not action:
            return "ERROR: give an action (" + ", ".join(ACTIONS) + ") or a list of edits"
        work = copy.deepcopy(nb)
        results, changed = [], False
        for n, op in enumerate(ops, 1):
            if not isinstance(op, dict):
                return f"ERROR: edit {n} must be an object"
            op = {k: v for k, v in op.items() if v is not None}
            if "cell_type" not in op and op.get("action") in ("insert", "append"):
                op["cell_type"] = "code"
            try:
                msg = _apply(work, op)
            except ValueError as e:
                return f"ERROR: edit {n} ({op.get('action', '?')}): {e}. Nothing was changed."
            results.append(msg if len(ops) == 1 else f"{n}. {msg}")
            changed = changed or op.get("action") not in ("list", "get")
        if changed:
            _save(p, work)
        head = "\n".join(results)
        tail = f"\n\nnotebook now has {len(work['cells'])} cells" if changed else ""
        return head + tail
    except ValueError as e:
        return f"ERROR: {e}"
    except PermissionError:
        return f"ERROR: cannot write {Path(path).name}: it is probably open in another program (Jupyter, VS Code). Close it or save there first, then try again."
    except OSError as e:
        return f"ERROR: {e}"


# ------------------------------------------------------------------ running
def _find_python(explicit: str | None) -> str | None:
    if explicit:
        return explicit if (os.path.isfile(explicit) or shutil.which(explicit)) else None
    return shutil.which("python") or shutil.which("python3") or shutil.which("py")


def notebook_run(path: str, cells: str = "", timeout: int = 600, allow_errors: bool = False,
                 python: str = "", output_path: str = "") -> str:
    from . import tools
    try:
        p, nb = _load(path)
    except ValueError as e:
        return f"ERROR: {e}"
    py = _find_python(python or None)
    if not py:
        return "ERROR: no Python interpreter found on PATH (pass python=<full path to python.exe>)"
    out = Path(output_path).expanduser() if output_path else p
    try:
        limit = max(5, min(int(timeout), 3600))
    except (TypeError, ValueError):
        limit = 600
    script = Path(__file__).with_name("nbrun.py")
    cmd = [py, "-u", str(script), str(p), str(out), cells or "", "1" if allow_errors else "0", str(limit)]
    kw: dict = {}
    if os.name == "nt":
        kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    else:
        kw["start_new_session"] = True
    env = dict(os.environ, PYTHONIOENCODING="utf-8", MPLBACKEND="Agg")
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding="utf-8", errors="replace", cwd=str(p.parent), env=env, **kw)
    except OSError as e:
        return f"ERROR: cannot start {py}: {e}"
    waited = 0.0
    try:
        while True:
            try:
                so, se = proc.communicate(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                waited += 0.2
                if waited >= limit + 30:
                    tools._kill_group(proc)
                    return (f"ERROR: the notebook run did not finish within {limit}s and was stopped. "
                            f"Run a smaller range with cells='1-5' or raise timeout (max 3600).")
    except BaseException:
        tools._kill_group(proc)
        raise
    text = (so or "").strip()
    if proc.returncode not in (0, 1) or not text:
        return tools._clip(f"ERROR: the runner failed (exit {proc.returncode}).\n{(se or '').strip()[-1500:]}\n{text[-800:]}")
    return tools._clip(text + (f"\n[stderr]\n{se.strip()[-800:]}" if se and se.strip() else ""))


# ------------------------------------------------------------------ registry
def specs(_schema, _s, _i):
    obj = {"type": "object", "properties": {
        "action": {"type": "string", "enum": list(ACTIONS)}, "index": _i, "source": _s,
        "cell_type": {"type": "string", "enum": list(TYPES)}, "to": _i}}
    return {
        "notebook_edit": (notebook_edit, _schema(
            "notebook_edit",
            "Edit a Jupyter notebook (.ipynb) safely cell by cell - never edit the JSON with edit_file. Cells are numbered from 1 "
            "(as read_file shows them). action: list (overview), get (index), replace (index, source), insert (index = the new cell's "
            "position, source, cell_type), append (source, cell_type), delete, move (index, to), clear_outputs (index, or all), "
            "set_type. For several changes pass edits=[{action,...},...]: applied in order, all or nothing. Replacing a code cell "
            "clears its old outputs; run notebook_run afterwards to refresh them.",
            {"path": _s, "action": obj["properties"]["action"], "index": _i, "source": _s,
             "cell_type": obj["properties"]["cell_type"], "to": _i,
             "edits": {"type": "array", "items": obj}}, ["path"]), "file", True),
        "notebook_run": (notebook_run, _schema(
            "notebook_run",
            "Execute a Jupyter notebook with the user's Python (from PATH, or python=<path>) and store the outputs, figures and "
            "execution counts back into it (or into output_path). cells='1-5' or '3,7' runs only those cells (the others are "
            "left as they are; state from earlier cells is NOT available unless they are included). Uses a built-in runner "
            "(supports print output, last-expression values, display(), PIL images, DataFrames as HTML and matplotlib figures; "
            "ignores harmless % magics, skips ! shell lines, no widgets or input()). Packages must already be installed in that "
            "Python. allow_errors=true keeps going after a failing cell. timeout in seconds "
            "(default 600, max 3600). Returns a per-cell summary; read the notebook for full outputs.",
            {"path": _s, "cells": _s, "timeout": _i, "allow_errors": {"type": "boolean"}, "python": _s, "output_path": _s},
            ["path"]), "shell", True),
    }
