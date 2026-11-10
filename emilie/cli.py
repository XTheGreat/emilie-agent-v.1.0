from . import paths
import os
import subprocess
import sys
import time

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .i18n import t as tr_
from . import i18n, language, persona, trust, talk, voice, __version__, context, effort as eff, logo, mcp, models, session, skills, tools, transcript, ui, viewer
from .agent import Agent, QuotaExhausted
from .banner import print_banner
from .config import PROVIDER
from . import inputbox
from .inputbox import COMMANDS, MODE_LABEL, InputBox
from .policy import Policy
from .theme import ERR, LAV, MUTED, OK, ROSE, WARN


def _bar(frac: float, width: int = 24) -> str:
    n = min(width, max(0, round(frac * width)))
    color = OK if frac < 0.6 else WARN if frac < 0.9 else ERR
    return f"[{color}]{'█' * n}[/][{MUTED}]{'░' * (width - n)}[/]"


def _k(n: float) -> str:
    return f"{n / 1000:.1f}k" if n >= 1000 else str(int(n))


def _help(console: Console) -> None:
    t = Table.grid(padding=(0, 3))
    for c, d in COMMANDS.items():
        t.add_row(f"[bold {ROSE}]{c}[/]", tr_(d))
    for c, d in inputbox.EXTRA_COMMANDS.items():
        t.add_row(f"[bold {ROSE}]{c}[/]", d)
    t.add_row("", "")
    for k, d in [("← → ↑ ↓", tr_('move cursor / command history')), ("ctrl+← →", tr_('jump by word')),
                 (tr_('shift+tab'), tr_('cycle mode: ask → trust → plan')), (tr_('alt+enter'), tr_('new line')), (tr_('mouse wheel / PgUp PgDn'), tr_('scroll the conversation')),
                 ("mouse drag", tr_("select text and copy it (double click = word, triple = line)")), ("ctrl+v", tr_('paste an image from the clipboard')), (tr_('drag image'), tr_('becomes [Image #n] automatically')),
                 (tr_('long paste'), "becomes [Pasted text #n +N lines]"),
                 ("@file", tr_("include a file's contents (tab = autocomplete)")),
                 ("!command", tr_('run a shell command directly')),
                 ("# note", tr_("save a note to the project's EMILIE.md")),
                 ("alt+c", tr_('take one photo with the camera and attach it to your message')),
                 ("alt+v", tr_('video call: a small camera window; she sees you and may start talking by herself; your messages include the last seconds of video')),
                 ("ctrl+c", tr_('stop the agent / clear typing; twice on an empty prompt = exit')),
                 ("emilie -c / -r", tr_('continue the last session / pick a session'))]:
        t.add_row(f"[bold {ROSE}]{k}[/]", d)
    console.print(Panel(t, title=tr_('[bold {ROSE}]help[/]', ROSE=ROSE), title_align="left",
                        border_style=MUTED, padding=(1, 2)))


def _show_skills(console: Console) -> None:
    t = Table(box=None, padding=(0, 2), header_style=f"bold {LAV}")
    for c in (tr_("name"), tr_("phase"), tr_("type"), tr_("source"), tr_("files"), tr_("description")):
        t.add_column(c)
    order = {pid: i for i, (pid, _l) in enumerate(skills.PHASES)}
    for n, sk in sorted(skills.SKILLS.items(), key=lambda kv: (order.get(kv[1].phase, 99), kv[0])):
        res = skills.resources(sk)
        files = tr_("{0} refs · {1} scripts", len(res["references"]), len(res["scripts"])) if (res["references"] or res["scripts"]) else "-"
        t.add_row(f"[bold {ROSE}]/{n}[/]", skills.phase_label(sk.phase) if sk.phase else "-", tr_('skill'), sk.source, files, sk.description[:60])
    for n, c in skills.COMMANDS.items():
        t.add_row(f"[bold {ROSE}]/{n}[/]", "-", tr_('command'), c.source, "-", c.description[:60])
    if not (skills.SKILLS or skills.COMMANDS):
        t.add_row("-", "-", "-", "-", "-", tr_('none found'))
    console.print(Panel(t, title=tr_('[bold {ROSE}]skills & commands[/]', ROSE=ROSE), title_align="left", border_style=MUTED,
                        subtitle=tr_('[{MUTED}]./.emilie|.claude/skills/<name>/SKILL.md  ·  commands/<name>.md  ·  ~/.emilie|.claude/...[/]', MUTED=MUTED),
                        padding=(1, 2)))
    w = Table(box=None, padding=(0, 2), header_style=f"bold {LAV}")
    for c in (tr_("phase"), tr_("installed"), tr_("planned, not installed yet")):
        w.add_column(c)
    for pid, _lab in skills.PHASES:
        have = [n for n, sk in skills.SKILLS.items() if sk.phase == pid]
        todo = [n for n in skills.CATALOG.get(pid, []) if n not in skills.SKILLS]
        w.add_row(f"[bold {ROSE}]{skills.phase_label(pid)}[/]", ", ".join(f"[{OK}]{n}[/]" for n in have) or "-",
                  f"[{MUTED}]{', '.join(todo)}[/]" if todo else "")
    console.print(Panel(w, title=tr_('[bold {ROSE}]development phases[/]', ROSE=ROSE), title_align="left", border_style=MUTED,
                        subtitle=tr_('[{MUTED}]/dev <task>  takes a task through these phases, like a senior developer[/]', MUTED=MUTED),
                        padding=(1, 2)))
    for msg in skills.SKIPPED:
        console.print(tr_('[{WARN}]skipped:[/] {0}', msg.replace(os.path.expanduser('~'), '~'), WARN=WARN))


def _show_mcp(console: Console) -> None:
    t = Table(box=None, padding=(0, 2), header_style=f"bold {LAV}")
    for c in (tr_("server"), tr_("status"), tr_("tools"), tr_("command")):
        t.add_column(c)
    for s_ in mcp.SERVERS.values():
        st = {"ready": f"[{OK}]ready[/]", "failed": f"[{ERR}]failed[/]"}.get(s_.status, f"[{WARN}]{s_.status}[/]")
        t.add_row(s_.name, st + (f" [{MUTED}]{s_.error[:50]}[/]" if s_.error else ""), str(len(s_.tool_names)),
                  f"{s_.command} {' '.join(map(str, s_.args))}"[:60])
    if not mcp.SERVERS:
        t.add_row("-", "-", "-", tr_('none configured'))
    console.print(Panel(t, title=tr_('[bold {ROSE}]MCP servers[/]', ROSE=ROSE), title_align="left", border_style=MUTED,
                        subtitle=tr_('[{MUTED}]config: ./.mcp.json or ~/.emilie/mcp.json  ·  tools always ask for permission[/]', MUTED=MUTED),
                        padding=(1, 2)))


