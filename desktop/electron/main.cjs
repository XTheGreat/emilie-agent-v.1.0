// Emilie desktop window (Electron main process).
// Starts Emilie's Python server (python -m emilie.desktop), waits for its ready line, then shows its UI in a frameless
// window with the native window buttons drawn over the title bar, like the Claude desktop app.
const { app, BrowserWindow, Menu, Notification, dialog, ipcMain, nativeTheme, powerSaveBlocker, shell } = require("electron");
const { spawn, execFile } = require("child_process");
const crypto = require("crypto");
const fs = require("fs");
const os = require("os");
const path = require("path");
const readline = require("readline");

const IS_WIN = process.platform === "win32";
const DESKTOP = path.resolve(__dirname, "..");
const ROOT = process.env.EMILIE_ROOT || readRootFile() || path.resolve(DESKTOP, "..");   // the folder with the emilie package
const ICON = path.join(DESKTOP, "build", IS_WIN ? "icon.ico" : "icon.png");
const DATA = path.join(os.homedir(), ".emilie", "desktop");
const STATE_FILE = path.join(DATA, "window.json");

let win = null;
let server = null;
let serverUrl = null;
let logTail = [];
let quitting = false;
let quitGen = 0;                         // bumped when a launch reopens Emilie while she was closing
let blocker = null;
const stopping = new Set();              // server shutdowns still running (a reopened Emilie may overlap the last one)
const stoppedOnPurpose = new WeakSet();  // servers we stopped ourselves: their exit is not an error

function readRootFile() {
  try {
    const p = fs.readFileSync(path.join(DESKTOP, "emilie-root.txt"), "utf8").trim();   // written when packaged as an .exe
    return p && fs.existsSync(path.join(p, "emilie")) ? p : null;
  } catch {
    return null;
  }
}

// "dev.emilie.app": the first id ("dev.emilie.desktop") stays tied to Electron's icon in Explorer's cache (a stray Electron.lnk
// claimed it), so Emilie moved to a clean one. EMILIE_APP_ID: a separate taskbar entry for tests.
const APP_ID = process.env.EMILIE_APP_ID || "dev.emilie.app";
app.setName("Emilie");
if (IS_WIN) app.setAppUserModelId(APP_ID);

// ---------------------------------------------------------------- jump list actions (right-click on the taskbar)
// "New Chat", "New Code Session [folder]", "Continue <session>" start Emilie again with a flag; the running window
// receives it (second-instance) and the page acts on it. A cold start keeps it until the page asks (take-action).
let pendingAction = parseAction(process.argv);

function parseAction(argv) {
  // values travel as one token (--new-session=<folder>): Windows/Chromium may reorder a second launch's arguments,
  // so "--flag value" can lose its value; the plain form is still read for hand-typed commands
  const get = (flag) => {
    for (let i = 0; i < argv.length; i++) {
      const a = String(argv[i]);
      if (a.startsWith(flag + "=")) return a.slice(flag.length + 1);
      if (a === flag) {
        const v = argv[i + 1];
        return v && !String(v).startsWith("--") ? String(v) : "";
      }
    }
    return null;
  };
  if (get("--new-chat") !== null) return { kind: "new-chat" };
  const sid = get("--open-session");
  if (sid) return { kind: "open-session", sid, cwd: get("--cwd") || "" };
  const folder = get("--new-session");
  if (folder !== null) return { kind: "new-session", path: folder || null };
  return null;
}

// One Emilie at a time. A second launch hands its arguments to the running one (second-instance) and quits without
// doing anything else: no window, no Python server (see whenReady / before-quit below).
const GOT_LOCK = app.requestSingleInstanceLock();
if (!GOT_LOCK) {
  app.quit();
} else {
  app.on("second-instance", (_e, argv) => launchedAgain(argv));
}

