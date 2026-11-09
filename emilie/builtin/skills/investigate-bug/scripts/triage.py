#!/usr/bin/env python3
"""Turn a stack trace or error text into a starting point for a bug investigation. Read-only.

    python triage.py --trace error.txt [--repo .]        # or:  --trace -  (read stdin)   or:  --text "..."

It extracts the error and the stack frames (Python, JavaScript/Node, Java/Kotlin, Go, Rust, C#/.NET, Ruby, PHP, or any
`file:line`), keeps the frames that belong to this repository, and for each one shows the surrounding code, the commit that
last changed that line, and the recent history of the file. It also lists the toolchain versions and the latest commits.
Nothing is modified, executed, or sent anywhere. Secret files (.env, keys) are never opened.
"""
import argparse
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

SECRET = re.compile(r"(^\.env(\..+)?$|\.pem$|\.key$|\.pfx$|\.p12$|^id_(rsa|dsa|ecdsa|ed25519)$|credentials|secrets?\.)", re.I)
LIB_HINT = re.compile(r"(site-packages|dist-packages|node_modules|/usr/lib|/usr/local/lib|\\Python\d+\\Lib\\|/rustc/|"
                      r"\\go\\src\\|/go/src/|/golang/|java\.base/|jdk\.internal|<frozen|<anonymous>|node:internal|internal/)", re.I)


def sh(args: list[str], cwd: Path, timeout: int = 15) -> str:
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, timeout=timeout)
        return r.stdout.decode("utf-8", errors="replace").strip() if r.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


# ---------------------------------------------------------------------------------------------- parsing
PATTERNS = [
    ("python", re.compile(r'File "(?P<f>[^"]+)", line (?P<l>\d+)(?:, in (?P<fn>.+))?')),
    ("dotnet", re.compile(r"\bat (?P<fn>[^\n]+?) in (?P<f>[^\n]+?):line (?P<l>\d+)")),
    ("java", re.compile(r"\bat (?P<fn>[\w.$<>/]+)\((?P<f>[\w$-]+\.(?:java|kt|scala|groovy)):(?P<l>\d+)\)")),
    ("rust-panic", re.compile(r"panicked at (?:'[^']*', )?(?P<f>[^\s:]+\.rs):(?P<l>\d+)(?::\d+)?")),
    ("rust", re.compile(r"^\s*at (?P<f>\S+\.rs):(?P<l>\d+)(?::\d+)?", re.M)),
    ("node", re.compile(r"\bat (?:(?P<fn>[^()\n]+?) \()?(?P<f>(?:[A-Za-z]:)?[^():\n]+?\.(?:[cm]?[jt]sx?|vue|svelte)):(?P<l>\d+):\d+\)?")),
    ("go", re.compile(r"^\s+(?P<f>\S+\.go):(?P<l>\d+)(?: \+0x[0-9a-f]+)?\s*$", re.M)),
    ("ruby", re.compile(r"(?P<f>[^\s:]+\.rb):(?P<l>\d+):in [`'](?P<fn>[^'`]+)'")),
    ("php", re.compile(r"#\d+ (?P<f>\S+\.php)\((?P<l>\d+)\)")),
    ("generic", re.compile(r"(?P<f>[\w./\\:-]+\.[A-Za-z]{1,5}):(?P<l>\d+)\b")),
]
ERROR_RE = [
    re.compile(r"^(?P<e>(?:[\w.]+\.)?\w*(?:Error|Exception|Warning|Fault|Panic)\b[^\n]*)$", re.M),
    re.compile(r"^(?P<e>panic: [^\n]+|fatal error: [^\n]+|thread '[^']*' panicked at [^\n]+|Segmentation fault[^\n]*|Unhandled[^\n]+)$", re.M),
    re.compile(r"^(?P<e>(?:Caused by|Exception in thread)[^\n]+)$", re.M),
]