def _show_effort(console: Console, agent: Agent) -> None:
    t = Table(box=None, padding=(0, 2), show_header=True, header_style=f"bold {LAV}")
    for c in (tr_("level"), tr_('max answer'), tr_('tool output'), tr_("rounds"), tr_("compacts at"), tr_("notes")):
        t.add_column(c)
    for e in eff.LEVELS.values():
        cur = e.name == agent.effort.name
        mark = f"[bold {ROSE}]▸ {e.name}[/]" if cur else f"  {e.name}"
        t.add_row(mark, tr_('{0:,} tok', e.max_output), tr_('{0:,} char', e.tool_out_chars), str(e.max_rounds),
                  tr_('~{0} tok', _k(e.compact_at)), tr_(e.desc))
    console.print(Panel(t, title=tr_('[bold {ROSE}]effort[/]', ROSE=ROSE), title_align="left", border_style=MUTED,
                        subtitle=tr_('[{MUTED}]/effort low|medium|high|max[/]', MUTED=MUTED), padding=(1, 2)))


def _context(console: Console, agent: Agent) -> None:
    from .agent import est_tokens
    sysn, hist, tl = est_tokens(agent.system_prompt()), est_tokens(agent.messages), est_tokens(tools.SCHEMAS)
    total, limit = sysn + hist + tl, agent.effort.compact_at
    t = Table.grid(padding=(0, 2))
    t.add_row(tr_('system + memory'), f"~{_k(sysn)}")
    t.add_row(tr_('tool definitions'), f"~{_k(tl)}")
    t.add_row(tr_('history'), tr_('~{0}  ({1} messages)', _k(hist), len(agent.messages)))
    t.add_row(tr_('[bold]total[/]'), f"[bold]~{_k(total)}[/] / {_k(limit)}  {_bar(total / limit)}  {total * 100 // limit}%")
    console.print(Panel(t, title=tr_('[bold {ROSE}]context (estimate)[/]', ROSE=ROSE), title_align="left",
                        border_style=MUTED, subtitle=tr_('[{MUTED}]auto-compacts at {0}[/]', _k(limit), MUTED=MUTED),
                        padding=(1, 2)))


def _cost(console: Console, agent: Agent) -> None:
    u = agent.usage
    tag = "" if u.exact else "~"
    t = Table.grid(padding=(0, 2))
    t.add_row(tr_('model calls'), str(u.calls))
    t.add_row(tr_('input tokens'), f"{tag}{u.inp:,}")
    t.add_row(tr_('output tokens'), f"{tag}{u.out:,}")
    t.add_row(tr_('[bold]total[/]'), f"[bold]{tag}{u.inp + u.out:,}[/]")
    m = models.multiplier(agent.model)
    if m:
        t.add_row(tr_('[{MUTED}]weighted ×{m:g}[/]', MUTED=MUTED, m=m), f"[{MUTED}]{tag}{int((u.inp + u.out) * m):,}[/]")
    note = tr_('exact numbers from the provider') if u.exact else tr_('estimate: the provider sends no usage data')
    console.print(Panel(t, title=tr_('[bold {ROSE}]session usage[/]', ROSE=ROSE), title_align="left",
                        border_style=MUTED, subtitle=f"[{MUTED}]{note}[/]", padding=(1, 2)))


def _pick_session(console: Console, cwd: str) -> dict | None:
    """Interactive session picker (up/down Enter Esc), newest first."""
    items = session.list_sessions(cwd, 15)
    if not items:
        console.print(tr_('[{MUTED}]no saved sessions in this folder[/]', MUTED=MUTED))
        return None
    tui = getattr(console, "tui", None)
    if tui is not None:                        # full screen: the picker is shown as an overlay
        rows = [[("bold", f"{it['title'][:60]:<62}"), (MUTED, f"{session.ago(it['updated']):<14}{it['n']} messages")]
                for it in items]
        res = tui.choose(tr_('resume session'), rows, 0)
        return session.load(cwd, items[res[1]]["id"]) if res and res[0] == "enter" else None
    idx = 0

    def render():
        t = Table(box=None, padding=(0, 2), header_style=f"bold {LAV}")
        for c in ("", tr_("conversation"), tr_('last used'), tr_("messages")):
            t.add_column(c)
        for i, it in enumerate(items):
            sel = i == idx
            t.add_row("▸" if sel else " ", Text(it["title"][:70], style=f"bold {ROSE}" if sel else ""),
                      Text(session.ago(it["updated"]), style=MUTED), Text(str(it["n"]), style=MUTED))
        return Panel(t, title=tr_('[bold {ROSE}]resume session[/]', ROSE=ROSE), title_align="left", border_style=MUTED,
                     subtitle=tr_('[{MUTED}]↑↓ select · Enter resume · Esc cancel[/]', MUTED=MUTED), padding=(1, 2))

    chosen = None
    with Live(render(), console=console, transient=True, auto_refresh=False) as lv:
        while True:
            k = ui.read_key()
            if k in ("up", "k"):
                idx = (idx - 1) % len(items)
            elif k in ("down", "j"):
                idx = (idx + 1) % len(items)
            elif k == "enter":
                chosen = items[idx]
                break
            elif k in ("esc", "ctrl-c", "q"):
                break
            lv.update(render(), refresh=True)
    return session.load(cwd, chosen["id"]) if chosen else None


INIT_PROMPT = ("Analyze the project in this folder (structure, language, how to run/test) using the read tools, "
               "then create a short EMILIE.md (max 40 lines) containing: project summary, key structure, "
               "build/run/test commands, and code conventions. Do not guess; write only what you verified.")


_ALT = False


def _enter_alt() -> None:
    """Alternate screen (like vim/less): on exit the terminal returns EXACTLY as it was before."""
    global _ALT
    if not _ALT:
        sys.stdout.write("\x1b[?1049h\x1b[2J\x1b[H")
        sys.stdout.flush()
        _ALT = True


def _leave_alt() -> None:
    global _ALT
    if _ALT:
        sys.stdout.write("\x1b[?1049l")
        sys.stdout.flush()
        _ALT = False


box_ref: list = []        # filled in by main(): access to the InputBox from _scrollback


