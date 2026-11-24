"""Tool-call display helpers and saved messages -> transcript items for the desktop UI.

A transcript item is a dict with a "kind":
    user        {text, images: [data-url], files: [path], command?: "/review ..."}
    assistant   {text}                                    markdown (may contain <say> tags; the UI shows them as ♪ lines)
    thinking    {text}
    tool        {name, label, target, input, status: running|ok|error|interrupted|denied, summary: [str], output, diff?}
    note        {text, level}                             small grey line (automatic continue, summaries, ...)
    notice      {blocks, level}                           what a command printed (see blocks.py)
Live events produce the same items, so a session looks the same whether it is running now or opened again later.
"""
from __future__ import annotations

import difflib
import json
import re
from pathlib import Path

from rich.text import Text

from .. import tools, ui

_ORIG_TOOL_RESULT = ui.tool_result          # kept before worker.py swaps ui.tool_result for its own
DIFF_TOOLS = {"write_file", "edit_file"}
OUT_LIVE, OUT_SNAPSHOT = 20_000, 6_000


def label(name: str) -> str:
    try:
        return ui.label(name)
    except Exception:
        return name


def target(name: str, args: dict) -> str:
    try:
        return str(ui._target(name, args if isinstance(args, dict) else {}))
    except Exception:
        return ""


def clip_args(args, limit: int = 4000):
    """Tool arguments for display: long strings are cut so one huge write_file does not flood the UI."""
    if isinstance(args, dict):
        return {k: clip_args(v, limit) for k, v in list(args.items())[:40]}
    if isinstance(args, list):
        return [clip_args(v, limit) for v in args[:60]]
    if isinstance(args, str) and len(args) > limit:
        return args[:limit] + f"\n… (+{len(args) - limit} chars)"
    return args


class _Cap:
    def __init__(self):
        self.lines: list[str] = []

    def print(self, *objs, **_kw):
        self.lines.append(" ".join(o.plain if isinstance(o, Text) else str(o) for o in objs))


def is_error(name: str, out: str) -> bool:
    return out.startswith(("ERROR", "BLOCKED")) or (name == "bash" and out.startswith("exit=") and not out.startswith("exit=0"))


def summary(name: str, out: str, dt: float | None = None) -> list[str]:
    """The short result lines the CLI shows under a tool call (reuses ui.tool_result, so they always match)."""
    cap = _Cap()
    try:
        _ORIG_TOOL_RESULT(cap, name, out or "", dt)
    except Exception:
        first = (out or "").strip().splitlines()[:1]
        return first
    return [re.sub(r"^\s*⎿\s?|^\s{4}", "", l) for l in cap.lines]


def _diff(path: str, old: str, new: str) -> dict | None:
    if old == new:
        return None
    lines = list(difflib.unified_diff(old.splitlines(), new.splitlines(), fromfile=path, tofile=path, lineterm="", n=3))
    added = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
    text = "\n".join(lines[2:])
    if len(text) > 60_000:
        text = text[:60_000] + "\n… (diff cut)"
    return {"text": text, "added": added, "removed": removed, "new_file": not old, "path": path}


def diff_for(name: str, args: dict) -> dict | None:
    """The real change a write/edit is about to make (call BEFORE the tool runs)."""
    try:
        if name == "edit_file":
            old, new, _eol, err = tools.compute_edit(args["path"], args.get("old_string", ""), args.get("new_string", ""),
                                                     bool(args.get("replace_all")), args.get("edits"))
            return None if err else _diff(args["path"], old, new)
        if name == "write_file":
            p = Path(args["path"]).expanduser()
            old = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
            new = old + args.get("content", "") if args.get("append") else args.get("content", "")
            return _diff(args["path"], old, new)
    except Exception:
        return None
    return None


def approx_diff(name: str, args: dict) -> dict | None:
    """For an old session (the file has changed since): the change as described by the call itself."""
    try:
        path = args.get("path", "")
        if name == "edit_file":
            edits = args.get("edits") or [{"old_string": args.get("old_string", ""), "new_string": args.get("new_string", "")}]
            old = "\n...\n".join(str(e.get("old_string", "")) for e in edits if isinstance(e, dict))
            new = "\n...\n".join(str(e.get("new_string", "")) for e in edits if isinstance(e, dict))
            d = _diff(path, old, new)
            if d:
                d["approx"] = True
            return d
        if name == "write_file":
            d = _diff(path, "", str(args.get("content", "")))
            if d:
                d["approx"], d["new_file"], d["append"] = True, not args.get("append"), bool(args.get("append"))
            return d
    except Exception:
        return None
    return None


