# Emilie desktop app

A window for Emilie that looks and works like the Claude Code desktop app. It is the same agent as the terminal
version: the CLI core runs unchanged, only the display is new.

Stack: **Electron** (the window) + **React 19, TypeScript, Tailwind CSS 4, Radix UI** (the interface, bundled with
**Vite**) + Emilie's **Python** engine.

## Install and run

```powershell
powershell -ExecutionPolicy Bypass -File install-desktop.ps1   # once: packages, build, Start menu + desktop shortcuts
emilie app                                                     # or the "Emilie" shortcut
emilie app --browser                                           # the same UI in your browser (no Electron needed)
```

## How it fits together

```
 Electron window (desktop/electron/main.cjs)
   │ starts  python -X utf8 -m emilie.desktop --port 0 --token <random> --watch-stdin
   │ loads   http://127.0.0.1:<port>/?token=…   (the React UI, built into emilie/desktop/web)
   ▼
 hub  (emilie/desktop/hub.py)  local HTTP server, 127.0.0.1 only, token + Host check
   │   JSON API  /api/…   ·   one event stream  /api/events (server-sent events)   ·   /media/… (logo, files)
   │   one worker process per open session (several can run at once, each in its own folder)
   ▼
 worker  (emilie/desktop/worker.py)   runs cli.make_core() — the CLI core, unchanged
       console.print(...)        → "item" events   (blocks.py turns Rich panels / tables into JSON)
       console.tui.ask_permission / choose / mark_running / talk_toggle   → "request" events, answered by the UI
       StreamView                → "delta" events (streaming text)
       ui.tool_header / result   → "item" + "tool_end" events, with the full output and a real diff
```

The worker also tells the model it is answering in a desktop window (`DESKTOP_STYLE` in `worker.py`): plain
Markdown, no box-drawing or ANSI art, no pasted command output (tool calls are already shown), no terminal key hints.
The terminal version's prompt is not changed.

## The window, piece by piece

- **Conversation**: tool calls in a row collapse into one quiet line, as in Claude Code ("Ran 3 commands, edited
  worker.py +6 −2 ›"); click it for each call with its output and diff (`ToolGroup` / `groupItems` in `Transcript.tsx`).
- **Environment panel** (right, 240px, `EnvPanel.tsx`): computer, folder, git branch, voice, context, connectors,
  the files Emilie wrote (click one to view it) and the git changes. Title-bar button or Settings → Code to hide it.
- **Viewer** (`Panes.tsx`): files, terminal, changes and browser as tabs, plus a tab per opened file; the path row
  ("docs \ GUIDE.md", from the project folder) sits between two lines, and Markdown files open rendered (</> shows
  the source). As in Claude Code, opening a tab closes the docked Environment panel; its title-bar button then shows
  it floating over the conversation (`envFloat` in the store; also used when the window is too narrow to dock it).
  The conversation never gets narrower than 380px (`App.tsx`, `MAIN_MIN` / `ENV_W` / `PANE_MIN`).
- **Session layout** (`SessionView.tsx`): the conversation fills the whole height and scrolls behind the message box,
  which floats at the bottom (its height is measured, so the last message always clears it); a line separates the
  title bar from the conversation once there is one.
- **Replies** (`Transcript.tsx`): hovering the last reply of a turn shows Claude Code's row: copy, fork from here (a
  new session with the conversation up to that reply: the worker's `fork` command, `/api/session/fork`), pin (the
  session moves to a "Pinned" group at the top of the sidebar; the `desktop_pinned` setting), read aloud (Emilie's
  voice) and "5 minutes ago". The terminal's "done in 3s" line is not shown in the window (the CLI keeps it).
- **Working line**: Emilie's flower (`Bloom`) turns and breathes while a word changes every few seconds ("Thinking…",
  "Pondering…"); while a tool runs it says what she is doing. Words: `THINKING_WORDS` in `Transcript.tsx`.
