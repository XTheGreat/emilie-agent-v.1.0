// Projects, Artifacts and Customize, laid out like the Claude Code desktop app's pages (measured from its dark theme):
// a serif title 24px in, its tools on the right, small grey section labels, then cards. Same places and shapes as
// Claude Code, so moving between the two apps needs no relearning.
import { useShallow } from "zustand/react/shallow";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useStore } from "@/lib/store";
import { get as apiGet, media } from "@/lib/api";
import { openPath } from "@/lib/desktop";
import type { Field } from "@/lib/types";
import { agoLong, agoShort, basename, cn } from "@/lib/util";
import * as I from "./icons";
import { insertIntoComposer } from "./Composer";
import { CUSTOM } from "./SettingsPanels";
import { Menu, MenuContent, MenuItem, MenuLabel, MenuSep, MenuTrigger, Spinner, Tip } from "./ui";

// ------------------------------------------------------------------ shared pieces
function Page({ title, tools, gap = 18, children }: { title: string; tools?: ReactNode; gap?: number; children: ReactNode }) {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto max-w-[1040px] px-6 pb-14 pt-[39px]">
        <div className="flex h-[28px] items-center gap-[2px]" style={{ marginBottom: gap }}>
          <h1 className="flex-1 font-serif text-[21px] font-medium leading-[28px] tracking-[-0.005em] text-text-100">{title}</h1>
          {tools}
        </div>
        {children}
      </div>
    </div>
  );
}

function IconBtn({ label, onClick, active, children, ...rest }: { label: string; onClick?: () => void; active?: boolean; children: ReactNode }) {
  return (
    <Tip content={label}>
      <button aria-label={label} onClick={onClick} {...rest}
        className={cn("flex h-[24px] w-[24px] items-center justify-center rounded-[6px] text-text-100 transition-colors hover:bg-hover aria-expanded:bg-hover",
          active && "bg-hover")}>
        {children}
      </button>
    </Tip>
  );
}

function SearchField({ value, onChange, placeholder, onClose }: { value: string; onChange: (v: string) => void; placeholder: string; onClose: () => void }) {
  return (
    <input autoFocus value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} spellCheck={false}
      onKeyDown={(e) => e.key === "Escape" && (e.stopPropagation(), onClose())}
      className="mr-[4px] h-[24px] w-[190px] rounded-[6px] border border-border-400 bg-transparent px-[8px] text-[11.5px] text-text-100 outline-none placeholder:text-text-500 focus:border-text-500 selectable" />
  );
}

function Tabs<T extends string>({ tabs, value, onChange }: { tabs: [T, string][]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="flex items-center">
      {tabs.map(([k, label]) => (
        <button key={k} onClick={() => onChange(k)}
          className={cn("h-[20px] rounded-[6px] px-[7px] text-[11.5px] text-text-100 transition-colors",
            value === k ? "bg-[var(--tab-on)]" : "hover:bg-hover")}>
          {label}
        </button>
      ))}
    </div>
  );
}

function Label({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("mb-[9px] text-[10.5px] leading-[14px] text-text-400", className)}>{children}</div>;
}

const WHEN: [number, string][] = [[0, "Any time"], [1, "Today"], [7, "Past week"], [30, "Past month"]];

// ------------------------------------------------------------------ Projects
interface Project { path: string; name: string; sessions: number; updated: number; exists: boolean }

