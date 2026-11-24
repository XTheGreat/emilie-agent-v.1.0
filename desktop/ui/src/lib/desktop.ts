// The Electron bridge (desktop/electron/preload.cjs). In a plain browser every call has a fallback.
import { post } from "./api";

export interface Bridge {
  isElectron: true;
  platform: string;
  version: string;
  pickFolder(): Promise<string | null>;
  pickFiles(opts?: { images?: boolean; title?: string }): Promise<string[]>;
  pickFile(opts?: { title?: string; filters?: { name: string; extensions: string[] }[] }): Promise<string | null>;
  openExternal(url: string): void;
  openPath(path: string): void;
  showItemInFolder(path: string): void;
  setTitleBar(colors: { color: string; symbolColor: string }): void;
  notify(title: string, body: string): void;
  flash(): void;
  getPathForFile(file: File): string;
  zoom(dir: number): void;
  reload(): void;
  devtools(): void;
  quit(): void;
  minimize(): void;
  maximize(): void;
  close(): void;
  setBusy(busy: boolean): void;
  // the taskbar's right-click menu (older shells may lack these: check before calling)
  setJumpList?(data: { folders: { name: string; path: string }[]; last: { sid: string; cwd: string; title: string } | null }): void;
  takeAction?(): Promise<JumpAction | null>;
  onAction?(cb: (a: JumpAction) => void): () => void;
  ptyCreate?(o: { cwd: string; cols: number; rows: number }): Promise<{ id?: string; shell?: string; error?: string }>;
  ptyWrite?(id: string, data: string): void;
  ptyResize?(id: string, cols: number, rows: number): void;
  ptyKill?(id: string): void;
  onPty?(onData: (id: string, data: string) => void, onExit: (id: string, code: number) => void): () => void;
  onNavButton?(cb: (d: "back" | "forward") => void): () => void;   // the mouse's Back / Forward buttons
}

export type JumpAction =
  | { kind: "new-chat" }
  | { kind: "new-session"; path: string | null }
  | { kind: "open-session"; sid: string | null; cwd: string };

export const bridge: Bridge | null = (window as any).emilieDesktop || null;
export const isElectron = !!bridge;
export const isWindows = (bridge?.platform || navigator.platform || "").toLowerCase().startsWith("win");
/** macOS draws its own traffic lights in the window; everywhere else Emilie draws them (TitleBar.tsx). */
export const isMac = /^(darwin|mac)/.test((bridge?.platform || navigator.platform || "").toLowerCase());

export function openExternal(url: string) {
  if (bridge) bridge.openExternal(url);
  else window.open(url, "_blank", "noopener");
}

export async function openPath(path: string, reveal = false) {
  if (bridge) return reveal ? bridge.showItemInFolder(path) : bridge.openPath(path);
  await post("/api/open", { path, reveal });
}

export function notify(title: string, body: string) {
  if (document.hasFocus()) return;
  if (bridge) {
    bridge.notify(title, body);
    bridge.flash();
    return;
  }
  if ("Notification" in window) {
    if (Notification.permission === "granted") new Notification(title, { body });
    else if (Notification.permission !== "denied") Notification.requestPermission();
  }
}

export function pathOfFile(file: File): string {
  try {
    return bridge?.getPathForFile(file) || (file as any).path || "";
  } catch {
    return "";
  }
}
