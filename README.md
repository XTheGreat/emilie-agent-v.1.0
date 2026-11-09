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

## Linux

It also runs on Linux: `pip install -e .` then `emilie`.
