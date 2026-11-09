#!/usr/bin/env python3
"""Read-only inventory of a code repository: the cheap facts, gathered in one pass.

    python inventory.py [path] [--no-git] [--max-files 6000]

It only READS. It never installs, builds, runs project code, or touches the network, and it never opens secret files
(.env, keys, credentials): for .env files it reports that they exist, and for .env.example it lists variable NAMES only.
The output is plain text in labelled sections, meant to be read by an agent and then verified against the real files.
"""
import argparse
import collections
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "env", "__pycache__", "dist", "build", "target", ".next", ".nuxt",
             "vendor", ".idea", ".vscode", ".tox", ".mypy_cache", ".pytest_cache", ".gradle", "coverage", "out", "bin",
             "obj", ".terraform", ".cache", "site-packages", ".eggs"}
SECRET_NAMES = re.compile(r"(^\.env(\..+)?$|\.pem$|\.key$|\.pfx$|\.p12$|^id_(rsa|dsa|ecdsa|ed25519)$|credentials|secrets?\.)", re.I)
ENV_EXAMPLES = {".env.example", ".env.sample", ".env.template", ".env.dist", "example.env", "sample.env"}
LANG = {".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
        ".ts": "TypeScript", ".tsx": "TypeScript", ".go": "Go", ".rs": "Rust", ".java": "Java", ".kt": "Kotlin",
        ".cs": "C#", ".rb": "Ruby", ".php": "PHP", ".swift": "Swift", ".c": "C", ".h": "C/C++", ".cpp": "C++",
        ".cc": "C++", ".hpp": "C++", ".scala": "Scala", ".dart": "Dart", ".lua": "Lua", ".sh": "Shell",
        ".ps1": "PowerShell", ".sql": "SQL", ".html": "HTML", ".css": "CSS", ".scss": "CSS", ".vue": "Vue",
        ".svelte": "Svelte", ".md": "Markdown", ".yml": "YAML", ".yaml": "YAML", ".json": "JSON", ".toml": "TOML",
        ".tf": "Terraform", ".proto": "Protobuf", ".graphql": "GraphQL", ".ipynb": "Notebook"}
CODE_LANGS = {v for v in LANG.values()} - {"Markdown", "YAML", "JSON", "TOML", "HTML", "CSS"}
MANIFESTS = ["package.json", "pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile", "poetry.lock",
             "go.mod", "Cargo.toml", "pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle", "composer.json",
             "Gemfile", "mix.exs", "pubspec.yaml", "CMakeLists.txt", "Makefile", "justfile", "Taskfile.yml",
             "Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yaml", "tsconfig.json", "deno.json",
             "next.config.js", "vite.config.ts", "vite.config.js", "webpack.config.js", "tox.ini", "pytest.ini",
             "jest.config.js", "vitest.config.ts", ".eslintrc.json", ".prettierrc", "ruff.toml", ".editorconfig",
             "global.json", "Directory.Build.props", ".nvmrc", ".python-version", ".tool-versions", "renovate.json",
             ".pre-commit-config.yaml"]
ENTRY_HINTS = ["main.py", "app.py", "manage.py", "wsgi.py", "asgi.py", "__main__.py", "cli.py", "server.py", "index.js",
               "server.js", "app.js", "index.ts", "main.ts", "src/main.rs", "main.go", "cmd", "Program.cs", "src/main.tsx",
               "src/index.tsx", "src/index.js", "src/App.tsx", "src/app", "pages", "app", "bin", "Main.java", "lib/main.dart"]


def out(s: str = "") -> None:
    print(s)


def section(title: str) -> None:
    out()
    out(f"== {title}")


def sh(args: list[str], cwd: Path, timeout: int = 20) -> str:
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, timeout=timeout)
        return r.stdout.decode("utf-8", errors="replace").strip() if r.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def read_text(p: Path, limit: int = 200_000) -> str:
    if SECRET_NAMES.search(p.name) and p.name.lower() not in ENV_EXAMPLES:
        return ""
    try:
        return p.read_bytes()[:limit].decode("utf-8", errors="replace")
    except OSError:
        return ""


