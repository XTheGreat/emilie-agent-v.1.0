#!/usr/bin/env python3
"""Find where a symbol or a string lives in a codebase, and sort the hits by what they are.

    python find_symbol.py <symbol> [path] [--max N] [--peek N] [--include-tests]
    python find_symbol.py --string "text shown to the user" [path]

Plain grep returns every mention in one pile. This groups them: DEFINITIONS (with a peek at the body), CALLS, IMPORTS,
TESTS, COMMENTS and other mentions, so you can start a trace at the right place. Read-only, no network, standard library
only. It skips build output, dependencies and secret files (.env, keys). It is a lead generator: dynamic dispatch,
decorators, dependency injection and reflection hide calls from any text search, so confirm in the code.
"""
import argparse
import collections
import os
import re
import subprocess
import sys
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "env", "__pycache__", "dist", "build", "target", ".next", ".nuxt",
             "vendor", ".idea", ".vscode", ".tox", ".mypy_cache", ".pytest_cache", ".gradle", "coverage", "out", "obj",
             ".terraform", ".cache", "site-packages", ".eggs"}
SECRET = re.compile(r"(^\.env(\..+)?$|\.pem$|\.key$|\.pfx$|\.p12$|^id_(rsa|dsa|ecdsa|ed25519)$|credentials|secrets?\.)", re.I)
TEXT_EXT = {".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".go", ".rs", ".java", ".kt", ".kts", ".cs", ".rb", ".php",
            ".swift", ".c", ".h", ".cpp", ".cc", ".hpp", ".scala", ".dart", ".lua", ".sh", ".ps1", ".sql", ".vue", ".svelte",
            ".html", ".css", ".scss", ".md", ".yml", ".yaml", ".json", ".toml", ".tf", ".proto", ".graphql", ".ex", ".exs",
            ".erl", ".clj", ".r", ".jl", ".txt", ".cfg", ".ini", ".gradle"}
TEST_PATH = re.compile(r"(^|[/\\])(tests?|__tests__|spec|specs|e2e|cypress|__mocks__)[/\\]|[._-](test|spec)\.[a-z0-9]+$|(^|[/\\])test_[^/\\]*\.py$|_test\.(go|py)$", re.I)
COMMENT = re.compile(r"^\s*(#|//|/\*|\*|--|;|<!--|\"\"\"|''')")


def definition_patterns(ext: str, s: str) -> list[re.Pattern]:
    """Regexes that mean 'this line DEFINES s', by language family. s is already re.escape()d."""
    py = [rf"^\s*(async\s+def|def|class)\s+{s}\b", rf"^{s}\s*(:[^=]+)?=[^=]"]
    js = [rf"\b(function\*?|class|interface|type|enum|namespace)\s+{s}\b", rf"\b(const|let|var)\s+{s}\s*(:[^=]+)?=",
          rf"^\s{{2,}}(public\s+|private\s+|protected\s+|static\s+|async\s+|get\s+|set\s+)*{s}\s*(<[^>]*>)?\([^)]*\)\s*(:[^{{]+)?\{{"]
    go = [rf"^func\s+(\([^)]*\)\s*)?{s}\b", rf"^(type|var|const)\s+{s}\b"]
    rs = [rf"\b(fn|struct|enum|trait|type|const|static|mod|macro_rules!)\s+{s}\b"]
    jvm = [rf"\b(class|interface|enum|record|object|fun|func|def|struct|protocol|trait)\s+{s}\b",
           rf"^\s*(public|private|protected|internal|static|final|override|async|virtual|abstract|suspend|open|\s)+[\w<>\[\],.?*\s]+\s+{s}\s*\("]
    rb = [rf"^\s*(def|class|module)\s+(self\.)?{s}\b"]
    php = [rf"\b(function|class|interface|trait|enum)\s+{s}\b"]
    c = [rf"^\s*[\w:<>*&~\s]+[\s*&]{s}\s*\([^;]*$", rf"\b(struct|class|enum|typedef|#define)\s+{s}\b"]
    sh = [rf"^\s*(function\s+)?{s}\s*\(\)\s*\{{", rf"^\s*function\s+{s}\b"]
    table = {".py": py, ".js": js, ".jsx": js, ".mjs": js, ".cjs": js, ".ts": js, ".tsx": js, ".vue": js, ".svelte": js,
             ".go": go, ".rs": rs, ".java": jvm, ".kt": jvm, ".kts": jvm, ".cs": jvm, ".scala": jvm, ".swift": jvm,
             ".dart": jvm, ".rb": rb, ".php": php, ".c": c, ".h": c, ".cpp": c, ".cc": c, ".hpp": c, ".sh": sh, ".ps1": sh}
    return [re.compile(p) for p in table.get(ext, [])]


