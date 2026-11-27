// What the project panels share (Git, Scripts, Problems, Tests, HTTP, Ports, Notes, Database): the look of their
// headings, cards, buttons and fields (the same as the Tasks / Search panels), following a background job on the
// server, and "Ask Emilie": a request sent to the session on screen (or put in the message box when there is none).
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { get } from "@/lib/api";
import { currentLive, useStore } from "@/lib/store";
import { cn } from "@/lib/util";
import { insertIntoComposer } from "./Composer";
import { ChevR, SearchSm, X } from "./icons";
import { colorLine } from "./TasksPane";
import { Tip } from "./ui";

// ------------------------------------------------------------------ look
export const btnSm = "inline-flex h-[20px] shrink-0 items-center gap-1 rounded-[5px] border border-border-300 px-2 text-[11px] text-text-200 hover:bg-hover hover:text-text-000 disabled:pointer-events-none disabled:opacity-40";
export const btnPrimary = "btn-contrast inline-flex h-[22px] shrink-0 items-center gap-1 rounded-[5px] px-2.5 text-[11px]";
export const btnIcon = "flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-[5px] text-text-300 hover:bg-hover hover:text-text-000 disabled:pointer-events-none disabled:opacity-35";
export const rowCls = "group flex min-w-0 items-center gap-2 px-3 hover:bg-hover/50";

export function Heading({ title, note, right, open, onToggle }: {
  title: React.ReactNode; note?: React.ReactNode; right?: React.ReactNode; open?: boolean; onToggle?: () => void;
}) {
  return (
    <div className="flex min-h-[26px] items-center gap-1.5 px-1 pb-1 pt-2 text-[11.5px] text-text-300">
      {onToggle ? (
        <button onClick={onToggle} className="flex min-w-0 flex-1 items-center gap-1 text-left hover:text-text-100">
          <ChevR size={10} className={cn("shrink-0 text-text-500 transition-transform duration-150", open && "rotate-90")} />
          <span className="truncate">{title}</span>
          {note !== undefined && note !== "" && <span className="shrink-0 tabular-nums text-[10.5px] text-text-500">{note}</span>}
        </button>
      ) : (
        <span className="flex min-w-0 flex-1 items-center gap-1.5">
          <span className="truncate">{title}</span>
          {note !== undefined && note !== "" && <span className="shrink-0 tabular-nums text-[10.5px] text-text-500">{note}</span>}
        </span>
      )}
      {right && <span className="flex shrink-0 items-center gap-0.5">{right}</span>}
    </div>
  );
}

export const Hint = ({ children, className }: { children: React.ReactNode; className?: string }) =>
  <div className={cn("px-1 py-0.5 text-[11px] leading-[16px] text-text-500", className)}>{children}</div>;

export const Card = ({ children, className }: { children: React.ReactNode; className?: string }) =>
  <div className={cn("shrink-0 overflow-hidden rounded-[9px] border border-border-300 bg-bg-200/40", className)}>{children}</div>;

export const Chevron = ({ on }: { on: boolean }) =>
  <ChevR size={10} className={cn("shrink-0 text-text-500 transition-transform duration-150", on && "rotate-90")} />;

export function IconBtn({ tip, onClick, children, disabled, active, danger, className }: {
  tip: string; onClick?: (e: React.MouseEvent) => void; children: React.ReactNode; disabled?: boolean; active?: boolean; danger?: boolean; className?: string;
}) {
  return (
    <Tip content={tip}>
      <button aria-label={tip} disabled={disabled} onClick={(e) => { e.stopPropagation(); onClick?.(e); }}
        className={cn(btnIcon, active && "bg-active text-text-000", danger && "hover:bg-danger/10 hover:text-danger", className)}>
        {children}
      </button>
    </Tip>
  );
}

/** A small button that shows on a row while the pointer is over it (always there for the keyboard). */
export function RowBtn({ tip, onClick, children, danger }: { tip: string; onClick: () => void; children: React.ReactNode; danger?: boolean }) {
  return (
    <Tip content={tip}>
      <button aria-label={tip} onClick={(e) => { e.stopPropagation(); onClick(); }}
        className={cn("flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-[4px] text-text-400 opacity-0 hover:bg-hover hover:text-text-000 focus-visible:opacity-100 group-hover:opacity-100",
          danger && "hover:text-danger")}>
        {children}
      </button>
    </Tip>
  );
}

