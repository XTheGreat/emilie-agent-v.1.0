// The row under the message box, as in the Claude Code desktop app: "This computer", folder, Worktree on the left;
// model + effort, permission mode and the ring on the right. White 11px text, grey chevrons, no boxes.
// Every chip explains itself in a tooltip on hover.
import { useEffect, useMemo, useRef, useState } from "react";
import { useStore, folderName } from "@/lib/store";
import type { Live } from "@/lib/types";
import { openPath } from "@/lib/desktop";
import { get as apiGet } from "@/lib/api";
import { cn, fmtTokens, prettyModel } from "@/lib/util";
import type { PickerName } from "@/lib/slash";
import { Check, ChevD, Eye, FolderOpen, FolderSm, ListTodo, Loader, MessageSquare, Plug, PlusSm, Refresh, Rewind, SearchSm, Shield, Zap } from "./icons";
import { Menu, MenuContent, MenuItem, MenuLabel, MenuSep, MenuTrigger, Pop, PopContent, PopTrigger, Segmented, Tip, TipBody } from "./ui";
import { focusComposer } from "./Composer";

// after a chip's menu closes, typing goes back to the message box (and the chip's tooltip does not pop up)
const refocus = (e: Event) => { e.preventDefault(); focusComposer(); };

/** Opens a picker when a typed command asks for it (/model, /effort, /mode, /cost, /rewind: lib/slash.ts). */
function useOpenOn(name: PickerName, open: () => void) {
  useEffect(() => {
    const f = (e: Event) => { if ((e as CustomEvent).detail === name) open(); };
    window.addEventListener("emilie:open", f);
    return () => window.removeEventListener("emilie:open", f);
  }, [name]);
}

export const chip = "no-drag inline-flex h-[20px] min-w-0 shrink-0 items-center gap-[5px] whitespace-nowrap rounded-[5px] px-1 text-[11px] text-text-100 transition-colors hover:bg-hover aria-expanded:bg-hover";
const chev = <ChevD size={9} strokeWidth={1.7} className="shrink-0 text-text-400" />;

export const MODES: Record<string, { label: string; short: string; desc: string; icon: React.ReactNode }> = {
  ask: { label: "Ask first", short: "Ask", desc: "Asks before changing files or running commands", icon: <Shield size={13} /> },
  trust: { label: "Trust", short: "Auto", desc: "Works on her own in this folder, no questions", icon: <Zap size={13} /> },
  plan: { label: "Plan", short: "Plan", desc: "Only reads, then proposes a plan for you to approve", icon: <ListTodo size={13} /> },
};

const MCP_CHOICES = [
  { value: "always", label: "Always" },
  { value: "on_demand", label: "On demand" },
  { value: "off", label: "Off" },
];

/** "MCP ∨": which MCP servers the next chat gets, and how (the mcp_modes setting): every tool sent each time,
 *  loaded only when needed (the default), or not started. */
export function McpChip({ cwd }: { cwd?: string | null }) {
  const modes = useStore((s) => s.settings.mcp_modes as Record<string, string> | undefined);
  const setSetting = useStore((s) => s.setSetting);
  const [open, setOpen] = useState(false);
  const [names, setNames] = useState<string[] | null>(null);
  useEffect(() => {
    if (!open) return;
    apiGet("/api/mcp/config", cwd ? { cwd } : {})
      .then((c: any) => setNames(Object.keys({ ...c.user?.servers, ...c.project?.servers }).sort()))
      .catch(() => setNames([]));
  }, [open, cwd]);
  return (
    <Pop open={open} onOpenChange={setOpen}>
      <Tip side="top" content="MCP servers" hidden={open}>
        <PopTrigger asChild>
          <button className={chip}><Plug size={12} />MCP{chev}</button>
        </PopTrigger>
      </Tip>
      <PopContent side="top" className="w-[300px] p-[10px]" onCloseAutoFocus={refocus}>
        <div className="mb-[2px] font-medium">MCP servers</div>
        <p className="mb-[8px] text-[11px] leading-[15px] text-text-400">On demand costs no tokens until Emilie needs the server.</p>
        <div className="max-h-[280px] overflow-y-auto">
          {names?.map((n) => (
            <div key={n} className="flex h-[28px] items-center gap-2">
              <span className="min-w-0 flex-1 truncate" title={n}>{n}</span>
              <Segmented value={modes?.[n] || "on_demand"} onChange={(v) => setSetting("mcp_modes", { ...modes, [n]: v })} options={MCP_CHOICES} />
            </div>
          ))}
          {names && !names.length && <div className="text-[11.5px] text-text-500">No MCP servers yet.</div>}
        </div>
        <button className="mt-[8px] flex items-center gap-[6px] text-[11.5px] text-text-300 hover:text-text-000"
          onClick={() => { setOpen(false); useStore.setState({ settingsOpen: "customize" }); }}>
          <PlusSm />Add or remove servers
        </button>
      </PopContent>
    </Pop>
  );
}

