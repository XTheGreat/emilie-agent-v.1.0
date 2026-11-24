// Settings -> Usage: tokens across all sessions, by provider and model, in total and per day (emilie/usage_log.py).
// One range filter on top scopes every number below it. Chart rules from the dataviz guide: one series in one validated
// hue (--chart-1), slim square-ended bars (5px rows, columns <= 10px taking half their slot), hairline solid grid,
// compact ticks, a hover and keyboard tooltip per column, and a table view with the same numbers.
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { get as apiGet } from "@/lib/api";
import type { Field } from "@/lib/types";
import { cn } from "@/lib/util";
import { Segmented, Spinner } from "./ui";

interface ModelRow { provider: string; label: string; model: string; calls: number; in: number; out: number; estimated: number }
interface Bucket { day: string; calls: number; in: number; out: number; models: Record<string, number> }
interface UsageData {
  since: number | null; start: string; end: string; days: number | null; weekly: boolean;
  models: ModelRow[]; total: { calls: number; in: number; out: number; estimated: number }; series: Bucket[];
}

const compact = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 });
const full = new Intl.NumberFormat("en-US");
/** In full under 10,000, compact above (1,284 / 12.9K / 1.2M). */
const fmt = (n: number) => (n < 10000 ? full.format(n) : compact.format(n));
const MONTH = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const dayLabel = (d: string, withYear = false) => {
  const [y, m, dd] = d.split("-").map(Number);
  return `${MONTH[m - 1]} ${dd}${withYear ? `, ${y}` : ""}`;
};

const RANGES = [{ value: "7", label: "7 days" }, { value: "30", label: "30 days" }, { value: "90", label: "90 days" }, { value: "0", label: "All time" }];

export function UsagePanel(_: { field: Field }) {
  const [days, setDays] = useState("30");
  const [data, setData] = useState<UsageData | null>(null);
  const [busy, setBusy] = useState(false);
  const [view, setView] = useState<"chart" | "table">("chart");
  useEffect(() => {
    let alive = true;
    const load = (first: boolean) => {
      if (first) setBusy(true);
      apiGet<UsageData>("/api/usage", { days })
        .then((d) => alive && setData(d))
        .catch(() => {})
        .finally(() => alive && first && setBusy(false));
    };
    load(true);
    const t = setInterval(() => load(false), 15000);   // sessions may be running while Settings is open
    return () => { alive = false; clearInterval(t); };
  }, [days]);

  if (!data) return <Spinner />;
  if (data.since === null) {
    return (
      <div className="rounded-[9px] border border-border-300 px-4 py-5 text-[11.5px] leading-relaxed text-text-300">
        <div className="mb-1 text-[12px] font-medium text-text-100">Nothing counted yet</div>
        From now on every request Emilie sends to a model is counted here, by provider and model, day by day, in the
        terminal and in this app. Sessions from before this version were not counted.
      </div>
    );
  }
  const tot = data.total;
  const rangeName = RANGES.find((r) => r.value === days)?.label.toLowerCase() || "";
  return (
    <div className={cn("flex flex-col transition-opacity", busy && "opacity-60")}>
      <div className="flex items-center gap-3">
        <Segmented value={days} onChange={setDays} options={RANGES} />
        <span className="text-[10.5px] text-text-400">
          {dayLabel(data.start, true)} to {dayLabel(data.end, true)}
        </span>
      </div>

      <Heading>By provider and model</Heading>
      {data.models.length ? <ModelList rows={data.models} /> : <Empty>No requests in the {days === "0" ? "log" : `last ${rangeName}`}.</Empty>}

      <Heading>Overall</Heading>
      <div className="grid grid-cols-4 gap-[8px]">
        <Tile label="Total tokens" value={tot.in + tot.out} />
        <Tile label="Input" value={tot.in} />
        <Tile label="Output" value={tot.out} />
        <Tile label="Requests" value={tot.calls} />
      </div>
      <p className="mt-[7px] text-[10.5px] leading-snug text-text-400">
        Counting since {new Date((data.since || 0) * 1000).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}.
        Input includes the conversation history Emilie resends with every request, so it grows with long sessions.
        {tot.estimated > 0 && ` ${full.format(tot.estimated)} request${tot.estimated === 1 ? " was" : "s were"} estimated: the provider sent no token counts.`}
      </p>

      <div className="mt-[18px] flex items-center">
        <h3 className="flex-1 text-[11px] font-semibold text-text-300">Usage over time{data.weekly ? " (per week)" : ""}</h3>
        <Segmented value={view} onChange={(v) => setView(v as "chart" | "table")}
          options={[{ value: "chart", label: "Chart" }, { value: "table", label: "Table" }]} />
      </div>
      <div className="mt-[8px]">
        {view === "chart" ? <Columns series={data.series} weekly={data.weekly} /> : <DayTable series={data.series} weekly={data.weekly} />}
      </div>
    </div>
  );
}