def toml(p: Path) -> dict:
    txt = read_text(p)
    try:
        import tomllib
        return tomllib.loads(txt)
    except Exception:
        return {}


# ---------------------------------------------------------------------------------------------- file listing
def list_files(root: Path, use_git: bool, cap: int) -> tuple[list[Path], str]:
    """Tracked files when this is a git repo (respects .gitignore), else a walk that skips the usual junk."""
    if use_git:
        raw = sh(["git", "ls-files", "-z"], root, 40)
        if raw:
            files = [root / f for f in raw.split("\0") if f]
            return files[:cap], f"git ls-files ({len(files)} tracked files)" + (f", first {cap} used" if len(files) > cap else "")
    files: list[Path] = []
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS and not d.startswith(".")]
        for f in fns:
            files.append(Path(dp) / f)
            if len(files) >= cap:
                return files, f"directory walk (stopped at {cap} files)"
    return files, f"directory walk ({len(files)} files)"


def count_lines(p: Path) -> int:
    try:
        if p.stat().st_size > 1_000_000:
            return 0
        with open(p, "rb") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


# ---------------------------------------------------------------------------------------------- sections
def show_git(root: Path) -> None:
    top = sh(["git", "rev-parse", "--show-toplevel"], root)
    if not top:
        out("not a git repository (history-based facts below are skipped)")
        return
    remote = re.sub(r"//[^/@]+@", "//", sh(["git", "remote", "get-url", "origin"], root))      # never print credentials
    out(f"git root: {top}")
    out(f"branch: {sh(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], root)} | remote: {remote or '(none)'}")
    out(f"commits: {sh(['git', 'rev-list', '--count', 'HEAD'], root)} | last: {sh(['git', 'log', '-1', '--format=%cs %s'], root)[:100]}")
    first = sh(["git", "log", "--reverse", "--format=%cs", "--max-count=1"], root) or "?"
    out(f"first commit: {first} | uncommitted changes: {len(sh(['git', 'status', '--short'], root).splitlines())} file(s)")
    if Path(top).resolve() != root.resolve():
        out(f"NOTE: {root} is a sub-folder of the repository root")


def show_size(files: list[Path], how: str) -> None:
    by_ext: collections.Counter = collections.Counter()
    lines: collections.Counter = collections.Counter()
    budget = 3500                                                    # files whose lines we count (keeps this fast)
    for p in files:
        lang = LANG.get(p.suffix.lower())
        if not lang or SECRET_NAMES.search(p.name):
            continue
        by_ext[lang] += 1
        if budget > 0:
            lines[lang] += count_lines(p)
            budget -= 1
    out(f"source: {how}")
    rows = sorted(by_ext.items(), key=lambda kv: -lines[kv[0]])[:10]
    for lang, n in rows:
        out(f"  {lang:<12} {n:>5} files  {lines[lang]:>8} lines" + ("  (lines partly sampled)" if budget <= 0 else ""))
    code = [l for l, _ in rows if l in CODE_LANGS]
    if code:
        out(f"main language(s): {', '.join(code[:3])}")