- **Search** (Ctrl+K or Search in the sidebar, `SearchPalette.tsx`): Claude Code's palette, measured from it (510px,
  25% from the top, the window dimmed by half). Types All / Artifacts / Sessions (chats) / Code (folder sessions) /
  Projects / Scheduled, "Recents" while nothing is typed, then "Results"; Actions: New session. Keys: ↑↓ move, ←→
  change type, Enter open, Alt+Enter the row's actions (open, pin, rename, open folder…), `/` filters (updated
  today / past week / past month, one folder), Tab "Compose" (a new session with what you typed), Esc close.
- **Projects** and **Artifacts** pages (`Pages.tsx`) have Claude Code's layout: serif title, tools at the top right,
  "Pinned" / "Recent" project cards (pin from a card's ··· menu, `desktop_pinned_projects`), and for artifacts the
  type tabs, search / filter / list-or-cards / +, the six "Make something new" tiles (each starts a session with the
  request half-written) and cards with a preview of the page: the picture itself or the file's first lines
  (`/api/fs/read?head=1800`, loaded as cards scroll into view).
- **Customize** (`CustomizePage` in `Pages.tsx`): Skills, Connectors and Scheduled tasks on their own page, as in
  Claude Code. The sidebar's Customize, More → Skills / Connectors / Scheduled tasks, the profile menu and the
  Environment panel's Connectors row open it. (Before, these called Settings with section names that did not exist,
  so Settings always opened on General.) Its panels act on the session you came from (`recentLive` in the store).
- **Environment chip** ("This computer" under the message box, `ComputerChip` in `Pickers.tsx`): tooltip
  "Environment"; its menu is Claude's: Search environments, Local (This computer ✓ and your folders), + New
  environment (pick a folder).
- **Context ring** (right of the chips): empty (only its faint track) until the session has used some context.
- **Usage** (Settings → Usage, or Usage in the profile menu; `UsagePanel.tsx`): tokens across all sessions. A range
  filter (7 / 30 / 90 days, all time) scopes everything under it: ranked bars per provider and model (input, output,
  requests), the overall totals, and a column chart per day (per week past 120 days) with a tooltip per column
  (hover or keyboard) and a table view of the same numbers. One series colour (`--chart-1`, checked with the dataviz
  palette validator for both themes and both accents). Data: `/api/usage?days=…` (`usage_log.LEDGER` in the hub).
- **Testing the window without touching your data**: start Electron with `USERPROFILE`/`HOME` pointing at an empty
  folder (Emilie keeps everything in `~/.emilie`) and its own `--user-data-dir`; `EMILIE_API_KEY` (any text) and
  `EMILIE_BASE_URL=http://127.0.0.1:9` get past the first-run screen without any request leaving the machine. For real
  replies, point `EMILIE_PROVIDER=openai` and `EMILIE_BASE_URL` at a small local server that answers
  `/v1/chat/completions` with a fixed streamed reply.
- **Settings** is a floating window over the app (`Settings.tsx`, Radix Dialog), with search across all settings.
- **Chips under the message box** (`Pickers.tsx`) each explain themselves in a tooltip (`TipBody` in `ui.tsx`).
- **Fonts**: Claude uses Anthropic's own typefaces (Anthropic Sans and Anthropic Serif), which are not licensed for
  other apps. Emilie uses the closest open fonts, measured against Claude's pixels: Newsreader at 12.6px for replies
  (same line breaks as Anthropic Serif) and Source Sans 3 for the interface (11.5px in the sidebar). Settings →
  Appearance → Chat font switches replies to sans, the system font or a dyslexia-friendly one. All bundled.
- **Geometry** (measured from Claude Code at 100%): message box 585px wide, the conversation 14px inside it on the left
  and 13px on the right, replies 43px narrower still (`SessionView.tsx`); sidebar rows 25px on a 26px pitch.
- **Zoom**: Ctrl+= / Ctrl+- / Ctrl+0. When the window is not at 100% the title bar shows the zoom ("110%"); click it
  to go back. Everything above assumes 100%.