function Heading({ children }: { children: React.ReactNode }) {
  return <h3 className="mb-[8px] mt-[18px] text-[11px] font-semibold text-text-300">{children}</h3>;
}

function Empty({ children }: { children: React.ReactNode }) {
  return <div className="rounded-[8px] border border-border-300 px-3 py-3 text-[11px] text-text-400">{children}</div>;
}

function Tile({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-[8px] border border-border-300 px-[10px] py-[8px]" title={full.format(value)}>
      <div className="text-[10.5px] text-text-400">{label}</div>
      <div className="mt-[2px] text-[17px] font-semibold leading-[22px] text-text-100">{fmt(value)}</div>
    </div>
  );
}

/** Ranked horizontal bars, largest first, one hue: name, bar and figure per row, bars aligned. */
function ModelList({ rows }: { rows: ModelRow[] }) {
  const max = Math.max(...rows.map((r) => r.in + r.out), 1);
  return (
    <div className="flex flex-col divide-y divide-border-200 rounded-[9px] border border-border-300">
      {rows.map((r) => {
        const t = r.in + r.out;
        return (
          <div key={r.provider + "|" + r.model} className="grid grid-cols-[minmax(0,1fr)_minmax(80px,38%)_64px] items-center gap-x-[12px] px-[11px] py-[7px]">
            <div className="min-w-0">
              <div className="truncate text-[11.5px] text-text-100" title={r.model}>{r.model}</div>
              <div className="truncate text-[10.5px] text-text-400"
                title={`${full.format(r.in)} input · ${full.format(r.out)} output · ${full.format(r.calls)} requests${r.estimated ? ` (${r.estimated} estimated)` : ""}`}>
                {r.label} · {fmt(r.in)} in · {fmt(r.out)} out · {fmt(r.calls)} request{r.calls === 1 ? "" : "s"}
              </div>
            </div>
            <div className="h-[5px]" aria-hidden>
              <div className="h-full bg-[var(--chart-1)]" style={{ width: `${Math.max(1.5, (t / max) * 100)}%` }} />
            </div>
            <div className="text-right text-[11.5px] tabular-nums text-text-100" title={`${full.format(t)} tokens`}>{fmt(t)}</div>
          </div>
        );
      })}
    </div>
  );
}

/** Round axis ticks: about four steps of 1, 2, 2.5 or 5 x 10^n. */
function niceTicks(max: number): number[] {
  if (max <= 0) return [0];
  const raw = max / 4;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const norm = raw / mag;
  const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10) * mag;
  const out: number[] = [];
  for (let v = 0; v < max + step * 0.999; v += step) out.push(v);
  return out;
}

/** A plain square-ended column standing on the baseline. */
function colPath(x: number, base: number, w: number, h: number): string {
  return `M${x},${base}V${base - h}H${x + w}V${base}Z`;
}

function Columns({ series, weekly }: { series: Bucket[]; weekly: boolean }) {
  const wrap = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(560);
  const [hover, setHover] = useState<number | null>(null);
  useLayoutEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setW(el.clientWidth));
    ro.observe(el);
    setW(el.clientWidth);
    return () => ro.disconnect();
  }, []);
  const H = 150, AX = 22, L = 42, R = 2;
  const plotW = Math.max(60, w - L - R);
  const totals = series.map((b) => b.in + b.out);
  const ticks = useMemo(() => niceTicks(Math.max(0, ...totals)), [series]);
  const top = ticks[ticks.length - 1] || 1;
  const n = Math.max(1, series.length);
  const band = plotW / n;
  const bw = Math.max(1, Math.min(10, band * 0.5));        // slim: at most 10px and half the slot, the rest is air
  const y = (v: number) => H - (v / top) * H;
  // Date labels at an even step counted back from today (always labelled), as many as fit (~78px each).
  const labelIdx = useMemo(() => {
    const step = Math.max(1, Math.ceil(n / Math.max(2, Math.floor(plotW / 78))));
    return new Set(Array.from({ length: n }, (_, i) => i).filter((i) => (n - 1 - i) % step === 0));
  }, [n, plotW]);
  const hb = hover !== null ? series[hover] : null;
  const empty = totals.every((v) => v === 0);
  return (
    <div ref={wrap} className="relative select-none" onPointerLeave={() => setHover(null)}>
      <svg width={w} height={H + AX} role="img" aria-label={`Tokens per ${weekly ? "week" : "day"}`} className="block overflow-visible">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={L} x2={w - R} y1={y(t) + 0.5} y2={y(t) + 0.5} stroke={t === 0 ? "var(--chart-axis)" : "var(--chart-grid)"} strokeWidth={1} />
            <text x={L - 7} y={y(t)} dy="0.32em" textAnchor="end" className="fill-[var(--text-400)] text-[9.5px] tabular-nums">{fmt(t)}</text>
          </g>
        ))}
        {series.map((b, i) => {
          const v = totals[i];
          if (v <= 0) return null;
          const h = Math.max(1.5, H - y(v));
          return <path key={b.day} d={colPath(L + i * band + (band - bw) / 2, H, bw, h)} fill="var(--chart-1)"
            opacity={hover === null || hover === i ? 1 : 0.5} />;
        })}
        {series.map((b, i) => labelIdx.has(i) && (
          <text key={"x" + b.day} x={L + i * band + band / 2} y={H + 15}
            textAnchor={i === 0 && n > 1 ? "start" : i === n - 1 && n > 1 ? "end" : "middle"}
            dx={i === 0 && n > 1 ? -Math.min(band / 2, 4) : i === n - 1 && n > 1 ? Math.min(band / 2, 4) : 0}
            className="fill-[var(--text-400)] text-[9.5px]">{dayLabel(b.day)}</text>
        ))}
        {series.map((b, i) => (
          <rect key={"h" + b.day} x={L + i * band} y={0} width={band} height={H} fill="transparent" tabIndex={0}
            className="outline-none focus-visible:fill-[var(--hover)]"
            aria-label={`${weekly ? "Week of " : ""}${dayLabel(b.day, true)}: ${full.format(totals[i])} tokens, ${full.format(b.calls)} requests`}
            onPointerEnter={() => setHover(i)} onFocus={() => setHover(i)} onBlur={() => setHover(null)} />
        ))}
      </svg>
      {empty && <div className="pointer-events-none absolute inset-x-0 top-[56px] text-center text-[11px] text-text-400">No usage in this period</div>}
      {hb && hover !== null && (
        <Tip x={L + hover * band + band / 2} w={w} b={hb} total={totals[hover]} weekly={weekly} />
      )}
    </div>
  );
}

