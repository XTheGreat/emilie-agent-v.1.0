import { useShallow } from "zustand/react/shallow";
import { useCallback, useEffect, useRef, useState } from "react";
import { TooltipPrimitive } from "./ui";
import { useStore, currentLive, queueEvent, useLiveInfo } from "@/lib/store";
import { connectEvents } from "@/lib/api";
import { bridge, type JumpAction } from "@/lib/desktop";
import { openPicker } from "@/lib/slash";
import { focusComposer } from "./Composer";
import { cn } from "@/lib/util";
import { TitleBar } from "./TitleBar";
import { Sidebar } from "./Sidebar";
import { Home } from "./Home";
import { SessionView } from "./SessionView";
import { Dialogs } from "./Dialogs";
import { Settings } from "./Settings";
import { Onboarding } from "./Onboarding";
import { Pane } from "./Panes";
import { EnvPanel } from "./EnvPanel";
import { applyCodeStyle } from "@/lib/codeThemes";
import { ArtifactsPage, CustomizePage, ProjectsPage } from "./Pages";
import { EmilieIcon } from "./EmilieIcon";
import { Alert, CircleCheck, X } from "./icons";
import { Button, Spinner } from "./ui";

export function App() {
  const boot = useStore((s) => s.boot);
  const bootError = useStore((s) => s.bootError);
  useEffect(() => {
    const s = useStore.getState();
    s.init();
    return connectEvents(
      queueEvent,                                    // applied once per frame, not one redraw per message
      (again) => {
        useStore.setState({ connected: true });
        if (again) {
          const st = useStore.getState();
          st.refreshState();
          st.refreshSessions();
          useStore.setState({ lives: Object.fromEntries(Object.entries(st.lives).map(([k, l]) => [k, { ...l, loaded: false }])) });
          const cur = currentLive(useStore.getState());
          if (cur) useStore.getState().ensureLoaded(cur.wid);
        }
      },
      () => useStore.setState({ connected: false }),
    );
  }, []);
  useTheme();
  useShortcuts();

  if (boot === "loading") return <Splash />;
  if (boot === "error") return <BootError message={bootError} />;
  return (
    <TooltipPrimitive.Provider delayDuration={450}>
      <Shell />
    </TooltipPrimitive.Provider>
  );
}

/** The taskbar's right-click menu (Windows jump list), as in Claude: recent folders under "New Code Session", then New
 *  Chat / New Code Session / Continue "<last session>". Keeps it current and acts on the item that was clicked. */
function useJumpList() {
  const folders = useStore((s) => s.folders);
  const sessions = useStore((s) => s.sessions);
  useEffect(() => {
    if (!bridge?.setJumpList) return;
    const t = setTimeout(() => {
      const last = sessions.find((x) => x.title) || sessions[0];
      bridge!.setJumpList!({
        folders: folders.filter((f) => f.exists).slice(0, 5).map((f) => ({ name: f.name, path: f.path })),
        last: last ? { sid: last.id, cwd: last.cwd, title: String(last.title || "your last session").replace(/^\(empty\)$/, "New session") } : null,
      });
    }, 800);
    return () => clearTimeout(t);
  }, [folders, sessions]);
  useEffect(() => {
    if (!bridge?.onAction) return;
    const run = async (a: JumpAction) => {
      const s = useStore.getState();
      if (a.kind === "new-chat") {
        s.setHome({ chat: true });
        s.navigate({ kind: "home" });
      } else if (a.kind === "new-session") {
        s.setHome(a.path ? { cwd: a.path, chat: false } : { chat: false });
        s.navigate({ kind: "home" });
      } else if (a.kind === "open-session" && a.sid) {
        await s.refreshSessions().catch(() => {});
        const meta = useStore.getState().sessions.find((x) => x.id === a.sid);
        await s.openSession(meta || { id: a.sid, cwd: a.cwd, title: "", updated: 0, created: 0, n: 0, model: "" });
      }
      setTimeout(focusComposer, 120);
    };
    bridge.takeAction?.().then((a) => a && run(a)).catch(() => {});     // Emilie was started from the jump list
    return bridge.onAction(run);                                         // Emilie was already open
  }, []);
}

