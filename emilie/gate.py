"""The "trust this folder?" screen shown before Emilie loads anything from the working folder.

Full-screen: the animated logo on top, the question under it. Enter on "Yes" remembers the folder and
starts the agent; "No" / Esc / Ctrl+C exits. Click the logo for the water ripple, as everywhere else.
"""
import sys
import textwrap

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.mouse_events import MouseEventType

from . import __version__, anim, logo, trust
from .i18n import t as tr_
from .inputbox import steady_output
from .theme import ERR, MUTED, OK, ROSE, WARN


def _text_blocks(cwd: str, width: int) -> list[tuple[str, str]]:
    """[(style, paragraph)] of the question, translated and wrapped later to the screen width."""
    blocks = [
        (MUTED, tr_("Accessing workspace:")),
        (f"bold {ROSE}", cwd),
        ("", tr_("Quick safety check: is this a project you created or one you trust? (Like your own code, a "
                 "well-known open source project, or work from your team.) If not, take a moment to review "
                 "what is in this folder first.")),
        ("", tr_("Emilie will be able to read, edit and run files here. It may also load skills, commands, "
                 "MCP servers and EMILIE.md from this folder.")),
    ]
    if trust.is_risky(cwd):
        blocks.append((f"bold {WARN}", tr_("This is your home (or root) folder: trusting it would cover everything "
                                           "inside it. Consider opening a specific project folder instead.")))
    return blocks


def run_gate(tui, cwd: str) -> bool:
    """Show the screen. True = trusted (and remembered), False = exit."""
    state = {"idx": 0}                                         # the pointer starts on "No, exit" (safe default)
    sprites: dict[int, "logo.Sprite"] = {}
    still: dict = {}

    def still_source():
        """The logo as a STILL image (icon.png / logo.png / first video frame): this screen never plays the video."""
        if "src" not in still:
            src = None
            try:
                sp = logo.find_still()
                if sp:
                    src = logo.Source(sp)
                else:
                    p = logo.find_logo()
                    src = logo.Source(p).make_still() if p else None
            except Exception:
                src = None
            still["src"] = src
        return still["src"]

    def pick_sprite(max_rows: int):
        src = still_source()
        if src is None or max_rows < 8:
            return None
        cols = max(12, min(40, int(max_rows * 2 / max(0.2, src.aspect))))
        if cols not in sprites:
            try:
                sp = logo.Sprite(src, cols)
                sp.t0 = -100.0                                  # skip the intro sweep: a plain, static image
                sprites[cols] = sp
            except Exception:
                return None
        return sprites[cols]

    def option(i: int, label: str, cols: int):
        sel = state["idx"] == i

        def click(me, i=i):
            if me.event_type == MouseEventType.MOUSE_UP:
                state["idx"] = i
                finish(i == 1)
        style = f"bold {ROSE}" if sel else ""
        return [(style, ("❯ " if sel else "  "), click), (style, f"{i + 1}. {label}", click)]

    def frags():
        cols, rows = tui._cols_rows()
        w = max(30, min(cols - 6, 78))
        title = [(f"bold {ROSE}", "(=^.^=) Emilie Agent"), (MUTED, f"  v{__version__}")]
        blocks = _text_blocks(cwd, w)

        def build(drop: int) -> list[list[tuple]]:
            """drop = how many optional parts to leave out (credit, long paragraphs) when the screen is small."""
            body: list[list[tuple]] = [title]
            if drop < 3:
                body.append(anim.rule_fragments(w, tui._ft()))
            body.append([])
            for i, (style, para) in enumerate(blocks):
                if (i == 2 and drop >= 2) or (i == 3 and drop >= 1) or (i == 4 and drop >= 2):
                    continue                                    # safety paragraphs go first, workspace + path never
                for ln in (textwrap.wrap(para, w, break_long_words=True, break_on_hyphens=False) or [""]):
                    body.append([(style, ln)])
                if drop < 3:
                    body.append([])
            body.append(option(0, tr_("No, exit"), cols))
            body.append(option(1, tr_("Yes, I trust this folder"), cols))
            if drop < 3:
                body.append([])
            body.append([(MUTED, tr_("Enter to confirm · Esc to cancel"))])
            if drop < 1:
                body.append([("", "")])
                body.append([(MUTED, "Develop By "), (f"bold {ROSE}", "SecretByEnumb")])
            return body
        drop = 0
        body = build(drop)
        if tui.sprite is not None and rows - len(body) - 2 < 8:     # prefer a small logo over the credit line + one paragraph
            drop = 1
            body = build(drop)
        while len(body) > rows - 1 and drop < 3:                # everything must fit: options stay visible
            drop += 1
            body = build(drop)
        sp = pick_sprite(rows - len(body) - 2)
        top: list[list[tuple]] = []
        if sp is not None and cols >= 30:
            pad = max(0, (cols - sp.w) // 2)
            for row in anim.sprite_rows(sp, tui._t(), col0=pad):
                top.append([("", " " * pad)] + [(it[0], it[1]) for it in row])      # (style, text) only: not clickable
            top.append([])
        total = len(top) + len(body)
        vpad = max(0, (rows - total) // 3)
        left = " " * max(0, (cols - w) // 2)
        out: list[tuple] = [("", "\n" * vpad)] if vpad else []
        for ln in top:
            out += ln + [("", "\n")]
        for ln in body:
            out += [("", left)] + ln + [("", "\n")]
        return out

    kb = KeyBindings()
    app: Application

    def finish(yes: bool) -> None:
        if app.is_running:
            app.exit(result=yes)

    @kb.add("up")
    @kb.add("down")
    @kb.add("k")
    @kb.add("j")
    @kb.add("tab")
    def _(event):
        state["idx"] = 1 - state["idx"]

    @kb.add("2")
    @kb.add("y")
    def _(event):
        finish(True)

    @kb.add("1")
    @kb.add("n")
    @kb.add("q")
    @kb.add("escape", eager=True)
    @kb.add("c-c")
    @kb.add("c-d")
    def _(event):
        finish(False)

    @kb.add("enter")
    def _(event):
        finish(state["idx"] == 1)

    fps = 12                                                    # only the gradient rule moves here (the logo is a still)
    animating = False
    app = Application(layout=Layout(Window(FormattedTextControl(frags, show_cursor=False),
                                           always_hide_cursor=True, wrap_lines=False)),
                      key_bindings=kb, full_screen=True, mouse_support=True, output=steady_output(),
                      refresh_interval=(1.0 / fps) if (animating or tui.borders_anim) else None)
    yes = bool(app.run())
    if yes:
        if trust.remember_enabled():
            trust.add(cwd)
    return yes


def text_gate(cwd: str) -> bool:
    """Plain-terminal version (classic UI). Never prompts when there is no terminal."""
    print(tr_("Accessing workspace:"), cwd)
    print(tr_("Emilie will be able to read, edit and run files here. It may also load skills, commands, "
              "MCP servers and EMILIE.md from this folder."))
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print(tr_("This folder is not trusted yet. Run emilie in a terminal to confirm it, or pass --trust-folder."),
              file=sys.stderr)
        return False
    try:
        ans = input(tr_("Trust this folder? [y/N] ")).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    if ans in ("y", "yes"):
        if trust.remember_enabled():
            trust.add(cwd)
        return True
    return False
