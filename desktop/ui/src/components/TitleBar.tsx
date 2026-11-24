// The top bar of the window (draggable). Sizes and colours measured from the Claude Code desktop app:
// 27px high, the sidebar's colour and divider continue into it, back/forward are chevrons, Chat/Code is a segmented switch.
import { useShallow } from "zustand/react/shallow";
import { useEffect, useState } from "react";
import { useStore, currentLive, type PaneKind } from "@/lib/store";
import { get as apiGet, post } from "@/lib/api";
import { bridge, isElectron, isMac, openPath } from "@/lib/desktop";
import { cn } from "@/lib/util";
import { ChatBubble, ChevD, ChevL, ChevR, CodeBrackets, DiffBox, Dots, FolderSm, GlobeSm, ListIcon, MenuLines, Prompt, SidebarToggle } from "./icons";
import { Menu, MenuContent, MenuItem, MenuSep, MenuTrigger, Tip } from "./ui";

export const TITLEBAR_H = 27;

function TBtn({ children, active, disabled, onClick, label, className }: {
  children: React.ReactNode; active?: boolean; disabled?: boolean; onClick?: () => void; label: string; className?: string;
}) {
  return (
    <button aria-label={label} disabled={disabled} onClick={onClick}
      className={cn("no-drag flex h-[22px] w-[23px] shrink-0 items-center justify-center rounded-[5px] text-text-100 transition-colors",
        "hover:bg-hover disabled:text-text-500 disabled:hover:bg-transparent", active && "bg-active", className)}>
      {children}
    </button>
  );
}

export function TitleBar({ sidebarW, envDockable, envOpen }: { sidebarW: number; envDockable: boolean; envOpen: boolean }) {
  const s = useStore(useShallow((st) => ({ back: st.back, envFloat: st.envFloat, fwd: st.fwd, goBack: st.goBack, goForward: st.goForward, home: st.home, navigate: st.navigate, paneTabs: st.paneTabs, setHome: st.setHome, setSetting: st.setSetting, settings: st.settings, view: st.view })));
  const live = useStore((st) => currentLive(st));
  const hasChat = !!live && live.items.length > 0;
  const sidebar = s.settings.desktop_sidebar !== false;
  const chat = s.home.chat;
  const title = live ? live.title || "New session" : s.view.kind === "projects" ? "Projects"
    : s.view.kind === "artifacts" ? "Artifacts" : s.view.kind === "customize" ? "Customize" : "New session";
  const isOpen = (k: string) => s.paneTabs.some((t) => t.key === k);
  // docked: the button shows/hides the panel for good (a setting); otherwise it opens the floating panel
  const toggleEnv = () => envDockable ? s.setSetting("desktop_env_panel", !envOpen) : useStore.setState({ envFloat: !s.envFloat });
  const setMode = (c: boolean) => {
    s.setHome({ chat: c });
    s.navigate({ kind: "home" });
  };

  return (
    <div className="drag relative z-30 flex shrink-0 select-none items-stretch" style={{ height: TITLEBAR_H }}>
      <div className={cn("flex items-center gap-px pl-2 pr-[5px]", sidebar && "border-r border-border-300 bg-bg-200")}
        style={{ width: sidebar ? sidebarW : undefined }}>
        <AppMenu />
        <Tip content={sidebar ? "Close sidebar  Ctrl+B" : "Open sidebar  Ctrl+B"}>
          <TBtn label="Toggle sidebar" onClick={() => s.setSetting("desktop_sidebar", !sidebar)}><SidebarToggle /></TBtn>
        </Tip>
        <Tip content="Back  Alt+←"><TBtn label="Back" disabled={!s.back.length} onClick={s.goBack}><ChevL /></TBtn></Tip>
        <Tip content="Forward  Alt+→"><TBtn label="Forward" disabled={!s.fwd.length} onClick={s.goForward}><ChevR /></TBtn></Tip>
        <div className="flex-1" />
        <div className="no-drag flex h-[21px] items-stretch rounded-md bg-seg">
          <Tip content="Chat (no folder)">
            <button aria-label="Chat" onClick={() => setMode(true)}
              className={cn("flex w-[26px] items-center justify-center rounded-md text-text-100", chat && "bg-active shadow-[inset_0_0_0_1px_#4b4b4b]")}>
              <ChatBubble />
            </button>
          </Tip>
          <Tip content="Code">
            <button aria-label="Code" onClick={() => setMode(false)}
              className={cn("flex w-[28px] items-center justify-center rounded-md text-text-100", !chat && "bg-active shadow-[inset_0_0_0_1px_#4b4b4b]")}>
              <CodeBrackets />
            </button>
          </Tip>
        </div>
      </div>
      {/* once a session has a conversation, a line separates the title bar from it (as in Claude Code) */}
      <div className={cn("flex min-w-0 flex-1 items-center gap-px pl-[19px] pr-[8px]", hasChat && "border-b border-border-300 dark:border-[#353535]")}>
        {/* with panels open the conversation's own panel header carries the title (and its menu): not twice */}
        {live ? (s.paneTabs.length ? null : <SessionTitle />) : <div className="min-w-0 truncate text-[11.5px] text-text-400">{title}</div>}
        <div className="flex-1" />
        {!live && (
          <button onClick={() => useStore.setState({ dialog: { kind: "whatsnew" } })}
            className="no-drag mr-2 rounded px-1 text-[11.5px] text-link hover:underline">What's new</button>
        )}
        {live && (
          <>
            <Tip content={envOpen ? "Hide the environment panel" : "Show the environment panel"}>
              <TBtn label="Environment panel" active={envOpen} onClick={toggleEnv}><ListIcon size={13} /></TBtn>
            </Tip>
            <div className="mx-1 h-[14px] w-px bg-border-400" />
          </>
        )}
        <ZoomBadge />
        <PaneBtn kind="terminal" tip="Terminal  Ctrl+J" active={isOpen("terminal")}><Prompt /></PaneBtn>
        {live && <PaneBtn kind="diff" tip="Changes" active={isOpen("diff")}><DiffBox /></PaneBtn>}
        <PaneBtn kind="browser" tip="Browser" active={isOpen("browser")}><GlobeSm /></PaneBtn>
        <PaneBtn kind="files" tip="Files  Ctrl+Shift+E" active={isOpen("files")}><FolderSm /></PaneBtn>
        {live && <MoreMenu />}
        {isElectron && !isMac && <WindowControls />}
      </div>
    </div>
  );
}

