#!/usr/bin/env python3
"""Validate a task breakdown and compute its order, parallel waves and critical path.

Usage:
  python task_graph.py <plan.md|plan.txt|plan.json> [--json] [--workers N]
  cat plan.md | python task_graph.py -

Line format (one task per line; bullets and checkboxes are optional):
  - [ ] T1 | Create the orders table | 2h | after: - | done: migration applies and rolls back
  - [x] T2 | Add the repository class | 3h | after: T1 | done: unit tests pass
  - [ ] T3 | Expose POST /orders | 1d | after: T1, T2 | done: contract test passes

  id | title | estimate | after: ids or '-' | done: acceptance check
  estimate: 30m, 2h, 1d (= 8h), 0.5d, or '?' when unknown.
  '[x]' marks a task already finished. Lines that do not match are ignored
  (headings, notes). A JSON file may hold a list of objects with the same keys
  (id, title, estimate, after, done, finished).

Reports: problems (cycles, unknown dependencies, duplicate ids, oversized or
unestimated tasks, missing acceptance checks, bottlenecks), a build order in
waves of tasks that can run in parallel, the critical path, and totals.
Read-only; stdlib only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict, deque

MAX_TASK_H = 8.0
LINE = re.compile(r"^\s*(?:[-*+]\s*)?(?:\[(?P<chk>[ xX])\]\s*)?(?P<id>[A-Za-z][\w.-]*\d[\w.-]*|\d+[\w.-]*)\s*\|(?P<rest>.*)$")


def parse_est(s: str):
    s = s.strip().lower()
    if s in ("", "?", "tbd", "-"):
        return None
    m = re.fullmatch(r"([\d.]+)\s*(m|min|h|hr|hrs|d|day|days|w)?", s)
    if not m:
        return None
    v = float(m.group(1))
    unit = m.group(2) or "h"
    return v * {"m": 1 / 60, "min": 1 / 60, "h": 1, "hr": 1, "hrs": 1, "d": 8, "day": 8, "days": 8, "w": 40}[unit]


def parse_text(text: str) -> list[dict]:
    tasks = []
    for raw in text.splitlines():
        m = LINE.match(raw)
        if not m:
            continue
        fields = [f.strip() for f in m.group("rest").split("|")]
        task = {"id": m.group("id"), "title": fields[0] if fields else "", "estimate_raw": "", "after": [], "done": "", "finished": (m.group("chk") or " ").lower() == "x"}
        for f in fields[1:]:
            low = f.lower()
            if low.startswith("after:"):
                deps = f.split(":", 1)[1]
                task["after"] = [d.strip() for d in re.split(r"[,\s]+", deps) if d.strip() and d.strip() != "-"]
            elif low.startswith("done:"):
                task["done"] = f.split(":", 1)[1].strip()
            elif not task["estimate_raw"]:
                task["estimate_raw"] = f
        tasks.append(task)
    return tasks


def parse_json(text: str) -> list[dict]:
    data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("tasks", [])
    out = []
    for d in data:
        out.append({
            "id": str(d.get("id", "")), "title": d.get("title", ""),
            "estimate_raw": str(d.get("estimate", "")),
            "after": [str(x) for x in d.get("after", [])] if isinstance(d.get("after"), list) else [x for x in re.split(r"[,\s]+", str(d.get("after", ""))) if x and x != "-"],
            "done": d.get("done", ""), "finished": bool(d.get("finished", False)),
        })
    return out


def find_cycle(deps: dict[str, list[str]], nodes: set[str]):
    color: dict[str, int] = {}
    path: list[str] = []

    def dfs(u):
        color[u] = 1
        path.append(u)
        for v in deps.get(u, []):
            if v not in nodes:
                continue
            if color.get(v, 0) == 0:
                r = dfs(v)
                if r:
                    return r
            elif color[v] == 1:
                return path[path.index(v):] + [v]
        path.pop()
        color[u] = 2
        return None

    for n in sorted(nodes):
        if color.get(n, 0) == 0:
            r = dfs(n)
            if r:
                return r
    return None


def fmt(h: float | None) -> str:
    if h is None:
        return "?"
    if h < 1:
        return f"{round(h * 60)}m"
    if h % 8 == 0 and h >= 8:
        return f"{int(h // 8)}d"
    return f"{h:g}h"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--workers", type=int, default=1, help="people/agents working in parallel, for the duration estimate")
    a = ap.parse_args()
    text = sys.stdin.read() if a.plan == "-" else open(a.plan, encoding="utf-8", errors="replace").read()
    try:
        tasks = parse_json(text) if text.lstrip().startswith(("[", "{")) else parse_text(text)
    except (json.JSONDecodeError, AttributeError) as e:
        print(f"error: cannot parse plan: {e}", file=sys.stderr)
        return 1
    if not tasks:
        print("No tasks found. Expected lines like:  - [ ] T1 | title | 2h | after: - | done: check", file=sys.stderr)
        return 1

    problems: list[tuple[str, str]] = []
    by_id: dict[str, dict] = {}
    for t in tasks:
        if t["id"] in by_id:
            problems.append(("ERROR", f"duplicate id {t['id']}"))
        by_id[t["id"]] = t
        t["h"] = parse_est(t["estimate_raw"])
    ids = set(by_id)
    deps = {t["id"]: list(dict.fromkeys(t["after"])) for t in tasks}
    for tid, ds in deps.items():
        for d in ds:
            if d not in ids:
                problems.append(("ERROR", f"{tid} depends on unknown task {d}"))
            if d == tid:
                problems.append(("ERROR", f"{tid} depends on itself"))
    cyc = find_cycle({k: [d for d in v if d != k] for k, v in deps.items()}, ids)
    if cyc:
        problems.append(("ERROR", "dependency cycle (each task waits for the next): " + " -> ".join(cyc)))

    for t in tasks:
        tid = t["id"]
        if t["h"] is None and not t["finished"]:
            problems.append(("WARN", f"{tid} has no estimate ('?' tasks hide risk; spike it or split it)"))
        elif t["h"] and t["h"] > MAX_TASK_H and not t["finished"]:
            problems.append(("WARN", f"{tid} is {fmt(t['h'])}: over {fmt(MAX_TASK_H)}, split it so progress is visible"))
        if not t["done"] and not t["finished"]:
            problems.append(("WARN", f"{tid} has no 'done:' acceptance check (how will anyone know it is finished?)"))
        if not t["title"]:
            problems.append(("WARN", f"{tid} has no title"))
        elif re.match(r"^(handle|deal with|work on|misc|various|improve|fix stuff|todo|etc)\b", t["title"], re.I):
            problems.append(("INFO", f"{tid} title '{t['title']}' is vague; name the outcome"))

    dependents: dict[str, list[str]] = defaultdict(list)
    for tid, ds in deps.items():
        for d in ds:
            if d in ids:
                dependents[d].append(tid)
    if len(tasks) >= 6:
        for tid in ids:
            if len(dependents[tid]) >= max(4, len(tasks) // 2):
                problems.append(("INFO", f"{tid} blocks {len(dependents[tid])} tasks: a bottleneck; do it first and keep it small"))

    fatal = any(s == "ERROR" for s, _ in problems)
    order, waves, cp, total = [], [], [], 0.0
    if not fatal:
        indeg = {t: len([d for d in deps[t] if d in ids]) for t in ids}
        q = deque(sorted(t for t, n in indeg.items() if n == 0))
        while q:
            u = q.popleft()
            order.append(u)
            for v in sorted(dependents[u]):
                indeg[v] -= 1
                if indeg[v] == 0:
                    q.append(v)
        level: dict[str, int] = {}
        es: dict[str, float] = {}
        ef: dict[str, float] = {}
        for u in order:
            ds = [d for d in deps[u] if d in ids]
            level[u] = 1 + max((level[d] for d in ds), default=-1)
            dur = 0.0 if by_id[u]["finished"] else (by_id[u]["h"] or 0.0)
            es[u] = max((ef[d] for d in ds), default=0.0)
            ef[u] = es[u] + dur
        end = max(ef.values()) if ef else 0.0
        ls: dict[str, float] = {}
        lf: dict[str, float] = {}
        for u in reversed(order):
            dur = 0.0 if by_id[u]["finished"] else (by_id[u]["h"] or 0.0)
            lf[u] = min((ls[v] for v in dependents[u]), default=end)
            ls[u] = lf[u] - dur
        crit = [u for u in order if abs(ls[u] - es[u]) < 1e-9 and not by_id[u]["finished"]]
        # one critical chain, following the zero-slack tasks in order
        cp = crit
        nwaves = max(level.values(), default=-1) + 1
        waves = [[u for u in order if level[u] == i] for i in range(nwaves)]
        total = sum(0.0 if t["finished"] else (t["h"] or 0.0) for t in tasks)

    remaining = [t for t in tasks if not t["finished"]]
    unknown = sum(1 for t in remaining if t["h"] is None)
    result = {
        "tasks": len(tasks), "finished": len(tasks) - len(remaining), "problems": [{"severity": s, "message": m} for s, m in problems],
        "waves": waves, "critical_path": cp, "total_hours": total,
        "duration_hours_with_workers": None,
    }
    if not fatal:
        result["duration_hours_with_workers"] = max(total / max(a.workers, 1), (max(ef.values()) if ef else 0.0))
    if a.json:
        print(json.dumps(result, indent=2))
        return 2 if fatal else 0

    print(f"Tasks: {len(tasks)} ({result['finished']} finished, {len(remaining)} remaining; {unknown} unestimated)\n")
    if problems:
        order_s = {"ERROR": 0, "WARN": 1, "INFO": 2}
        for s, m in sorted(problems, key=lambda x: order_s[x[0]]):
            print(f"[{s}] {m}")
        print()
    if fatal:
        print("Fix the errors above, then run again. No order is computed for an invalid graph.")
        return 2
    print("Build order (tasks in the same wave can run in parallel):")
    for i, w in enumerate(waves, 1):
        items = ", ".join(f"{u}{' (done)' if by_id[u]['finished'] else ''} [{fmt(by_id[u]['h'])}]" for u in w)
        print(f"  Wave {i}: {items}")
    print()
    print("Critical path (any delay here delays everything): " + (" -> ".join(cp) if cp else "none (all finished)"))
    print(f"Remaining effort: {fmt(total)} ({total / 8:.1f} working days of effort)")
    dur = result["duration_hours_with_workers"]
    print(f"Shortest possible duration with {max(a.workers, 1)} worker(s): {fmt(dur)}  (the critical path bounds it from below)")
    if unknown:
        print(f"Note: {unknown} task(s) have no estimate and count as 0 here, so these numbers are optimistic.")
    print("Estimates are guesses: add a buffer (commonly 25 to 50%) and re-plan after the first wave.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