export function FolderChip({ cwd, chat, onPick, readonly }: { cwd: string | null; chat: boolean; onPick?: (p: string | null, chat: boolean) => void; readonly?: boolean }) {
  const folders = useStore((s) => s.folders);
  const scratch = useStore((s) => s.scratch);
  const pickFolder = useStore((s) => s.pickFolder);
  const label = chat ? "No folder" : folderName(cwd, scratch);
  const tip = chat ? <TipBody title="No folder" desc="A plain chat: Emilie does not read or change files on your computer." />
    : cwd ? <TipBody title={cwd} desc={readonly ? "The folder this session works in." : "The folder Emilie works in. Click to choose another."} />
    : <TipBody title="Choose a folder" desc="Pick the project folder Emilie should work in." />;
  const trigger = (
    <Tip side="top" content={tip}>
      <MenuTrigger asChild>
        <button className={chip}>{chat ? <MessageSquare size={12} /> : <FolderSm size={12} />}<span className="max-w-[180px] truncate">{label}</span>{chev}</button>
      </MenuTrigger>
    </Tip>
  );
  if (readonly) {
    return (
      <Menu>
        {trigger}
        <MenuContent align="start" side="top" onCloseAutoFocus={refocus}>
          <MenuLabel>{cwd}</MenuLabel>
          {cwd && <MenuItem icon={<FolderOpen />} onSelect={() => openPath(cwd)}>Open in File Explorer</MenuItem>}
        </MenuContent>
      </Menu>
    );
  }
  return (
    <Menu>
      {trigger}
      <MenuContent align="start" side="top" className="max-h-[340px] min-w-[240px] overflow-y-auto" onCloseAutoFocus={refocus}>
        {folders.filter((f) => f.exists).slice(0, 12).map((f) => (
          <MenuItem key={f.path} icon={<FolderSm />} checked={!chat && cwd?.toLowerCase() === f.path.toLowerCase()} onSelect={() => onPick?.(f.path, false)}>
            <span title={f.path}>{f.name}</span>
          </MenuItem>
        ))}
        <MenuItem icon={<MessageSquare />} checked={chat} onSelect={() => onPick?.(null, true)}>No folder (chat)</MenuItem>
        <MenuSep />
        <MenuItem icon={<FolderOpen />} onSelect={async () => {
          const p = await pickFolder("Choose a folder");
          if (p) onPick?.(p, false);
        }}>Choose folder…</MenuItem>
      </MenuContent>
    </Menu>
  );
}

