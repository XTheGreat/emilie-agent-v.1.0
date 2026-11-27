// The Problems panel: the project's own type checkers and linters (TypeScript, ESLint, Ruff, mypy, Pyright, Flake8,
// cargo check, go vet, and a built-in Python syntax check), run with one click and read into one list grouped by
// file. A click opens the file at the line; one problem, a file's, or all of them can be handed to Emilie to fix.
import { useEffect, useMemo, useState } from "react";
import { get, post } from "@/lib/api";
import { useStore } from "@/lib/store";
import { cn } from "@/lib/util";
import * as I from "./icons";
import {
  agoSecs, askEmilie, btnPrimary, btnSm, Card, Chevron, Empty, Heading, Hint, Output, Pill, plural, remember,
  RowBtn, rowCls, SearchField, splitPath, took, useJob,
} from "./PaneKit";
import { Spinner, Tip } from "./ui";

interface Checker { id: string; kind: string; label: string; dir: string; cmd: string }
interface Problem { file: string; abs: string; line: number; col: number; severity: "error" | "warning" | "info"; message: string; code: string; source: string }
interface Result { id: string; kind: string; label: string; dir: string; problems: Problem[]; code: number; secs: number; tail: string; error: string }
interface Run { results: Result[]; pending: string[]; at?: number }
type Sev = "all" | "error" | "warning";

interface Mem { off: Record<string, boolean>; job: string | null; run: Run | null; at: number; q: string; sev: Sev }
const mem = new Map<string, Mem>();
const SEV_ICON = {
  error: <I.CircleX size={12} className="shrink-0 text-danger" />,
  warning: <I.Alert size={12} className="shrink-0 text-warn" />,
  info: <I.Info size={12} className="shrink-0 text-link" />,
};
const where = (c: { label: string; dir: string }) => c.label + (c.dir ? ` · ${c.dir}` : "");

function brief(p: Problem): string {
  return `${p.file}:${p.line}${p.col ? `:${p.col}` : ""} ${p.severity} ${p.code ? `[${p.code}] ` : ""}(${p.source}): ${p.message}`;
}

