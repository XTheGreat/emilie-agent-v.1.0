#!/usr/bin/env python3
"""Find how a project is built, tested, linted and run - and the state of its git tree.

Usage: python detect_commands.py [project-root] [--json]

Reads (never runs) package.json scripts, pyproject.toml / setup.cfg / tox.ini /
pytest.ini, Makefile and justfile targets, Cargo.toml, go.mod, pom.xml,
build.gradle, composer.json, Gemfile, and CI workflow files, then prints the
commands a developer would use for: install, test, lint, format, typecheck,
build, run. Each entry says where it was found, so you can verify it.
Also prints the current branch and whether the working tree is clean.

Read-only, stdlib only. The commands are *candidates*: confirm with the user or
the README before running anything that installs or changes files.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

try:
    import tomllib  # py3.11+
except ImportError:  # pragma: no cover
    tomllib = None

KINDS = ("install", "test", "lint", "format", "typecheck", "build", "run")
SCRIPT_KIND = {
    "test": "test", "tests": "test", "check": "lint", "lint": "lint", "eslint": "lint", "format": "format", "fmt": "format",
    "prettier": "format", "typecheck": "typecheck", "tsc": "typecheck", "types": "typecheck", "build": "build", "compile": "build",
    "start": "run", "dev": "run", "serve": "run", "run": "run", "install": "install", "setup": "install", "bootstrap": "install",
}


def read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def add(res, kind, cmd, src):
    if cmd and (kind, cmd) not in {(k, c) for k, c, _ in res}:
        res.append((kind, cmd, src))


def kind_of(name: str):
    n = name.lower()
    if n in SCRIPT_KIND:
        return SCRIPT_KIND[n]
    base = re.split(r"[:_\-.]", n)[0]
    return SCRIPT_KIND.get(base)


def node(root: Path, res):
    pj = root / "package.json"
    if not pj.exists():
        return
    try:
        d = json.loads(read(pj))
    except json.JSONDecodeError:
        return
    pm = "npm"
    for lock, name in (("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"), ("bun.lockb", "bun"), ("bun.lock", "bun"), ("package-lock.json", "npm")):
        if (root / lock).exists():
            pm = name
            break
    add(res, "install", f"{pm} install", "package.json")
    for k, v in (d.get("scripts") or {}).items():
        kind = kind_of(k)
        if kind and kind != "install":
            run = f"{pm} test" if k == "test" and pm == "npm" else (f"{pm} run {k}" if pm != "yarn" else f"yarn {k}")
            add(res, kind, f"{run}    # {v[:70]}", f"package.json scripts.{k}")
    if (root / "tsconfig.json").exists():
        add(res, "typecheck", "npx tsc --noEmit", "tsconfig.json present")


def python(root: Path, res):
    pp = root / "pyproject.toml"
    data = {}
    if pp.exists() and tomllib:
        try:
            data = tomllib.loads(read(pp))
        except Exception:
            data = {}
    tool = data.get("tool", {})
    text = read(pp)
    if pp.exists() or (root / "setup.py").exists() or (root / "requirements.txt").exists():
        if (root / "uv.lock").exists():
            add(res, "install", "uv sync", "uv.lock")
        elif (root / "poetry.lock").exists() or "tool.poetry" in text:
            add(res, "install", "poetry install", "pyproject.toml (poetry)")
        elif (root / "requirements.txt").exists():
            add(res, "install", "pip install -r requirements.txt", "requirements.txt")
        elif pp.exists() or (root / "setup.py").exists():
            extras = data.get("project", {}).get("optional-dependencies", {}) or {}
            ex = next((e for e in ("dev", "test", "tests") if e in extras), None)
            add(res, "install", f'pip install -e ".[{ex}]"' if ex else "pip install -e .", "pyproject.toml" + (f" (extra '{ex}')" if ex else ""))
    has_pytest = "pytest" in tool or (root / "pytest.ini").exists() or (root / "tox.ini").exists() and "pytest" in read(root / "tox.ini") or "pytest" in text or (root / "tests").is_dir() and any((root / "tests").glob("test_*.py"))
    if has_pytest:
        add(res, "test", "python -m pytest", "pytest config / tests dir")
    elif (root / "tests").is_dir() or list(root.glob("test_*.py")):
        add(res, "test", "python -m unittest discover", "tests found, no pytest config")
    if "ruff" in tool or (root / "ruff.toml").exists() or (root / ".ruff.toml").exists():
        add(res, "lint", "ruff check .", "ruff config")
        add(res, "format", "ruff format .", "ruff config")
    if "black" in tool:
        add(res, "format", "black .", "pyproject [tool.black]")
    if "flake8" in read(root / "setup.cfg") or (root / ".flake8").exists():
        add(res, "lint", "flake8", "flake8 config")
    if "mypy" in tool or (root / "mypy.ini").exists():
        add(res, "typecheck", "mypy .", "mypy config")
    if "pyright" in tool or (root / "pyrightconfig.json").exists():
        add(res, "typecheck", "pyright", "pyright config")
    for name, target in (data.get("project", {}).get("scripts") or {}).items():
        add(res, "run", f"{name}    # entry point {target}", "pyproject [project.scripts]")
    if (root / "manage.py").exists():
        add(res, "run", "python manage.py runserver", "manage.py (Django)")
        add(res, "test", "python manage.py test", "manage.py (Django)")


def make(root: Path, res):
    for name in ("Makefile", "makefile", "GNUmakefile", "justfile", "Justfile"):
        p = root / name
        if not p.exists():
            continue
        runner = "just" if "ust" in name else "make"
        for m in re.finditer(r"^([A-Za-z][\w:-]*)\s*:(?!=)", read(p), re.M):
            t = m.group(1)
            k = kind_of(t)
            if k:
                add(res, k, f"{runner} {t}", name)


def others(root: Path, res):
    if (root / "Cargo.toml").exists():
        for k, c in (("build", "cargo build"), ("test", "cargo test"), ("lint", "cargo clippy --all-targets"), ("format", "cargo fmt"), ("run", "cargo run")):
            add(res, k, c, "Cargo.toml")
    if (root / "go.mod").exists():
        for k, c in (("build", "go build ./..."), ("test", "go test ./..."), ("lint", "go vet ./..."), ("format", "gofmt -l ."), ("run", "go run .")):
            add(res, k, c, "go.mod")
    if (root / "pom.xml").exists():
        for k, c in (("build", "mvn -q package"), ("test", "mvn -q test"), ("install", "mvn -q install -DskipTests")):
            add(res, k, c, "pom.xml")
    for g in ("build.gradle", "build.gradle.kts"):
        if (root / g).exists():
            w = "./gradlew" if (root / "gradlew").exists() else "gradle"
            for k, c in (("build", f"{w} build"), ("test", f"{w} test")):
                add(res, k, c, g)
    if (root / "composer.json").exists():
        add(res, "install", "composer install", "composer.json")
        add(res, "test", "vendor/bin/phpunit", "composer.json")
    if (root / "Gemfile").exists():
        add(res, "install", "bundle install", "Gemfile")
        add(res, "test", "bundle exec rspec" if (root / "spec").is_dir() else "bundle exec rake test", "Gemfile")
    if list(root.glob("*.csproj")) or list(root.glob("*.sln")):
        for k, c in (("build", "dotnet build"), ("test", "dotnet test"), ("run", "dotnet run")):
            add(res, k, c, "*.csproj/*.sln")


def ci(root: Path):
    found = []
    wf = root / ".github" / "workflows"
    files = list(wf.glob("*.y*ml")) if wf.is_dir() else []
    for extra in (".gitlab-ci.yml", "azure-pipelines.yml", ".circleci/config.yml", "Jenkinsfile"):
        if (root / extra).exists():
            files.append(root / extra)
    for f in files[:8]:
        for m in re.finditer(r"^\s*-?\s*run:\s*(.+)$", read(f), re.M):
            c = m.group(1).strip()
            if c and c != "|" and re.search(r"test|lint|build|check|pytest|ruff|tsc|clippy|vet", c, re.I):
                found.append((c[:100], f.relative_to(root).as_posix()))
    return found[:12]


def git(root: Path):
    def g(*a):
        try:
            return subprocess.run(["git", "-C", str(root), *a], capture_output=True, text=True, timeout=15).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None
    if g("rev-parse", "--is-inside-work-tree") != "true":
        return None
    status = g("status", "--porcelain") or ""
    lines = [l for l in status.splitlines() if l.strip()]
    return {
        "branch": g("rev-parse", "--abbrev-ref", "HEAD"),
        "clean": not lines,
        "changed_files": len(lines),
        "untracked": sum(1 for l in lines if l.startswith("??")),
        "last_commit": g("log", "-1", "--format=%h %s"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    root = Path(a.root).resolve()
    if not root.is_dir():
        print(f"error: {a.root} is not a directory", file=sys.stderr)
        return 1
    res: list[tuple[str, str, str]] = []
    node(root, res)
    python(root, res)
    make(root, res)
    others(root, res)
    cif = ci(root)
    g = git(root)
    if a.json:
        print(json.dumps({"root": str(root), "commands": [{"kind": k, "command": c, "source": s} for k, c, s in res],
                          "ci": [{"command": c, "source": s} for c, s in cif], "git": g}, indent=2))
        return 0
    print(f"Project: {root}")
    if g:
        state = "clean" if g["clean"] else f"{g['changed_files']} changed file(s), {g['untracked']} untracked"
        print(f"Git: branch {g['branch']}, {state}; last commit: {g['last_commit']}")
    else:
        print("Git: not a repository (or git not available)")
    print()
    if not res:
        print("No build/test configuration recognized. Look at the README and CI files, or ask the user.")
    for kind in KINDS:
        rows = [(c, s) for k, c, s in res if k == kind]
        if rows:
            print(f"{kind}:")
            for c, s in rows:
                print(f"  {c}    [{s}]")
    if cif:
        print("\nCommands the CI runs (the truth about what must pass):")
        for c, s in cif:
            print(f"  {c}    [{s}]")
    print("\nThese are candidates read from config files, not commands that were run. Check the README before installing anything.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
