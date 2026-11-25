// Left sidebar, measured from the Claude Code desktop app: 220px wide, 25px rows, 12px text, white icons,
// folder headers in small grey type, long titles fading out instead of "…", the account row at the bottom.
import { useShallow } from "zustand/react/shallow";
import { useMemo, useState } from "react";
import { useStore, useLiveOnScreen, folderName } from "@/lib/store";
import type { SessionMeta } from "@/lib/types";
import { bridge, openExternal, openPath } from "@/lib/desktop";
import { cn, prettyModel } from "@/lib/util";
import {
  Archive, ArtifactsIcon, Blocks, Book, ChevD, ChevR, CircleHelp, Clock, Cpu, CustomizeIcon, Dots, FileText, FolderOpen, Gauge,
  Globe, Info, Keyboard, LaptopOff, Loader, LogOut, MessageCircle, Pencil, Pin, PinOff, Plug, PlusSm, ProjectsIcon,
  ScrollText, SearchSm, Settings, Trash,
} from "./icons";
import { Menu, MenuContent, MenuItem, MenuLabel, MenuSep, MenuSub, MenuSubContent, MenuSubTrigger, MenuTrigger, Tip } from "./ui";

export const SIDEBAR_W = 220;

export function Sidebar({ width }: { width: number }) {
  const s = useStore(useShallow((st) => ({ home: st.home, navigate: st.navigate, opening: st.opening, pickFolder: st.pickFolder, sessions: st.sessions, setHome: st.setHome, setSetting: st.setSetting, settings: st.settings, state: st.state, view: st.view })));
  const live = useLiveOnScreen();                  // not the whole session: the sidebar must not redraw on every word of a reply
  const collapsed: string[] = Array.isArray(s.settings.desktop_collapsed) ? s.settings.desktop_collapsed : [];
  const [more, setMore] = useState<Record<string, boolean>>({});

  const rawPins = s.settings.desktop_pinned;
  const pins: string[] = Array.isArray(rawPins) ? rawPins : [];
  const groups = useMemo(() => {
    type Group = { key: string; name: string; cwd: string; chat: boolean; pinned?: boolean; items: SessionMeta[] };
    const m = new Map<string, Group>();
    // pinned sessions sit in their own group at the top (as in Claude Code), newest pin first
    const pinned: Group = { key: "__pinned__", name: "Pinned", cwd: "", chat: false, pinned: true, items: [] };
    for (const x of s.sessions) {
      if (pins.includes(x.id)) {
        pinned.items.push(x);
        continue;
      }
      const key = x.chat ? "__chat__" : (x.cwd || "").toLowerCase();
      if (!m.has(key)) m.set(key, { key, name: x.chat ? "No folder" : folderName(x.cwd), cwd: x.cwd, chat: !!x.chat, items: [] });
      m.get(key)!.items.push(x);
    }
    pinned.items.sort((a, b) => pins.indexOf(a.id) - pins.indexOf(b.id));
    const arr = [...m.values()];
    if (s.home.chat) arr.sort((a, b) => Number(b.chat) - Number(a.chat));
    return pinned.items.length ? [pinned, ...arr] : arr;
  }, [s.sessions, s.home.chat, pins.join("|")]);

  const toggle = (key: string) => {
    const next = collapsed.includes(key) ? collapsed.filter((k) => k !== key) : [...collapsed, key];
    s.setSetting("desktop_collapsed", next);
  };
  const newIn = (cwd: string, chat: boolean) => {
    s.setHome({ cwd: chat ? s.home.cwd : cwd, chat });
    s.navigate({ kind: "home" });
  };
  // Skills, Connectors and Scheduled tasks have their own page (as in Claude Code), not a Settings section.
  const customize = (tab: "plugins" | "skills" | "connectors" | "scheduled") => s.navigate({ kind: "customize", tab });

  return (
    <aside className={cn("flex h-full shrink-0 flex-col overflow-hidden bg-bg-200 text-[11.5px]", width > 0 && "border-r border-border-300")} style={{ width }}>
      <nav className="flex flex-col gap-px px-[7px] pt-[6px]">
        <NavRow icon={<PlusSm />} active={s.view.kind === "home"} onClick={() => s.navigate({ kind: "home" })}>New</NavRow>
        <NavRow icon={<SearchSm />} onClick={() => useStore.setState({ dialog: { kind: "search" } })}>Search</NavRow>
        <NavRow icon={<ProjectsIcon />} active={s.view.kind === "projects"} onClick={() => s.navigate({ kind: "projects" })}
          extra={
            <Tip content="Open a folder">
              <span role="button" className="rounded p-0.5 text-text-400 opacity-0 hover:text-text-100 group-hover:opacity-100"
                onClick={async (e) => {
                  e.stopPropagation();
                  const p = await s.pickFolder("Open a project folder");
                  if (p) newIn(p, false);
                }}><PlusSm size={12} /></span>
            </Tip>
          }>
          Projects
          <span className="ml-1.5 inline-flex h-[14px] items-center rounded-[4px] bg-bg-400 px-[5px] text-[9.5px] font-semibold text-[#a3a19f]">Beta</span>
        </NavRow>
        <NavRow icon={<ArtifactsIcon />} active={s.view.kind === "artifacts"} onClick={() => s.navigate({ kind: "artifacts" })}>Artifacts</NavRow>
        <NavRow icon={<CustomizeIcon />} active={s.view.kind === "customize"} onClick={() => customize("skills")}>Customize</NavRow>
        <Menu>
          <MenuTrigger asChild>
            <div><NavRow icon={<Dots />}>More</NavRow></div>
          </MenuTrigger>
          <MenuContent side="right" align="start" className="min-w-[210px]">
            <MenuItem icon={<Book />} onSelect={() => customize("skills")}>Skills</MenuItem>
            <MenuItem icon={<Plug />} onSelect={() => customize("connectors")}>Connectors (MCP)</MenuItem>
            <MenuItem icon={<Clock />} onSelect={() => customize("scheduled")}>Scheduled tasks</MenuItem>
            <MenuSep />
            <MenuItem icon={<Keyboard />} onSelect={() => useStore.setState({ dialog: { kind: "shortcuts" } })}>Keyboard shortcuts</MenuItem>
            <MenuItem icon={<FolderOpen />} onSelect={() => s.state && openPath(s.state.data_dir)}>Open Emilie's data folder</MenuItem>
            <MenuItem icon={<ScrollText />} onSelect={() => s.state && openPath(s.state.log)}>Open the app log</MenuItem>
            <MenuItem icon={<Info />} onSelect={() => openExternal("https://github.com/XTheGreat/emilie-agent-v.1.0")}>Emilie on GitHub</MenuItem>
          </MenuContent>
        </Menu>
      </nav>

      <div className="mt-[14px] min-h-0 flex-1 overflow-y-auto px-[7px] pb-2">
        {groups.length === 0 && <div className="px-2 py-4 text-[11.5px] text-text-500">No sessions yet.</div>}
        {groups.map((g, gi) => {
          const isCollapsed = collapsed.includes(g.key);
          const showAll = more[g.key];
          const list = showAll ? g.items : g.items.slice(0, 6);
          return (
            <div key={g.key} className={cn(gi > 0 && "mt-[14px]")}>
              <div className="group flex h-[24px] items-center rounded-[6px] pl-2 pr-0.5">
                <button className="flex min-w-0 items-center gap-1 text-left text-[10.5px] font-medium text-text-400 hover:text-text-200" onClick={() => toggle(g.key)}>
                  <span className="truncate">{g.name}</span>
                  {isCollapsed ? <ChevR size={10} strokeWidth={1.6} /> : <ChevD size={10} strokeWidth={1.6} />}
                </button>
                <div className="flex-1" />
                {!g.pinned && (
                  <Tip content={g.chat ? "New chat" : `New session in ${g.name}`}>
                    <button aria-label="New session here" onClick={() => newIn(g.cwd, g.chat)}
                      className="flex h-[18px] w-[18px] items-center justify-center rounded text-text-400 opacity-0 hover:bg-hover hover:text-text-100 group-hover:opacity-100">
                      <PlusSm size={11} />
                    </button>
                  </Tip>
                )}
                {!g.chat && !g.pinned && (
                  <Menu>
                    <MenuTrigger asChild>
                      <button aria-label="Folder options"
                        className="flex h-[18px] w-[18px] items-center justify-center rounded text-text-400 opacity-0 hover:bg-hover hover:text-text-100 group-hover:opacity-100 data-[state=open]:opacity-100">
                        <Dots size={11} />
                      </button>
                    </MenuTrigger>
                    <MenuContent align="start">
                      <MenuItem icon={<PlusSm />} onSelect={() => newIn(g.cwd, false)}>New session here</MenuItem>
                      <MenuItem icon={<FolderOpen />} onSelect={() => openPath(g.cwd)}>Open in File Explorer</MenuItem>
                    </MenuContent>
                  </Menu>
                )}
              </div>
              {!isCollapsed && (
                <div className="flex flex-col gap-px">
                  {list.map((x) => (
                    <SessionRow key={x.id} meta={x} active={!!live && live.sid === x.id} opening={s.opening === x.id} />
                  ))}
                  {g.items.length > 6 && (
                    <button onClick={() => setMore({ ...more, [g.key]: !showAll })}
                      className="h-[25px] rounded-[6px] px-2 text-left text-[11px] text-text-400 hover:bg-hover hover:text-text-100">
                      {showAll ? "Show less" : `Show ${g.items.length - 6} more`}
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <AccountRow />
    </aside>
  );
}

function NavRow({ icon, children, onClick, active, extra }: {
  icon: React.ReactNode; children: React.ReactNode; onClick?: () => void; active?: boolean; extra?: React.ReactNode;
}) {
  return (
    <div role="button" tabIndex={0} onClick={onClick} onKeyDown={(e) => e.key === "Enter" && onClick?.()}
      className={cn("group flex h-[25px] cursor-default items-center gap-2 rounded-[6px] px-2 text-text-100 transition-colors",
        active ? "bg-active" : "hover:bg-hover")}>
      <span className="flex w-[13px] shrink-0 justify-center">{icon}</span>
      <span className="flex min-w-0 flex-1 items-center whitespace-nowrap">{children}</span>
      {extra}
    </div>
  );
}

function SessionRow({ meta, active, opening }: { meta: SessionMeta; active: boolean; opening: boolean }) {
  const s = useStore.getState();
  // what the row shows of its open session (a few fields, so the row of a session that is writing does not redraw per word)
  const live = useStore(useShallow((st) => {
    const l = Object.values(st.lives).find((x) => x.sid === meta.id);
    return l ? { wid: l.wid, busy: l.busy, request: !!l.request, title: l.title, closed: l.closed } : null;
  }));
  const sidebarW = useStore((st) => Number(st.settings.desktop_sidebar_width) || 220);
  const busy = live ? live.busy : meta.busy;
  const waiting = live ? !!live.request : meta.waiting;
  const title = (live?.title || meta.title || "New session").replace(/^\(empty\)$/, "New session");
  const rawPins = useStore((st) => st.settings.desktop_pinned);
  const pins: string[] = Array.isArray(rawPins) ? rawPins : [];
  const isPinned = pins.includes(meta.id);
  return (
    <div role="button" tabIndex={0}
      onClick={() => s.openSession(meta)}
      onKeyDown={(e) => e.key === "Enter" && s.openSession(meta)}
      className={cn("group relative flex h-[25px] cursor-default items-center gap-1.5 rounded-[6px] pl-2 pr-1 text-text-100 transition-colors",
        active ? "bg-active" : "hover:bg-hover")}>
      <span className="fade-r min-w-0 flex-1">{title}</span>
      {(busy || opening) && !waiting && <Loader size={11} className="shrink-0 animate-spin text-text-400" />}
      {waiting && <span className="h-[7px] w-[7px] shrink-0 rounded-full bg-accent" title="Waiting for you" />}
      {meta.chat && !busy && !waiting && <LaptopOff size={12} className={cn("shrink-0 text-text-400", active ? "hidden" : "group-hover:hidden")} />}
      <Menu>
        <MenuTrigger asChild>
          {/* like Claude Code: always shown on the open session, on the others when hovered */}
          <button aria-label="Session options" onClick={(e) => e.stopPropagation()}
            className={cn("h-[18px] w-[18px] shrink-0 items-center justify-center rounded text-text-300 hover:bg-hover hover:text-text-000 data-[state=open]:flex",
              active ? "flex" : "hidden group-hover:flex")}>
            <Dots size={11} />
          </button>
        </MenuTrigger>
        <MenuContent align="end" side="bottom" sideOffset={4} alignOffset={4} style={{ minWidth: 156, width: 156, maxWidth: 156 }} onClick={(e) => e.stopPropagation()}>
          <MenuItem icon={isPinned ? <PinOff /> : <Pin />}
            onSelect={() => s.setSetting("desktop_pinned", isPinned ? pins.filter((x) => x !== meta.id) : [meta.id, ...pins])}>
            {isPinned ? "Unpin" : "Pin"}
          </MenuItem>
          <MenuItem icon={<Pencil />} onSelect={() => useStore.setState({ dialog: { kind: "rename", id: meta.id, cwd: meta.cwd, title } })}>Rename</MenuItem>
          {!meta.chat && <MenuItem icon={<FolderOpen />} onSelect={() => openPath(meta.cwd)}>Open folder</MenuItem>}
          {live && !live.closed && <MenuItem icon={<Archive />} onSelect={() => s.closeSession(live.wid)}>Close session</MenuItem>}
          <MenuSep />
          <MenuItem icon={<Trash />} danger onSelect={() => s.deleteSession(meta)}>Delete</MenuItem>
        </MenuContent>
      </Menu>
    </div>
  );
}

const REPO = "https://github.com/XTheGreat/emilie-agent-v.1.0";

/** The profile row at the bottom, as in Claude Code: avatar, name and plan (here: the provider), a chevron at the far
 *  right and no extra buttons. Its menu mirrors Claude's, with Emilie's own destinations. */
function AccountRow() {
  const s = useStore(useShallow((st) => ({ navigate: st.navigate, settings: st.settings, state: st.state })));
  const st = s.state;
  const name = s.settings.desktop_name || st?.user || "You";
  const provider = (st?.provider?.label || "No provider").split(" (")[0];
  const model = String(s.settings.model || st?.provider?.model || "");
  const open = (sec: string) => useStore.setState({ settingsOpen: sec });
  return (
    <div className="flex h-[34px] shrink-0 items-center border-t border-border-400 px-[7px]">
      <Menu>
        <MenuTrigger asChild>
          <button className="flex h-[26px] w-full min-w-0 items-center gap-[8px] rounded-[6px] pl-[5px] pr-[7px] text-left transition-colors hover:bg-hover aria-expanded:bg-hover">
            <span className="flex h-[15px] w-[15px] shrink-0 items-center justify-center rounded-full bg-[#10a122] text-[8.5px] font-semibold text-[#e6f4e2]">
              {String(name).trim().charAt(0).toUpperCase() || "E"}
            </span>
            <span className="min-w-0 flex-1 truncate text-[12px] font-medium text-text-100">
              {name}<span className="text-[11px] font-normal text-text-400"> - {provider}</span>
            </span>
            <ChevD size={10} strokeWidth={1.6} className="shrink-0 text-text-400" />
          </button>
        </MenuTrigger>
        <MenuContent side="top" align="start" sideOffset={6} className="w-[var(--radix-dropdown-menu-trigger-width)] min-w-[206px]">
          <MenuLabel>{provider}{model ? ` · ${prettyModel(model)}` : ""}</MenuLabel>
          <MenuItem icon={<Settings />} shortcut="Ctrl+," onSelect={() => open("general")}>Settings</MenuItem>
          <MenuItem icon={<Gauge />} onSelect={() => open("usage")}>Usage</MenuItem>
          <MenuItem icon={<Globe />} onSelect={() => open("general")}>Language</MenuItem>
          <MenuItem icon={<CircleHelp />} onSelect={() => openExternal(`${REPO}#readme`)}>Get help</MenuItem>
          <MenuItem icon={<MessageCircle />} onSelect={() => openExternal(`${REPO}/issues/new`)}>Send feedback</MenuItem>
          <MenuSub>
            <MenuSubTrigger icon={<Info />}>Learn more</MenuSubTrigger>
            <MenuSubContent className="min-w-[190px]">
              <MenuItem icon={<Keyboard />} onSelect={() => useStore.setState({ dialog: { kind: "shortcuts" } })}>Keyboard shortcuts</MenuItem>
              <MenuItem icon={<Info />} onSelect={() => open("desktop")}>About Emilie</MenuItem>
              <MenuItem icon={<Book />} onSelect={() => openExternal(REPO)}>Emilie on GitHub</MenuItem>
            </MenuSubContent>
          </MenuSub>
          <MenuSep />
          <MenuItem icon={<Cpu />} onSelect={() => open("model")}>Provider and model</MenuItem>
          <MenuItem icon={<Blocks />} onSelect={() => s.navigate({ kind: "customize", tab: "skills" })}>Skills and connectors</MenuItem>
          <MenuItem icon={<FileText />} onSelect={() => useStore.setState({ dialog: { kind: "whatsnew" } })}>View changelog</MenuItem>
          <MenuSep />
          <MenuItem icon={<LogOut />} onSelect={() => (bridge ? bridge.quit() : window.close())}>Quit Emilie</MenuItem>
        </MenuContent>
      </Menu>
    </div>
  );
}
