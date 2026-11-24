"""A short snapshot of the working folder for the system prompt.

Today's date, the git branch with its uncommitted changes and last commits, the project's build/run scripts and the
top-level layout. Emilie starts every session already knowing where she is, so she does not spend her first tool calls
(and the user's tokens) on `git status`, `ls` and opening package.json, and she does not guess the year.

Taken once when a session starts or is cleared: the system prompt stays identical between calls, so prompt caching keeps
working. The prompt says it can be out of date. Broad folders (home, a drive root, the chat folder) get the date only.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

SKIP = {".git", "node_modules", "__pycache__", ".venv", "venv", "env", ".idea", ".vscode", "dist", "build", "out",
        ".next", ".nuxt", ".cache", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", "target", ".gradle",
        ".DS_Store", "Thumbs.db", "desktop.ini", ".turbo", "coverage", ".parcel-cache"}
KEEP_DOT = {".github", ".emilie", ".claude", ".env.example", ".gitignore", ".dockerignore"}
MAX_CHARS = 1800
STATUS_LINES = 15

# Marker file -> what it tells about the project (shown when present at the top level).
MARKERS = (
    ("requirements.txt", "requirements.txt (pip)"), ("Pipfile", "Pipfile (pipenv)"), ("environment.yml", "environment.yml (conda)"),
    ("Cargo.toml", "Cargo.toml (Rust)"), ("go.mod", "go.mod (Go)"), ("pom.xml", "pom.xml (Maven)"),
    ("build.gradle", "build.gradle (Gradle)"), ("build.gradle.kts", "build.gradle.kts (Gradle)"),
    ("composer.json", "composer.json (PHP)"), ("Gemfile", "Gemfile (Ruby)"), ("pubspec.yaml", "pubspec.yaml (Flutter/Dart)"),
    ("CMakeLists.txt", "CMakeLists.txt (CMake)"), ("Makefile", "Makefile"), ("Dockerfile", "Dockerfile"),
    ("docker-compose.yml", "docker-compose.yml"), ("compose.yaml", "compose.yaml"), ("manage.py", "manage.py (Django)"),
)


def _run_git(cwd: str, *args: str, timeout: float = 4.0) -> str | None:
    try:
        r = subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=cwd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL, timeout=timeout,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return r.stdout.rstrip() if r.returncode == 0 else None


def _git(cwd: str) -> list[str]:
    root = _run_git(cwd, "rev-parse", "--show-toplevel")
    if not root:
        return []
    branch = _run_git(cwd, "branch", "--show-current") or "(detached HEAD)"
    same = os.path.normcase(os.path.abspath(root)) == os.path.normcase(os.path.abspath(cwd))
    out = [f"Git: on branch {branch}" + ("" if same else f" (repository root: {os.path.abspath(root)})")]
    st = _run_git(cwd, "status", "--short")
    if st is not None:
        lines = [x for x in st.splitlines() if x.strip()]
        if not lines:
            out.append("Working tree clean.")
        else:
            out.append(f"Uncommitted changes ({len(lines)}):")
            out += ["  " + x[:120] for x in lines[:STATUS_LINES]]
            if len(lines) > STATUS_LINES:
                out.append(f"  ... and {len(lines) - STATUS_LINES} more")
    log = _run_git(cwd, "log", "-5", "--format=%h\x1f%s\x1f%ar")
    if log:
        out.append("Last commits:")
        for x in log.splitlines():
            h, subj, when = (x.split("\x1f") + ["", ""])[:3]
            out.append(f"  {h} {subj if len(subj) <= 90 else subj[:89] + '…'} ({when})")
    return out


def _toml_name(text: str) -> tuple[str, list[str]]:
    """(project name, [project.scripts]) from pyproject.toml, with tomllib when there is one (Python 3.11+)."""
    try:
        import tomllib
        d = tomllib.loads(text)
        proj = d.get("project") or {}
        name = proj.get("name") or ((d.get("tool") or {}).get("poetry") or {}).get("name") or ""
        return str(name), [str(k) for k in (proj.get("scripts") or {})]
    except Exception:
        m = re.search(r'^\s*name\s*=\s*["\']([^"\']+)', text, re.M)
        return (m.group(1) if m else ""), []


def _project(cwd: str) -> list[str]:
    p = Path(cwd)
    out: list[str] = []
    pkg = p / "package.json"
    if pkg.is_file():
        line = "package.json"
        try:
            d = json.loads(pkg.read_text(encoding="utf-8", errors="replace"))
            if d.get("name"):
                line += f" ({d['name']})"
            scripts = list((d.get("scripts") or {}).items())
            if scripts:
                line += ": scripts " + "; ".join(f"{k} = {str(v)[:60]}" for k, v in scripts[:10])
        except (OSError, ValueError):
            pass
        for lock, pm in (("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"), ("bun.lockb", "bun"), ("bun.lock", "bun"),
                         ("package-lock.json", "npm")):
            if (p / lock).exists():
                line += f" [uses {pm}]"
                break
        out.append(line)
    py = p / "pyproject.toml"
    if py.is_file():
        try:
            name, scripts = _toml_name(py.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            name, scripts = "", []
        out.append("pyproject.toml" + (f" ({name})" if name else "") + (": scripts " + ", ".join(scripts[:8]) if scripts else ""))
    out += [label for f, label in MARKERS if (p / f).exists()]
    try:
        sln = next((e.name for e in os.scandir(cwd) if e.name.endswith((".sln", ".csproj"))), None)
    except OSError:
        sln = None
    if sln:
        out.append(f"{sln} (.NET)")
    for v in (".venv", "venv", "env"):
        exe = p / v / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if exe.exists():
            out.append(f"Python virtualenv: {v}/ (run Python with {exe.relative_to(p)})")
            break
    return ["Project files: " + " | ".join(out)] if out else []


def _layout(cwd: str) -> list[str]:
    try:
        entries = sorted(os.scandir(cwd), key=lambda e: (not e.is_dir(follow_symlinks=False), e.name.lower()))
    except OSError:
        return []
    names = [e.name + ("/" if e.is_dir(follow_symlinks=False) else "") for e in entries
             if e.name not in SKIP and (not e.name.startswith(".") or e.name in KEEP_DOT)]
    if not names:
        return ["Top level: (empty folder)"]
    more = f"  (+{len(names) - 40} more)" if len(names) > 40 else ""
    return ["Top level: " + "  ".join(names[:40]) + more]


def _broad(cwd: str) -> bool:
    """Folders too wide to describe: the home folder and its standard folders, a drive root, the chat folder."""
    c = os.path.normcase(os.path.abspath(cwd)).rstrip("\\/")
    home = os.path.normcase(str(Path.home())).rstrip("\\/")
    if c == home or len(Path(c).parts) <= 1:
        return True
    std = {os.path.normcase(str(Path.home() / x)) for x in ("Desktop", "Documents", "Downloads", "OneDrive", "Pictures")}
    return c in std or c == os.path.normcase(str(Path.home() / "Documents" / "Emilie"))


def snapshot(cwd: str | None = None) -> str:
    """The system-prompt section. Never raises: a failing part is just left out."""
    cwd = os.path.abspath(cwd or os.getcwd())
    lines = [f"Today is {time.strftime('%A, %d %B %Y')} (local time {time.strftime('%H:%M')} when the session started)."]
    if not _broad(cwd):
        for part in (_git, _project, _layout):
            try:
                lines += part(cwd)
            except Exception:
                pass
    text = "\n".join(lines)
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS].rsplit("\n", 1)[0] + "\n..."
    return ("\n\n# Workspace snapshot\nTaken when this session started; files and git may have changed since, so check "
            "before relying on a detail. Use it to skip re-running git status / ls / reading package.json just to "
            "orient yourself.\n" + text)