function Shell() {
  const s = useStore(useShallow((st) => ({ connected: st.connected, envFloat: st.envFloat, home: st.home, paneMax: st.paneMax, paneTabs: st.paneTabs, scratch: st.scratch, setSetting: st.setSetting, settings: st.settings, settingsOpen: st.settingsOpen, state: st.state, view: st.view })));
  // only what the frame needs: the conversation reads the session itself (LiveSession), so a reply being written
  // redraws the conversation, not the title bar, sidebar and panels around it
  const live = useLiveInfo();
  useJumpList();
  const sidebar = s.settings.desktop_sidebar !== false;
  const [sidebarW, setSidebarW] = useState<number>(Number(s.settings.desktop_sidebar_width) || 220);
  useEffect(() => {
    if (s.settings.desktop_sidebar_width) setSidebarW(Number(s.settings.desktop_sidebar_width));
  }, [s.settings.desktop_sidebar_width]);
  const hasKey = s.state?.has_key;

  // Like Claude Code: the Environment panel sits on the right of a session, but closes as soon as a file (or any viewer
  // tab) is open; the title-bar button then opens it as a floating panel over the conversation. The same happens when
  // the window is too narrow to dock it. The conversation never gets narrower than MAIN_MIN.
  const winW = useWindowWidth();
  const paneOpen = s.paneTabs.length > 0;
  const sideW = sidebar ? sidebarW : 0;
  const inSession = s.view.kind === "session" && !!live.wid;
  const envDockable = inSession && !paneOpen && winW - sideW - ENV_W >= MAIN_MIN;
  const envShown = envDockable && s.settings.desktop_env_panel !== false;
  const envFloat = inSession && !envDockable && s.envFloat && !(s.paneMax && paneOpen);
  useEffect(() => {
    if (envDockable && useStore.getState().envFloat) useStore.setState({ envFloat: false });
  }, [envDockable]);

  return (
    <div className="flex h-full flex-col bg-bg-100 text-text-100">
      <TitleBar sidebarW={sidebarW} envDockable={envDockable} envOpen={envDockable ? envShown : envFloat} />
      {!s.connected && <div className="bg-warn-soft py-1 text-center text-[11.5px] text-warn">Reconnecting to Emilie's background process…</div>}
      <div className="flex min-h-0 flex-1">
        {sidebar && <Sidebar width={sidebarW} />}
        {sidebar && <Resizer value={sidebarW} min={180} max={420} onChange={setSidebarW} onDone={(w) => s.setSetting("desktop_sidebar_width", w)}
          closeBelow={130} onClose={() => s.setSetting("desktop_sidebar", false)} />}
        <Pane cwd={live.cwd || (s.home.chat ? s.scratch : s.home.cwd) || s.state?.home || ""} chatTitle={(inSession && live.title) || "Conversation"}
          chat={(
            <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-bg-100">
              {s.view.kind === "session" && live.wid ? <LiveSession wid={live.wid} envFloat={envFloat} />
                : s.view.kind === "projects" ? <ProjectsPage />
                  : s.view.kind === "artifacts" ? <ArtifactsPage />
                    : s.view.kind === "customize" ? <CustomizePage tab={s.view.tab} />
                      : <Home />}
            </main>
          )} />
        {envShown && live.wid && <DockedEnvPanel wid={live.wid} />}
      </div>
      {s.settingsOpen && <Settings />}
      <Dialogs />
      <Toasts />
      {hasKey === false && <Onboarding />}
    </div>
  );
}

/** The session on screen: read here, so its changes (every piece of a reply) redraw the conversation only. */
function LiveSession({ wid, envFloat }: { wid: string; envFloat: boolean }) {
  const live = useStore((st) => st.lives[wid]);
  return live ? <SessionView live={live} envFloat={envFloat} /> : null;
}

/** The Environment panel docked on the right (it skips the redraws that do not change what it shows: see EnvPanel). */
function DockedEnvPanel({ wid }: { wid: string }) {
  const live = useStore((st) => st.lives[wid]);
  const onCommand = useCallback((cmd: string) => { useStore.getState().send(wid, cmd, [], []); }, [wid]);
  return live ? <EnvPanel live={live} onCommand={onCommand} /> : null;
}

const MAIN_MIN = 380;      // the conversation column never gets narrower than this
const ENV_W = 240;         // the Environment panel
const PANE_MIN = 200;      // the viewer (files, terminal, diff, browser)

function useWindowWidth() {
  const [w, setW] = useState(window.innerWidth);
  useEffect(() => {
    const f = () => setW(window.innerWidth);
    window.addEventListener("resize", f);
    return () => window.removeEventListener("resize", f);
  }, []);
  return w;
}

export function Resizer({ value, min, max, onChange, onDone, side = "right", closeBelow, onClose }: {
  value: number; min: number; max: number; onChange: (v: number) => void; onDone: (v: number) => void; side?: "right" | "left";
  closeBelow?: number; onClose?: () => void;     // dragged narrower than this it looks shut; letting go there really closes it
}) {
  const start = useRef<{ x: number; w: number } | null>(null);
  return (
    <div
      className="group relative z-20 w-0 cursor-col-resize"
      onMouseDown={(e) => {
        e.preventDefault();
        start.current = { x: e.clientX, w: value };
        let last = value, closing = false;
        const move = (ev: MouseEvent) => {
          if (ev.buttons === 0) { up(); return; }           // the release was missed (a page under the pointer)
          const d = ev.clientX - start.current!.x;
          const raw = start.current!.w + (side === "right" ? d : -d);
          closing = !!closeBelow && !!onClose && raw < closeBelow;
          if (closing) { onChange(0); return; }              // it looks shut; dragging back wider before letting go opens it again
          last = Math.max(min, Math.min(max, raw));
          onChange(last);
        };
        const up = () => {
          window.removeEventListener("mousemove", move);
          window.removeEventListener("mouseup", up);
          window.removeEventListener("blur", up);
          document.body.style.cursor = "";
          document.body.classList.remove("dragging");
          if (closing) { onChange(start.current!.w); onClose!(); return; }     // let go while shut: now it really closes
          onDone(last);
        };
        document.body.style.cursor = "col-resize";
        window.addEventListener("mousemove", move);
        window.addEventListener("mouseup", up);
        window.addEventListener("blur", up);
        document.body.classList.add("dragging");
      }}
    >
      <div className="absolute inset-y-0 -left-[3px] w-[5px] transition-colors group-hover:bg-accent/40" />
    </div>
  );
}

function Toasts() {
  const toasts = useStore((s) => s.toasts);
  if (!toasts.length) return null;
  return (
    <div className="pointer-events-none fixed bottom-24 left-1/2 z-[120] flex -translate-x-1/2 flex-col items-center gap-2">
      {toasts.map((t) => (
        // neutral like Claude Code's: white text on the menu colour; only the small icon says "error" or "done"
        <div key={t.id} className="pointer-events-auto flex max-w-[520px] items-center gap-2 rounded-[9px] border border-border-400 bg-menu px-3 py-[7px] text-[11.5px] leading-[1.4] text-text-100 shadow-menu animate-pop">
          {t.kind === "error" ? <Alert size={14} className="shrink-0 text-danger" /> : t.kind === "ok" ? <CircleCheck size={14} className="shrink-0 text-ok" /> : null}
          <span className="min-w-0 break-words">{t.text}</span>
          <button className="ml-1 shrink-0 text-text-400 hover:text-text-100"
            onClick={() => useStore.setState({ toasts: useStore.getState().toasts.filter((x) => x.id !== t.id) })}><X size={14} /></button>
        </div>
      ))}
    </div>
  );
}

function Splash() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 bg-bg-100">
      <Spinner size={22} />
    </div>
  );
}

