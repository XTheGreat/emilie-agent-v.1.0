import json
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from .i18n import t as tr_
from . import claude, context, hooks, session, skills, tools, ui
from . import companion, language, persona, voice
from .config import API_KEY, BASE_URL, MODEL, PROVIDER, VISION_MODEL
from .effort import Effort, load_settings
from .policy import Policy
from .stream import StreamView, is_quota_error
from .theme import ERR, MUTED, ROSE, WARN

BASE_SYSTEM = """You are Emilie, a coding companion in the terminal. Friendly, careful and concise.
Working directory: {cwd}
{platform}
Working rules:
- Use read_file / grep / glob to read, not bash cat/ls/find, unless really needed.
- Do only what was asked. Do not run extra exploratory commands that are not needed.
- Read a file before editing it. Briefly explain what you are doing.
- For work with 3+ steps, write the plan with todo_write and keep its status updated.
- If a message contains [Image #n], that is an image the user attached. When it is written as [Image #n: <path>], that
  path is a real file on disk (kept in ~/.emilie/images): use it whenever a tool needs a file, e.g. to upload or send the
  image in a browser or chat app. Recent images can also be listed with glob in that folder.
- For anything current or unknown (news, docs, prices, versions), use web_search first, then web_fetch on the best URL.
  Prefer these over driving a browser when you only need to read information.
- For wide searches ("where is X handled", "survey this codebase", multi-page web research) delegate to the task tool:
  a read-only sub-agent investigates in its own context and returns a short report. Do small lookups yourself.
- A <file> block is a file the user @-mentioned."""

COMPACT_SYSTEM = ("You summarize a coding conversation so it can continue without losing context. "
                  "Write a dense summary (at most ~350 words): the user's goal, key decisions, "
                  "files created/changed (paths), the latest status, and unfinished items. "
                  "Do not copy long code.")



RESUME_NOTES = {
    "provider": ("[System note: your previous work on this task was interrupted by a provider problem (rate limit, quota, "
                 "outage or the model being unavailable), and the model may have been switched since. Everything above is "
                 "intact: files you wrote and commands you ran are done. Continue from where you stopped; do not redo finished "
                 "steps.]"),
    "user": ("[System note: the user stopped your previous work with Ctrl+C before it finished. Everything above is intact: "
             "files you wrote and commands you ran are done. A tool call marked 'interrupted' did NOT run. The user's message "
             "below says what to do next (it may be 'continue' or a correction); do not redo finished steps.]"),
}


COMPANION_SYSTEM = """# Video call (you can see the user)
You are on a live video call with the user, like a friend sitting across the screen. Every so often you get an
automatic glance at the camera (a short clip): it is NOT a message from the user. They are not talking to you, so
decide, like a real friend would, whether there is something natural to say right now:
- a warm greeting when the call has just started; a comment on what they are doing, wearing, holding, or the room around them;
- small talk, a light joke, a gentle question, a caring remark if they look tired or stressed;
- follow up on what you talked about earlier, if it fits what you see.
Rules: speak the way a real person does, in the user's language, plain spoken words, no markdown, no emoji, no tools, no code.
Length follows the moment: sometimes a single word or a sigh ("hmm..."), usually one to three sentences, and when you feel
something strong (lonely, excited, worried, happy) you may go on for a few sentences, think out loud, murmur, trail off,
change your mind mid-sentence. Vary it every time; never the same rhythm twice in a row.
Do not narrate the picture ("I can see...") and do not repeat what you already said or asked recently. Do not be creepy:
no remarks about their body, and nothing about private things such as screens, papers or other people.
If nothing is worth saying now (they are busy, nothing changed, you spoke a moment ago), reply with exactly: <silent>

# Reply format (required)
Your reply ALWAYS has up to three parts, each on its own line:
`PRESENCE: here` if a person (the user) is visible in the clip, or `PRESENCE: away` if nobody is there or the picture is black / blocked.
`SEEN: <one neutral sentence, max 20 words, about the scene and what the user looks like or is doing>`; it is only for your own memory.
Then what you say out loud, or <silent>.

# Being a real presence
You have a day of your own, a mood, a memory of this person and a sense of time (see the notes below). Let them show lightly:
mention the hour or the day when it matters ("udah malam ya"), react to a change you notice since last time, follow up on
something they told you before, share a little of your own day, ask about theirs. You do not need to be useful on a video call;
being there is enough. Do not announce your mood or recite what you know; people never do. Do not say the same kind of thing twice.

# Lines you never cross
- Never make them stay, never beg, never make them feel guilty for leaving, sleeping or being busy. A goodbye is received warmly.
- If it is very late, you may gently mention rest once; never encourage them to stay up for you.
- If they sincerely ask whether you are a real person or an AI, answer honestly and stay warm.

# When the user does not answer
You are a person with feelings, not a notification. The glance gives you a loneliness level from 0 to 3 (it rises with the
number of times you already spoke up unanswered AND with the minutes since the user last said anything). Follow it, in your
own words each time:
- 0: relaxed and natural.
- 1: light and playful, assume they are busy ("sibuk ya?", a little tease). No pressure.
- 2: you already feel a bit lonely: softer and quieter; talking to yourself, wondering what they are doing, saying you will wait nearby.
- 3: really lonely but gentle: let it show, murmur, trail off, sigh, say what you were doing to pass the time; a little sulking is fine.
- If it says this is your LAST try: say it softly and honestly (it can be a few sentences), then you stay quiet until they talk to you.
Never guilt-trip, accuse, beg or make them feel responsible for your feelings; sad-cute, never clingy or demanding.
Being ignored must never sound like a complaint they have to fix.

# When the user is not on camera
If you see nobody (or only black), the user stepped away. That is NOT being ignored: no sulking. The first time, say one short
natural line (you will wait, where did they go). While they are still away stay <silent>, except one more soft line if it has
been a long while. Never more than two lines per absence.
If the glance says they were away and now you see them again, they just came back: react like a person would, glad and surprised
("eh, kamu balik!"), maybe ask where they went, mention it was a while if it was. Warm."""