def tool_item(name: str, args, tid: str) -> dict:
    if isinstance(args, str):
        try:
            args = json.loads(args or "{}")
        except ValueError:
            args = {}
    args = args if isinstance(args, dict) else {}
    return {"kind": "tool", "id": tid, "name": name, "label": label(name), "target": target(name, args)[:600],
            "input": clip_args(args), "status": "running", "summary": [], "output": ""}


def finish_tool(item: dict, out, limit: int = OUT_LIVE, dt: float | None = None) -> dict:
    if isinstance(out, list):                     # Anthropic tool_result content blocks
        out = "\n".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in out)
    out = str(out or "")
    if "<system-reminder>" in out:                # notes for the model (todo reminder), not tool output for the user
        out = re.sub(r"\s*<system-reminder>.*?</system-reminder>", "", out, flags=re.S)
    name = item.get("name", "")
    if out.startswith("interrupted"):
        item["status"] = "interrupted"
    elif out.startswith("The user denied") or out.startswith("BLOCKED"):
        item["status"] = "denied"
    else:
        item["status"] = "error" if is_error(name, out) else "ok"
    item["summary"] = summary(name, out, dt)[:8]
    item["output"] = out if len(out) <= limit else out[:limit] + f"\n… (+{len(out) - limit} chars)"
    if dt is not None:
        item["secs"] = round(dt, 2)
    # pictures the call produced or opened (a browser screenshot, an image read with read_file): the app shows them
    imgs = _IMG_SAVED.findall(out)
    if name == "read_file" and item["status"] == "ok":
        p = str((item.get("input") or {}).get("path") or "")
        if Path(p).suffix.lower() in tools.IMAGE_EXTS:
            imgs.insert(0, str(Path(p).expanduser().resolve()))
    if imgs:
        item["images"] = list(dict.fromkeys(i.strip() for i in imgs))[:6]
    return item


_IMG_SAVED = re.compile(r"\[image saved: ([^\]\n]+)\]")


# ---------------------------------------------------------------- user text as the user typed it
_SYS_NOTE = re.compile(r"^\[System note: .*?\]\s*", re.S)
_REUNION = re.compile(r"^\(While the user was silent .*?\)\s*", re.S)
_HINT = re.compile(r"\s*<skill-hint>.*?</skill-hint>\s*$", re.S)
_FILES = re.compile(r'\n*<file path="([^"]+)">\n.*?\n</file>', re.S)
_IMGREF = re.compile(r"\s*\[Image #\d+(?::[^\]]*)?\]")
_SKILL = re.compile(r'^<skill name="([^"]+)"[^>]*>.*?</skill>\s*(.*)$', re.S)
_DEV = re.compile(r"^Take the task below through the development lifecycle.*?\nTASK: (.*?)\n", re.S)
_ATTACHED = re.compile(r"\n*\[Attached file: ([^\]]+)\]")


def clean_user_text(text: str) -> tuple[str, list[str], str | None]:
    """-> (text to show, @mentioned / attached files, command it came from or None)."""
    t = _SYS_NOTE.sub("", text or "")
    t = _REUNION.sub("", t)
    t = _HINT.sub("", t)
    files = _FILES.findall(t) + _ATTACHED.findall(t)
    t = _ATTACHED.sub("", _FILES.sub("", t))
    m = _SKILL.match(t)
    if m:
        arg = m.group(2).strip()
        return arg, files, f"/{m.group(1)}"
    m = _DEV.match(t)
    if m:
        return m.group(1).strip(), files, "/dev"
    return _IMGREF.sub("", t).strip(), files, None


def _image_url(p: dict) -> str | None:
    if p.get("type") == "image":
        src = p.get("source") or {}
        if src.get("type") == "base64" and src.get("data"):
            return f"data:{src.get('media_type', 'image/png')};base64,{src['data']}"
    if p.get("type") == "image_url":
        return (p.get("image_url") or {}).get("url")
    return None


GLANCE = "[Automatic camera glance during the video call: the user said nothing.]"