/** Emilie was launched again (Start menu, taskbar, jump list) while this process runs. Closing takes a few seconds
 *  (the Python server shuts its sessions down) and the process keeps the single-instance lock meanwhile, so a click in
 *  that moment used to land here with no window and be swallowed: the user had to click twice. Now it calls the exit
 *  off and opens the window again at once. */
function launchedAgain(argv) {
  const a = parseAction(argv);
  if (quitting || !win) {
    if (quitting) {
      quitting = false;
      quitGen++;                          // the shutdown still running must not end the app when it finishes
    }
    if (a) pendingAction = a;             // the page asks for it once loaded (take-action)
    if (win) {                            // quit from the menu: the window was only hidden, its server is going away
      win.loadFile(path.join(__dirname, "loading.html"), { query: { dark: isDark() ? "1" : "0", warm: savedSettings().desktop_theme === "warm" ? "1" : "0" } });
      win.show();
      win.focus();
      connect();
    } else {
      boot();
    }
    return;
  }
  if (win.isMinimized()) win.restore();
  win.show();
  win.focus();
  if (a) win.webContents.send("action", a);
}

// How Windows starts Emilie again (taskbar pin, jump list): electron.exe + this app's folder, or the packaged exe.
const quoteArg = (a) => (/[\s"]/.test(a) ? `"${String(a).replace(/"/g, '\\"')}"` : String(a));
const baseArgs = () => (app.isPackaged ? [] : [app.getAppPath()]);
const relaunchCommand = () => [process.execPath, ...baseArgs()].map(quoteArg).join(" ");

/** Windows picks a taskbar button's icon and name from the Start Menu shortcut that carries the app's id. Make that
 *  shortcut Emilie's (her icon, name and launch command), and drop a bare "Electron.lnk" claiming the same id: Windows
 *  creates one for notifications, and it put Electron's atom and name on the taskbar. Skipped for test instances. */
function fixStartMenuShortcut() {
  if (!IS_WIN || process.env.EMILIE_APP_ID) return;
  const dir = path.join(process.env.APPDATA || "", "Microsoft", "Windows", "Start Menu", "Programs");
  const want = {
    target: process.execPath, args: baseArgs().map(quoteArg).join(" "), cwd: app.isPackaged ? path.dirname(process.execPath) : app.getAppPath(),
    icon: ICON, iconIndex: 0, appUserModelId: APP_ID, description: "Emilie - coding agent",
  };
  try {
    const mine = path.join(dir, "Emilie.lnk");
    let current = null;
    try { current = shell.readShortcutLink(mine); } catch { /* missing */ }
    if (!current || current.appUserModelId !== APP_ID || current.icon !== ICON || current.args !== want.args || current.target !== want.target) {
      shell.writeShortcutLink(mine, current ? "replace" : "create", want);
    }
    const stray = path.join(dir, "Electron.lnk");
    if (fs.existsSync(stray)) {
      let s = null;
      try { s = shell.readShortcutLink(stray); } catch { /* unreadable */ }
      if (s && s.appUserModelId === APP_ID) fs.unlinkSync(stray);
    }
  } catch (e) {
    logTail.push(`start menu shortcut: ${e.message}\n`);
  }
}

/** The right-click menu of the taskbar button, laid out like Claude's: recent folders under "New Code Session",
 *  then New Chat / New Code Session / Continue "<last session>" under Tasks. Fed by the page (setJumpList). */
function updateJumpList(data) {
  if (!IS_WIN) return;
  const short = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);
  const task = (title, args, description) => ({
    type: "task", title: short(title, 60), description: short(description || title, 120), program: process.execPath,
    args: [...baseArgs(), ...args].map(quoteArg).join(" "), iconPath: ICON, iconIndex: 0,
  });
  const folders = (Array.isArray(data?.folders) ? data.folders : []).filter((f) => f && f.path).slice(0, 5);
  const last = data?.last && data.last.sid ? data.last : null;
  const tasks = [
    task("New Chat", ["--new-chat"], "Start a new chat without a folder"),
    task("New Code Session", ["--new-session"], "Start a new session"),
  ];
  if (last) tasks.push(task(`Continue "${short(String(last.title || "your last session"), 34)}"`,
    [`--open-session=${last.sid}`, `--cwd=${last.cwd || ""}`], "Open your last session again"));
  const list = [];
  if (folders.length) {
    list.push({ type: "custom", name: "New Code Session",
      items: folders.map((f) => task(String(f.name || f.path), [`--new-session=${f.path}`], `New session in ${f.path}`)) });
  }
  list.push({ type: "tasks", items: tasks });
  try {
    const r = app.setJumpList(list);
    if (r && r !== "ok") logTail.push(`jump list: ${r}\n`);
    return r || "ok";
  } catch (e) {
    logTail.push(`jump list: ${e.message}\n`);
    return `error: ${e.message}`;
  }
}

// ---------------------------------------------------------------- the Python side
function findPython() {
  const c = [];
  if (process.env.EMILIE_PYTHON) c.push(process.env.EMILIE_PYTHON);
  if (IS_WIN) {
    c.push(path.join(ROOT, ".venv", "Scripts", "python.exe"));
    c.push(path.join(process.env.LOCALAPPDATA || "", "Emilie", "venv", "Scripts", "python.exe"));
  } else {
    c.push(path.join(ROOT, ".venv", "bin", "python"));
  }
  for (const p of c) if (p && fs.existsSync(p)) return p;
  return IS_WIN ? "python" : "python3";
}

function startServer() {
  return new Promise((resolve, reject) => {
    const py = findPython();
    const token = crypto.randomBytes(24).toString("hex");
    const env = { ...process.env, PYTHONUNBUFFERED: "1", PYTHONIOENCODING: "utf-8",
      PYTHONPATH: ROOT + (process.env.PYTHONPATH ? path.delimiter + process.env.PYTHONPATH : "") };
    delete env.ELECTRON_RUN_AS_NODE;
    let done = false;
    const finish = (err, url) => {
      if (done) return;
      done = true;
      err ? reject(err) : resolve(url);
    };
    let proc;
    try {
      proc = server = spawn(py, ["-X", "utf8", "-m", "emilie.desktop", "--port", "0", "--token", token, "--watch-stdin"],
        { cwd: ROOT, env, windowsHide: true, stdio: ["pipe", "pipe", "pipe"] });
    } catch (e) {
      return finish(new Error(`Could not start Python (${py}): ${e.message}`));
    }
    readline.createInterface({ input: proc.stdout }).on("line", (line) => {
      try {
        const j = JSON.parse(line);
        if (j.ready && j.url) {
          serverUrl = j.url;
          finish(null, j.url);
        }
      } catch {
        logTail.push(line + "\n");
      }
    });
    proc.stderr.on("data", (d) => {
      logTail.push(String(d));
      if (logTail.length > 300) logTail = logTail.slice(-300);
    });
    proc.on("error", (e) => finish(new Error(`Could not start Python (${py}): ${e.message}`)));
    proc.on("exit", (code) => {
      if (!done) return finish(new Error(`Emilie's background process stopped (exit ${code}).\n\nPython: ${py}\n\n${tail()}`));
      if (!quitting && !stoppedOnPurpose.has(proc)) failed(`Emilie's background process stopped unexpectedly (exit ${code}).`, tail());
    });
    setTimeout(() => finish(new Error(`Emilie's background process did not start within 90 seconds.\n\nPython: ${py}\n\n${tail()}`)), 90000);
  });
}

const tail = () => logTail.join("").slice(-4000);

function stopServer() {
  const p = server;
  server = null;
  if (!p || p.exitCode !== null) return Promise.resolve();
  stoppedOnPurpose.add(p);
  const stopped = new Promise((resolve) => {
    const t = setTimeout(() => {                     // it did not finish in time: end the whole process tree
      if (IS_WIN) execFile("taskkill", ["/F", "/T", "/PID", String(p.pid)], () => resolve());
      else { try { p.kill("SIGKILL"); } catch {} resolve(); }
    }, 5000);
    p.once("exit", () => { clearTimeout(t); resolve(); });
    try { p.stdin.end(); } catch {}                 // the server shuts its sessions down when stdin closes
  });
  stopping.add(stopped);
  stopped.finally(() => stopping.delete(stopped));
  return stopped;
}

// ---------------------------------------------------------------- window
function savedSettings() {
  try {
    return JSON.parse(fs.readFileSync(path.join(os.homedir(), ".emilie", "settings.json"), "utf8"));
  } catch {
    return {};
  }
}

function isDark() {
  const t = savedSettings().desktop_theme || "dark";
  return t === "dark" || t === "eveny" || (t === "auto" && nativeTheme.shouldUseDarkColors);
}

function isEveny() {
  return savedSettings().desktop_theme === "eveny";
}

/** The window's colour before the page has painted. */
function themeBg() {
  if (isEveny()) return "#0a0f1c";
  if (isDark()) return "#191919";
  return savedSettings().desktop_theme === "warm" ? "#faf9f5" : "#ffffff";
}

function loadState() {
  try {
    return JSON.parse(fs.readFileSync(STATE_FILE, "utf8"));
  } catch {
    return {};
  }
}

function saveState() {
  if (!win) return;
  try {
    fs.mkdirSync(DATA, { recursive: true });
    const b = win.getNormalBounds();
    fs.writeFileSync(STATE_FILE, JSON.stringify({ ...b, maximized: win.isMaximized() }));
  } catch {}
}

function createWindow() {
  const dark = isDark();
  const bg = themeBg();
  const st = loadState();
  win = new BrowserWindow({
    width: st.width || 1280, height: st.height || 860, x: st.x, y: st.y, minWidth: 760, minHeight: 520,
    show: false, title: "Emilie", icon: ICON, backgroundColor: bg,
    // no titleBarOverlay: on Windows and Linux the page draws its own macOS-style red / yellow / green buttons
    // (TitleBar.tsx, they call minimize / maximize / close below); macOS keeps its native ones
    titleBarStyle: "hidden",
    trafficLightPosition: { x: 14, y: 13 },
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"), contextIsolation: true, nodeIntegration: false, sandbox: true,
      webviewTag: true, spellcheck: false,
    },
  });
  if (IS_WIN) {
    // the taskbar button shows Emilie's icon and name (not Electron's), and "Pin to taskbar" pins Emilie
    win.setAppDetails({ appId: APP_ID, appIconPath: ICON, appIconIndex: 0, relaunchCommand: relaunchCommand(),
      relaunchDisplayName: "Emilie" });
    win.setIcon(ICON);
    updateJumpList(null);                               // Tasks right away; folders arrive once the page has loaded
  }
  if (st.maximized) win.maximize();
  win.once("ready-to-show", () => win.show());
  win.on("close", saveState);
  win.on("closed", () => (win = null));

  // links open in the real browser; the window itself never navigates away from Emilie
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^(https?|mailto):/i.test(url)) shell.openExternal(url);
    return { action: "deny" };
  });
  win.webContents.on("will-navigate", (e, url) => {
    if (serverUrl && url.startsWith(new URL(serverUrl).origin)) return;
    if (url.startsWith("file:")) return;
    e.preventDefault();
    if (/^https?:/i.test(url)) shell.openExternal(url);
  });
  // Emilie opens at 100%, the size it is designed for (and measured against Claude Code at). Chromium would otherwise
  // remember a Ctrl+= for the page's address and open every later window zoomed. Ctrl+= / Ctrl+- still work while
  // the window is open, and the title bar shows the zoom when it is not 100%.
  let zoomReset = false;
  win.webContents.on("did-navigate", (_e, url) => {
    if (zoomReset || !serverUrl || !url.startsWith(new URL(serverUrl).origin)) return;
    zoomReset = true;
    win.webContents.setZoomLevel(0);
  });
  // The mouse's Back/Forward buttons (and Alt+Arrows) must not walk the window's own page history: the first
  // entry is the "Starting Emilie..." page, which never moves on. Once Emilie's page is up its history is emptied
  // (Emilie has its own Back/Forward, which the page binds to those buttons).
  const dropHistory = () => {
    const wc = win && win.webContents;
    if (!wc) return;
    try { wc.navigationHistory ? wc.navigationHistory.clear() : wc.clearHistory(); } catch {}
  };
  win.webContents.on("did-finish-load", () => {
    const u = win && win.webContents.getURL();
    if (serverUrl && u && u.startsWith(new URL(serverUrl).origin)) dropHistory();
  });
  win.on("app-command", (e, cmd) => {
    if (cmd === "browser-backward" || cmd === "browser-forward") {
      e.preventDefault();
      if (win) win.webContents.send("nav-button", cmd === "browser-backward" ? "back" : "forward");
    }
  });
  win.webContents.on("will-attach-webview", (_e, prefs) => {            // the Browser pane: a plain page, no Node
    delete prefs.preload;
    prefs.nodeIntegration = false;
    prefs.contextIsolation = true;
  });
  win.loadFile(path.join(__dirname, "loading.html"), { query: { dark: dark ? "1" : "0", warm: savedSettings().desktop_theme === "warm" ? "1" : "0" } });
}