export function ProjectsPage() {
  const s = useStore(useShallow((st) => ({ folders: st.folders, navigate: st.navigate, pickFolder: st.pickFolder, sessions: st.sessions, setHome: st.setHome, setSetting: st.setSetting, settings: st.settings })));
  const [q, setQ] = useState("");
  const [searching, setSearching] = useState(false);
  const [byName, setByName] = useState(false);
  const rawPins = s.settings.desktop_pinned_projects;
  const pins: string[] = Array.isArray(rawPins) ? rawPins : [];
  const projects = useMemo(() => {
    const m = new Map<string, Project>();
    for (const f of s.folders) m.set(f.path.toLowerCase(), { path: f.path, name: f.name, sessions: 0, updated: 0, exists: f.exists });
    for (const x of s.sessions) {
      if (x.chat || !x.cwd) continue;
      const k = x.cwd.toLowerCase();
      const e = m.get(k) || { path: x.cwd, name: basename(x.cwd), sessions: 0, updated: 0, exists: true };
      e.sessions += 1;
      e.updated = Math.max(e.updated, x.updated || 0);
      m.set(k, e);
    }
    const ql = q.trim().toLowerCase();
    return [...m.values()].filter((p) => !ql || (p.name + " " + p.path).toLowerCase().includes(ql))
      .sort((a, b) => (byName ? a.name.localeCompare(b.name) : b.updated - a.updated));
  }, [s.folders, s.sessions, q, byName]);
  const pinned = projects.filter((p) => pins.includes(p.path));
  const rest = projects.filter((p) => !pins.includes(p.path));
  const start = (path: string) => {
    s.setHome({ cwd: path, chat: false });
    s.navigate({ kind: "home" });
  };
  const togglePin = (path: string) =>
    s.setSetting("desktop_pinned_projects", pins.includes(path) ? pins.filter((x) => x !== path) : [path, ...pins]);
  const grid = (list: Project[]) => (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(270px,1fr))] gap-x-[21px] gap-y-[10px]">
      {list.map((p) => <ProjectCard key={p.path} p={p} pinned={pins.includes(p.path)} onOpen={() => p.exists && start(p.path)} onPin={() => togglePin(p.path)} />)}
    </div>
  );
  return (
    <Page title="Projects" gap={40} tools={<>
      {searching && <SearchField value={q} onChange={setQ} placeholder="Search projects" onClose={() => { setSearching(false); setQ(""); }} />}
      <IconBtn label="Search" active={searching} onClick={() => { setSearching(!searching); setQ(""); }}><I.SearchSm size={14} /></IconBtn>
      <IconBtn label={byName ? "Sort: name" : "Sort: most recent"} onClick={() => setByName(!byName)}><I.ArrowUpDown size={13} /></IconBtn>
      <button onClick={async () => { const p = await s.pickFolder("Open a project folder"); if (p) start(p); }}
        className="ml-[8px] h-[21px] rounded-[6px] bg-[var(--btn-solid)] px-[8px] text-[11.5px] font-medium text-[var(--btn-solid-fg)] transition hover:opacity-90">
        New project
      </button>
    </>}>
      {pinned.length > 0 && <><Label>Pinned</Label>{grid(pinned)}</>}
      {rest.length > 0 && <><Label className={pinned.length ? "mt-[26px]" : ""}>{pinned.length ? "All projects" : "Recent"}</Label>{grid(rest)}</>}
      {!projects.length && <div className="py-10 text-center text-[11.5px] text-text-500">{q ? "No project matches." : "No projects yet. Open a folder to start one."}</div>}
    </Page>
  );
}

