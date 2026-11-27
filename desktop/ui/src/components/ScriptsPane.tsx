// The Scripts panel: one click runs a command the project defines (package.json scripts, Makefile targets, justfile
// recipes, pyproject tasks, cargo, go, Django, Docker Compose, deno, composer, .claude/launch.json) or one you saved.
// Each run streams its output here; a dev server's address opens in the Browser panel; a failed run can go to Emilie.
import { useEffect, useMemo, useState } from "react";
import { get, post } from "@/lib/api";
import { adoptRun, useStore, type TermRun } from "@/lib/store";
import { cn } from "@/lib/util";
import * as I from "./icons";
import {
  askEmilie, btnPrimary, btnSm, Card, Chevron, copy, Empty, fence, Heading, Hint, IconBtn, Output, remember, RowBtn, rowCls,
  SearchField, stripAnsi, took,
} from "./PaneKit";
import { openInBrowser } from "./TasksPane";
import { Spinner } from "./ui";

interface Item { name: string; command: string; detail: string }
interface Group { id: string; dir: string; source: string; label: string; kind: string; items: Item[]; more: number }
interface Custom { name: string; command: string; dir: string }
interface Detected { groups: Group[]; custom: Custom[] }

const mem = new Map<string, { q: string; shut: Record<string, boolean> }>();
const KIND_ICON: Record<string, React.ReactNode> = {
  node: <I.Package size={11} />, make: <I.Hammer size={11} />, just: <I.Hammer size={11} />, task: <I.Hammer size={11} />,
  python: <I.CodeBrackets size={11} />, rust: <I.Box size={11} />, go: <I.Box size={11} />, docker: <I.Layers size={11} />,
  php: <I.CodeBrackets size={11} />, deno: <I.Package size={11} />, launch: <I.AppWindow size={11} />,
};
const URL_RX = /https?:\/\/(?:localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1?\]|[\w-]+(?:\.[\w-]+)*):\d{2,5}(?:\/[^\s"'<>)\]]*)?/;

const join = (root: string, rel: string) => (!rel ? root : root.replace(/[\\/]+$/, "") + (root.includes("\\") ? "\\" : "/") + rel.split("/").join(root.includes("\\") ? "\\" : "/"));

/** The address a dev server printed ("Local: http://localhost:5173/"), made openable. */
function serverUrl(lines: string[]): string {
  for (let i = Math.max(0, lines.length - 300); i < lines.length; i++) {
    const m = stripAnsi(lines[i]).match(URL_RX);
    if (m) return m[0].replace(/0\.0\.0\.0|\[::1?\]/, "localhost").replace(/[.,;:]+$/, "");
  }
  return "";
}

export function ScriptsPane({ cwd }: { cwd: string }) {
  const m = remember(mem, cwd, () => ({ q: "", shut: {} as Record<string, boolean> }));
  const toast = useStore((s) => s.toast);
  const allRuns = useStore((s) => s.runs);
  const [data, setData] = useState<Detected | null>(null);
  const [err, setErr] = useState("");
  const [q, setQState] = useState(m.q);
  const setQ = (v: string) => { m.q = v; setQState(v); };
  const [shut, setShut] = useState(m.shut);
  const [open, setOpen] = useState("");
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState<Custom>({ name: "", command: "", dir: "" });
  const [, tick] = useState(0);

  const root = cwd.replace(/[\\/]+$/, "").toLowerCase();
  const runs = useMemo(() => allRuns.filter((r) => r.cwd.toLowerCase().startsWith(root)), [allRuns, root]);
  const live = runs.some((r) => r.code === null);

  const load = () => get<Detected>("/api/project/scripts", { cwd }).then((r) => { setData(r); setErr(""); }).catch((e) => setErr(e.message));
  useEffect(() => {
    if (!cwd) return;
    load();
    // after a window reload: the commands still running come back into the list
    get<{ terms: { tid: string; cwd: string; command: string; name: string; started: number; lines: string[] }[] }>("/api/term/list")
      .then((r) => {
        const have = new Set(useStore.getState().runs.map((x) => x.tid));
        for (const t of r.terms) {
          if (t.name && !have.has(t.tid) && t.cwd.toLowerCase().startsWith(root)) {
            adoptRun({ tid: t.tid, cwd: t.cwd, command: t.command, name: t.name, lines: t.lines, code: null, at: t.started * 1000 });
          }
        }
      }).catch(() => {});
  }, [cwd]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!live) return;
    const t = window.setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, [live]);

  const start = async (name: string, command: string, dir: string) => {
    const where = join(cwd, dir);
    const same = runs.find((r) => r.code === null && r.command === command && r.cwd === where);
    if (same) { setOpen(same.tid); toast(`${name} is already running`); return; }
    try {
      const r = await post<{ tid: string }>("/api/term/run", { cwd: where, command, name });
      adoptRun({ tid: r.tid, cwd: where, command, name, lines: [], code: null, at: Date.now() });
      setOpen(r.tid);
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  const stop = (r: TermRun) => post("/api/term/kill", { tid: r.tid }).catch((e) => toast(e.message, "error"));
  const forget = (r: TermRun) => useStore.setState({ runs: useStore.getState().runs.filter((x) => x.tid !== r.tid) });
  const fix = (r: TermRun) => askEmilie(
    `The command \`${r.command}\` (run in ${r.cwd}) failed with exit code ${r.code}. The end of its output:\n${fence(r.lines.join("\n"))}\nFind the cause and fix it, then tell me how to check it works.`);
  const saveCustom = async (list: Custom[]) => {
    try {
      const r = await post<{ custom: Custom[] }>("/api/project/commands", { cwd, commands: list });
      setData((d) => (d ? { ...d, custom: r.custom } : d));
      return true;
    } catch (e: any) {
      toast(e.message, "error");
      return false;
    }
  };
  const addCustom = async () => {
    if (!form.command.trim()) return;
    if (await saveCustom([...(data?.custom || []), { ...form, name: form.name.trim() || form.command.trim().slice(0, 40) }])) {
      setAdding(false);
      setForm({ name: "", command: "", dir: "" });
    }
  };

  if (!cwd) return <Empty icon={<I.Play size={22} />} title="No folder">Open a session in a folder to run its scripts.</Empty>;
  const ql = q.trim().toLowerCase();
  const match = (it: { name: string; command: string; detail?: string }) => !ql || it.name.toLowerCase().includes(ql) || it.command.toLowerCase().includes(ql) || (it.detail || "").toLowerCase().includes(ql);
  const groups = (data?.groups || []).map((g) => ({ ...g, items: g.items.filter(match) })).filter((g) => g.items.length);
  const custom = (data?.custom || []).filter(match);
  const dirs = [...new Set((data?.groups || []).map((g) => g.dir))];
  const runningOf = (command: string, dir: string) => runs.find((r) => r.code === null && r.command === command && r.cwd === join(cwd, dir));

  const itemRow = (it: Item | Custom, dir: string, i: number, extra?: React.ReactNode) => {
    const r = runningOf(it.command, dir);
    return (
      <div key={it.name + i} role="button" onClick={() => (r ? setOpen(r.tid) : start(it.name, it.command, dir))} title={it.command}
        className={cn(rowCls, "h-[26px] gap-1.5 pl-2 pr-2", i > 0 && "border-t border-border-200")}>
        <span className={cn("flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-[4px]", r ? "text-accent" : "text-text-400 group-hover:text-ok")}>
          {r ? <span className="h-[7px] w-[7px] animate-pulse rounded-full bg-accent" /> : <I.Play size={11} />}
        </span>
        <span className="min-w-0 shrink-0 truncate text-text-100" style={{ maxWidth: "55%" }}>{it.name}</span>
        <span className="min-w-0 flex-1 truncate font-mono text-[10px] text-text-500">{"detail" in it && it.detail ? it.detail : it.command}</span>
        {r && <span className="shrink-0 tabular-nums text-[10.5px] text-accent">{took((Date.now() - r.at) / 1000)}</span>}
        {r && <RowBtn tip="Stop" danger onClick={() => stop(r)}><I.Square size={10} /></RowBtn>}
        <RowBtn tip="Copy the command" onClick={() => copy(it.command, "Command copied")}><I.Copy size={11} /></RowBtn>
        {extra}
      </div>
    );
  };

  return (
    <div className="flex h-full flex-col text-[11.5px]">
      <div className="flex items-center gap-1 px-2.5 pt-2">
        <SearchField value={q} onChange={setQ} placeholder="Filter scripts" />
        <IconBtn tip="Add a command" onClick={() => { setAdding(true); setForm({ name: "", command: "", dir: "" }); }}><I.PlusSm size={13} /></IconBtn>
        <IconBtn tip="Look for scripts again" onClick={load}><I.Refresh size={12} /></IconBtn>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2.5 pb-3">
        {err && <div className="mt-2 text-[11px] text-danger">{err}</div>}
        {!data && !err && <div className="p-2"><Spinner /></div>}

        {adding && (
          <Card className="mt-2.5 p-2.5">
            <div className="mb-1.5 text-[11px] text-text-300">A command of your own for this project</div>
            <input autoFocus value={form.command} onChange={(e) => setForm({ ...form, command: e.target.value })} placeholder="Command, e.g. docker compose up -d db"
              onKeyDown={(e) => { if (e.key === "Enter") addCustom(); if (e.key === "Escape") setAdding(false); }}
              className="mb-1.5 h-[24px] w-full rounded-[6px] border border-border-300 bg-bg-100 px-2 font-mono text-[11px] text-text-100 outline-none focus:border-border-400 selectable" />
            <div className="flex flex-wrap items-center gap-1.5">
              <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Name (optional)"
                onKeyDown={(e) => { if (e.key === "Enter") addCustom(); }}
                className="h-[24px] min-w-[120px] flex-1 rounded-[6px] border border-border-300 bg-bg-100 px-2 text-[11.5px] text-text-100 outline-none focus:border-border-400 selectable" />
              {dirs.some(Boolean) && (
                <select value={form.dir} onChange={(e) => setForm({ ...form, dir: e.target.value })} title="Folder to run it in"
                  className="h-[24px] rounded-[6px] border border-border-300 bg-bg-100 px-1.5 text-[11px] text-text-100 outline-none">
                  <option value="">(project folder)</option>
                  {dirs.filter(Boolean).map((d) => <option key={d} value={d}>{d}</option>)}
                </select>
              )}
              <button className={btnPrimary} disabled={!form.command.trim()} onClick={addCustom}>Save</button>
              <button className={btnSm} onClick={() => setAdding(false)}>Cancel</button>
            </div>
          </Card>
        )}

        {!!runs.length && (
          <>
            <Heading title="Runs" note={runs.filter((r) => r.code === null).length ? `${runs.filter((r) => r.code === null).length} running` : ""}
              right={runs.some((r) => r.code !== null) && <button className="text-[10.5px] text-text-500 hover:text-text-100" onClick={() => useStore.setState({ runs: useStore.getState().runs.filter((r) => r.code === null || !r.cwd.toLowerCase().startsWith(root)) })}>Clear finished</button>} />
            <div className="flex flex-col gap-2">
              {runs.map((r) => <RunCard key={r.tid} r={r} cwd={cwd} on={open === r.tid} toggle={() => setOpen(open === r.tid ? "" : r.tid)}
                stop={() => stop(r)} again={() => { forget(r); start(r.name || r.command, r.command, rel(cwd, r.cwd)); }} forget={() => forget(r)} fix={() => fix(r)} />)}
            </div>
          </>
        )}

        {data && !groups.length && !custom.length && !adding && (
          ql ? <Hint className="mt-3">No script matches "{q}".</Hint> : (
            <Empty icon={<I.Play size={22} />} title="No scripts found"
              action={<button className={btnPrimary} onClick={() => setAdding(true)}>Add a command</button>}>
              Emilie looks in package.json, Makefile, justfile, Taskfile, pyproject.toml, Cargo.toml, go.mod, manage.py,
              Docker Compose, deno.json and composer.json. You can also save your own commands.
            </Empty>
          )
        )}

        {!!custom.length && (
          <>
            <Heading title="Your commands" note={custom.length} />
            <Card>
              {custom.map((c, i) => itemRow(c, c.dir, i, (
                <RowBtn tip="Remove" danger onClick={() => saveCustom((data?.custom || []).filter((x) => x !== c))}><I.Trash size={11} /></RowBtn>
              )))}
            </Card>
          </>
        )}

        {groups.map((g) => {
          const on = !shut[g.id];
          return (
            <div key={g.id}>
              <Heading open={on} onToggle={() => setShut((s) => { const n = { ...s, [g.id]: on }; m.shut = n; return n; })}
                title={<span className="flex min-w-0 items-center gap-1.5"><span className="shrink-0 text-text-400">{KIND_ICON[g.kind] || <I.Play size={11} />}</span>
                  <span className="truncate">{g.source}</span>{g.dir && <span className="truncate text-[10.5px] text-text-500">{g.dir}</span>}</span>}
                note={g.label !== g.source ? g.label : ""} />
              {on && (
                <Card>
                  {g.items.map((it, i) => itemRow(it, g.dir, i))}
                  {g.more > 0 && <div className="border-t border-border-200 px-3 py-[4px] text-[10.5px] text-text-500">and {g.more} more</div>}
                </Card>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

const rel = (root: string, p: string) => {
  const r = root.replace(/[\\/]+$/, "");
  return p.toLowerCase().startsWith(r.toLowerCase()) ? p.slice(r.length).replace(/^[\\/]+/, "").replace(/\\/g, "/") : "";
};

function RunCard({ r, cwd, on, toggle, stop, again, forget, fix }: {
  r: TermRun; cwd: string; on: boolean; toggle: () => void; stop: () => void; again: () => void; forget: () => void; fix: () => void;
}) {
  const running = r.code === null;
  const failed = !running && r.code !== 0;
  const url = useMemo(() => serverUrl(r.lines), [r.lines]);
  const where = rel(cwd, r.cwd);
  const secs = ((r.ended || Date.now()) - r.at) / 1000;
  return (
    <Card>
      <div role="button" onClick={toggle} className={cn(rowCls, "py-[6px]")}>
        <span className={cn("flex w-[12px] shrink-0 justify-center", running ? "text-accent" : failed ? "text-danger" : "text-ok")}>
          {running ? <span className="h-[7px] w-[7px] animate-pulse rounded-full bg-accent" /> : failed ? <I.X size={12} /> : <I.Check size={12} />}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-baseline gap-1.5">
            <span className="truncate text-text-100">{r.name || r.command}</span>
            {where && <span className="truncate text-[10px] text-text-500">{where}</span>}
          </div>
          <div className="truncate font-mono text-[10px] text-text-500" title={r.command}>{r.command}</div>
        </div>
        <span className={cn("shrink-0 tabular-nums text-[10.5px]", failed ? "text-danger" : "text-text-500")}>{running ? took(secs) : `exit ${r.code} · ${took(secs)}`}</span>
        <Chevron on={on} />
      </div>
      {(url || on || failed) && (
        <div className="flex flex-wrap items-center gap-1.5 px-3 pb-2">
          {url && <button className={cn(btnSm, "text-link")} onClick={() => openInBrowser(url)} title="Open in the Browser panel"><I.GlobeSm size={11} />{url.replace(/^https?:\/\//, "")}</button>}
          {running && <button className={cn(btnSm, "hover:text-danger")} onClick={stop}><I.Square size={9} />Stop</button>}
          {!running && <button className={btnSm} onClick={again}><I.RotateCw size={10} />Run again</button>}
          {failed && <button className={btnSm} onClick={fix}><I.Sparkles size={11} />Fix with Emilie</button>}
          {on && <button className={btnSm} onClick={() => copy(stripAnsi(r.lines.join("\n")), "Output copied")}><I.Copy size={10} />Copy output</button>}
          {!running && <button className={btnSm} onClick={forget}>Remove</button>}
        </div>
      )}
      {on && <Output lines={r.lines} className="border-t border-border-200" empty={running ? "Starting…" : "(no output)"} />}
    </Card>
  );
}