export function WorktreeToggle({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  return (
    <Tip side="top" content={<TipBody title="Worktree" desc="Work in a new git worktree on its own branch, so your current checkout stays untouched. It starts from the last commit: uncommitted changes are not copied." />}>
      <label className={cn(chip, "gap-[6px] hover:bg-transparent", on ? "text-text-100" : "text-text-400 hover:text-text-200")}>
        {/* the real checkbox stays for the keyboard; the box beside it shows a tick when it is on. Its focus must not
            reach the tooltip: a click focuses it, and the tooltip would pop up again on every click */}
        <input type="checkbox" checked={on} onChange={(e) => onChange(e.target.checked)} className="peer sr-only"
          onFocus={(e) => e.stopPropagation()} />
        <span className={cn("flex h-[12px] w-[12px] shrink-0 items-center justify-center rounded-[3px] border transition-colors",
          "peer-focus-visible:ring-1 peer-focus-visible:ring-accent",
          on ? "border-accent bg-accent text-white" : "border-border-400 bg-transparent")}>
          {on && <Check size={9} strokeWidth={3.2} />}
        </span>
        Worktree
      </label>
    </Tip>
  );
}

/** "gemini-3.7-flash Max": ONE chip, as in Claude: the model in white and the effort in grey, opening one picker
 *  with the models and the effort levels together (also Ctrl+Shift+I, /model and /effort). */
export function ModelEffortChip({ model, effort, onModel, onEffort }: { model: string; effort: string; onModel: (m: string) => void; onEffort: (e: string) => void }) {
  return <ModelChip value={model} onChange={onModel} effort={effort} onEffort={onEffort} />;
}

const cap = (s: string) => s.replace(/^./, (c) => c.toUpperCase());

/** The model picker. Given an effort, the chip shows it after the model and the picker has the effort levels under
 *  the list, like Claude's model menu (Ctrl+Shift+I opens it from anywhere the message box is). */
export function ModelChip({ value, onChange, effort, onEffort }: {
  value: string; onChange: (m: string) => void; effort?: string; onEffort?: (e: string) => void;
}) {
  const models = useStore((s) => s.models);
  const loadModels = useStore((s) => s.loadModels);
  const efforts = useStore((s) => s.state?.efforts || []);
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const withEffort = !!onEffort;
  useOpenOn("model", () => setOpen(true));
  useOpenOn("model-toggle", () => setOpen((o) => !o));
  useOpenOn("effort", () => withEffort && setOpen(true));   // /effort: the same picker, its effort row
  const level = efforts.find((e) => e.name === (effort || "medium"));
  const effortName = cap(effort || "medium");
  useEffect(() => {
    if (open && !models.loaded) loadModels();
    if (open) setTimeout(() => input.current?.focus(), 30);
  }, [open]);
  const rows = useMemo(() => {
    const ql = q.toLowerCase();
    return models.rows.filter((m) => !ql || m.id.toLowerCase().includes(ql)).slice(0, 300);
  }, [models.rows, q]);
  return (
    <Pop open={open} onOpenChange={setOpen}>
      <Tip side="top" hidden={open} content={withEffort
        ? <TipBody title={`${value || "No model chosen"} · ${effortName}`} keys="Ctrl+Shift+I"
            desc={`The model Emilie uses and how hard she thinks (${level ? level.desc : "effort"}). Click to change either.`} />
        : <TipBody title={value || "No model chosen"} desc="The model Emilie uses. Click to switch." />}>
        <PopTrigger asChild>
          <button className={cn(chip, "shrink")} aria-label={withEffort ? `Model ${value}, effort ${effortName}` : `Model ${value}`}>
            <span className="min-w-0 max-w-[190px] truncate">{prettyModel(value)}</span>
            {withEffort && <span className="shrink-0 text-text-400">{effortName}</span>}
          </button>
        </PopTrigger>
      </Tip>
      <PopContent align="end" side="top" className="w-[340px] p-0" onCloseAutoFocus={refocus}>
        <div className="flex items-center gap-2 border-b border-border-300 px-2.5">
          <SearchSm size={12} className="text-text-400" />
          <input ref={input} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search models"
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                const pick = rows[0]?.id || q.trim();
                if (pick) { onChange(pick); setOpen(false); }
              }
            }}
            className="h-[30px] flex-1 bg-transparent text-[12px] outline-none placeholder:text-text-500 selectable" />
          <Tip content="Reload the list from the provider">
            <button className="rounded p-1 text-text-400 hover:bg-hover hover:text-text-100" onClick={() => loadModels(true)}>
              {models.loading ? <Loader size={12} className="animate-spin" /> : <Refresh size={12} />}
            </button>
          </Tip>
        </div>
        <div className="max-h-[320px] overflow-y-auto p-1">
          {models.error && <div className="px-2 py-1 text-[11px] text-warn">{models.error}</div>}
          {rows.map((m) => (
            <button key={m.id} onClick={() => { onChange(m.id); setOpen(false); }}
              className={cn("flex h-[26px] w-full items-center gap-2 rounded-[5px] px-2 text-left text-text-100 hover:bg-active")}>
              <span className="min-w-0 flex-1 truncate text-[12px]" title={m.id}>{m.id}</span>
              {m.vision && <span title="Sees images"><Eye size={12} className="text-text-400" /></span>}
              {m.price && <span className="text-[10.5px] text-text-400">{m.price}</span>}
              {m.id === value && <Check size={12} />}
            </button>
          ))}
          {!rows.length && !models.loading && q.trim() && (
            <button onClick={() => { onChange(q.trim()); setOpen(false); }} className="h-[26px] w-full rounded-[5px] px-2 text-left text-[12px] hover:bg-active">
              Use “{q.trim()}”
            </button>
          )}
          {models.loading && !rows.length && <div className="px-2 py-2 text-[12px] text-text-400">Loading models…</div>}
        </div>
        {onEffort && efforts.length > 0 && (
          <div className="flex flex-col gap-[5px] border-t border-border-300 px-2.5 py-2">
            <div className="flex items-center gap-2">
              <span className="flex-1 text-[11px] text-text-400">Effort</span>
              <Segmented value={effort || "medium"} onChange={onEffort}
                options={efforts.map((e) => ({ value: e.name, label: cap(e.name) }))} />
            </div>
            {level && <div className="text-[10.5px] leading-snug text-text-500">{cap(level.desc)}</div>}
          </div>
        )}
        <div className="border-t border-border-300 px-2.5 py-1.5 text-[11px] text-text-400">
          <button className="hover:text-text-100" onClick={() => { setOpen(false); useStore.setState({ settingsOpen: "model" }); }}>Provider and API key…</button>
        </div>
      </PopContent>
    </Pop>
  );
}

