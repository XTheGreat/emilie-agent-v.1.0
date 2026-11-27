"""The Scripts panel: the commands a project defines for itself, found in its files (package.json scripts, Makefile
targets, justfile recipes, pyproject task runners, Cargo, Go, Django's manage.py, Docker Compose, deno.json tasks,
composer.json scripts, .claude/launch.json), plus commands the user saved for the project. Each one is a command line
run in its folder by the hub's Terminal runner (hub.Term), so its output streams to the panel."""
from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path

from .. import paths
from .projkit import IS_WIN, norm, project_dirs, read_json, read_jsonc, read_toml, venv_python

MARKERS = ("package.json", "Makefile", "makefile", "GNUmakefile", "justfile", "Justfile", ".justfile", "Taskfile.yml",
           "Taskfile.yaml", "pyproject.toml", "manage.py", "Cargo.toml", "go.mod", "composer.json", "deno.json",
           "deno.jsonc", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")
STORE = paths.HOME_DIR / "desktop" / "projects.json"
_lock = threading.Lock()
MAX_ITEMS = 60


def _pm(d: Path, pkg: dict) -> str:
    """The package manager the project uses: its packageManager field, else its lock file."""
    want = str(pkg.get("packageManager") or "").split("@")[0]
    if want in ("npm", "pnpm", "yarn", "bun"):
        return want
    for lock, pm in (("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"), ("bun.lockb", "bun"), ("bun.lock", "bun")):
        cur = d
        for _ in range(4):                               # a workspace keeps the lock file at its root
            if (cur / lock).exists():
                return pm
            if cur.parent == cur:
                break
            cur = cur.parent
    return "npm"


def _run_word(pm: str, name: str) -> str:
    quoted = name if re.fullmatch(r"[\w:.@/-]+", name) else json.dumps(name)
    return f"yarn {quoted}" if pm == "yarn" else f"{pm} run {quoted}"


def _present(d: Path, names: tuple[str, ...]) -> str | None:
    """The first of these files that is in d, by its real name (Windows would also match "makefile" for "Makefile")."""
    try:
        have = set(os.listdir(d))
    except OSError:
        return None
    return next((n for n in names if n in have and (d / n).is_file()), None)


def _group(rel: str, source: str, label: str, items: list[dict], kind: str) -> dict:
    return {"id": f"{rel}|{source}", "dir": rel, "source": source, "label": label, "kind": kind, "items": items[:MAX_ITEMS],
            "more": max(0, len(items) - MAX_ITEMS)}


def _package_json(d: Path, rel: str) -> list[dict]:
    pkg = read_json(d / "package.json")
    scripts = pkg.get("scripts") if isinstance(pkg.get("scripts"), dict) else {}
    if not scripts:
        return []
    pm = _pm(d, pkg)
    items = [{"name": k, "command": _run_word(pm, k), "detail": str(v)} for k, v in scripts.items() if isinstance(v, str)]
    return [_group(rel, "package.json", pm, items, "node")]


_MAKE_TARGET = re.compile(r"^([A-Za-z0-9_][A-Za-z0-9_.\-/]*)\s*:(?![:=])([^#\n]*)(?:##\s*(.*))?$")


def _makefile(d: Path, rel: str) -> list[dict]:
    name = _present(d, ("GNUmakefile", "makefile", "Makefile"))
    if not name:
        return []
    try:
        lines = (d / name).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    items, seen = [], set()
    for i, line in enumerate(lines):
        m = _MAKE_TARGET.match(line)
        if not m or "%" in m.group(1) or m.group(1).startswith(".") or m.group(1) in seen:
            continue
        seen.add(m.group(1))
        desc = (m.group(3) or "").strip()
        if not desc and i and lines[i - 1].startswith("#"):
            desc = lines[i - 1].lstrip("#").strip()
        items.append({"name": m.group(1), "command": f"make {m.group(1)}", "detail": desc})
    return [_group(rel, name, "make", items, "make")] if items else []


_JUST_RECIPE = re.compile(r"^@?([A-Za-z_][\w-]*)(?:\s+[^:]*?)?:(?!=)")      # "serve port='8000':", not "x := 1"


def _justfile(d: Path, rel: str) -> list[dict]:
    name = _present(d, ("justfile", "Justfile", ".justfile"))
    if not name:
        return []
    try:
        lines = (d / name).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    items = []
    for i, line in enumerate(lines):
        if line[:1] in (" ", "\t", "#") or line.startswith(("set ", "alias ", "export ", "import ", "mod ")):
            continue
        m = _JUST_RECIPE.match(line)
        if m and not (m.group(1) in ("if", "else")):
            desc = lines[i - 1].lstrip("#").strip() if i and lines[i - 1].startswith("#") else ""
            items.append({"name": m.group(1), "command": f"just {m.group(1)}", "detail": desc})
    return [_group(rel, name, "just", items, "just")] if items else []


def _taskfile(d: Path, rel: str) -> list[dict]:
    name = _present(d, ("Taskfile.yml", "Taskfile.yaml"))
    if not name:
        return []
    try:
        text = (d / name).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    m = re.search(r"^tasks:\s*\n((?:[ \t]+.*\n?|\s*\n)*)", text, re.M)
    if not m:
        return []
    block = m.group(1)
    indent = re.match(r"[ \t]+", block)
    names = re.findall(rf"^{indent.group(0) if indent else '  '}([\w:.-]+):", block, re.M)
    items = [{"name": n, "command": f"task {n}", "detail": ""} for n in dict.fromkeys(names)]
    return [_group(rel, name, "task", items, "task")] if items else []


def _python(d: Path, root: Path) -> str:
    v = venv_python(d, root)
    if not v:
        return "python" if IS_WIN else "python3"
    return f'& "{v}"' if IS_WIN else f'"{v}"'


def _pyproject(d: Path, root: Path, rel: str) -> list[dict]:
    t = read_toml(d / "pyproject.toml")
    if not t:
        return []
    tool = t.get("tool") or {}
    out = []

    def add(source: str, label: str, table, prefix: str) -> None:
        if isinstance(table, dict) and table:
            items = []
            for k, v in table.items():
                detail = v if isinstance(v, str) else (v.get("cmd") or v.get("shell") or v.get("help") or "") if isinstance(v, dict) else ""
                items.append({"name": k, "command": f"{prefix} {k}", "detail": str(detail)})
            out.append(_group(rel, source, label, items, "python"))

    add("pyproject.toml · poe", "poe", tool.get("poe", {}).get("tasks") if isinstance(tool.get("poe"), dict) else None, "poe")
    add("pyproject.toml · taskipy", "task", tool.get("taskipy", {}).get("tasks") if isinstance(tool.get("taskipy"), dict) else None, "task")
    add("pyproject.toml · pdm", "pdm", tool.get("pdm", {}).get("scripts") if isinstance(tool.get("pdm"), dict) else None, "pdm run")
    hatch = (((tool.get("hatch") or {}).get("envs") or {}).get("default") or {}).get("scripts") if isinstance(tool.get("hatch"), dict) else None
    add("pyproject.toml · hatch", "hatch", hatch, "hatch run")
    entry = dict((t.get("project") or {}).get("scripts") or {})
    entry.update(((tool.get("poetry") or {}).get("scripts") or {}) if isinstance(tool.get("poetry"), dict) else {})
    if entry:
        items = [{"name": k, "command": k, "detail": f"{v} (installed command)"} for k, v in entry.items() if isinstance(v, str)]
        out.append(_group(rel, "pyproject.toml · commands", "python", items, "python"))
    py = _python(d, root)
    common = []
    if (d / "tests").is_dir() or (d / "conftest.py").exists() or "pytest" in tool:
        common.append({"name": "test", "command": f"{py} -m pytest" if "pytest" in tool or (d / "conftest.py").exists()
                       else f"{py} -m unittest discover -s tests -v", "detail": "run the tests"})
    if common:
        out.append(_group(rel, "pyproject.toml · python", "python", common, "python"))
    return out


def _manage_py(d: Path, root: Path, rel: str) -> list[dict]:
    if not (d / "manage.py").is_file():
        return []
    py = _python(d, root)
    items = [{"name": n, "command": f"{py} manage.py {n}", "detail": desc} for n, desc in (
        ("runserver", "start the development server"), ("migrate", "apply database migrations"),
        ("makemigrations", "create migrations from model changes"), ("test", "run the tests"),
        ("check", "check the project for problems"), ("createsuperuser", "make an admin user (asks questions)"))]
    return [_group(rel, "manage.py", "django", items, "python")]


def _cargo(d: Path, rel: str) -> list[dict]:
    if not (d / "Cargo.toml").is_file():
        return []
    items = [{"name": n, "command": f"cargo {n}", "detail": desc} for n, desc in (
        ("run", "build and run"), ("build", "compile"), ("test", "run the tests"), ("check", "check without building"),
        ("clippy", "lint"), ("fmt", "format the code"), ("build --release", "optimized build"))]
    return [_group(rel, "Cargo.toml", "cargo", items, "rust")]


def _go(d: Path, rel: str) -> list[dict]:
    if not (d / "go.mod").is_file():
        return []
    items = [{"name": n, "command": c, "detail": desc} for n, c, desc in (
        ("run", "go run .", "build and run"), ("build", "go build ./...", "compile every package"),
        ("test", "go test ./...", "run the tests"), ("vet", "go vet ./...", "report suspicious code"),
        ("tidy", "go mod tidy", "tidy go.mod"))]
    return [_group(rel, "go.mod", "go", items, "go")]


def _composer(d: Path, rel: str) -> list[dict]:
    c = read_json(d / "composer.json")
    scripts = c.get("scripts") if isinstance(c.get("scripts"), dict) else {}
    items = [{"name": k, "command": f"composer run-script {k}", "detail": v if isinstance(v, str) else " && ".join(map(str, v)) if isinstance(v, list) else ""}
             for k, v in scripts.items() if not k.startswith(("pre-", "post-"))]
    return [_group(rel, "composer.json", "composer", items, "php")] if items else []


def _deno(d: Path, rel: str) -> list[dict]:
    for name in ("deno.json", "deno.jsonc"):
        if (d / name).is_file():
            tasks = read_jsonc(d / name).get("tasks")
            if isinstance(tasks, dict) and tasks:
                items = [{"name": k, "command": f"deno task {k}", "detail": v if isinstance(v, str) else str((v or {}).get("command", ""))}
                         for k, v in tasks.items()]
                return [_group(rel, name, "deno", items, "deno")]
    return []


def _compose(d: Path, rel: str) -> list[dict]:
    name = _present(d, ("compose.yaml", "compose.yml", "docker-compose.yml", "docker-compose.yaml"))
    if not name:
        return []
    f = "" if name in ("compose.yaml", "docker-compose.yml") else f" -f {name}"      # the two docker finds by itself
    items = [{"name": n, "command": f"docker compose{f} {c}", "detail": desc} for n, c, desc in (
        ("up", "up", "start the services (stays attached)"), ("up -d", "up -d", "start them in the background"),
        ("down", "down", "stop and remove them"), ("ps", "ps", "what is running"),
        ("logs", "logs -f --tail 200", "follow their logs"), ("build", "build", "build the images"))]
    return [_group(rel, name, "docker", items, "docker")]


def _launch_json(root: Path) -> list[dict]:
    """Dev servers written to .claude/launch.json (the Browser panel's "Detect dev server")."""
    cfg = read_jsonc(root / ".claude" / "launch.json")
    items = []
    for c in cfg.get("configurations") or []:
        if not isinstance(c, dict) or not c.get("runtimeExecutable"):
            continue
        args = [str(a) for a in c.get("runtimeArgs") or []]
        cmd = " ".join([str(c["runtimeExecutable"])] + [a if re.fullmatch(r"[\w:./=@-]+", a) else json.dumps(a) for a in args])
        port = f" · port {c['port']}" if c.get("port") else ""
        items.append({"name": str(c.get("name") or c["runtimeExecutable"]), "command": cmd, "detail": f"dev server{port}"})
    return [_group("", ".claude/launch.json", "dev servers", items, "launch")] if items else []


# ---------------------------------------------------------------------------------------------------- saved commands
def _load_store() -> dict:
    try:
        d = json.loads(STORE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def custom(root: str) -> list[dict]:
    entry = _load_store().get(norm(root)) or {}
    out = []
    for c in entry.get("commands") or []:
        if isinstance(c, dict) and str(c.get("command") or "").strip():
            out.append({"name": str(c.get("name") or c["command"])[:80], "command": str(c["command"])[:2000],
                        "dir": str(c.get("dir") or "").replace("\\", "/").strip("/")})
    return out


def save_custom(root: str, commands: list) -> dict:
    if not root or not os.path.isdir(root):
        raise ValueError("folder not found")
    clean = []
    for c in commands or []:
        if isinstance(c, dict) and str(c.get("command") or "").strip():
            d = str(c.get("dir") or "").replace("\\", "/").strip("/")
            if ".." in d.split("/"):
                d = ""
            clean.append({"name": str(c.get("name") or "").strip()[:80] or str(c["command"]).strip()[:40],
                          "command": str(c["command"]).strip()[:2000], "dir": d})
    with _lock:
        data = _load_store()
        data[norm(root)] = {**(data.get(norm(root)) or {}), "commands": clean[:100]}
        STORE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STORE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(STORE)
    return {"custom": custom(root)}


# ---------------------------------------------------------------------------------------------------- all of it
def detect(root: str) -> dict:
    if not root or not os.path.isdir(root):
        return {"groups": [], "custom": []}
    base = Path(root)
    groups: list[dict] = []
    groups += _launch_json(base)
    for r in project_dirs(root, MARKERS, depth=2, limit=10):
        d = base / r
        groups += _package_json(d, r) + _makefile(d, r) + _justfile(d, r) + _taskfile(d, r) + _pyproject(d, base, r)
        groups += _manage_py(d, base, r) + _cargo(d, r) + _go(d, r) + _composer(d, r) + _deno(d, r) + _compose(d, r)
    return {"groups": groups, "custom": custom(root)}
