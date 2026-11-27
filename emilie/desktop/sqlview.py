"""The Database panel: SQLite files of the project (db.sqlite3, dev.db, *.sqlite …) opened read-only by default:
their tables and views with columns and row counts, a page of rows, and any SQL statement (one at a time). Changes
need "Allow changes" in the panel, which opens the file writable for that statement only."""
from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from urllib.parse import quote

from .projkit import project_files

EXTS = (".db", ".sqlite", ".sqlite3", ".db3", ".s3db", ".sl3")
MAX_ROWS = 1000
MAX_SECONDS = 15


def _is_sqlite(p: Path) -> bool:
    try:
        with p.open("rb") as fh:
            return fh.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False


def files(cwd: str) -> dict:
    if not cwd or not os.path.isdir(cwd):
        return {"files": []}
    out = []
    for r in project_files(cwd, EXTS, limit=20000):
        p = Path(cwd) / r
        if _is_sqlite(p):
            try:
                size = p.stat().st_size
            except OSError:
                size = 0
            out.append({"rel": r, "abs": str(p), "size": size})
    return {"files": out[:200]}


def _connect(path: str, write: bool = False) -> sqlite3.Connection:
    p = Path(path)
    if not p.is_file() or not _is_sqlite(p):
        raise ValueError("Not an SQLite database file.")
    uri = "file:" + quote(str(p.resolve()).replace("\\", "/"), safe="/:") + ("?mode=rw" if write else "?mode=ro")
    con = sqlite3.connect(uri, uri=True, timeout=5, check_same_thread=False)
    deadline = time.monotonic() + MAX_SECONDS
    con.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 20000)   # stops a runaway query
    return con


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def tables(path: str) -> dict:
    con = _connect(path)
    try:
        rows = con.execute("SELECT name, type, sql FROM sqlite_master WHERE type IN ('table','view') "
                           "AND name NOT LIKE 'sqlite_%' ORDER BY type, name").fetchall()
        out = []
        for name, typ, sql in rows:
            cols = [{"name": c[1], "type": c[2] or "", "notnull": bool(c[3]), "default": c[4], "pk": int(c[5] or 0)}
                    for c in con.execute(f"PRAGMA table_info({_q(name)})").fetchall()]
            try:
                n = con.execute(f"SELECT COUNT(*) FROM (SELECT 1 FROM {_q(name)} LIMIT 100001)").fetchone()[0]
            except sqlite3.Error:
                n = None
            out.append({"name": name, "type": typ, "columns": cols, "rows": n, "more": n is not None and n > 100000,
                        "sql": sql or ""})
        return {"tables": out, "size": Path(path).stat().st_size}
    finally:
        con.close()


def _cell(v):
    if isinstance(v, bytes):
        return {"blob": len(v)}
    if isinstance(v, float) and v != v:              # NaN is not JSON
        return None
    return v


def browse(path: str, table: str, offset: int = 0, limit: int = 200, order: str = "", desc: bool = False) -> dict:
    con = _connect(path)
    try:
        names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')").fetchall()}
        if table not in names:
            raise ValueError("No such table.")
        cols = [c[1] for c in con.execute(f"PRAGMA table_info({_q(table)})").fetchall()]
        by = f" ORDER BY {_q(order)}{' DESC' if desc else ''}" if order in cols else ""
        limit = max(1, min(int(limit), MAX_ROWS))
        offset = max(0, int(offset))
        t0 = time.perf_counter()
        cur = con.execute(f"SELECT * FROM {_q(table)}{by} LIMIT ? OFFSET ?", (limit, offset))
        rows = [[_cell(v) for v in r] for r in cur.fetchall()]
        return {"columns": [d[0] for d in cur.description or []], "rows": rows, "offset": offset,
                "ms": round((time.perf_counter() - t0) * 1000, 1)}
    finally:
        con.close()


def query(path: str, sql: str, write: bool = False) -> dict:
    sql = (sql or "").strip()
    if not sql:
        raise ValueError("Write an SQL statement first.")
    con = _connect(path, write)
    try:
        t0 = time.perf_counter()
        try:
            cur = con.execute(sql)
        except sqlite3.OperationalError as e:
            if "readonly" in str(e).lower() or "read-only" in str(e).lower():
                raise ValueError("This statement changes the database: turn on Allow changes to run it.")
            if "interrupted" in str(e).lower():
                raise ValueError(f"Stopped: the query ran longer than {MAX_SECONDS} seconds.")
            raise ValueError(str(e))
        except sqlite3.Warning as e:                         # more than one statement
            raise ValueError(f"{e} Run one statement at a time.")
        except sqlite3.Error as e:
            raise ValueError(str(e))
        cols = [d[0] for d in cur.description or []]
        rows = [[_cell(v) for v in r] for r in cur.fetchmany(MAX_ROWS + 1)] if cols else []
        if write:
            con.commit()
        return {"columns": cols, "rows": rows[:MAX_ROWS], "cut": len(rows) > MAX_ROWS,
                "changes": con.total_changes if write else 0, "ms": round((time.perf_counter() - t0) * 1000, 1)}
    finally:
        con.close()
