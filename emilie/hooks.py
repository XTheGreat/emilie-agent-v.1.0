"""Hooks: shell commands that run automatically around tool calls.

Configured ONLY in ~/.emilie/settings.json (never from a project folder, so a cloned repo cannot make Emilie run code):

  {"hooks": {
      "PreToolUse":  [{"matcher": "bash(git push*)", "command": "echo not now 1>&2 & exit 2"}],
      "PostToolUse": [{"matcher": "edit_file",       "command": "ruff check ."}]}}

matcher = a permission-style rule ("tool" or "tool(arg glob)", see policy.py); empty or "*" = every tool.
The hook receives JSON on stdin: {event, tool_name, tool_input, tool_output (post only), cwd}.
Exit 0 = fine. Exit 2 = PreToolUse: block the call and tell the model the stderr; PostToolUse: show the stderr to the
model as feedback. Any other non-zero exit is only a warning. Timeout 30 s.
"""
import json
import os
import subprocess

from . import effort
from .policy import Policy

TIMEOUT = 30


def _matching(event: str, name: str, args: dict) -> list[str]:
    cfg = effort.load_settings().get("hooks")
    items = cfg.get(event) if isinstance(cfg, dict) else None
    out = []
    for h in items if isinstance(items, list) else []:
        if not isinstance(h, dict) or not isinstance(h.get("command"), str):
            continue
        m = h.get("matcher") or "*"
        if m == "*" or Policy._rule_match(m, name, args):
            out.append(h["command"])
    return out


def _run(cmd: str, payload: dict, name: str) -> tuple[int, str, str]:
    env = dict(os.environ, EMILIE_TOOL=name, EMILIE_EVENT=payload["event"])
    try:
        r = subprocess.run(cmd, shell=True, input=json.dumps(payload, ensure_ascii=False), text=True, encoding="utf-8",
                           capture_output=True, timeout=TIMEOUT, env=env, cwd=os.getcwd())
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return 1, "", f"hook timed out after {TIMEOUT}s"
    except OSError as e:
        return 1, "", str(e)


def pre(name: str, args: dict) -> tuple[bool, str]:
    """(allowed, message). allowed=False when a hook exited 2: the message is what the model should be told."""
    for cmd in _matching("PreToolUse", name, args):
        code, out, err = _run(cmd, {"event": "PreToolUse", "tool_name": name, "tool_input": args,
                                     "cwd": os.getcwd()}, name)
        if code == 2:
            return False, err or out or "blocked by a hook"
    return True, ""


def post(name: str, args: dict, output: str) -> tuple[str, list[str]]:
    """(feedback for the model, warnings for the user). Feedback comes from hooks that exited 2."""
    feedback, warnings = [], []
    for cmd in _matching("PostToolUse", name, args):
        code, out, err = _run(cmd, {"event": "PostToolUse", "tool_name": name, "tool_input": args,
                                     "tool_output": output[:20000], "cwd": os.getcwd()}, name)
        if code == 2:
            feedback.append(err or out or "a hook asked for attention")
        elif code != 0:
            warnings.append(f"hook failed ({code}): {err or out or cmd}")
    return "\n".join(feedback), warnings
