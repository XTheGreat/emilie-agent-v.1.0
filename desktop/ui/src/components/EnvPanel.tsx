// The "Environment" panel on the right of a session, like the Claude Code desktop app (240px):
// where she works (computer, folder, git branch), a toggle, Context (what fills it, by kind, and when it is summarized),
// Connectors, Outputs (files she wrote) and Changes.
import { memo, useEffect, useMemo, useRef, useState } from "react";
import { useStore } from "@/lib/store";
import type { CtxParts, Item, Live, Status } from "@/lib/types";
import { get as apiGet, post } from "@/lib/api";
import { openExternal, openPath } from "@/lib/desktop";
import { cn, dirname } from "@/lib/util";
import { BranchSm, Camera, ChevD, Video, ChevR, CodeXml, FileDiff, FileText, FolderSm, GearSm, GlobeSm, LaptopIcon, Volume } from "./icons";
import { Menu, MenuContent, MenuItem, MenuLabel, MenuSep, MenuTrigger, Switch, Tip } from "./ui";

const WRITE_TOOLS = new Set(["write_file", "edit_file", "docx_create", "docx_edit", "xlsx_write", "notebook_edit"]);
const CONNECTORS_SHOWN = 3;              // then "Show more"
const OUTPUTS_SHOWN = 5;                 // then "Show more", as in Claude

function fileIcon(name: string) {
  const ext = name.split(".").pop()?.toLowerCase() || "";
  if (["html", "htm"].includes(ext)) return <GlobeSm size={12} />;
  if (["md", "txt", "docx", "pdf", "rtf"].includes(ext)) return <FileText size={12} />;
  return <CodeXml size={12} />;
}

type EnvProps = {
  live: Live; onCommand: (cmd: string) => void;
  floating?: boolean; maxHeight?: string; onClose?: () => void;    // floating: over the conversation while a file is open
};

/** The panel shows the session's folder, status and the files she wrote. A piece of a reply changes none of these but
 *  makes the session a new object, so the panel compares what it shows instead and skips those redraws. */
function sameEnv(a: EnvProps, b: EnvProps): boolean {
  if (a.onCommand !== b.onCommand || a.floating !== b.floating || a.maxHeight !== b.maxHeight || a.onClose !== b.onClose) return false;
  const x = a.live, y = b.live;
  return x === y || (x.wid === y.wid && x.cwd === y.cwd && x.busy === y.busy && x.closed === y.closed && x.status === y.status
    && outputsKey(x.items) === outputsKey(y.items));
}

/** The files written so far (what Outputs lists), as one string; remembered per list of items. */
const outKeys = new WeakMap<Item[], string>();
function outputsKey(items: Item[]): string {
  let k = outKeys.get(items);
  if (k === undefined) {
    k = "";
    for (const it of items) if (it.kind === "tool" && WRITE_TOOLS.has(it.name) && it.status === "ok" && it.input?.path) k += String(it.input.path) + "\n";
    outKeys.set(items, k);
  }
  return k;
}

