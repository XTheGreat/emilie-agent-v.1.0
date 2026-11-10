"""Agent Skills (SKILL.md) and custom slash commands (commands/*.md).

Skill  : a folder holding SKILL.md with frontmatter (name, description). Only the name + description
         go into the system prompt; the full body is loaded by the model through the `use_skill` tool
         (progressive disclosure), or directly through `/<skill-name> [arguments]`.
Command: a .md file; `/<name> arguments` sends its content as a message ($ARGUMENTS is replaced by the arguments).
Locations: ./.emilie/{skills,commands}, ./.claude/{skills,commands}, ~/.emilie/..., ~/.claude/...
"""
import re
from dataclasses import dataclass
from pathlib import Path

from .i18n import t as tr_, N_
from . import tools


@dataclass
class Skill:
    name: str
    description: str
    path: Path            # SKILL.md
    source: str           # project | user
    body: str
    phase: str = ""       # one of PHASES (pahami, rencana, ...) or "" when the skill does not belong to a phase


# The development lifecycle Emilie works through, like a senior developer: understand -> plan -> build -> check -> release -> maintain.
PHASES: list[tuple[str, str]] = [("pahami", N_("Understand")), ("rencana", N_("Plan")), ("bangun", N_("Build")),
                                 ("cek-mutu", N_("Quality check")), ("rilis", N_("Release")), ("rawat", N_("Maintain"))]
# The planned skill set per phase. Used to place a skill that does not say which phase it is, and to show what is still missing.
CATALOG: dict[str, list[str]] = {
    "pahami": ["project-overview", "trace-code", "clarify-requirements", "evaluate-technology", "investigate-bug"],
    "rencana": ["design-architecture", "design-database", "design-api", "design-ui-ux", "break-down-tasks"],
    "bangun": ["build-feature", "scaffold-project", "refactor-code", "migrate-code", "integrate-third-party"],
    "cek-mutu": ["write-tests", "fix-flaky-tests", "load-test", "review-code", "deep-review", "security-audit",
                 "accessibility-check", "profile-performance"],
    "rilis": ["prepare-release", "write-changelog", "commit-and-pr", "setup-ci-cd", "containerize-deploy",
              "emergency-rollback"],
    "rawat": ["upgrade-dependencies", "pay-down-tech-debt", "setup-monitoring", "debug-production",
              "write-documentation", "write-adr", "onboard-teammate", "explain-code"],
}
PHASE_OF = {skill: ph for ph, names in CATALOG.items() for skill in names}
_PHASE_ALIAS = {"understand": "pahami", "plan": "rencana", "planning": "rencana", "build": "bangun", "implement": "bangun",
                "quality": "cek-mutu", "qa": "cek-mutu", "review": "cek-mutu", "cekmutu": "cek-mutu", "check": "cek-mutu",
                "release": "rilis", "maintain": "rawat", "maintenance": "rawat"}


def phase_id(text: str) -> str:
    """'Bangun', 'fase-3-bangun', '3-build', 'Quality' ... -> a phase id, or '' if it is none of them."""
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    s = re.sub(r"^(fase|phase|step|tahap)?-?\d*-?", "", s).strip("-")
    s = _PHASE_ALIAS.get(s, s)
    return s if s in {p for p, _ in PHASES} else ""


def phase_label(pid: str) -> str:
    return tr_(dict(PHASES).get(pid, pid))


@dataclass
class Command:
    name: str
    description: str
    path: Path
    source: str
    body: str


SKILLS: dict[str, Skill] = {}
SKIPPED: list[str] = []      # skill folders that were ignored, with the reason (shown by /skills)
COMMANDS: dict[str, Command] = {}


def parse_frontmatter(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    meta: dict[str, str] = {}
    lines = m.group(1).splitlines()
    i = 0
    while i < len(lines):
        km = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", lines[i])
        i += 1
        if not km:
            continue
        key, val = km.group(1), km.group(2).strip()
        if val in (">", "|", ">-", "|-", ""):
            parts = []
            while i < len(lines) and (lines[i].startswith((" ", "\t")) or not lines[i].strip()):
                parts.append(lines[i].strip())
                i += 1
            val = " ".join(p for p in parts if p)
        meta[key] = val.strip("\"'")
    return meta, m.group(2)


BUILTIN = Path(__file__).resolve().parent / "builtin"      # skills that ship with Emilie: builtin/skills/<name>/SKILL.md


def _roots(cwd: str) -> list[tuple[Path, str]]:
    """Earlier wins when names clash: a project's own skill beats yours, which beats the one that ships with Emilie."""
    home, here = Path.home(), Path(cwd)
    return [(here / ".emilie", "project"), (here / ".claude", "project"),
            (home / ".emilie", "user"), (home / ".claude", "user"), (BUILTIN, "builtin")]


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "-", s.lower()).strip("-")