async function boot() {
  fixStartMenuShortcut();                 // before the window exists, so its taskbar button is Emilie's
  createWindow();
  await connect();
}

/** Start Emilie's Python server and show its UI in the window (which shows the loading page meanwhile). */
async function connect() {
  try {
    const url = await startServer();
    if (win) win.loadURL(url + "&shell=electron");
  } catch (e) {
    failed("Emilie could not start.", e.message);
  }
}

async function failed(title, detail) {
  if (!win) return;
  const r = await dialog.showMessageBox(win, {
    type: "error", title: "Emilie", message: title, detail: String(detail || "").slice(-3500),
    buttons: ["Try again", "Open the log", "Quit"], defaultId: 0, cancelId: 2, noLink: true,
  });
  if (r.response === 0) {
    logTail = [];
    await stopServer();
    win.loadFile(path.join(__dirname, "loading.html"), { query: { dark: isDark() ? "1" : "0", warm: savedSettings().desktop_theme === "warm" ? "1" : "0" } });
    try {
      const url = await startServer();
      win.loadURL(url + "&shell=electron");
    } catch (e) {
      failed("Emilie could not start.", e.message);
    }
  } else if (r.response === 1) {
    shell.openPath(path.join(DATA, "desktop.log"));
    failed(title, detail);
  } else {
    app.quit();
  }
}