def show_manifests(root: Path, files: list[Path]) -> None:
    rels = {str(f.relative_to(root)).replace("\\", "/"): f for f in files if root in f.parents or f.parent == root}
    found = [m for m in MANIFESTS if m in rels]
    nested = sorted(r for r in rels if r.count("/") == 1 and Path(r).name in ("package.json", "pyproject.toml", "go.mod",
                                                                              "Cargo.toml", "pom.xml"))[:12]
    out("top-level: " + (", ".join(found) or "(none of the usual manifests)"))
    if nested:
        out("nested manifests (monorepo?): " + ", ".join(nested))
    pj = rels.get("package.json")
    if pj:
        try:
            d = json.loads(read_text(pj))
            deps = {**d.get("dependencies", {}), **d.get("devDependencies", {})}
            out(f"package.json: {d.get('name', '?')} v{d.get('version', '?')} | type={d.get('type', 'commonjs')} | main={d.get('main', '-')}")
            if d.get("scripts"):
                out("  scripts: " + "; ".join(f"{k}={str(v)[:50]}" for k, v in list(d["scripts"].items())[:12]))
            if d.get("workspaces"):
                out(f"  workspaces: {d['workspaces']}")
            if d.get("engines"):
                out(f"  engines: {d['engines']}")
            known = [k for k in ("react", "next", "vue", "nuxt", "svelte", "angular", "express", "fastify", "nestjs",
                                 "@nestjs/core", "koa", "vite", "webpack", "typescript", "jest", "vitest", "mocha",
                                 "playwright", "cypress", "prisma", "@prisma/client", "mongoose", "sequelize", "typeorm",
                                 "tailwindcss", "electron", "react-native", "expo", "eslint", "prettier") if k in deps]
            out(f"  {len(deps)} dependencies; notable: {', '.join(known) or '-'}")
        except ValueError:
            out("package.json: (could not parse)")
    pp = rels.get("pyproject.toml")
    if pp:
        d = toml(pp)
        proj = d.get("project", {}) or d.get("tool", {}).get("poetry", {})
        if proj:
            deps = proj.get("dependencies", [])
            deps = list(deps.keys()) if isinstance(deps, dict) else deps
            out(f"pyproject.toml: {proj.get('name', '?')} v{proj.get('version', '?')} | python {proj.get('requires-python', '-')}")
            out(f"  dependencies ({len(deps)}): " + ", ".join(re.split(r"[<>=!~ \[;]", x)[0] for x in deps[:15]))
            if proj.get("scripts"):
                out(f"  console scripts: {', '.join(list(proj['scripts'])[:8])}")
        out(f"  build backend: {d.get('build-system', {}).get('build-backend', '-')} | tools: "
            f"{', '.join(sorted(d.get('tool', {}))[:8]) or '-'}")
    for name in ("requirements.txt",):
        if name in rels:
            reqs = [l for l in read_text(rels[name]).splitlines() if l.strip() and not l.startswith(("#", "-"))]
            out(f"{name}: {len(reqs)} entries ({', '.join(re.split(r'[<>=!~ ;\[]', r)[0] for r in reqs[:10])}...)")
    for name, rx in (("go.mod", r"^(module|go) (.+)$"),):
        if name in rels:
            out("go.mod: " + "; ".join(f"{m[0]} {m[1]}" for m in re.findall(rx, read_text(rels[name]), re.M)))
    cargo = rels.get("Cargo.toml")
    if cargo:
        d = toml(cargo)
        out(f"Cargo.toml: {d.get('package', {}).get('name', '(workspace)')} | deps: {', '.join(list(d.get('dependencies', {}))[:12])}")
    mk = rels.get("Makefile")
    if mk:
        targets = re.findall(r"^([A-Za-z0-9_.-]+):(?!=)", read_text(mk), re.M)
        out(f"Makefile targets: {', '.join(targets[:15])}")
    for name in ("Dockerfile",):
        if name in rels:
            t = read_text(rels[name])
            out(f"Dockerfile: FROM {', '.join(re.findall(r'^FROM\s+(\S+)', t, re.M)[:3])} | EXPOSE {', '.join(re.findall(r'^EXPOSE\s+(.+)$', t, re.M)) or '-'}")
    for name in ("docker-compose.yml", "docker-compose.yaml", "compose.yaml"):
        if name in rels:
            svc = re.findall(r"^  ([A-Za-z0-9_-]+):\s*$", read_text(rels[name]).split("services:", 1)[-1], re.M)
            out(f"{name}: services {', '.join(svc[:10]) or '?'}")