/** The session title with its menu (rename, folder, export, close), like Claude's "title ∨". */
export function SessionTitle() {
  const s = useStore(useShallow((st) => ({ closeSession: st.closeSession, deleteSession: st.deleteSession, send: st.send, sessions: st.sessions })));
  const live = useStore((st) => currentLive(st));
  const [wt, setWt] = useState(false);                       // this session's folder is a git worktree
  const cwd = live?.cwd || "";
  useEffect(() => {
    let dead = false;
    setWt(false);
    if (cwd) apiGet("/api/worktree/info", { cwd }).then((r: any) => { if (!dead) setWt(!!r?.is); }).catch(() => {});
    return () => { dead = true; };
  }, [cwd]);
  if (!live) return null;
  const meta = s.sessions.find((x) => x.id === live.sid);
  const title = live.title || "New session";
  const removeWorktree = async () => {
    const st = useStore.getState();
    if (!(await st.confirm("Remove worktree?", "The folder of this worktree is deleted and this session closes. Its branch is deleted too, unless it holds work that is not merged.", { danger: true, ok: "Remove" }))) return;
    try {
      let r: any = await post("/api/worktree/remove", { cwd });
      if (r.dirty) {
        if (!(await st.confirm("Uncommitted changes", "This worktree has changes that are not committed. Removing it deletes them.", { danger: true, ok: "Remove anyway" }))) return;
        r = await post("/api/worktree/remove", { cwd, force: true });
      }
      st.toast(r.branch_kept ? `Worktree removed. Branch ${r.branch} kept (it has unmerged work).` : "Worktree removed");
    } catch (e: any) {
      st.toast(e.message, "error");
    }
  };
  return (
    <Menu>
      <MenuTrigger asChild>
        <button className="no-drag flex min-w-0 items-center gap-1 rounded-[5px] px-1 py-0.5 text-[11.5px] text-text-100 hover:bg-hover data-[state=open]:bg-hover">
          <span className="truncate">{title}</span><ChevD size={9} strokeWidth={1.8} className="shrink-0 text-text-400" />
        </button>
      </MenuTrigger>
      <MenuContent align="start" className="min-w-[200px]">
        <MenuItem onSelect={() => live.sid && useStore.setState({ dialog: { kind: "rename", id: live.sid, cwd: live.cwd, title } })}>Rename</MenuItem>
        <MenuItem onSelect={() => openPath(live.cwd)}>Open folder</MenuItem>
        <MenuItem onSelect={() => s.send(live.wid, "/export", [], [])}>Export as Markdown</MenuItem>
        <MenuSep />
        {wt && <MenuItem onSelect={removeWorktree}>Remove worktree…</MenuItem>}
        <MenuItem onSelect={() => s.closeSession(live.wid)}>Close session</MenuItem>
        {meta && <MenuItem danger onSelect={() => s.deleteSession(meta)}>Delete</MenuItem>}
      </MenuContent>
    </Menu>
  );
}

