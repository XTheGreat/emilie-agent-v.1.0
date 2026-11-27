// The Activity panel: every tool the agent ran in this session, newest first, with how it ended and how long it took.
// Filter to the commands, the file changes or the failures; open one for what went in and what came out.
import { useMemo, useState } from "react";
import { currentLive, useStore } from "@/lib/store";
import type { Item } from "@/lib/types";
import { cn } from "@/lib/util";
import { insertIntoComposer } from "./Composer";
import { ChevR } from "./icons";
import { DiffView } from "./Transcript";

type Tool = Extract<Item, { kind: "tool" }>;
type Filter = "all" | "run" | "edit" | "bad";

const RUN = new Set(["bash", "bash_bg", "bg_output", "bg_stop", "notebook_run"]);
const EDIT = new Set(["write_file", "edit_file", "notebook_edit", "docx_edit", "docx_create", "xlsx_write"]);
const FILTERS: [Filter, string][] = [["all", "All"], ["run", "Commands"], ["edit", "Edits"], ["bad", "Failed"]];
const NONE: Item[] = [];

const failed = (t: Tool) => t.status === "error" || t.status === "denied" || t.status === "interrupted";
const fits = (t: Tool, f: Filter) => f === "all" || (f === "run" ? RUN.has(t.name) : f === "edit" ? EDIT.has(t.name) : failed(t));
const took = (s: number) => (s < 1 ? `${Math.round(s * 1000)} ms` : s < 60 ? `${s.toFixed(1)} s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`);
const subject = (t: Tool) => String(t.input?.command || t.target || "");
const inputText = (t: Tool) => (typeof t.input?.command === "string" ? t.input.command
  : t.input && Object.keys(t.input).length ? JSON.stringify(t.input, null, 2) : "");

/** What went wrong or came out, put in the message being written. Long output keeps its end, where errors are. */
function attach(t: Tool) {
  const out = String(t.output || "");
  const tail = out.length > 2000 ? "…" + out.slice(-2000) : out;
  insertIntoComposer(`\n${t.label || t.name}: ${subject(t)} (${t.status})\n\`\`\`\n${tail || "(no output)"}\n\`\`\`\n`);
}

const copy = (text: string) => navigator.clipboard.writeText(text)
  .then(() => useStore.getState().toast("Copied"))
  .catch(() => useStore.getState().toast("Could not copy", "error"));

export function ActivityPane() {
  const items = useStore((st) => currentLive(st)?.items || NONE);
  const closed = useStore((st) => !!currentLive(st)?.closed);
  const [filter, setFilter] = useState<Filter>("all");
  const [open, setOpen] = useState("");

  const tools = useMemo(() => (items.filter((i) => i.kind === "tool") as Tool[]).reverse(), [items]);
  const shown = tools.filter((t) => fits(t, filter));
  const bad = tools.filter(failed).length;
  const secs = tools.reduce((a, t) => a + (t.secs || 0), 0);

  const btn = "rounded-[5px] border border-border-300 px-2 py-[2px] text-[11px] text-text-200 hover:bg-hover hover:text-text-000 disabled:opacity-40";

  return (
    <div className="flex h-full flex-col text-[11.5px]">
      <div className="px-2.5 pt-2">
        <div className="flex flex-wrap items-center gap-1">
          {FILTERS.map(([k, label]) => (
            <button key={k} aria-pressed={filter === k} onClick={() => setFilter(k)}
              className={cn("rounded-[5px] px-2 py-[2px] text-[11px]", filter === k ? "bg-active text-text-000" : "text-text-400 hover:bg-hover hover:text-text-100")}>{label}</button>
          ))}
        </div>
        <div className="px-1 py-1.5 text-[11px] text-text-500">
          {tools.length} step{tools.length === 1 ? "" : "s"}{secs >= 0.1 && ` · ${took(secs)} in tools`}
          {!!bad && <span className="text-danger"> · {bad} failed</span>}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2.5 pb-3">
        {!shown.length && (
          <div className="px-1 text-[11px] leading-[16px] text-text-500">
            {tools.length ? "Nothing matches this filter." : "Nothing yet. Each command, file read and edit Emilie runs shows up here."}
          </div>
        )}
        {!!shown.length && (
          <div className="overflow-hidden rounded-[9px] border border-border-300 bg-bg-200/40">
            {shown.map((t, i) => {
              const on = open === t.id;
              const input = on ? inputText(t) : "";
              return (
                <div key={t.id} className={cn(i > 0 && "border-t border-border-200")}>
                  <div role="button" onClick={() => setOpen(on ? "" : t.id)} className="flex min-w-0 items-center gap-2 px-3 py-[6px] hover:bg-hover/50">
                    <span title={t.status} className={cn("shrink-0", failed(t) ? "text-danger" : "text-text-400", t.status === "running" && "shimmer-text")}>{t.label || t.name}</span>
                    <span className="min-w-0 flex-1 truncate font-mono text-[10.5px] text-text-100" title={subject(t)}>{subject(t)}</span>
                    {t.secs !== undefined && <span className="shrink-0 tabular-nums text-[10.5px] text-text-500">{took(t.secs)}</span>}
                    <ChevR size={10} className={cn("shrink-0 text-text-500 transition-transform duration-150", on && "rotate-90")} />
                  </div>
                  {on && (
                    <div className="border-t border-border-200 bg-bg-100">
                      {input && !t.diff?.text && <pre className="max-h-[160px] overflow-auto whitespace-pre-wrap break-words px-3 py-2 font-mono text-[10.5px] leading-[15px] text-text-300 selectable">{input}</pre>}
                      {t.diff?.text ? <DiffView diff={t.diff} file={t.target} /> : null}
                      <pre className="max-h-[260px] overflow-auto whitespace-pre-wrap break-words border-t border-border-200 px-3 py-2 font-mono text-[10.5px] leading-[15px] text-text-200 selectable">
                        {t.output || (t.status === "running" ? "Still running…" : "(no output)")}
                      </pre>
                      <div className="flex flex-wrap items-center justify-end gap-2 border-t border-border-200 px-3 py-2">
                        {RUN.has(t.name) && !!t.input?.command && <button className={btn} onClick={() => copy(String(t.input.command))}>Copy command</button>}
                        <button className={btn} disabled={!t.output} onClick={() => copy(String(t.output))}>Copy output</button>
                        <button className={btn} disabled={closed} onClick={() => attach(t)}>Attach to chat</button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
