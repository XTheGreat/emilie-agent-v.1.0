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

## Desktop app

The same Emilie in a window that works like the Claude Code desktop app: sessions in a sidebar grouped by folder,
streaming answers, tool calls with diffs, permission cards, plan approval, a task list, `/` commands and `@` files,
a model / effort / mode picker, Files, Terminal, Browser and Changes panes, and a full Settings page.
It needs Node.js once, for the window (`winget install OpenJS.NodeJS.LTS`):

```powershell
powershell -ExecutionPolicy Bypass -File install-desktop.ps1
```

Then open **Emilie** from the Start menu or the desktop shortcut, or run `emilie app`
(`emilie app --browser` opens the same interface in your browser, no Node.js needed).
Every slash command, skill, MCP server and setting of the terminal version works there too; both share
`%USERPROFILE%\.emilie`. How it is built and how to extend it: [docs/DESKTOP.md](docs/DESKTOP.md).

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
Every MCP tool call asks for permission first, except in trust mode (Shift+Tab), where MCP tools are allowed. To allow only some, use a rule such as `/allow mcp__playwright__*`.

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

## Safe edits

Every time Emilie writes or edits a file, its syntax is checked at once. If her change broke the file, the error and
the lines around it come back to her in the same step, so she fixes it before going on instead of finding out later
from a failing build (you see it too, as a `⚠` line under the tool call):

| File | Checked with |
|---|---|
| Python | Python's own compiler (`.py`, `.pyi`) |
| JSON | strict JSON; comments and trailing commas are accepted where the reading tool allows them (`tsconfig.json`, `.vscode\*.json`, `*.jsonc`, ...) |
| TOML, XML, SVG | built in |
| JavaScript, TypeScript, JSX/TSX | the project's own TypeScript from `node_modules` (or a global one); without it `node --check` for `.js` |
| PowerShell | the PowerShell parser |
| YAML | PyYAML, when installed (`pip install pyyaml`) |
| Shell scripts | `bash -n` (Linux/macOS) |

Only the syntax is checked: nothing is run and types are not checked. An error that was already in the file before her
change is mentioned once, briefly. `write_file` also refuses to replace an existing file she has not read in this
conversation, or one that changed on disk since she read it (you edited it meanwhile), so your work is never
overwritten unseen. Turn them off with `/config syntax_check off` and `/config overwrite_guard off`.

## Rate limits (429)

