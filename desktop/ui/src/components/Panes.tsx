// The side pane, like the Claude Code desktop app: a strip of tabs (open files, Files, Terminal, Browser, Changes),
// a path bar, and the file shown with line numbers. Expand makes it take the conversation's place.
import { createElement, memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { currentLive, useStore, type PaneTab } from "@/lib/store";
import { SessionTitle } from "./TitleBar";
import { get as apiGet, post } from "@/lib/api";
import { bridge, isElectron, openPath } from "@/lib/desktop";
import { RealTerminal } from "./RealTerminal";
import { highlight } from "@/lib/markdown";
import { basename, cn, tabsThatDoNotFit } from "@/lib/util";
import * as I from "./icons";
import { Menu, MenuContent, MenuItem, MenuLabel, MenuSep, MenuSub, MenuSubContent, MenuSubTrigger, MenuTrigger, Pop, PopContent, PopTrigger } from "./ui";
import { insertIntoComposer } from "./Composer";
import { DiffView, Markdown, type DiffViewOpts } from "./Transcript";
import { Spinner, Tip } from "./ui";

const ICON: Record<string, React.ReactNode> = {
  files: <I.FolderSm size={11} />, terminal: <I.Prompt size={11} />, browser: <I.GlobeSm size={11} />, diff: <I.FileDiff size={11} />,
};

type Panel = { id: string; kind: "chat" | "viewer" | "terminal" | "browser" | "diff"; tabs: PaneTab[] };
const PANEL_TITLE: Record<string, string> = { terminal: "Terminal", browser: "Browser", diff: "Changes" };
const MIN_PX = 160;        // no panel is dragged narrower (or shorter) than this ...
const CHAT_MIN_PX = 300;   // ... and the conversation not narrower than this
const MIN_W_PX = 240;      // side by side no panel gets narrower than this, so its header icons (close, expand ...) never slide out of sight
const EASE = "cubic-bezier(.2,.8,.2,1)";
const EASE_MS = ".16s";
const MIN_FR = 0.08;       // no panel gets smaller than this share of the side area

// ------------------------------------------------------------------ the layout of the panels
/** The panels sit in a tree of splits (like Claude Code's): a leaf is one panel, a split lays its children side by side
 *  ("row") or on top of each other ("col"), each with its share of the room. Dragging a panel by its title bar docks it
 *  to the left / right / top / bottom of another panel, which re-cuts the tree. The panels themselves are NOT nested
 *  in the page like the tree (each one is positioned from its computed rectangle), so moving one never remounts it:
 *  a terminal keeps its shell, a page keeps its place. */
type LNode = { t: "leaf"; id: string } | { t: "split"; dir: "row" | "col"; kids: LNode[]; sizes: number[] };
type Edge = "left" | "right" | "top" | "bottom";
type Rect = { x: number; y: number; w: number; h: number };       // in percent of the side area
type Sep = { dir: "row" | "col"; x: number; y: number; len: number; parent: Rect; path: number[]; i: number; sizes: number[]; chatA: boolean; chatB: boolean };
const LAYOUT_KEY = "emilie.paneLayout";

const leafIds = (n: LNode | null): string[] => !n ? [] : n.t === "leaf" ? [n.id] : n.kids.flatMap(leafIds);

function norm(sizes: number[]): number[] {
  const t = sizes.reduce((a, b) => a + b, 0) || 1;
  return sizes.map((x) => x / t);
}

/** Tidy a tree: a split with one child is that child; a split inside a split of the same direction is merged into it. */
function tidy(n: LNode): LNode {
  if (n.t === "leaf") return n;
  const kids: LNode[] = [], sizes: number[] = [];
  n.kids.forEach((k0, i) => {
    const k = tidy(k0);
    if (k.t === "split" && k.dir === n.dir) k.kids.forEach((g, j) => { kids.push(g); sizes.push(n.sizes[i] * k.sizes[j]); });
    else { kids.push(k); sizes.push(n.sizes[i]); }
  });
  if (kids.length === 1) return kids[0];
  return { t: "split", dir: n.dir, kids, sizes: norm(sizes) };
}

function removeLeaf(n: LNode, id: string): LNode | null {
  if (n.t === "leaf") return n.id === id ? null : n;
  const kids: LNode[] = [], sizes: number[] = [];
  n.kids.forEach((k, i) => { const r = removeLeaf(k, id); if (r) { kids.push(r); sizes.push(n.sizes[i]); } });
  if (!kids.length) return null;
  return tidy({ t: "split", dir: n.dir, kids, sizes: norm(sizes) });
}

function dock(n: LNode, target: string, id: string, edge: Edge): LNode {
  const dir = edge === "left" || edge === "right" ? "row" : "col";
  const before = edge === "left" || edge === "top";
  const rec = (x: LNode): LNode => {
    if (x.t === "leaf") {
      if (x.id !== target) return x;
      const me: LNode = { t: "leaf", id };
      const mine = id === "chat" ? 0.65 : x.id === "chat" ? 0.35 : 0.5;          // the conversation is given more room
      return { t: "split", dir, kids: before ? [me, x] : [x, me], sizes: before ? [mine, 1 - mine] : [1 - mine, mine] };
    }
    return { ...x, kids: x.kids.map(rec) };
  };
  return tidy(rec(n));
}

/** The tree for the panels that are open now: keeps the user's arrangement, drops closed panels, puts the conversation
 *  on the left and a new panel under the last one (beside the conversation when it is the first). side: the share of
 *  the room the panels take when they first open. */
function reconcile(tree: LNode | null, ids: string[], side: number): LNode | null {
  let t = tree;
  for (const id of leafIds(t)) if (!ids.includes(id)) t = t && removeLeaf(t, id);
  for (const id of ids) {
    if (leafIds(t).includes(id)) continue;
    const me: LNode = { t: "leaf", id };
    if (!t) { t = me; continue; }
    if (id === "chat") { t = { t: "split", dir: "row", kids: [me, t], sizes: [1 - side, side] }; continue; }
    const rest = leafIds(t).filter((x) => x !== "chat");
    if (!rest.length) t = { t: "split", dir: "row", kids: [t, me], sizes: [1 - side, side] };
    else t = dock(t, rest[rest.length - 1], id, "bottom");
  }
  return t;
}

function setSizesAt(n: LNode, path: number[], sizes: number[]): LNode {
  if (n.t === "leaf") return n;
  if (!path.length) return { ...n, sizes };
  return { ...n, kids: n.kids.map((k, i) => (i === path[0] ? setSizesAt(k, path.slice(1), sizes) : k)) };
}

const has = (n: LNode) => leafIds(n).includes("chat");

function layoutTree(n: LNode, r: Rect, path: number[], rects: Map<string, Rect>, seps: Sep[]) {
  if (n.t === "leaf") { rects.set(n.id, r); return; }
  let cum = 0;
  n.kids.forEach((k, i) => {
    const f = n.sizes[i];
    const kr: Rect = n.dir === "row" ? { x: r.x + cum * r.w, y: r.y, w: f * r.w, h: r.h } : { x: r.x, y: r.y + cum * r.h, w: r.w, h: f * r.h };
    layoutTree(k, kr, [...path, i], rects, seps);
    cum += f;
    if (i < n.kids.length - 1) {
      seps.push(n.dir === "row"
        ? { dir: "row", x: r.x + cum * r.w, y: r.y, len: r.h, parent: r, path, i, sizes: n.sizes, chatA: has(n.kids[i]), chatB: has(n.kids[i + 1]) }
        : { dir: "col", x: r.x, y: r.y + cum * r.h, len: r.w, parent: r, path, i, sizes: n.sizes, chatA: has(n.kids[i]), chatB: has(n.kids[i + 1]) });
    }
  });
}

/** Which panel and which side of it the pointer is over (px inside the side area). */
function dropTarget(rects: Map<string, Rect>, box: DOMRect, cx: number, cy: number, self: string): { id: string; edge: Edge } | null {
  const px = ((cx - box.left) / box.width) * 100, py = ((cy - box.top) / box.height) * 100;
  for (const [id, r] of rects) {
    if (px < r.x || px > r.x + r.w || py < r.y || py > r.y + r.h) continue;
    if (id === self) return null;
    const u = (px - r.x) / r.w, v = (py - r.y) / r.h;
    const d = { left: u, right: 1 - u, top: v, bottom: 1 - v };
    const edge = (Object.keys(d) as Edge[]).reduce((a, b) => (d[b] < d[a] ? b : a));
    return { id, edge };
  }
  return null;
}

/** The working area, like Claude Code's: the conversation and the panels (Terminal, Browser, Changes, the file viewer)
 *  are all panels in one layout. Each has a title bar: drag it onto another panel to dock it there (it lifts off and
 *  follows the pointer); drag a splitter to resize. With no panel open the conversation simply fills the area. */
export function Pane({ cwd, chat, chatTitle }: { cwd: string; chat: React.ReactNode; chatTitle: string }) {
  const saved = Number(useStore((st) => st.settings.desktop_pane_w)) || 520;
  const paneTabs = useStore((st) => st.paneTabs);
  const box = useRef<HTMLDivElement>(null);
  const [cw, setCw] = useState(0);                      // the width of the working area
  const [tree, setTree] = useState<LNode | null>(() => {
    try { return JSON.parse(localStorage.getItem(LAYOUT_KEY) || "null"); } catch { return null; }
  });
  const [grab, setGrab] = useState<{ id: string; dx: number; dy: number; over: { id: string; edge: Edge } | null } | null>(null);
  const [resizing, setResizing] = useState(false);   // a splitter is being dragged: the panels follow at once, no easing

  const panels = useMemo<Panel[]>(() => {
    const out: Panel[] = [{ id: "chat", kind: "chat", tabs: [] }];
    for (const t of paneTabs) {
      if (t.kind === "file" || t.kind === "files") {
        const v = out.find((p) => p.kind === "viewer");
        if (v) v.tabs.push(t); else out.push({ id: "viewer", kind: "viewer", tabs: [t] });
      } else out.push({ id: t.key, kind: t.kind as Panel["kind"], tabs: [t] });
    }
    return out;
  }, [paneTabs]);
  const ids = panels.map((p) => p.id);
  const idKey = ids.join("|");
  const solo = ids.length === 1;                         // only the conversation: no title bar, no frame
  const [expanded, setExpanded] = useState<string | null>(null);   // "Expand": this panel alone fills the area
  const [snap, setSnap] = useState(false);                           // expanding / restoring is instant: no easing (and no re-fit of every panel per frame)
  const max = expanded !== null && !solo;

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setCw(el.clientWidth));
    ro.observe(el);
    setCw(el.clientWidth);
    return () => ro.disconnect();
  }, []);

  useEffect(() => { if (expanded && !ids.includes(expanded)) setExpanded(null); }, [idKey]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { useStore.setState({ paneMax: expanded !== null }); }, [expanded]);
  useEffect(() => {
    if (!snap) return;
    let b = 0;
    const a = requestAnimationFrame(() => { b = requestAnimationFrame(() => setSnap(false)); });   // easing is back once the jump is painted
    return () => { cancelAnimationFrame(a); cancelAnimationFrame(b); };
  }, [snap]);

  const side = cw > 0 ? Math.min(0.6, Math.max(0.25, saved / cw)) : 0.45;
  const eff = useMemo(() => reconcile(tree, ids, side), [tree, idKey]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    try { if (eff && leafIds(eff).length > 1) localStorage.setItem(LAYOUT_KEY, JSON.stringify(eff)); } catch { /* private window: fine */ }
  }, [eff]);

  // While a panel is held, the others already sit where they would be if it were dropped here (a live preview); the
  // panel itself stays lifted at its old size and follows the pointer, and a placeholder shows the slot it would take.
  const base: LNode | null = eff && max && expanded ? { t: "leaf", id: expanded } : eff;
  const over = grab?.over;
  const rest = grab && over && base ? removeLeaf(base, grab.id) : null;
  const lay = rest ? dock(rest, over!.id, grab!.id, over!.edge) : base;
  const rects = new Map<string, Rect>(), seps: Sep[] = [];
  if (lay) layoutTree(lay, { x: 0, y: 0, w: 100, h: 100 }, [], rects, seps);
  const baseRects = new Map<string, Rect>();
  if (grab && base) layoutTree(base, { x: 0, y: 0, w: 100, h: 100 }, [], baseRects, []);
  const order = leafIds(lay);
  const inset = solo || max ? 0 : 0.5;

  const startSplit = (sp: Sep) => (e: React.MouseEvent) => {
    e.preventDefault();
    const b = box.current!.getBoundingClientRect();
    const pair = sp.sizes[sp.i] + sp.sizes[sp.i + 1];
    const before = sp.sizes.slice(0, sp.i).reduce((a, c) => a + c, 0);
    const parentPx = ((sp.dir === "row" ? b.width * sp.parent.w : b.height * sp.parent.h) / 100) || 1;
    const other = sp.dir === "row" ? MIN_W_PX : MIN_PX;
    const lo = Math.min((sp.chatA ? CHAT_MIN_PX : other) / parentPx, pair / 2);
    const hi = pair - Math.min((sp.chatB ? CHAT_MIN_PX : other) / parentPx, pair / 2);
    drag((ev) => {
      const p = sp.dir === "row" ? ((ev.clientX - b.left) / b.width) * 100 : ((ev.clientY - b.top) / b.height) * 100;
      const t = (p - (sp.dir === "row" ? sp.parent.x : sp.parent.y)) / (sp.dir === "row" ? sp.parent.w : sp.parent.h);
      const first = Math.min(hi, Math.max(lo, t - before));
      const sizes = [...sp.sizes];
      sizes[sp.i] = first;
      sizes[sp.i + 1] = pair - first;
      setTree(setSizesAt(eff!, sp.path, sizes));
    }, sp.dir === "row" ? "col-resize" : "row-resize", () => setResizing(false));
    setResizing(true);
  };

  const startGrab = (id: string, e: React.MouseEvent) => {
    if (e.button !== 0 || (e.target as HTMLElement).closest("button, [role=button], input")) return;
    if (order.length < 2) return;                                   // nothing to dock it next to
    const x0 = e.clientX, y0 = e.clientY;
    let started = false;
    const b = () => box.current!.getBoundingClientRect();
    const move = (ev: MouseEvent) => {
      if (ev.buttons === 0) { up(ev); return; }              // the release was missed (a webview under the pointer)
      if (!started && Math.hypot(ev.clientX - x0, ev.clientY - y0) < 6) return;
      started = true;
      setGrab({ id, dx: ev.clientX - x0, dy: ev.clientY - y0, over: dropTarget(rects, b(), ev.clientX, ev.clientY, id) });
    };
    const up = (ev: MouseEvent) => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
      window.removeEventListener("blur", blur);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      document.body.classList.remove("dragging");
      if (!started) return;
      const t = dropTarget(rects, b(), ev.clientX, ev.clientY, id);
      setGrab(null);
      if (!t) return;
      const rest = removeLeaf(eff!, id);
      if (rest) setTree(dock(rest, t.id, id, t.edge));
    };
    const blur = () => up(new MouseEvent("mouseup", { clientX: x0, clientY: y0 }));
    document.body.style.cursor = "grabbing";
    document.body.style.userSelect = "none";
    document.body.classList.add("dragging");
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    window.addEventListener("blur", blur);
  };

  const geo = (r: Rect): React.CSSProperties =>
    ({ left: `calc(${r.x}% + ${inset}px)`, top: `calc(${r.y}% + ${inset}px)`, width: `calc(${r.w}% - ${inset * 2}px)`, height: `calc(${r.h}% - ${inset * 2}px)` });

  return (
    <div ref={box} className={cn("relative min-h-0 min-w-0 flex-1", solo || max ? "bg-bg-100" : "bg-border-300 dark:bg-[#353535]")}>
      {panels.map((p) => {
        const r = grab?.id === p.id ? baseRects.get(p.id) : rects.get(p.id);     // the lifted one keeps its own size
        return (
          <PanelView key={p.id} p={p} cwd={cwd} chat={chat} chatTitle={chatTitle} solo={solo}
            expanded={expanded === p.id} onExpand={() => { setSnap(true); setExpanded(expanded === p.id ? null : p.id); }}
            lift={grab?.id === p.id ? grab : null} ease={!resizing && !snap}
            onGrab={(e) => startGrab(p.id, e)} style={r ? geo(r) : { display: "none" }} />
        );
      })}
      {grab && rects.get(grab.id) && (
        <div className="absolute rounded-[3px] border border-accent/40 bg-bg-200"
          style={{ ...geo(rects.get(grab.id)!), transition: ["left", "top", "width", "height"].map((k) => `${k} ${EASE_MS} ${EASE}`).join(", ") }} />
      )}
      {seps.map((sp, i) => (
        <div key={i} onMouseDown={startSplit(sp)}
          className={cn("absolute z-10 hover:bg-accent/30", grab && "pointer-events-none", sp.dir === "row" ? "w-[7px] -translate-x-1/2 cursor-col-resize" : "h-[7px] -translate-y-1/2 cursor-row-resize")}
          style={sp.dir === "row" ? { left: `${sp.x}%`, top: `${sp.y}%`, height: `${sp.len}%` } : { left: `${sp.x}%`, top: `${sp.y}%`, width: `${sp.len}%` }} />
      ))}
    </div>
  );
}