RESOURCE_DIRS = {"references", "scripts", "assets", "templates", "examples", "node_modules"}
DESC_LIMIT = 700           # trigger phrases live at the END of a good description: do not cut them off


def _skill_files(skills_dir: Path) -> list[Path]:
    """Every SKILL.md under skills/: skills/<name>/SKILL.md and, for multi-phase skills,
    skills/<group>/<phase>/SKILL.md (up to 2 levels). Resource folders (references/, scripts/ ...) are never searched."""
    found: list[Path] = []

    def walk(d: Path, depth: int) -> None:
        try:
            kids = sorted(p for p in d.iterdir() if p.is_dir() and not p.name.startswith(".") and p.name not in RESOURCE_DIRS)
        except OSError:
            return
        for k in kids:
            if (k / "SKILL.md").exists():
                found.append(k / "SKILL.md")
            if depth < 2:
                walk(k, depth + 1)

    walk(skills_dir, 1)
    return found


def resources(skill: "Skill") -> dict[str, list[Path]]:
    """{'references': [...], 'scripts': [...], 'other': [...]} files bundled next to a SKILL.md (recursive, sorted)."""
    base = skill.path.parent
    out: dict[str, list[Path]] = {"references": [], "scripts": [], "other": []}
    for p in sorted(base.rglob("*")):
        if not p.is_file() or p.name == "SKILL.md" or any(part.startswith(".") for part in p.relative_to(base).parts):
            continue
        rel = p.relative_to(base).parts
        if (base / rel[0] / "SKILL.md").exists() and len(rel) > 1:
            continue                                         # belongs to a nested phase skill, listed with that one
        key = rel[0] if rel[0] in ("references", "scripts") else "other"
        out[key].append(p)
    return out


def load(cwd: str) -> None:
    """(Re)load skills & commands; the earlier source (project) wins when names clash."""
    SKILLS.clear()
    COMMANDS.clear()
    SKIPPED.clear()
    for root, src in _roots(cwd):
        for d in sorted(p for p in (root / "skills").glob("*") if p.is_dir() and not p.name.startswith(".")):
            if not (d / "SKILL.md").exists():
                other = sorted(x.name for x in d.glob("*.md"))
                if other:                                  # only folders that look like a misnamed skill
                    SKIPPED.append(tr_('{d} has no SKILL.md (found {0}: rename it to SKILL.md)', ', '.join(other[:3]), d=d))
        for f in _skill_files(root / "skills"):
            try:
                meta, body = parse_frontmatter(f.read_text(errors="replace"))
            except OSError:
                continue
            name = _slug(meta.get("name") or f.parent.name)
            if name and name not in SKILLS:
                desc = meta.get("description") or next((l.strip() for l in body.splitlines() if l.strip()), "")
                sdir = root / "skills"
                phase = (phase_id(meta.get("phase") or meta.get("fase") or "")            # 1) the skill says so
                         or (phase_id(f.parent.parent.name) if f.parent.parent != sdir else "")  # 2) skills/<phase>/<skill>/
                         or (phase_id(f.parent.name) if re.match(r"^(fase|phase)-", f.parent.name.lower()) else "")
                         or PHASE_OF.get(name, ""))                                      # 3) the planned catalogue
                SKILLS[name] = Skill(name, desc, f, src, body.strip(), phase)
        for f in sorted((root / "commands").glob("*.md")):
            try:
                meta, body = parse_frontmatter(f.read_text(errors="replace"))
            except OSError:
                continue
            name = _slug(f.stem)
            if name and name not in COMMANDS:
                desc = meta.get("description") or next((l.strip().lstrip("# ") for l in body.splitlines() if l.strip()), "")
                COMMANDS[name] = Command(name, desc, f, src, body.strip())
    _sync_tool()