function ProjectCard({ p, pinned, onOpen, onPin }: { p: Project; pinned: boolean; onOpen: () => void; onPin: () => void }) {
  return (
    <div role="button" onClick={onOpen} title={p.path}
      className={cn("group flex h-[48px] cursor-default items-center gap-[10px] rounded-[9px] bg-[var(--card-fill)] pl-[14px] pr-[8px] transition-colors hover:bg-hover",
        !p.exists && "opacity-50")}>
      <span className="flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-[6px] bg-[var(--folder-tile)] text-[var(--folder-tint)]">
        <I.FolderIcon size={12} strokeWidth={1.8} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[11.5px] leading-[15px] text-text-100">{p.name}</div>
        <div className="truncate text-[10.5px] leading-[14px] text-text-400">
          {!p.exists ? "Folder not found" : p.updated ? agoLong(p.updated) : "No sessions yet"}
        </div>
      </div>
      <Menu>
        <MenuTrigger asChild>
          <button aria-label="Project options" onClick={(e) => e.stopPropagation()}
            className="flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-[5px] text-text-300 opacity-0 hover:bg-hover hover:text-text-100 group-hover:opacity-100 aria-expanded:opacity-100">
            <I.Dots size={12} />
          </button>
        </MenuTrigger>
        <MenuContent align="end" onClick={(e) => e.stopPropagation()}>
          <MenuLabel>{p.sessions ? `${p.sessions} session${p.sessions === 1 ? "" : "s"}` : p.name}</MenuLabel>
          <MenuItem icon={pinned ? <I.PinOff /> : <I.Pin />} onSelect={onPin}>{pinned ? "Unpin" : "Pin"}</MenuItem>
          {p.exists && <MenuItem icon={<I.PlusSm />} onSelect={onOpen}>New session here</MenuItem>}
          {p.exists && <MenuItem icon={<I.FolderOpen />} onSelect={() => openPath(p.path)}>Open in File Explorer</MenuItem>}
          <MenuSep />
          <MenuItem icon={<I.SearchSm />} onSelect={() => useStore.setState({ dialog: { kind: "search", tab: "code", q: p.name } })}>Search its sessions</MenuItem>
        </MenuContent>
      </Menu>
    </div>
  );
}

// ------------------------------------------------------------------ Artifacts
interface Artifact { name: string; path: string; title: string; session: string; updated: number; exists: boolean }
type Kind = "image" | "doc" | "sheet" | "slides" | "web" | "notebook" | "code";

const EXT: Record<string, Kind> = {
  png: "image", jpg: "image", jpeg: "image", gif: "image", webp: "image", svg: "image", bmp: "image", ico: "image",
  docx: "doc", doc: "doc", pdf: "doc", md: "doc", txt: "doc", rtf: "doc", odt: "doc",
  xlsx: "sheet", xls: "sheet", csv: "sheet", tsv: "sheet", ods: "sheet", pptx: "slides", ppt: "slides", odp: "slides",
  html: "web", htm: "web", ipynb: "notebook",
};
const kindOf = (name: string): Kind => EXT[name.split(".").pop()?.toLowerCase() || ""] || "code";
/** Type label and the colour behind the page preview (Claude: navy for docs, a warm tone for slides, grey otherwise). */
const KIND: Record<Kind, { label: string; bg: string }> = {
  image: { label: "Image", bg: "var(--thumb-bg)" },
  doc: { label: "Docs", bg: "#1c355f" },
  sheet: { label: "Sheets", bg: "#173f27" },
  slides: { label: "Slides", bg: "#4d1b31" },
  web: { label: "Web page", bg: "var(--thumb-bg)" },
  notebook: { label: "Notebook", bg: "#35204d" },
  code: { label: "Code", bg: "var(--thumb-bg)" },
};
const BINARY = new Set(["docx", "doc", "pdf", "rtf", "odt", "xlsx", "xls", "ods", "pptx", "ppt", "odp"]);

/** "Make something new": the same six tiles as Claude Code, in the same order. Each starts a session with the request
 *  half-written in the message box. Slides is teal here: orange is Claude's colour. */
const MAKE: { label: string; bg: string; fg: string; icon: (p: any) => ReactNode; prompt: string }[] = [
  { label: "Docs", bg: "#0e3d7e", fg: "#9cc8ff", icon: I.FilePlain, prompt: "Write a Word document (.docx) about " },
  { label: "Slides", bg: "#0c4a50", fg: "#86dfe6", icon: I.Presentation, prompt: "Make a PowerPoint deck (.pptx) about " },
  { label: "Sheets", bg: "#0f4d17", fg: "#90cf59", icon: I.Table, prompt: "Make an Excel workbook (.xlsx) that " },
  { label: "Design", bg: "#3a2684", fg: "#d6c8ff", icon: I.Palette, prompt: "Design a single-file web page (index.html, no build step) for " },
  { label: "Data", bg: "#761a1c", fg: "#ffa3a3", icon: I.ChartColumn, prompt: "Analyse this data and save the charts as PNG files: " },
  { label: "Whiteboard", bg: "#651838", fg: "#ffa6d8", icon: I.Blend, prompt: "Draw a diagram (Mermaid, saved in a .md file) of " },
];