function BootError({ message }: { message: string }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 bg-bg-100 px-8 text-center">
      <EmilieIcon size={72} mode="image" />
      <div className="text-[15px] font-semibold text-text-100">Emilie could not start</div>
      <div className="max-w-[560px] text-[12px] text-text-400 selectable">{message}</div>
      <Button onClick={() => location.reload()}>Try again</Button>
    </div>
  );
}

function useTheme() {
  const theme = useStore((s) => s.settings.desktop_theme || "dark");
  const codeLight = useStore((s) => s.settings.desktop_code_light as string | undefined);
  const codeDark = useStore((s) => s.settings.desktop_code_dark as string | undefined);
  const codeFont = useStore((s) => s.settings.desktop_code_font as string | undefined);
  const codePx = useStore((s) => s.settings.desktop_code_size as number | undefined);
  const accent = useStore((s) => s.settings.desktop_accent || "sakura");   // "clay" (Claude orange) is gone: pink
  const font = useStore((s) => s.settings.desktop_font || "default");
  useEffect(() => {
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      const eveny = theme === "eveny";                                      // a deep navy, almost black: a dark theme with its own colours
      const dark = eveny || theme === "dark" || (theme === "auto" && mq.matches);
      const root = document.documentElement;
      root.classList.toggle("dark", dark);
      root.classList.toggle("light", !dark);
      root.classList.toggle("eveny", eveny);
      applyCodeStyle(dark, dark ? codeDark : codeLight, codeFont, codePx);
      root.classList.toggle("accent-lavender", accent === "lavender");     // Emilie pink is the base accent
      for (const c of ["chat-sans", "chat-system", "chat-dyslexic"]) root.classList.remove(c);
      if (font !== "default") root.classList.add("chat-" + font);
      try {
        localStorage.setItem("emilie-theme", theme);
      } catch { /* private mode */ }
      bridge?.setTitleBar({ color: eveny ? "#0a0f1c" : dark ? "#191919" : "#faf9f5", symbolColor: dark ? "#c2c0b6" : "#3d3d3a" });
    };
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [theme, accent, font, codeLight, codeDark, codeFont, codePx]);
}

