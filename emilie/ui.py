"""Display of tool calls, diffs and the one-key permission prompt."""
import difflib
import os
import re
import select
import sys
from pathlib import Path

from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text

from .i18n import t as tr_, N_
from .theme import ADD, DEL, ERR, LAV, MUTED, OK, ROSE, WARN

LABELS = {"bash": "Bash", "bash_bg": "Bash(bg)", "bg_output": "BgOutput", "bg_stop": "BgStop", "write_file": "Write", "edit_file": "Update",
          "read_file": "Read", "grep": "Search", "glob": "Glob", "web_fetch": "Fetch", "web_search": "WebSearch", "task": "Task", "tasks": "Tasks", "exit_plan_mode": "Plan",
          "todo_write": "Todos", "use_skill": "Skill"}


def label(name: str) -> str:
    if name.startswith("mcp__"):
        _, srv, tool = (name.split("__", 2) + ["", ""])[:3]
        return f"MCP {srv}:{tool}"
    return LABELS.get(name, name)


def _one_line(s: str, n: int = 100) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _target(name: str, args: dict) -> str:
    if name in ("bash", "bash_bg"):
        return args.get("command", "")
    if name in ("bg_output", "bg_stop"):
        return f"task {args.get('id') or 'all'}"
    if name in {"grep", "glob"}:
        return f"{args.get('pattern', '')}  {args.get('path', '')}".strip()
    if name == "web_fetch":
        return args.get("url", "")
    if name == "web_search":
        return args.get("query", "")
    if name == "task":
        return args.get("description", "")
    if name == "tasks":
        return ", ".join(str(j.get("description", "?")) for j in args.get("jobs", []) if isinstance(j, dict))[:100]
    if name == "exit_plan_mode":
        first = next((l.strip(" #*-") for l in str(args.get("plan", "")).splitlines() if l.strip()), "")
        return first[:80]
    if name == "todo_write":
        return f"{len(args.get('todos', []))} item"
    if "path" in args:
        return args["path"]
    import json as _json
    return _json.dumps(args, ensure_ascii=False)[:300]


def tool_header(console: Console, name: str, args: dict) -> None:
    t = Text()
    t.append("● ", style=f"bold {ROSE}")
    t.append(label(name), style="bold")
    t.append(f"({_one_line(_target(name, args))})", style=MUTED)
    console.print(t)


def tool_result(console: Console, name: str, out: str, dt: float | None = None) -> None:
    lines = out.splitlines() or [""]
    err = out.startswith("ERROR") or (name == "bash" and not out.startswith("exit=0"))
    if name == "read_file" and not err:
        n = sum(1 for l in lines if re.match(r"\s*\d+\t", l))
        summary = ([tr_('Read {n} lines', n=n) + (" (partial)" if any(l.startswith("...[lines") for l in lines) else "")]
                   if n else [_one_line(lines[0], 80)])      # PDF, notebook, image: not a numbered text file
    elif name == "glob":
        summary = ["no files" if lines == ["no matches"] else f"{len(lines)} file"]
    elif name == "web_fetch" and not err:
        summary = [tr_('Fetched {0} characters', len(out))]
    elif name == "web_search" and not err:
        summary = [tr_('{0} results', sum(1 for l in lines if re.match(r"\d+\. ", l)))]
    elif name == "todo_write":
        summary = lines[:1]
    elif name in {"write_file", "edit_file"}:
        summary = lines[:1]
    elif name == "grep":
        summary = [lines[0] if lines == ["no matches"] else f"{len(lines)} kecocokan"]
    else:  # bash
        body = lines[1:] if lines and lines[0].startswith("exit=") else lines
        body = [l for l in body if l.strip()]
        head = lines[0] if lines and lines[0].startswith("exit=") and err else ""
        summary = ([head] if head else []) + body[:6]
        if len(body) > 6:
            summary.append(tr_("… +{0} lines", len(body) - 6))
        if not summary:
            summary = ["(no output)"]
    if dt is not None and dt >= 0.05 and summary:
        summary = [summary[0] + f"  ({dt:.2f}s)"] + summary[1:]
    style = ERR if err else MUTED
    for i, l in enumerate(summary):
        console.print(Text(("  ⎿ " if i == 0 else "    ") + _one_line(l, 140), style=style))