type ArtTab = "all" | "docs" | "code" | "images";

export function ArtifactsPage() {
  const s = useStore(useShallow((st) => ({ folders: st.folders, navigate: st.navigate, setHome: st.setHome })));
  const [rows, setRows] = useState<Artifact[] | null>(null);
  const [tab, setTab] = useState<ArtTab>("all");
  const [q, setQ] = useState("");
  const [searching, setSearching] = useState(false);
  const [asList, setAsList] = useState(false);
  const [days, setDays] = useState(0);
  const [folder, setFolder] = useState<string | null>(null);
  useEffect(() => {
    apiGet("/api/artifacts").then((r) => setRows(r.files || [])).catch(() => setRows([]));
  }, []);
  const ql = q.trim().toLowerCase();
  const since = days ? Date.now() / 1000 - days * 86400 : 0;
  const list = (rows || []).filter((r) => {
    const k = kindOf(r.name);
    const inTab = tab === "all" || (tab === "images" ? k === "image" : tab === "docs" ? ["doc", "sheet", "slides"].includes(k) : ["code", "web", "notebook"].includes(k));
    return inTab && (!since || r.updated >= since) && (!folder || r.path.toLowerCase().startsWith(folder.toLowerCase()))
      && (!ql || (r.name + " " + r.path + " " + r.title).toLowerCase().includes(ql));
  });
  const make = (prompt: string) => {
    s.setHome({ chat: false });
    s.navigate({ kind: "home" });
    setTimeout(() => insertIntoComposer(prompt), 80);
  };
  const filtered = days > 0 || !!folder;
  return (
    <Page title="Artifacts">
      <div className="flex h-[24px] items-center gap-[1px]">
        <Tabs<ArtTab> value={tab} onChange={setTab} tabs={[["all", "All"], ["docs", "Documents"], ["code", "Code"], ["images", "Images"]]} />
        <div className="flex-1" />
        {searching && <SearchField value={q} onChange={setQ} placeholder="Search files" onClose={() => { setSearching(false); setQ(""); }} />}
        <IconBtn label="Search" active={searching} onClick={() => { setSearching(!searching); setQ(""); }}><I.SearchSm size={14} /></IconBtn>
        <Menu>
          <MenuTrigger asChild>
            <IconBtn label="Filter" active={filtered}><I.ListFilter size={14} /></IconBtn>
          </MenuTrigger>
          <MenuContent align="end" className="max-h-[340px] overflow-y-auto">
            <MenuLabel>Updated</MenuLabel>
            {WHEN.map(([d, l]) => <MenuItem key={d} checked={days === d} onSelect={() => setDays(d)}>{l}</MenuItem>)}
            <MenuSep />
            <MenuLabel>Folder</MenuLabel>
            <MenuItem checked={!folder} onSelect={() => setFolder(null)}>Any folder</MenuItem>
            {s.folders.filter((f) => f.exists).slice(0, 14).map((f) => (
              <MenuItem key={f.path} checked={folder === f.path} onSelect={() => setFolder(f.path)}>{f.name}</MenuItem>
            ))}
          </MenuContent>
        </Menu>
        <IconBtn label={asList ? "Show as cards" : "Show as a list"} onClick={() => setAsList(!asList)}>
          {asList ? <I.LayoutGrid size={14} /> : <I.ListIcon size={14} />}
        </IconBtn>
        <Menu>
          <MenuTrigger asChild>
            <IconBtn label="Make something new"><I.PlusSm size={14} /></IconBtn>
          </MenuTrigger>
          <MenuContent align="end">
            {MAKE.map((m) => <MenuItem key={m.label} icon={m.icon({})} onSelect={() => make(m.prompt)}>{m.label}</MenuItem>)}
          </MenuContent>
        </Menu>
      </div>
      <Label className="mt-[23px]">Make something new</Label>
      <div className="flex flex-wrap gap-[6px]">
        {MAKE.map((m, i) => (
          <button key={m.label} onClick={() => make(m.prompt)} className="group w-[91px] text-left">
            <div className="relative flex h-[63px] items-center justify-center overflow-hidden rounded-[7px] transition-[filter] group-hover:brightness-[1.15]"
              style={{ background: m.bg, color: m.fg }}>
              <Doodle flip={i % 2 === 1} />
              <span className="relative">{m.icon({ size: 27, strokeWidth: 1.7 })}</span>
            </div>
            <div className="mt-[5px] text-[11px] leading-[14px] text-text-100">{m.label}</div>
          </button>
        ))}
      </div>
      <div className="mt-[31px]">
        {!rows && <Spinner />}
        {rows && !list.length && (
          <div className="py-10 text-center text-[11.5px] text-text-500">{rows.length ? "Nothing matches." : "Files Emilie creates or edits show up here."}</div>
        )}
        {!asList ? (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(190px,1fr))] gap-x-[19px] gap-y-[20px]">
            {list.map((r) => <ArtifactCard key={r.path} r={r} />)}
          </div>
        ) : list.length > 0 && (
          <div className="flex flex-col overflow-hidden rounded-[9px] border border-[var(--card-line)]">
            {list.map((r) => <ArtifactRow key={r.path} r={r} />)}
          </div>
        )}
      </div>
    </Page>
  );
}

