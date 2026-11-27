// The Ports panel: what listens on this computer's TCP ports, and which program it is. A dev server opens in the
// Browser panel with one click; the program that keeps a port busy can be stopped (after asking). Emilie's own
// processes are marked and cannot be stopped from here. Refreshes every few seconds while it is open.
import { useEffect, useMemo, useState } from "react";
import { get, post } from "@/lib/api";
import { openExternal } from "@/lib/desktop";
import { useStore } from "@/lib/store";
import { cn } from "@/lib/util";
import * as I from "./icons";
import { Card, copy, Empty, Hint, IconBtn, Pill, RowBtn, rowCls, SearchField } from "./PaneKit";
import { openInBrowser } from "./TasksPane";
import { Spinner } from "./ui";

// hint: what usually runs on that port (netkit.KNOWN); dev: worth listing without "All"
interface Port { port: number; pid: number; name: string; addresses: string[]; url: string; dev: boolean; own: string; local: boolean; hint: string }

let showAll = false;

export function PortsPane() {
  const toast = useStore((s) => s.toast);
  const [rows, setRows] = useState<Port[] | null>(null);
  const [err, setErr] = useState("");
  const [all, setAllState] = useState(showAll);
  const setAll = (v: boolean) => { showAll = v; setAllState(v); };
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    setBusy(true);
    try {
      const r = await get<{ ports: Port[] }>("/api/ports");
      setRows(r.ports);
      setErr("");
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    load();
    const t = window.setInterval(() => { if (!document.hidden) load(); }, 4000);
    return () => clearInterval(t);
  }, []);

  const stop = async (p: Port) => {
    const ok = await useStore.getState().confirm(`Stop ${p.name || "this program"}?`,
      `${p.name || "The program"} (PID ${p.pid}) listening on port ${p.port} is stopped, with the programs it started. Anything unsaved in it is lost.`,
      { danger: true, ok: "Stop it" });
    if (!ok) return;
    try {
      await post("/api/ports/kill", { pid: p.pid });
      toast(`Stopped ${p.name || p.pid}`);
    } catch (e: any) {
      toast(e.message, "error");
    }
    load();
  };

  const shown = useMemo(() => {
    const ql = q.trim().toLowerCase();
    return (rows || []).filter((r) => (all || r.dev || r.own) && (!ql || String(r.port).includes(ql) || r.name.toLowerCase().includes(ql) || String(r.pid) === ql));
  }, [rows, all, q]);
  const hidden = (rows || []).length - (rows || []).filter((r) => r.dev || r.own).length;

  return (
    <div className="flex h-full flex-col text-[11.5px]">
      <div className="flex items-center gap-1 px-2.5 pt-2">
        <SearchField value={q} onChange={setQ} placeholder="Port, program or PID" />
        <Pill on={all} onClick={() => setAll(!all)} title="Also system services and high ports">All</Pill>
        <IconBtn tip="Refresh" onClick={load}>{busy ? <Spinner size={11} /> : <I.Refresh size={12} />}</IconBtn>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-2.5 pb-3 pt-2">
        {err && <div className="text-[11px] text-danger">{err}</div>}
        {!rows && !err && <Spinner />}
        {rows && !shown.length && (q ? <Hint>Nothing matches "{q}".</Hint> : (
          <Empty icon={<I.Port size={22} />} title="No dev servers running">
            Nothing is listening on a development port. Start one from the Scripts panel or ask Emilie, and it shows up here.
            {hidden > 0 && <> <button className="text-link underline-offset-2 hover:underline" onClick={() => setAll(true)}>Show {hidden} system ports</button></>}
          </Empty>
        ))}
        {!!shown.length && (
          <Card>
            {shown.map((p, i) => {
              const hint = p.hint;
              const web = !p.own && p.dev && !/sql|redis|mongo|postgres|rabbit|elastic/i.test(`${p.name} ${hint}`);
              return (
                <div key={`${p.port}-${p.pid}`} className={cn(rowCls, "py-[6px]", i > 0 && "border-t border-border-200")}>
                  <span className={cn("w-[52px] shrink-0 font-mono text-[12px] tabular-nums", p.own ? "text-text-400" : "text-text-000")}>:{p.port}</span>
                  <div className="min-w-0 flex-1">
                    <div className="flex min-w-0 items-baseline gap-1.5">
                      <span className="truncate text-text-100">{p.name || "unknown"}</span>
                      <span className="shrink-0 text-[10px] text-text-500">PID {p.pid}</span>
                    </div>
                    <div className="truncate text-[10px] text-text-500" title={p.addresses.join(", ")}>
                      {p.own ? <span className="text-accent">{p.own}</span> : hint || (p.local ? "this computer only" : "reachable from the network")}
                      {" · "}{p.addresses.map((a) => (a === "0.0.0.0" || a === "[::]" || a === "::" ? "all addresses" : a)).filter((a, j, s) => s.indexOf(a) === j).join(", ")}
                    </div>
                  </div>
                  {web && <RowBtn tip="Open in the Browser panel" onClick={() => openInBrowser(p.url)}><I.GlobeSm size={12} /></RowBtn>}
                  {web && <RowBtn tip="Open in your browser" onClick={() => openExternal(p.url)}><I.External size={11} /></RowBtn>}
                  <RowBtn tip="Copy the address" onClick={() => copy(p.url, "Address copied")}><I.Copy size={11} /></RowBtn>
                  {!p.own && <RowBtn tip="Stop this program" danger onClick={() => stop(p)}><I.Square size={10} /></RowBtn>}
                </div>
              );
            })}
          </Card>
        )}
        {rows && !all && hidden > 0 && !!shown.length && <Hint className="mt-2">{hidden} system port{hidden > 1 ? "s" : ""} hidden. <button className="text-link underline-offset-2 hover:underline" onClick={() => setAll(true)}>Show all</button></Hint>}
      </div>
    </div>
  );
}
