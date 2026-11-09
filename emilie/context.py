"""Extra context: project memory (EMILIE.md) and @file mentions."""
import re
from pathlib import Path

from .effort import HOME_DIR

MEMORY_NAMES = ("EMILIE.md", "CLAUDE.md", "AGENTS.md")   # the first file that exists per folder
PER_FILE, TOTAL = 8_000, 16_000


def memory_files(cwd: str) -> list[Path]:
    """~/.emilie/EMILIE.md, then from the root down to the working folder (one file per folder)."""
    found: list[Path] = []
    g = HOME_DIR / "EMILIE.md"
    if g.is_file():
        found.append(g)
    here = Path(cwd).resolve()
    for d in reversed([here, *here.parents]):
        for n in MEMORY_NAMES:
            f = d / n
            if f.is_file():
                found.append(f)
                break
    return found


def load_memory(cwd: str) -> tuple[str, list[Path]]:
    files, parts, used = memory_files(cwd), [], 0
    for f in files:
        try:
            txt = f.read_text(errors="replace")[:PER_FILE]
        except OSError:
            continue
        if used + len(txt) > TOTAL:
            break
        used += len(txt)
        parts.append(f'<memory path="{f}">\n{txt.strip()}\n</memory>')
    return "\n\n".join(parts), files


MENTION = re.compile(r"(?<![\w@])@([\w./~\-]+)")


def expand_mentions(text: str, cwd: str, max_chars: int) -> tuple[str, list[tuple[str, int]]]:
    """@path/to/file -> the file contents are appended to the message. Returns (new_text, [(path, line_count)])."""
    seen, blocks, info = set(), [], []
    for m in MENTION.finditer(text):
        raw = m.group(1).rstrip(".,;:)")
        p = Path(raw).expanduser()
        p = p if p.is_absolute() else Path(cwd) / p
        if raw in seen or not p.is_file():
            continue
        seen.add(raw)
        try:
            body = p.read_text(errors="replace")
        except OSError:
            continue
        n = body.count("\n") + 1
        clipped = body if len(body) <= max_chars else body[:max_chars] + "\n...[truncated]"
        blocks.append(f'<file path="{raw}">\n{clipped}\n</file>')
        info.append((raw, n))
    return (text + "\n\n" + "\n\n".join(blocks) if blocks else text), info


def append_note(cwd: str, note: str) -> Path:
    """`# note` -> appended to EMILIE.md in the working folder."""
    f = Path(cwd) / "EMILIE.md"
    if not f.exists():
        f.write_text("# Project notes\n\n")
    with f.open("a") as fh:
        fh.write(f"- {note.strip()}\n")
    return f