export function Pill({ on, onClick, children, title }: { on: boolean; onClick: () => void; children: React.ReactNode; title?: string }) {
  return (
    <button aria-pressed={on} onClick={onClick} title={title}
      className={cn("inline-flex h-[20px] items-center gap-1 rounded-[5px] px-2 text-[11px]", on ? "bg-active text-text-000" : "text-text-400 hover:bg-hover hover:text-text-100")}>
      {children}
    </button>
  );
}

export function SearchField({ value, onChange, placeholder, autoFocus, onEnter, children }: {
  value: string; onChange: (v: string) => void; placeholder: string; autoFocus?: boolean; onEnter?: () => void; children?: React.ReactNode;
}) {
  return (
    <div className="flex min-w-0 flex-1 items-center gap-1 rounded-[7px] border border-border-300 bg-bg-200/40 py-[2px] pl-2 pr-1 focus-within:border-border-400">
      <SearchSm size={11} className="shrink-0 text-text-500" />
      <input autoFocus={autoFocus} value={value} onChange={(e) => onChange(e.target.value)} spellCheck={false} placeholder={placeholder}
        onKeyDown={(e) => { if (e.key === "Enter") onEnter?.(); if (e.key === "Escape" && value) { e.stopPropagation(); onChange(""); } }}
        className="h-[20px] min-w-0 flex-1 bg-transparent px-1 text-[11.5px] text-text-100 outline-none placeholder:text-text-500 selectable" />
      {value && <button aria-label="Clear" onClick={() => onChange("")} className="shrink-0 rounded p-0.5 text-text-500 hover:text-text-100"><X size={10} /></button>}
      {children}
    </div>
  );
}

/** A panel with nothing to show yet: an icon, a line, what to do. */
export function Empty({ icon, title, children, action }: { icon: React.ReactNode; title: string; children?: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="flex h-full min-h-[180px] flex-col items-center justify-center gap-2 px-6 text-center">
      <span className="text-text-500">{icon}</span>
      <div className="mt-1 text-[12.5px] font-medium text-text-100">{title}</div>
      {children && <div className="max-w-[300px] text-[11.5px] leading-[16px] text-text-400">{children}</div>}
      {action && <div className="mt-2 flex flex-wrap justify-center gap-2">{action}</div>}
    </div>
  );
}

/** Output of a command: coloured like the Tasks panel's, follows the newest line unless you scrolled up. */
export function Output({ lines, className, empty = "(no output yet)" }: { lines: string[]; className?: string; empty?: string }) {
  const box = useRef<HTMLPreElement>(null);
  const stick = useRef(true);
  useLayoutEffect(() => { const el = box.current; if (el && stick.current) el.scrollTop = el.scrollHeight; }, [lines]);
  const shown = lines.length > 1500 ? lines.slice(-1500) : lines;
  return (
    <pre ref={box} onScroll={() => { const el = box.current!; stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 8; }}
      className={cn("max-h-[260px] overflow-auto whitespace-pre-wrap break-words bg-bg-100 px-3 py-2 font-mono text-[10.5px] leading-[15px] text-text-200 selectable", className)}>
      {shown.length ? shown.map((l, i) => <div key={i}>{l ? colorLine(stripAnsi(l)) : " "}</div>) : <span className="text-text-500">{empty}</span>}
    </pre>
  );
}

// ------------------------------------------------------------------ helpers
export const stripAnsi = (s: string) => s.replace(/\x1b\[[\d;?]*[A-Za-z]|\x1b\][^\x07]*\x07/g, "");

export const plural = (n: number, one: string, many = one + "s") => `${n} ${n === 1 ? one : many}`;

