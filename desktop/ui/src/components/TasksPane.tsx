// The Tasks panel: what is running beside the conversation. Background processes (dev servers, watchers, slow builds the
// agent started with bash_bg) with their live output and a stop button, and the sub-agents of this session.
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { post } from "@/lib/api";
import { highlight } from "@/lib/markdown";
import { currentLive, useStore } from "@/lib/store";
import type { Item } from "@/lib/types";
import { cn } from "@/lib/util";
import { ChevR } from "./icons";
import { childWords, Markdown } from "./Transcript";

interface Task { id: number; command: string; running: boolean; code: number | null; seconds: number; url: string; last: string; output?: string }
type Agent = Extract<Item, { kind: "tool" }>;

const clock = (s: number) => (s < 60 ? `${s}s` : s < 3600 ? `${Math.floor(s / 60)}m ${s % 60}s` : `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`);

function openInBrowser(url: string) {
  const st = useStore.getState();
  const tabs = st.paneTabs;
  useStore.setState({
    paneTabs: tabs.some((t) => t.key === "browser") ? tabs : [...tabs, { key: "browser", kind: "browser", title: "Browser" }],
    paneActive: "browser", pane: "browser", browserGo: { url, n: (st.browserGo?.n || 0) + 1 },
  });
}

function Dot({ tone }: { tone: "run" | "ok" | "bad" }) {
  return <span className={cn("h-[6px] w-[6px] shrink-0 rounded-full", tone === "run" ? "bg-accent animate-pulse" : tone === "ok" ? "bg-ok" : "bg-danger")} />;
}