def import_pattern(ext: str, s: str) -> re.Pattern | None:
    if ext == ".py":
        return re.compile(rf"^\s*(from\s+\S+\s+)?import\b.*\b{s}\b")
    if ext in (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".vue", ".svelte"):
        return re.compile(rf"\bimport\b.*\b{s}\b|\brequire\(.*\b{s}\b|\bexport\b.*\bfrom\b.*\b{s}\b")
    if ext == ".rs":
        return re.compile(rf"^\s*(pub\s+)?use\s+.*\b{s}\b")
    if ext in (".java", ".kt", ".scala", ".cs", ".swift", ".dart"):
        return re.compile(rf"^\s*(import|using)\s+.*\b{s}\b")
    if ext == ".go":
        return re.compile(rf"^\s*\"[^\"]*\b{s}\b[^\"]*\"\s*$")
    return None


def list_files(root: Path) -> list[Path]:
    try:
        r = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=root,
                           capture_output=True, timeout=30)
        if r.returncode == 0 and r.stdout:
            return [root / f for f in r.stdout.decode("utf-8", errors="replace").split("\0") if f]
    except (OSError, subprocess.TimeoutExpired):
        pass
    out: list[Path] = []
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS and not d.startswith(".")]
        out += [Path(dp) / f for f in fns]
    return out


def read_lines(p: Path) -> list[str] | None:
    try:
        if p.stat().st_size > 2_000_000:
            return None
        data = p.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:4096]:
        return None
    return data.decode("utf-8", errors="replace").splitlines()


def trim(line: str, n: int = 110) -> str:
    line = line.strip()
    return line if len(line) <= n else line[: n - 1] + "…"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("symbol", nargs="?", default="")
    ap.add_argument("path", nargs="?", default=".")
    ap.add_argument("--string", help="search for this exact text instead of a symbol")
    ap.add_argument("--max", type=int, default=12, help="hits shown per group (default 12)")
    ap.add_argument("--peek", type=int, default=8, help="body lines shown after each definition (default 8, 0 = none)")
    ap.add_argument("--include-tests", action="store_true", help="also list hits inside test files in full")
    a = ap.parse_args()
    if not a.symbol and not a.string:
        ap.error("give a symbol or --string")
    root = Path(a.path).resolve()
    if not root.exists():
        print(f"ERROR: {root} does not exist")
        return 1
    needle = a.string if a.string else a.symbol
    esc = re.escape(needle)
    word = re.compile(rf"(?<![\w$]){esc}(?![\w$])") if not a.string else re.compile(esc)
    call = re.compile(rf"(?<![\w$.]){esc}\s*\(|\.{esc}\s*\(") if not a.string else None

    groups: dict[str, list[tuple[str, int, str, list[str]]]] = collections.defaultdict(list)
    scanned = 0
    for f in sorted(list_files(root) if root.is_dir() else [root]):
        if f.name and SECRET.search(f.name):
            continue
        ext = f.suffix.lower()
        if ext not in TEXT_EXT and ext != "":
            continue
        lines = read_lines(f)
        if lines is None:
            continue
        scanned += 1
        rel = str(f.relative_to(root)) if root.is_dir() else f.name
        is_test = bool(TEST_PATH.search(rel))
        defs = definition_patterns(ext, esc) if not a.string else []
        imp = import_pattern(ext, esc) if not a.string else None
        for i, line in enumerate(lines):
            if not word.search(line):
                continue
            if is_test:
                kind = "tests"
            elif COMMENT.match(line):
                kind = "comments"
            elif any(d.search(line) for d in defs):
                kind = "definitions"
            elif imp and imp.search(line):
                kind = "imports"
            elif call and call.search(line):
                kind = "calls"
            else:
                kind = "mentions"
            peek = lines[i + 1: i + 1 + a.peek] if kind == "definitions" and a.peek else []
            groups[kind].append((rel, i + 1, line, peek))

    total = sum(len(v) for v in groups.values())
    print(f"{'STRING' if a.string else 'SYMBOL'}: {needle}   ({scanned} files searched, {total} hits)")
    if not total:
        print("no hits. Try: a shorter or differently-cased name, the same word in another form (snake_case/camelCase),")
        print("a nearby user-visible string with --string, or check that the path is right.")
        return 0
    labels = [("definitions", "DEFINITIONS (start reading here)"), ("calls", "CALLS / USES"), ("imports", "IMPORTS"),
              ("mentions", "OTHER MENTIONS (assignments, references, config, docs)"), ("tests", "TESTS"), ("comments", "COMMENTS")]
    for key, label in labels:
        hits = groups.get(key, [])
        if not hits:
            continue
        print(f"\n{label} - {len(hits)}")
        limit = len(hits) if (key == "tests" and a.include_tests) else a.max
        by_file = collections.Counter(h[0] for h in hits)
        for rel, n, line, peek in hits[:limit]:
            print(f"  {rel}:{n}  {trim(line)}")
            for extra in peek:
                if extra.strip():
                    print(f"      | {trim(extra, 100)}")
        if len(hits) > limit:
            top = ", ".join(f"{p} ({c})" for p, c in by_file.most_common(4))
            print(f"  ... +{len(hits) - limit} more; busiest files: {top}")
    print("\nNOTE: text search cannot see dynamic dispatch, decorators/registries, DI, reflection or generated code.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
