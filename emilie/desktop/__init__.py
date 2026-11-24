"""Emilie desktop app: the same agent as the CLI, shown in a window that works like the Claude Code desktop app.

    hub.py      local HTTP server (127.0.0.1 only, token protected): serves the UI in web/, the JSON API and one
                event stream (server-sent events). Starts one worker process per open session.
    worker.py   one session in its own process and folder. Runs the CLI core (cli.make_core) unchanged; what it
                prints is turned into structured events (text deltas, tool calls, permission requests, ...).
    blocks.py   Rich renderables (panels, tables, markdown) -> simple JSON blocks the UI draws natively.
    convert.py  saved conversation messages -> transcript items (used when a session is opened again).
    schema.py   the settings page, described as data (new settings show up without UI changes).

The window itself lives in desktop/ at the repository root (Electron + React). `emilie app` starts everything.
See docs/DESKTOP.md.
"""

# ------------------------------------------------------------------ the / menu of the window
# Terminal-only commands are left out. Commands that open a screen in the window (desktop/ui/src/lib/slash.ts) say
# so; /usage exists only in the window.
TERMINAL_ONLY = {"/mouse", "/scroll", "/borders", "/history"}
DESKTOP_DESC = {
    "/help": "commands and keyboard shortcuts",
    "/model": "pick the model (/model <name> sets it)",
    "/effort": "pick the effort level (/effort low|medium|high|max)",
    "/mode": "pick the permission mode (ask, trust, plan)",
    "/context": "what fills the context (opens the Environment panel)",
    "/cost": "token usage of this session",
    "/usage": "token usage across all sessions (Settings → Usage)",
    "/config": "all settings (opens Settings)",
    "/permissions": "allow and deny rules (Settings → Privacy)",
    "/skills": "Agent Skills and custom commands (opens Customize)",
    "/mcp": "MCP servers and their tools (opens Connectors)",
    "/schedule": "scheduled tasks (opens Customize)",
    "/resume": "find and open an older session",
    "/todos": "show the task list of this session",
    "/memory": "open the project memory files (EMILIE.md)",
    "/rewind": "go back to before a turn that changed files",
}


def desktop_commands(commands: dict, tr=lambda s: s) -> list[dict]:
    """The built-in commands for the window's / menu: [{name, desc, kind}]."""
    out = [{"name": c, "desc": DESKTOP_DESC.get(c) or tr(d), "kind": "builtin"}
           for c, d in commands.items() if c not in TERMINAL_ONLY]
    after_cost = next((i + 1 for i, x in enumerate(out) if x["name"] == "/cost"), len(out))
    out.insert(after_cost, {"name": "/usage", "desc": DESKTOP_DESC["/usage"], "kind": "builtin"})
    return out