// What a tool prints, coloured by what each part is: addresses, errors, warnings, success marks, numbers, "> script" lines.
const PARTS = /(https?:\/\/[^\s"'<>)]+)|(\b(?:errors?|failed|failure|fatal|exception|traceback|ERR!)\b)|(\b(?:warn(?:ing)?s?|deprecated)\b)|([✓✔➜→]|\b(?:ready|success(?:fully)?|compiled|passed|done)\b)|(\b\d+(?:\.\d+)*(?:ms|s|kB|MB|%)?\b)/gi;
const TONE = ["", "text-link", "text-danger", "text-warn", "text-ok", "text-accent"];

function colorLine(line: string): React.ReactNode {
  const prompt = line.match(/^(\s*[>$] )(.*)$/);                  // "> vite", "> pkg@1.0.0 dev": a command npm echoed
  if (prompt) return <><span className="text-text-500">{prompt[1]}</span><span dangerouslySetInnerHTML={{ __html: highlight(prompt[2], "bash") }} /></>;
  const out: React.ReactNode[] = [];
  let last = 0;
  for (const m of line.matchAll(PARTS)) {
    const i = m.index!;
    if (i > last) out.push(line.slice(last, i));
    out.push(<span key={i} className={TONE[m.slice(1).findIndex((g) => g !== undefined) + 1]}>{m[0]}</span>);
    last = i + m[0].length;
  }
  out.push(line.slice(last));
  return out;
}

/** A task's output: follows the newest line unless you scrolled up. */
function Output({ text }: { text: string }) {
  const box = useRef<HTMLPreElement>(null);
  const stick = useRef(true);
  useLayoutEffect(() => { const el = box.current; if (el && stick.current) el.scrollTop = el.scrollHeight; }, [text]);
  return (
    <pre ref={box} onScroll={() => { const el = box.current!; stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 8; }}
      className="max-h-[260px] overflow-auto border-t border-border-200 bg-bg-100 px-3 py-2 font-mono text-[10.5px] leading-[15px] text-text-200 whitespace-pre-wrap break-words selectable">
      {text ? text.split("\n").map((l, i) => <div key={i}>{l ? colorLine(l) : "\u00a0"}</div>) : "(no output yet)"}
    </pre>
  );
}

export function TasksPane() {
  const wid = useStore((st) => currentLive(st)?.wid || "");
  const closed = useStore((st) => !!currentLive(st)?.closed);
  const items = useStore((st) => currentLive(st)?.items);
  const [tasks, setTasks] = useState<Task[] | null>(null);
  const [open, setOpen] = useState(0);
  const [openAgent, setOpenAgent] = useState("");
  const openRef = useRef(0);
  openRef.current = open;

  const ask = async (extra: { stop?: number } = {}) => {
    if (!wid) return;
    try {
      const r = await post<{ tasks: Task[] }>("/api/session/bg", { wid, open: openRef.current, ...extra });
      setTasks(r.tasks || []);
    } catch (e: any) {
      if (extra.stop) useStore.getState().toast(e.message, "error");
      setTasks((t) => t || []);
    }
  };
  // one request at a time, every second while the panel is open (resting while the app is hidden)
  useEffect(() => {
    if (!wid || closed) { setTasks([]); return; }
    let dead = false, timer = 0;
    const tick = async () => {
      if (!document.hidden) await ask();
      if (!dead) timer = window.setTimeout(tick, 1000);
    };
    tick();
    return () => { dead = true; clearTimeout(timer); };
  }, [wid, closed]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (open) ask(); }, [open]);   // eslint-disable-line react-hooks/exhaustive-deps

  const agents = useMemo(() => ((items || []).filter((i) => i.kind === "tool" && (i.name === "task" || i.name === "tasks")) as Agent[]).reverse(), [items]);
  const running = (tasks || []).filter((t) => t.running).length;
  const busyAgents = agents.filter((a) => a.status === "running").length;

  return (
    <div className="h-full overflow-y-auto px-2.5 pb-3 pt-1 text-[11.5px]">
      <Heading title="Background processes" note={running ? `${running} running` : ""} />
      {tasks === null && <Hint>Loading…</Hint>}
      {tasks !== null && !tasks.length && <Hint>Nothing running. Ask Emilie to start a dev server or a watcher and it shows up here.</Hint>}
      {!!tasks?.length && (
        <Card>
          {tasks.map((t, i) => (
            <div key={t.id} className={cn(i > 0 && "border-t border-border-200")}>
              <div role="button" onClick={() => setOpen(open === t.id ? 0 : t.id)} className="flex min-w-0 items-center gap-2 px-3 py-[7px] hover:bg-hover/50">
                <Dot tone={t.running ? "run" : t.code === 0 ? "ok" : "bad"} />
                <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-text-100" title={t.command}>
                  <span className="select-none text-text-500">$ </span><span dangerouslySetInnerHTML={{ __html: highlight(t.command, "bash") }} />
                </span>
                <span className="shrink-0 tabular-nums text-[10.5px] text-text-500">{t.running ? clock(t.seconds) : `exit ${t.code} · ${clock(t.seconds)}`}</span>
                {t.running && (
                  <button onClick={(e) => { e.stopPropagation(); ask({ stop: t.id }); }}
                    className="shrink-0 rounded-[5px] px-1.5 text-[10.5px] leading-[17px] text-text-300 hover:bg-danger/10 hover:text-danger">Stop</button>
                )}
                <Chevron on={open === t.id} />
              </div>
              {t.url && (
                <div className="flex min-w-0 items-center gap-2 pb-[7px] pl-[26px] pr-3 text-[11px]">
                  <button onClick={() => openInBrowser(t.url)} title="Open in the Browser panel" className="min-w-0 truncate text-link underline-offset-2 hover:underline">{t.url}</button>
                </div>
              )}
              {open !== t.id && !t.url && t.last && <div className="truncate pb-[7px] pl-[26px] pr-3 font-mono text-[10.5px] text-text-500">{colorLine(t.last)}</div>}
              {open === t.id && <Output text={t.output || ""} />}
            </div>
          ))}
        </Card>
      )}

      <Heading title="Sub-agents" note={busyAgents ? `${busyAgents} running` : ""} />
      {!agents.length && <Hint>No sub-agent has run in this session.</Hint>}
      <div className="flex flex-col gap-2">
        {agents.map((a) => <AgentCard key={a.id} a={a} on={openAgent === a.id} toggle={() => setOpenAgent(openAgent === a.id ? "" : a.id)} />)}
      </div>
    </div>
  );
}

function Heading({ title, note }: { title: string; note: string }) {
  return (
    <div className="flex items-center gap-2 px-1 pb-1.5 pt-2.5 text-[11.5px] text-text-300">
      <span className="flex-1">{title}</span>
      {note && <span className="text-[10.5px] text-accent">{note}</span>}
    </div>
  );
}

const Hint = ({ children }: { children: React.ReactNode }) => <div className="px-1 py-0.5 text-[11px] leading-[16px] text-text-500">{children}</div>;
const Card = ({ children }: { children: React.ReactNode }) => <div className="overflow-hidden rounded-[9px] border border-border-300 bg-bg-200/40">{children}</div>;
const Chevron = ({ on }: { on: boolean }) => <ChevR size={10} className={cn("shrink-0 text-text-500 transition-transform duration-150", on && "rotate-90")} />;

/** One sub-agent run: its task(s), then, when opened, what it did (one row per step) and its report. */
function AgentCard({ a, on, toggle }: { a: Agent; on: boolean; toggle: () => void }) {
  const live = a.status === "running";
  // the first lines of the steps only repeat the tasks it was given ("sub-agent: …")
  const steps = (a.children || []).filter((c) => !/^sub-agent/i.test(c.label || ""));
  const tasks = (a.children || []).filter((c) => /^sub-agent/i.test(c.label || "")).map((c) => String(c.label).replace(/^sub-agent:?\s*/i, "") || c.target || "");
  const title = String(a.input?.description || tasks.filter(Boolean).join(", ") || a.target || "Sub-agent");
  const [allSteps, setAllSteps] = useState(false);
  const shown = allSteps ? steps : steps.slice(0, 6);
  return (
    <Card>
      <div role="button" onClick={toggle} className="flex min-w-0 items-center gap-2 px-3 py-[7px] hover:bg-hover/50">
        <Dot tone={live ? "run" : a.status === "ok" ? "ok" : "bad"} />
        <span className={cn("min-w-0 flex-1 truncate text-text-100", live && "shimmer-text")} title={title}>{title}</span>
        <span className="shrink-0 text-[10.5px] text-text-500">{live ? "running" : a.status === "ok" ? "done" : a.status}{steps.length ? ` · ${steps.length} steps` : ""}</span>
        <Chevron on={on} />
      </div>
      {on && (
        <>
          {!!steps.length && (
            <div className="border-t border-border-200 bg-bg-100/40">
              {shown.map((c, i) => {
                const w = childWords(c);
                return (
                  <div key={i} className={cn("flex min-w-0 items-baseline gap-1.5 py-[4px] pl-[26px] pr-3 text-[11px]", i > 0 && "border-t border-border-200")} title={w.full}>
                    <span className="shrink-0 text-text-400">{w.verb}</span><span className="min-w-0 truncate text-text-100">{w.subject}</span>
                  </div>
                );
              })}
              {steps.length > 6 && (
                <button onClick={() => setAllSteps(!allSteps)} className="w-full border-t border-border-200 py-[4px] pl-[26px] pr-3 text-left text-[10.5px] text-text-400 hover:text-text-100">
                  {allSteps ? "Show fewer steps" : `Show ${steps.length - 6} more steps`}
                </button>
              )}
            </div>
          )}
          {a.output
            ? <div className="max-h-[360px] overflow-auto border-t border-border-200 px-3 py-2"><Markdown text={String(a.output)} className="text-[12px]" /></div>
            : !steps.length && <div className="border-t border-border-200 px-3 py-2 text-[11px] text-text-500">No details yet.</div>}
        </>
      )}
    </Card>
  );
}