export const EnvPanel = memo(function EnvPanel({ live, onCommand, floating, maxHeight, onClose }: EnvProps) {
  const box = useRef<HTMLElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    if (!floating) return;
    const down = (e: MouseEvent) => {
      const t = e.target as HTMLElement;
      // its own menus and the title-bar button that toggles it do not count as "outside"
      if (box.current?.contains(t) || t.closest('[aria-label="Environment panel"]') || t.closest("[data-radix-popper-content-wrapper]")) return;
      close.current?.();
    };
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape" && (box.current?.contains(document.activeElement) || document.activeElement === document.body)) close.current?.();
    };
    document.addEventListener("mousedown", down);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("mousedown", down);
      document.removeEventListener("keydown", key);
    };
  }, [floating]);
  const voice = useStore((s) => !!s.settings.voice);
  const setSetting = useStore((s) => s.setSetting);
  const openFile = useStore((s) => s.openFile);
  const [git, setGit] = useState<{ repo: boolean; remote?: string; branch?: string; added?: number; removed?: number; files?: number } | null>(null);
  const [mcp, setMcp] = useState<{ name: string; status: string; error?: string; tools?: string[] }[] | null>(null);
  const cwd = live.cwd;

  useEffect(() => {
    if (live.busy || !cwd) return;
    let dead = false;
    apiGet("/api/git/status", { cwd }).then((r) => !dead && setGit(r)).catch(() => {});
    if (!live.closed) post("/api/session/mcp", { wid: live.wid }).then((r) => !dead && setMcp(r)).catch(() => {});
    return () => { dead = true; };
  }, [cwd, live.busy, live.wid]);

  const outputs = useMemo(() => {
    const seen = new Map<string, string>();
    for (const it of live.items as Item[]) {
      if (it.kind !== "tool" || !WRITE_TOOLS.has(it.name) || it.status !== "ok" || !it.input?.path) continue;
      const p = String(it.input.path);
      const abs = /^([a-zA-Z]:[\\/]|[\\/])/.test(p) ? p : `${cwd.replace(/[\\/]+$/, "")}\\${p.replace(/\//g, "\\")}`;
      seen.delete(abs);
      seen.set(abs, p.split(/[\\/]/).pop() || p);
    }
    return [...seen.entries()].reverse();
  }, [live.items, cwd]);

  const [allOutputs, setAllOutputs] = useState(false);
  const [allConn, setAllConn] = useState(false);
  const toFix = (mcp || []).filter((m) => m.status !== "ready").length;
  const st = live.status;
  const folder = cwd.split(/[\\/]/).filter(Boolean).pop() || cwd;
  const parent = dirname(cwd);
  const parentShort = parent.length > 18 ? "…" + parent.slice(-16) : parent;

  return (
    <aside ref={box} style={floating ? { maxHeight } : undefined}
      className={cn("flex w-[240px] shrink-0 flex-col overflow-y-auto bg-bg-100 px-[13px] pb-4 pt-[12px] text-[11.5px]",
        floating
          ? "absolute right-2 top-2 z-20 rounded-[10px] border border-border-300 shadow-[0_4px_18px_rgba(0,0,0,0.45)] animate-pop dark:border-[#222]"
          : "border-l border-border-300")}>
      <Title plain>Environment</Title>
      <Row icon={<LaptopIcon size={12} />} label="This computer"
        right={<Tip content="Session settings"><button className="text-text-200 hover:text-text-000" onClick={() => useStore.setState({ settingsOpen: "code" })}><GearSm size={12} /></button></Tip>} />
      <Menu>
        <MenuTrigger asChild>
          <div role="button" title={cwd} className="-mx-1 flex h-[24px] cursor-default items-center gap-[9px] rounded-[5px] px-1 text-text-100 hover:bg-hover">
            <span className="flex w-[12px] shrink-0 justify-center text-text-400"><FolderSm size={12} /></span>
            <span className="min-w-0 flex-1 truncate">{folder} <span className="text-text-400">· {parentShort}</span></span>
          </div>
        </MenuTrigger>
        <MenuContent align="start">
          <MenuItem onSelect={() => openPath(cwd, true)}>Show in Explorer</MenuItem>
          {git?.remote && <MenuItem onSelect={() => openExternal(git.remote!)}>Open repository on GitHub</MenuItem>}
          <MenuSep />
          <MenuItem onSelect={() => copyText(cwd)}>Copy path</MenuItem>
          <MenuItem onSelect={() => useStore.getState().setPane("terminal")}>Open in terminal</MenuItem>
        </MenuContent>
      </Menu>
      {git?.repo && (
        <Menu>
          <MenuTrigger asChild>
            <div role="button" title="Git branch" className="-mx-1 flex h-[24px] cursor-default items-center gap-[9px] rounded-[5px] px-1 text-text-100 hover:bg-hover">
              <span className="flex w-[12px] shrink-0 justify-center text-text-400"><BranchSm size={12} /></span>
              <span className="min-w-0 flex-1 truncate">{git.branch || "(no branch)"}</span>
            </div>
          </MenuTrigger>
          <MenuContent align="start">
            <MenuItem onSelect={() => copyText(git.branch || "")}>Copy branch name</MenuItem>
            <MenuSep />
            <MenuItem onSelect={() => useStore.getState().setPane("terminal")}>Open in terminal</MenuItem>
          </MenuContent>
        </Menu>
      )}
      <Row icon={<Volume size={12} />} label="Voice" right={<Switch checked={voice} onChange={(v) => setSetting("voice", v)} />} />
      <Row icon={<Video size={12} />} label="Video" title="A video call: Emilie sees you through the camera while it is on"
        right={<Switch checked={!!st.call} onChange={(v) => useStore.getState().setCall(live.wid, v)} />} />
      <CameraRow />
      <Divider />
      <Fold id="context" title="Context" summary={<CtxSummary st={st} />}>
        <ContextSection st={st} />
      </Fold>
      <Divider />
      <Fold id="connectors" title="Connectors" summary={
        <span className={cn("text-[11px]", toFix ? "text-warn" : "text-text-400")}>
          {mcp === null ? "" : !mcp.length ? "none" : toFix ? `${toFix} to reconnect` : `${mcp.length} connected`}</span>}>
      {mcp !== null && !mcp.length && <div className="py-1 text-[11px] text-text-400">No connectors yet.</div>}
      {(mcp || []).slice(0, allConn ? 60 : CONNECTORS_SHOWN).map((m) => (
        <Row key={m.name} onClick={() => useStore.setState({ dialog: { kind: "connector", wid: live.wid, name: m.name,
          status: m.status, error: m.error, tools: m.tools?.length, done: (l) => setMcp(l) } })}
          icon={<span className="flex h-[14px] w-[14px] items-center justify-center rounded-[3px] bg-bg-400 text-[9px] font-medium uppercase text-text-300">{m.name.charAt(0)}</span>}
          label={m.name}
          right={m.status === "ready"
            ? <span className="text-[11px] text-text-400">Connected</span>
            : <span className="text-[11px] text-warn">Connect</span>} />
      ))}
      {(mcp || []).length > CONNECTORS_SHOWN && (
        <button onClick={() => setAllConn(!allConn)}
          className="-mx-1 mt-[2px] h-[24px] self-start rounded-[5px] px-1 text-left text-text-400 hover:text-text-100">
          {allConn ? "Show less" : "Show more"}
        </button>
      )}
      </Fold>
      <Divider />
      <Fold id="outputs" title="Outputs" summary={<span className="text-[11px] text-text-400">{outputs.length || ""}</span>}>
      {!outputs.length && <div className="py-1 text-[11px] text-text-400">Files Emilie writes show up here.</div>}
      {outputs.slice(0, allOutputs ? 60 : OUTPUTS_SHOWN).map(([abs, name]) => (
        <Row key={abs} icon={fileIcon(name)} label={name} title={abs} onClick={() => openFile(abs)} />
      ))}
      {outputs.length > OUTPUTS_SHOWN && (
        <button onClick={() => setAllOutputs(!allOutputs)}
          className="-mx-1 mt-[2px] h-[24px] self-start rounded-[5px] px-1 text-left text-text-400 hover:text-text-100">
          {allOutputs ? "Show less" : "Show more"}
        </button>
      )}
      </Fold>
      <Divider />
      <Fold id="changes" title="Changes" summary={git?.repo && (git.added || git.removed)
        ? <span className="font-mono text-[11px]"><span className="text-ok">+{git.added || 0}</span> <span className="text-danger">−{git.removed || 0}</span></span> : null}>
      {git?.repo ? (
        <>
          <Row icon={<FileDiff size={12} />} onClick={() => useStore.getState().setPane("diff")} title="Open the changes"
            label={<span className="font-mono text-[11px]"><span className="text-ok">+{git.added || 0}</span> <span className="text-danger">−{git.removed || 0}</span></span>}
            right={<button onClick={(e) => { e.stopPropagation(); onCommand("/pr"); }}
              className="h-[22px] rounded-[5px] bg-bg-400 px-2 text-[11.5px] text-text-100 hover:brightness-125">Create PR</button>} />
          <Menu>
            <MenuTrigger asChild>
              <button className="mt-1 inline-flex h-[22px] items-center gap-1 self-start rounded-[5px] bg-bg-400 px-2 text-[11px] text-text-300 hover:text-text-100">
                Git actions <ChevD size={9} strokeWidth={1.8} />
              </button>
            </MenuTrigger>
            <MenuContent align="start">
              <MenuItem onSelect={() => onCommand("/review")}>Review the changes</MenuItem>
              <MenuItem onSelect={() => onCommand("/commit")}>Commit (writes the message)</MenuItem>
              <MenuItem onSelect={() => onCommand("/pr")}>Draft a pull request</MenuItem>
              <MenuSep />
              <MenuItem onSelect={() => useStore.getState().setPane("diff")}>Open the diff</MenuItem>
            </MenuContent>
          </Menu>
        </>
      ) : (
        <div className="py-1 text-[11px] text-text-400">{git ? "This folder is not a git repository." : ""}</div>
      )}
      </Fold>
    </aside>
  );
}, sameEnv);