def prompt_section() -> str:
    if not SKILLS:
        return ""
    lines = ["# Available skills",
             "If the request matches a skill's description, even partly, your FIRST action must be to call use_skill for "
             "it, before searching, reading files or answering. A skill holds the procedure, the quality bar and the "
             "output format the user expects, so do not work from memory when one applies. A skill may tell you to load "
             "another one: do so. If none matches, carry on normally."]
    if any(s.phase for s in SKILLS.values()):
        lines.append("You work like a senior developer, in phases: " + " -> ".join(f"{lab} ({pid})" for pid, lab in PHASES) +
                     ". Understand before planning, plan before building, verify before releasing. For a task decide which "
                     "phases it needs (a bug: Understand, Build, Quality check; a feature: Understand, Plan, Build, Quality check; "
                     "a release: Quality check, Release), say so in one line, and load the skill of each phase as you enter it. "
                     "If no skill is installed for a phase, do that phase yourself with the same care.")
    budget = 12000                                           # total characters for the whole list
    groups = [(f"## {lab} ({pid})", [s for s in SKILLS.values() if s.phase == pid]) for pid, lab in PHASES]
    groups.append(("## Other", [s for s in SKILLS.values() if not s.phase]))
    for head, items in groups:
        if not items:
            continue
        if any(s.phase for s in SKILLS.values()):
            lines.append(head)
        for s in items[:60]:
            line = f"- {s.name}: {s.description[:DESC_LIMIT]}"
            budget -= len(line)
            if budget < 0:
                return "\n".join(lines)
            lines.append(line)
    return "\n".join(lines)


def triggers(s: "Skill") -> list[str]:
    """The quoted phrases after 'Triggers' in a skill's description, lower-cased: 'Triggers - "trace", "walk me through"'."""
    tail = re.split(r"\bTriggers?\b", s.description, maxsplit=1)
    if len(tail) < 2:
        return []
    return [p.strip().lower() for p in re.findall(r"[\"“]([^\"”]{2,80})[\"”]", tail[1]) if p.strip()]


def matching(text: str) -> list["Skill"]:
    """Skills whose trigger phrase appears in the user's message (whole words, case-insensitive)."""
    low = (text or "").lower()
    out = []
    for s in SKILLS.values():
        if any(re.search(r"(?<!\w)" + re.escape(p) + r"(?!\w)", low) for p in triggers(s)):
            out.append(s)
    return out


def with_hint(text: str) -> str:
    """Models do not always load a skill on their own. When the message contains a skill's trigger phrase, append a short
    note so the first action is use_skill. Not applied to slash commands (those load a skill explicitly)."""
    if not SKILLS or not text or text.lstrip().startswith(("/", "!", "#")) or "<skill " in text:
        return text
    hits = matching(text)[:2]
    if not hits:
        return text
    names = ", ".join(f"'{s.name}'" for s in hits)
    return (f"{text}\n\n<skill-hint>This request matches the skill {names}. Call use_skill for it first and follow it, "
            "unless it clearly does not apply.</skill-hint>")


def _bind(s: "Skill", text: str) -> str:
    """Skills refer to their own folder as <path-skill>, ${SKILL_DIR} or {baseDir}: fill in the real path."""
    base = str(s.path.parent)
    for ph in ("<path-skill>", "${SKILL_DIR}", "$SKILL_DIR", "{baseDir}", "<skill-dir>"):
        text = text.replace(ph, base)
    return text