/** A drag with the mouse. A <webview> / <iframe> under the pointer (the Browser panel) swallows the mouse events, so the
 *  release is never seen and the drag stays "held": while dragging they are made transparent to the mouse (body.dragging),
 *  and the drag also ends if a move arrives with no button down, or the window loses focus. */
function drag(move: (e: MouseEvent) => void, cursor: string, onEnd?: () => void) {
  const mv = (e: MouseEvent) => { if (e.buttons === 0) up(); else move(e); };
  const up = () => {
    window.removeEventListener("mousemove", mv);
    window.removeEventListener("mouseup", up);
    window.removeEventListener("blur", up);
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
    document.body.classList.remove("dragging");
    onEnd?.();
  };
  document.body.style.cursor = cursor;
  document.body.style.userSelect = "none";
  document.body.classList.add("dragging");
  window.addEventListener("mousemove", mv);
  window.addEventListener("mouseup", up);
  window.addEventListener("blur", up);
}

type Lift = { dx: number; dy: number } | null;

/** How a panel sits and moves: lifted it follows the pointer as a floating card (a transform, so it never remounts and
 *  nothing clips it); otherwise its position and size ease to where the layout puts them. */
function frame(style: React.CSSProperties, lift: Lift, ease: boolean): { className: string; style: React.CSSProperties } {
  const t = ["left", "top", "width", "height", "transform"].map((k) => `${k} ${EASE_MS} ${EASE}`).join(", ");
  return {
    className: cn("absolute flex min-h-0 min-w-0 flex-col bg-bg-100", lift && "pointer-events-none z-40 overflow-hidden rounded-[10px] shadow-2xl ring-1 ring-border-400"),
    style: { ...style, transform: lift ? `translate3d(${lift.dx}px, ${lift.dy}px, 0) scale(1.015)` : "none",
      transition: lift ? "box-shadow .15s" : ease ? t : "none", willChange: lift ? "transform" : undefined },
  };
}