export function took(s: number): string {
  return s < 1 ? `${Math.round(s * 1000)} ms` : s < 60 ? `${s.toFixed(1)} s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
}

export function agoSecs(at: number): string {
  const s = Math.max(0, Math.floor(Date.now() / 1000 - at));
  return s < 10 ? "just now" : s < 60 ? `${s}s ago` : s < 3600 ? `${Math.floor(s / 60)} min ago` : `${Math.floor(s / 3600)} h ago`;
}

export function fmtBytes(n: number): string {
  return n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(n < 10240 ? 1 : 0)} KB` : `${(n / 1048576).toFixed(1)} MB`;
}

export const copy = (text: string, what = "Copied") => navigator.clipboard.writeText(text)
  .then(() => useStore.getState().toast(what))
  .catch(() => useStore.getState().toast("Could not copy", "error"));

/** "a/b/c.ts" -> ["c.ts", "a/b"] */
export function splitPath(p: string): [string, string] {
  const i = p.lastIndexOf("/");
  return i < 0 ? [p, ""] : [p.slice(i + 1), p.slice(0, i)];
}

/** Hand a request to Emilie: sent to the session on screen; with none open it waits in the message box of a new one. */
export function askEmilie(text: string) {
  const st = useStore.getState();
  const live = currentLive(st);
  if (live && !live.closed) {
    st.send(live.wid, text, [], []);
    st.toast(live.busy ? "Queued for Emilie" : "Sent to Emilie");
  } else {
    insertIntoComposer(text);
    st.toast("Put in the message box: press Enter to send it");
  }
}

/** The tail of some output, fenced for a message. */
export function fence(text: string, max = 3000): string {
  const t = stripAnsi(text).trimEnd();
  const cut = t.length > max ? "…" + t.slice(-max) : t;
  return "```\n" + cut.replace(/```/g, "``​`") + "\n```";
}

// ------------------------------------------------------------------ background jobs (/api/job)
export interface JobInfo<R = any> {
  id: string; kind: string; running: boolean; secs: number; n: number; lines: string[]; result: R | null; error: string;
  stopped: boolean; gone?: boolean;
}

/** Follow a job: its output as it comes, then its result. onDone runs once when it has ended. */
export function useJob<R = any>(id: string | null, onDone?: (j: JobInfo<R>) => void): { job: JobInfo<R> | null; lines: string[] } {
  const [job, setJob] = useState<JobInfo<R> | null>(null);
  const [lines, setLines] = useState<string[]>([]);
  const done = useRef(onDone);
  done.current = onDone;
  useEffect(() => {
    setJob(null);
    setLines([]);
    if (!id) return;
    let dead = false, timer = 0, n = 0;
    const tick = async () => {
      try {
        const j = await get<JobInfo<R>>("/api/job", { id, since: n });
        if (dead) return;
        n = j.n;
        if (j.lines.length) setLines((l) => { const m = l.concat(j.lines); return m.length > 4000 ? m.slice(-4000) : m; });
        setJob(j);
        if (!j.running) { done.current?.(j); return; }
      } catch (e: any) {
        if (dead) return;
        setJob({ id, kind: "", running: false, secs: 0, n, lines: [], result: null, error: e.message || "lost the run", stopped: false, gone: true });
        return;
      }
      timer = window.setTimeout(tick, document.hidden ? 1500 : 450);
    };
    tick();
    return () => { dead = true; clearTimeout(timer); };
  }, [id]);
  return { job, lines };
}

/** The panels remember what they showed per project folder while the app runs (closing a panel keeps it). */
export function remember<T>(map: Map<string, T>, key: string, make: () => T): T {
  let v = map.get(key);
  if (v === undefined) { v = make(); map.set(key, v); }
  return v;
}

/** Refresh when the window comes back into focus, and when Emilie finishes a turn in this folder. */
export function useRefreshOn(cwd: string, refresh: () => void) {
  const fn = useRef(refresh);
  fn.current = refresh;
  const busy = useStore((s) => Object.values(s.lives).some((l) => l.cwd === cwd && l.busy));
  const first = useRef(true);
  useEffect(() => {
    if (first.current) { first.current = false; return; }
    if (!busy) fn.current();
  }, [busy]);
  useEffect(() => {
    const f = () => fn.current();
    window.addEventListener("focus", f);
    return () => window.removeEventListener("focus", f);
  }, []);
}