export function ModeChip({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const m = MODES[value] || MODES.ask;
  const [open, setOpen] = useState(false);
  useOpenOn("mode", () => setOpen(true));
  useEffect(() => {
    if (!open) return;
    const keys = Object.keys(MODES);
    const f = (e: KeyboardEvent) => {
      const k = keys[Number(e.key) - 1];
      if (k && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); onChange(k); setOpen(false); }
    };
    window.addEventListener("keydown", f);
    return () => window.removeEventListener("keydown", f);
  }, [open, onChange]);
  return (
    <Menu open={open} onOpenChange={setOpen}>
      <Tip side="top" content={<TipBody title={m.label} keys="Shift+Tab" desc={m.desc + "."} />}>
        <MenuTrigger asChild>
          <button className={cn(chip, "ml-1")}>{m.label}</button>
        </MenuTrigger>
      </Tip>
      <MenuContent align="end" side="top" className="w-[300px]" onCloseAutoFocus={refocus}>
        <MenuLabel>Mode</MenuLabel>
        {Object.entries(MODES).map(([k, x], i) => (
          <MenuItem key={k} className="py-[5px]" onSelect={() => onChange(k)}>
            {/* one child: MenuItem wraps its children in a single span, so the row's own flex layout lives in here */}
            <div className="flex w-full items-start gap-3 whitespace-normal">
              <div className="flex min-w-0 flex-1 flex-col gap-px">
                <span className="text-[12.5px] text-text-000">{x.label}</span>
                <span className="text-[10.5px] leading-snug text-text-400">{x.desc}</span>
              </div>
              <span className="flex shrink-0 items-center gap-2 pt-px">
                {k === value && <Check size={13} className="text-accent" />}
                <span className="w-[8px] text-center text-[10.5px] text-text-500">{i + 1}</span>
              </span>
            </div>
          </MenuItem>
        ))}
      </MenuContent>
    </Menu>
  );
}

