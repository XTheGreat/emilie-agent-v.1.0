// The Database panel: the project's SQLite files (db.sqlite3, dev.db, *.sqlite…) with their tables and views, a page
// of rows (sortable by a column), each table's structure, and a SQL box. Read-only unless "Allow changes" is on, and
// then only for the statement being run. Another database file can be opened from anywhere.
import { useEffect, useMemo, useState } from "react";
import { get, post } from "@/lib/api";
import { bridge } from "@/lib/desktop";
import { useStore } from "@/lib/store";
import { cn } from "@/lib/util";
import * as I from "./icons";
import { askEmilie, btnPrimary, btnSm, Empty, fmtBytes, Hint, IconBtn, Pill, remember } from "./PaneKit";
import { Menu, MenuContent, MenuItem, MenuLabel, MenuSep, MenuTrigger, Spinner } from "./ui";

interface DbFile { rel: string; abs: string; size: number }
interface Col { name: string; type: string; notnull: boolean; default: any; pk: number }
interface Table { name: string; type: string; columns: Col[]; rows: number | null; more: boolean; sql: string }
interface Grid { columns: string[]; rows: any[][]; offset?: number; ms: number; cut?: boolean; changes?: number }
type View = "data" | "structure" | "sql";

interface Mem { path: string; table: string; view: View; sql: string; write: boolean; extra: DbFile[] }
const mem = new Map<string, Mem>();
const PAGE = 200;

function cell(v: any): React.ReactNode {
  if (v === null || v === undefined) return <span className="italic text-text-500">NULL</span>;
  if (typeof v === "object" && "blob" in v) return <span className="text-text-500">BLOB {fmtBytes(v.blob)}</span>;
  if (typeof v === "number") return <span className="tabular-nums text-link">{String(v)}</span>;
  return String(v);
}

