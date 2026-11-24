// The Search palette, laid out like Claude Code's (Ctrl+K): a type row (All, Artifacts, Sessions, Code, Projects,
// Scheduled), "Recents" when nothing is typed, an "Actions" section and the key hints along the bottom.
// Measured from Claude Code dark: 510px wide, top at 25% of the window, #303030 panel, #4f4f4f highlight, the
// window dimmed by half behind it.
import { useShallow } from "zustand/react/shallow";
import { forwardRef, useEffect, useMemo, useRef, useState, type ButtonHTMLAttributes, type ReactNode } from "react";
import { Dialog as D } from "radix-ui";
import { useStore, folderName, type SearchTab } from "@/lib/store";
import { get as apiGet } from "@/lib/api";
import { openPath } from "@/lib/desktop";
import type { SessionMeta } from "@/lib/types";
import { basename, cn } from "@/lib/util";
import * as I from "./icons";
import { insertIntoComposer } from "./Composer";
import { Menu, MenuContent, MenuItem, MenuLabel, MenuSep, MenuTrigger } from "./ui";

type Kind = "chats" | "code" | "artifacts" | "projects" | "scheduled";
interface Hit {
  key: string;
  kind: Kind;
  title: string;
  sub?: string;          // dim text after the title (folder, session)
  hay: string;           // what the query is matched against
  updated: number;       // seconds
  folder?: string;       // for the folder filter
  icon: ReactNode;
  open: () => void;
  menu?: () => ReactNode;
}
interface Artifact { name: string; path: string; title: string; session: string; updated: number; exists: boolean }

const TABS: [SearchTab, string][] = [
  ["all", "All"], ["artifacts", "Artifacts"], ["chats", "Sessions"], ["code", "Code"], ["projects", "Projects"], ["scheduled", "Scheduled"],
];
const WHEN: [number, string][] = [[0, "Any time"], [1, "Today"], [7, "Past week"], [30, "Past month"]];

