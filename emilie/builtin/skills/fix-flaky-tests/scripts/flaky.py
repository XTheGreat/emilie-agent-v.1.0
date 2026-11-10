#!/usr/bin/env python3
"""Find and reproduce flaky tests.

Usage:
  python flaky.py scan [path] [--top 12] [--json]
  python flaky.py run [-n 10] [--timeout 600] [--until-fail] [--env NAME=VALUE ...] [--cwd DIR] -- <test command ...>

scan  Static smells in test files that cause intermittent failures: sleeps, real clock, unseeded randomness, real network,
      fixed ports, shared temp paths, global state and environment changes, threads without join, focused tests (.only).
      Each hit says why it is a risk and the usual cure. Read-only.
run   Runs the test command N times and shows which tests failed in how many runs. A test that fails in some runs but not all is
      flaky; one that fails in all is simply broken. --until-fail stops at the first failing run and prints the tail of its output
      (the evidence you need). --env sets variables for every run (for example PYTHONHASHSEED=random, or a TZ). Understands pytest,
      unittest, jest/vitest, node --test, go test, cargo test and Maven output; with other runners only the exit codes are compared.
      The command is executed as given (no shell), in --cwd or the current folder.

Standard library only. A passing streak is not proof: N clean runs only bound the failure rate (about 3/N at 95% confidence).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "env", "dist", "build", "out", ".next", "target", "vendor", "site-packages", ".tox"}
TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec|e2e|cypress)(/|$)|\.(test|spec)\.[a-z]+$|_test\.(go|py|rb|rs)$|(^|/)test_[^/]*\.py$|Tests?\.(java|kt|cs)$|_spec\.rb$", re.I)

SMELLS = [
    ("sleep", r"\b(time\.sleep|asyncio\.sleep|Thread\.sleep|time\.Sleep|usleep|sleep)\s*\(|setTimeout\s*\(|waitForTimeout\s*\(",
     "fixed sleep/timeout", "waiting a guessed time races with the real work; wait for a condition, an event or a fake clock instead"),
    ("clock", r"\b(datetime\.(now|utcnow|today)|date\.today|time\.time|time\.monotonic|Date\.now|new Date\(\)|Instant\.now|LocalDateTime\.now|time\.Now|SystemTime::now)\b",
     "reads the real clock", "results change with the time of day, month end, DST, slow machines; inject a clock or freeze time"),
    ("random", r"\b(random\.(random|randint|choice|shuffle|sample|uniform)|uuid\.uuid4|Math\.random|rand\.(Int|Float|Intn)|rand::|SecureRandom|new Random\(\))",
     "unseeded randomness", "a different input every run; seed the generator and log the seed, or inject it"),
    ("network", r"\b(requests\.(get|post|put|delete|request)|urllib\.request|urlopen|socket\.(socket|create_connection)|httpx\.(get|post)|fetch\(\s*['\"`]https?://|axios\.(get|post)\(\s*['\"`]https?://|http\.Get|reqwest::)",
     "real network call", "depends on the internet and remote services; fake the boundary or use a local server"),
    ("port", r"(localhost|127\.0\.0\.1|0\.0\.0\.0):\d{4,5}\b|\bport\s*[=:]\s*\d{4,5}\b|\.listen\(\s*\d{4,5}\b",
     "hard-coded port", "collides with other runs or processes; bind to port 0 and read the assigned port"),
    ("tmp", r"['\"`](/tmp/|C:\\\\Temp|\./(out|output|tmp|test_output)[\w./-]*)['\"`]|open\(\s*['\"][\w./-]+\.(txt|json|csv|db|log)['\"]\s*,\s*['\"][wa]",
     "shared file path", "parallel or leftover files change the outcome; use a unique temp directory per test"),
    ("env", r"\bos\.environ\[[^\]]+\]\s*=|\bos\.putenv\(|process\.env\.\w+\s*=[^=]|\bsetenv\(|\bos\.chdir\(|\bprocess\.chdir\(",
     "changes process-wide state", "leaks into later tests; use the framework's scoped helper (monkeypatch, t.Setenv) so it is undone"),
    ("global", r"^\s*global\s+\w+|^[A-Z_][A-Z0-9_]*\s*=\s*(\[\]|\{\}|dict\(\)|list\(\))|\bbeforeAll\(|\b@BeforeClass\b|\bsetUpClass\b",
     "shared mutable state", "tests that share state pass or fail depending on order; build fresh state per test"),
    ("thread", r"\b(threading\.Thread|Thread\(|new Thread|go func|ThreadPoolExecutor|concurrent\.futures|asyncio\.create_task|setImmediate|process\.nextTick)\b",
     "concurrency in a test", "the result depends on scheduling; join/await explicitly, use barriers or events, never rely on timing"),
    ("focus", r"\b(it|test|describe)\.only\(|\bfit\(|\bfdescribe\(|@pytest\.mark\.skip\b|\.skip\(|@Ignore\b|@Disabled\b|\bt\.Skip\(|xfail",
     "focused or skipped test", "a forgotten .only silently skips everything else; skips and xfail hide real failures"),
    ("order", r"@pytest\.mark\.(order|dependency)|dependsOnMethods|@Order\(|@TestMethodOrder|test_\d+_|\bit\(\s*['\"]step \d",
     "order dependence", "tests that need to run in sequence break under shuffling or parallel runs; make each independent"),
    ("float", r"assert\w*\s*\(?\s*\w+[^=\n]*==\s*\d+\.\d+|assertEqual\([^,]+,\s*\d+\.\d+\)|toBe\(\s*\d+\.\d+\s*\)|expect\([^)]*\)\.toEqual\(\s*\d+\.\d+",
     "exact float comparison", "floating point is not exact across platforms; compare with a tolerance (approx, isclose, toBeCloseTo)"),
    ("dict-order", r"\bset\(\)|list\(\s*\w+\.(keys|values|items)\(\)\s*\)\s*==|os\.listdir\(|glob\.glob\(|readdir|Files\.list",
     "unordered data compared as ordered", "sets, directory listings and some maps have no guaranteed order; sort before comparing"),
]
SMELL_RX = [(k, re.compile(rx), title, why) for k, rx, title, why in SMELLS]


def scan(root: Path, top: int, as_json: bool) -> int:
    base = root if root.is_dir() else root.parent
    hits: dict[str, list] = defaultdict(list)
    nfiles = 0
    paths = [root] if root.is_file() else []
    if root.is_dir():
        for dp, dn, fn in os.walk(root):
            dn[:] = [d for d in dn if d not in SKIP_DIRS and not d.startswith(".")]
            paths += [Path(dp) / f for f in fn]
    for p in paths:
        rel = p.relative_to(base).as_posix() if root.is_dir() else p.name
        if p.suffix not in {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".go", ".java", ".kt", ".rs", ".rb", ".php", ".cs"} or not TEST_PATH.search(rel):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        nfiles += 1
        for i, line in enumerate(text.splitlines(), 1):
            s = line.strip()
            if s.startswith(("#", "//", "*", "/*")):
                continue
            for key, rx, title, why in SMELL_RX:
                if rx.search(line):
                    hits[key].append((rel, i, s[:110]))
    if as_json:
        print(json.dumps({"test_files": nfiles, "smells": {k: {"count": len(v), "samples": v[:top]} for k, v in hits.items()}}, indent=2))
        return 0
    print(f"Scanned {nfiles} test file(s).\n")
    if not nfiles:
        print("No test files found under that path.")
        return 0
    meta = {k: (t, w) for k, _, t, w in SMELL_RX}
    for key, items in sorted(hits.items(), key=lambda kv: -len(kv[1])):
        title, why = meta[key]
        print(f"{title}: {len(items)} place(s)\n    why: {why}")
        for rel, ln, src in items[:top // 2 + 2]:
            print(f"      {rel}:{ln}  {src}")
        if len(items) > top // 2 + 2:
            print(f"      ... and {len(items) - (top // 2 + 2)} more")
        print()
    if not hits:
        print("No common flakiness smells found. Run the tests repeatedly (flaky.py run) to look for timing or order problems.")
    else:
        print("These are suspects, not proof. Reproduce the failure first (flaky.py run), then match it to a cause.")
    return 0


# ------------------------------------------------------------------ run
FAIL_PATTERNS = [
    re.compile(r"^FAILED\s+(\S+::\S+?)(?:\s+-\s.*)?$", re.M),                       # pytest summary
    re.compile(r"^ERROR\s+(\S+::\S+?)(?:\s+-\s.*)?$", re.M),
    re.compile(r"^ERROR\s+(\S+\.py)\s*$", re.M),                                 # pytest collection error
    re.compile(r"^(?:FAIL|ERROR):\s+(\w+)\s+\(([\w.]+)\)", re.M),                  # unittest
    re.compile(r"^\s*●\s+(.+?)\s*$", re.M),                                          # jest
    re.compile(r"^\s*(?:FAIL|✗|×|✖)\s+(\S.*?)\s*(?:\d+ms)?$", re.M),                # vitest / node test
    re.compile(r"^not ok \d+ - (.+)$", re.M),                                        # TAP / node --test
    re.compile(r"^\s*--- FAIL:\s+(\S+)", re.M),                                      # go
    re.compile(r"^test (\S+) \.\.\. FAILED", re.M),                                  # cargo
    re.compile(r"^\[ERROR\]\s+((?:\w+\.)+\w+(?::\d+)?)\b", re.M),                    # maven
]


def failed_tests(output: str) -> set[str]:
    out: set[str] = set()
    for rx in FAIL_PATTERNS:
        for m in rx.finditer(output):
            g = [x for x in m.groups() if x]
            name = ".".join(reversed(g)) if len(g) == 2 and rx.pattern.startswith("^(?:FAIL|ERROR)") else (g[0] if g else "")
            name = re.sub(r"\x1b\[[0-9;]*m", "", name).strip()
            if name and not name.lower().startswith(("test suite", "tests:", "failures", "build", "there ", "to see")):
                out.add(name[:140])
    return out


def run(args) -> int:
    cmd = args.command
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        print("error: give the test command after --, e.g.  flaky.py run -n 10 -- python -m pytest -q", file=sys.stderr)
        return 1
    env = dict(os.environ)
    for kv in args.env or []:
        k, _, v = kv.partition("=")
        env[k] = v
    results, tail_of_first_fail = [], None
    print(f"Running {' '.join(cmd)}  x{args.n}" + (f"  env: {', '.join(args.env)}" if args.env else "") + "\n")
    for i in range(1, args.n + 1):
        t0 = time.time()
        try:
            r = subprocess.run(cmd, cwd=args.cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=args.timeout, stdin=subprocess.DEVNULL)
            out = (r.stdout or "") + (r.stderr or "")
            code = r.returncode
        except subprocess.TimeoutExpired as e:
            out = ((e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")) + "\n[timeout]"
            code = 124
        except FileNotFoundError:
            print(f"error: command not found: {cmd[0]}", file=sys.stderr)
            return 1
        dt = time.time() - t0
        fails = failed_tests(out) if code else set()
        if code and not fails:
            fails = {f"<run failed with exit code {code}; no test names recognized>"}
        results.append({"run": i, "code": code, "seconds": round(dt, 2), "failed": sorted(fails)})
        print(f"  run {i:>3}: {'PASS' if code == 0 else 'FAIL'}  exit={code}  {dt:5.1f}s" + (f"  ({len(fails)} failing)" if fails else ""))
        if code and tail_of_first_fail is None:
            tail_of_first_fail = (i, "\n".join(out.strip().splitlines()[-40:]))
        if code and args.until_fail:
            break
    n = len(results)
    bad = [r for r in results if r["code"] != 0]
    print(f"\n{n - len(bad)} passed, {len(bad)} failed of {n} run(s).")
    counts = Counter(t for r in results for t in r["failed"])
    if counts:
        print("\nTests by failures:")
        for t, c in counts.most_common(15):
            kind = "FAILS EVERY RUN (broken, not flaky)" if c == n else f"flaky: {c}/{n} runs ({100 * c // n}%)"
            print(f"  {c:>3}/{n}  {t}   [{kind}]")
    times = [r["seconds"] for r in results]
    if len(times) > 1:
        print(f"\nDuration: min {min(times):.1f}s  max {max(times):.1f}s  (large swings point to timing-sensitive tests or a loaded machine)")
    if not bad:
        print(f"\nNo failure in {n} run(s). That bounds the failure rate to about {min(100, round(300 / n))}% at 95% confidence, it does not prove stability. "
              f"Try more runs, --env PYTHONHASHSEED=random, a loaded machine (run twice in parallel), or a different test order.")
    elif tail_of_first_fail:
        print(f"\nEnd of the output of the first failing run (run {tail_of_first_fail[0]}):\n" + "-" * 60 + f"\n{tail_of_first_fail[1]}\n" + "-" * 60)
    return 0 if not bad else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="mode", required=True)
    s = sub.add_parser("scan")
    s.add_argument("path", nargs="?", default=".")
    s.add_argument("--top", type=int, default=12)
    s.add_argument("--json", action="store_true")
    r = sub.add_parser("run")
    r.add_argument("-n", type=int, default=10)
    r.add_argument("--timeout", type=int, default=600)
    r.add_argument("--until-fail", action="store_true")
    r.add_argument("--env", action="append")
    r.add_argument("--cwd", default=None)
    r.add_argument("command", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    if a.mode == "scan":
        root = Path(a.path).resolve()
        if not root.exists():
            print(f"error: {a.path} not found", file=sys.stderr)
            return 1
        return scan(root, a.top, a.json)
    return run(a)


if __name__ == "__main__":
    sys.exit(main())