Free and shared endpoints (NVIDIA build.nvidia.com, OpenRouter's free models, Groq) answer `429 Too Many Requests`
when you go over your limit, and on a busy model even when you use it lightly. Emilie waits instead of failing:

- every rate-limited or busy request is tried again up to 6 times (`/config retries 0-10`), waiting what the provider
  asks for (`Retry-After`, `x-ratelimit-reset`) or else 5, 10, 20, 40, 60, 60 seconds, so up to about 3 minutes;
- all sessions on your computer (each desktop session, the terminal, sub-agents) share one cool-down per model, kept
  in `%USERPROFILE%\.emilie\ratelimit.json`: after a 429 none of them calls that model until the wait is over;
- after a 429 her requests to that model are spaced a few seconds apart for a while, then she speeds up again;
- session titles and video-call remarks are skipped while the model is rate-limited.

If the provider still refuses after that, your progress is kept: type `continue` later, set `/fallback <model>` so she
switches by herself, or pick another model with `/model`. A used-up quota or daily limit is reported at once.

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

## Web search and page reading

Two tools keep tokens and credits low: `web_search(query, intent, max_results)` returns only title, domain, date, a
snippet (max 300 characters) and the url (default 4 results, max 6); `read_page(url, focus)` then opens the chosen page
as Markdown, at most 6,000 characters, most relevant paragraphs first when `focus` is given.

**API keys.** Put them in `%USERPROFILE%\.emilie\.env` (survives reinstalling), or in `.env` at the repo root when you
run from source. Copy the names from [.env.example](.env.example), then restart Emilie. A provider without a key is skipped.

| Variable | Needed for |
|---|---|
| `TAVILY_API_KEY` | Tavily search |
| `EXA_API_KEY` | Exa search |
| `FIRECRAWL_API_KEY` | Firecrawl page reader |
| `JINA_API_KEY` | optional: higher Jina Reader limits |
| `SEARXNG_URL` | optional: your own SearXNG (JSON format enabled) |

| Provider | Used for | Free allowance assumed (check the pricing page) |
|---|---|---|
| Tavily | `general`, `news`; last backup for `docs` | 1,000 credits/month |
| Exa | `semantic` | about $10 credit/month |
| ddgs | first for `docs`, backup for the rest | no key; needs `pip install ddgs` |
| SearXNG | like ddgs | self-hosted |
| Jina Reader | `read_page`, first | free without a key, rate limited |
| Firecrawl | `read_page`, when Jina fails | 1,000 credits/month |
| plain HTTP | `read_page`, last | free |

Install ddgs into Emilie's own environment:

```powershell
& "$env:LOCALAPPDATA\Emilie\venv\Scripts\python.exe" -m pip install ddgs
```

- Limits (env): `TAVILY_LIMIT=900`, `EXA_LIMIT=900`, `FIRECRAWL_LIMIT=400` per month; `WEB_SEARCH_BUDGET=5`,
  `WEB_READ_BUDGET=3` per task (cache hits are free). `TAVILY_DEPTH=advanced` costs 2 credits per search.
- Cache: `./.cache/web/` (news 30 minutes, general/semantic/pages 24 hours, docs 7 days).
- Usage counter: `%USERPROFILE%\.emilie\web_usage.json`. It counts only what Emilie spends. Log with provider, remaining
  quota and estimated tokens: `%USERPROFILE%\.emilie\web.log`.
- Junk domains to drop: `config/blocked_domains.txt`.
- Privacy: queries go to the search provider, and the urls you read go to Jina or Firecrawl.

Example (what the agent calls): `web_search("berita AI hari ini", intent="news")`, then
`read_page(url, focus="model baru")`.

Tests (providers are mocked): `python -m unittest discover -s tests`. The live test runs only with `TAVILY_API_KEY` and
`EMILIE_LIVE_TESTS=1` set.

## Diagrams

The `render_diagram` tool turns Mermaid or PlantUML source into an SVG or PNG in `.\diagrams\` of your project. It
asks permission first (except in trust mode) and is blocked in plan mode. The renderers are not installed with
Emilie; install the ones you want:

| | Mermaid | PlantUML |
|---|---|---|
| Needs | Node.js 18+, mermaid-cli | Java, Graphviz, PlantUML |
| Windows | `winget install OpenJS.NodeJS.LTS`<br>`npm install -g @mermaid-js/mermaid-cli` | `winget install EclipseAdoptium.Temurin.21.JRE`<br>`winget install Graphviz.Graphviz`<br>`choco install plantuml` |
| macOS | `brew install node`<br>`npm install -g @mermaid-js/mermaid-cli` | `brew install openjdk graphviz plantuml` |
| Linux (Debian/Ubuntu) | install Node.js 18+, then<br>`npm install -g @mermaid-js/mermaid-cli` | `sudo apt install default-jre graphviz plantuml` |

Open a new terminal (or restart the app) afterwards so the new commands are on `PATH`.

Example: ask "draw the login flow as a flowchart", or the call itself:

```json
{"kind": "mermaid", "fmt": "svg", "filename": "login", "code": "flowchart TD\n  A[Login] --> B{Valid?}\n  B -->|yes| C[Home]\n  B -->|no| A"}
```

It answers `{"ok": true, "path": "...\\diagrams\\login.svg"}`, or `{"ok": false, "error": "..."}` with the renderer's
own message so Emilie can fix the syntax and try again. A file with the same name is replaced (`/rewind` does not
restore it). Source is limited to 100 KB and a render to 60 seconds. PlantUML runs with
`PLANTUML_SECURITY_PROFILE=SANDBOX` (no `!include` of local files or URLs) unless you set that variable yourself.
`--no-sandbox` (`emilie/builtin/puppeteer.json`) is used for Mermaid only if Chromium fails with a sandbox error.

Without a local renderer you can set `KROKI_URL` (your own [Kroki](https://kroki.io) server, or `https://kroki.io`).
The diagram source is then **sent to that server**.

Tests: `python -m unittest discover -s tests -v` (tests needing a missing renderer are skipped).

## Scrolling

The conversation scrolls inside Emilie (mouse wheel, touchpad, PageUp/PageDown). Tune the feel live with `/scroll`:
`/scroll lines <1-10>` (lines per mouse-wheel notch) and `/scroll smooth <0-300>` (milliseconds of easing, 0 = instant).
The settings are saved in `%USERPROFILE%\.emilie\settings.json`.

## Linux

It also runs on Linux: `pip install -e .` then `emilie`.

## Editable draw.io diagrams

Install draw.io Desktop (`winget install JGraph.Draw` on Windows), or point
`DRAWIO_PATH` at its executable. Ask Emilie to “Render examples/contoh.drawio
as login.png and inspect the result.” The equivalent tool call is
`render_drawio(xml=<complete XML>, filename="login", fmt="png", scale=2)`.
The editable source and export go into `./diagrams/`. SVG and PDF exports also
produce a sibling PNG for visual review. See [the XML style guide](emilie/builtin/DRAWIO_STYLE.md).