def parse(text: str) -> tuple[list[tuple[str, str, int, str]], str]:
    """-> ([(language, file, line, function)], error line). Frames keep trace order."""
    frames: list[tuple[str, str, int, str]] = []
    seen = set()
    for lang, rx in PATTERNS:
        if lang == "generic" and frames:
            continue
        for m in rx.finditer(text):
            key = (m.group("f"), int(m.group("l")), m.start())
            gd = m.groupdict()
            frames.append((lang, m.group("f").strip(), int(m.group("l")), (gd.get("fn") or "").strip()))
            seen.add(key)
        if frames and lang != "generic":
            break
    error = ""
    for rx in ERROR_RE:
        found = [m.group("e").strip() for m in rx.finditer(text)]
        if found:
            error = found[-1] if "Traceback" in text else found[0]       # Python prints the error LAST
            break
    if not error:
        lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
        error = lines[-1] if lines else ""
    return frames, error[:300]


# ---------------------------------------------------------------------------------------------- resolving files
def tracked(repo: Path) -> list[str]:
    raw = sh(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], repo, 30)
    if raw:
        return [f for f in raw.split("\0") if f]
    out = []
    for dp, dns, fns in os.walk(repo):
        dns[:] = [d for d in dns if d not in {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", "target"}]
        out += [str((Path(dp) / f).relative_to(repo)) for f in fns]
    return out


def resolve(repo: Path, files: list[str], raw: str, fn: str) -> tuple[str | None, list[str]]:
    """The repo-relative path for a path as printed in a trace (absolute on another machine, relative, or a bare name)."""
    p = raw.replace("\\", "/")
    if LIB_HINT.search(raw) or LIB_HINT.search(p):
        return None, []
    cand = Path(raw)
    try:
        if cand.is_absolute() and cand.exists() and repo in cand.resolve().parents:
            return str(cand.resolve().relative_to(repo)).replace("\\", "/"), []
    except OSError:
        pass
    norm = [f.replace("\\", "/") for f in files]
    parts = [x for x in p.split("/") if x not in ("", ".", "..") and not re.fullmatch(r"[A-Za-z]:", x)]
    for n in range(len(parts), 0, -1):                                   # longest matching path suffix wins
        suffix = "/".join(parts[-n:])
        hits = [f for f in norm if f == suffix or f.endswith("/" + suffix)]
        if len(hits) == 1:
            return hits[0], []
        if len(hits) > 1:
            if fn and "." in fn:                                         # Java: com.acme.Foo.bar -> com/acme/Foo.java
                pkg = "/".join(fn.split("(")[0].split(".")[:-1]).replace("$", "/")
                better = [h for h in hits if pkg and pkg in h]
                if len(better) == 1:
                    return better[0], []
                # modules often do not mirror the package in the folder names: read each candidate's `package` line
                dotted = ".".join(fn.split("(")[0].split(".")[:-2])
                if dotted:
                    by_decl = []
                    for h in hits:
                        try:
                            head = (repo / h).read_text(encoding="utf-8", errors="replace")[:2000]
                        except OSError:
                            continue
                        if re.search(rf"^\s*package\s+{re.escape(dotted)}\s*;?\s*$", head, re.M):
                            by_decl.append(h)
                    if len(by_decl) == 1:
                        return by_decl[0], []
            return None, hits[:4]
    return None, []


# ---------------------------------------------------------------------------------------------- output
def show_environment(repo: Path) -> None:
    print("== ENVIRONMENT")
    print(f"os: {platform.system()} {platform.release()} | machine: {platform.machine()}")
    for label, cmd in (("python", [sys.executable, "--version"]), ("node", ["node", "--version"]), ("npm", ["npm", "--version"]),
                       ("go", ["go", "version"]), ("java", ["java", "-version"]), ("rustc", ["rustc", "--version"]),
                       ("dotnet", ["dotnet", "--version"]), ("ruby", ["ruby", "--version"]), ("php", ["php", "--version"])):
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=8, cwd=repo)
            out = (r.stdout + r.stderr).decode("utf-8", errors="replace").strip().splitlines()
            if r.returncode == 0 and out:
                print(f"{label}: {out[0][:80]}")
        except (OSError, subprocess.TimeoutExpired):
            continue
    if sh(["git", "rev-parse", "--is-inside-work-tree"], repo) == "true":
        print(f"git: branch {sh(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], repo)} @ {sh(['git', 'rev-parse', '--short', 'HEAD'], repo)}"
              f" | uncommitted files: {len(sh(['git', 'status', '--short'], repo).splitlines())}")


def context(repo: Path, rel: str, line: int, radius: int = 4) -> list[str]:
    p = repo / rel
    if SECRET.search(p.name):
        return ["(secret file: not shown)"]
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ["(file not readable)"]
    lo, hi = max(1, line - radius), min(len(lines), line + radius)
    return [f"{'>' if i == line else ' '} {i:>5}  {lines[i - 1][:140]}" for i in range(lo, hi + 1)]


def blame(repo: Path, rel: str, line: int) -> str:
    out = sh(["git", "blame", "-L", f"{line},{line}", "--porcelain", "--", rel], repo)
    if not out:
        return "no blame (untracked or no history)"
    commit = out.splitlines()[0].split()[0][:8]
    when = re.search(r"^author-time (\d+)", out, re.M)
    summ = re.search(r"^summary (.+)$", out, re.M)
    import datetime as dt
    day = dt.datetime.fromtimestamp(int(when.group(1))).strftime("%Y-%m-%d") if when else "?"
    if set(commit) == {"0"}:
        return "line is uncommitted (a local change)"
    return f"{commit} on {day}: {summ.group(1)[:80] if summ else '?'}"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo", default=".")
    ap.add_argument("--trace", help="file with the stack trace or error text ('-' = stdin)")
    ap.add_argument("--text", help="the error text itself")
    ap.add_argument("--max-frames", type=int, default=8)
    a = ap.parse_args()
    repo = Path(a.repo).resolve()
    if a.trace == "-":
        text = sys.stdin.read()
    elif a.trace:
        try:
            text = Path(a.trace).read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            print(f"ERROR: cannot read {a.trace}: {e}")
            return 1
    else:
        text = a.text or ""
    print(f"TRIAGE in {repo}")
    show_environment(repo)
    if not text.strip():
        print("\n(no trace given: pass --trace FILE, --trace - or --text \"...\")")
        return 0
    frames, error = parse(text)
    print("\n== ERROR")
    print(error or "(no error line recognised)")
    files = tracked(repo)
    mine, outside, unresolved = [], 0, []
    for lang, raw, line, fn in frames:
        rel, ambiguous = resolve(repo, files, raw, fn)
        if rel:
            mine.append((rel, line, fn, lang))
        elif ambiguous:
            unresolved.append((raw, line, ambiguous))
        else:
            outside += 1
    print(f"\n== FRAMES: {len(frames)} found, {len(mine)} in this repository, {outside} in libraries or elsewhere"
          + (f", {len(unresolved)} ambiguous" if unresolved else ""))
    if frames and mine:
        lang = mine[0][3]
        order = "most recent call LAST (Python): the throw site is the last frame listed" if lang == "python" else \
                "most recent call FIRST: the throw site is the first frame listed"
        print(f"(trace order: {order})")
    deduped, seen = [], set()
    for m in mine:
        if (m[0], m[1]) not in seen:
            seen.add((m[0], m[1]))
            deduped.append(m)
    for rel, line, fn, _ in deduped[: a.max_frames]:
        print(f"\n--- {rel}:{line}" + (f"  in {fn}" if fn else ""))
        for l in context(repo, rel, line):
            print(l)
        print(f"  last changed: {blame(repo, rel, line)}")
    for raw, line, hits in unresolved[:3]:
        print(f"\n--- {raw}:{line} is ambiguous; candidates: {', '.join(hits)}")
    touched = sorted({r for r, *_ in deduped})
    if touched and sh(["git", "rev-parse", "--is-inside-work-tree"], repo) == "true":
        print("\n== RECENT CHANGES to these files (last 30 days)")
        recent = sh(["git", "log", "--since=30.days", "--format=%h %cs %s", "--"] + touched[:12], repo)
        print(recent or "none in the last 30 days: this code did not change recently, so suspect data, config or environment")
    print("\n== NEXT")
    print("1. Reproduce it yourself before theorising. 2. The frame in your code nearest the throw site is the first suspect;")
    print("   read the branch that led there. 3. If a recent change touched it, compare with `git show <hash>`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
