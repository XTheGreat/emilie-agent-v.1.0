#!/usr/bin/env python3
"""Measure before you optimize: profile Python code, time commands, compare two commands fairly.

Usage:
  python perf.py cprofile [--top 20] [--sort tottime|cumulative] [--paths DIR] [--callers NAME] [-m] TARGET [args ...]
  python perf.py memory   [--top 15] [-m] TARGET [args ...]
  python perf.py time     [-n 10] [--warmup 1] [--timeout 600] [--cwd DIR] -- COMMAND [args ...]
  python perf.py compare  [-n 15] [--warmup 1] [--timeout 600] [--cwd DIR] -- COMMAND_A [args] -- COMMAND_B [args]

cprofile  Runs a Python script (or module with -m) under cProfile in THIS interpreter (use your project's venv python to run perf.py)
          and prints the hottest functions by own time and by cumulative time, how much time is spent inside your code (--paths, default the
          current folder) vs libraries, and with --callers NAME who calls a function and what it calls.
memory    Runs the target under tracemalloc and prints the peak and the source lines that allocated the most memory.
time      Runs a command N times (after warm-up runs) and prints min / median / mean / stdev / p90 / max wall-clock seconds.
compare   Alternates runs of command A and B (to cancel drift), then reports medians, the ratio, and a 95% bootstrap confidence
          interval for the difference: it says "no clear difference" when the data cannot tell them apart.

Standard library only. Profilers add overhead and change timings: use them to find WHERE time goes, use `time`/`compare` to measure HOW
MUCH. Commands run as given (no shell), with output discarded. Limits: cProfile sees Python calls only (not time inside C extensions
other than as the calling function's own time, not I/O wait attribution beyond wall time); multi-process and async work needs other tools.
"""
from __future__ import annotations

import argparse
import cProfile
import io
import os
import pstats
import random
import runpy
import statistics
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path


def _run_target(module: bool, target: str, args: list[str]) -> None:
    if module:
        sys.argv = [target] + args
        runpy.run_module(target, run_name="__main__", alter_sys=True)
    else:
        p = Path(target)
        if not p.is_file():
            raise SystemExit(f"error: {target} not found")
        sys.argv = [str(p)] + args
        sys.path.insert(0, str(p.resolve().parent))
        runpy.run_path(str(p), run_name="__main__")


def cprofile_cmd(a) -> int:
    pr = cProfile.Profile()
    t0 = time.perf_counter()
    try:
        pr.enable()
        try:
            _run_target(a.module, a.target, a.args)
        finally:
            pr.disable()
    except SystemExit as e:
        if isinstance(e.code, str):
            print(e.code, file=sys.stderr)
            return 2
    wall = time.perf_counter() - t0
    st = pstats.Stats(pr)
    root = os.path.abspath(a.paths)
    rows = []
    mine = lib = 0.0
    for (fn, ln, name), (cc, nc, tt, ct, _callers) in st.stats.items():
        if os.path.abspath(fn) == os.path.abspath(__file__) or "runpy" in fn or name in ("<built-in method builtins.exec>", "<method 'disable' of '_lsprof.Profiler' objects>"):
            continue                                   # the harness itself is not part of the program being measured
        inproj = os.path.abspath(fn).startswith(root) if not fn.startswith("<") and not fn.startswith("~") else False
        if inproj:
            mine += tt
        else:
            lib += tt
        rows.append((fn, ln, name, nc, tt, ct, inproj))
    total = mine + lib or 1e-9
    print(f"Wall time under the profiler: {wall:.2f}s (profiling overhead inflates it). Own time in your code ({root}): {100 * mine / total:.0f}%, libraries/builtins: {100 * lib / total:.0f}%\n")

    def show(title, key):
        print(title)
        print(f"  {'calls':>9} {'own s':>8} {'cum s':>8}  function")
        for fn, ln, name, nc, tt, ct, inproj in sorted(rows, key=key, reverse=True)[: a.top]:
            try:
                short = os.path.relpath(fn, root) if inproj else (Path(fn).name if not fn.startswith(("<", "~")) else fn)
            except ValueError:
                short = fn
            print(f"  {nc:>9} {tt:>8.3f} {ct:>8.3f}  {name} ({short}:{ln}){' *' if inproj else ''}")
        print()
    show("Hottest by OWN time (time spent in the function itself; * = your code):", lambda r: r[4])
    show("Hottest by CUMULATIVE time (including everything it calls):", lambda r: r[5])
    if a.callers:
        s = io.StringIO()
        ps = pstats.Stats(pr, stream=s)
        ps.print_callers(a.callers)
        ps.print_callees(a.callers)
        print(f"Callers and callees matching '{a.callers}':\n" + s.getvalue()[:4000])
    print("Read the 'own time' table for the loop or call that dominates; check calls counts for things done too often (a function called 1e6 times is a design question,\n"
          "a slow function called once is an algorithm question). Fix the top item, then measure again with `perf.py time`.")
    return 0