function useShortcuts() {
  useEffect(() => {
    // the mouse's Back / Forward buttons are Emilie's own Back / Forward (never the window's page history)
    const mouse = (e: MouseEvent) => {
      if (e.button !== 3 && e.button !== 4) return;
      e.preventDefault();
      if (e.type === "mouseup") { const s = useStore.getState(); e.button === 3 ? s.goBack() : s.goForward(); }
    };
    window.addEventListener("mouseup", mouse);
    window.addEventListener("mousedown", mouse);
    const off = bridge?.onNavButton?.((d) => { const s = useStore.getState(); d === "back" ? s.goBack() : s.goForward(); });
    const h = (e: KeyboardEvent) => {
      const s = useStore.getState();
      const mod = e.ctrlKey || e.metaKey;
      const k = e.key.toLowerCase();
      if (mod && k === "n" && !e.shiftKey) { e.preventDefault(); s.navigate({ kind: "home" }); }
      else if (mod && k === "k") { e.preventDefault(); useStore.setState({ dialog: { kind: "search" } }); }
      else if (mod && e.key === ",") { e.preventDefault(); useStore.setState({ settingsOpen: s.settingsOpen ? null : "general" }); }
      else if (mod && k === "b") { e.preventDefault(); s.setSetting("desktop_sidebar", s.settings.desktop_sidebar === false); }
      else if (mod && k === "j") { e.preventDefault(); s.setPane("terminal"); }
      else if (mod && e.shiftKey && k === "e") { e.preventDefault(); s.setPane("files"); }
      // the model picker with its effort levels, as Ctrl+Shift+I in Claude (the developer tools moved to F12)
      else if (mod && e.shiftKey && k === "i" && !e.repeat) { e.preventDefault(); openPicker("model-toggle"); }
      else if (e.altKey && e.key === "ArrowLeft") { e.preventDefault(); s.goBack(); }
      else if (e.altKey && e.key === "ArrowRight") { e.preventDefault(); s.goForward(); }
      else if (e.altKey && !mod && !e.shiftKey && e.code === "KeyV") {
        // video call on/off, as Alt+V in the terminal (e.code: the V key whatever the keyboard layout)
        const live = currentLive(s);
        const home = s.view.kind === "home" && !s.dialog && !s.settingsOpen;
        if (!(live && !live.closed) && !home) return;
        e.preventDefault();
        if (e.repeat) return;                                // holding the keys must not flip it on and off
        if (live && !live.closed) s.setCall(live.wid, !live.status.call);
        else s.startWith("call");                            // New session page: start the session, then the call
      }
      else if (e.key === "Escape" && !s.dialog && !s.settingsOpen) {
        const live = currentLive(s);
        const t = e.target as HTMLElement;
        if (live?.busy && !live.request && !(t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA"))) s.stop(live.wid);
      }
    };
    window.addEventListener("keydown", h);
    return () => {
      window.removeEventListener("keydown", h);
      window.removeEventListener("mouseup", mouse);
      window.removeEventListener("mousedown", mouse);
      off?.();
    };
  }, []);
}