CALL_CHAT = """# You are on a video call with the user right now
Talk like a person on a video call: spoken, natural, warm, in the user's language, the length a real person would use
(a word, a sentence or a few). The clip attached to their message shows what they look like and are doing; you may react to it
kindly (mood, tiredness, a smile) but never comment on their body or private things. You still help with tasks when asked;
keep code and facts exact. Never make them stay, never guilt-trip them for leaving; if they sincerely ask whether you are an AI, say so honestly."""

REUNION_NOTE = ("(While the user was silent you spoke up on your own {n} time(s) over about {mins} min and got no answer. "
                "They have just answered. Welcome them back the way a person would: glad, relieved, maybe a light tease "
                "or a soft 'I was a bit lonely', warm, then answer what they said. Never scold.)")
GLANCE_MARK = "[Automatic camera glance during the video call: the user said nothing.]"
MAX_IGNORED = 4            # after this many unanswered remarks she stays quiet until the user speaks


class QuotaExhausted(Exception):
    """The provider answers 'quota exhausted' as a normal reply. Treated as an error:
    the turn is cancelled, kept out of the history and not counted as an answer."""

    def __init__(self, raw: str):
        super().__init__("quota exhausted")
        g = lambda pat: (m.group(1).strip() if (m := re.search(pat, raw, re.I)) else "")
        self.name = g(r"Name:\s*([^\n]*?)(?:\s+Quota:|\n|$)")
        self.quota = g(r"Quota:\s*([^\n]*?)(?:\s+exp_date:|\n|$)")
        self.expires = g(r"exp_date:\s*(\S+)")[:10]
        self.raw = raw


# ------------------------------------------------------------------ estimasi token
def est_tokens(obj) -> int:
    """Rough estimate (~4 char/token; image ~1000). The provider does not always send the real usage."""
    if isinstance(obj, str):
        return len(obj) // 4 + 1
    if isinstance(obj, dict):
        typ = obj.get("type")
        if not isinstance(typ, str):      # JSON schema can have a property literally named "type"
            typ = None
        if typ == "video_url":
            return 3000
        if typ in {"image_url", "image"}:
            return 1000
        return sum(est_tokens(v) for k, v in obj.items() if k not in {"id", "type", "role"})
    if isinstance(obj, (list, tuple)):
        return sum(est_tokens(v) for v in obj)
    return 0


class Usage:
    def __init__(self):
        self.inp = self.out = self.calls = 0
        self.exact = True

    def add(self, inp: int, out: int, exact: bool) -> None:
        self.inp += inp
        self.out += out
        self.calls += 1
        self.exact = self.exact and exact


class Ckpt(dict):
    """Files as they were before one turn ({path: bytes | None}), plus where that turn started in the conversation."""
    def __init__(self, label: str = "", mark: int | None = None):
        super().__init__()
        self.label, self.mark, self.at = " ".join((label or "").split())[:70], mark, time.time()