/** Copy to the clipboard (the Electron page has navigator.clipboard); a failure is ignored. */
function copyText(t: string) {
  try { navigator.clipboard.writeText(t); useStore.getState().toast("Copied", "ok"); } catch { /* no clipboard */ }
}

/** Camera: a row that opens a menu (take a photo into the message, pick the device, open the camera settings). */
function CameraRow() {
  const [info, setInfo] = useState<{ available: boolean; devices: string[]; configured?: string | null } | null>(null);
  const load = () => apiGet("/api/camera").then(setInfo).catch(() => setInfo({ available: false, devices: [] }));
  const pick = async (d: string | null) => {
    try { setInfo(await post("/api/camera/device", { device: d })); } catch (e: any) { useStore.getState().toast(e.message, "error"); }
  };
  const chosen = info?.configured || "";
  return (
    <Menu onOpenChange={(o) => o && load()}>
      <MenuTrigger asChild>
        <div role="button" title="Camera" className="-mx-1 flex h-[24px] cursor-default items-center gap-[9px] rounded-[5px] px-1 text-text-100 hover:bg-hover">
          <span className="flex w-[12px] shrink-0 justify-center text-text-400"><Camera size={12} /></span>
          <span className="min-w-0 flex-1 truncate">Camera</span>
          <ChevD size={10} className="shrink-0 text-text-400" />
        </div>
      </MenuTrigger>
      <MenuContent align="start" className="min-w-[210px]">
        <MenuItem disabled={info !== null && !info.available}
          onSelect={() => window.dispatchEvent(new CustomEvent("emilie:take-photo"))}>Take a photo</MenuItem>
        {info !== null && !info.available && <div className="px-2 py-1 text-[11px] leading-[15px] text-text-400">No camera found. Install ffmpeg (winget install Gyan.FFmpeg) and plug one in.</div>}
        {!!info?.devices.length && (
          <>
            <MenuSep />
            <MenuLabel>Camera device</MenuLabel>
            <MenuItem checked={!chosen} onSelect={() => pick(null)}>Automatic</MenuItem>
            {info.devices.map((d) => <MenuItem key={d} checked={chosen === d} onSelect={() => pick(d)}>{d}</MenuItem>)}
          </>
        )}
        <MenuSep />
        <MenuItem onSelect={() => useStore.setState({ settingsOpen: "capabilities" })}>Camera settings…</MenuItem>
      </MenuContent>
    </Menu>
  );
}