/** The faint scribbles on Claude's tiles, in the tile's own colour. */
function Doodle({ flip }: { flip?: boolean }) {
  return (
    <svg viewBox="0 0 91 63" className="absolute inset-0 h-full w-full opacity-[0.13]" style={flip ? { transform: "scaleX(-1)" } : undefined}
      fill="none" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round">
      <path d="M-4 47c9-14 17 9 27-5s14-21 24-8 9 18 20 6 15-17 28-10" />
      <path d="M6-3c5 9-6 15 2 23s14-2 15 8" />
      <path d="M64 67c-2-9 9-12 6-21s9-12 14-6" />
      <path d="M40 4c6 3 10-4 15 1s2 9 8 9" />
    </svg>
  );
}

function artifactMenu(r: Artifact) {
  const s = useStore.getState();
  const meta = s.sessions.find((x) => x.id === r.session);
  return (
    <>
      <MenuItem icon={<I.FileText />} onSelect={() => s.openFile(r.path)}>Open</MenuItem>
      {meta && <MenuItem icon={<I.MessageCircle />} onSelect={() => s.openSession(meta)}>Open the session</MenuItem>}
      <MenuSep />
      <MenuItem icon={<I.External />} onSelect={() => openPath(r.path)}>Open with the default app</MenuItem>
      <MenuItem icon={<I.FolderOpen />} onSelect={() => openPath(r.path, true)}>Show in folder</MenuItem>
    </>
  );
}

/** Loads once the element scrolls near the view. */
function useSeen<T extends Element>(): [React.RefObject<T | null>, boolean] {
  const ref = useRef<T>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || seen) return;
    const io = new IntersectionObserver((es) => {
      if (es.some((e) => e.isIntersecting)) { setSeen(true); io.disconnect(); }
    }, { rootMargin: "300px" });
    io.observe(el);
    return () => io.disconnect();
  }, [seen]);
  return [ref, seen];
}

const heads = new Map<string, string | null>();   // file -> its first lines (null: not text), kept while the app runs

