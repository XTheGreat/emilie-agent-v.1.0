# Emilie

A coding agent for your terminal with an animated banner, an optional voice and a video-call companion.
Works with Anthropic, OpenAI-compatible APIs, OpenRouter and NVIDIA (build.nvidia.com).

## Install on Windows

You need Windows 10/11 and Python 3.10+ (`winget install Python.Python.3.12`).
Use **Windows Terminal** (best), not the old console window.

```powershell
git clone https://github.com/XTheGreat/emilie-agent-v.1.0.git
cd emilie-agent-v.1.0
powershell -ExecutionPolicy Bypass -File install.ps1
```

Emilie is copied to `%LOCALAPPDATA%\Emilie`, so you may delete the cloned folder afterwards.
Open a **new** terminal, then:

```powershell
cd C:\path\to\your\project
emilie
```

The first run asks which provider to use and for your API key (stored in `%USERPROFILE%\.emilie\keys.json`).
Change it later with `emilie --setup`.

### Manual install

```powershell
python -m venv .venv
.venv\Scripts\pip install -e .
.venv\Scripts\emilie
```

## Windows notes

- The `bash` tool runs commands in **PowerShell** (`pwsh` if installed, otherwise Windows PowerShell). Emilie knows this and writes PowerShell commands.
- Camera (`Alt+C`, video call) and microphone use **ffmpeg** with DirectShow: `winget install Gyan.FFmpeg`.
- Voice output needs a running voicebox server; audio plays through `mpv`/`ffplay` if installed, otherwise the built-in PowerShell WAV player.
- Kitty-style inline images are not available in Windows Terminal; the camera view uses a separate window (Tk, included with Python) or half-block characters.
- Settings, history and sessions live in `%USERPROFILE%\.emilie\`.

## MCP servers

Put them in `%USERPROFILE%\.emilie\mcp.json` (or `.mcp.json` in a trusted project folder):

```json
{
  "mcpServers": {
    "browser": { "command": "npx", "args": ["-y", "@playwright/mcp@latest", "--browser", "chrome"] }
  }
}
```

Requires Node.js (`winget install OpenJS.NodeJS.LTS`). Check status with `/mcp`; reload with `/mcp reload`.
Every MCP tool call asks for permission first.

## Commands

`/help` lists everything. Useful ones: `/mcp`, `/effort`, `/logo size <n>`, `/voice`, `/camera`, `/history`.
Project instructions go in `EMILIE.md`; skills in `.emilie\skills\`.

## More commands

| | |
|---|---|
| `/plan` then approve | In plan mode Emilie investigates, then shows a plan: **y** approve (asks per change), **t** approve and run on its own, **n** keep planning |
| `/review`, `/commit`, `/pr` | Review changes (`/review`, `/review <branch>`, `/review <PR#>`), write the commit message and commit (never pushes), draft a PR title and body |
| `/rewind` | Go back to before an earlier turn: files, chat, or both |
| `/allow`, `/deny`, `/permissions` | Permanent allow/deny rules (`mcp__browser__*`, `bash(git *)`, `read_file(*.env*)`) and an overview |
| `/config` | See and change settings (`/config timeout 300`); `live` ones apply at once |
| `/fallback <model>` | Backup model used when the main one keeps failing; busy/rate-limit errors are retried first |
| `/doctor` | Test what the current model supports (chat, streaming, tools, vision) |
| `/export [file.md]` | Save the conversation as markdown |
| `/schedule` | Run a prompt on a timer with the Windows Task Scheduler (read-only unless you pass `--trust`) |
| `/cost` | Token usage; set `/config price_in` and `price_out` (USD per 1M tokens) for a cost estimate |
| `emilie -p "prompt"` | One non-interactive turn for scripts; `--trust` allows edits, exit code 2 = something was denied |

## Notebook and Office tools

No extra packages needed (they use only the standard library):

| Tool | What it does |
|---|---|
| `notebook_edit` | Edit a Jupyter notebook cell by cell: list, get, replace, insert, append, delete, move, clear outputs; several edits at once, all or nothing |
| `notebook_run` | Run the notebook with your own Python (from `PATH`, or `python=`) and store the outputs, `print` text and matplotlib figures in it. Packages must already be installed there. Magics (`%`) are ignored and `!` lines skipped |
| `docx_read` / `docx_edit` / `docx_create` | Read, edit in place (replace text across formatting, paragraphs, tables, pictures) and create Word documents; styles and everything else are kept |
| `xlsx_read` / `xlsx_write` | Read a sheet as a grid (dates and formulas shown) and set cells or formulas, or create a workbook |
| `pptx_read` | Slide text, tables and speaker notes |

Changing tools ask permission like `write_file` (`/allow notebook_edit` to skip the question); `notebook_run` asks like a shell command.
`read_file` also opens `.docx`, `.xlsx` and `.pptx` as text. Not supported: tracked changes, charts, cell styling, adding sheets to an existing workbook, layout rendering.

`read_file` also reads PDFs (`pages="1-5"`), notebooks and images. The `tasks` tool runs up to four read-only sub-agents in
parallel. MCP servers can be remote too: `{"url": "https://...", "headers": {"Authorization": "Bearer ${TOKEN}"}}`.
Global instructions go in `%USERPROFILE%\.emilie\EMILIE.md` (loaded for every project, before the project's own file).

## Scrolling

The conversation scrolls inside Emilie (mouse wheel, touchpad, PageUp/PageDown). Tune the feel live with `/scroll`:
`/scroll lines <1-10>` (lines per mouse-wheel notch) and `/scroll smooth <0-300>` (milliseconds of easing, 0 = instant).
The settings are saved in `%USERPROFILE%\.emilie\settings.json`.

## Linux

It also runs on Linux: `pip install -e .` then `emilie`.