function Row({ icon, label, right, onClick, title }: { icon?: React.ReactNode; label: React.ReactNode; right?: React.ReactNode; onClick?: () => void; title?: string }) {
  return (
    <div role={onClick ? "button" : undefined} onClick={onClick} title={title}
      className={cn("-mx-1 flex h-[24px] items-center gap-[9px] rounded-[5px] px-1 text-text-100", onClick && "cursor-default hover:bg-hover")}>
      {icon && <span className="flex w-[12px] shrink-0 justify-center text-text-400">{icon}</span>}
      <span className="min-w-0 flex-1 truncate">{label}</span>
      {right}
    </div>
  );
}

function Divider() {
  return <div className="my-[7px] h-px shrink-0 bg-[var(--divider)]" />;
}

const FOLD_KEY = "emilie.env.open";
function readFolds(): Record<string, boolean> {
  try { return JSON.parse(localStorage.getItem(FOLD_KEY) || "{}") || {}; } catch { return {}; }
}

/** A section that opens and closes (closed by default, as in Claude's panel): a header with a chevron and a short
 *  summary on the right, then the body. The choice is remembered. */
function Fold({ id, title, summary, children }: { id: string; title: string; summary?: React.ReactNode; children: React.ReactNode }) {
  const [open, setOpen] = useState<boolean>(() => !!readFolds()[id]);
  const toggle = () => {
    const v = !open;
    setOpen(v);
    try { localStorage.setItem(FOLD_KEY, JSON.stringify({ ...readFolds(), [id]: v })); } catch { /* no storage */ }
  };
  return (
    <>
      <button onClick={toggle} aria-expanded={open}
        className="-mx-1 flex h-[26px] w-[calc(100%+8px)] items-center gap-1 rounded-[5px] px-1 text-left text-text-100 hover:bg-hover">
        <span className="text-[11.5px]">{title}</span>
        <ChevR size={9} strokeWidth={1.8} className={cn("shrink-0 text-text-400 transition-transform duration-150", open && "rotate-90")} />
        <span className="flex-1" />
        {!open && summary}
      </button>
      {open && <div className="pb-1 pt-[3px]">{children}</div>}
    </>
  );
}