def memory_cmd(a) -> int:
    tracemalloc.start(15)
    try:
        _run_target(a.module, a.target, a.args)
    except SystemExit as e:
        if isinstance(e.code, str):
            print(e.code, file=sys.stderr)
    cur, peak = tracemalloc.get_traced_memory()
    snap = tracemalloc.take_snapshot()
    tracemalloc.stop()
    snap = snap.filter_traces((tracemalloc.Filter(False, "<frozen*"), tracemalloc.Filter(False, tracemalloc.__file__)))
    print(f"Peak traced memory: {peak / 1048576:.1f} MiB; still allocated at exit: {cur / 1048576:.1f} MiB (Python allocations only; native/C memory is not counted)\n")
    print("Source lines holding the most memory at exit:")
    for st in snap.statistics("lineno")[: a.top]:
        fr = st.traceback[0]
        print(f"  {st.size / 1024:>10.1f} KiB  {st.count:>7} blocks  {fr.filename}:{fr.lineno}")
    print("\nPeak can be far above the 'at exit' figure: temporary lists/copies. Look for whole-file reads, list() around generators, accumulating caches, and copies in loops.")
    return 0


def run_once(cmd, cwd, timeout) -> tuple[float, int]:
    t0 = time.perf_counter()
    try:
        r = subprocess.run(cmd, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, timeout=timeout)
        return time.perf_counter() - t0, r.returncode
    except subprocess.TimeoutExpired:
        return time.perf_counter() - t0, 124


def stats_line(xs: list[float]) -> str:
    xs_sorted = sorted(xs)
    p90 = xs_sorted[min(len(xs) - 1, int(0.9 * len(xs)))]
    sd = statistics.stdev(xs) if len(xs) > 1 else 0.0
    return (f"min {min(xs):.3f}s  median {statistics.median(xs):.3f}s  mean {statistics.mean(xs):.3f}s  stdev {sd:.3f}s  p90 {p90:.3f}s  max {max(xs):.3f}s")


def split_commands(rest: list[str]) -> list[list[str]]:
    cmds, cur = [], []
    for tok in rest:
        if tok == "--":
            if cur:
                cmds.append(cur)
            cur = []
        else:
            cur.append(tok)
    if cur:
        cmds.append(cur)
    return cmds


def time_cmd(a) -> int:
    cmds = split_commands(a.command)
    if len(cmds) != 1:
        print("error: give exactly one command after --", file=sys.stderr)
        return 2
    cmd = cmds[0]
    for _ in range(a.warmup):
        t, rc = run_once(cmd, a.cwd, a.timeout)
        if rc != 0:
            print(f"error: the command failed during warm-up (exit {rc}); fix it first", file=sys.stderr)
            return 1
    xs = []
    for i in range(a.n):
        t, rc = run_once(cmd, a.cwd, a.timeout)
        if rc != 0:
            print(f"error: run {i + 1} failed (exit {rc}); timing a failing command is meaningless", file=sys.stderr)
            return 1
        xs.append(t)
    print(f"{' '.join(cmd)}\n  {a.n} runs (+{a.warmup} warm-up): " + stats_line(xs))
    if len(xs) > 2 and statistics.stdev(xs) > 0.15 * statistics.mean(xs):
        print("  NOTE: high variance (stdev over 15% of the mean). Close other programs, raise -n, or compare medians, not single runs.")
    return 0