def show_ci(root: Path) -> None:
    wf = sorted((root / ".github" / "workflows").glob("*.y*ml")) if (root / ".github" / "workflows").is_dir() else []
    other = [n for n in (".gitlab-ci.yml", "Jenkinsfile", "azure-pipelines.yml", ".circleci/config.yml", "bitbucket-pipelines.yml",
                         ".travis.yml") if (root / n).exists()]
    if not wf and not other:
        out("no CI configuration found")
        return
    for f in wf:
        t = read_text(f)
        name = (re.search(r"^name:\s*(.+)$", t, re.M) or [None, f.stem])[1]
        on = ", ".join(sorted(set(re.findall(r"\b(push|pull_request|schedule|workflow_dispatch|release|tag)\b", t)))[:5])
        run = [r.strip()[:60] for r in re.findall(r"^\s*-?\s*run:\s*(.+)$", t, re.M)][:4]
        out(f"GitHub Actions: {f.name} - {name} | on: {on or '?'} | runs: {' ; '.join(run) or '-'}")
    for n in other:
        out(f"CI: {n}")


def show_docs(root: Path) -> None:
    readme = next((p for p in sorted(root.glob("README*")) if p.is_file()), None)
    if readme:
        t = read_text(readme, 30_000)
        heads = [h.strip("# ").strip() for h in re.findall(r"^#{1,3}\s+.+$", t, re.M)][:12]
        para = next((p.strip() for p in re.split(r"\n\s*\n", re.sub(r"^#.*$|^!\[.*$|^\[!\[.*$", "", t, flags=re.M)) if len(p.strip()) > 40), "")
        out(f"{readme.name}: {len(t.splitlines())} lines | headings: {' > '.join(heads) or '-'}")
        out(f"  opening: {' '.join(para.split())[:300]}")
    else:
        out("no README")
    for n in ("CONTRIBUTING.md", "ARCHITECTURE.md", "CHANGELOG.md", "SECURITY.md", "LICENSE", "docs", "doc", "EMILIE.md",
              "CLAUDE.md", "AGENTS.md", ".github/CODEOWNERS", ".github/pull_request_template.md"):
        if (root / n).exists():
            out(f"  has {n}" + (f" ({sum(1 for _ in (root / n).rglob('*') if _.is_file())} files)" if (root / n).is_dir() else ""))


def show_layout(root: Path, files: list[Path]) -> None:
    top: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    loose = []
    for f in files:
        try:
            rel = f.relative_to(root)
        except ValueError:
            continue
        if len(rel.parts) == 1:
            loose.append(rel.name)
        else:
            top[rel.parts[0]][LANG.get(f.suffix.lower(), f.suffix.lower() or "(none)")] += 1
    for d, c in sorted(top.items(), key=lambda kv: -sum(kv[1].values()))[:18]:
        out(f"  {d + '/':<22} {sum(c.values()):>5} files  mostly {c.most_common(1)[0][0]}")
    if loose:
        out(f"  (root files: {len(loose)}: {', '.join(sorted(loose)[:12])}{'...' if len(loose) > 12 else ''})")


def show_entry(root: Path, files: list[Path]) -> None:
    names = {str(f.relative_to(root)).replace("\\", "/") for f in files if root in f.parents or f.parent == root}
    tops = {n.split("/")[0] for n in names}
    hits = [h for h in ENTRY_HINTS if h in names or (("/" not in h) and h in tops and not h.endswith((".py", ".js", ".ts")))]
    deep = [n for n in names if re.search(r"(^|/)(main|app|server|index|__main__|cli)\.(py|js|ts|go|rs|java|cs)$", n) and n.count("/") <= 2]
    out("candidates (VERIFY by reading them): " + (", ".join(sorted(set(hits) | set(deep))[:15]) or "none obvious"))


def show_env(root: Path, files: list[Path]) -> None:
    real = [f.name for f in files if f.parent == root and SECRET_NAMES.search(f.name) and f.name.lower() not in ENV_EXAMPLES][:6]
    # tracked files are listed by git; an untracked/ignored .env is still worth reporting
    real += [p.name for p in root.glob(".env*") if p.name.lower() not in ENV_EXAMPLES and p.name not in real][:6]
    if real:
        out(f"secret-bearing files present (NOT opened): {', '.join(sorted(set(real)))}")
    for ex in sorted({f for f in files if f.name.lower() in ENV_EXAMPLES} | {p for p in root.glob(".env*") if p.name.lower() in ENV_EXAMPLES})[:3]:
        names = re.findall(r"^\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=", read_text(ex), re.M)
        out(f"{ex.name}: {len(names)} variables (names only): {', '.join(names[:25])}")
    if not real and not any(f.name.lower() in ENV_EXAMPLES for f in files):
        out("no .env files or examples found")