function MoreMenu() {
  const s = useStore(useShallow((st) => ({ send: st.send })));
  const live = useStore((st) => currentLive(st));
  if (!live) return null;
  const run = (cmd: string) => s.send(live.wid, cmd, [], []);
  return (
    <Menu>
      <MenuTrigger asChild>
        <button aria-label="More" className="no-drag flex h-[22px] w-[23px] shrink-0 items-center justify-center rounded-[5px] text-text-100 hover:bg-hover data-[state=open]:bg-hover">
          <Dots />
        </button>
      </MenuTrigger>
      <MenuContent align="end" className="min-w-[210px]">
        <MenuItem onSelect={() => run("/compact")}>Compact the conversation</MenuItem>
        <MenuItem onSelect={() => run("/cost")}>Usage and cost</MenuItem>
        <MenuItem onSelect={() => run("/todos")}>Task list</MenuItem>
        <MenuItem onSelect={() => run("/rewind")}>Rewind…</MenuItem>
        <MenuSep />
        <MenuItem onSelect={() => run("/export")}>Export as Markdown</MenuItem>
        <MenuItem onSelect={() => useStore.setState({ settingsOpen: "code" })}>Session settings</MenuItem>
      </MenuContent>
    </Menu>
  );
}

// Chromium's zoom steps (Ctrl+= / Ctrl+- move half a level: 1.2 ^ (n / 2)).
const ZOOM_STEPS = Array.from({ length: 15 }, (_, i) => Math.pow(1.2, (i - 6) / 2));

/** The window's zoom, read from the page itself: a frameless window's outer width is in screen units, the inner
 *  width in CSS pixels, so their ratio is the zoom (snapped to the nearest step to ignore border pixels). */
function useZoom(): number {
  const read = () => {
    const r = window.outerWidth && window.innerWidth ? window.outerWidth / window.innerWidth : 1;
    return ZOOM_STEPS.reduce((best, z) => (Math.abs(z - r) < Math.abs(best - r) ? z : best), 1);
  };
  const [z, setZ] = useState(read);
  useEffect(() => {
    const f = () => setZ(read());
    window.addEventListener("resize", f);
    return () => window.removeEventListener("resize", f);
  }, []);
  return z;
}

/** "110%": only there when the window is zoomed, so sizes never silently differ from Claude Code's. Click: 100%. */
function ZoomBadge() {
  const z = useZoom();
  if (!bridge || Math.abs(z - 1) < 0.01) return null;
  const pct = Math.round(z * 100);
  return (
    <Tip content={`Zoomed to ${pct}%. Click to go back to 100% (Ctrl+0).`}>
      <button onClick={() => bridge!.zoom(0)}
        className="no-drag mr-1 flex h-[20px] items-center rounded-[5px] px-1.5 text-[11px] text-text-300 hover:bg-hover hover:text-text-100">
        {pct}%
      </button>
    </Tip>
  );
}

function PaneBtn({ kind, tip, active, children }: { kind: PaneKind; tip: string; active: boolean; children: React.ReactNode }) {
  const setPane = useStore((s) => s.setPane);
  return (
    <Tip content={tip}>
      <TBtn label={tip} active={active} onClick={() => setPane(kind)}>{children}</TBtn>
    </Tip>
  );
}