def make_preview(name: str, args: dict) -> Text | None:
    """Coloured diff for edit/write."""
    try:
        if name == "edit_file":
            from . import tools as _tools
            old, new, _eol, err = _tools.compute_edit(
                args["path"], args.get("old_string", ""), args.get("new_string", ""),
                bool(args.get("replace_all")), args.get("edits"))
            if err:
                return None
        elif name == "write_file":
            p = Path(args["path"]).expanduser()
            old = p.read_text() if p.exists() else ""
            new = old + args["content"] if args.get("append") else args["content"]
        else:
            return None
    except (OSError, KeyError, UnicodeDecodeError):
        return None

    t = Text()
    if not old:
        ls = new.splitlines()
        for l in ls[:14]:
            t.append(f"+ {l}\n", style=ADD)
        if len(ls) > 14:
            t.append(tr_('  … +{0} more lines (new file, {1} lines)', len(ls) - 14, len(ls)), style=MUTED)
        return t
    diff = list(difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=2))[2:]
    for l in diff[:30]:
        style = ADD if l.startswith("+") else DEL if l.startswith("-") else LAV if l.startswith("@@") else MUTED
        t.append(l[:160] + "\n", style=style)
    if len(diff) > 30:
        t.append(tr_('… +{0} more diff lines', len(diff) - 30), style=MUTED)
    return t if diff else None


def print_preview(console: Console, name: str, args: dict) -> None:
    pv = make_preview(name, args)
    if pv:
        console.print(Panel(pv, border_style=MUTED, padding=(0, 1)))


def getkey() -> str:
    """Read one key without Enter. A lone Esc -> 'esc'; arrows/other sequences -> 'seq' (ignored)."""
    if not sys.stdin.isatty():
        return "n"
    from .term import RawInput
    with RawInput() as ri:
        ch = ri.read(1).decode(errors="ignore")
        if ch == "\x1b":
            if not ri.ready(0.05):
                return "esc"          # lone Esc
            while ri.ready(0.02):
                ri.read(8)
            return "seq"              # arrows/function keys -> ignored
        return ch


def read_key() -> str:
    """One key: 'up','down','pgup','pgdn','enter','esc','ctrl-c', or its character."""
    if not sys.stdin.isatty():
        return "esc"
    from .term import RawInput
    with RawInput() as ri:
        b = ri.read(1)
        if b == b"\x1b":
            if not ri.ready(0.05):
                return "esc"
            seq = b""
            while ri.ready(0.02):
                seq += ri.read(8)
            return {b"[A": "up", b"OA": "up", b"[B": "down", b"OB": "down",
                    b"[5~": "pgup", b"[6~": "pgdn"}.get(seq, "seq")
        if b in (b"\r", b"\n"):
            return "enter"
        if b == b"\x03":
            return "ctrl-c"
        return b.decode(errors="ignore").lower()


def plan_panel(plan: str) -> tuple[Panel, Text]:
    """The plan the model wants approved (exit_plan_mode): the plan as markdown + three clear choices."""
    from rich.markdown import Markdown
    opts = Text()
    opts.append("[y]", style=f"bold {OK}"); opts.append(tr_(" approve, ask before each change   "))
    opts.append("[t]", style=f"bold {ROSE}"); opts.append(tr_(" approve and run on its own   "))
    opts.append("[n]", style=f"bold {ERR}"); opts.append(tr_(" keep planning"))
    return (Panel(Markdown((plan or "(empty plan)")[:8000]), title=tr_('[bold {LAV}]plan: ready to start?[/]', LAV=LAV),
                  title_align="left", border_style=LAV, padding=(0, 1)), opts)


