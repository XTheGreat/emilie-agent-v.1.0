// The only bridge between the page and the desktop: a few named calls, no Node access for the page.
const { contextBridge, ipcRenderer, webUtils } = require("electron");

contextBridge.exposeInMainWorld("emilieDesktop", {
  isElectron: true,
  platform: process.platform,
  version: process.versions.electron,
  pickFolder: () => ipcRenderer.invoke("pick-folder"),
  pickFiles: (o) => ipcRenderer.invoke("pick-files", o || {}),
  pickFile: (o) => ipcRenderer.invoke("pick-file", o || {}),
  openExternal: (url) => ipcRenderer.send("open-external", url),
  openPath: (p) => ipcRenderer.send("open-path", p),
  showItemInFolder: (p) => ipcRenderer.send("show-item", p),
  setTitleBar: (c) => ipcRenderer.send("titlebar", c),
  notify: (title, body) => ipcRenderer.send("notify", { title, body }),
  flash: () => ipcRenderer.send("flash"),
  getPathForFile: (file) => webUtils.getPathForFile(file),
  zoom: (d) => ipcRenderer.send("zoom", d),
  reload: () => ipcRenderer.send("reload"),
  devtools: () => ipcRenderer.send("devtools"),
  quit: () => ipcRenderer.send("quit"),
  minimize: () => ipcRenderer.send("win", "minimize"),
  maximize: () => ipcRenderer.send("win", "maximize"),
  close: () => ipcRenderer.send("win", "close"),
  setBusy: (busy) => ipcRenderer.send("busy", !!busy),
  // the taskbar's right-click menu: recent folders + New Chat / New Code Session / Continue
  setJumpList: (data) => ipcRenderer.invoke("jumplist", data),
  takeAction: () => ipcRenderer.invoke("take-action"),
  onNavButton: (cb) => {                // the mouse's Back / Forward buttons
    const f = (_e, d) => cb(d);
    ipcRenderer.on("nav-button", f);
    return () => ipcRenderer.removeListener("nav-button", f);
  },
  // real terminals (node-pty in the main process; xterm.js in the page)
  ptyCreate: (o) => ipcRenderer.invoke("pty-create", o || {}),
  ptyWrite: (id, data) => ipcRenderer.send("pty-write", id, data),
  ptyResize: (id, cols, rows) => ipcRenderer.send("pty-resize", id, cols, rows),
  ptyKill: (id) => ipcRenderer.send("pty-kill", id),
  onPty: (onData, onExit) => {
    const d = (_e, id, data) => onData(id, data);
    const x = (_e, id, code) => onExit(id, code);
    ipcRenderer.on("pty-data", d);
    ipcRenderer.on("pty-exit", x);
    return () => { ipcRenderer.removeListener("pty-data", d); ipcRenderer.removeListener("pty-exit", x); };
  },
  onAction: (cb) => {
    const f = (_e, a) => cb(a);
    ipcRenderer.on("action", f);
    return () => ipcRenderer.removeListener("action", f);
  },
});