def _scrollback(console: Console) -> None:
    """Open the history viewer; after it closes, redraw the end of the history on screen."""
    text = transcript.text()
    if not text.strip():
        console.print(tr_('[{MUTED}]no display history yet[/]', MUTED=MUTED))
        return
    viewer.view(text)
    sys.stdout.write(viewer.tail(text))
    sys.stdout.flush()
    if box_ref:
        box_ref[0].scroll_block_until = time.monotonic() + 1.5   # leftover trackpad momentum does not reopen it


class Core:
    """The application core shared by both interfaces (full-screen & classic)."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


def make_core(console: Console, argv: list[str], hooks) -> Core:
    """hooks: antarmuka-spesifik → load_logo()->str|None, clear(), history(), show_logo_banner()."""
    skills.load(os.getcwd())
    inputbox.EXTRA_COMMANDS.clear()
    inputbox.EXTRA_COMMANDS.update(skills.extras())
    if "--banner" not in argv:
        mcp.start_all(os.getcwd())
    policy = Policy(os.getcwd())
    if "--trust" in argv:
        policy.mode = "trust"
    if "--plan" in argv:
        policy.mode = "plan"
    agent = Agent(console, policy, eff.load_effort())

    def banner_info() -> dict:
        return {"version": __version__, "model": agent.active_model,
                "cwd": os.getcwd().replace(os.path.expanduser("~"), "~", 1),
                "effort": agent.effort.name, "mode": tr_(MODE_LABEL[policy.mode]),
                "session": agent.session_id[-8:], "tools": tools.groups()}

    def short_cwd(n: int = 28) -> str:
        """Long ~/a/b/c -> …/b/c so the footer is not pushed off the screen."""
        d = os.getcwd().replace(os.path.expanduser("~"), "~", 1).replace("\\", "/")
        if len(d) <= n:
            return d
        parts = d.split("/")
        out = parts[-1]
        for seg in reversed(parts[:-1]):
            if len(out) + len(seg) + 2 > n:
                break
            out = seg + "/" + out
        return "…/" + out[-(n - 2):]

    def status() -> dict:
        home = os.path.expanduser("~")
        pct = min(999, agent.ctx_tokens() * 100 // agent.effort.compact_at)
        return {"model": agent.active_model, "mult": models.multiplier(agent.active_model),
                "cwd": short_cwd(), "mode": policy.mode,
                "mode_label": tr_(MODE_LABEL[policy.mode]), "effort": agent.effort.name, "ctx": pct}

    def startup(real_console: Console) -> None:
        """Continue a session (-c / -r) and show the memory; the -r picker uses the real terminal."""
        data = None
        if "--continue" in argv or "-c" in argv:
            ss = session.list_sessions(os.getcwd(), 1)
            data = session.load(os.getcwd(), ss[0]["id"]) if ss else None
        elif "--resume" in argv or "-r" in argv:
            data = _pick_session(real_console, os.getcwd())
        if data:
            agent.resume(data)
            ui.replay_history(console, data["messages"], data.get("updated"))
        if agent.memory_files:
            console.print(tr_('[{MUTED}]memory loaded: {0}[/]', ', '.join(str(f).replace(os.path.expanduser('~'), '~') for f in agent.memory_files), MUTED=MUTED))

    def run(text: str, images=None) -> bool:
        """True if it was stopped/failed. The steps already finished stay in the history (agent.salvaged says how many)."""
        console.print()
        stopped = False
        try:
            agent.run_turn(text, images or [])
        except KeyboardInterrupt:
            stopped = True
            if agent.salvaged:
                console.print(tr_("\n[{ERR}]stopped[/] [{MUTED}]· your progress is kept ({0} steps) · say what to do next, or type 'continue'[/]", agent.salvaged, ERR=ERR, MUTED=MUTED))
            else:
                console.print(tr_('\n[{ERR}]stopped[/] [{MUTED}]· this turn was removed from history[/]', ERR=ERR, MUTED=MUTED))
        except QuotaExhausted as q:
            stopped = True
            info = Table.grid(padding=(0, 2))
            if q.name:
                info.add_row(tr_('[{MUTED}]account[/]', MUTED=MUTED), q.name)
            if q.quota:
                info.add_row(tr_('[{MUTED}]quota[/]', MUTED=MUTED), q.quota)
            if q.expires:
                info.add_row(tr_('[{MUTED}]valid until[/]', MUTED=MUTED), q.expires)
            info.add_row("", "")
            info.add_row(tr_('[{MUTED}]fix[/]', MUTED=MUTED), tr_('top up your quota on the bankai dashboard, or change [bold]EMILIE_API_KEY[/] in .env'))
            info.add_row("", tr_('[{MUTED}]/model to try another model · this turn was not saved to history[/]', MUTED=MUTED)
                         if not agent.salvaged else
                         tr_("[{MUTED}]your progress is kept ({0} steps) · /model to switch, then type 'continue'[/]", agent.salvaged, MUTED=MUTED))
            console.print(Panel(info, title=tr_('[bold {ERR}]API quota exhausted[/]', ERR=ERR), title_align="left",
                                border_style=ERR, padding=(0, 1)))
        except Exception as e:
            body = f"{type(e).__name__}: {e}"[:800]
            if agent.salvaged:
                body += "\n" + tr_("your progress is kept ({0} steps) · /model to switch, then type 'continue'", agent.salvaged)
            console.print(Panel(body, title=tr_('[bold]error[/]'), border_style=ERR, title_align="left"))
        console.print()
        return stopped

    def hint() -> str | None:
        if agent.messages:
            return (tr_('[{MUTED}]resume: [/][bold {ROSE}]emilie -r[/][{MUTED}] (pick a session) · [/][bold {ROSE}]emilie -c[/][{MUTED}] (last session)[/]', MUTED=MUTED, ROSE=ROSE))
        return None

    def process(sub) -> str | None:
        """One user input. Returns "exit" to quit."""
        text = sub.text
        if not text and not sub.images:
            return None
        voice.VOICE.stop()                  # a new message silences the previous reply
        voice.VOICE.story = bool(text) and not text.startswith(("/", "!", "#")) and bool(voice.STORY_RE.search(text))
        voice.VOICE.notify = lambda m: console.print(f"[{MUTED}]{m}[/]")

        # ---------- slash commands ----------
        if text.startswith("/"):
            cmd, _, arg = text.partition(" ")
            arg = arg.strip()
            if cmd in ("/exit", "/quit"):
                return "exit"
            elif cmd == "/help":
                _help(console)
            elif cmd == "/clear":
                agent.reset()
                hooks.clear()
                console.print(tr_('[{MUTED}]history cleared, new session[/]', MUTED=MUTED))
            elif cmd == "/compact":
                try:
                    if agent.compact(arg) is None:
                        console.print(tr_('[{MUTED}]not enough history to compact[/]', MUTED=MUTED))
                except Exception as e:
                    console.print(tr_('[{ERR}]compaction failed: {e}[/]', ERR=ERR, e=e))
            elif cmd == "/cost":
                _cost(console, agent)
            elif cmd == "/context":
                _context(console, agent)
            elif cmd == "/effort":
                if arg in eff.LEVELS:
                    agent.set_effort(eff.LEVELS[arg])
                    eff.save_settings(effort=arg)
                    console.print(tr_('[{MUTED}]effort →[/] [bold {ROSE}]{arg}[/] [{MUTED}]({0}, saved)[/]', tr_(agent.effort.desc), MUTED=MUTED, ROSE=ROSE, arg=arg))
                elif arg:
                    console.print(tr_('[{ERR}]unknown level:[/] {arg}  [{MUTED}](low|medium|high|max)[/]', ERR=ERR, arg=arg, MUTED=MUTED))
                _show_effort(console, agent)
            elif cmd in ("/mode", "/plan", "/trust"):
                new = {"/plan": "ask" if policy.mode == "plan" else "plan",
                       "/trust": "ask" if policy.mode == "trust" else "trust"}.get(cmd, arg)
                if new in ("ask", "trust", "plan"):
                    policy.mode = new
                    console.print(tr_('[{MUTED}]mode →[/] {0}', tr_(MODE_LABEL[new]), MUTED=MUTED))
                else:
                    console.print(tr_('[{MUTED}]current mode:[/] {0}  [{MUTED}](/mode ask|trust|plan)[/]', tr_(MODE_LABEL[policy.mode]), MUTED=MUTED))
            elif cmd in ("/allow", "/deny"):
                kind = "allow" if cmd == "/allow" else "deny"
                perms = eff.load_settings().get("permissions")
                perms = perms if isinstance(perms, dict) else {}
                rules = [r for r in perms.get(kind, []) if isinstance(r, str)]
                rm = arg.startswith("rm ")
                rule = (arg[3:] if rm else arg).strip()
                if not rule:
                    console.print(tr_('[{MUTED}]{kind} rules:[/] {0}', ", ".join(rules) or "-", MUTED=MUTED, kind=kind))
                    console.print(tr_('[{MUTED}]{cmd} <rule> adds one, {cmd} rm <rule> removes it. e.g. mcp__browser__*  ·  bash(git *)  ·  web_fetch[/]', MUTED=MUTED, cmd=cmd))
                else:
                    rules = [r for r in rules if r != rule] + ([] if rm else [rule])
                    perms[kind] = rules
                    eff.save_settings(permissions=perms)
                    console.print(tr_('[{MUTED}]{kind} rules (saved):[/] {0}', ", ".join(rules) or "-", MUTED=MUTED, kind=kind))
            elif cmd == "/undo":
                done = agent.undo()
                if done is None:
                    console.print(tr_('[{MUTED}]no file changes to undo[/]', MUTED=MUTED))
                else:
                    console.print(f"[{OK}]restored:[/] " + ", ".join(os.path.relpath(p) for p in done)
                                  + tr_('  [{MUTED}](changes made through bash are not undone)[/]', MUTED=MUTED))
            elif cmd == "/thinking":
                from . import claude as _claude
                cur = int(eff.load_settings().get("thinking") or 0)
                if PROVIDER != "anthropic":
                    console.print(tr_('[{MUTED}]extended thinking is a Claude feature: it needs the Anthropic provider (emilie --setup)[/]', MUTED=MUTED))
                elif not arg:
                    console.print(tr_('[{MUTED}]thinking:[/] {0}  [{MUTED}](/thinking on | off | <tokens, min {1}>)[/]',
                                      f"{cur} tokens" if cur else "off", _claude.MIN_THINKING, MUTED=MUTED))
                else:
                    val = {"off": 0, "on": 4000}.get(arg.lower(), int(arg) if arg.isdigit() else None)
                    if val is None or (val and val < _claude.MIN_THINKING):
                        console.print(tr_('[{ERR}]usage: /thinking on | off | <tokens, at least {0}>[/]', _claude.MIN_THINKING, ERR=ERR))
                    else:
                        eff.save_settings(thinking=val)
                        console.print(tr_('[{MUTED}]thinking →[/] {0} [{MUTED}](saved; costs extra output tokens)[/]',
                                          f"{val} tokens" if val else "off", MUTED=MUTED))
            elif cmd == "/rewind":
                parts = arg.split()
                cps = agent.checkpoints
                if not parts:
                    if not cps:
                        console.print(tr_('[{MUTED}]nothing to rewind yet: only turns that changed files are listed[/]', MUTED=MUTED))
                    for n in range(1, len(cps) + 1):
                        ck = cps[-n]
                        files = ", ".join(os.path.relpath(p) for p in list(ck)[:3]) + (" …" if len(ck) > 3 else "")
                        console.print(f"[{ROSE}]{n}[/]  {ck.label or '?'}  [{MUTED}]· {files}{'' if ck.mark is not None else ' · files only'}[/]")
                    if cps:
                        console.print(tr_('[{MUTED}]/rewind <n> [both|files|chat]  →  go back to just before that turn (1 = the latest)[/]', MUTED=MUTED))
                elif not parts[0].isdigit():
                    console.print(tr_('[{ERR}]usage: /rewind <n> [both|files|chat][/]', ERR=ERR))
                else:
                    what = parts[1] if len(parts) > 1 else "both"
                    if what not in ("both", "files", "chat"):
                        console.print(tr_('[{ERR}]usage: /rewind <n> [both|files|chat][/]', ERR=ERR))
                    else:
                        res = agent.rewind(int(parts[0]), files=what != "chat", chat=what != "files")
                        if isinstance(res, str):
                            console.print(f"[{ERR}]{res}[/]")
                        else:
                            restored, removed = res
                            console.print(f"[{OK}]rewound[/] " + (f"files: {', '.join(os.path.relpath(p) for p in restored)}  " if restored else "")
                                          + (f"· {removed} messages removed" if removed else "")
                                          + tr_('  [{MUTED}](changes made through bash are not undone)[/]', MUTED=MUTED))
            elif cmd == "/todos":
                ui.print_todos(console, agent.todos) if agent.todos else console.print(tr_('[{MUTED}]no todos yet[/]', MUTED=MUTED))
            elif cmd == "/resume":
                data = _pick_session(console, os.getcwd())
                if data:
                    agent.resume(data)
                    ui.replay_history(console, data["messages"], data.get("updated"))
            elif cmd == "/init":
                run(INIT_PROMPT)
                agent.memory_text, agent.memory_files = context.load_memory(os.getcwd())
            elif cmd == "/memory":
                if agent.memory_files:
                    for f in agent.memory_files:
                        console.print(f"  [{ROSE}]●[/] {f}")
                else:
                    console.print(tr_("[{MUTED}]no EMILIE.md / CLAUDE.md found; use /init to create one, or '# note'[/]", MUTED=MUTED))
            elif cmd == "/provider":
                from . import providers
                from .config import PROVIDER_ID
                for k, p in providers.PRESETS.items():
                    mark = "●" if k == PROVIDER_ID else " "
                    console.print(f"  [{ROSE}]{mark}[/] {k:<11} {tr_(p['label'])}")
                console.print(tr_('[{MUTED}]switch: quit and run  emilie --setup <name>  (keys are saved, restart applies it)[/]', MUTED=MUTED))
            elif cmd == "/model":
                chosen = arg or None
                if not arg and PROVIDER == "openai":
                    with console.status(tr_('[{MUTED}]loading model list…[/]', MUTED=MUTED), spinner="dots"):
                        live = models.fetch_live(agent.client)
                    chosen = models.pick_model(console, agent.model, live)
                elif not arg:
                    console.print(tr_('[{MUTED}]model:[/] {0}  [{MUTED}](/model <name> to switch)[/]', agent.model, MUTED=MUTED))
                if chosen and chosen != agent.model:
                    agent.model = chosen
                    eff.save_settings(model=chosen)
                    g, m = models.BANKAI.get(chosen, (None, None))
                    extra = tr_(" · grade {0}", g) if g else ""
                    extra += tr_(" · price ×{0}", f"{m:g}") if m else ""
                    console.print(tr_('[{MUTED}]model →[/] [bold {ROSE}]{chosen}[/][{MUTED}]{extra} (saved)[/]', MUTED=MUTED, ROSE=ROSE, chosen=chosen, extra=extra))
                elif chosen:
                    console.print(tr_('[{MUTED}]model unchanged:[/] {0}', agent.model, MUTED=MUTED))
            elif cmd in ("/history", "/scroll"):
                hooks.history()
            elif cmd in ("/ui", "/screen"):
                if arg in ("tui", "classic", "alt", "main"):
                    key = "ui" if arg in ("tui", "classic") else "screen"
                    eff.save_settings(**{key: arg})
                    console.print(tr_('[{MUTED}]{key} →[/] [bold {ROSE}]{arg}[/] [{MUTED}](applies the next time emilie starts)[/]', MUTED=MUTED, key=key, ROSE=ROSE, arg=arg))
                else:
                    console.print(tr_('[{MUTED}]/ui tui = full-screen (default: the video banner scrolls with the chat) · /ui classic = plain terminal (native scrollback)[/]', MUTED=MUTED))
            elif cmd == "/camera":
                from . import camera
                sub = arg.split()
                if sub[:1] == ["test"]:
                    data, msg = camera.grab()
                    console.print(tr_('[{OK}]camera works ({0}, {1} KB)[/]', msg, len(data) // 1024, OK=OK) if data
                                  else tr_('[{ERR}]camera: {0}[/]', msg, ERR=ERR))
                elif sub[:1] == ["view"] and len(sub) > 1 and sub[1] in ("window", "inline"):
                    eff.save_settings(camera_view=sub[1])
                    console.print(tr_('[{MUTED}]video call picture -> {0} (saved)[/]', sub[1], MUTED=MUTED))
                elif sub[:1] == ["chat"]:
                    v = sub[1] if len(sub) > 1 else ""
                    if v in ("on", "off"):
                        eff.save_settings(companion=(v == "on"))
                        console.print(tr_('[{MUTED}]video call: she {0} (saved)[/]', tr_('starts talking by herself') if v == "on" else tr_('only answers when you speak first'), MUTED=MUTED))
                    elif v.isdigit() and 15 <= int(v) <= 600:
                        eff.save_settings(companion=True, companion_secs=int(v))
                        console.print(tr_('[{MUTED}]video call: she looks at the camera about every {0} s (saved)[/]', v, MUTED=MUTED))
                    else:
                        st = eff.load_settings()
                        console.print(tr_('[{MUTED}]video call chat: {0} · every ~{1} s · /camera chat on|off|<15-600 seconds>[/]',
                                          tr_('on') if st.get("companion", True) else tr_('off'), st.get("companion_secs", 45), MUTED=MUTED))
                elif sub[:1] == ["memory"]:
                    from . import companion
                    from rich.markup import escape
                    if sub[1:2] in (["on"], ["off"]):
                        eff.save_settings(companion_memory=(sub[1] == "on"))
                        console.print(tr_('[{MUTED}]what she remembers between calls: {0} (saved)[/]', sub[1], MUTED=MUTED))
                    else:
                        for ln in companion.describe(agent._state()):
                            console.print(f"[{MUTED}]{escape(ln)}[/]", highlight=False)
                        console.print(tr_('[{MUTED}]/camera memory on|off · /camera forget deletes it all (text only, on this computer)[/]', MUTED=MUTED))
                elif sub[:1] == ["forget"]:
                    from . import companion
                    done = companion.forget()
                    agent._comp = companion.load()
                    console.print(tr_('[{MUTED}]she forgot everything she knew about you[/]', MUTED=MUTED) if done
                                  else tr_('[{MUTED}]there was nothing to forget[/]', MUTED=MUTED))
                elif sub[:1] == ["device"] and len(sub) > 1:
                    camera.set_device(None if sub[1] == "auto" else sub[1])
                    console.print(tr_('[{MUTED}]camera device -> {0} (saved)[/]', sub[1], MUTED=MUTED))
                else:
                    console.print(tr_('[{MUTED}]cameras: {0} · using: {1}[/]', ", ".join(camera.devices()) or "-",
                                      camera.configured() or "auto", MUTED=MUTED))
                    console.print(tr_('[{MUTED}]Alt+C = one photo for your next message (the camera is on only for that moment) · /camera test · /camera device <path|auto> · /camera view window|inline · /camera chat on|off|<seconds> (during Alt+V she may start talking by herself) · /camera memory · /camera forget[/]', MUTED=MUTED))
            elif cmd == "/logo":
                if arg.startswith("fps"):
                    n = arg.split()[1] if len(arg.split()) > 1 else ""
                    if n.isdigit() and 4 <= int(n) <= 60:
                        console.print(tr_('[{MUTED}]{0} (saved)[/]', hooks.set_fps(int(n)), MUTED=MUTED))
                    else:
                        console.print(tr_('[{MUTED}]/logo fps <4-60>   (Alt+F cycles 8 / 12 / 18 / 24 / 30)[/]', MUTED=MUTED))
                elif arg == "sixel":
                    console.print(tr_('[{MUTED}]{0} (saved)[/]', hooks.set_sixel(True), MUTED=MUTED))
                elif arg == "ascii":
                    console.print(tr_('[{MUTED}]{0} (saved)[/]', hooks.set_ascii(True), MUTED=MUTED))
                elif arg in ("still", "video"):
                    console.print(tr_('[{MUTED}]{0} (saved)[/]', hooks.set_still(arg == 'still'), MUTED=MUTED))
                elif arg.startswith("size"):
                    n = arg.split()[1] if len(arg.split()) > 1 else ""
                    if n == "auto":
                        eff.save_settings(logo_cols=None)
                    elif n.isdigit() and 12 <= int(n) <= 80:
                        eff.save_settings(logo_cols=int(n))
                    else:
                        console.print(tr_('[{MUTED}]/logo size <12-80|auto>  (more columns = more pixels = sharper, but taller)[/]', MUTED=MUTED))
                        return None
                    err = hooks.load_logo()
                    console.print(f"[{ERR}]{err}[/]" if err else tr_('[{MUTED}]logo size → {n} (saved)[/]', MUTED=MUTED, n=n))
                elif arg == "reset":
                    eff.save_settings(logo=None)
                    err = hooks.load_logo()
                    console.print(tr_('[{MUTED}]logo reset to default[/]', MUTED=MUTED) if not err else f"[{ERR}]{err}[/]")
                elif arg:
                    from pathlib import Path
                    f = Path(arg).expanduser()
                    if not f.is_file() or f.suffix.lower() not in logo.VIDEO_EXTS | logo.IMAGE_EXTS:
                        console.print(tr_('[{ERR}]file not found / unsupported format:[/] {arg}  [{MUTED}](mp4, webm, mov, gif, png, jpg)[/]', ERR=ERR, arg=arg, MUTED=MUTED))
                    else:
                        eff.save_settings(logo=str(f.resolve()))
                        err = hooks.load_logo()
                        console.print(tr_('[{ERR}]failed to load:[/] {err}', ERR=ERR, err=err) if err else
                                      tr_('[{MUTED}]logo changed → {0} (saved)[/]', f.name, MUTED=MUTED))
                else:
                    hooks.show_banner()
            elif cmd == "/language":
                a = arg.strip().lower()
                if a and a != "list":
                    err = i18n.set_lang(a)
                    if err:
                        console.print(f"[{ERR}]{err}[/]")
                    else:
                        hooks.refresh_language()
                        console.print(tr_('[{MUTED}]interface language: {0} (saved)[/]', i18n.available().get(a, a), MUTED=MUTED))
                else:
                    cur = i18n.current()
                    for code, name in i18n.available().items():
                        console.print(f"  [{ROSE}]{'●' if code == cur else ' '}[/] {code:<6} {name}")
                    console.print(tr_('[{MUTED}]/language <code> - change the interface language. Your own languages: ~/.emilie/locales/<code>.json[/]', MUTED=MUTED))
            elif cmd == "/mouse":
                if arg.strip().lower() in ("on", "off"):
                    console.print(tr_('[{MUTED}]{0}[/]', hooks.set_mouse(arg.strip().lower() == "on"), MUTED=MUTED))
                else:
                    console.print(tr_('[{MUTED}]/mouse on|off  -  on: drag to select + copy inside Emilie (default) · off: let the terminal select text natively[/]', MUTED=MUTED))
            elif cmd == "/reply":
                if arg.strip():
                    console.print(f"[{MUTED}]{language.set_language(arg)}[/]")
                else:
                    console.print(tr_('[{MUTED}]reply language: {0}\n/reply auto|en|id|ja|ms|ko|zh|es|fr|de|... or any language name (the language the AI answers in)[/]', language.display(), MUTED=MUTED))
            elif cmd == "/persona":
                a = arg.strip().lower()
                if a in ("on", "off"):
                    console.print(f"[{MUTED}]{persona.set_enabled(a == 'on')}[/]")
                elif a == "reset":
                    console.print(f"[{MUTED}]{persona.reset()}[/]")
                elif a == "show":
                    console.print(persona.text(), highlight=False)
                else:
                    console.print(tr_('[{MUTED}]persona: {0}  (file: {1})\n/persona on|off|show|reset  - changes apply on your next message[/]', 'on' if persona.enabled() else 'off', persona.HOME_FILE, MUTED=MUTED))
            elif cmd == "/talk":
                tui = getattr(console, "tui", None)
                a = arg.split(None, 1)
                sub_cmd, val = (a[0].lower() if a else ""), (a[1].strip() if len(a) > 1 else "")
                if sub_cmd == "pause" and val:
                    try:
                        voice.VOICE.set(talk_pause=max(0.4, min(5.0, float(val))))
                        console.print(tr_('[{MUTED}]a pause of {val}s ends your turn (restart talk mode to apply)[/]', MUTED=MUTED, val=val))
                    except ValueError:
                        console.print(tr_('[{ERR}]give seconds, e.g. /talk pause 1.5[/]', ERR=ERR))
                elif sub_cmd == "lang":
                    voice.VOICE.set(talk_lang="" if val in ("", "auto") else val)
                    console.print(tr_('[{MUTED}]talk language: {0}[/]', val or 'auto-detect', MUTED=MUTED))
                elif sub_cmd == "model" and val:
                    voice.VOICE.set(talk_model=val)
                    console.print(tr_('[{MUTED}]speech model: {val} (downloads on first use)[/]', MUTED=MUTED, val=val))
                elif tui is None:
                    console.print(tr_('[{ERR}]talk mode needs the full-screen UI (not --classic)[/]', ERR=ERR))
                elif sub_cmd in ("on", "off", ""):
                    want = (sub_cmd != "off") if sub_cmd else not talk.TALK.on
                    if want != talk.TALK.on:
                        console.print(f"[{MUTED}]{tui.talk_toggle()}[/]")
                    if want and not voice.VOICE.enabled:
                        console.print(tr_('[{MUTED}]tip: /voice on to hear the replies too[/]', MUTED=MUTED))
            elif cmd == "/voice":
                V = voice.VOICE
                a = arg.split(None, 1)
                sub_cmd, val = (a[0].lower() if a else ""), (a[1].strip() if len(a) > 1 else "")
                if sub_cmd in ("on", "off"):
                    V.set(voice=sub_cmd == "on")
                    if sub_cmd == "off":
                        V.stop()
                    console.print(tr_('[{MUTED}]voice {sub_cmd} (saved)[/]', MUTED=MUTED, sub_cmd=sub_cmd))
                elif sub_cmd == "mode" and val in ("say", "full"):
                    V.set(voice_mode=val)
                    console.print(tr_('[{MUTED}]voice mode: {val}  ({0})[/]', 'a short spoken line in the chosen language' if val == 'say' else 'reads the whole reply', MUTED=MUTED, val=val))
                elif sub_cmd == "lang" and val:
                    V.set(voice_lang=val)
                    console.print(tr_('[{MUTED}]voice language: {val}[/]', MUTED=MUTED, val=val))
                elif sub_cmd == "profile" and val:
                    V.set(voice_profile=val)
                    V._pid_cache.clear()
                    console.print(tr_('[{MUTED}]voice profile: {val}[/]', MUTED=MUTED, val=val))
                elif sub_cmd == "stop":
                    V.stop()
                    console.print(f"[{MUTED}]{tr_('Voicebox server stopped') if V.stop_server() else tr_('stopped talking')}[/]")
                elif sub_cmd == "test":
                    V.speak(val or "こんにちは、わたしはワグリです。よろしくお願いします。")
                    console.print(tr_('[{MUTED}]sending a test line…[/]', MUTED=MUTED))
                else:
                    for ln in V.status_lines():
                        console.print(f"[{MUTED}]{ln}[/]")
                    console.print(tr_('[{MUTED}]/voice on|off · mode say|full · lang ja|en|ms · profile <name> · test [text] · stop[/]', MUTED=MUTED))
            elif cmd in ("/borders", "/glow"):
                if arg in ("on", "off"):
                    console.print(tr_('[{MUTED}]{0} (saved)[/]', hooks.set_borders(arg == 'on'), MUTED=MUTED))
                else:
                    console.print(tr_('[{MUTED}]/borders on|off  (Alt+B toggles) - animated gradient borders; off saves CPU[/]', MUTED=MUTED))
            elif cmd == "/dev":
                console.print(tr_('[{MUTED}]  ⎿ development workflow: {0}[/]', arg or "…", MUTED=MUTED))
                run(skills.dev_message(arg), sub.images)
            elif cmd == "/skills":
                if arg == "reload":
                    skills.load(os.getcwd())
                    inputbox.EXTRA_COMMANDS.clear()
                    inputbox.EXTRA_COMMANDS.update(skills.extras())
                _show_skills(console)
            elif cmd == "/mcp":
                if arg == "reload":
                    mcp.start_all(os.getcwd())
                    time.sleep(1.5)
                _show_mcp(console)
            else:
                name = cmd[1:]
                msg = skills.expand_command(name, arg)
                kind = "command"
                if msg is None:
                    msg, kind = skills.skill_message(name, arg), "skill"
                if msg is not None:
                    console.print(tr_('[{MUTED}]  ⎿ {kind} /{name} loaded[/]', MUTED=MUTED, kind=kind, name=name))
                    run(msg, sub.images)
                else:
                    console.print(tr_('[{ERR}]unknown command:[/] {cmd}  [{MUTED}](/help)[/]', ERR=ERR, cmd=cmd, MUTED=MUTED))
            return None

        # ---------- ! shell langsung ----------
        if text.startswith("!") and len(text) > 1:
            cmd = text[1:].strip()
            try:
                out = tools.bash(cmd).split("\n", 1)[1].rstrip() or "(no output)"
            except KeyboardInterrupt:
                console.print(tr_('[{ERR}]stopped[/]', ERR=ERR))
                return None
            lines = out.splitlines()
            body = "\n".join(lines[:60]) + (tr_("\n… +{0} lines", len(lines) - 60) if len(lines) > 60 else "")
            console.print(Panel(body, title=f"[bold]$ {cmd[:80]}[/]", title_align="left",
                                border_style=MUTED, padding=(0, 1)))
            return None

        # ---------- # catatan ----------
        if text.startswith("# ") and len(text) > 2:
            f = context.append_note(os.getcwd(), text[2:])
            agent.memory_text, agent.memory_files = context.load_memory(os.getcwd())
            console.print(tr_('[{MUTED}]noted in {f}[/]', MUTED=MUTED, f=f))
            return None

        # ---------- normal message ----------
        ui.show_submission(console, sub)
        text, mentions = context.expand_mentions(text, os.getcwd(), agent.effort.tool_out_chars)
        for path, n in mentions:
            console.print(tr_('[{MUTED}]  ⎿ @{path} · {n} lines read[/]', MUTED=MUTED, path=path, n=n))
        run(text, sub.images)
        return None

    return Core(agent=agent, policy=policy, process=process, status=status, banner_info=banner_info,
                startup=startup, hint=hint, run=run)


# ======================================================================= mode klasik
class _ClassicHooks:
    def __init__(self):
        self.box = None

    def load_logo(self):
        self.box.load_logo()
        if not self.box.logo_error:
            self.box.show_banner = True
        return self.box.logo_error

    def clear(self):
        transcript.clear()

    def set_fps(self, n):
        return tr_('fps applies to the full-screen UI only')

    def set_still(self, still):
        return tr_('still/video applies to the full-screen UI only')

    def set_ascii(self, on):
        return tr_('still/video applies to the full-screen UI only')

    def set_sixel(self, on):
        return tr_('still/video applies to the full-screen UI only')

    def refresh_language(self):
        pass

    def set_mouse(self, on):
        return tr_("mouse settings apply to the full-screen UI only")

    def set_borders(self, on):
        return tr_('animated borders apply to the full-screen UI only')

    def history(self):
        _scrollback(Console())

    def show_banner(self):
        self.box.show_banner = True
        Console().print(tr_('[{MUTED}]the banner will show at the next prompt[/]', MUTED=MUTED))


def main_classic(argv: list[str]) -> None:
    if trust.needed(argv):
        from .gate import text_gate
        if not text_gate(os.getcwd()):
            sys.exit(1)
    console = Console()
    transcript.attach(console)       # display history for the scrollback viewer
    hooks = _ClassicHooks()
    core = make_core(console, argv, hooks)
    agent, policy = core.agent, core.policy

    screen = paths.env("SCREEN") or eff.load_settings().get("screen", "alt")
    if screen == "alt" and sys.stdout.isatty():
        import atexit
        _enter_alt()
        atexit.register(_leave_alt)      # whatever happens, the terminal is restored
    core.startup(console)

    box = InputBox(core.status, core.banner_info, on_cycle_mode=policy.cycle_mode)
    hooks.box = box
    box_ref.append(box)
    if box.logo_error:
        console.print(tr_('[{MUTED}]could not load the logo ({0}); using a static image/text[/]', box.logo_error, MUTED=MUTED))
    if not box.can_banner():     # terminal too small for the animated banner -> compact header
        print_banner(console, agent.model, tools.groups(), effort=agent.effort.name,
                     mode=tr_(MODE_LABEL[policy.mode]))

    def bye() -> None:
        _leave_alt()                     # the terminal is clean again; the emilie display is gone
        h = core.hint()
        if h:
            console.print(h)

    draft = ""                         # typing that was pending when the history (scroll) was opened
    while True:
        try:
            sub = box.ask(default=draft)
            draft = ""
        except (KeyboardInterrupt, EOFError):   # second Ctrl+C within the time window (InputBox) / Ctrl+D
            console.print()
            bye()
            return
        if sub.scroll:                     # mouse wheel up / PageUp -> history viewer
            _scrollback(console)
            draft = sub.draft
            continue
        transcript.add_line("❯ " + (sub.raw or sub.text).replace("\n", " ⏎ ")[:300], "\x1b[1;38;2;217;104;154m")
        if core.process(sub) == "exit":
            bye()
            return


# ======================================================================= print mode (emilie -p)
def _final_text(messages: list[dict]) -> str:
    """The text of the last assistant message (Anthropic blocks or OpenAI string)."""
    for m in reversed(messages):
        if m.get("role") != "assistant":
            continue
        c = m.get("content")
        if isinstance(c, str):
            if c.strip():
                return c
        elif isinstance(c, list):
            t = "".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
            if t.strip():
                return t
    return ""


def _print_prompt(argv: list[str]) -> str | None:
    """Prompt for `emilie -p "..."`: the text after -p/--print, plus anything piped on stdin."""
    i = next((k for k, a in enumerate(argv) if a in ("-p", "--print")), None)
    if i is None:
        return None
    text = argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith("-") else ""
    if not sys.stdin.isatty():
        piped = sys.stdin.read()
        text = (text + "\n\n" + piped).strip() if text else piped.strip()
    return text


def main_print(argv: list[str], prompt: str) -> int:
    """Non-interactive: run ONE turn, print only the final answer on stdout (progress goes to stderr).
    Nobody can answer a permission question, so anything that would ask is denied, unless --trust (or an /allow rule)
    covers it. Exit code: 0 ok, 1 error, 2 a tool call was denied and the task may be incomplete."""
    if trust.needed(argv):
        print(tr_("print mode cannot ask whether to trust this folder. Run emilie once here to trust it, or pass "
                  "--trust-folder."), file=sys.stderr)
        return 1
    console = Console(file=sys.stderr, force_terminal=False, highlight=False)
    denied: list[str] = []

    def no_prompt(_console, name, args, reason):
        denied.append(name)
        print(f"[print mode] denied {name}: nobody to ask. Use --trust or /allow rules to permit it.", file=sys.stderr)
        return "n"

    ui.ask_permission = no_prompt
    core = make_core(console, argv, _ClassicHooks())
    try:
        core.agent.run_turn(prompt, [])
    except KeyboardInterrupt:
        return 130
    except BaseException as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    out = _final_text(core.agent.messages)
    sys.stdout.write(out if out.endswith("\n") else out + "\n")
    return 2 if denied else 0


# ======================================================================= entri
def main() -> None:
    argv = sys.argv[1:]
    if os.name == "nt":
        if not sys.flags.utf8_mode:      # Windows defaults to cp1252 for files and pipes: run again in UTF-8 mode
            try:
                sys.exit(subprocess.call([sys.executable, "-X", "utf8", "-m", "emilie.cli", *argv]))
            except KeyboardInterrupt:
                sys.exit(130)
        from .term import enable_vt_output
        enable_vt_output()
    if "--untrust" in argv:                      # forget the "trust this folder" answer for the current folder
        print(tr_("folder no longer trusted: {0}", os.getcwd()) if trust.remove()
              else tr_("this folder was not in the trusted list: {0}", os.getcwd()))
        return
    if "--setup" in argv or (argv[:1] == ["setup"]):
        rest = [a for a in argv if a not in ("--setup", "setup")]
        from . import providers
        providers.setup(rest[0] if rest else None)
        return
    from . import providers
    if not providers.has_key() and "--banner" not in argv:
        if sys.stdin.isatty():
            print(tr_("Welcome to Emilie Agent! No API key yet, let's set one up (once)."))
            if not providers.setup():
                return
            if os.name == "nt":
                sys.exit(subprocess.call([sys.executable, "-m", "emilie.cli", *argv]))
            os.execv(sys.executable, [sys.executable, "-m", "emilie.cli", *argv])
        print(tr_('No API key. Run: emilie --setup'), file=sys.stderr)
        sys.exit(1)
    prompt = _print_prompt(argv)
    if prompt is not None:                       # emilie -p "question"  /  type file | emilie -p "summarise"
        if not prompt:
            print(tr_('Usage: emilie -p "your prompt"   (or pipe text in)  [--trust] [--plan] [--trust-folder]'),
                  file=sys.stderr)
            sys.exit(1)
        sys.exit(main_print(argv, prompt))
    if "--banner" in argv:
        console = Console()
        hooks = _ClassicHooks()
        core = make_core(console, argv, hooks)
        print_banner(console, core.agent.model, tools.groups(), effort=core.agent.effort.name,
                     mode=tr_(MODE_LABEL[core.policy.mode]))
        return
    mode = "classic" if "--classic" in argv else (paths.env("UI") or eff.load_settings().get("ui", "tui"))
    if mode == "tui" and sys.stdin.isatty() and sys.stdout.isatty():
        from .tui import run_tui
        run_tui(argv, make_core)
        return
    main_classic(argv)


if __name__ == "__main__":
    main()