- **Colours**: Emilie's pink (`#d9689a`, the terminal's ROSE) is the accent everywhere, the context ring included;
  Settings → Appearance offers Sakura (pink) or Lavender. Claude's orange is not used (an old "clay" setting shows pink).
- **Profile row and menu** (`AccountRow` in `Sidebar.tsx`): avatar, name and provider with the chevron at the far
  right, as in Claude Code; its menu has Claude's layout (Settings, Usage, Language, Get help, Send feedback, Learn
  more ›, Provider and model, Skills and connectors, View changelog, Quit) with icons.
- **Menus and messages**: dropdowns use Claude's measured style (`--dropdown-*` tokens: #303030 fill, #363636 border,
  21px rows, #454545 separators); toasts are neutral (white text, only the small icon is coloured). A session whose
  folder is gone says so plainly (the trust check reports `exists`) instead of asking to trust a missing folder.
- **Tool use**: `emilie/toolguide.py` is added to the system prompt (terminal and app): how to use each tool well,
  what to do when a tool fails, and how to report. Edit it there.
- **Usage log** (`emilie/usage_log.py`, terminal and app): every model call (conversation, sub-agents, helper calls)
  appends one line to `~/.emilie/usage.jsonl`: time, provider id, model, input and output tokens, and whether the
  provider reported them or Emilie estimated them. `Usage.add` in `agent.py` writes it; each session process appends
  under a short file lock, and the hub reads only the new lines on each request. Counting starts with this version.
- **Workspace snapshot** (`emilie/workspace.py`, terminal and app): when a session starts or is cleared, Emilie gets
  today's date, the git branch with its uncommitted changes and last 5 commits, the project's scripts (package.json,
  pyproject, a virtualenv…) and the top-level layout, so she starts oriented instead of spending her first tool calls
  on `git status` / `ls` and never guesses the year. Taken once, so the prompt stays cacheable; marked as possibly
  out of date. Home, a drive root and the chat folder get the date only.
- **MCP awareness**: every request lists the MCP servers connected right now with their exact tool names
  (`mcp.inventory()`, purposes in `mcp.PURPOSE`), and a turn waits up to 30s for servers still starting
  (`Agent._await_mcp`), so the model never believes a slow-starting server (npx) is missing.
- **Pictures from tools**: an image an MCP tool returns (a browser screenshot) is saved in `~/.emilie/images`, shown to
  the model, and drawn as a thumbnail on the tool line (click: full size in the viewer); images opened with read_file
  too (`convert.finish_tool` → `images`).
- **Task list**: lives in the conversation under the latest message, as in Claude Code (`TaskList` in `Requests.tsx`).
- **Windows taskbar** (`main.cjs`): `setAppDetails` gives the taskbar button Emilie's icon and name (not Electron's)
  and a relaunch command, so "Pin to taskbar" pins Emilie. The right-click jump list mirrors Claude's: recent folders
  under "New Code Session", then New Chat / New Code Session / Continue "<last session>" (`updateJumpList`, fed by
  `useJumpList` in `App.tsx`). A click starts Emilie with `--new-chat`, `--new-session=<folder>` or
  `--open-session=<id> --cwd=<folder>`; the running window gets it (`second-instance`) and the page acts on it.
  `EMILIE_APP_ID` gives a test instance its own taskbar entry. Jump lists fail when `USERPROFILE` is moved (tests).
  Windows takes the taskbar icon from the Start Menu shortcut carrying the app id (`dev.emilie.app`):
  `fixStartMenuShortcut()` keeps `Emilie.lnk` carrying it and removes a bare `Electron.lnk` that claims it (Windows had
  made one for notifications, which put Electron's atom on the taskbar; the old id stays cached to it in Explorer).
- **Emilie's icon size**: `/logo size <12-80|auto>` (the terminal's command) or Settings → Appearance → Icon size;
  about 3.2px per step on the New session screen (26 ≈ the default 84px). Any setting a /command changes reaches the
  window at once: the worker announces it (`save_and_tell` in `worker.py`).