/** The ring on the right (in the accent colour): how full the context is, like the usage ring in Claude. */
export function ContextRing({ live, onCommand }: { live?: Live | null; onCommand?: (cmd: string) => void }) {
  const st = live?.status || {};
  const pct = Math.min(100, st.ctx_pct || 0);
  const r = 4.6, c = 2 * Math.PI * r;
  const confirm = useStore((s) => s.confirm);
  const [open, setOpen] = useState(false);
  useOpenOn("context", () => live && setOpen(true));
  const used = `${pct}% used · ${fmtTokens(st.ctx_tokens || 0)} of ${fmtTokens(st.ctx_limit || 0)} tokens`;
  const ring = (
    <svg width="13" height="13" viewBox="0 0 13 13">
      <circle cx="6.5" cy="6.5" r={r} fill="none" stroke="var(--ring)" strokeOpacity="0.28" strokeWidth="1.6" />
      {pct > 0 && (   /* nothing used yet (a new session): only the faint track, no arc */
        <circle cx="6.5" cy="6.5" r={r} fill="none" stroke="var(--ring)" strokeWidth="1.6" strokeLinecap="round"
          strokeDasharray={`${(pct / 100) * c} ${c}`} transform="rotate(-90 6.5 6.5)" style={{ transition: "stroke-dasharray .4s ease" }} />
      )}
    </svg>
  );
  if (!live) {
    return (
      <Tip side="top" content={<TipBody title="Context" desc="Empty: a new session starts with a fresh context." />}>
        <span className="ml-1.5 inline-flex h-[20px] w-[20px] items-center justify-center">{ring}</span>
      </Tip>
    );
  }
  const cps = st.checkpoints || [];
  return (
    <Pop open={open} onOpenChange={setOpen}>
      <Tip side="top" hidden={open} content={<TipBody title="Context" desc={used} />}>
        <PopTrigger asChild>
          <button className={cn(chip, "ml-1 w-[20px] justify-center px-0")} aria-label="Context">
            {ring}                                      {/* always the usage ring: it fills as the conversation grows, it does not spin while she works */}
          </button>
        </PopTrigger>
      </Tip>
      <PopContent align="end" side="top" className="w-[290px] p-3" onCloseAutoFocus={refocus}>
        <div className="mb-1.5 flex items-baseline justify-between">
          <span className="text-[12px] font-medium text-text-100">Context</span>
          <span className="text-[11px] text-text-400">{fmtTokens(st.ctx_tokens || 0)} / {fmtTokens(st.ctx_limit || 0)} · {pct}%</span>
        </div>
        <div className="h-1 overflow-hidden rounded-full bg-bg-400">
          <div className="h-full rounded-full bg-ring" style={{ width: `${pct}%` }} />
        </div>
        <p className="mt-1.5 text-[11px] text-text-400">The history is summarized automatically when it is full.</p>
        <div className="mt-2.5 grid grid-cols-3 gap-1.5 text-center">
          <Stat label="Input" value={fmtTokens(st.usage?.in || 0)} />
          <Stat label="Output" value={fmtTokens(st.usage?.out || 0)} />
          <Stat label="Calls" value={String(st.usage?.calls || 0)} />
        </div>
        <div className="mt-2.5 flex flex-wrap gap-1">
          {/* /context opens the Environment panel and /usage Settings → Usage (lib/slash.ts) */}
          {(["/compact", "/context", "/usage"] as const).map((cmd) => (
            <button key={cmd} className="h-[22px] rounded-[5px] border border-border-400 px-2 text-[11px] text-text-100 hover:bg-hover"
              onClick={() => { setOpen(false); onCommand?.(cmd); }}>
              {cmd === "/compact" ? "Compact now" : cmd === "/context" ? "Details" : "All usage"}
            </button>
          ))}
        </div>
        {cps.length > 0 && (
          <div className="mt-2.5 border-t border-border-300 pt-2">
            <div className="mb-1 text-[11px] font-medium text-text-400">Rewind (turns that changed files)</div>
            <div className="max-h-36 overflow-y-auto">
              {cps.slice(0, 12).map((cp) => (
                <button key={cp.n} className="flex h-[24px] w-full items-center gap-2 rounded-[5px] px-1.5 text-left text-[11.5px] hover:bg-hover"
                  onClick={async () => {
                    if (await confirm("Rewind?", `Go back to just before “${cp.label || "this turn"}”: ${cp.nfiles} file(s) are restored and the conversation after it is removed. Changes made with shell commands are not undone.`, { ok: "Rewind", danger: true }))
                      onCommand?.(`/rewind ${cp.n} both`);
                  }}>
                  <Rewind size={12} className="shrink-0 text-text-400" />
                  <span className="min-w-0 flex-1 truncate">{cp.label || "(turn)"}</span>
                  <span className="text-[10.5px] text-text-400">{cp.nfiles} file{cp.nfiles === 1 ? "" : "s"}</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </PopContent>
    </Pop>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[6px] bg-bg-300 py-1">
      <div className="text-[12px] text-text-100">{value}</div>
      <div className="text-[10px] text-text-400">{label}</div>
    </div>
  );
}

export { folderName };