function PanelView({ p, cwd, chat, chatTitle, solo, expanded, onExpand, style, lift, ease, onGrab }:
  { p: Panel; cwd: string; chat: React.ReactNode; chatTitle: string; solo: boolean; expanded: boolean; onExpand: () => void; style: React.CSSProperties; lift: Lift; ease: boolean; onGrab: (e: React.MouseEvent) => void }) {
  const paneActive = useStore((st) => st.paneActive);
  const inSession = useStore((st) => !!currentLive(st));
  const wid = useStore((st) => currentLive(st)?.wid || "none");
  const f = frame(style, lift, ease);
  const closePanel = () => {
    const s = useStore.getState();
    const keep = s.paneTabs.filter((t) => !p.tabs.some((x) => x.key === t.key));
    const act = keep.find((t) => t.key === s.paneActive) ? s.paneActive : keep[keep.length - 1]?.key || null;
    const k = keep.find((t) => t.key === act);
    useStore.setState({ paneTabs: keep, paneActive: act, pane: k ? (k.kind === "file" ? "files" : (k.kind as any)) : null, paneMax: keep.length ? s.paneMax : false });
  };
  if (p.kind === "chat") {
    return (
      <section className={f.className} style={f.style}>
        {!solo && (
          <div onMouseDown={onGrab} className="flex h-[27px] shrink-0 cursor-grab items-center gap-1.5 border-b border-border-300 px-3 text-[11.5px] text-text-100 dark:border-[#353535]">
            {inSession ? <span className="flex min-w-0" onMouseDown={(e) => e.stopPropagation()}><SessionTitle /></span>
              : <span className="min-w-0 truncate">{chatTitle}</span>}
          </div>
        )}
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">{chat}</div>
      </section>
    );
  }
  if (p.kind === "diff") {
    return (
      <section className={f.className} style={f.style}>
        <DiffPane cwd={cwd} onGrab={onGrab} max={expanded} onExpand={onExpand} onClose={closePanel} />
      </section>
    );
  }
  if (p.kind === "terminal" && bridge?.ptyCreate) {
    return (
      <section className={f.className} style={f.style}>
        <RealTerminal cwd={cwd} fallback={<TerminalPane cwd={cwd} />} chrome={{ onGrab, expanded, onExpand, onClose: closePanel }} />
      </section>
    );
  }
  if (p.kind === "browser") {
    return (
      <section className={f.className} style={f.style}>
        <BrowserPane key={wid} wid={wid} chrome={{ onGrab, expanded, onExpand, onClose: closePanel }} />
      </section>
    );
  }
  const tab = p.kind === "viewer" ? (p.tabs.find((t) => t.key === paneActive) || p.tabs[p.tabs.length - 1]) : p.tabs[0];
  return (
    <section className={f.className} style={f.style}>
      <div onMouseDown={onGrab} className="flex h-[27px] shrink-0 cursor-grab items-center gap-1 border-b border-border-300 px-2 dark:border-[#353535]">
        <div className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto">
          {p.kind === "viewer"
            ? p.tabs.map((t) => <TabChip key={t.key} t={t} active={t.key === tab.key} />)
            : <span className="flex h-[22px] items-center gap-1.5 px-1 text-[11.5px] text-text-100"><span className="text-text-300">{ICON[p.kind]}</span>{PANEL_TITLE[p.kind]}</span>}
        </div>
        <Tip content={expanded ? "Restore" : "Expand"}>
          <button onClick={onExpand} className="flex h-[22px] w-[22px] items-center justify-center rounded-[5px] text-text-100 hover:bg-hover">
            {expanded ? <I.Shrink size={12} /> : <I.Expand size={12} />}
          </button>
        </Tip>
        <Tip content="Close">
          <button onClick={closePanel} className="flex h-[22px] w-[22px] items-center justify-center rounded-[5px] text-text-100 hover:bg-hover"><I.X size={13} /></button>
        </Tip>
      </div>
      <div className="min-h-0 flex-1 overflow-hidden">
        {tab.kind === "file" && <FileTab key={tab.key} path={tab.path!} cwd={cwd} />}
        {tab.kind === "files" && <FilesPane cwd={cwd} />}
        {tab.kind === "terminal" && (bridge?.ptyCreate ? <RealTerminal cwd={cwd} fallback={<TerminalPane cwd={cwd} />} /> : <TerminalPane cwd={cwd} />)}
      </div>
    </section>
  );
}

function TabChip({ t, active }: { t: PaneTab; active: boolean }) {
  const s = useStore.getState();
  return (
    <div role="button" onClick={() => s.activateTab(t.key)} title={t.path || t.title}
      className={cn("group flex h-[22px] shrink-0 items-center gap-1.5 rounded-[5px] pl-2 pr-1 text-[11.5px]",
        active ? "bg-bg-400 text-text-000" : "text-text-300 hover:bg-hover hover:text-text-100")}>
      {t.kind !== "file" && <span className="text-text-300">{ICON[t.kind]}</span>}
      <span className={cn("max-w-[180px] truncate", t.kind === "file" && "italic")}>{t.title}</span>
      <button aria-label="Close tab" onClick={(e) => { e.stopPropagation(); s.closeTab(t.key); }}
        className={cn("flex h-[16px] w-[16px] items-center justify-center rounded-[4px] hover:bg-hover", !active && "opacity-0 group-hover:opacity-100")}>
        <I.X size={10} />
      </button>
    </div>
  );
}

// ------------------------------------------------------------------ a file, with line numbers
function FileTab({ path, cwd }: { path: string; cwd: string }) {
  const [file, setFile] = useState<any>(null);
  const [source, setSource] = useState(false);
  const seq = useRef(0);                                  // a slow answer for a file you already left must not replace the one on screen
  const load = () => {
    const n = ++seq.current;
    setFile(null);
    apiGet("/api/fs/read", { cwd, path }).then((r) => { if (n === seq.current) setFile(r); })
      .catch((e) => { if (n === seq.current) setFile({ kind: "error", error: e.message }); });
  };
  useEffect(() => { load(); return () => { seq.current++; }; }, [path]);   // eslint-disable-line react-hooks/exhaustive-deps
  // inside the project the path is shown from the project folder ("docs \ DESKTOP.md"), like Claude Code
  const root = cwd.replace(/[\\/]+$/, "");
  const inside = !!root && path.toLowerCase().startsWith(root.toLowerCase() + (path[root.length] === "/" ? "/" : "\\"));
  const parts = (inside ? path.slice(root.length + 1) : path).split(/[\\/]/).filter(Boolean);
  const markdown = file?.kind === "text" && /^(md|markdown|mdx)$/i.test(String(file.ext || "").replace(/^\./, ""));
  return (
    <div className="flex h-full flex-col">
      {/* the path sits between two lines: the tab row's and its own */}
      <div className="flex h-[34px] shrink-0 items-center gap-1 border-b border-border-300 px-3 text-[11px] dark:border-[#353535]">
        <div className="flex min-w-0 flex-1 items-center text-text-400" title={path}>
          {/* the folders shrink (with an ellipsis) so the file name always stays readable */}
          <span className="min-w-0 truncate">
            {parts.slice(0, -1).map((p, i) => <span key={i}>{i > 0 && <span className="mx-1">\</span>}{p}</span>)}
          </span>
          {parts.length > 1 && <span className="mx-1 shrink-0">\</span>}
          <span className="shrink-0 text-text-100">{parts[parts.length - 1]}</span>
        </div>
        {markdown && (
          <Tip content={source ? "Show it rendered" : "Show the source"}>
            <button className={cn("flex h-[20px] w-[20px] items-center justify-center rounded text-text-200 hover:bg-hover", source && "bg-active")}
              onClick={() => setSource(!source)}><I.CodeBrackets size={12} /></button>
          </Tip>
        )}
        <Tip content="Mention in chat"><button className="flex h-[20px] w-[20px] items-center justify-center rounded text-text-200 hover:bg-hover" onClick={() => insertIntoComposer(`@${path.replace(/\\/g, "/")} `)}><I.AtSign size={11} /></button></Tip>
        <Tip content="Open with the default app"><button className="flex h-[20px] w-[20px] items-center justify-center rounded text-text-200 hover:bg-hover" onClick={() => openPath(path)}><I.External size={11} /></button></Tip>
        <Tip content="Reload"><button className="flex h-[20px] w-[20px] items-center justify-center rounded text-text-200 hover:bg-hover" onClick={load}><I.Refresh size={11} /></button></Tip>
      </div>
      <div className="min-h-0 flex-1 overflow-auto" style={file?.kind === "text" && !markdown ? { background: "var(--code-bg-custom, transparent)" } : undefined}>
        {!file && <div className="p-3"><Spinner /></div>}
        {markdown && !source && <Markdown text={file.text} className="px-5 py-4" />}
        {file?.kind === "text" && (!markdown || source) && <CodeView text={file.text} ext={file.ext || ""} />}
        {file?.kind === "image" && <img src={file.url} alt="" className="m-3 max-w-[calc(100%-24px)] rounded-md" />}
        {file?.kind === "video" && <video src={file.url} controls className="m-3 max-w-[calc(100%-24px)] rounded-md" />}
        {file?.kind === "pdf" && <iframe src={file.url} className="h-full w-full border-0" title="pdf" />}
        {["large", "binary"].includes(file?.kind) && <Empty text={`${file.kind === "large" ? "Large" : "Binary"} file (${Math.round(file.size / 1024)} KB). Open it with the default app.`} />}
        {file?.kind === "error" && <div className="p-3 text-[11px] text-danger">{file.error}</div>}
      </div>
    </div>
  );
}

function CodeView({ text, ext }: { text: string; ext: string }) {
  const html = useMemo(() => highlight(text, ext), [text, ext]);
  const lines = useMemo(() => text.split("\n").length, [text]);
  return (
    <div className="code-view flex min-w-max py-1" style={{ minHeight: "100%" }}>
      <div className="gutter sticky left-0 shrink-0">
        {Array.from({ length: lines }, (_, i) => <div key={i} className={i === 0 ? "cur" : ""}>{i + 1}</div>)}
      </div>
      <pre className="m-0 pr-6 text-text-100 selectable"><code className="hljs" dangerouslySetInnerHTML={{ __html: html }} /></pre>
    </div>
  );
}

// ------------------------------------------------------------------ the folder tree
interface Entry { name: string; path: string; abs: string; dir: boolean; size: number; dim: boolean }