export function DatabasePane({ cwd }: { cwd: string }) {
  const m = remember(mem, cwd, (): Mem => ({ path: "", table: "", view: "data", sql: "", write: false, extra: [] }));
  const toast = useStore((s) => s.toast);
  const [files, setFiles] = useState<DbFile[] | null>(null);
  const [path, setPathState] = useState(m.path);
  const [tables, setTables] = useState<Table[] | null>(null);
  const [table, setTableState] = useState(m.table);
  const [view, setViewState] = useState<View>(m.view);
  const [grid, setGrid] = useState<Grid | null>(null);
  const [offset, setOffset] = useState(0);
  const [order, setOrder] = useState<{ col: string; desc: boolean } | null>(null);
  const [sql, setSqlState] = useState(m.sql);
  const [write, setWriteState] = useState(m.write);
  const [result, setResult] = useState<Grid | { error: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [again, setAgain] = useState(0);                       // Reload: the rows are read again too
  const setPath = (p: string) => { m.path = p; setPathState(p); setTableState(""); m.table = ""; setGrid(null); setResult(null); };
  const setTable = (t: string) => { m.table = t; setTableState(t); setOffset(0); setOrder(null); };
  const setView = (v: View) => { m.view = v; setViewState(v); };
  const setSql = (s: string) => { m.sql = s; setSqlState(s); };
  const setWrite = (w: boolean) => { m.write = w; setWriteState(w); };

  const allFiles = useMemo(() => [...(files || []), ...m.extra.filter((x) => !(files || []).some((f) => f.abs === x.abs))], [files, m.extra]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!cwd) return;
    get<{ files: DbFile[] }>("/api/db/files", { cwd }).then((r) => {
      setFiles(r.files);
      if (!m.path && r.files[0]) setPath(r.files[0].abs);
    }).catch((e) => setErr(e.message));
  }, [cwd]);   // eslint-disable-line react-hooks/exhaustive-deps

  const loadTables = () => {
    if (!path) return;
    setTables(null);
    get<{ tables: Table[] }>("/api/db/tables", { path }).then((r) => {
      setTables(r.tables);
      setErr("");
      if (!r.tables.some((t) => t.name === m.table) && r.tables[0]) setTable(r.tables[0].name);
    }).catch((e) => { setErr(e.message); setTables([]); });
  };
  useEffect(loadTables, [path]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!path || !table || view !== "data") return;
    let dead = false;
    get<Grid>("/api/db/rows", { path, table, offset, limit: PAGE, order: order?.col || "", desc: order?.desc ? "1" : "" })
      .then((r) => { if (!dead) setGrid(r); }).catch((e) => { if (!dead) setGrid({ columns: [], rows: [], ms: 0 }); toast(e.message, "error"); });
    return () => { dead = true; };
  }, [path, table, offset, order, view, again]);   // eslint-disable-line react-hooks/exhaustive-deps

  const runSql = async () => {
    if (!sql.trim() || busy) return;
    setBusy(true);
    try {
      const r = await post<Grid>("/api/db/query", { path, sql, write });
      setResult(r);
      if (write && r.changes !== undefined) { toast(`${r.changes} row${r.changes === 1 ? "" : "s"} changed`); loadTables(); }
    } catch (e: any) {
      setResult({ error: e.message });
    } finally {
      setBusy(false);
    }
  };
  const openOther = async () => {
    const p = await bridge?.pickFile?.({ title: "Open an SQLite database", filters: [{ name: "SQLite", extensions: ["db", "sqlite", "sqlite3", "db3"] }, { name: "All files", extensions: ["*"] }] });
    if (!p) return;
    m.extra = [...m.extra.filter((x) => x.abs !== p), { rel: p, abs: p, size: 0 }];
    setPath(p);
  };

  if (!cwd) return <Empty icon={<I.Database size={22} />} title="No folder">Open a session in a folder to browse its databases.</Empty>;
  if (files && !allFiles.length) {
    return (
      <Empty icon={<I.Database size={22} />} title="No SQLite database in this project"
        action={<>{bridge?.pickFile && <button className={btnPrimary} onClick={openOther}>Open a database file…</button>}</>}>
        Files such as db.sqlite3, dev.db or *.sqlite show up here (they are found by their content, whatever their name).
      </Empty>
    );
  }
  const cur = tables?.find((t) => t.name === table);
  const curFile = allFiles.find((f) => f.abs === path);
  const g: Grid | null = view === "data" ? grid : result && !("error" in result) ? result : null;

  return (
    <div className="flex h-full flex-col text-[11.5px]">
      <div className="flex h-[32px] shrink-0 items-center gap-1 border-b border-border-300 px-2 dark:border-[#353535]">
        <Menu>
          <MenuTrigger asChild>
            <button className="flex h-[24px] min-w-0 items-center gap-1.5 rounded-[5px] px-1.5 text-[11.5px] text-text-100 hover:bg-hover data-[state=open]:bg-hover" title={path}>
              <I.Database size={12} className="shrink-0 text-text-300" /><span className="truncate">{curFile?.rel || "Choose a database"}</span><I.ChevD size={10} className="shrink-0 text-text-400" />
            </button>
          </MenuTrigger>
          <MenuContent align="start" className="max-w-[380px]">
            <MenuLabel>Databases in the project</MenuLabel>
            {allFiles.map((f) => <MenuItem key={f.abs} checked={f.abs === path} shortcut={f.size ? fmtBytes(f.size) : ""} onSelect={() => setPath(f.abs)}>{f.rel}</MenuItem>)}
            {bridge?.pickFile && <><MenuSep /><MenuItem icon={<I.FolderOpen />} onSelect={openOther}>Open another file…</MenuItem></>}
          </MenuContent>
        </Menu>
        {!!tables?.length && (
          <Menu>
            <MenuTrigger asChild>
              <button className="flex h-[24px] min-w-0 items-center gap-1.5 rounded-[5px] px-1.5 text-[11.5px] text-text-100 hover:bg-hover data-[state=open]:bg-hover">
                <I.TableIcon size={12} className="shrink-0 text-text-300" /><span className="truncate">{table || "Table"}</span><I.ChevD size={10} className="shrink-0 text-text-400" />
              </button>
            </MenuTrigger>
            <MenuContent align="start" className="max-h-[360px] min-w-[220px] overflow-y-auto">
              {tables.map((t) => (
                <MenuItem key={t.name} checked={t.name === table} shortcut={t.rows === null ? t.type : `${t.more ? "100k+" : t.rows.toLocaleString()}${t.type === "view" ? " · view" : ""}`}
                  onSelect={() => { setTable(t.name); if (view === "sql") setView("data"); }}>{t.name}</MenuItem>
              ))}
            </MenuContent>
          </Menu>
        )}
        <span className="flex-1" />
        <IconBtn tip="Reload" onClick={() => { loadTables(); setAgain((n) => n + 1); }}><I.Refresh size={12} /></IconBtn>
      </div>

      <div className="flex items-center gap-1 px-2.5 pt-2">
        <Pill on={view === "data"} onClick={() => setView("data")}><I.TableIcon size={11} />Data</Pill>
        <Pill on={view === "structure"} onClick={() => setView("structure")}><I.ListIcon size={11} />Structure</Pill>
        <Pill on={view === "sql"} onClick={() => setView("sql")}><I.CodeXml size={11} />SQL</Pill>
        <span className="flex-1" />
        {view === "data" && cur && cur.rows !== null && cur.rows > PAGE && (
          <span className="flex items-center gap-0.5 text-[10.5px] text-text-500">
            <IconBtn tip="Previous rows" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}><I.ChevL size={11} /></IconBtn>
            <span className="tabular-nums">{(offset + 1).toLocaleString()}–{Math.min(offset + PAGE, cur.rows).toLocaleString()} of {cur.more ? "100,000+" : cur.rows.toLocaleString()}</span>
            <IconBtn tip="Next rows" disabled={!cur.more && offset + PAGE >= cur.rows} onClick={() => setOffset(offset + PAGE)}><I.ChevR size={11} /></IconBtn>
          </span>
        )}
      </div>

      {view === "sql" && (
        <div className="px-2.5 pt-2">
          <textarea value={sql} onChange={(e) => setSql(e.target.value)} rows={4} spellCheck={false}
            placeholder={`SELECT * FROM ${table || "table"} LIMIT 50;   (Ctrl+Enter to run)`}
            onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); runSql(); } }}
            className="block w-full resize-y rounded-[7px] border border-border-300 bg-bg-200/40 px-2.5 py-1.5 font-mono text-[11px] leading-[16px] text-text-100 outline-none focus:border-border-400 placeholder:text-text-500 selectable" />
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            <button className={btnPrimary} disabled={!sql.trim() || busy || !path} onClick={runSql}>{busy ? <Spinner size={11} className="text-current" /> : <I.Play size={11} />}Run</button>
            <label className={cn("flex items-center gap-1.5 text-[11px]", write ? "text-danger" : "text-text-400")}>
              <input type="checkbox" checked={write} onChange={(e) => setWrite(e.target.checked)} className="h-[12px] w-[12px] accent-[var(--danger)]" />
              Allow changes (INSERT, UPDATE, DELETE…)
            </label>
            <span className="flex-1" />
            <button className={btnSm} onClick={() => askEmilie(`Write an SQL query for the SQLite database ${curFile?.rel || path} that: (describe what you need here). The tables are: ${(tables || []).map((t) => `${t.name}(${t.columns.map((c) => c.name).join(", ")})`).join("; ")}.`)}>
              <I.Sparkles size={11} />Ask Emilie
            </button>
          </div>
          {result && "error" in result && <div className="mt-2 rounded-[7px] bg-danger-soft px-2.5 py-1.5 font-mono text-[10.5px] text-danger selectable">{result.error}</div>}
          {result && !("error" in result) && (
            <div className="mt-1.5 text-[10.5px] text-text-500">
              {result.columns.length ? `${result.rows.length.toLocaleString()} row${result.rows.length === 1 ? "" : "s"}${result.cut ? " (first 1,000)" : ""}` : `${result.changes ?? 0} row(s) changed`} · {result.ms} ms
            </div>
          )}
        </div>
      )}

      <div className="mt-2 min-h-0 flex-1 overflow-auto border-t border-border-300 dark:border-[#353535]">
        {err && <div className="p-3 text-[11px] text-danger">{err}</div>}
        {!tables && !err && path && <div className="p-3"><Spinner /></div>}
        {tables && !tables.length && !err && <Hint className="p-3">This database has no tables.</Hint>}

        {view === "structure" && cur && (
          <div className="p-2.5">
            <table className="w-full border-collapse text-[11px]">
              <thead><tr className="text-left text-[10.5px] text-text-400">{["Column", "Type", "Key", "Not null", "Default"].map((h) => <th key={h} className="border-b border-border-300 px-2 py-1 font-medium">{h}</th>)}</tr></thead>
              <tbody>
                {cur.columns.map((c) => (
                  <tr key={c.name} className="border-b border-border-200">
                    <td className="px-2 py-1 font-mono text-text-100">{c.name}</td>
                    <td className="px-2 py-1 font-mono text-text-300">{c.type || "—"}</td>
                    <td className="px-2 py-1 text-accent">{c.pk ? "primary" : ""}</td>
                    <td className="px-2 py-1 text-text-300">{c.notnull ? "yes" : ""}</td>
                    <td className="px-2 py-1 font-mono text-text-400">{c.default === null ? "" : String(c.default)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {cur.sql && <pre className="mt-3 whitespace-pre-wrap break-words rounded-[7px] border border-border-300 bg-bg-200/40 px-2.5 py-2 font-mono text-[10.5px] leading-[15px] text-text-300 selectable">{cur.sql}</pre>}
          </div>
        )}

        {view !== "structure" && g && (
          g.columns.length ? (
            <table className="min-w-full border-separate border-spacing-0 font-mono text-[10.5px]">
              <thead className="sticky top-0 z-[1] bg-bg-200">
                <tr>
                  {view === "data" && <th className="w-[1%] border-b border-r border-border-300 bg-bg-200 px-2 py-[5px] text-right font-normal text-text-500">#</th>}
                  {g.columns.map((c) => {
                    const sorted = view === "data" && order?.col === c;
                    return (
                      <th key={c} onClick={() => view === "data" && setOrder(sorted ? (order!.desc ? null : { col: c, desc: true }) : { col: c, desc: false })}
                        className={cn("whitespace-nowrap border-b border-r border-border-300 bg-bg-200 px-2 py-[5px] text-left font-medium text-text-200", view === "data" && "cursor-pointer hover:text-text-000")}>
                        {c}{sorted && <span className="ml-1 text-accent">{order!.desc ? "↓" : "↑"}</span>}
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                {g.rows.map((r, i) => (
                  <tr key={i} className="hover:bg-hover/60">
                    {view === "data" && <td className="border-b border-r border-border-200 px-2 py-[3px] text-right text-text-500">{offset + i + 1}</td>}
                    {r.map((v, j) => (
                      <td key={j} title={v !== null && typeof v !== "object" ? String(v) : undefined}
                        className="max-w-[320px] truncate whitespace-nowrap border-b border-r border-border-200 px-2 py-[3px] text-text-100 selectable">{cell(v)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          ) : view === "data" ? <Hint className="p-3">{table ? "No rows." : ""}</Hint> : null
        )}
        {view === "data" && !g && table && <div className="p-3"><Spinner /></div>}
      </div>
    </div>
  );
}