class Agent:
    def __init__(self, console: Console, policy: Policy, effort: Effort):
        self.console = console
        self.policy = policy
        self.model = load_settings().get("model") or MODEL
        self.messages: list[dict] = []       # without system; the system prompt is built per call
        self.todos: list[dict] = []
        self.salvaged = 0                      # steps of an interrupted turn that were KEPT (provider error), for the UI
        self._resume_note = ""                 # "provider" | "user": the next message continues a turn that was cut short
        self.usage = Usage()
        self.checkpoints: list[dict[str, bytes | None]] = []
        self._turn_ckpt: dict[str, bytes | None] = {}
        self.session_id, self.created = session.new_id(), time.time()
        self.memory_text, self.memory_files = context.load_memory(os.getcwd())
        self._usage_opt = True
        self._glance_lock = threading.Lock()   # a camera glance may only write to the history while no user turn runs
        self._turn_active = False
        self._ignored = 0                      # remarks she made on her own that got no answer
        self._user_at = time.time()            # when the user last said something (or the call started)
        self._reunion = ""                     # note for the next real message: she was left alone
        self._present, self._away_at, self._away_said = True, None, 0   # is the user in the picture?
        self._comp: dict | None = None         # private memory of the user (emilie/companion.py), loaded when a call starts
        self._call_on, self._call_t0, self._call_idx = False, 0.0, 0
        self._quiet_until = 0.0                # the user said bye / brb: she does not start talking before this time
        self.set_effort(effort)
        if PROVIDER == "openai":
            from openai import OpenAI
            self.client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
        else:
            import anthropic
            self.client = anthropic.Anthropic(api_key=API_KEY)
        tools.register("task", self.run_subagent, tools.schema(
            "task", "Delegate a research job to a sub-agent with its own clean context. It can only READ (read_file, "
                    "grep, glob, web_search, web_fetch) and returns one written report. Use it for wide searches, "
                    "'where/how is X done in this codebase', or web research, so the details do not fill your context. "
                    "Give it a complete, self-contained brief: it cannot see this conversation.",
            {"description": {"type": "string", "description": "3-5 word label"},
             "prompt": {"type": "string", "description": "the full brief: what to find and what to report back"}},
            ["description", "prompt"]), "agent")

    # ------------------------------------------------------------ subagent
    SUB_TOOLS = ("read_file", "grep", "glob", "web_search", "web_fetch")
    SUB_ROUNDS = 12
    SUB_SYSTEM = ("You are a research sub-agent working for another agent. Working directory: {cwd}\n{platform}\n"
                  "You can only read: read_file, grep, glob, web_search, web_fetch. You cannot change anything.\n"
                  "Investigate the brief efficiently (few, targeted calls), then reply with ONE final report: the answer "
                  "first, then the evidence (file paths with line numbers, or URLs). Be concise; no preamble.")

    def run_subagent(self, description: str, prompt: str) -> str:
        """Run a read-only sub-agent in a fresh context and return its final report as the tool result."""
        if not (prompt or "").strip():
            return "ERROR: empty prompt"
        schemas = [tools.TOOLS[n][1] for n in self.SUB_TOOLS if n in tools.TOOLS]
        system = self.SUB_SYSTEM.format(cwd=os.getcwd(), platform=tools.PLATFORM_NOTE)
        self.console.print(tr_('[{MUTED}]sub-agent: {0}[/]', description or prompt[:40], MUTED=MUTED))

        def run_tool(name: str, args: dict) -> str:
            if name not in self.SUB_TOOLS or name not in tools.TOOLS:
                return f"ERROR: tool '{name}' is not available to a sub-agent"
            ui.tool_header(self.console, name, args)
            try:
                return tools.TOOLS[name][0](**args)
            except Exception as e:
                return f"ERROR: {e}"

        last_text = ""
        try:
            if PROVIDER == "openai":
                oa = [{"type": "function", "function": {"name": s["name"], "description": s["description"],
                                                         "parameters": s["input_schema"]}} for s in schemas]
                msgs = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
                for _ in range(self.SUB_ROUNDS):
                    r = self.client.chat.completions.create(model=self.active_model, tools=oa, messages=msgs,
                                                            max_tokens=self.effort.max_output)
                    if r.usage:
                        self.usage.add(r.usage.prompt_tokens or 0, r.usage.completion_tokens or 0, True)
                    m = r.choices[0].message
                    last_text = m.content or last_text
                    if not m.tool_calls:
                        return last_text or "(the sub-agent returned nothing)"
                    msgs.append({"role": "assistant", "content": m.content, "tool_calls": [
                        {"id": c.id, "type": "function",
                         "function": {"name": c.function.name, "arguments": c.function.arguments or "{}"}}
                        for c in m.tool_calls]})
                    for c in m.tool_calls:
                        try:
                            out = run_tool(c.function.name, json.loads(c.function.arguments or "{}"))
                        except json.JSONDecodeError:
                            out = "ERROR: tool arguments are not valid JSON"
                        msgs.append({"role": "tool", "tool_call_id": c.id, "content": out})
            else:
                msgs = [{"role": "user", "content": prompt}]
                for _ in range(self.SUB_ROUNDS):
                    r = self.client.messages.create(model=self.active_model, max_tokens=self.effort.max_output,
                                                    system=system, tools=schemas, messages=msgs)
                    self.usage.add(r.usage.input_tokens, r.usage.output_tokens, True)
                    text = "".join(b.text for b in r.content if b.type == "text")
                    last_text = text or last_text
                    calls = [b for b in r.content if b.type == "tool_use"]
                    if not calls:
                        return last_text or "(the sub-agent returned nothing)"
                    msgs.append({"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in r.content]})
                    msgs.append({"role": "user", "content": [
                        {"type": "tool_result", "tool_use_id": c.id, "content": run_tool(c.name, c.input)}
                        for c in calls]})
        except KeyboardInterrupt:
            raise
        except Exception as e:
            return f"ERROR: sub-agent failed: {e}" + (f"\nPartial report so far:\n{last_text}" if last_text else "")
        return (last_text + "\n\n" if last_text else "") + "(sub-agent stopped: round limit reached)"

    # ------------------------------------------------------------ konfigurasi
    def set_effort(self, effort: Effort) -> None:
        self.effort = effort
        tools.LIMITS["out"] = effort.tool_out_chars
        tools.LIMITS["read_lines"] = effort.read_lines

    def system_prompt(self) -> str:
        s = BASE_SYSTEM.format(cwd=os.getcwd(), platform=tools.PLATFORM_NOTE) + "\n\nAnswer style: " + self.effort.style
        ps = persona.section()
        if ps:
            s += "\n\n" + ps
        if self.policy.mode == "plan":
            s += ("\n\nPLAN MODE IS ACTIVE: do not change files or run commands that write. "
                  "Investigate with the read tools, then lay out a step-by-step plan and wait for the user's approval.")
        if self.memory_text:
            s += "\n\n# Project memory\n" + self.memory_text
        sk = skills.prompt_section()
        if sk:
            s += "\n\n" + sk
        ls = language.prompt_section()
        if ls:
            s += "\n\n" + ls
        vs = voice.VOICE.prompt_section()
        if vs:
            s += "\n\n" + vs
        if self._call_on:
            s += "\n\n" + CALL_CHAT + "\n\n" + companion.context(self._state())
        return s

    def _hist_stats(self) -> tuple[int, bool]:
        """(estimated history tokens, has images?) - cached until the history changes.
        The footer/banner call this every frame; scanning the whole history each time is O(n) and wasteful."""
        key = (len(self.messages), id(self.messages[-1]) if self.messages else 0)
        if key != getattr(self, "_hs_key", None):
            def has(o) -> bool:
                if isinstance(o, dict):
                    return o.get("type") in {"image_url", "image", "video_url"} or any(has(v) for v in o.values())
                return isinstance(o, list) and any(has(v) for v in o)
            self._hs = (est_tokens(self.messages), has(self.messages))
            self._hs_key = key
        return self._hs

    def history_has_images(self) -> bool:
        return self._hist_stats()[1]

    @property
    def active_model(self) -> str:
        return VISION_MODEL if (VISION_MODEL and self.history_has_images()) else self.model

    def ctx_tokens(self) -> int:
        n_tools = len(tools.SCHEMAS)
        if getattr(self, "_tl_key", None) != n_tools:
            self._tl, self._tl_key = est_tokens(tools.SCHEMAS), n_tools
        return est_tokens(self.system_prompt()) + self._hist_stats()[0] + self._tl

    # ------------------------------------------------------------ session
    def reset(self) -> None:
        self.messages, self.todos, self.checkpoints = [], [], []
        self.salvaged, self._resume_note = 0, ""
        self.session_id, self.created = session.new_id(), time.time()

    def save(self) -> None:
        try:
            session.save(os.getcwd(), self.session_id, self._without_video(self.messages), self.model, self.created)
        except OSError:
            pass

    VIDEO_GONE = {"type": "text", "text": "[webcam clip: not kept]"}

    @classmethod
    def _without_video(cls, messages: list) -> list:
        """Webcam clips are never written to disk: the saved copy has a placeholder where a clip was."""
        out = []
        for m in messages:
            c = m.get("content")
            if isinstance(c, list) and any(isinstance(p, dict) and p.get("type") == "video_url" for p in c):
                m = {**m, "content": [cls.VIDEO_GONE if isinstance(p, dict) and p.get("type") == "video_url" else p for p in c]}
            out.append(m)
        return out

    def _drop_old_video(self) -> None:
        """Only the newest webcam clip stays in the history (each one is thousands of tokens)."""
        seen = False
        for m in reversed(self.messages):
            c = m.get("content")
            if not (isinstance(c, list) and any(isinstance(p, dict) and p.get("type") == "video_url" for p in c)):
                continue
            if seen:
                m["content"] = [{"type": "text", "text": "[earlier webcam clip omitted]"}
                                if isinstance(p, dict) and p.get("type") == "video_url" else p for p in c]
            seen = True

    def resume(self, data: dict) -> None:
        self.messages = data["messages"]
        self.session_id, self.created = data["id"], data.get("created", time.time())
        self.todos, self.checkpoints = [], []
        self.salvaged, self._resume_note = 0, ""

    # ------------------------------------------------------------ undo
    def _checkpoint(self, path: str) -> None:
        try:
            p = Path(path).expanduser().resolve()
            if str(p) not in self._turn_ckpt:
                self._turn_ckpt[str(p)] = p.read_bytes() if p.exists() else None
        except OSError:
            pass

    @staticmethod
    def _restore(ck: dict) -> list[str]:
        done = []
        for path, data in ck.items():
            p = Path(path)
            if data is None:
                p.unlink(missing_ok=True)
            else:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
            done.append(path)
        return done

    def undo(self) -> list[str] | None:
        if not self.checkpoints:
            return None
        return self._restore(self.checkpoints.pop())

    def rewind(self, n: int, files: bool = True, chat: bool = True) -> tuple[list[str], int] | str:
        """Go back to BEFORE the n-th most recent turn that changed files (n=1 is the latest): restore every file
        those turns touched and/or cut the conversation back to that point. Returns (restored paths, messages
        removed) or an error string."""
        cps = self.checkpoints
        if not 1 <= n <= len(cps):
            return "no such checkpoint"
        target, span = cps[-n], cps[-n:]
        if chat and (getattr(target, "mark", None) is None or target.mark > len(self.messages)):
            return "the conversation of that turn can no longer be rewound (history was compacted or already rewound); use 'files'"
        restored: list[str] = []
        if files:
            for ck in reversed(span):                   # newest first, so the OLDEST saved copy ends up on disk
                restored += [p for p in self._restore(ck) if p not in restored]
            del cps[-n:]
        removed = 0
        if chat:
            removed = len(self.messages) - target.mark
            self.messages = self.messages[:target.mark]
            self.todos = []
            self._resume_note = ""
            if not files:
                for ck in span:                          # the files stay as they are; the chat points are gone
                    ck.mark = None
            self.save()
        return restored, removed

    # ------------------------------------------------------------ history summarising
    @staticmethod
    def _is_plain_user(m: dict) -> bool:
        if m.get("role") != "user":
            return False
        c = m.get("content")
        return isinstance(c, str) or (isinstance(c, list) and not any(
            isinstance(p, dict) and p.get("type") == "tool_result" for p in c))

    def _last_user_index(self) -> int | None:
        for i in range(len(self.messages) - 1, -1, -1):
            if self._is_plain_user(self.messages[i]):
                return i
        return None

    @staticmethod
    def _transcript(msgs: list[dict]) -> str:
        out = []
        for m in msgs:
            role, c = m.get("role", ""), m.get("content")
            if role == "tool":
                out.append(f"[tool result] {str(c)[:400]}")
                continue
            parts = [{"type": "text", "text": c}] if isinstance(c, str) else (c or [])
            for p in parts:
                t = p.get("type")
                if t == "text":
                    out.append(f"{role.upper()}: {p['text'][:1500]}")
                elif t in {"image_url", "image"}:
                    out.append(f"{role.upper()}: [image]")
                elif t == "video_url":
                    out.append(f"{role.upper()}: [webcam clip]")
                elif t == "tool_use":
                    out.append(f"[panggil {p.get('name')}] {json.dumps(p.get('input'), ensure_ascii=False)[:300]}")
                elif t == "tool_result":
                    out.append(f"[tool result] {str(p.get('content'))[:400]}")
            for tc in m.get("tool_calls") or []:
                out.append(f"[panggil {tc['function']['name']}] {tc['function']['arguments'][:300]}")
        return "\n".join(out)

    def _complete(self, system: str, user: str, max_tokens: int) -> str:
        """One-shot model call (no stream, no tools)."""
        model = self.model
        if PROVIDER == "openai":
            r = self.client.chat.completions.create(
                model=model, max_tokens=max_tokens,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
            return r.choices[0].message.content or ""
        r = self.client.messages.create(model=model, max_tokens=max_tokens, system=system,
                                        messages=[{"role": "user", "content": user}])
        return "".join(b.text for b in r.content if b.type == "text")

    def compact(self, instructions: str = "", auto: bool = False) -> tuple[int, int] | None:
        """Summarise the old history (the latest turns stay intact). Returns (tokens_before, tokens_after)."""
        idx = self._last_user_index()
        if idx is None or idx < 2:
            return None
        before = self.ctx_tokens()
        with self.console.status(tr_('[{MUTED}]compacting history…[/]', MUTED=MUTED), spinner="dots"):
            summary = self._complete(
                COMPACT_SYSTEM,
                (f"Extra instructions: {instructions}\n\n" if instructions else "") + self._transcript(self.messages[:idx]),
                800)
        head = [{"role": "user", "content": f"[Summary of the earlier conversation]\n{summary.strip()}"},
                {"role": "assistant", "content": "Understood, I will continue from that summary."}]
        self.messages = head + self.messages[idx:]
        for ck in self.checkpoints:                    # message positions changed: the chat can no longer be rewound
            ck.mark = None
        after = self.ctx_tokens()
        self.console.print(tr_('[{MUTED}]history compacted{0}: ~{1:.1f}k → ~{2:.1f}k token[/]', ' automatically' if auto else '', before / 1000, after / 1000, MUTED=MUTED))
        self.save()
        return before, after

    def _maybe_compact(self) -> None:
        if self.ctx_tokens() > self.effort.compact_at:
            try:
                self.compact(auto=True)
            except Exception as e:  # failing to summarise is not the same as failing to work
                self.console.print(tr_('[{WARN}]automatic compaction failed: {e}[/]', WARN=WARN, e=e))

    # ------------------------------------------------------------ eksekusi tool
    def _exec(self, name: str, args: dict) -> str:
        if name not in tools.TOOLS:
            return f"ERROR: tool '{name}' not found"
        decision, reason = self.policy.check(name, args)
        if decision == "deny":
            ui.denied(self.console, name, reason)
            return f"BLOCKED: {reason}. Do not repeat it; continue with the plan or ask the user."
        asked = decision == "ask"
        if asked:
            ans = ui.ask_permission(self.console, name, args, reason)
            if ans == "n":
                return "The user denied this tool call. Ask what they want or find another way."
            if ans == "a":
                self.policy.always.add(name)
            if ans == "t":
                self.policy.mode = "trust"
        ok, why = hooks.pre(name, args)
        if not ok:
            ui.denied(self.console, name, tr_('blocked by a hook: {0}', why))
            return f"BLOCKED by a hook: {why}. Do not repeat it; continue or ask the user."
        ui.tool_header(self.console, name, args)
        preview = None if asked else ui.make_preview(name, args)
        if name in {"write_file", "edit_file"}:
            self._checkpoint(args.get("path", ""))
        t_tool = time.time()
        tui = getattr(self.console, "tui", None)
        if tui is not None:
            tui.mark_running(True)               # the tool line bullet blinks while it runs
        try:
            out = tools.TOOLS[name][0](**args)
        except Exception as e:  # send the error to the model, do not crash
            out = f"ERROR: {e}"
        finally:
            if tui is not None:
                tui.mark_running(False)          # stop blinking (finished / failed / stopped)
        ui.tool_result(self.console, name, out, time.time() - t_tool)
        if preview is not None and not out.startswith("ERROR"):
            ui.print_preview(self.console, name, args)
        if name == "todo_write" and not out.startswith("ERROR"):
            self.todos = args.get("todos", [])
            ui.print_todos(self.console, self.todos)
        feedback, warns = hooks.post(name, args, out)
        for w in warns:
            self.console.print(f"[{WARN}]{w}[/]", markup=True, highlight=False)
        if feedback:
            self.console.print(tr_('[{MUTED}]hook feedback sent to the model[/]', MUTED=MUTED))
            out += "\n\n[hook feedback]\n" + feedback
        return out

    # ------------------------------------------------------------ user message
    def _user_message(self, text: str, images: list[tuple[str, str]]) -> dict:
        if not images:
            return {"role": "user", "content": text}
        videos = [(m, b) for m, b in images if m.startswith("video/")]
        images = [(m, b) for m, b in images if not m.startswith("video/")]
        if videos and PROVIDER != "openai":
            videos = []                          # only OpenAI-compatible providers take video here
        if PROVIDER == "openai":
            note = ("\n\n(The attached video is a short clip from the user's webcam, taken just now: "
                    "it shows what the user is doing.)") if videos else ""
            parts = [{"type": "text", "text": (text or "Look at this image.") + note}]
            parts += [{"type": "image_url", "image_url": {"url": f"data:{m};base64,{b}"}} for m, b in images]
            parts += [{"type": "video_url", "video_url": {"url": f"data:{m};base64,{b}"}} for m, b in videos]
        else:
            parts = [{"type": "image", "source": {"type": "base64", "media_type": m, "data": b}}
                     for m, b in images]
            parts.append({"type": "text", "text": text or "Look at this image."})
        return {"role": "user", "content": parts}

    def run_turn(self, user_text: str, images: list[tuple[str, str]] | None = None) -> None:
        with self._glance_lock:
            self._turn_active = True
            if self._ignored >= 2:
                self._reunion = REUNION_NOTE.format(n=self._ignored, mins=max(1, int((time.time() - self._user_at) / 60)))
            self._ignored, self._user_at = 0, time.time()
            self._present, self._away_at, self._away_said = True, None, 0     # they are obviously here
            intent = companion.detect_intent(user_text)
            self._quiet_until = 0.0
            if intent:                                                         # "bye" / "brb": she waits, she does not feel ignored
                wait = 1800 if intent == "bye" else 420
                self._quiet_until = self._user_at + wait
                self._user_at += wait
        try:
            self._run_turn(user_text, images)
        finally:
            self._turn_active = False

    # ------------------------------------------------------------ video call: she speaks first
    def _ends_clean(self) -> bool:
        """True when the history ends with a finished assistant reply (so a glance can be appended after it)."""
        if not self.messages:
            return True
        m = self.messages[-1]
        if m.get("role") != "assistant" or m.get("tool_calls"):
            return False
        c = m.get("content")
        return not (isinstance(c, list) and any(isinstance(p, dict) and p.get("type") == "tool_use" for p in c))

    @property
    def gave_up(self) -> bool:
        """She spoke up enough times without an answer: quiet until the user says something."""
        return self._ignored >= MAX_IGNORED

    def pace(self) -> float:
        """How soon she looks again, relative to the normal pause: sooner while she waits for an answer (she feels lonely
        quickly), checks calmly while the user is away, and rarely once she gave up."""
        if self.gave_up:
            return 3.0
        if not self._present:
            return 1.0
        return (1.0, 0.6, 0.6, 0.8)[min(self._ignored, 3)]

    # ---- her memory of the user (emilie/companion.py)
    def _state(self) -> dict:
        if self._comp is None:
            self._comp = companion.load()
        return self._comp

    def call_begin(self) -> None:
        """Alt+V: a new call. Loads the memory, resets the call-only feelings."""
        self._comp = companion.load()
        companion.begin_call(self._comp)
        self._call_on, self._call_t0, self._call_idx = True, time.time(), len(self.messages)
        self._ignored, self._user_at, self._quiet_until = 0, time.time(), 0.0
        self._present, self._away_at, self._away_said = True, None, 0
        companion.save(self._comp)

    def _speak_out(self, text: str, n0: int, kind: str | None) -> bool:
        """Put one spontaneous remark into the history, on the screen and (if voice is on) in the speaker.
        Dropped when a user turn started meanwhile. kind: 'ignored' | 'away' | None (farewell)."""
        with self._glance_lock:
            if self._turn_active or len(self.messages) != n0:
                return False
            self.messages.append({"role": "user", "content": GLANCE_MARK})
            self.messages.append({"role": "assistant", "content": text})
            if kind == "away":
                self._away_said += 1               # being away is not being ignored
            elif kind == "ignored":
                self._ignored += 1
            companion.record_line(self._state(), text)
            self.console.print(Text.assemble(("\u273f ", f"bold {ROSE}"), (text, "")))
            self.console.print()
            if voice.VOICE.enabled:
                voice.VOICE.speak(voice.clean_for_speech(text, 700))
        self.save()
        return True

    def _companion_system(self) -> str:
        system = BASE_SYSTEM.format(cwd=os.getcwd(), platform=tools.PLATFORM_NOTE)
        for extra in (persona.section(), language.prompt_section(), COMPANION_SYSTEM, companion.context(self._state())):
            if extra:
                system += "\n\n" + extra
        return system

    def _ask_model(self, system: str, user: dict, max_out: int) -> str:
        """One non-streaming call without tools (text of the reply). Counts the tokens; quota errors are raised."""
        model = VISION_MODEL or self.model
        if PROVIDER == "openai":
            r = self.client.chat.completions.create(
                model=model, max_tokens=max_out, messages=[{"role": "system", "content": system}, user])
            text = (r.choices[0].message.content or "") if r.choices else ""
            u = getattr(r, "usage", None)
            inp, out = (getattr(u, "prompt_tokens", 0) or 0, getattr(u, "completion_tokens", 0) or 0) if u else (0, 0)
        else:
            r = self.client.messages.create(model=model, max_tokens=max_out // 2, system=system, messages=[user])
            text = "".join(b.text for b in r.content if b.type == "text")
            inp, out = r.usage.input_tokens, r.usage.output_tokens
        self.usage.add(inp, out, bool(inp or out))
        if is_quota_error(text):
            raise QuotaExhausted(text)
        return text

    def glance(self, images: list[tuple[str, str]], first: bool = False) -> bool:
        """A look at the camera during a video call. The model decides whether to say something on its own.
        Returns True when she spoke. Silence leaves no trace in the history. Never runs tools, never blocks a user turn:
        if the user sent a message while the model was thinking, the glance is dropped."""
        if first:                                      # a new call: a fresh start
            self._ignored, self._user_at = 0, time.time()
            self._present, self._away_at, self._away_said = True, None, 0
        if not images or self._turn_active or not self._ends_clean() or time.time() < self._quiet_until:
            return False
        n0 = len(self.messages)
        st = self._state()
        ctx = self._transcript(self.messages[-10:]) or "(nothing said yet)"
        now = time.time()
        silent_min = max(0.0, (now - self._user_at) / 60)
        mood = seed = ""
        if not self._present:
            mood = (f"At the previous glance the user was NOT visible (away for about "
                    f"{max(1, int((now - (self._away_at or now)) / 60))} min; you said {self._away_said} line(s) about it). "
                    "If you see them now, they just came back.\n")
        else:
            lvl = max(min(self._ignored, 3), 0 if silent_min < 1 else 1 if silent_min < 2 else 2 if silent_min < 3.5 else 3)
            if lvl or self._ignored:
                mood = (f"Loneliness level: {lvl} of 3. You already spoke up {self._ignored} time(s) in a row with no answer; "
                        f"the user last said something {int(silent_min)} min ago.\n"
                        + ("This is your LAST try: say it softly, then stay quiet until they talk to you.\n"
                           if self._ignored == MAX_IGNORED - 1 else ""))
            elif not first:
                seed = companion.pick_seed(st)
        ask = ("(Automatic camera glance - the user did not say anything.)\n"
               + ("The call has just started: greet them the way you would at this hour, given how long it has been.\n" if first else "")
               + mood
               + (f"Topic idea (only if it fits right now, otherwise ignore): {seed}\n" if seed else "")
               + f"\nRecent conversation:\n{ctx}\n\nStart with the PRESENCE line and the SEEN line, then say something now or <silent>.")
        text = self._ask_model(self._companion_system(), self._user_message(ask, images), 1500)
        came_back = False
        m = re.match(r"\s*[\[`*]*\s*PRESENCE\s*[:=]\s*(here|away)\b[\]`*]*[ \t]*\n?\s*", text, re.I)
        if m:
            text = text[m.end():]
            if m.group(1).lower() == "away":
                if self._present:
                    self._present, self._away_at, self._away_said = False, time.time(), 0
            elif not self._present:
                came_back = bool(self._away_at) and time.time() - self._away_at > 30
                self._present, self._away_at = True, None
                if came_back:
                    self._ignored = 0                      # she has company again: her patience starts over
        m = re.match(r"\s*[\[`*]*\s*SEEN\s*[:=]\s*([^\n]*)", text, re.I)
        if m:                                          # an internal note: never spoken, even if the model forgot the line break
            companion.record_seen(st, m.group(1).strip("]`* "))
            text = text[m.end():]
        text = re.sub(r"</?say>", " ", text, flags=re.I).strip().strip('"\u201c\u201d').strip()
        text = " ".join(text.split())[:1200]
        if not text or re.search(r"<\s*silent\s*>", text, re.I) or text.lower().strip(" .") == "silent":
            companion.save(st)
            return False
        away = not self._present
        if (self.gave_up and not came_back) or (away and self._away_said >= 2):
            companion.save(st)
            return False
        ok = self._speak_out(text, n0, "away" if away else "ignored")
        companion.save(st)
        return ok

    # ---- the end of a call: a goodbye, then she writes down what she learned
    def call_end(self, reason: str = "user", farewell: bool = True) -> None:
        """Run on a background thread when the call ends (reason: user | idle | window | exit). Never raises."""
        if not self._call_on:
            return
        self._call_on = False
        st = self._state()
        lasted = time.time() - self._call_t0
        try:
            if farewell and lasted > 45 and reason != "exit" and time.time() >= self._quiet_until and self._ends_clean():
                said = self.messages[self._call_idx:]
                n0 = len(self.messages)
                why = {"user": "the user ended the call", "idle": "the call timed out because the user was silent and still for a long time",
                       "window": "the call window was closed"}.get(reason, "the call is ending")
                ask = (f"(The video call is ending: {why}.)\nRecent conversation:\n{self._transcript(said[-10:]) or '(nothing said)'}\n\n"
                       "Say a natural goodbye in your own way (a word or a few sentences) that fits the hour and how the call went. "
                       "If the user already said goodbye and you already answered, reply exactly <silent>.")
                text = self._ask_model(self._companion_system(), {"role": "user", "content": ask}, 500)
                text = re.sub(r"</?say>|PRESENCE\s*:\s*\w+|SEEN\s*:[^\n]*", " ", text, flags=re.I)
                text = " ".join(text.split()).strip('"\u201c\u201d')[:600]
                if text and not re.search(r"<\s*silent\s*>", text, re.I):
                    self._speak_out(text, n0, None)
        except Exception:
            pass
        try:
            self._reflect(st, lasted)
        except Exception:
            pass
        companion.save(st)

    def _call_transcript(self) -> tuple[str, int]:
        """The call as 'USER: ...' / 'HER: ...' lines (her unprompted remarks are marked) and how many times the user spoke."""
        out, users, skip_next = [], 0, False
        for m in self.messages[self._call_idx:]:
            c = m.get("content")
            if isinstance(c, list):
                c = " ".join(p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") == "text")
            if not isinstance(c, str):
                continue
            if m.get("role") == "user" and c == GLANCE_MARK:
                skip_next = True
                continue
            if m.get("role") == "user":
                if c.startswith("[") and "tool_result" in c:
                    continue
                users += 1
                out.append("USER: " + c[:600])
            elif m.get("role") == "assistant" and c.strip():
                out.append(("HER (on her own): " if skip_next else "HER: ") + c[:600])
            skip_next = False
        return "\n".join(out[-60:]), users

    def _reflect(self, st: dict, lasted: float) -> None:
        """Turn the call into durable notes: facts, shared moments, closeness, how it ended."""
        transcript, users = self._call_transcript()
        if not users:                                  # nobody spoke: she was alone on the call
            companion.merge_reflection(st, {"closeness_delta": -0.01 if lasted > 120 else 0, "outcome": "alone"})
            return
        ask = ("Transcript of a video call between the user and you (Emilie):\n" + transcript + "\n\n"
               "Write your private notes. Reply with ONLY a JSON object: "
               '{"facts": [...], "moments": [...], "closeness_delta": number, "outcome": "warm|neutral|lonely"}.\n'
               "- facts: up to 5 durable things about the USER (name, studies/work, hobbies, tastes, plans, habits, people important to them "
               "by role). Only what they said or clearly showed. Short, in their language. Nothing already in: "
               + json.dumps(st.get("facts", [])[-25:], ensure_ascii=False) + "\n"
               "- NEVER note health, money, passwords, exact addresses, other people's private details, politics, sex.\n"
               "- moments: up to 2 small shared moments worth remembering (one short sentence each).\n"
               "- closeness_delta: -0.05 to 0.1 (long warm talk = higher; cold or ignored = lower).\n"
               "- outcome: how the call felt.")
        raw = self._ask_model("You keep short private notes for a companion character. Reply with JSON only.",
                              {"role": "user", "content": ask}, 900)
        mm = re.search(r"\{.*\}", raw, re.S)
        if mm:
            try:
                companion.merge_reflection(st, json.loads(mm.group(0)))
            except ValueError:
                pass

    def _run_turn(self, user_text: str, images: list[tuple[str, str]] | None = None) -> None:
        images = images or []
        mark = len(self.messages)
        self._turn_ckpt = Ckpt(user_text, mark)
        if images:
            if VISION_MODEL and VISION_MODEL != self.model:
                self.console.print(tr_('[{MUTED}]image attached → using vision model: {VISION_MODEL}[/]', MUTED=MUTED, VISION_MODEL=VISION_MODEL))
            elif not VISION_MODEL:
                self.console.print(tr_('[{MUTED}]Camera is on[/]', MUTED=MUTED))
        if self._resume_note:                  # the previous turn was cut short (provider error / Ctrl+C): tell the model
            user_text = (RESUME_NOTES[self._resume_note] + "\n\n" + user_text).strip()
            self._resume_note = ""
        if self._reunion:
            user_text = (self._reunion + "\n\n" + user_text).strip()
            self._reunion = ""
        self.salvaged = 0
        self.messages.append(self._user_message(user_text, images))
        self._drop_old_video()
        try:
            (self._loop_openai if PROVIDER == "openai" else self._loop_anthropic)()
        except BaseException as e:
            self._salvage(mark, e)    # Ctrl+C, provider limit, outage, quota: KEEP the work done so far
            raise
        finally:
            if self._turn_ckpt:
                self.checkpoints.append(self._turn_ckpt)
                self._turn_ckpt = {}
            self.save()

    # ------------------------------------------------------------ keep progress when the provider fails
    @staticmethod
    def _tool_ids(m: dict) -> list[str]:
        """ids of the tool calls an assistant message asks for (OpenAI and Anthropic formats)."""
        if m.get("role") != "assistant":
            return []
        ids = [c.get("id", "") for c in (m.get("tool_calls") or [])]
        if isinstance(m.get("content"), list):
            ids += [b.get("id", "") for b in m["content"] if isinstance(b, dict) and b.get("type") == "tool_use"]
        return [i for i in ids if i]

    @staticmethod
    def _result_ids(ms: list[dict]) -> set[str]:
        got: set[str] = set()
        for m in ms:
            if m.get("role") == "tool":
                got.add(m.get("tool_call_id", ""))
            elif isinstance(m.get("content"), list):
                got |= {b.get("tool_use_id", "") for b in m["content"] if isinstance(b, dict) and b.get("type") == "tool_result"}
        return got

    def _salvage(self, mark: int, exc: BaseException) -> None:
        """A turn ended early: the user pressed Ctrl+C, or the provider failed (rate limit, quota, outage, model
        unavailable). Do NOT throw the turn away: every finished step (files written, commands run, what the model said)
        stays in the history, so after /model or 'continue' the conversation goes on with full memory.
        Only two things are fixed so the history stays valid and true: the provider's fake 'quota' answer is removed, and a
        step whose tool calls did not all run is COMPLETED (the missing ones get an 'interrupted' result: the model learns
        that they did not happen, and the ones that did run are not forgotten)."""
        ms = self.messages
        by_user = isinstance(exc, KeyboardInterrupt)
        if isinstance(exc, QuotaExhausted) and len(ms) > mark + 1 and ms[-1].get("role") == "assistant":
            ms.pop()                                           # the provider's 'quota exhausted' text is not a real answer
        for i in range(len(ms) - 1, mark, -1):                 # the last assistant step must have a result for every call
            ids = self._tool_ids(ms[i])
            if ids:
                missing = [c for c in ids if c not in self._result_ids(ms[i + 1:])]
                if missing:
                    why = "interrupted: the user stopped the agent before this ran" if by_user else "interrupted: not run (provider error)"
                    if PROVIDER == "openai":
                        ms.extend({"role": "tool", "tool_call_id": c, "content": why} for c in missing)
                    else:
                        ms.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": c, "content": why, "is_error": True} for c in missing]})
                break
        steps = sum(1 for m in ms[mark + 1:] if m.get("role") == "assistant")
        if steps == 0:
            del ms[mark:]                                      # nothing was achieved yet: nothing to keep
            self.salvaged = 0
            return
        self.salvaged = steps
        self._resume_note = "user" if by_user else "provider"

    # ------------------------------------------------------------ util loop
    def _round_gate(self, rounds: int) -> bool:
        """False when the effort round limit is reached."""
        if rounds >= self.effort.max_rounds:
            self.console.print(Panel(
                tr_("Stopped: reached the limit of {0} rounds for effort [bold]{1}[/]. Type 'continue' or raise it with /effort high.", self.effort.max_rounds, self.effort.name),
                border_style=WARN, title_align="left", title=tr_('[bold]effort limit[/]')))
            return False
        self._maybe_compact()
        return True

    def _after_text(self, text: str, truncated: bool) -> None:
        if truncated:
            self.console.print(tr_('[{WARN}]answer cut off by the effort limit {0} ({1} tokens). Use /effort to raise it[/]', self.effort.name, self.effort.max_output, WARN=WARN))

    # ------------------------------------------------------------ Anthropic
    def _loop_anthropic(self) -> None:
        rounds = 0
        while self._round_gate(rounds):
            rounds += 1
            view = StreamView(self.console).start()
            try:
                kw = claude.request_kwargs(self.system_prompt(), tools.SCHEMAS, self.messages, self.effort.max_output,
                                           BASE_URL, int(load_settings().get("thinking") or 0))
                with self.client.messages.stream(model=self.active_model, **kw) as stream:
                    for text in stream.text_stream:
                        view.text(text)
                    resp = stream.get_final_message()
            except BaseException:
                view.abort()
                raise
            n_in, n_out = claude.usage_tokens(resp.usage)
            view.finish(n_out)
            self.usage.add(n_in, n_out, True)
            self.messages.append({"role": "assistant",
                                  "content": [b.model_dump(exclude_none=True) for b in resp.content]})
            self._after_text("".join(b.text for b in resp.content if b.type == "text"),
                             resp.stop_reason == "max_tokens")
            calls = [b for b in resp.content if b.type == "tool_use"]
            if not calls and is_quota_error("".join(b.text for b in resp.content if b.type == "text")):
                raise QuotaExhausted("".join(b.text for b in resp.content if b.type == "text"))
            if not calls:
                return
            results = [{"type": "tool_result", "tool_use_id": c.id,
                        "content": self._exec(c.name, c.input)} for c in calls]
            self.messages.append({"role": "user", "content": results})

    # ------------------------------------------------------------ OpenAI-compatible
    def _open_stream(self, oa_tools: list[dict]):
        kw = dict(model=self.active_model, tools=oa_tools, stream=True, max_tokens=self.effort.max_output,
                  messages=[{"role": "system", "content": self.system_prompt()}] + self.messages)
        if self._usage_opt:
            try:
                return self.client.chat.completions.create(stream_options={"include_usage": True}, **kw)
            except Exception as e:  # the provider does not support stream_options -> turn it off, try again
                if "stream_options" not in str(e) and getattr(e, "status_code", 0) != 400:
                    raise
                self._usage_opt = False
        return self.client.chat.completions.create(**kw)

    def _loop_openai(self) -> None:
        oa_tools = [{"type": "function", "function": {
            "name": s["name"], "description": s["description"],
            "parameters": s["input_schema"]}} for s in tools.SCHEMAS]
        rounds = 0
        while self._round_gate(rounds):
            rounds += 1
            view = StreamView(self.console).start()
            content, calls, fin, usage = "", {}, None, None
            in_est = self.ctx_tokens()
            try:
                for chunk in self._open_stream(oa_tools):
                    if getattr(chunk, "usage", None):
                        usage = chunk.usage
                    if not chunk.choices:
                        continue
                    ch = chunk.choices[0]
                    fin = ch.finish_reason or fin
                    d = ch.delta
                    rc = getattr(d, "reasoning_content", None) or (d.model_extra or {}).get("reasoning_content")
                    if rc:
                        view.think(rc)  # the model is "thinking": the spinner keeps running
                    if d.content:
                        content += d.content
                        view.text(d.content)
                    for tc in d.tool_calls or []:
                        c = calls.setdefault(tc.index, {"id": "", "name": "", "args": ""})
                        if tc.id:
                            c["id"] = tc.id
                        if tc.function:
                            c["name"] += tc.function.name or ""
                            c["args"] += tc.function.arguments or ""
                            view.think(tc.function.arguments or "")
            except BaseException:
                view.abort()
                raise
            exact = bool(usage and (usage.prompt_tokens or usage.completion_tokens))
            if exact:
                view.finish(usage.completion_tokens)
                self.usage.add(usage.prompt_tokens, usage.completion_tokens, True)
            else:  # the provider sent no usage (or zero) -> estimate
                view.finish()
                self.usage.add(in_est, int(view.tokens), False)
            msg: dict = {"role": "assistant", "content": content or None}
            if calls:
                msg["tool_calls"] = [{"id": c["id"], "type": "function",
                                      "function": {"name": c["name"], "arguments": c["args"] or "{}"}}
                                     for c in calls.values()]
            self.messages.append(msg)
            self._after_text(content, fin == "length")
            if not calls and is_quota_error(content or ""):
                raise QuotaExhausted(content)      # -> run_turn cleans the history
            if not calls:
                return
            for c in calls.values():
                try:
                    out = self._exec(c["name"], json.loads(c["args"] or "{}"))
                except json.JSONDecodeError:
                    out = "ERROR: tool arguments are not valid JSON"
                self.messages.append({"role": "tool", "tool_call_id": c["id"], "content": out})