def items_from_messages(messages: list[dict], aliases: dict | None = None, max_images: int = 16,
                        live: bool = False) -> list[dict]:
    """The whole conversation as transcript items. Each item gets "mi": the index of the message it came from.
    live=True: a turn is running now, so calls of the last assistant message without a result are still running."""
    aliases = aliases or {}
    items: list[dict] = []
    tools_by_id: dict[str, dict] = {}
    n_img = [0]
    # count images from the end so the most recent ones are kept as pictures
    total_imgs = sum(1 for m in messages if isinstance(m.get("content"), list)
                     for p in m["content"] if isinstance(p, dict) and p.get("type") in ("image", "image_url"))
    skip_imgs = max(0, total_imgs - max_images)
    spontaneous = False

    def add(item: dict, mi: int) -> None:
        item["mi"] = mi
        item.setdefault("id", f"m{mi}-{len(items)}")
        items.append(item)

    for mi, m in enumerate(messages):
        role, c = m.get("role"), m.get("content")
        if role == "tool":                                            # OpenAI tool result
            it = tools_by_id.get(m.get("tool_call_id", ""))
            if it:
                finish_tool(it, c, OUT_SNAPSHOT)
            continue
        parts = [{"type": "text", "text": c}] if isinstance(c, str) else (c if isinstance(c, list) else [])
        if role == "user":
            texts, images = [], []
            for p in parts:
                if not isinstance(p, dict):
                    continue
                if p.get("type") == "tool_result":
                    it = tools_by_id.get(p.get("tool_use_id", ""))
                    if it:
                        finish_tool(it, p.get("content"), OUT_SNAPSHOT)
                elif p.get("type") == "text":
                    texts.append(p.get("text", ""))
                elif p.get("type") in ("image", "image_url"):
                    if skip_imgs > 0:
                        skip_imgs -= 1
                        images.append(None)
                    else:
                        images.append(_image_url(p))
                elif p.get("type") == "video_url":
                    texts.append("[webcam clip]")
            raw = "\n".join(t for t in texts if t).strip()
            if not raw and not images:
                continue
            if raw == GLANCE:
                spontaneous = True
                continue
            if raw.startswith(("[Summary of the earlier conversation]", "[Ringkasan")):
                add({"kind": "note", "text": "Earlier conversation was summarized to save context", "detail": raw,
                     "level": "muted"}, mi)
                continue
            if raw.startswith("(auto)"):
                add({"kind": "note", "text": "Continuing automatically…", "level": "muted"}, mi)
                continue
            if raw.startswith("[note] ") or raw.startswith("[the image(s) you just opened with read_file"):
                add({"kind": "note", "text": raw.strip("[]").replace("note] ", ""), "level": "muted",
                     "images": [u for u in images if u]}, mi)
                continue
            text, files, cmd = clean_user_text(raw)
            alias = aliases.get(str(mi))
            add({"kind": "user", "text": alias or text, "files": files, "images": [u for u in images if u],
                 "hidden_images": sum(1 for u in images if u is None), "command": cmd if not alias else None,
                 "prompt": raw if alias else None}, mi)
        elif role == "assistant":
            buf: list[str] = []

            def flush_text():
                txt = "\n\n".join(t for t in buf if t.strip()).strip()
                buf.clear()
                if txt:
                    add({"kind": "assistant", "text": txt, "spontaneous": spontaneous}, mi)
            for p in parts:
                if not isinstance(p, dict):
                    continue
                typ = p.get("type")
                if typ == "text":
                    buf.append(p.get("text", ""))
                elif typ == "thinking":
                    flush_text()
                    if (p.get("thinking") or "").strip():
                        add({"kind": "thinking", "text": p["thinking"]}, mi)
                elif typ == "tool_use":
                    flush_text()
                    it = tool_item(p.get("name", "?"), p.get("input", {}), p.get("id") or f"t{mi}-{len(items)}")
                    if it["name"] in DIFF_TOOLS:
                        it["diff"] = approx_diff(it["name"], it["input"])
                    add(it, mi)
                    tools_by_id[it["id"]] = it
            flush_text()
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function") or {}
                it = tool_item(fn.get("name", "?"), fn.get("arguments", "{}"), tc.get("id") or f"t{mi}-{len(items)}")
                if it["name"] in DIFF_TOOLS:
                    it["diff"] = approx_diff(it["name"], it["input"])
                add(it, mi)
                tools_by_id[it["id"]] = it
            spontaneous = False
    last_ai = max((i for i, m in enumerate(messages) if m.get("role") == "assistant"), default=-1)
    for it in tools_by_id.values():                 # a call with no result: the turn was cut off before it ran
        if it["status"] == "running" and not (live and it.get("mi") == last_ai):
            it["status"] = "interrupted"
    return items