def _resource_block(s: "Skill") -> str:
    res = resources(s)
    if not any(res.values()):
        return ""
    base = s.path.parent

    def row(p: Path) -> str:
        try:
            kb = max(1, p.stat().st_size // 1024)
        except OSError:
            kb = 0
        return f"  - {p.relative_to(base)}  ({kb} KB)"
    out = [f"\n\n## Bundled files (paths below are relative to the base directory {base})"]
    if res["references"]:
        out += ["References - load one with use_skill(name='%s', file='<path>') or read_file when the instructions say so:" % s.name]
        out += [row(p) for p in res["references"]]
    if res["scripts"]:
        out += ["Scripts - run them with the bash tool, e.g.  bash %s/<path> [args]  (read-only helpers unless the instructions say otherwise):" % base]
        out += [row(p) for p in res["scripts"]]
    if res["other"]:
        out += ["Other files:"] + [row(p) for p in res["other"]]
    return "\n".join(out)


def use_skill(name: str, file: str = "") -> str:
    s = SKILLS.get(_slug(name))
    if not s:
        return f"ERROR: unknown skill '{name}'. Available: {', '.join(SKILLS) or 'none'}"
    if file:                                                  # one bundled file (reference / template / script source)
        base = s.path.parent.resolve()
        target = (base / file).resolve()
        if base != target and base not in target.parents:
            return f"ERROR: '{file}' is outside the skill folder"
        if not target.is_file():
            names = [str(p.relative_to(base)) for ps in resources(s).values() for p in ps]
            return f"ERROR: no file '{file}' in skill '{s.name}'. Files: {', '.join(names) or 'none'}"
        txt = target.read_text(errors="replace")
        cut = "\n...[truncated]" if len(txt) > 30000 else ""
        return f"# {s.name}/{file}\n\n" + _bind(s, txt[:30000]) + cut
    ph = f" (phase: {dict(PHASES)[s.phase]})" if s.phase else ""
    return f"# Skill: {s.name}{ph}\nBase directory: {s.path.parent}\n\n{_bind(s, s.body)}" + _resource_block(s)


def _sync_tool() -> None:
    """The use_skill tool only exists when there are skills."""
    if SKILLS:
        tools.register("use_skill", use_skill, {
            "name": "use_skill",
            "description": ("Load the full instructions of an Agent Skill by name (skills are listed in the system prompt). "
                            "Skills may chain: a skill can tell you to load another one. Pass `file` (e.g. 'references/template.md') "
                            "to read one of the skill's bundled reference files instead."),
            "input_schema": {"type": "object", "properties": {"name": {"type": "string"},
                                                              "file": {"type": "string", "description": "optional path inside the skill folder"}},
                             "required": ["name"]}},
            "skills")
    else:
        tools.unregister("use_skill")


def expand_command(name: str, arg: str) -> str | None:
    c = COMMANDS.get(name)
    if not c:
        return None
    body = c.body
    return body.replace("$ARGUMENTS", arg) if "$ARGUMENTS" in body else (body + (f"\n\n{arg}" if arg else ""))


def skill_message(name: str, arg: str) -> str | None:
    s = SKILLS.get(name)
    if not s:
        return None
    return (f'<skill name="{s.name}" base="{s.path.parent}">\n{_bind(s, s.body)}{_resource_block(s)}\n</skill>\n\n'
            f"{arg or 'Apply this skill to the current task.'}")


def dev_message(task: str) -> str:
    """/dev <task>: ask the agent to take the task through the lifecycle like a senior developer."""
    have = {pid: [s.name for s in SKILLS.values() if s.phase == pid] for pid, _ in PHASES}
    lines = [f"- {lab} ({pid}): " + (", ".join(have[pid]) or "(no skill installed: do this phase yourself)") for pid, lab in PHASES]
    return ("Take the task below through the development lifecycle, like a careful senior developer.\n\n"
            f"TASK: {task or '(ask me what to work on)'}\n\n"
            "Phases and the skills installed for each:\n" + "\n".join(lines) + "\n\n"
            "How to work:\n"
            "1. First decide which phases this task really needs (a bug: Understand, Build, Quality check; a feature: Understand, "
            "Plan, Build, Quality check; a release: Quality check, Release; ...) and tell me the route in one line.\n"
            "2. For each phase in the route: say 'Phase: <name>', load its skill(s) with use_skill, follow them, and finish the "
            "phase with a 2-3 line summary of what you found or did and the evidence.\n"
            "3. Ask me to confirm before leaving Plan for Build when the change is large or risky, and before anything "
            "irreversible (commit, push, deploy, deleting data).\n"
            "4. Do not call a phase done without evidence (tests run, output seen). Say plainly what you could not verify.\n"
            "5. If a phase has no skill, still do it, briefly.")


def extras() -> dict[str, str]:
    """For autocomplete & /help: '/name' -> description."""
    out = {f"/{n}": f"[skill] {s.description[:60]}" for n, s in SKILLS.items()}
    out.update({f"/{n}": f"[command] {c.description[:60]}" for n, c in COMMANDS.items()})
    return out