export function SearchPalette({ onClose, tab: tab0, q: q0 }: { onClose: () => void; tab?: SearchTab; q?: string }) {
  const s = useStore(useShallow((st) => ({ folders: st.folders, navigate: st.navigate, openFile: st.openFile, openSession: st.openSession, sessions: st.sessions, setHome: st.setHome, setSetting: st.setSetting, settings: st.settings })));
  const [q, setQ] = useState(q0 || "");
  const [tab, setTab] = useState<SearchTab>(tab0 || "all");
  const [idx, setIdx] = useState(0);
  const [arts, setArts] = useState<Artifact[]>([]);
  const [sched, setSched] = useState<string[]>([]);
  const [days, setDays] = useState(0);
  const [inFolder, setInFolder] = useState<string | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [menuFor, setMenuFor] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLDivElement>(null);

  useEffect(() => {
    apiGet("/api/artifacts").then((r) => setArts(r.files || [])).catch(() => {});
    apiGet("/api/schedule").then((r) => setSched(r.supported ? (r.rows || []).filter((x: string) => !x.startsWith("no scheduled")) : [])).catch(() => {});
  }, []);

  const go = (fn: () => void) => { onClose(); fn(); };
  // A menu (Filters, a row's actions) hands the keyboard back to the search box when it closes, not to its button.
  const backToInput = (e: Event) => { e.preventDefault(); input.current?.focus(); };
  const newSession = (text = "") => go(() => {
    s.navigate({ kind: "home" });
    if (text) setTimeout(() => insertIntoComposer(text), 80);
  });

  const all = useMemo<Hit[]>(() => {
    const pins: string[] = Array.isArray(s.settings.desktop_pinned) ? s.settings.desktop_pinned : [];
    const out: Hit[] = [];
    const sessionMenu = (m: SessionMeta) => () => {
      const pinned = pins.includes(m.id);
      return (
        <>
          <MenuItem icon={<I.CornerDownLeft />} onSelect={() => go(() => s.openSession(m))}>Open</MenuItem>
          <MenuItem icon={pinned ? <I.PinOff /> : <I.Pin />}
            onSelect={() => s.setSetting("desktop_pinned", pinned ? pins.filter((x) => x !== m.id) : [m.id, ...pins])}>{pinned ? "Unpin" : "Pin"}</MenuItem>
          <MenuItem icon={<I.Pencil />} onSelect={() => useStore.setState({ dialog: { kind: "rename", id: m.id, cwd: m.cwd, title: m.title || "New session" } })}>Rename</MenuItem>
          {!m.chat && <MenuItem icon={<I.FolderOpen />} onSelect={() => openPath(m.cwd)}>Open folder</MenuItem>}
        </>
      );
    };
    for (const m of s.sessions) {
      const chat = !!m.chat || !m.cwd;
      out.push({
        key: "s:" + m.id, kind: chat ? "chats" : "code", title: m.title || "New session",
        sub: chat ? undefined : folderName(m.cwd), hay: `${m.title} ${chat ? "" : m.cwd}`, updated: m.updated || 0,
        folder: chat ? undefined : m.cwd,
        icon: chat ? <I.MessageCircle /> : <I.CodeXml />, open: () => go(() => s.openSession(m)), menu: sessionMenu(m),
      });
    }
    for (const a of arts) {
      const meta = s.sessions.find((x) => x.id === a.session);
      const inFolder = meta && !meta.chat ? meta.cwd : undefined;
      out.push({
        key: "a:" + a.path, kind: "artifacts", title: a.name, sub: inFolder ? folderName(inFolder) : undefined, hay: `${a.name} ${a.path}`,
        updated: a.updated || 0, folder: inFolder, icon: <I.Files />,
        open: () => go(() => s.openFile(a.path)),
        menu: () => (
          <>
            <MenuItem icon={<I.CornerDownLeft />} onSelect={() => go(() => s.openFile(a.path))}>Open</MenuItem>
            {meta && <MenuItem icon={<I.MessageCircle />} onSelect={() => go(() => s.openSession(meta))}>Open the session</MenuItem>}
            <MenuItem icon={<I.External />} onSelect={() => openPath(a.path)}>Open with the default app</MenuItem>
            <MenuItem icon={<I.FolderOpen />} onSelect={() => openPath(a.path, true)}>Show in folder</MenuItem>
          </>
        ),
      });
    }
    const projects = new Map<string, { path: string; name: string; updated: number; exists: boolean }>();
    for (const f of s.folders) projects.set(f.path.toLowerCase(), { path: f.path, name: f.name, updated: 0, exists: f.exists });
    for (const m of s.sessions) {
      if (m.chat || !m.cwd) continue;
      const k = m.cwd.toLowerCase();
      const p = projects.get(k) || { path: m.cwd, name: basename(m.cwd), updated: 0, exists: true };
      p.updated = Math.max(p.updated, m.updated || 0);
      projects.set(k, p);
    }
    for (const p of projects.values()) {
      if (!p.exists) continue;
      const start = () => go(() => { s.setHome({ cwd: p.path, chat: false }); s.navigate({ kind: "home" }); });
      out.push({
        key: "p:" + p.path, kind: "projects", title: p.name, hay: `${p.name} ${p.path}`, updated: p.updated, folder: p.path,
        icon: <I.FolderIcon className="text-[var(--folder-tint)]" />, open: start,
        menu: () => (
          <>
            <MenuItem icon={<I.PlusSm />} onSelect={start}>New session here</MenuItem>
            <MenuItem icon={<I.FolderOpen />} onSelect={() => openPath(p.path)}>Open in File Explorer</MenuItem>
          </>
        ),
      });
    }
    for (const r of sched) {
      const name = r.split("  ·  ")[0];
      out.push({
        key: "t:" + name, kind: "scheduled", title: name, sub: r.slice(name.length).replace(/^\s*·\s*/, "") || undefined,
        hay: r, updated: 0, icon: <I.Clock />, open: () => go(() => s.navigate({ kind: "customize", tab: "scheduled" })),
      });
    }
    return out;
  }, [s.sessions, s.folders, s.settings.desktop_pinned, arts, sched]);

  const ql = q.trim().toLowerCase();
  const rows = useMemo(() => {
    const since = days ? Date.now() / 1000 - days * 86400 : 0;
    const fl = inFolder?.toLowerCase();
    let r = all.filter((h) => (tab === "all" || h.kind === tab)
      && (!since || h.updated >= since)
      && (!fl || (h.folder || "").toLowerCase().startsWith(fl)));
    if (ql) {
      const words = ql.split(/\s+/);
      const score = (h: Hit) => {
        const t = h.title.toLowerCase();
        return t.startsWith(ql) ? 3 : t.includes(ql) ? 2 : 1;
      };
      r = r.filter((h) => { const hay = h.hay.toLowerCase(); return words.every((w) => hay.includes(w)); })
        .sort((a, b) => score(b) - score(a) || b.updated - a.updated);
    } else {
      // Recents: newest first; scheduled tasks have no date and only show on their own tab.
      r = r.filter((h) => tab !== "all" || h.kind !== "scheduled").sort((a, b) => b.updated - a.updated);
    }
    return r.slice(0, ql || tab !== "all" ? 60 : 8);
  }, [all, tab, ql, days, inFolder]);

  // The highlight walks the results, then the actions under them.
  const actions: { key: string; label: string; icon: ReactNode; run: () => void }[] = [
    { key: "new", label: q.trim() ? `New session: “${q.trim()}”` : "New session", icon: <I.MessageCirclePlus />, run: () => newSession(q.trim()) },
  ];
  const count = rows.length + actions.length;
  useEffect(() => setIdx(0), [ql, tab, days, inFolder]);
  useEffect(() => {
    list.current?.querySelector(`[data-i="${idx}"]`)?.scrollIntoView({ block: "nearest" });
  }, [idx]);
  const run = (i: number) => (i < rows.length ? rows[i].open() : actions[i - rows.length]?.run());
  const moveTab = (d: number) => {
    const i = TABS.findIndex(([k]) => k === tab);
    setTab(TABS[(i + d + TABS.length) % TABS.length][0]);
  };

  const onKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    const el = e.currentTarget;
    if (e.key === "ArrowDown") { e.preventDefault(); setIdx((i) => Math.min(count - 1, i + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setIdx((i) => Math.max(0, i - 1)); }
    else if (e.key === "ArrowLeft" && (!q || el.selectionStart === 0) && el.selectionEnd === el.selectionStart) { e.preventDefault(); moveTab(-1); }
    else if (e.key === "ArrowRight" && (!q || el.selectionStart === q.length)) { e.preventDefault(); moveTab(1); }
    else if (e.key === "Enter" && e.altKey) { e.preventDefault(); if (rows[idx]?.menu) setMenuFor(rows[idx].key); }
    else if (e.key === "Enter") { e.preventDefault(); run(idx); }
    else if (e.key === "Tab") { e.preventDefault(); newSession(q.trim()); }
    else if (e.key === "/" && !q) { e.preventDefault(); setFiltersOpen(true); }
  };

  const filterLabel = [days ? WHEN.find(([d]) => d === days)?.[1] : null, inFolder ? basename(inFolder) : null].filter(Boolean).join(" · ");
  const label = ql ? (tab === "all" ? "Results" : TABS.find(([k]) => k === tab)![1]) : "Recents";

  return (
    <D.Root open onOpenChange={(o) => !o && onClose()}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-[80] bg-[var(--pal-dim)] animate-fade-in" />
        <D.Content aria-describedby={undefined}
          onOpenAutoFocus={(e) => { e.preventDefault(); input.current?.focus(); }}
          onEscapeKeyDown={(e) => { if (menuFor || filtersOpen) e.preventDefault(); }}
          className="fixed left-1/2 top-[25vh] z-[81] flex max-h-[70vh] w-[min(510px,calc(100vw-32px))] -translate-x-1/2 flex-col overflow-hidden rounded-[12px] border border-[var(--pal-border)] bg-[var(--pal-bg)] text-text-100 shadow-menu outline-none animate-pop">
          <D.Title className="sr-only">Search</D.Title>
          <div className="mt-[12px] flex h-[26px] shrink-0 items-center pl-[18px] pr-[9px]">
            <input ref={input} value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={onKey} placeholder="Search" spellCheck={false}
              className="h-full min-w-0 flex-1 bg-transparent text-[12px] text-text-100 outline-none placeholder:text-text-500 selectable" />
            <button aria-label="Close" onClick={onClose}
              className="flex h-[22px] w-[22px] items-center justify-center rounded-[5px] text-text-100 transition-colors hover:bg-hover">
              <I.X size={14} strokeWidth={1.8} />
            </button>
          </div>
          <div className="mt-[6px] flex shrink-0 items-center px-[18px]">
            {TABS.map(([k, l]) => (
              <button key={k} onClick={() => { setTab(k); input.current?.focus(); }}
                className={cn("h-[20px] rounded-[6px] px-[7px] text-[11.5px] text-text-100 transition-colors",
                  tab === k ? "bg-[var(--pal-hi)]" : "hover:bg-hover")}>
                {l}
              </button>
            ))}
            {filterLabel && (
              <button onClick={() => { setDays(0); setInFolder(null); input.current?.focus(); }} title="Clear the filters"
                className="ml-auto flex h-[20px] items-center gap-[4px] rounded-[6px] bg-accent-soft px-[7px] text-[11px] text-accent">
                {filterLabel}<I.X size={10} strokeWidth={2} />
              </button>
            )}
          </div>
          <div className="mt-[12px] h-px shrink-0 bg-[var(--pal-sep)]" />
          <div ref={list} className="min-h-0 flex-1 overflow-y-auto px-[9px] pb-[18px] pt-[14px]">
            <SectionLabel>{label}</SectionLabel>
            {!rows.length && (
              <div className="px-[9px] pb-[6px] pt-[2px] text-[11.5px] text-text-500">
                {ql ? "Nothing matches." : tab === "scheduled" ? "No scheduled tasks." : "Nothing here yet."}
              </div>
            )}
            {rows.map((h, i) => (
              <Row key={h.key} i={i} on={i === idx} icon={h.icon} onHover={() => setIdx(i)} onClick={h.open}
                right={i === idx && (
                  <>
                    {h.menu && (
                      <Menu open={menuFor === h.key} onOpenChange={(o) => setMenuFor(o ? h.key : null)}>
                        <MenuTrigger asChild>
                          <button aria-label="Actions" onClick={(e) => e.stopPropagation()}
                            className="flex h-[18px] w-[20px] items-center justify-center rounded-[4px] text-text-200 hover:bg-hover hover:text-text-100">
                            <I.Dots size={12} />
                          </button>
                        </MenuTrigger>
                        <MenuContent align="end" onClick={(e) => e.stopPropagation()} onCloseAutoFocus={backToInput}>
                          <MenuLabel>{h.title}</MenuLabel>
                          {h.menu()}
                        </MenuContent>
                      </Menu>
                    )}
                    <I.CornerDownLeft size={12} className="ml-[4px] text-text-300" />
                  </>
                )}>
                <span className={cn("truncate", i === idx ? "text-text-100" : "text-[var(--pal-row)]")}>{h.title}</span>
                {h.sub && <span className="min-w-0 shrink truncate whitespace-pre text-text-500"> · {h.sub}</span>}
              </Row>
            ))}
            <SectionLabel className="mt-[12px]">Actions</SectionLabel>
            {actions.map((a, j) => {
              const i = rows.length + j;
              return (
                <Row key={a.key} i={i} on={i === idx} icon={a.icon} onHover={() => setIdx(i)} onClick={a.run}
                  right={i === idx && <I.CornerDownLeft size={12} className="text-text-300" />}>
                  <span className={cn("truncate", i === idx ? "text-text-100" : "text-[var(--pal-row)]")}>{a.label}</span>
                </Row>
              );
            })}
          </div>
          <div className="flex h-[33px] shrink-0 items-center gap-[14px] border-t border-[var(--pal-sep)] px-[18px] text-[10.5px] text-text-400">
            <Hint label="Close" keys={["Esc"]} onClick={onClose} />
            <Hint label="Change type" keys={["←", "→"]} onClick={() => moveTab(1)} />
            <Menu open={filtersOpen} onOpenChange={setFiltersOpen}>
              <MenuTrigger asChild>
                <Hint label="Filters" keys={["/"]} />
              </MenuTrigger>
              <MenuContent side="top" align="start" className="max-h-[320px] overflow-y-auto" onCloseAutoFocus={backToInput}>
                <MenuLabel>Updated</MenuLabel>
                {WHEN.map(([d, l]) => <MenuItem key={d} checked={days === d} onSelect={() => setDays(d)}>{l}</MenuItem>)}
                <MenuSep />
                <MenuLabel>Folder</MenuLabel>
                <MenuItem checked={!inFolder} onSelect={() => setInFolder(null)}>Any folder</MenuItem>
                {s.folders.filter((f) => f.exists).slice(0, 12).map((f) => (
                  <MenuItem key={f.path} checked={inFolder === f.path} onSelect={() => setInFolder(f.path)}>{f.name}</MenuItem>
                ))}
              </MenuContent>
            </Menu>
            <Hint label="Actions" keys={["Alt", "↵"]} onClick={() => rows[idx]?.menu && setMenuFor(rows[idx].key)} />
            <div className="flex-1" />
            <Hint label="Compose" keys={["Tab"]} onClick={() => newSession(q.trim())} />
          </div>
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}

function SectionLabel({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("mb-[5px] px-[9px] text-[10.5px] leading-[14px] text-text-400", className)}>{children}</div>;
}

function Row({ i, on, icon, onHover, onClick, right, children }: {
  i: number; on: boolean; icon: ReactNode; onHover: () => void; onClick: () => void; right?: ReactNode; children: ReactNode;
}) {
  return (
    <div data-i={i} role="option" aria-selected={on} onMouseMove={onHover} onClick={onClick}
      className={cn("flex h-[27px] cursor-default items-center gap-[7px] rounded-[7px] pl-[9px] pr-[8px] text-[11.5px]",
        on && "bg-[var(--pal-hi)]")}>
      <span className={cn("flex w-[14px] shrink-0 justify-center [&_svg]:size-[13px]", on ? "text-text-200" : "text-text-400")}>{icon}</span>
      <span className="flex min-w-0 flex-1 items-center">{children}</span>
      {right && <span className="flex shrink-0 items-center">{right}</span>}
    </div>
  );
}

const Hint = forwardRef<HTMLButtonElement, { label: string; keys: string[] } & ButtonHTMLAttributes<HTMLButtonElement>>(
  function Hint({ label, keys, ...rest }, ref) {
    return (
      <button ref={ref} type="button" tabIndex={-1} {...rest} className="flex items-center gap-[5px] outline-none hover:text-text-200">
        {label}
        <span className="flex gap-[2px]">
          {keys.map((k) => (
            <kbd key={k} className="flex h-[14px] min-w-[14px] items-center justify-center rounded-[3px] border border-[var(--pal-kbd)] px-[3px] font-sans text-[9.5px] leading-none">{k}</kbd>
          ))}
        </span>
      </button>
    );
  });