// ---------------------------------------------------------------- menu (keyboard shortcuts; the bar itself is hidden)
Menu.setApplicationMenu(Menu.buildFromTemplate([
  { label: "Emilie", submenu: [{ role: "quit" }] },
  { role: "editMenu" },
  {
    label: "View", submenu: [
      // F12, not Ctrl+Shift+I: that opens the model and effort picker in the page, as in Claude
      { role: "reload" }, { role: "forceReload" }, { role: "toggleDevTools", accelerator: "F12" }, { type: "separator" },
      { role: "resetZoom" }, { role: "zoomIn" }, { role: "zoomIn", accelerator: "CommandOrControl+=", visible: false }, { role: "zoomOut" },
      { type: "separator" }, { role: "togglefullscreen" },
    ],
  },
  { role: "windowMenu" },
]));

// ---------------------------------------------------------------- calls from the page (preload.cjs)
const owner = (e) => win && e.sender === win.webContents;

ipcMain.handle("pick-folder", async (e) => {
  if (!owner(e)) return null;
  const r = await dialog.showOpenDialog(win, { title: "Choose a folder", properties: ["openDirectory", "createDirectory"] });
  return r.canceled ? null : r.filePaths[0];
});
ipcMain.handle("pick-files", async (e, o = {}) => {
  if (!owner(e)) return [];
  const r = await dialog.showOpenDialog(win, { title: o.title || "Add files", properties: ["openFile", "multiSelections"] });
  return r.canceled ? [] : r.filePaths;
});
ipcMain.handle("pick-file", async (e, o = {}) => {
  if (!owner(e)) return null;
  const r = await dialog.showOpenDialog(win, { title: o.title || "Choose a file", properties: ["openFile"], filters: o.filters });
  return r.canceled ? null : r.filePaths[0];
});
ipcMain.on("open-external", (e, url) => {
  if (owner(e) && /^(https?|mailto):/i.test(String(url))) shell.openExternal(String(url));
});
ipcMain.on("open-path", (e, p) => owner(e) && shell.openPath(String(p)));
ipcMain.on("show-item", (e, p) => owner(e) && shell.showItemInFolder(String(p)));
ipcMain.on("titlebar", (e, c) => {
  if (!owner(e) || !c) return;
  try {
    win.setBackgroundColor(c.color);                // the caption buttons are the page's own now: nothing to recolour
  } catch {}
});
ipcMain.on("notify", (e, m) => {
  if (!owner(e) || !Notification.isSupported() || win.isFocused()) return;
  const n = new Notification({ title: String(m?.title || "Emilie"), body: String(m?.body || ""), icon: ICON, silent: false });
  n.on("click", () => { if (win) { win.show(); win.focus(); } });
  n.show();
});
ipcMain.on("flash", (e) => owner(e) && !win.isFocused() && win.flashFrame(true));
ipcMain.handle("jumplist", (e, data) => (owner(e) ? updateJumpList(data) : "not allowed"));
ipcMain.handle("take-action", (e) => {                   // the page is ready: the jump list action Emilie started with
  if (!owner(e)) return null;
  const a = pendingAction;
  pendingAction = null;
  return a;
});
ipcMain.on("zoom", (e, d) => {
  if (!owner(e)) return;
  const wc = win.webContents;
  wc.setZoomLevel(d === 0 ? 0 : Math.max(-3, Math.min(4, wc.getZoomLevel() + (d > 0 ? 0.5 : -0.5))));
});
ipcMain.on("reload", (e) => owner(e) && win.webContents.reload());
ipcMain.on("devtools", (e) => owner(e) && win.webContents.toggleDevTools());
ipcMain.on("quit", (e) => owner(e) && app.quit());
ipcMain.on("win", (e, what) => {
  if (!owner(e)) return;
  if (what === "minimize") win.minimize();
  else if (what === "maximize") win.isMaximized() ? win.unmaximize() : win.maximize();
  else if (what === "close") win.close();
});
ipcMain.on("busy", (e, busy) => {                    // keep the computer awake while Emilie works
  if (!owner(e)) return;
  if (busy && blocker === null) blocker = powerSaveBlocker.start("prevent-app-suspension");
  if (!busy && blocker !== null) {
    powerSaveBlocker.stop(blocker);
    blocker = null;
  }
});