def show_tests(root: Path, files: list[Path]) -> None:
    tests = [f for f in files if re.search(r"(^|[/\\])(tests?|__tests__|spec|e2e)[/\\]|[._-](test|spec)\.[a-z]+$|^test_.*\.py$", str(f.relative_to(root)) if root in f.parents else f.name)]
    src = [f for f in files if LANG.get(f.suffix.lower()) in CODE_LANGS]
    out(f"test files: {len(tests)} of {len(src)} source files" + (f" ({100 * len(tests) // max(1, len(src))}% by count)" if src else ""))
    if tests:
        dirs = collections.Counter(str(t.parent.relative_to(root)).split(os.sep)[0] for t in tests if root in t.parents)
        out("  where: " + ", ".join(f"{d} ({n})" for d, n in dirs.most_common(5)))


def show_health(root: Path, files: list[Path], use_git: bool) -> None:
    if use_git and sh(["git", "rev-parse", "--show-toplevel"], root):
        out("recent commits:")
        for l in sh(["git", "log", "-12", "--format=%cs %s"], root).splitlines():
            out(f"  {l[:100]}")
        authors = sh(["git", "shortlog", "-sn", "HEAD"], root).splitlines()
        out(f"contributors: {len(authors)}" + (f" (top share: {authors[0].split()[0]} commits)" if authors else ""))
        names = sh(["git", "log", "--since=90.days", "--name-only", "--format="], root, 40).splitlines()
        hot = collections.Counter(n for n in names if n and not re.search(r"(lock|\.min\.|\.svg$|\.png$)", n))
        if hot:
            out("most-changed files in the last 90 days (likely the living core, or a hotspot): "
                + ", ".join(f"{n} ({c})" for n, c in hot.most_common(8)))
    marks = collections.Counter()
    biggest = []
    for p in files[:3000]:
        if SECRET_NAMES.search(p.name) or LANG.get(p.suffix.lower()) not in CODE_LANGS:
            continue
        try:
            sz = p.stat().st_size
        except OSError:
            continue
        biggest.append((sz, p))
        if sz < 400_000:
            for m in re.findall(r"\b(TODO|FIXME|HACK|XXX)\b", read_text(p, 400_000)):
                marks[m] += 1
    if marks:
        out("markers in code: " + ", ".join(f"{k}={v}" for k, v in marks.most_common()))
    biggest.sort(reverse=True)
    if biggest:
        out("largest source files: " + ", ".join(f"{p.relative_to(root)} ({sz // 1024} KB)" for sz, p in biggest[:5] if root in p.parents))


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("path", nargs="?", default=".")
    ap.add_argument("--no-git", action="store_true")
    ap.add_argument("--max-files", type=int, default=6000)
    a = ap.parse_args()
    root = Path(a.path).resolve()
    if not root.is_dir():
        print(f"ERROR: {root} is not a folder")
        return 1
    t0 = time.time()
    use_git = not a.no_git
    out(f"INVENTORY of {root}")
    section("GIT")
    show_git(root) if use_git else out("(skipped: --no-git)")
    files, how = list_files(root, use_git, a.max_files)
    section("SIZE AND LANGUAGES")
    show_size(files, how)
    section("MANIFESTS, STACK, TOOLING")
    show_manifests(root, files)
    section("CI")
    show_ci(root)
    section("DOCS AND AGENT INSTRUCTIONS")
    show_docs(root)
    section("LAYOUT (top-level folders)")
    show_layout(root, files)
    section("ENTRY-POINT CANDIDATES")
    show_entry(root, files)
    section("CONFIGURATION")
    show_env(root, files)
    section("TESTS")
    show_tests(root, files)
    section("HEALTH SIGNALS")
    show_health(root, files, use_git)
    out()
    out(f"-- done in {time.time() - t0:.1f}s. Everything above is a lead, not a fact: confirm the important parts in the files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