function Title({ children, plain }: { children: React.ReactNode; plain?: boolean }) {
  return <div className={cn("mb-[6px] mt-[2px] text-[11px] text-text-100", !plain && "font-semibold")}>{children}</div>;
}

// ---------------------------------------------------------------- Context
/** Closed-state summary of Context: the percentage used and a thin bar. */
function CtxSummary({ st }: { st: Partial<Status> }) {
  const limit = Math.max(1, st.ctx_limit || st.ctx_parts?.compact_default || 1);
  const pct = Math.min(100, Math.round(((st.ctx_tokens || 0) * 100) / limit));
  return (
    <span className="flex items-center gap-2 text-[11px] text-text-400">
      {pct}%
      <span className="h-[4px] w-[34px] overflow-hidden rounded-full bg-bg-400"><span className="block h-full bg-[#5b8def]" style={{ width: `${pct}%` }} /></span>
    </span>
  );
}

/** What fills the context, in the order and colours of Claude's panel (they read well in light and dark). */
const PARTS: { key: keyof CtxParts; label: string; color: string; tip: string }[] = [
  { key: "messages", label: "Messages", color: "#5b8def", tip: "The conversation so far: your messages, Emilie's answers and tool results" },
  { key: "system_tools", label: "System tools", color: "#e8833a", tip: "Definitions of Emilie's built-in tools (files, shell, web, …)" },
  { key: "mcp_tools", label: "MCP tools", color: "#2bb5a0", tip: "Tools of the connected MCP servers, and the note that lists them" },
  { key: "system_prompt", label: "System prompt", color: "#d9a632", tip: "Emilie's instructions, persona and a snapshot of this folder" },
  { key: "skills", label: "Skills", color: "#e0679b", tip: "The list of skills Emilie can load" },
  { key: "memory", label: "Memory", color: "#9b7bea", tip: "Project memory files (EMILIE.md, …)" },
];
/** "Auto-compact at" choices: 160K (max effort's point), then Claude's big-window steps (300K–1M).
 *  Anything above 70% of the model's window is hidden (and the backend caps it the same way). */
const COMPACT_CHOICES = [160_000, 300_000, 400_000, 500_000, 1_000_000];

/** 64.1K, 33K, 848.5K, 1M, 1.5M, 812 */
function fmtTok(n: number): string {
  const one = (x: number) => (Math.round(x * 10) / 10).toString();
  if (n >= 1_000_000) return one(n / 1_000_000) + "M";
  if (n >= 1000) return one(n / 1000) + "K";
  return String(Math.max(0, Math.round(n)));
}

function fmtPct(n: number, of: number): string {
  const p = (n * 100) / Math.max(1, of);
  return p > 0 && p < 0.1 ? "<0.1%" : p.toFixed(1) + "%";
}

/** The Context section, laid out like Claude's: how full it is, a bar split by kind, when older messages are
 *  summarized (a real setting: compact_at), and the breakdown with each kind's share. Percentages are of the
 *  auto-compact point, the budget Emilie actually works in (the model's full window is often unknown). */