Sessions are the CLI's own files (`~/.emilie/sessions`), so a session started in the terminal opens in the app and
the other way round. The app adds a small file per session in `~/.emilie/desktop/sessions` (title, what you typed
for `/commands`, command output) and writes its log to `~/.emilie/desktop/desktop.log`.

## Files

| Path | What |
|---|---|
| `desktop/electron/main.cjs` | the window: starts the server, native folder/file pickers, notifications, zoom, title bar colours |
| `desktop/electron/preload.cjs` | the only bridge between the page and Electron (`window.emilieDesktop`) |
| `desktop/ui/src/lib/store.ts` | app state (zustand); `onEvent()` handles every server event |
| `desktop/ui/src/lib/api.ts` | `get` / `post` / event stream |
| `desktop/ui/src/components/` | `App`, `TitleBar`, `Sidebar`, `Home`, `SessionView`, `Transcript`, `Composer`, `Pickers`, `Requests`, `Settings`, `SettingsPanels`, `EnvPanel`, `Panes`, `Pages`, `Dialogs`, `EmilieIcon`, `ui` (Radix building blocks) |
| `desktop/ui/src/styles.css` | Claude's colour tokens (light + dark), markdown, code and diff styles |
| `emilie/desktop/hub.py` | HTTP API, event stream, worker pool, sessions list, files, git, terminal, MCP config, … |
| `emilie/desktop/worker.py` | one session; the bridge to the CLI core |
| `emilie/desktop/schema.py` | the Settings page as data, and the one place settings are validated and saved |
| `emilie/desktop/convert.py` | saved messages → transcript items (when a session is opened again) |
| `emilie/desktop/blocks.py` | Rich renderables → JSON blocks |

## Changing it

**Develop with hot reload**

```powershell
python -X utf8 -m emilie.desktop --port 47321 --token dev     # terminal 1 (the Emilie venv's python)
cd desktop; npm run dev                                        # terminal 2, then open http://localhost:5173/?token=dev
```

After changing the UI run `npm run build` (in `desktop/`); the window picks it up on the next start (or Ctrl+R).
`npm run typecheck` checks the TypeScript. Python changes need the app restarted.

**A new slash command, skill or MCP server** needs nothing here: the app sends what you type to the CLI core, the
`/` menu lists `inputbox.COMMANDS` plus the skills, and whatever the command prints is shown (panels and tables
become cards). Skills: `~/.emilie/skills/<name>/SKILL.md` or `.emilie/skills/` in a project.

**A new setting**: add a `Key` to `emilie/config_cmds.py` (it appears under *Advanced* and in `/config`), or one
`F(...)` line in `emilie/desktop/schema.py` to place it in a section. Field types: `toggle`, `select`, `segmented`,
`number`, `text`, `password`, `textarea`, or `custom:<name>` with a component in `SettingsPanels.tsx` (`CUSTOM`).

**A new kind of thing in the conversation**: emit it from the worker (`emit("item", item={"kind": "...", ...})` or
`self.add_item(...)`), then render that `kind` in `ItemView` in `Transcript.tsx`. New events: handle the event
name in `onEvent()` in `store.ts`.

**A new API call**: add a function to `ROUTES` at the end of `hub.py`; call it with `get()` / `post()` from `api.ts`.

**Colours and fonts**: the tokens at the top of `styles.css` (`--bg-*`, `--text-*`, `--accent`, …); Tailwind uses
them as `bg-bg-100`, `text-text-300`, `border-border-300`, `bg-accent`, …

## Keyboard

Enter send · Shift+Enter new line · Esc stop · Shift+Tab ask → trust → plan · `/` commands · `@` files · ↑ last
message · Ctrl+N new session · Ctrl+K search · Ctrl+, settings · Ctrl+B sidebar · Ctrl+J terminal ·
Ctrl+Shift+E files · Alt+←/→ back/forward · Ctrl+= / Ctrl+- zoom.

## Not in the app (terminal only)

`/mouse`, `/scroll`, `/borders` and `/history` change the terminal UI and do nothing here. The video call (Alt+V in
the terminal) is in the `+` menu and uses the same camera window as the terminal.
