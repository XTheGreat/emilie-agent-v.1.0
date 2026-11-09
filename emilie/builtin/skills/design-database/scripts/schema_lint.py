#!/usr/bin/env python3
"""Lint a relational schema from SQL DDL files or a SQLite database.

Usage:
  python schema_lint.py <file.sql | dir | file.db|.sqlite|.sqlite3> [...] [--json]

Reads CREATE TABLE / CREATE INDEX statements (and ALTER TABLE ... ADD
[CONSTRAINT] FOREIGN KEY / PRIMARY KEY), builds a model, prints it, and flags
design problems with a severity (WARN / INFO) and a reason. Read-only, stdlib
only. Heuristics: a finding is a question to answer, not a verdict.

Limits: dialect-neutral regex parser. Vendor-specific syntax (partitions,
generated columns, triggers, views, enum types) is skipped, not interpreted.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

MONEY = re.compile(r"(price|amount|total|cost|balance|fee|tax|salary|revenue|subtotal|discount|payment)", re.I)
FLOAT_T = re.compile(r"^(float|real|double|double precision|float4|float8)\b", re.I)
DATE_NAME = re.compile(r"(_at|_on|_date|_time|^date|^created|^updated|^deleted|timestamp)$", re.I)
TEXT_T = re.compile(r"^(var)?char|^text|^string|^nvarchar|^clob", re.I)
STATUSY = re.compile(r"^(status|state|type|kind|role|category|level|stage)$", re.I)


def strip_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    return re.sub(r"--[^\n]*", " ", sql)


def split_top(s: str) -> list[str]:
    out, depth, cur, q = [], 0, [], None
    for ch in s:
        if q:
            cur.append(ch)
            if ch == q:
                q = None
            continue
        if ch in "'\"`":
            q = ch
            cur.append(ch)
        elif ch == "(":
            depth += 1
            cur.append(ch)
        elif ch == ")":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if "".join(cur).strip():
        out.append("".join(cur).strip())
    return out


def unq(name: str) -> str:
    name = name.strip()
    name = name.split(".")[-1]
    return name.strip('`"[]').lower()


def cols_of(s: str) -> list[str]:
    m = re.search(r"\(([^)]*)\)", s)
    if not m:
        return []
    return [unq(re.split(r"\s+", c.strip())[0]) for c in m.group(1).split(",") if c.strip()]


def find_statements(sql: str):
    sql = strip_comments(sql)
    for m in re.finditer(r"\bCREATE\s+(?:(?:GLOBAL\s+|LOCAL\s+)?(?:TEMP|TEMPORARY)\s+|UNLOGGED\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([^\s(]+)\s*\(", sql, re.I):
        start = m.end()
        depth, i, q = 1, start, None
        while i < len(sql) and depth:
            ch = sql[i]
            if q:
                if ch == q:
                    q = None
            elif ch in "'\"`":
                q = ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            i += 1
        yield ("table", unq(m.group(1)), sql[start : i - 1])
    for m in re.finditer(r"\bCREATE\s+(UNIQUE\s+)?INDEX\s+(?:CONCURRENTLY\s+)?(?:IF\s+NOT\s+EXISTS\s+)?([^\s(]+)\s+ON\s+(?:ONLY\s+)?([^\s(]+)\s*(?:USING\s+\w+\s*)?\(([^;]*?)\)\s*(?:WHERE[^;]*)?;?", sql, re.I):
        cols = [unq(re.split(r"\s+", c.strip())[0]) for c in split_top(m.group(4))]
        yield ("index", unq(m.group(2)), (unq(m.group(3)), cols, bool(m.group(1))))
    for m in re.finditer(r"\bALTER\s+TABLE\s+(?:ONLY\s+)?(?:IF\s+EXISTS\s+)?([^\s]+)\s+ADD\s+(?:CONSTRAINT\s+\S+\s+)?((?:FOREIGN|PRIMARY)\s+KEY[^;]*)", sql, re.I):
        yield ("alter", unq(m.group(1)), m.group(2))


def parse(sql_texts: list[str]):
    tables: dict[str, dict] = {}
    indexes: list[dict] = []
    for sql in sql_texts:
        for kind, name, body in find_statements(sql):
            if kind == "table":
                t = {"name": name, "columns": [], "pk": [], "fks": [], "uniques": [], "checks": 0}
                for part in split_top(body):
                    low = part.lower().lstrip()
                    if re.match(r"(constraint\s+\S+\s+)?primary\s+key", low):
                        t["pk"] = cols_of(part)
                    elif re.match(r"(constraint\s+\S+\s+)?foreign\s+key", low):
                        r = re.search(r"references\s+([^\s(]+)\s*(?:\(([^)]*)\))?", part, re.I)
                        t["fks"].append({
                            "cols": cols_of(part),
                            "ref": unq(r.group(1)) if r else "?",
                            "ref_cols": [unq(c) for c in r.group(2).split(",")] if r and r.group(2) else [],
                            "on_delete": bool(re.search(r"on\s+delete", part, re.I)),
                        })
                    elif re.match(r"(constraint\s+\S+\s+)?unique", low):
                        t["uniques"].append(cols_of(part))
                    elif re.match(r"(constraint\s+\S+\s+)?check", low):
                        t["checks"] += 1
                    elif re.match(r"(key|index|fulltext|spatial|exclude|like|period)\b", low):
                        c = cols_of(part)
                        if c:
                            indexes.append({"name": "(inline)", "table": name, "cols": c, "unique": low.startswith("unique")})
                    else:
                        cm = re.match(r"\s*([`\"\[]?[\w$]+[`\"\]]?)\s+(.*)", part, re.S)
                        if not cm:
                            continue
                        cname, rest = unq(cm.group(1)), cm.group(2)
                        tm = re.match(r"([A-Za-z_][\w ]*?(?:\([^)]*\))?)(?=\s+(?:not|null|primary|unique|default|references|check|constraint|generated|collate|auto_increment|autoincrement|identity)\b|\s*$)", rest, re.I)
                        ctype = (tm.group(1) if tm else rest.split()[0]).strip()
                        up = rest.lower()
                        col = {
                            "name": cname, "type": ctype,
                            "not_null": bool(re.search(r"\bnot\s+null\b", up)),
                            "default": bool(re.search(r"\bdefault\b", up)),
                            "pk": bool(re.search(r"\bprimary\s+key\b", up)),
                            "unique": bool(re.search(r"\bunique\b", up)),
                            "check": bool(re.search(r"\bcheck\b", up)),
                        }
                        r = re.search(r"\breferences\s+([^\s(]+)\s*(?:\(([^)]*)\))?", rest, re.I)
                        if r:
                            t["fks"].append({
                                "cols": [cname], "ref": unq(r.group(1)),
                                "ref_cols": [unq(c) for c in r.group(2).split(",")] if r.group(2) else [],
                                "on_delete": bool(re.search(r"on\s+delete", rest, re.I)),
                            })
                        if col["pk"]:
                            t["pk"] = [cname]
                        if col["check"]:
                            t["checks"] += 1
                        t["columns"].append(col)
                tables[name] = t
            elif kind == "index":
                tname, cols, uniq = body
                indexes.append({"name": name, "table": tname, "cols": cols, "unique": uniq})
            else:
                t = tables.get(name)
                if t is None:
                    continue
                if re.match(r"primary", body, re.I):
                    t["pk"] = cols_of(body)
                else:
                    r = re.search(r"references\s+([^\s(]+)\s*(?:\(([^)]*)\))?", body, re.I)
                    t["fks"].append({
                        "cols": cols_of(body), "ref": unq(r.group(1)) if r else "?",
                        "ref_cols": [unq(c) for c in r.group(2).split(",")] if r and r.group(2) else [],
                        "on_delete": bool(re.search(r"on\s+delete", body, re.I)),
                    })
    return tables, indexes


def base_type(t: str) -> str:
    return re.sub(r"\(.*\)", "", t.lower()).strip()


INT_FAMILY = {"int", "integer", "bigint", "smallint", "serial", "bigserial", "int4", "int8", "tinyint", "mediumint"}


def type_family(t: str) -> str:
    b = base_type(t)
    if b in INT_FAMILY:
        return "int"
    if b in ("uuid", "char", "varchar", "text", "string", "nvarchar") or "char" in b:
        return "uuid/text" if b == "uuid" else "text"
    return b


def lint(tables: dict, indexes: list) -> list[dict]:
    out: list[dict] = []

    def add(sev, table, msg, why):
        out.append({"severity": sev, "table": table, "finding": msg, "why": why})

    covered: dict[str, list[list[str]]] = {}
    for t in tables.values():
        lead = []
        if t["pk"]:
            lead.append(t["pk"])
        lead.extend(t["uniques"])
        for c in t["columns"]:
            if c["unique"]:
                lead.append([c["name"]])
        covered[t["name"]] = lead
    for ix in indexes:
        covered.setdefault(ix["table"], []).append(ix["cols"])

    names = list(tables)
    plural = sum(1 for n in names if n.endswith("s") and not n.endswith("ss"))
    mixed_plural = names and 0 < plural < len(names) and min(plural, len(names) - plural) >= max(1, len(names) // 5)
    if mixed_plural:
        add("INFO", "(all)", "table names mix singular and plural", "pick one convention so names are predictable")
    if names and any(re.search(r"[A-Z]", n) for n in names) and any("_" in n for n in names):
        add("INFO", "(all)", "table names mix camelCase and snake_case", "one naming style avoids quoting and confusion")

    for t in tables.values():
        n = t["name"]
        colmap = {c["name"]: c for c in t["columns"]}
        if not t["pk"]:
            add("WARN", n, "no primary key", "rows cannot be addressed or replicated reliably; add a key")
        if len(t["columns"]) > 30:
            add("INFO", n, f"{len(t['columns'])} columns", "wide tables often hide several entities or sparse attributes")
        for c in t["columns"]:
            cn, ty = c["name"], c["type"]
            if MONEY.search(cn) and FLOAT_T.match(ty):
                add("WARN", n, f"{cn} is {ty}", "binary floats cannot represent decimal money exactly; use DECIMAL/NUMERIC or integer minor units")
            if DATE_NAME.search(cn) and TEXT_T.match(ty):
                add("WARN", n, f"{cn} is {ty}", "store dates and times in a date/timestamp type so ordering, ranges and time zones work")
            if re.fullmatch(r"(password|passwd|pwd)", cn, re.I):
                add("WARN", n, f"column named {cn}", "never store plain passwords; store a salted slow hash (name it password_hash)")
            if re.search(r"(card_?number|cvv|ssn|secret|api_?key|token)$", cn, re.I) and not re.search(r"(hash|encrypted|last4|_id)$", cn, re.I):
                add("WARN", n, f"{cn} may hold a sensitive value in clear", "encrypt, tokenize or do not store it; document the retention rule")
            if STATUSY.match(cn) and TEXT_T.match(ty) and not c["check"] and not t["checks"]:
                add("INFO", n, f"{cn} is free text", "constrain allowed values (CHECK, enum, or a lookup table) so typos cannot enter")
            if re.fullmatch(r"(email|username|slug|sku|code)", cn, re.I) and not any(
                lead and lead[0] == cn for lead in covered.get(n, [])
            ):
                add("INFO", n, f"{cn} has no unique constraint or index", "if it identifies a row, enforce uniqueness in the database; if it is searched, index it")
        if not any(re.search(r"(created|inserted|added)_?(at|on|date|time)?$", c, re.I) for c in colmap) and len(t["columns"]) > 3:
            add("INFO", n, "no created-at column", "useful for debugging, audits and archiving; skip for pure lookup or join tables")
        for fk in t["fks"]:
            if fk["ref"] not in tables and fk["ref"] != "?":
                add("INFO", n, f"FK {fk['cols']} references {fk['ref']} which is not in the input", "schema may be incomplete")
            else:
                ref = tables.get(fk["ref"])
                if ref and len(fk["cols"]) == 1:
                    rc = fk["ref_cols"][0] if fk["ref_cols"] else (ref["pk"][0] if len(ref["pk"]) == 1 else None)
                    rcol = next((c for c in ref["columns"] if c["name"] == rc), None)
                    lcol = colmap.get(fk["cols"][0])
                    if rcol and lcol and type_family(rcol["type"]) != type_family(lcol["type"]):
                        add("WARN", n, f"{fk['cols'][0]} ({lcol['type']}) references {fk['ref']}.{rc} ({rcol['type']})", "mismatched key types force casts and can defeat indexes")
            if not any(lead[: len(fk["cols"])] == fk["cols"] for lead in covered.get(n, [])):
                add("WARN", n, f"FK {fk['cols']} -> {fk['ref']} has no index starting with it", "joins and cascading deletes on the parent will scan this table")
            if not fk["on_delete"]:
                add("INFO", n, f"FK {fk['cols']} -> {fk['ref']} has no ON DELETE rule", "state the intent: RESTRICT, CASCADE or SET NULL (the default is usually 'no action')")
        fkcols = {c for fk in t["fks"] for c in fk["cols"]}
        if len(t["fks"]) >= 2 and len(t["columns"]) <= len(fkcols) + 3 and not any(
            set(fkcols) <= set(u) for u in t["uniques"] + [t["pk"]]
        ):
            add("WARN", n, "looks like a join table without a composite key", "duplicate links are possible; make the pair the primary key or unique")

    seen = {}
    for ix in indexes:
        key = (ix["table"], tuple(ix["cols"]))
        if key in seen:
            add("INFO", ix["table"], f"index {ix['name']} duplicates {seen[key]}", "drop one; each index slows writes")
        seen[key] = ix["name"]
    for ix in indexes:
        for other in indexes:
            if other is ix or other["table"] != ix["table"] or ix["unique"]:
                continue
            if len(ix["cols"]) < len(other["cols"]) and other["cols"][: len(ix["cols"])] == ix["cols"]:
                add("INFO", ix["table"], f"index {ix['name']} {ix['cols']} is a prefix of {other['name']} {other['cols']}", "usually redundant; verify before dropping")
                break
    return out


def load_inputs(paths: list[str]) -> tuple[list[str], list[str]]:
    texts, sources = [], []
    for p in paths:
        pp = Path(p)
        files = []
        if pp.is_dir():
            files = [f for f in pp.rglob("*") if f.suffix.lower() in {".sql", ".db", ".sqlite", ".sqlite3"} and "node_modules" not in f.parts and ".git" not in f.parts]
        elif pp.is_file():
            files = [pp]
        for f in files:
            if f.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
                try:
                    con = sqlite3.connect(f"file:{f.as_posix()}?mode=ro", uri=True)
                    rows = con.execute("select sql from sqlite_master where sql is not null and name not like 'sqlite_%'").fetchall()
                    con.close()
                    texts.append(";\n".join(r[0] for r in rows) + ";")
                    sources.append(str(f))
                except sqlite3.Error as e:
                    print(f"warning: cannot read {f}: {e}", file=sys.stderr)
            else:
                texts.append(f.read_text(encoding="utf-8", errors="replace"))
                sources.append(str(f))
    return texts, sources


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    texts, sources = load_inputs(a.paths)
    if not texts:
        print("No .sql files or SQLite databases found.", file=sys.stderr)
        return 1
    tables, indexes = parse(texts)
    if not tables:
        print("No CREATE TABLE statements found (are the schema files migrations written in an ORM DSL? read those by hand).")
        return 0
    findings = lint(tables, indexes)
    if a.json:
        print(json.dumps({"sources": sources, "tables": tables, "indexes": indexes, "findings": findings}, indent=2))
        return 0
    print(f"Sources: {len(sources)} | tables: {len(tables)} | indexes: {len(indexes)}\n")
    for t in tables.values():
        fk = "; ".join(f"{','.join(f['cols'])}->{f['ref']}" for f in t["fks"])
        print(f"  {t['name']}  ({len(t['columns'])} cols)  pk={','.join(t['pk']) or 'NONE'}" + (f"  fk: {fk}" if fk else ""))
    print()
    order = {"WARN": 0, "INFO": 1}
    for f in sorted(findings, key=lambda x: (order[x["severity"]], x["table"])):
        print(f"[{f['severity']}] {f['table']}: {f['finding']}\n        why: {f['why']}")
    w = sum(1 for f in findings if f["severity"] == "WARN")
    print(f"\n{w} warning(s), {len(findings) - w} note(s). Findings are prompts to decide, not verdicts.")
    print("Limits: regex parser; views, triggers, partitions, enum types and ORM-only definitions are not read.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
