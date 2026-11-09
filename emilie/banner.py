import os
import uuid

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .i18n import t as tr_
from . import __version__
from . import logo
from .theme import LAV, MUTED, ROSE
from .tools import shorten

FALLBACK = """\
   ⣀⣤⣤⣀
 ⣴⣿⣿⣿⣿⣿⣦
 ⣿⣿⣿⠿⠿⣿⣿⣿
 ⠙⢿⣿⣿⣿⣿⡿⠋
    ⠉⠉⠉⠉
 (put assets/logo.png)"""


def make_logo(width: int = 34) -> Text:
    return logo.static_logo(width) or Text(FALLBACK, style=ROSE)


def print_banner(console: Console, model: str, tool_groups: dict[str, list[str]],
                 session: str | None = None, effort: str = "medium", mode: str = "") -> None:
    session = session or uuid.uuid4().hex[:8]
    mode = mode or tr_('ask first')

    left = Text()
    right_w = 40
    logo_w = max(20, min(40, console.width - 6 - 4 - right_w))
    left.append_text(make_logo(logo_w))
    left.append(f"\n\n{model}", style=f"bold {ROSE}")
    left.append(f"\n{os.getcwd()}", style=LAV)
    left.append(f"\neffort {effort} · {mode}", style=MUTED)
    left.append(f"\nSession: {session}", style=MUTED)

    right = Text()
    right.append("Welcome!\n", style=f"bold {ROSE}")
    right.append(tr_('Tell me what we are building today.\n\n'), style=MUTED)
    right.append("Tools\n", style=f"bold {LAV}")
    for group, names in tool_groups.items():
        right.append(f"  {group:<7}", style=LAV)
        right.append(", ".join(shorten(names)) + "\n")
    right.append("\nTips\n", style=f"bold {LAV}")
    for k, v in [(tr_('shift+tab'), tr_('switch mode ask/trust/plan')), ("@file", tr_('include a file')),
                 ("!command", tr_('run a shell command')), ("ctrl+v", tr_('paste an image')),
                 ("/effort", tr_('token saving level')), ("/help", tr_('all commands'))]:
        right.append(f"  {k:<10}", style=ROSE)
        right.append(f"{v}\n", style=MUTED)

    grid = Table.grid(padding=(0, 4))
    grid.add_column()
    grid.add_column(width=right_w)
    grid.add_row(left, right)

    console.print(Panel(
        grid,
        title=tr_('[bold {ROSE}](=^.^=) Emilie Agent[/] [{MUTED}]v{0}[/]', __version__, ROSE=ROSE, MUTED=MUTED),
        title_align="left",
        border_style=ROSE,
        padding=(1, 2),
    ))