// ---------------------------------------------------------------- real terminals (pseudo-consoles)
// The Terminal panel is a real PowerShell/bash: node-pty runs it here, xterm.js draws it in the page. If the native
// module cannot load (pty-unavailable), the page falls back to its simple command box.
let ptyMod = null;
let ptyErr = "";
try { ptyMod = require("@lydell/node-pty"); } catch (e) { ptyErr = String((e && e.message) || e); }
const ptys = new Map();                  // id -> pty
let ptyN = 0;

// The prompt (PowerShell): "user@computer  folder  branch" on one line, "❯" on the next, in colour. It replaces only the
// plain default prompt, so one from your own profile (oh-my-posh, starship...) is left alone.
const PS_PROMPT = [
  "$__d = (Get-Command prompt -ErrorAction SilentlyContinue).ScriptBlock.ToString()",
  "if ($__d -like '*PS $(*') {",
  "  function global:prompt {",
  "    $e = [char]27",
  "    $b = ''",
  "    try { $b = (git rev-parse --abbrev-ref HEAD 2>$null) } catch {}",
  "    $l = \"$e[1;35m$env:USERNAME@$env:COMPUTERNAME$e[0m $e[1;36m$($executionContext.SessionState.Path.CurrentLocation)$e[0m\"",
  "    if ($b) { $l += \" $e[1;32m$b$e[0m\" }",
  "    \"$l`n$e[1;34m\u276f$e[0m \"",
  "  }",
  "}",
].join("\n");