export function ProblemsPane({ cwd }: { cwd: string }) {
  const m = remember(mem, cwd, (): Mem => {
    let off: Record<string, boolean> = {};
    try { off = JSON.parse(localStorage.getItem("emilie.problems.off:" + cwd) || "{}"); } catch { /* none */ }
    return { off, job: null, run: null, at: 0, q: "", sev: "all" };
  });
  const toast = useStore((s) => s.toast);
  const [checkers, setCheckers] = useState<Checker[] | null>(null);
  const [err, setErr] = useState("");
  const [off, setOffState] = useState(m.off);
  const [jobId, setJobId] = useState<string | null>(m.job);
  const [run, setRun] = useState<Run | null>(m.run);
  const [q, setQ] = useState(m.q);
  const [sev, setSev] = useState<Sev>(m.sev);
  const [shut, setShut] = useState<Record<string, boolean>>({});
  const [showOut, setShowOut] = useState("");
  const [, tick] = useState(0);
  useEffect(() => { m.q = q; m.sev = sev; }, [q, sev]);   // eslint-disable-line react-hooks/exhaustive-deps

  const detect = () => get<{ checkers: Checker[] }>("/api/problems/checkers", { cwd }).then((r) => { setCheckers(r.checkers); setErr(""); }).catch((e) => setErr(e.message));
  useEffect(() => { if (cwd) detect(); }, [cwd]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { const t = window.setInterval(() => tick((n) => n + 1), 30000); return () => clearInterval(t); }, []);

  const setOff = (id: string, v: boolean) => {
    const n = { ...off, [id]: v };
    m.off = n;
    setOffState(n);
    try { localStorage.setItem("emilie.problems.off:" + cwd, JSON.stringify(n)); } catch { /* private window */ }
  };
  const { job, lines } = useJob<Run>(jobId, (j) => {
    m.job = null;
    if (j.result) { m.run = j.result; m.at = Date.now() / 1000; setRun(j.result); }
    if (j.error && j.error !== "Stopped") toast(j.error, "error");
  });
  useEffect(() => { if (job?.running && job.result) setRun(job.result); }, [job]);   // results come in as each checker finishes
  const running = !!job?.running || (!!jobId && !job);

  const start = async (ids?: string[]) => {
    const chosen = ids || (checkers || []).filter((c) => !off[c.id]).map((c) => c.id);
    if (!chosen.length) { toast("Choose at least one checker", "error"); return; }
    try {
      const r = await post<{ job: string }>("/api/problems/run", { cwd, ids: chosen });
      m.job = r.job;
      setJobId(r.job);
    } catch (e: any) {
      toast(e.message, "error");
    }
  };

  const all = useMemo(() => (run?.results || []).flatMap((r) => r.problems), [run]);
  const counts = useMemo(() => ({
    error: all.filter((p) => p.severity === "error").length, warning: all.filter((p) => p.severity === "warning").length,
    info: all.filter((p) => p.severity === "info").length,
  }), [all]);
  const files = useMemo(() => {
    const ql = q.trim().toLowerCase();
    const shown = all.filter((p) => (sev === "all" || p.severity === sev) && (!ql || p.message.toLowerCase().includes(ql)
      || p.file.toLowerCase().includes(ql) || p.code.toLowerCase().includes(ql)));
    const by = new Map<string, Problem[]>();
    for (const p of shown) { const l = by.get(p.file) || []; l.push(p); by.set(p.file, l); }
    const rank = (ps: Problem[]) => (ps.some((p) => p.severity === "error") ? 0 : 1);
    return [...by.entries()].map(([file, ps]) => ({ file, abs: ps[0].abs, ps: ps.sort((a, b) => a.line - b.line || a.col - b.col) }))
      .sort((a, b) => rank(a.ps) - rank(b.ps) || a.file.localeCompare(b.file));
  }, [all, q, sev]);
  const failedTools = (run?.results || []).filter((r) => r.error);

  const fixOne = (p: Problem) => askEmilie(`Fix this problem the ${p.source} check reports, without changing anything else:\n${brief(p)}`);
  const fixFile = (file: string, ps: Problem[]) => askEmilie(
    `Fix the ${plural(ps.length, "problem")} reported in ${file}:\n${ps.slice(0, 60).map((p) => "- " + brief(p)).join("\n")}${ps.length > 60 ? `\n(and ${ps.length - 60} more)` : ""}`);
  const fixAll = () => {
    const list = all.filter((p) => p.severity !== "info");
    askEmilie(`The project's checks report ${plural(counts.error, "error")} and ${plural(counts.warning, "warning")}. Fix them, errors first; ` +
      `run the same checks again at the end to make sure they pass.\n${list.slice(0, 80).map((p) => "- " + brief(p)).join("\n")}` +
      (list.length > 80 ? `\n(and ${list.length - 80} more: run the checks to see them)` : ""));
  };

  if (!cwd) return <Empty icon={<I.AlertCircle size={22} />} title="No folder">Open a session in a folder to check its code.</Empty>;
  if (checkers && !checkers.length) {
    return (
      <Empty icon={<I.AlertCircle size={22} />} title="No checkers found"
        action={<button className={btnPrimary} onClick={() => askEmilie("Set up type checking and linting for this project (the standard tools for its language, with a config file and a script to run them). Keep the rules close to the defaults.")}>Ask Emilie to set them up</button>}>
        Emilie runs the project's own TypeScript, ESLint, Ruff, mypy, Pyright, Flake8, cargo check and go vet, and checks Python
        syntax by itself. None of them applies to this folder yet.
      </Empty>
    );
  }

  return (
    <div className="flex h-full flex-col text-[11.5px]">
      <div className="border-b border-border-300 px-2.5 pb-2 pt-2 dark:border-[#353535]">
        <div className="flex items-center gap-1.5">
          {running
            ? <button className={cn(btnSm, "hover:text-danger")} onClick={() => post("/api/job/stop", { id: jobId })}><I.Square size={9} />Stop</button>
            : <button className={btnPrimary} disabled={!checkers} onClick={() => start()}><I.Play size={11} />Run checks</button>}
          {running && <span className="flex min-w-0 items-center gap-1.5 text-[11px] text-text-400"><Spinner size={11} /><span className="truncate">{lines.filter((l) => l.startsWith("▸")).slice(-1)[0]?.slice(2) || "Starting…"}</span></span>}
          {!running && run && <span className="min-w-0 truncate text-[11px] text-text-500">checked {agoSecs(m.at || run.at || 0)}</span>}
          <span className="flex-1" />
          {!running && all.some((p) => p.severity !== "info") && <button className={btnSm} onClick={fixAll}><I.Sparkles size={11} />Fix all with Emilie</button>}
        </div>
        <div className="mt-2 flex flex-wrap gap-1">
          {!checkers && <Spinner size={12} />}
          {(checkers || []).map((c) => {
            const r = run?.results.find((x) => x.id === c.id);
            const n = r?.problems.length ?? null;
            const isOn = !off[c.id];
            return (
              <Tip key={c.id} content={<span>{c.cmd}{c.dir ? ` (in ${c.dir})` : ""}<br /><span className="text-text-400">Click to {isOn ? "leave it out" : "include it"}</span></span>}>
                <button onClick={() => setOff(c.id, isOn)} aria-pressed={isOn}
                  className={cn("inline-flex h-[20px] items-center gap-1 rounded-full border px-2 text-[10.5px]",
                    isOn ? "border-border-400 text-text-100" : "border-border-300 text-text-500 line-through decoration-1")}>
                  {isOn && <span className={cn("h-[6px] w-[6px] rounded-full", r?.error ? "bg-warn" : n === null ? "bg-text-500/50" : n ? "bg-danger" : "bg-ok")} />}
                  {where(c)}{n ? <span className="tabular-nums text-text-400">{n}</span> : null}
                </button>
              </Tip>
            );
          })}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2.5 pb-3">
        {err && <div className="mt-2 text-[11px] text-danger">{err}</div>}
        {!run && !running && checkers && (
          <Hint className="mt-3">Press Run checks to run {checkers.filter((c) => !off[c.id]).map(where).join(", ") || "the checkers you include"}. The results stay here while the app is open.</Hint>
        )}

        {run && (
          <div className="mt-2 flex flex-wrap items-center gap-1">
            <Pill on={sev === "all"} onClick={() => setSev("all")}>All <span className="tabular-nums text-text-500">{all.length}</span></Pill>
            <Pill on={sev === "error"} onClick={() => setSev("error")}>{SEV_ICON.error}<span className="tabular-nums">{counts.error}</span></Pill>
            <Pill on={sev === "warning"} onClick={() => setSev("warning")}>{SEV_ICON.warning}<span className="tabular-nums">{counts.warning}</span></Pill>
            <div className="ml-1 flex min-w-[120px] flex-1"><SearchField value={q} onChange={setQ} placeholder="Filter problems" /></div>
          </div>
        )}

        {failedTools.map((r) => (
          <div key={r.id} className="mt-2 overflow-hidden rounded-[8px] border border-warn/30 bg-warn-soft">
            <div className="flex items-center gap-2 px-2.5 py-1.5 text-[11px] text-warn">
              <I.Alert size={12} className="shrink-0" /><span className="min-w-0 flex-1">{r.error}</span>
              <button className="shrink-0 underline-offset-2 hover:underline" onClick={() => setShowOut(showOut === r.id ? "" : r.id)}>{showOut === r.id ? "Hide output" : "Output"}</button>
            </div>
            {showOut === r.id && <Output lines={r.tail.split("\n")} className="border-t border-warn/20" />}
          </div>
        ))}

        {run && !running && !all.length && !failedTools.length && (
          <div className="mt-6 flex flex-col items-center gap-1.5 text-center">
            <I.CheckBig size={22} className="text-ok" />
            <div className="text-[12.5px] font-medium text-text-100">No problems</div>
            <div className="text-[11px] text-text-500">{run.results.map((r) => `${where(r)} ${took(r.secs)}`).join(" · ")}</div>
          </div>
        )}
        {run && !!all.length && !files.length && <Hint className="mt-3">Nothing matches this filter.</Hint>}

        <div className="mt-2 flex flex-col gap-2">
          {files.map(({ file, abs, ps }) => {
            const on = !shut[file];
            const [name, dir] = splitPath(file);
            return (
              <Card key={file}>
                <div role="button" onClick={() => setShut((s) => ({ ...s, [file]: on }))} className={cn(rowCls, "py-[6px]")} title={abs}>
                  <Chevron on={on} />
                  <span className="max-w-[60%] shrink-0 truncate text-text-100">{name}</span>
                  <span className="min-w-0 flex-1 truncate text-[10.5px] text-text-500">{dir}</span>
                  <RowBtn tip="Fix this file's problems with Emilie" onClick={() => fixFile(file, ps)}><I.Sparkles size={11} /></RowBtn>
                  <span className={cn("shrink-0 tabular-nums text-[10.5px]", ps.some((p) => p.severity === "error") ? "text-danger" : "text-warn")}>{ps.length}</span>
                </div>
                {on && (
                  <div className="border-t border-border-200">
                    {ps.slice(0, 200).map((p, i) => (
                      <div key={i} role="button" onClick={() => useStore.getState().openFile(p.abs, p.line || undefined)} title={`${p.source}${p.code ? ` · ${p.code}` : ""}`}
                        className={cn("group flex min-w-0 items-start gap-2 py-[4px] pl-[12px] pr-2.5 hover:bg-hover/50", i > 0 && "border-t border-border-200")}>
                        <span className="mt-[2px]">{SEV_ICON[p.severity]}</span>
                        <span className="min-w-0 flex-1 whitespace-pre-wrap break-words text-[11px] leading-[16px] text-text-200">
                          {p.message}{p.code && <span className="ml-1.5 text-[10px] text-text-500">{p.code}</span>}
                        </span>
                        <RowBtn tip="Fix with Emilie" onClick={() => fixOne(p)}><I.Sparkles size={11} /></RowBtn>
                        <span className="mt-[1px] shrink-0 tabular-nums text-[10px] text-text-500">{p.line}{p.col ? `:${p.col}` : ""}</span>
                      </div>
                    ))}
                    {ps.length > 200 && <div className="border-t border-border-200 py-[4px] pl-[32px] text-[10.5px] text-text-500">and {ps.length - 200} more</div>}
                  </div>
                )}
              </Card>
            );
          })}
        </div>

        {(running || (run && lines.length > 0)) && (
          <>
            <Heading title="Output" open={showOut === "live"} onToggle={() => setShowOut(showOut === "live" ? "" : "live")} />
            {showOut === "live" && <Card><Output lines={lines} /></Card>}
          </>
        )}
        {run && !!all.length && !running && (
          <div className="mt-2 px-1 text-[10.5px] text-text-500">{run.results.map((r) => `${where(r)}: ${r.problems.length} in ${took(r.secs)}`).join(" · ")}</div>
        )}
      </div>
    </div>
  );
}