def bootstrap_ci(a: list[float], b: list[float], iters: int = 4000):
    rnd = random.Random(1234)
    diffs = []
    for _ in range(iters):
        ra = [rnd.choice(a) for _ in a]
        rb = [rnd.choice(b) for _ in b]
        diffs.append(statistics.median(rb) - statistics.median(ra))
    diffs.sort()
    return diffs[int(0.025 * iters)], diffs[int(0.975 * iters)]


def compare_cmd(a) -> int:
    cmds = split_commands(a.command)
    if len(cmds) != 2:
        print("error: give two commands separated by --:  compare -- A args -- B args", file=sys.stderr)
        return 2
    A, B = cmds
    for c in (A, B):
        for _ in range(a.warmup):
            t, rc = run_once(c, a.cwd, a.timeout)
            if rc != 0:
                print(f"error: {' '.join(c)} failed during warm-up (exit {rc})", file=sys.stderr)
                return 1
    xa, xb = [], []
    for i in range(a.n):
        first, second = (A, B) if i % 2 == 0 else (B, A)           # alternate order to cancel drift and cache effects
        for c in (first, second):
            t, rc = run_once(c, a.cwd, a.timeout)
            if rc != 0:
                print(f"error: {' '.join(c)} failed (exit {rc})", file=sys.stderr)
                return 1
            (xa if c is A else xb).append(t)
    ma, mb = statistics.median(xa), statistics.median(xb)
    lo, hi = bootstrap_ci(xa, xb)
    print(f"A: {' '.join(A)}\n   " + stats_line(xa))
    print(f"B: {' '.join(B)}\n   " + stats_line(xb))
    ratio = mb / ma if ma else float("inf")
    print(f"\nmedian B - A = {mb - ma:+.3f}s  (95% CI {lo:+.3f}s .. {hi:+.3f}s)   B/A = {ratio:.2f}x")
    if lo > 0:
        print(f"Verdict: A is faster, about {100 * (1 - ma / mb):.0f}% less time (the interval excludes zero).")
    elif hi < 0:
        print(f"Verdict: B is faster, about {100 * (1 - mb / ma):.0f}% less time (the interval excludes zero).")
    else:
        print("Verdict: no clear difference: the interval includes zero. More runs (-n), a quieter machine, or a larger workload may reveal one.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="mode", required=True)
    c = sub.add_parser("cprofile")
    c.add_argument("--top", type=int, default=20)
    c.add_argument("--sort", default="tottime")
    c.add_argument("--paths", default=".")
    c.add_argument("--callers")
    c.add_argument("-m", "--module", action="store_true")
    c.add_argument("target")
    c.add_argument("args", nargs=argparse.REMAINDER)
    m = sub.add_parser("memory")
    m.add_argument("--top", type=int, default=15)
    m.add_argument("-m", "--module", action="store_true")
    m.add_argument("target")
    m.add_argument("args", nargs=argparse.REMAINDER)
    for name in ("time", "compare"):
        t = sub.add_parser(name)
        t.add_argument("-n", type=int, default=10 if name == "time" else 15)
        t.add_argument("--warmup", type=int, default=1)
        t.add_argument("--timeout", type=int, default=600)
        t.add_argument("--cwd", default=None)
        t.add_argument("command", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    return {"cprofile": cprofile_cmd, "memory": memory_cmd, "time": time_cmd, "compare": compare_cmd}[a.mode](a)


if __name__ == "__main__":
    sys.exit(main())