function Tip({ x, w, b, total, weekly }: { x: number; w: number; b: Bucket; total: number; weekly: boolean }) {
  const models = Object.entries(b.models).sort((a, c) => c[1] - a[1]);
  const W = 210;
  const left = Math.max(0, Math.min(w - W, x - W / 2));
  return (
    <div className="pointer-events-none absolute top-[-6px] z-10 rounded-[8px] border border-[var(--dropdown-border)] bg-[var(--dropdown-bg)] px-[10px] py-[7px] shadow-menu"
      style={{ left, width: W }}>
      <div className="text-[10.5px] text-text-400">{weekly ? "Week of " : ""}{dayLabel(b.day, true)}</div>
      <div className="text-[13px] font-semibold text-text-100">{full.format(total)} <span className="text-[11px] font-normal text-text-300">tokens</span></div>
      <div className="text-[10.5px] text-text-300">{fmt(b.in)} in · {fmt(b.out)} out · {full.format(b.calls)} request{b.calls === 1 ? "" : "s"}</div>
      {models.length > 1 && (
        <div className="mt-[5px] border-t border-[var(--dropdown-sep)] pt-[4px]">
          {models.slice(0, 4).map(([name, v]) => (
            <div key={name} className="flex items-baseline gap-2 text-[10.5px]">
              <span className="min-w-0 flex-1 truncate text-text-400">{name}</span>
              <span className="tabular-nums text-text-100">{fmt(v)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function DayTable({ series, weekly }: { series: Bucket[]; weekly: boolean }) {
  const rows = series.filter((b) => b.calls > 0).reverse();
  if (!rows.length) return <Empty>No usage in this period.</Empty>;
  return (
    <div className="max-h-[260px] overflow-y-auto rounded-[9px] border border-border-300">
      <table className="w-full text-[11px] tabular-nums">
        <thead className="sticky top-0 bg-bg-200 text-text-400">
          <tr className="border-b border-border-300">
            <th className="px-[10px] py-[5px] text-left font-normal">{weekly ? "Week of" : "Day"}</th>
            <th className="px-[10px] py-[5px] text-right font-normal">Input</th>
            <th className="px-[10px] py-[5px] text-right font-normal">Output</th>
            <th className="px-[10px] py-[5px] text-right font-normal">Total</th>
            <th className="px-[10px] py-[5px] text-right font-normal">Requests</th>
          </tr>
        </thead>
        <tbody className="text-text-100">
          {rows.map((b) => (
            <tr key={b.day} className="border-b border-border-200 last:border-b-0">
              <td className="px-[10px] py-[4px] text-left">{dayLabel(b.day, true)}</td>
              <td className="px-[10px] py-[4px] text-right">{full.format(b.in)}</td>
              <td className="px-[10px] py-[4px] text-right">{full.format(b.out)}</td>
              <td className="px-[10px] py-[4px] text-right">{full.format(b.in + b.out)}</td>
              <td className="px-[10px] py-[4px] text-right">{full.format(b.calls)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