function AppMenu() {
  const s = useStore(useShallow((st) => ({ navigate: st.navigate })));
  const openSettings = (sec = "general") => useStore.setState({ settingsOpen: sec });
  return (
    <Menu>
      <MenuTrigger asChild>
        <button aria-label="Menu" className="no-drag flex h-[22px] w-[23px] shrink-0 items-center justify-center rounded-[5px] text-text-100 hover:bg-hover data-[state=open]:bg-hover">
          <MenuLines />
        </button>
      </MenuTrigger>
      <MenuContent className="min-w-[210px]">
        <MenuItem onSelect={() => s.navigate({ kind: "home" })} shortcut="Ctrl+N">New session</MenuItem>
        <MenuItem onSelect={() => useStore.setState({ dialog: { kind: "search" } })} shortcut="Ctrl+K">Search sessions</MenuItem>
        <MenuSep />
        <MenuItem onSelect={() => openSettings()} shortcut="Ctrl+,">Settings</MenuItem>
        <MenuItem onSelect={() => useStore.setState({ dialog: { kind: "shortcuts" } })}>Keyboard shortcuts</MenuItem>
        <MenuSep />
        {bridge && (
          <>
            <MenuItem onSelect={() => bridge!.zoom(1)} shortcut="Ctrl+=">Zoom in</MenuItem>
            <MenuItem onSelect={() => bridge!.zoom(-1)} shortcut="Ctrl+-">Zoom out</MenuItem>
            <MenuItem onSelect={() => bridge!.zoom(0)} shortcut="Ctrl+0">Actual size</MenuItem>
            <MenuSep />
            <MenuItem onSelect={() => bridge!.reload()} shortcut="Ctrl+R">Reload window</MenuItem>
            <MenuItem onSelect={() => bridge!.devtools()} shortcut="F12">Developer tools</MenuItem>
            <MenuSep />
            <MenuItem onSelect={() => bridge!.quit()}>Quit Emilie</MenuItem>
          </>
        )}
        {!bridge && <MenuItem onSelect={() => location.reload()} shortcut="Ctrl+R">Reload</MenuItem>}
      </MenuContent>
    </Menu>
  );
}

/** True while this window is the active one (macOS greys its traffic lights in a background window). */
function useWindowFocused(): boolean {
  const [focused, setFocused] = useState(() => document.hasFocus());
  useEffect(() => {
    const on = () => setFocused(true);
    const off = () => setFocused(false);
    window.addEventListener("focus", on);
    window.addEventListener("blur", off);
    return () => { window.removeEventListener("focus", on); window.removeEventListener("blur", off); };
  }, []);
  return focused;
}

// macOS's colours: fill, its darker rim, and the dark symbol shown while the pointer is over the group
const LIGHTS = [
  { label: "Minimize", fill: "bg-[#febc2e]", hover: "group-hover:bg-[#febc2e]", rim: "#dea123", ink: "#985700", act: "minimize" },
  { label: "Maximize", fill: "bg-[#28c840]", hover: "group-hover:bg-[#28c840]", rim: "#1aab29", ink: "#006500", act: "maximize" },
  { label: "Close", fill: "bg-[#ff5f57]", hover: "group-hover:bg-[#ff5f57]", rim: "#e0443e", ink: "#4c0002", act: "close" },
] as const;

function LightGlyph({ act, ink }: { act: string; ink: string }) {
  return (
    <svg width="8" height="8" viewBox="0 0 8 8" aria-hidden className="opacity-0 transition-opacity group-hover:opacity-100">
      {act === "close" && <path d="M2 2l4 4M6 2L2 6" stroke={ink} strokeWidth="1.2" strokeLinecap="round" />}
      {act === "minimize" && <path d="M1.6 4h4.8" stroke={ink} strokeWidth="1.3" strokeLinecap="round" />}
      {act === "maximize" && <path d="M2 2h2.6L2 4.6zM6 6H3.4L6 3.4z" fill={ink} />}
    </svg>
  );
}

/** The window buttons as macOS draws them: red close, yellow minimize, green maximize, 12px dots 8px apart. Their
 *  symbols appear while the pointer is over the group; in a background window they turn grey until hovered. */
function WindowControls() {
  const focused = useWindowFocused();
  const run = (act: string) => (act === "close" ? bridge?.close() : act === "minimize" ? bridge?.minimize() : bridge?.maximize());
  return (
    <div className="no-drag group ml-3 flex items-center gap-[8px] pr-[2px]" role="group" aria-label="Window">
      {LIGHTS.map((l) => (
        <button key={l.act} aria-label={l.label} title={l.label} onClick={() => run(l.act)}
          style={{ boxShadow: focused ? `inset 0 0 0 0.5px ${l.rim}` : undefined }}
          className={cn("flex h-[12px] w-[12px] items-center justify-center rounded-full outline-none transition-colors",
            "focus-visible:ring-2 focus-visible:ring-accent/60 active:brightness-90",
            focused ? l.fill : cn("bg-[#d1d0cc] dark:bg-[#4a4a4a]", l.hover))}>
          <LightGlyph act={l.act} ink={l.ink} />
        </button>
      ))}
    </div>
  );
}