function shellFor() {
  if (!IS_WIN) return { file: process.env.SHELL || "/bin/bash", args: [] };
  const pwsh = ["ProgramFiles", "ProgramW6432"].map((k) => process.env[k] && path.join(process.env[k], "PowerShell", "7", "pwsh.exe"))
    .find((p) => p && fs.existsSync(p));
  const enc = Buffer.from(PS_PROMPT, "utf16le").toString("base64");
  return { file: pwsh || "powershell.exe", args: ["-NoLogo", "-NoExit", "-EncodedCommand", enc] };
}

function killAllPtys() {
  for (const p of ptys.values()) { try { p.kill(); } catch {} }
  ptys.clear();
}

ipcMain.handle("pty-create", (e, o = {}) => {
  if (!owner(e)) return { error: "not allowed" };
  if (!ptyMod) return { error: "unavailable: " + ptyErr };
  try {
    const cwd = o.cwd && fs.existsSync(String(o.cwd)) ? String(o.cwd) : os.homedir();
    const sh = shellFor();
    const p = ptyMod.spawn(sh.file, sh.args, {
      name: "xterm-256color", cols: Math.max(2, Math.min(500, o.cols | 0 || 80)), rows: Math.max(1, Math.min(200, o.rows | 0 || 24)),
      cwd, env: { ...process.env, TERM_PROGRAM: "Emilie", COLORTERM: process.env.COLORTERM || "truecolor" },
    });
    const id = "pty" + ++ptyN;
    ptys.set(id, p);
    const send = (ch, ...a) => { if (win && !win.isDestroyed()) win.webContents.send(ch, id, ...a); };
    p.onData((d) => send("pty-data", d));
    p.onExit((x) => { ptys.delete(id); send("pty-exit", x.exitCode); });
    return { id, shell: path.basename(sh.file) };
  } catch (err) {
    return { error: String((err && err.message) || err) };
  }
});
ipcMain.on("pty-write", (e, id, data) => { if (owner(e)) { try { ptys.get(id)?.write(String(data)); } catch {} } });
ipcMain.on("pty-resize", (e, id, cols, rows) => {
  if (owner(e)) { try { ptys.get(id)?.resize(Math.max(2, Math.min(500, cols | 0)), Math.max(1, Math.min(200, rows | 0))); } catch {} }
});
ipcMain.on("pty-kill", (e, id) => {
  if (!owner(e)) return;
  try { ptys.get(id)?.kill(); } catch {}
  ptys.delete(id);
});

// ---------------------------------------------------------------- life cycle
app.whenReady().then(() => {
  if (GOT_LOCK) boot();                 // a second launch only passes its click on: it must not start a server
});
app.on("window-all-closed", () => app.quit());
app.on("activate", () => {
  if (GOT_LOCK && (quitting || !win)) launchedAgain([]);
});
app.on("before-quit", (e) => {
  if (!GOT_LOCK || quitting) return;
  quitting = true;
  e.preventDefault();
  killAllPtys();                        // no PowerShell left running behind a closed window
  saveState();
  if (win) win.hide();                  // gone at once; the server shuts down behind the scenes
  const gen = quitGen;
  stopServer();
  // exit once every server is down, unless a new launch reopened Emilie meanwhile (launchedAgain)
  Promise.allSettled([...stopping]).then(() => {
    if (gen === quitGen) app.exit(0);
  });
});