function FilesPane({ cwd }: { cwd: string }) {
  const [open, setOpen] = useState<Record<string, Entry[] | "loading">>({});
  const [root, setRoot] = useState<Entry[] | null>(null);
  const [err, setErr] = useState("");
  const openFile = useStore((s) => s.openFile);
  const load = async (rel: string) => (await apiGet<{ entries: Entry[] }>("/api/fs/list", { cwd, path: rel })).entries;
  const gen = useRef(0);                                   // a refresh (or another folder) outdates answers still on their way
  const refresh = () => {
    const g = ++gen.current;
    setErr("");
    setOpen({});
    load("").then((r) => { if (g === gen.current) setRoot(r); }).catch((e) => { if (g === gen.current) setErr(e.message); });
  };
  useEffect(() => { if (cwd) refresh(); }, [cwd]);
  const toggle = async (e: Entry) => {
    if (open[e.path]) return setOpen((o) => { const n = { ...o }; delete n[e.path]; return n; });
    const g = gen.current;
    setOpen((o) => ({ ...o, [e.path]: "loading" }));
    try {
      const kids = await load(e.path);
      if (g === gen.current) setOpen((o) => (e.path in o ? { ...o, [e.path]: kids } : o));   // closed again while loading: stays closed
    } catch {
      setOpen((o) => { const n = { ...o }; delete n[e.path]; return n; });
    }
  };
  const render = (list: Entry[], depth: number): React.ReactNode => list.map((e) => (
    <div key={e.path}>
      <div onClick={() => (e.dir ? toggle(e) : openFile(e.abs))}
        className={cn("group flex h-[22px] cursor-default items-center gap-1.5 rounded-[5px] pr-1 text-[11.5px] hover:bg-hover", e.dim ? "text-text-400" : "text-text-100")}
        style={{ paddingLeft: 6 + depth * 12 }}>
        {e.dir ? (open[e.path] ? <I.ChevD size={10} className="text-text-400" /> : <I.ChevR size={10} className="text-text-400" />) : <span className="w-[10px]" />}
        {e.dir ? <I.FolderSm size={12} className="text-text-400" /> : <I.FileIcon size={12} className="text-text-400" />}
        <span className="min-w-0 flex-1 truncate">{e.name}</span>
        <Tip content="Mention in chat">
          <button className="hidden rounded p-0.5 text-text-400 hover:text-text-100 group-hover:block"
            onClick={(x) => { x.stopPropagation(); insertIntoComposer(`@${e.path.replace(/\\/g, "/")}${e.dir ? "/" : ""} `); }}><I.AtSign size={11} /></button>
        </Tip>
      </div>
      {e.dir && open[e.path] === "loading" && <div style={{ paddingLeft: 28 + depth * 12 }} className="py-1"><Spinner size={11} /></div>}
      {e.dir && Array.isArray(open[e.path]) && render(open[e.path] as Entry[], depth + 1)}
    </div>
  ));
  if (!cwd) return <Empty text="Open a session in a folder to see its files." />;
  return (
    <div className="flex h-full flex-col">
      <div className="flex h-[30px] shrink-0 items-center gap-1 px-3 text-[11px] text-text-400">
        <span className="min-w-0 flex-1 truncate" title={cwd}>{cwd}</span>
        <button className="flex h-[20px] w-[20px] items-center justify-center rounded hover:bg-hover" onClick={refresh}><I.Refresh size={11} /></button>
        <button className="flex h-[20px] w-[20px] items-center justify-center rounded hover:bg-hover" onClick={() => openPath(cwd)}><I.External size={11} /></button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-1.5 pb-2">
        {err && <div className="p-3 text-[11px] text-danger">{err}</div>}
        {!root && !err && <div className="p-3"><Spinner /></div>}
        {root && render(root, 0)}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ terminal: commands in the session folder
function TerminalPane({ cwd }: { cwd: string }) {
  const runs = useStore((s) => s.terms);
  const [cmd, setCmd] = useState("");
  const [hist, setHist] = useState<string[]>([]);
  const [hi, setHi] = useState(-1);
  const box = useRef<HTMLDivElement>(null);
  const toast = useStore((s) => s.toast);
  useEffect(() => { box.current?.scrollTo({ top: box.current.scrollHeight }); }, [runs]);
  const run = async () => {
    const c = cmd.trim();
    if (!c || !cwd) return;
    setCmd("");
    setHist((h) => [...h.filter((x) => x !== c), c].slice(-100));
    setHi(-1);
    if (c === "clear" || c === "cls") return useStore.setState({ terms: [] });
    try {
      const r = await post<{ tid: string }>("/api/term/run", { cwd, command: c });
      useStore.setState({ terms: [...useStore.getState().terms, { tid: r.tid, cwd, command: c, lines: [], code: null, at: Date.now() }] });
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  const input = useRef<HTMLInputElement>(null);
  const shell = navigator.platform.startsWith("Win") ? "PowerShell" : "bash";
  const where = cwd || "~";
  const plain = (t: string) => t.replace(/\x1b?\[[\d;]*[A-Za-z]/g, "");        // colour codes the shell prints
  // like a real terminal: the prompt and what you type sit on the LAST line, right under the output
  return (
    <div ref={box} onClick={() => { if (!window.getSelection()?.toString()) input.current?.focus(); }}
      className="h-full cursor-text overflow-y-auto px-3 py-2 font-mono text-[11.5px] leading-[16px] selectable">
      {!runs.length && <div className="mb-1 text-text-400">{shell} · {where}</div>}
      {runs.map((r) => (
        <div key={r.tid} className="mb-1.5">
          <div className="flex items-start gap-2 text-text-100">
            <span className="shrink-0 text-accent">❯</span>
            <span className="min-w-0 flex-1 break-all">{r.command}</span>
            {r.code === null ? <button className="shrink-0 font-sans text-[10.5px] text-danger hover:underline" onClick={() => post("/api/term/kill", { tid: r.tid })}>stop</button>
              : r.code !== 0 && <span className="shrink-0 font-sans text-[10.5px] text-danger">exit {r.code}</span>}
          </div>
          <div className="whitespace-pre-wrap break-words text-text-300">{plain(r.lines.join("\n"))}</div>
        </div>
      ))}
      <div className="flex items-center gap-2">
        <span className="shrink-0 text-accent">❯</span>
        <input ref={input} autoFocus value={cmd} onChange={(e) => setCmd(e.target.value)} spellCheck={false} disabled={!cwd}
          onKeyDown={(e) => {
            if (e.key === "Enter") run();
            else if (e.key === "ArrowUp" && hist.length) { e.preventDefault(); const i = Math.min(hist.length - 1, hi + 1); setHi(i); setCmd(hist[hist.length - 1 - i]); }
            else if (e.key === "ArrowDown" && hi >= 0) { e.preventDefault(); const i = hi - 1; setHi(i); setCmd(i < 0 ? "" : hist[hist.length - 1 - i]); }
            else if (e.key === "l" && e.ctrlKey) { e.preventDefault(); useStore.setState({ terms: [] }); }
          }}
          className="h-[18px] min-w-0 flex-1 bg-transparent font-mono text-[11.5px] text-text-100 caret-accent outline-none selectable" />
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ browser: starts empty in every session, like Claude's
type BTab = { id: number; url: string; title: string };
type BState = { tabs: BTab[]; active: number; next: number; viewport: "responsive" | "mobile" | "tablet" };
const browsers = new Map<string, BState>();                 // per session: what its Browser panel had open
const VIEWPORTS = { responsive: "Responsive", mobile: "Mobile (375 × 812)", tablet: "Tablet (768 × 1024)" } as const;
const DEV_ASK = "Detect this project's dev servers, write them to .claude/launch.json, then call preview_start.";

function BrowserPane({ wid, chrome }: { wid: string; chrome?: { onGrab: (e: React.MouseEvent) => void; expanded: boolean; onExpand: () => void; onClose: () => void } }) {
  const init = useMemo<BState>(() => browsers.get(wid) || { tabs: [{ id: 1, url: "", title: "" }], active: 1, next: 2, viewport: "responsive" }, [wid]);
  const [st, setSt] = useState<BState>(init);
  const [draft, setDraft] = useState("");
  const views = useRef<Record<number, any>>({});
  const strip = useRef<HTMLDivElement>(null);
  const [hidden, setHidden] = useState<number[]>([]);          // tabs that no longer fit even squeezed: the ∨ button lists them
  const [listOpen, setListOpen] = useState(false);
  const [reloads, setReloads] = useState(0);
  const asked = useStore((s) => s.browserGo);                     // an address the agent opened with browser_open
  useEffect(() => { browsers.set(wid, st); }, [wid, st]);
  const tab = st.tabs.find((t) => t.id === st.active) || st.tabs[0];
  useEffect(() => { setDraft(tab.url); }, [tab.id, tab.url]);
  useEffect(() => {
    const el = strip.current;
    if (!el) return;
    const check = () => {
      const out = tabsThatDoNotFit(st.tabs.map((t) => t.id), st.active, el.clientWidth, 56, 38);   // the selected tab never goes into the list
      setHidden((h) => (h.length === out.length && h.every((x, i) => x === out[i]) ? h : out));
    };
    el.querySelector<HTMLElement>(`[data-tid="${st.active}"]`)?.scrollIntoView({ inline: "nearest", block: "nearest" });
    check();
    const ro = new ResizeObserver(check);
    ro.observe(el);
    return () => ro.disconnect();
  }, [st.tabs.length, st.active]);
  useEffect(() => { if (!hidden.length) setListOpen(false); }, [hidden.length]);
  const patch = (id: number, p: Partial<BTab>) => setSt((s) => ({ ...s, tabs: s.tabs.map((t) => (t.id === id ? { ...t, ...p } : t)) }));
  const norm = (u: string) => {
    const v = u.trim();
    if (!v) return "";
    return /^[a-z]+:\/\//i.test(v) ? v : (/^(localhost|127\.|\d+\.\d+)/.test(v) ? "http://" : "https://") + v;
  };
  const go = (u: string) => { const v = norm(u); if (v) patch(tab.id, { url: v, title: v.replace(/^[a-z]+:\/\//i, "").replace(/\/$/, "") }); };
  useEffect(() => { if (asked?.url) go(asked.url); }, [asked?.n]);   // eslint-disable-line react-hooks/exhaustive-deps
  const addTab = () => setSt((s) => ({ ...s, tabs: [...s.tabs, { id: s.next, url: "", title: "" }], active: s.next, next: s.next + 1 }));
  const closeTab = (id: number) => setSt((s) => {
    if (s.tabs.length === 1) return { ...s, tabs: [{ id: s.next, url: "", title: "" }], active: s.next, next: s.next + 1 };
    const i = s.tabs.findIndex((t) => t.id === id);
    const tabs = s.tabs.filter((t) => t.id !== id);
    return { ...s, tabs, active: s.active === id ? tabs[Math.max(0, i - 1)].id : s.active };
  });
  // webview events: keep each tab's address and title in step with the page
  const hook = (id: number) => (el: any) => {
    if (!el || views.current[id] === el) return;
    views.current[id] = el;
    el.addEventListener("did-navigate", (e: any) => patch(id, { url: e.url }));
    el.addEventListener("did-navigate-in-page", (e: any) => patch(id, { url: e.url }));
    el.addEventListener("page-title-updated", (e: any) => patch(id, { title: e.title }));
  };
  const cur = () => views.current[tab.id];
  const askDev = () => {
    const l = currentLive(useStore.getState());
    if (l) useStore.getState().send(l.wid, DEV_ASK, [], []);
  };
  const shot = async () => {
    try {
      const img = await cur()?.capturePage?.();
      if (!img) return;
      const a = document.createElement("a");
      a.href = img.toDataURL(); a.download = "screenshot.png"; a.click();
    } catch { /* the page is not ready */ }
  };
  const openHtml = async () => {
    const p = await bridge?.pickFile?.({ title: "Open an HTML file", filters: [{ name: "HTML", extensions: ["html", "htm"] }] });
    if (p) go("file:///" + p.replace(/\\/g, "/"));
  };
  const clearData = async () => {
    try { await cur()?.executeJavaScript?.("localStorage.clear();sessionStorage.clear();document.cookie.split(';').forEach(c=>document.cookie=c.split('=')[0]+'=;expires=Thu,01 Jan 1970 00:00:00 GMT;path=/')"); } catch { /* none */ }
    cur()?.reload?.();
  };
  const btn = "flex h-[22px] w-[22px] items-center justify-center rounded-[5px] text-text-100 hover:bg-hover disabled:opacity-35";
  const vp = st.viewport === "mobile" ? { w: 375 } : st.viewport === "tablet" ? { w: 768 } : null;
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div onMouseDown={chrome?.onGrab} className="flex h-[34px] shrink-0 cursor-grab items-center gap-1 border-b border-border-300 px-2 dark:border-[#353535]">
        <div ref={strip} className="flex min-w-0 flex-1 items-center gap-1 overflow-hidden">
          {st.tabs.map((t) => (
            <div key={t.id} data-tid={t.id} onMouseDown={(e) => e.stopPropagation()} onClick={() => setSt((s) => ({ ...s, active: t.id }))}
              className={cn("group relative flex h-[24px] max-w-[150px] shrink cursor-pointer items-center gap-1 rounded-[6px] pl-2 text-[11.5px]",
                t.id === tab.id ? "min-w-[56px] bg-active pr-1 text-text-000" : "min-w-[38px] pr-2 text-text-300 hover:bg-hover",
                hidden.includes(t.id) && "hidden")}>
              <span className="min-w-0 flex-1 truncate">{t.title || "New tab"}</span>
              {(st.tabs.length > 1 || t.url) && (
                <button onClick={(e) => { e.stopPropagation(); closeTab(t.id); }} aria-label="Close tab"
                  className={cn("flex h-[16px] w-[16px] items-center justify-center rounded text-text-400 hover:bg-hover hover:text-text-100",
                    t.id === tab.id ? "shrink-0" : "absolute right-[3px] top-[4px] bg-bg-400 opacity-0 group-hover:opacity-100")}><I.X size={10} /></button>
              )}
            </div>
          ))}
        </div>
        {hidden.length > 0 && (
          <Menu open={listOpen} onOpenChange={setListOpen}>
            <MenuTrigger asChild><button className={btn} title="More tabs" onMouseDown={(e) => e.stopPropagation()}><I.ChevD size={12} /></button></MenuTrigger>
            <MenuContent align="end" className="min-w-[220px]">
              {st.tabs.filter((t) => hidden.includes(t.id)).map((t) => (
                <div key={t.id} className="flex items-center rounded-[5px] hover:bg-active">
                  <button className="min-w-0 flex-1 truncate px-2 py-[5px] text-left text-[12px] text-text-100" onClick={() => { setSt((s) => ({ ...s, active: t.id })); setListOpen(false); }}>{t.title || "New tab"}</button>
                  <button aria-label="Close tab" onClick={() => closeTab(t.id)}
                    className="mr-0.5 flex h-[26px] w-[26px] shrink-0 items-center justify-center rounded-[5px] text-text-300 hover:bg-hover hover:text-text-000"><I.X size={15} /></button>
                </div>
              ))}
            </MenuContent>
          </Menu>
        )}
        <Tip content="New tab"><button className={btn} onClick={addTab} onMouseDown={(e) => e.stopPropagation()}><I.PlusSm size={12} /></button></Tip>
        <Menu>
          <Tip content="Dev servers"><MenuTrigger asChild><button className={btn} onMouseDown={(e) => e.stopPropagation()}><I.AppWindow size={13} /></button></MenuTrigger></Tip>
          <MenuContent align="end">
            <MenuItem onSelect={askDev}>Add server</MenuItem>
          </MenuContent>
        </Menu>
        <Menu>
          <Tip content="More"><MenuTrigger asChild><button className={btn} onMouseDown={(e) => e.stopPropagation()}><I.Dots size={13} /></button></MenuTrigger></Tip>
          <MenuContent align="end">
            <MenuItem disabled={!tab.url} onSelect={() => window.open(tab.url, "_blank")}>Open in browser</MenuItem>
            <MenuItem disabled={!tab.url} onSelect={() => navigator.clipboard?.writeText(tab.url).catch(() => {})}>Copy link</MenuItem>
            <MenuItem disabled={!tab.url || !isElectron} onSelect={shot}>Save screenshot</MenuItem>
            <MenuItem disabled={!bridge?.pickFile} onSelect={openHtml}>Open HTML file…</MenuItem>
            <MenuSep />
            <MenuSub>
              <MenuSubTrigger>Viewport</MenuSubTrigger>
              <MenuSubContent>
                {(Object.keys(VIEWPORTS) as (keyof typeof VIEWPORTS)[]).map((k) => (
                  <MenuItem key={k} checked={st.viewport === k} onSelect={() => setSt((s) => ({ ...s, viewport: k }))}>{VIEWPORTS[k]}</MenuItem>
                ))}
              </MenuSubContent>
            </MenuSub>
            <MenuSep />
            <MenuItem disabled={!tab.url || !isElectron} onSelect={clearData}><span className="text-danger">Clear browsing data</span></MenuItem>
          </MenuContent>
        </Menu>
        {chrome && (
          <Tip content={chrome.expanded ? "Restore" : "Expand"}>
            <button className={btn} onClick={chrome.onExpand} onMouseDown={(e) => e.stopPropagation()}>{chrome.expanded ? <I.Shrink size={12} /> : <I.Expand size={12} />}</button>
          </Tip>
        )}
        {chrome && <Tip content="Close"><button className={btn} onClick={chrome.onClose} onMouseDown={(e) => e.stopPropagation()}><I.X size={13} /></button></Tip>}
      </div>
      <div className="flex h-[32px] shrink-0 items-center gap-1 px-2">
        <button className={btn} disabled={!isElectron || !tab.url} onClick={() => cur()?.goBack?.()}><I.ChevL size={12} /></button>
        <button className={btn} disabled={!isElectron || !tab.url} onClick={() => cur()?.goForward?.()}><I.ChevR size={12} /></button>
        <button className={btn} disabled={!tab.url} onClick={() => (isElectron ? cur()?.reload?.() : setReloads((n) => n + 1))}><I.Refresh size={11} /></button>
        <input value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => e.key === "Enter" && go(draft)} placeholder="Type a URL"
          className="h-[24px] flex-1 rounded-[6px] bg-bg-400 px-2.5 text-[11.5px] outline-none placeholder:text-text-500 selectable" />
      </div>
      <div className="relative min-h-0 flex-1 overflow-auto bg-bg-100">
        {st.tabs.map((t) => (
          <div key={t.id} className={cn("absolute inset-0 flex justify-center bg-bg-100", t.id !== tab.id && "hidden")}>
            {t.url ? (
              <div className="h-full bg-white" style={{ width: vp ? vp.w : "100%", maxWidth: "100%" }}>
                {isElectron
                  ? createElement("webview", { ref: hook(t.id), src: t.url, style: { width: "100%", height: "100%" }, allowpopups: "true" })
                  : <iframe key={`${t.url}|${reloads}`} src={t.url} className="h-full w-full border-0" title="preview" />}
              </div>
            ) : (
              <div className="flex h-full max-w-[300px] flex-col items-center justify-center gap-2 px-4 text-center">
                <I.Globe size={22} className="text-text-500" />
                <div className="mt-2 text-[13px] font-medium text-text-100">Browse with Emilie</div>
                <div className="text-[11.5px] leading-[16px] text-text-400">Type a URL or ask Emilie to open a site. Emilie can read, click, and type.</div>
                <div className="mt-3 text-[11.5px] text-text-400">Preview your app instead?{" "}
                  <button className="text-text-100 underline-offset-2 hover:underline" onClick={askDev}>Detect dev server</button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ git changes
type GitFile = { path: string; status?: string; nodiff?: string };
type DiffFile = { path: string; status: string; nodiff: string; added: number; removed: number; large: boolean; diffObj: { text: string; added: number; removed: number } };
type Commit = { hash: string; subject: string; author: string; when: string };
type GitInfo = { branch: string; branches: string[]; default: string; commits: Commit[] };
type DiffMode = { kind: "all" | "uncommitted" | "commit"; base?: string; commit?: string };
const IMG_EXT = /\.(png|jpe?g|gif|webp|ico|bmp|svg|avif)$/i;
const CODE_EXT = /\.(py|js|jsx|ts|tsx|cjs|mjs|json|toml|ya?ml|css|html?|sh|ps1|rs|go|java|c|h|cpp)$/i;
const LARGE_DIFF = 1500;                                   // lines; over this a file gets a "Large diff" badge
type ListPos = "auto" | "right" | "hidden";
type ViewState = DiffViewOpts & { pos: ListPos; lines: number; listW: number };
const VIEW_KEY = "emilie.changesView";
const DEFAULT_VIEW: ViewState = { wrap: true, split: false, nums: true, ws: false, pos: "auto", lines: 600, listW: 232 };
const LIST_MIN_PX = 150;       // the file list on the right: never narrower than this while it is dragged ...
const LIST_CLOSE_PX = 110;     // ... but dragged down to this it closes
const MAIN_MIN_PX = 90;        // the diffs keep at least this much room: the list can be dragged wide until the main part is just a thin strip
const LIST_BTN_PX = 300;        // narrower than this the panel hides the list button (and the list); wider, they come back
const POS_LABEL: Record<ListPos, string> = { auto: "Automatic", right: "Right", hidden: "Hidden" };
const PAL_ROWS = 12;                                       // rows the file search shows at once
const HUGE_DIFF = 5000;                                    // changed lines; over this the header says so too

const fileIcon = (p: string) => IMG_EXT.test(p) ? <I.ImageIcon size={12} /> : CODE_EXT.test(p) ? <I.CodeBrackets size={12} /> : <I.FileText size={12} />;

function MenuSearch({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder: string }) {
  return (
    <input autoFocus value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
      onKeyDown={(e) => e.stopPropagation()}                 // the menu would take the typed letters for its own search
      className="mb-1 w-full bg-transparent px-2 py-1.5 text-[12px] text-text-100 outline-none placeholder:text-text-500" />
  );
}

/** One file of the changes. Memoised: dragging the panel's edge changes only the sizes it is given, so the cards of a long
 *  list are not rebuilt (menus and all) on every frame of the drag. */
const FileCard = memo(function FileCard({ f, isOpen, tight, tiny, cwd, lines, view, onToggle, openFile }:
  { f: DiffFile; isOpen: boolean; tight: boolean; tiny: boolean; cwd: string; lines: number; view: DiffViewOpts; onToggle: (p: string) => void; openFile: (p: string) => void }) {
  const i = f.path.lastIndexOf("/"), name = f.path.slice(i + 1), dir = i > 0 ? f.path.slice(0, i) : "";
  const full = `${cwd}\\${f.path.replace(/\//g, "\\")}`;
  const tone = f.status === "A" ? "text-ok" : f.status === "D" ? "text-danger" : "text-text-100";
  return (
      <div key={f.path} data-path={f.path} className={cn("diff-card", isOpen && "border-y border-border-300 bg-bg-200")}>
        <div className={cn("group relative flex h-[22px] items-center text-[10.5px] hover:bg-hover", tight ? "gap-1 px-1.5" : "gap-1.5 px-2.5", !f.nodiff && "cursor-pointer")}
          onClick={() => !f.nodiff && onToggle(f.path)}>
          <span className="w-[10px] shrink-0 text-text-400">{f.nodiff ? null : isOpen ? <I.ChevD size={10} /> : <I.ChevR size={10} />}</span>
          <span className="shrink-0 text-text-400">{fileIcon(f.path)}</span>
          {/* the folder gives way first (cut with an ellipsis), then the name a little; the counts are never dropped */}
          <span className="flex min-w-0 flex-1 items-baseline gap-1.5">
            <span className={cn("min-w-0 shrink-[0.25] truncate font-normal", tone)}>{name}</span>
            {dir && <span className="min-w-0 truncate text-[9.5px] text-text-500">{dir}</span>}
            {f.nodiff === "Too large to show" && <span className="shrink-0 text-[9.5px] text-text-500">{f.nodiff}</span>}
          </span>
          {f.large && !tight && <span className="shrink-0 rounded-full border border-border-300 px-1.5 text-[9.5px] text-text-400">Large diff</span>}
          {f.added > 0 && <span className="shrink-0 text-[10px] tabular-nums text-ok">+{f.added}</span>}
          {f.removed > 0 && <span className="shrink-0 text-[10px] tabular-nums text-danger">−{f.removed}</span>}
          <button title="Open file" disabled={f.status === "D"}
            className={cn("flex shrink-0 items-center justify-center rounded text-text-400 hover:bg-hover hover:text-text-100 disabled:opacity-30", tight ? "h-[16px] w-[16px]" : "h-[18px] w-[18px]")}
            onClick={(e) => { e.stopPropagation(); openFile(full); }}>↗</button>
          <Menu>
            <MenuTrigger asChild>
              <button title="More" onClick={(e) => e.stopPropagation()}
                className={cn("flex shrink-0 items-center justify-center rounded text-text-400 hover:bg-hover hover:text-text-100", tight ? "h-[16px] w-[16px]" : "h-[18px] w-[18px]")}><I.Dots size={11} /></button>
            </MenuTrigger>
            <MenuContent align="end" onClick={(e) => e.stopPropagation()}>
              <MenuItem onSelect={() => insertIntoComposer(`@${f.path} `)}>Attach as context</MenuItem>
              <MenuSub>
                <MenuSubTrigger>Copy</MenuSubTrigger>
                <MenuSubContent>
                  <MenuItem onSelect={() => navigator.clipboard?.writeText(full).catch(() => {})}>Copy path</MenuItem>
                  <MenuItem onSelect={() => navigator.clipboard?.writeText(f.path).catch(() => {})}>Copy relative path</MenuItem>
                  <MenuItem onSelect={() => navigator.clipboard?.writeText(name).catch(() => {})}>Copy file name</MenuItem>
                </MenuSubContent>
              </MenuSub>
              <MenuSep />
              <MenuItem disabled={f.status === "D"} onSelect={() => openFile(full)}>Open file</MenuItem>
              <MenuSub>
                <MenuSubTrigger>Open in</MenuSubTrigger>
                <MenuSubContent>
                  <MenuItem disabled={f.status === "D"} onSelect={() => openPath(full)}>Default app</MenuItem>
                </MenuSubContent>
              </MenuSub>
              <MenuItem onSelect={() => openPath(full, true)}>Show in Explorer</MenuItem>
            </MenuContent>
          </Menu>
        </div>
        {isOpen && <DiffView diff={f.diffObj} max={lines} file={f.path} flat view={view} />}
      </div>
  );
});

function DiffPane({ cwd, onGrab, max, onExpand, onClose }: { cwd: string; onGrab: (e: React.MouseEvent) => void; max: boolean; onExpand: () => void; onClose: () => void }) {
  const [data, setData] = useState<{ diff: string; files: GitFile[] } | null>(null);
  const [info, setInfo] = useState<GitInfo | null>(null);
  const [err, setErr] = useState("");
  const [open, setOpen] = useState<Record<string, boolean>>({});     // every file starts collapsed
  const [sel, setSel] = useState("");
  const [mode, setMode] = useState<DiffMode>({ kind: "all" });
  const [vs, setVs] = useState<ViewState>(() => {                   // how diffs are shown (the "…" menu), kept between runs
    try { return { ...DEFAULT_VIEW, ...JSON.parse(localStorage.getItem(VIEW_KEY) || "{}") }; } catch { return DEFAULT_VIEW; }
  });
  const setV = (part: Partial<ViewState>) => setVs((v) => {
    const n = { ...v, ...part };
    try { localStorage.setItem(VIEW_KEY, JSON.stringify(n)); } catch { /* private window: fine */ }
    return n;
  });
  const viewOpts = useMemo<DiffViewOpts>(() => ({ wrap: vs.wrap, split: vs.split, nums: vs.nums, ws: vs.ws }), [vs.wrap, vs.split, vs.nums, vs.ws]);
  const root = useRef<HTMLDivElement>(null);
  const seq = useRef(0);                                          // only the newest diff request may fill the panel
  const dragOff = useRef<(() => void) | null>(null);              // ends a list drag still running if the panel is closed mid-drag
  useEffect(() => () => dragOff.current?.(), []);
  const [pw, setPw] = useState(0);                                    // the panel's width: "Automatic" shows the list when it is wide
  const [pal, setPal] = useState(false);                              // the file search (the magnifier)
  const [pq, setPq] = useState("");
  const [pi, setPi] = useState(0);
  const [commitsOpen, setCommitsOpen] = useState(true);
  const [searching, setSearching] = useState(false);
  const [filter, setFilter] = useState("");
  const [bq, setBq] = useState("");                                   // the branch / commit searches in the menu
  const [cq, setCq] = useState("");
  const main = useRef<HTMLDivElement>(null);
  const openFile = useStore((s) => s.openFile);
  const busy = useStore((s) => Object.values(s.lives).some((l) => l.cwd === cwd && l.busy));
  const modeKey = `${mode.kind}|${mode.base || ""}|${mode.commit || ""}`;
  const load = () => {
    const n = ++seq.current;
    return apiGet("/api/git/diff", { cwd, mode: mode.kind, base: mode.base || "", commit: mode.commit || "" })
      .then((r) => { if (n === seq.current) { setErr(""); setData({ diff: r.diff || "", files: r.files || [] }); } })
      .catch((e) => { if (n === seq.current) setErr(e.message); });
  };
  const loadInfo = () => apiGet("/api/git/info", { cwd }).then((r) => setInfo(r)).catch(() => {});
  useEffect(() => { if (cwd) load(); }, [cwd, busy, modeKey]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (cwd) loadInfo(); }, [cwd, busy]);          // eslint-disable-line react-hooks/exhaustive-deps
  const choose = (m: DiffMode) => { setMode(m); setData(null); setOpen({}); setSel(""); };

  const all = useMemo(() => {
    if (!data) return [];
    const chunks = new Map<string, { body: string; added: number; removed: number; lines: number }>();
    for (const chunk of data.diff.split(/^(?=diff --git )/m)) {
      if (!chunk.startsWith("diff --git")) continue;
      const m = chunk.match(/^diff --git a\/(.+?) b\/(.+)$/m);
      const body = chunk.split("\n").filter((l) => !/^(diff --git|index |new file mode|deleted file mode|similarity|rename |old mode|new mode)/.test(l)).join("\n");
      chunks.set(m ? m[2] : "?", {
        body, added: (body.match(/^\+(?!\+\+)/gm) || []).length, removed: (body.match(/^-(?!--)/gm) || []).length,
        lines: body.split("\n").length,
      });
    }
    const list: GitFile[] = data.files.length ? data.files : [...chunks.keys()].map((path) => ({ path }));
    return list.map((f) => {
      const c = chunks.get(f.path);
      const binary = !!c && /^Binary files /m.test(c.body);
      const nodiff = f.nodiff || (binary ? "Binary file" : !c ? "No preview" : "");
      const added = c?.added || 0, removed = c?.removed || 0;
      // a stable object, so the memoised DiffView is not re-rendered when only the pane's size changes
      return { path: f.path, status: f.status || "M", nodiff, added, removed, large: (c?.lines || 0) > LARGE_DIFF,
               diffObj: { text: c?.body || "", added, removed } };
    });
  }, [data]);
  const files = useMemo(() => {                                    // "Find in changes": by name or by what the diff says
    const q = filter.trim().toLowerCase();
    return q ? all.filter((f) => f.path.toLowerCase().includes(q) || f.diffObj.text.toLowerCase().includes(q)) : all;
  }, [all, filter]);
  useEffect(() => {                                                // a find opens the files it matched
    const q = filter.trim();
    if (q.length < 2) return;
    setOpen((o) => ({ ...o, ...Object.fromEntries(files.filter((f) => !f.nodiff).slice(0, 30).map((f) => [f.path, true])) }));
  }, [filter]);                                                    // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const el = root.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setPw(el.clientWidth));
    ro.observe(el);
    setPw(el.clientWidth);
    return () => ro.disconnect();
  }, []);
  const [peek, setPeek] = useState(false);                          // the list is being dragged shut: shown closed, but only final on release
  // What the user chose (vs.pos) is never overwritten by the panel's width: narrow the panel and the list (and its button)
  // go away, widen it again and they come back exactly as the user had left them.
  const canList = pw === 0 || pw >= LIST_BTN_PX;
  const listOn = canList && (vs.pos === "right" || (vs.pos === "auto" && pw >= 760));
  const palFiles = useMemo(() => {
    const q = pq.trim().toLowerCase();
    return q ? all.filter((f) => f.path.toLowerCase().includes(q)) : all;
  }, [all, pq]);
  const openable = all.filter((f) => !f.nodiff);
  const anyOpen = openable.some((f) => open[f.path]);
  const allOpen = !openable.length || openable.every((f) => open[f.path]);
  const huge = useMemo(() => all.reduce((n, f) => n + f.added + f.removed, 0) > HUGE_DIFF, [all]);

  const toggle = useCallback((p: string) => setOpen((c) => ({ ...c, [p]: !c[p] })), []);
  const pick = (p: string) => {                                    // from the list on the right: open it and bring it into view
    setSel(p);
    setOpen((c) => ({ ...c, [p]: true }));
    requestAnimationFrame(() => requestAnimationFrame(() => {
      const el = Array.from(main.current?.querySelectorAll<HTMLElement>("[data-path]") || []).find((e) => e.dataset.path === p);
      el?.scrollIntoView({ block: "start" });
    }));
  };
  if (!cwd) return <Empty text="Open a session in a folder to see its changes." />;

  const base = mode.base || info?.default || "HEAD";
  const from = mode.kind === "commit" ? (mode.commit || "") : mode.kind === "uncommitted" ? "HEAD" : base;
  const to = mode.kind === "commit" ? "commit" : "working tree";
  const bl = bq.trim().toLowerCase(), cl = cq.trim().toLowerCase();
  const branches = (info?.branches || []).filter((b) => !bl || b.toLowerCase().includes(bl));
  const commits = (info?.commits || []).filter((c) => !cl || c.subject.toLowerCase().includes(cl) || c.hash.includes(cl));
  const startList = (e: React.MouseEvent) => {                    // drag the list's left edge to size it; a tiny list closes
    e.preventDefault();
    const right = root.current!.getBoundingClientRect().right;
    let closing = false;
    const stop = () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", stop);
      window.removeEventListener("blur", stop);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      document.body.classList.remove("dragging");
      dragOff.current = null;
      if (closing) setV({ pos: "hidden" });                       // released while shut: now it really closes
      setPeek(false);
    };
    dragOff.current = () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", stop);
      window.removeEventListener("blur", stop);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      document.body.classList.remove("dragging");
    };
    const move = (ev: MouseEvent) => {
      if (ev.buttons === 0) { stop(); return; }
      const w = right - ev.clientX;
      closing = w < LIST_CLOSE_PX;
      setPeek(closing);                                           // dragged back wider before release: it opens again
      if (closing) return;
      setV({ listW: Math.round(Math.min(Math.max(w, LIST_MIN_PX), Math.max(LIST_MIN_PX, pw - MAIN_MIN_PX))) });
    };
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    window.addEventListener("mousemove", move);
    document.body.classList.add("dragging");
    window.addEventListener("mouseup", stop);
    window.addEventListener("blur", stop);
  };
  const mainW = pw - (listOn ? Math.min(vs.listW, Math.max(LIST_MIN_PX, pw - MAIN_MIN_PX)) + 1 : 0);   // room left for the diffs
  const tight = mainW > 0 && mainW < 300, tiny = mainW > 0 && mainW < 200;   // the file rows shrink their parts so name, arrow and menu stay in view
  const closeAll = () => setOpen({});
  const openAll = () => setOpen(Object.fromEntries(openable.slice(0, 80).map((f) => [f.path, true])));    // cap: a thousand diffs at once would freeze the panel
  const hdrBtn = "flex h-[24px] w-[24px] shrink-0 items-center justify-center rounded-[5px] text-text-100 hover:bg-hover";

  return (
    <div ref={root} tabIndex={-1} className="flex h-full flex-col outline-none"
      onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "f") { e.preventDefault(); setSearching(true); } }}>
      <div onMouseDown={onGrab} className="flex h-[34px] shrink-0 cursor-grab items-center gap-2 overflow-hidden border-b border-border-300 px-3 text-[12px] dark:border-[#353535]">
        <Menu>
          <MenuTrigger asChild>
            <button className="flex min-w-0 items-center gap-1.5 rounded-[5px] px-1.5 py-1 text-text-100 hover:bg-hover">
              <span className="truncate">{from}</span><span className="text-text-400">→</span><span className="truncate">{to}</span><I.ChevD size={10} />
            </button>
          </MenuTrigger>
          <MenuContent align="start" className="min-w-[230px]">
            <MenuItem checked={mode.kind === "all"} shortcut={`vs ${base}`} onSelect={() => choose({ kind: "all", base: mode.base })}>All changes</MenuItem>
            <MenuItem checked={mode.kind === "uncommitted"} onSelect={() => choose({ kind: "uncommitted" })}>Uncommitted changes</MenuItem>
            <MenuSep />
            <MenuSub>
              <MenuSubTrigger><span className="flex w-full items-center">Compare against<span className="ml-auto pl-3 text-text-500">{base}</span></span></MenuSubTrigger>
              <MenuSubContent className="w-[270px]">
                <MenuSearch value={bq} onChange={setBq} placeholder="Search branches" />
                <MenuSep />
                <div className="max-h-[260px] overflow-y-auto">
                  {branches.map((b) => (
                    <MenuItem key={b} checked={mode.kind === "all" && base === b} shortcut={b === info?.default ? "default" : undefined}
                      onSelect={() => choose({ kind: "all", base: b })}>{b}</MenuItem>
                  ))}
                  {!branches.length && <div className="px-2 py-2 text-[11.5px] text-text-500">No branches</div>}
                </div>
              </MenuSubContent>
            </MenuSub>
            <MenuSub>
              <MenuSubTrigger><span className="flex w-full items-center">Commits<span className="ml-auto pl-3 text-text-500">{info?.commits.length ?? 0}</span></span></MenuSubTrigger>
              <MenuSubContent className="w-[360px]">
                <MenuSearch value={cq} onChange={setCq} placeholder="Search commits" />
                <MenuSep />
                <div className="max-h-[260px] overflow-y-auto">
                  {commits.map((c) => (
                    <MenuItem key={c.hash} checked={mode.kind === "commit" && mode.commit === c.hash} shortcut={c.hash}
                      onSelect={() => choose({ kind: "commit", commit: c.hash })}>{c.subject}</MenuItem>
                  ))}
                  {!commits.length && <div className="px-2 py-2 text-[11.5px] text-text-500">No commits</div>}
                </div>
              </MenuSubContent>
            </MenuSub>
          </MenuContent>
        </Menu>
        {huge && pw >= 420 && <span className="shrink-0 rounded-full bg-bg-400 px-2 py-[1px] text-[10.5px] text-text-300">Large diff</span>}
        <span className="flex-1" />
        <Pop open={pal} onOpenChange={(o) => { setPal(o); if (o) { setPq(""); setPi(0); } }}>
          <PopTrigger asChild><button className={cn(hdrBtn, pal && "bg-active")} title="Search changed files"><I.SearchSm size={13} /></button></PopTrigger>
          <PopContent align="end" sideOffset={8} className="w-[340px] overflow-hidden p-0">
            <input autoFocus value={pq} onChange={(e) => { setPq(e.target.value); setPi(0); }} placeholder="Search changed files"
              onKeyDown={(e) => {
                const n = Math.min(PAL_ROWS, palFiles.length);
                if (e.key === "ArrowDown") { e.preventDefault(); setPi((pi + 1) % Math.max(1, n)); }
                else if (e.key === "ArrowUp") { e.preventDefault(); setPi((pi - 1 + Math.max(1, n)) % Math.max(1, n)); }
                else if (e.key === "Enter" && palFiles[pi]) { e.preventDefault(); setPal(false); setFilter(""); pick(palFiles[pi].path); }
              }}
              className="w-full border-b border-[var(--dropdown-sep)] bg-transparent px-3 py-2.5 text-[12.5px] text-text-100 outline-none placeholder:text-text-500" />
            <div className="p-1.5">
              {palFiles.slice(0, PAL_ROWS).map((f, i) => {
                const k = f.path.lastIndexOf("/"), name = f.path.slice(k + 1), dir = k > 0 ? f.path.slice(0, k) : "";
                return (
                  <button key={f.path} onMouseEnter={() => setPi(i)} onClick={() => { setPal(false); setFilter(""); pick(f.path); }}
                    className={cn("flex h-[28px] w-full items-center gap-2 rounded-[6px] px-2 text-left text-[12px]", i === pi && "bg-active")}>
                    <span className="shrink-0 text-text-300">{fileIcon(f.path)}</span>
                    <span className="min-w-0 flex-1 truncate"><span className="font-medium text-text-000">{name}</span>{dir && <span className="ml-1.5 text-[9.5px] text-text-500">{dir}</span>}</span>
                    {f.added > 0 && <span className="font-mono text-[11px] text-ok">+{f.added}</span>}
                    {f.removed > 0 && <span className="font-mono text-[11px] text-danger">−{f.removed}</span>}
                  </button>
                );
              })}
              {!palFiles.length && <div className="px-2 py-3 text-[11.5px] text-text-500">No file matches.</div>}
            </div>
            {palFiles.length > PAL_ROWS && (
              <div className="border-t border-[var(--dropdown-sep)] px-3 py-2 text-[11px] text-text-500">{palFiles.length - PAL_ROWS} more files. Keep typing to narrow.</div>
            )}
          </PopContent>
        </Pop>
        {canList && <Tip content="File list and commits"><button className={cn(hdrBtn, listOn && "bg-active")} onClick={() => setV({ pos: listOn ? "hidden" : "right" })}><I.MenuLines size={13} /></button></Tip>}
        <Menu>
          <MenuTrigger asChild><button className={hdrBtn} title="More"><I.Dots size={13} /></button></MenuTrigger>
          <MenuContent align="end" className="min-w-[262px]">
            <MenuSub>
              <MenuSubTrigger><span className="flex w-full items-center">File list position<span className="ml-auto pl-4 text-text-500">{POS_LABEL[vs.pos]}</span></span></MenuSubTrigger>
              <MenuSubContent>
                {(["auto", "right", "hidden"] as ListPos[]).map((k) => <MenuItem key={k} checked={vs.pos === k} onSelect={() => setV({ pos: k })}>{POS_LABEL[k]}</MenuItem>)}
              </MenuSubContent>
            </MenuSub>
            <MenuSep />
            <MenuItem shortcut="Ctrl+F" onSelect={() => setSearching(true)}>Find in changes</MenuItem>
            <MenuItem disabled={!anyOpen} onSelect={closeAll}>Collapse all files</MenuItem>
            <MenuItem disabled={allOpen} onSelect={openAll}>Expand all files</MenuItem>
            <MenuSep />
            <MenuItem checked={vs.split} onSelect={() => setV({ split: !vs.split })}>Side by side</MenuItem>
            <MenuItem checked={vs.wrap} onSelect={() => setV({ wrap: !vs.wrap })}>Word wrap</MenuItem>
            <MenuItem checked={vs.ws} onSelect={() => setV({ ws: !vs.ws })}>Hide whitespace changes</MenuItem>
            <MenuSub>
              <MenuSubTrigger>More settings</MenuSubTrigger>
              <MenuSubContent>
                <MenuItem checked={vs.nums} onSelect={() => setV({ nums: !vs.nums })}>Line numbers</MenuItem>
                <MenuSep />
                <MenuLabel>Lines shown per file</MenuLabel>
                {[[600, "600 lines"], [2000, "2000 lines"], [1000000, "All lines"]].map(([n, label]) => (
                  <MenuItem key={n} checked={vs.lines === n} onSelect={() => setV({ lines: n as number })}>{label}</MenuItem>
                ))}
              </MenuSubContent>
            </MenuSub>
            <MenuSep />
            <MenuItem onSelect={() => { load(); loadInfo(); }}>Refresh</MenuItem>
          </MenuContent>
        </Menu>
        <Tip content={max ? "Restore" : "Expand"}><button className={hdrBtn} onClick={onExpand}>{max ? <I.Shrink size={12} /> : <I.Expand size={12} />}</button></Tip>
        <Tip content="Close"><button className={hdrBtn} onClick={onClose}><I.X size={14} /></button></Tip>
      </div>
      {searching && (
        <div className="flex h-[32px] shrink-0 items-center gap-2 border-b border-border-300 px-3 dark:border-[#353535]">
          <I.SearchSm size={12} />
          <input autoFocus value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Find in changes"
            className="min-w-0 flex-1 bg-transparent text-[12px] text-text-100 outline-none placeholder:text-text-500" />
          <span className="text-[11px] text-text-500">{files.length} / {all.length}</span>
          <button className="flex h-[20px] w-[20px] items-center justify-center rounded text-text-400 hover:bg-hover hover:text-text-100" title="Close"
            onClick={() => { setSearching(false); setFilter(""); }}><I.X size={11} /></button>
        </div>
      )}
      <div className="flex min-h-0 flex-1">
        <div ref={main} className="min-w-0 flex-1 overflow-y-auto bg-changes pb-3">
          {err && <div className="p-3 text-[11px] text-danger">{err}</div>}
          {data === null && !err && <div className="p-3"><Spinner /></div>}
          {data !== null && !all.length && <Empty text="No changes (or not a git repository)." />}
          {data !== null && !!all.length && !files.length && <Empty text="No file matches." />}
          {files.map((f) => (
            <FileCard key={f.path} f={f} isOpen={!!open[f.path] && !f.nodiff} tight={tight} tiny={tiny} cwd={cwd} lines={vs.lines}
              view={viewOpts} onToggle={toggle} openFile={openFile} />
          ))}
        </div>
        {listOn && (
          <div className={cn("relative flex shrink-0 flex-col dark:border-[#353535]", peek ? "overflow-hidden border-l-0 opacity-0" : "border-l border-border-300")}
          style={{ width: peek ? 0 : Math.min(vs.listW, Math.max(LIST_MIN_PX, pw - MAIN_MIN_PX)) }}>
            <div onMouseDown={startList} className="absolute -left-[4px] top-0 z-10 h-full w-[7px] cursor-col-resize hover:bg-accent/30" />
            <div className="min-h-0 flex-1 overflow-y-auto py-1">
              {files.map((f) => {
                const i = f.path.lastIndexOf("/"), name = f.path.slice(i + 1), dir = i > 0 ? f.path.slice(0, i) : "";
                const tone = f.status === "A" ? "text-ok" : f.status === "D" ? "text-danger" : "text-text-100";
                return (
                  <button key={f.path} title={f.path} onClick={() => pick(f.path)}
                    className={cn("flex h-[21px] w-full items-center gap-1.5 rounded-[4px] px-2 text-left text-[10.5px] hover:bg-hover", sel === f.path && "bg-active")}>
                    <span className="shrink-0 text-text-400">{fileIcon(f.path)}</span>
                    <span className="min-w-0 flex-1 truncate"><span className={cn("font-normal", tone)}>{name}</span>{dir && <span className="ml-1.5 text-[9.5px] text-text-500">{dir}</span>}</span>
                    {f.added > 0 && <span className="tabular-nums text-[9.5px] text-ok">+{f.added}</span>}
                    {f.removed > 0 && <span className="tabular-nums text-[9.5px] text-danger">−{f.removed}</span>}
                  </button>
                );
              })}
            </div>
            <div className="flex max-h-[46%] min-h-0 shrink-0 flex-col border-t border-border-300 dark:border-[#353535]">
              <button onClick={() => setCommitsOpen(!commitsOpen)} className="flex h-[24px] shrink-0 items-center gap-1.5 px-2.5 text-[10.5px] text-text-100 hover:bg-hover">
                {commitsOpen ? <I.ChevD size={10} /> : <I.ChevR size={10} />}<span className="flex-1 text-left">Commits</span>
                <span className="text-[10.5px] text-text-500">{info?.commits.length ?? 0}</span>
              </button>
              {commitsOpen && (
                <div className="min-h-0 flex-1 overflow-y-auto px-1.5 pb-2">
                  <button onClick={() => choose({ kind: "all", base: mode.base })} className={cn("block w-full rounded-[5px] px-2 py-1 text-left text-[11px] hover:bg-hover", mode.kind === "all" && "bg-active")}>All changes</button>
                  <button onClick={() => choose({ kind: "uncommitted" })} className={cn("block w-full rounded-[5px] px-2 py-1 text-left text-[11px] hover:bg-hover", mode.kind === "uncommitted" && "bg-active")}>Uncommitted changes</button>
                  {(info?.commits || []).map((c) => (
                    <button key={c.hash} onClick={() => choose({ kind: "commit", commit: c.hash })}
                      className={cn("block w-full rounded-[5px] px-2 py-1 text-left hover:bg-hover", mode.kind === "commit" && mode.commit === c.hash && "bg-active")}>
                      <div className="line-clamp-2 text-[11px] leading-[14px] text-text-100">{c.subject}</div>
                      <div className="truncate text-[9.5px] text-text-500">{c.hash} · {c.author} · {c.when}</div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <div className="px-4 py-8 text-center text-[11.5px] text-text-400">{text}</div>;
}