function ContextSection({ st }: { st: Partial<Status> }) {
  const setSetting = useStore((s) => s.setSetting);
  const choice = useStore((s) => s.settings.compact_at as number | null | undefined);
  const [mcpOpen, setMcpOpen] = useState(false);
  const p = st.ctx_parts || null;
  const used = st.ctx_tokens || 0;
  const limit = Math.max(1, st.ctx_limit || p?.compact_default || 1);
  const scale = Math.max(limit, used);                     // past 100% (just before a summary) the bar is full
  const rows = PARTS.map((d) => ({ ...d, n: p ? Number(p[d.key]) || 0 : 0 })).filter((r) => r.n > 0);
  const free = Math.max(0, limit - used);
  const servers = p?.mcp_servers || [];
  const nTools = servers.reduce((a, s) => a + s.tools, 0);
  const cap = p?.window ? Math.floor(p.window * 0.7) : Infinity;   // compaction never goes past 70% of the window
  const choices = COMPACT_CHOICES.filter((c) => c <= cap);

  return (
    <>
      <div className="flex h-[20px] items-center justify-between">
        <span className="text-text-100">{Math.round((used * 100) / limit)}% used</span>
        <span className="tabular-nums text-text-400">{fmtTok(used)} / {fmtTok(limit)}</span>
      </div>
      <div className="mt-[5px] flex h-[6px] w-full gap-px overflow-hidden rounded-full bg-bg-400" aria-hidden>
        {rows.map((r) => (
          <span key={r.key} className="h-full shrink-0 transition-[width] duration-300"
            style={{ width: `${(r.n * 100) / scale}%`, minWidth: 2, background: r.color }} />
        ))}
      </div>

      <div className="mt-[11px] flex h-[22px] items-center justify-between">
        <span className="font-medium text-text-100">Auto-compact at</span>
        <Menu>
          <MenuTrigger asChild>
            <button className="-mr-1 flex h-[22px] items-center gap-1 rounded-[5px] px-1 tabular-nums text-text-100 hover:bg-hover">
              {fmtTok(limit)} <ChevD size={9} strokeWidth={1.8} className="text-text-400" />
            </button>
          </MenuTrigger>
          <MenuContent align="end" className="min-w-[200px]">
            <MenuLabel>Summarize older messages at</MenuLabel>
            <MenuItem checked={!choice} onSelect={() => setSetting("compact_at", null)}
              shortcut={p ? fmtTok(Math.min(p.compact_default, cap)) : undefined}>
              Effort default
            </MenuItem>
            <MenuSep />
            {choices.map((c) => (
              <MenuItem key={c} checked={choice === c} onSelect={() => setSetting("compact_at", c)}
                shortcut={c === 400_000 ? "Recommended" : undefined}>{fmtTok(c)}</MenuItem>
            ))}
          </MenuContent>
        </Menu>
      </div>
      <p className="mb-[9px] mt-[1px] text-[11px] leading-[15px] text-text-400">
        Lower uses fewer tokens. Emilie summarizes older messages sooner.
      </p>

      {rows.map((r) => <Legend key={r.key} swatch={r.color} label={r.label} tip={r.tip} n={r.n} pct={fmtPct(r.n, limit)} />)}
      {!p && <div className="py-1 text-[11px] text-text-400">Measured once the session has started.</div>}
      <div className="h-[7px]" />
      <Legend swatch="var(--bg-400)" label="Free space" tip="Room left before older messages are summarized" n={free} pct={fmtPct(free, limit)} />
      {p?.window ? <Legend swatch="transparent" outline label="Model window" tip="This model's whole context window" n={p.window} pct="—" /> : null}

      {nTools > 0 && (
        <>
          <button onClick={() => setMcpOpen(!mcpOpen)}
            className="-mx-1 mt-[6px] flex h-[24px] items-center gap-[7px] rounded-[5px] px-1 text-left text-text-300 hover:bg-hover hover:text-text-100">
            <ChevR size={9} strokeWidth={1.8} className={cn("shrink-0 text-text-400 transition-transform duration-150", mcpOpen && "rotate-90")} />
            <span className="flex-1">MCP tools</span>
            <span className="tabular-nums text-text-400">{nTools}</span>
          </button>
          {mcpOpen && servers.map((s) => (
            <div key={s.name} className="flex h-[22px] items-center gap-2 pl-[16px] text-text-300" title={`${s.tools} tools · ~${fmtTok(s.tokens)} tokens`}>
              <span className="min-w-0 flex-1 truncate">{s.name}</span>
              <span className="shrink-0 tabular-nums text-text-400">{s.tools}</span>
              <span className="w-[42px] shrink-0 text-right tabular-nums text-text-400">{fmtTok(s.tokens)}</span>
            </div>
          ))}
        </>
      )}
    </>
  );
}

function Legend({ swatch, label, tip, n, pct, outline }: {
  swatch: string; label: string; tip: string; n: number; pct: string; outline?: boolean;
}) {
  return (
    <div className="flex h-[22px] items-center gap-[9px]" title={tip}>
      <span className={cn("h-[8px] w-[8px] shrink-0 rounded-[2px]", outline && "border border-text-500")} style={{ background: swatch }} />
      <span className="min-w-0 flex-1 truncate text-text-300">{label}</span>
      <span className="shrink-0 tabular-nums text-text-300">{fmtTok(n)}</span>
      <span className="w-[42px] shrink-0 text-right font-medium tabular-nums text-text-100">{pct}</span>
    </div>
  );
}