def permission_panel(name: str, args: dict, reason: str) -> tuple[Panel, Text]:
    """(detail panel, choice lines) - used by both classic and full-screen mode."""
    if name == "exit_plan_mode":
        return plan_panel(str(args.get("plan", "")))
    body = [Text(_target(name, args)[:2500], style="bold")]
    if reason:
        body.append(Text(f"! {reason}", style=WARN))
    pv = make_preview(name, args)
    if pv:
        body += [Text(""), pv]
    opts = Text()
    opts.append("[y]", style=f"bold {OK}"); opts.append(tr_(" yes   "))
    if not reason:
        opts.append("[a]", style=f"bold {LAV}"); opts.append(tr_(" always {0}   ", label(name)))
        opts.append("[t]", style=f"bold {ROSE}"); opts.append(tr_(' trust this folder   '))
    opts.append("[n]", style=f"bold {ERR}"); opts.append(tr_(" deny"))
    return (Panel(Group(*body), title=tr_('[bold {WARN}]permission: {0}[/]', label(name), WARN=WARN),
                  title_align="left", border_style=WARN, padding=(0, 1)), opts)


ANS_LABEL = dict(y=N_("allowed"), a=N_('allowed (always)'), t=N_('folder trusted'), n=N_("denied"))


def ask_permission(console: Console, name: str, args: dict, reason: str) -> str:
    """return 'y' | 'a' | 't' | 'n'"""
    tui = getattr(console, "tui", None)
    if tui is not None:                                  # full-screen mode: the keys are handled by the app
        return tui.ask_permission(name, args, reason)
    panel, opts = permission_panel(name, args, reason)
    console.print(panel)
    console.print(opts)
    while True:
        k = getkey().lower()
        if k in {"y", "\r", "\n"}:
            ans = "y"
        elif k == "a" and not reason:
            ans = "a"
        elif k == "t" and not reason:
            ans = "t"
        elif k == "\x03":
            console.print(tr_('  [{MUTED}]→ stopped[/]', MUTED=MUTED))
            raise KeyboardInterrupt          # ctrl+c = stop the whole agent, not just refuse
        elif k in {"n", "esc", "\x04"}:
            ans = "n"
        else:
            continue  # other keys are ignored, no message spam
        console.print(f"  [{MUTED}]→ {tr_(ANS_LABEL[ans])}[/]")
        return ans


def denied(console: Console, name: str, reason: str) -> None:
    console.print(Text(tr_('⊘ {0} blocked — {reason}', label(name), reason=reason), style=WARN))


def print_todos(console: Console, todos: list[dict]) -> None:
    if not todos:
        return
    t = Text()
    for i, it in enumerate(todos):
        st = it.get("status")
        mark, style = {"completed": ("☑", f"{MUTED} strike"), "in_progress": ("◐", f"bold {ROSE}")}.get(st, ("☐", ""))
        t.append(f"{mark} {it.get('content', '')}", style=style)
        if i < len(todos) - 1:
            t.append("\n")
    done = sum(1 for x in todos if x.get("status") == "completed")
    console.print(Panel(t, title=tr_('[bold {LAV}]todo {done}/{0}[/]', len(todos), LAV=LAV, done=done), title_align="left",
                        border_style=MUTED, padding=(0, 1)))