/** The page peeking up from the bottom of a card, as in Claude: the picture itself, or the file's first lines. */
function Preview({ r }: { r: Artifact }) {
  const k = kindOf(r.name);
  const ext = r.name.split(".").pop()?.toLowerCase() || "";
  const [ref, seen] = useSeen<HTMLDivElement>();
  const [text, setText] = useState<string | null | undefined>(heads.get(r.path));
  const [badImg, setBadImg] = useState(false);
  const wantsText = r.exists && k !== "image" && !BINARY.has(ext);
  useEffect(() => {
    if (!seen || !wantsText || text !== undefined) return;
    apiGet("/api/fs/read", { path: r.path, head: 1800 })
      .then((d) => { const t = d.kind === "text" ? String(d.text || "") : null; heads.set(r.path, t); setText(t); })
      .catch(() => { heads.set(r.path, null); setText(null); });
  }, [seen]);
  const dark = k === "code" || k === "web" || k === "notebook" || k === "slides";
  const paper = cn("absolute inset-x-[22px] bottom-0 top-[19px] overflow-hidden rounded-t-[4px] shadow-[0_1px_8px_rgb(0_0_0/0.35)]",
    dark ? "bg-[#1c1c1c] text-[#d4d4d4]" : "bg-bg-200 text-text-100");
  if (k === "image") {
    return (
      <div ref={ref} className={cn(paper, "bg-bg-300")}>
        {r.exists && !badImg && seen
          ? <img src={media("/media/file", { path: r.path })} alt="" draggable={false} onError={() => setBadImg(true)} className="h-full w-full object-cover object-top" />
          : <div className="flex h-full items-center justify-center text-text-500"><I.ImageIcon size={22} /></div>}
      </div>
    );
  }
  let body: ReactNode;
  if (typeof text === "string" && text.trim()) {
    const lines = text.replace(/\r/g, "").split("\n");
    const code = k !== "doc" && k !== "sheet";
    const shown = (code ? lines : lines.filter((l) => l.trim())).slice(0, 22);
    body = (
      <div className={cn("px-[8px] pt-[7px]", code ? "font-mono text-[5.4px] leading-[7.4px]" : "text-[5.6px] leading-[7.6px]")}>
        {shown.map((l, i) => {
          const h = !code && /^#{1,3}\s/.test(l);
          return (
            <div key={i} className={cn(code ? "whitespace-pre" : "truncate", h && "mb-[2px] font-serif text-[8.5px] font-semibold leading-[10px]")}>
              {(h ? l.replace(/^#+\s*/, "") : l) || " "}
            </div>
          );
        })}
      </div>
    );
  } else {
    // A Word/PowerPoint/Excel file (no text to show): its name as the page's heading over grey lines.
    body = (
      <div className="px-[10px] pt-[10px]">
        <div className={cn("mb-[6px] line-clamp-2 font-serif text-[9px] font-semibold leading-[11px]", k === "slides" && "mt-[10px] text-center text-[10px]")}>
          {r.name.replace(/\.[^.]+$/, "")}
        </div>
        {k !== "slides" && [92, 80, 86, 64, 88, 72].map((w, i) => (
          <div key={i} className={cn("mb-[4px] h-[3px] rounded-full", dark ? "bg-white/15" : "bg-black/10")} style={{ width: `${w}%` }} />
        ))}
      </div>
    );
  }
  return <div ref={ref} className={paper}>{body}</div>;
}

function ArtifactCard({ r }: { r: Artifact }) {
  const k = kindOf(r.name);
  return (
    <div role="button" onClick={() => r.exists && useStore.getState().openFile(r.path)} title={`${r.path}${r.title ? `\n${r.title}` : ""}`}
      className={cn("group relative cursor-default overflow-hidden rounded-[9px] border border-[var(--card-line)] transition-[filter] hover:brightness-110",
        !r.exists && "opacity-50")}>
      <div className="relative h-[104px] overflow-hidden" style={{ background: KIND[k].bg }}><Preview r={r} /></div>
      <div className="bg-[var(--card-foot)] px-[9px] pb-[8px] pt-[7px]">
        <div className="truncate text-[11.5px] leading-[15px] text-text-100">{r.name}</div>
        <div className="truncate text-[10.5px] leading-[14px] text-text-400">{KIND[k].label} · {agoShort(r.updated)}</div>
      </div>
      <Menu>
        <MenuTrigger asChild>
          <button aria-label="File options" onClick={(e) => e.stopPropagation()}
            className="absolute right-[6px] top-[6px] flex h-[22px] w-[22px] items-center justify-center rounded-[5px] bg-black/50 text-white opacity-0 hover:bg-black/70 group-hover:opacity-100 aria-expanded:opacity-100">
            <I.Dots size={12} />
          </button>
        </MenuTrigger>
        <MenuContent align="end" onClick={(e) => e.stopPropagation()}>{artifactMenu(r)}</MenuContent>
      </Menu>
    </div>
  );
}

function ArtifactRow({ r }: { r: Artifact }) {
  const k = kindOf(r.name);
  return (
    <div role="button" onClick={() => r.exists && useStore.getState().openFile(r.path)}
      className={cn("group flex h-[46px] cursor-default items-center gap-[10px] border-b border-[var(--card-line)] px-[12px] transition-colors last:border-b-0 hover:bg-hover",
        !r.exists && "opacity-50")}>
      <span className="text-text-400">{k === "image" ? <I.ImageIcon size={14} /> : k === "code" || k === "web" ? <I.CodeXml size={14} /> : <I.FileText size={14} />}</span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[11.5px] text-text-100">{r.name}</div>
        <div className="truncate text-[10.5px] text-text-500" title={r.path}>{r.path}</div>
      </div>
      <span className="max-w-[220px] truncate text-[10.5px] text-text-400">{r.title || ""}</span>
      <span className="w-[62px] shrink-0 text-right text-[10.5px] text-text-500">{agoShort(r.updated)}</span>
      <Menu>
        <MenuTrigger asChild>
          <button aria-label="File options" onClick={(e) => e.stopPropagation()}
            className="flex h-[22px] w-[22px] items-center justify-center rounded-[5px] text-text-300 opacity-0 hover:bg-hover group-hover:opacity-100 aria-expanded:opacity-100">
            <I.Dots size={12} />
          </button>
        </MenuTrigger>
        <MenuContent align="end" onClick={(e) => e.stopPropagation()}>{artifactMenu(r)}</MenuContent>
      </Menu>
    </div>
  );
}

// ------------------------------------------------------------------ Customize
export type CustomizeTab = "plugins" | "skills" | "connectors" | "scheduled";

const CUSTOMIZE_INFO: Record<CustomizeTab, string> = {
  plugins: "Plugins bundle skills, slash commands and connectors in one folder. Add one from a folder or a GitHub address.",
  skills: "Skills teach Emilie how to do a kind of job. She loads a matching one by herself, or you call it with /name.",
  connectors: "Connectors (MCP servers) give Emilie extra tools: a real browser, library docs, memory, GitHub and more.",
  scheduled: "Tasks that run Emilie on a schedule through the Windows Task Scheduler, even when this window is closed.",
};

/** Skills, Connectors and Scheduled tasks on one page (Claude Code's Customize), instead of inside Settings. */
export function CustomizePage({ tab }: { tab?: CustomizeTab }) {
  const s = useStore(useShallow((st) => ({ navigate: st.navigate })));
  const t: CustomizeTab = tab || "plugins";
  const field: Field = { key: "", type: "", label: "" };
  const Panel = t === "plugins" ? CUSTOM.plugins : t === "skills" ? CUSTOM.skills : t === "connectors" ? CUSTOM.mcp : CUSTOM.schedule;
  return (
    <Page title="Customize">
      <Tabs<CustomizeTab> value={t} onChange={(v) => s.navigate({ kind: "customize", tab: v }, true)}
        tabs={[["plugins", "Plugins"], ["skills", "Skills"], ["connectors", "Connectors"], ["scheduled", "Scheduled tasks"]]} />
      <p className="mb-[16px] mt-[14px] text-[11.5px] text-text-400">{CUSTOMIZE_INFO[t]}</p>
      <div className="max-w-[780px]">{Panel ? <Panel key={t} field={field} /> : null}</div>
    </Page>
  );
}