def show_submission(console: Console, sub) -> None:
    """Show what the agent 'read': pasted text and attached images."""
    for n, txt in sub.pastes:
        ls = txt.splitlines()
        console.print(Text(tr_('  ⎿ Pasted text #{n} · {0} lines · {1:,} chars', len(ls), len(txt), n=n), style=MUTED))
        for l in ls[:3]:
            console.print(Text(f"    │ {l[:100]}", style=MUTED))
        if len(ls) > 3:
            console.print(Text(tr_('    │ … +{0} more lines', len(ls) - 3), style=MUTED))
    for n, (w, h), size in sub.image_meta:
        console.print(Text(tr_('  ⎿ Image #{n} · {w}×{h} · {0} KB', size // 1024, n=n, w=w, h=h), style=MUTED))


def _msg_text(m: dict) -> str:
    c = m.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") == "text")
    return ""


def show_history(console: Console, messages: list[dict], n: int = 3) -> None:
    """Preview of the latest history when a session is resumed (emilie -c / -r)."""
    items = []
    for m in messages:
        txt = " ".join(_msg_text(m).split())
        if m.get("role") == "user" and txt and not txt.startswith(("[Summary of the earlier", "[Ringkasan")):
            items.append(("you", txt))
        elif m.get("role") == "assistant" and txt:
            items.append(("emilie", txt))
    if not items:
        return
    t = Text()
    for i, (who, txt) in enumerate(items[-n * 2:]):
        t.append(f"{who:<7}", style=f"bold {ROSE}" if who == "emilie" else f"bold {LAV}")
        t.append(txt[:150] + ("…" if len(txt) > 150 else ""), style=MUTED if who == "emilie" else "")
        t.append("\n")
    t.rstrip()
    console.print(Panel(t, title=tr_('[bold {LAV}]recent history · {0} messages[/]', len(messages), LAV=LAV), title_align="left",
                        border_style=MUTED, padding=(0, 1)))


def replay_history(console: Console, messages: list[dict], updated: float | None = None, limit: int = 400) -> None:
    """Show the WHOLE conversation of an old session in the conversation area (scrollable), so its context can be read."""
    import json
    from rich.markdown import Markdown
    from rich.rule import Rule
    from . import session as _session

    def tool_row(name: str, args) -> None:
        if isinstance(args, str):
            try:
                args = json.loads(args or "{}")
            except ValueError:
                args = {}
        t = Text()
        t.append("● ", style=f"bold {ROSE}")
        t.append(label(name), style="bold")
        t.append(f"({_one_line(_target(name, args if isinstance(args, dict) else {}))})", style=MUTED)
        console.print(t)

    def result_row(content) -> None:
        txt = content if isinstance(content, str) else " ".join(
            p.get("text", "") for p in (content or []) if isinstance(p, dict))
        lines = [l for l in str(txt).splitlines() if l.strip()]
        first = _one_line(lines[0], 130) if lines else "(no output)"
        more = f"  (+{len(lines) - 1} lines)" if len(lines) > 1 else ""
        console.print(Text(f"  ⎿ {first}{more}", style=MUTED))

    hidden = max(0, len(messages) - limit)
    msgs = messages[hidden:]
    ago = tr_(' · last used {0}', _session.ago(updated)) if updated else ""
    console.print(Rule(tr_('[bold {LAV}]resumed session · {0} messages{ago}[/]', len(messages), LAV=LAV, ago=ago), style=MUTED))
    if hidden:
        console.print(Text(tr_("… {hidden} earlier messages not shown (still in the agent's memory)", hidden=hidden), style=MUTED))
    for m in msgs:
        role, c = m.get("role"), m.get("content")
        if role == "tool":                                       # format OpenAI
            result_row(c)
            continue
        parts = [{"type": "text", "text": c}] if isinstance(c, str) else (c or [])
        if role == "user":
            texts = [p.get("text", "") for p in parts if isinstance(p, dict) and p.get("type") == "text"]
            has_img = any(isinstance(p, dict) and p.get("type") in ("image", "image_url") for p in parts)
            for p in parts:                                       # Anthropic format: tool result
                if isinstance(p, dict) and p.get("type") == "tool_result":
                    result_row(p.get("content"))
            body = "\n".join(t for t in texts if t).strip()
            if body:
                console.print()
                if body.startswith(("[Summary of the earlier", "[Ringkasan")):
                    console.print(Text(tr_('(summary of an even earlier part of this conversation)'), style=MUTED))
                    console.print(Text(body[:1200], style=MUTED))
                else:
                    console.print(Text.assemble(("❯ ", f"bold {ROSE}"), (body[:2000] + ("…" if len(body) > 2000 else ""), "bold")))
            if has_img:
                console.print(Text("  [image attached]", style=MUTED))
        elif role == "assistant":
            text = "\n".join(p.get("text", "") for p in parts if isinstance(p, dict) and p.get("type") == "text").strip()
            if text:
                console.print()
                console.print(Markdown(text[:12000]))
            for p in parts:                                       # format Anthropic
                if isinstance(p, dict) and p.get("type") == "tool_use":
                    tool_row(p.get("name", "?"), p.get("input", {}))
            for tc in m.get("tool_calls") or []:                  # format OpenAI
                tool_row(tc["function"]["name"], tc["function"]["arguments"])
    console.print()
    console.print(Rule(tr_('[bold {LAV}]end of previous conversation - continue below[/]', LAV=LAV), style=MUTED))
    console.print()
