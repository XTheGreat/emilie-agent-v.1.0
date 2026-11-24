// The Terminal panel as a real terminal (like Claude Code's): xterm.js draws it, node-pty (in Electron's main process)
// runs PowerShell behind it. Terminals live in this module, not in the component, so closing and reopening the panel
// (or moving it in the layout) keeps what was running. Without the native module the caller shows its simple fallback.
import { useEffect, useRef, useState } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import { bridge } from "@/lib/desktop";
import { useStore } from "@/lib/store";
import { basename, cn, tabsThatDoNotFit } from "@/lib/util";
import * as I from "./icons";
import { Menu, MenuContent, MenuItem, MenuSub, MenuSubContent, MenuSubTrigger, MenuTrigger, Tip } from "./ui";

interface Sess { id: string; title: string; term: Terminal; fit: FitAddon; opened: boolean; exited: boolean }
/** What the "…" menu sets, for every terminal, kept between runs. */
interface TermPrefs { cursor: "block" | "bar" | "underline"; blink: boolean; copy: boolean; scrollback: number }
const PREF_KEY = "emilie.terminal";
const prefs: TermPrefs = (() => {
  const d: TermPrefs = { cursor: "block", blink: true, copy: false, scrollback: 10000 };
  try { return { ...d, ...JSON.parse(localStorage.getItem(PREF_KEY) || "{}") }; } catch { return d; }
})();
const sessions: Sess[] = [];
const subs = new Set<() => void>();
const notify = () => subs.forEach((f) => f());

function setPrefs(part: Partial<TermPrefs>) {
  Object.assign(prefs, part);
  try { localStorage.setItem(PREF_KEY, JSON.stringify(prefs)); } catch { /* private window: fine */ }
  for (const s of sessions) {
    s.term.options.cursorStyle = prefs.cursor;
    s.term.options.cursorBlink = prefs.blink;
    s.term.options.scrollback = prefs.scrollback;
  }
  notify();
}

/** What the panel's header needs from the layout: drag handle, Expand and Close. */
export interface TermChrome { onGrab: (e: React.MouseEvent) => void; expanded: boolean; onExpand: () => void; onClose: () => void }
let listening = false;
let counter = 0;
// The shell starts talking as soon as it exists, which can be before its terminal is registered here (ptyCreate has not
// answered yet): that first output (the prompt) is held and written once the terminal is there, instead of being lost.
let creating = 0;
const early = new Map<string, string[]>();

function ensureListener() {
  if (listening || !bridge?.onPty) return;
  listening = true;
  bridge.onPty(
    (id, data) => {
      const t = sessions.find((s) => s.id === id);
      if (t) t.term.write(data);
      else if (creating > 0) { const q = early.get(id) || []; if (q.length < 500) q.push(data); early.set(id, q); }
    },
    (id, code) => {
      const s = sessions.find((x) => x.id === id);
      if (!s) return;
      s.exited = true;
      s.term.write(`\r\n\x1b[2m[process exited with code ${code}]\x1b[0m\r\n`);
      notify();
    },
  );
}

/** The colour behind the terminal: the first opaque background up the tree, so it matches the panel in either theme. */
function panelBg(from?: HTMLElement | null): string {
  for (let el: HTMLElement | null = from || document.body; el; el = el.parentElement) {
    const c = getComputedStyle(el).backgroundColor;
    if (c && c !== "transparent" && !/rgba\(.*,\s*0\)$/.test(c)) return c;
  }
  return "#1a1a1a";
}

function themeNow(from?: HTMLElement | null) {
  const bg = panelBg(from);
  const m = bg.match(/\d+/g) || ["26", "26", "26"];
  const light = (+m[0] + +m[1] + +m[2]) / 3 > 140;
  return light
    ? { background: bg, foreground: "#2b2b2b", cursor: "#2b2b2b", selectionBackground: "#bcd7f5",
      black: "#2b2b2b", red: "#c4372f", green: "#2e7d32", yellow: "#a06a00", blue: "#1f5fbf", magenta: "#9a3fb0", cyan: "#00798c", white: "#8a8a8a",
      brightBlack: "#6b6b6b", brightRed: "#e0463d", brightGreen: "#3a9a40", brightYellow: "#b8860b", brightBlue: "#2f74da", brightMagenta: "#b24fc8", brightCyan: "#0e95ab", brightWhite: "#4a4a4a" }
    : { background: bg, foreground: "#d8d8d8", cursor: "#d8d8d8", selectionBackground: "#35507a",
      black: "#4a4a4a", red: "#f0707a", green: "#9fd47f", yellow: "#ecc576", blue: "#6cb2ff", magenta: "#d58df0", cyan: "#62cbd8", white: "#d8d8d8",
      brightBlack: "#7a7a7a", brightRed: "#ff8a92", brightGreen: "#b3e693", brightYellow: "#f7d78a", brightBlue: "#8cc4ff", brightMagenta: "#e3a6f8", brightCyan: "#7fdde8", brightWhite: "#ffffff" };
}

async function newSession(cwd: string): Promise<{ id?: string; error?: string }> {
  if (!bridge?.ptyCreate) return { error: "unavailable: not running in the desktop app" };
  ensureListener();
  creating++;
  const term = new Terminal({
    cursorBlink: prefs.blink, cursorStyle: prefs.cursor, fontSize: 12, lineHeight: 1.15, scrollback: prefs.scrollback,
    fontFamily: '"Cascadia Mono", Consolas, "Courier New", monospace', theme: themeNow(),
  });
  const fit = new FitAddon();
  term.loadAddon(fit);
  let r: { id?: string; shell?: string; error?: string };
  try { r = await bridge.ptyCreate({ cwd, cols: term.cols, rows: term.rows }); }
  catch (e: any) { creating--; early.clear(); term.dispose(); return { error: String(e?.message || e || "could not start the shell") }; }
  if (!r.id) { creating--; early.clear(); term.dispose(); return { error: r.error || "could not start the shell" }; }
  const id = r.id;
  term.onData((d) => bridge!.ptyWrite?.(id, d));
  term.onSelectionChange(() => { if (prefs.copy && term.hasSelection()) navigator.clipboard.writeText(term.getSelection()).catch(() => {}); });
  term.onResize(({ cols, rows }) => bridge!.ptyResize?.(id, cols, rows));
  // Ctrl+C with a selection copies (as in Windows Terminal); Ctrl+V pastes. Without a selection Ctrl+C is the interrupt.
  term.attachCustomKeyEventHandler((e) => {
    if (e.type === "keydown" && e.ctrlKey && !e.shiftKey && e.key.toLowerCase() === "c" && term.hasSelection()) {
      navigator.clipboard.writeText(term.getSelection()).catch(() => {});
      return false;
    }
    return true;
  });
  sessions.push({ id, title: `Terminal ${++counter}`, term, fit, opened: false, exited: false });
  for (const d of early.get(id) || []) term.write(d);
  early.delete(id);
  creating--;
  return { id };
}

/** One terminal is just "Terminal" (and cannot be closed); with two or more each has its number. */
function termName(i: number) { return sessions.length > 1 ? `Terminal ${i + 1}` : "Terminal"; }

function closeSession(id: string) {
  const i = sessions.findIndex((s) => s.id === id);
  if (i < 0 || sessions.length <= 1) return;       // the last terminal stays
  const s = sessions[i];
  bridge?.ptyKill?.(id);
  s.term.dispose();
  sessions.splice(i, 1);
  notify();
}

export function RealTerminal({ cwd, fallback, chrome }: { cwd: string; fallback: React.ReactNode; chrome?: TermChrome }) {
  const [, force] = useState(0);
  const [active, setActive] = useState<string | null>(sessions[0]?.id ?? null);
  const [err, setErr] = useState("");
  const host = useRef<HTMLDivElement>(null);
  const starting = useRef(false);
  const tabs = useRef<HTMLDivElement>(null);
  const [hidden, setHidden] = useState<string[]>([]);     // the terminals whose tab does not fit: the ∨ button lists just these
  const [listOpen, setListOpen] = useState(false);

  const add = async () => {
    if (starting.current) return;
    starting.current = true;
    let r: { id?: string; error?: string };
    try { r = await newSession(cwd); } catch (e: any) { r = { error: String(e?.message || e) }; } finally { starting.current = false; }
    if (r.id) { setActive(r.id); setErr(""); } else setErr(r.error || "");
    notify();
  };

  useEffect(() => {
    const f = () => force((n) => n + 1);
    subs.add(f);
    if (!sessions.length) add();
    return () => { subs.delete(f); };
  }, []);

  // when the active terminal was closed, move to a neighbour
  useEffect(() => {
    if (active && sessions.some((s) => s.id === active)) return;
    setActive(sessions[sessions.length - 1]?.id ?? null);
  });

  useEffect(() => {
    const el = tabs.current;
    if (!el) return;
    const check = () => {
      const out = tabsThatDoNotFit(sessions.map((s) => s.id), active, el.clientWidth, 40, 26);   // the selected terminal never goes into the list
      setHidden((h) => (h.length === out.length && h.every((x, i) => x === out[i]) ? h : out));
    };
    el.querySelector<HTMLElement>(`[data-sid="${active}"]`)?.scrollIntoView({ inline: "nearest", block: "nearest" });   // the chosen tab is shown
    check();
    const ro = new ResizeObserver(check);
    ro.observe(el);
    el.addEventListener("scroll", check);
    return () => { ro.disconnect(); el.removeEventListener("scroll", check); };
  }, [sessions.length, active]);
  useEffect(() => { if (!hidden.length) setListOpen(false); }, [hidden.length]);

  // the theme (light / dark / Eveny) changed while terminals are open: recolour them all now, no need to reopen
  useEffect(() => {
    const apply = () => requestAnimationFrame(() => {
      const t = themeNow(host.current?.parentElement);
      for (const s of sessions) s.term.options.theme = t;
    });
    const mo = new MutationObserver(apply);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "data-theme"] });
    return () => mo.disconnect();
  }, []);

  // show the active terminal in the host box, keep it fitted to the panel
  useEffect(() => {
    const s = sessions.find((x) => x.id === active);
    const el = host.current;
    if (!s || !el) return;
    el.replaceChildren();
    s.term.options.theme = themeNow(el.parentElement);
    const st = useStore.getState().settings;
    s.term.options.fontSize = Number(st.desktop_code_size) > 0 ? Number(st.desktop_code_size) : 12;
    const cf = String(st.desktop_code_font || "").replace(/["\\;{}]/g, "").trim();
    s.term.options.fontFamily = (cf ? `"${cf}", ` : "") + '"Cascadia Mono", Consolas, "Courier New", monospace';      // follows the light/dark theme each time it is shown
    if (!s.opened) { s.term.open(el); s.opened = true; } else if (s.term.element) el.appendChild(s.term.element);
    const doFit = () => { try { if (el.clientWidth > 20 && el.clientHeight > 20) s.fit.fit(); } catch { /* not laid out yet */ } };
    doFit();
    s.term.focus();
    // fitting re-flows the whole buffer and tells the shell: while the panel is moving or being resized do it at most
    // every 90 ms, plus once when it stops
    let timer = 0;
    const ro = new ResizeObserver(() => { if (!timer) timer = window.setTimeout(() => { timer = 0; doFit(); }, 90); });
    ro.observe(el);
    return () => { ro.disconnect(); if (timer) clearTimeout(timer); };
  }, [active, sessions.length]);

  const on = sessions.find((s) => s.id === active);
  const hb = "flex h-[24px] w-[24px] shrink-0 items-center justify-center rounded-[5px] text-text-100 hover:bg-hover";
  const sub = (label: string, value: string) => <span className="flex w-full items-center">{label}<span className="ml-auto pl-4 text-text-500">{value}</span></span>;
  const header = (withTabs: boolean) => (
    <div onMouseDown={chrome?.onGrab} className="flex h-[34px] shrink-0 cursor-grab items-center gap-1 border-b border-border-300 px-2 dark:border-[#353535]">
      {!withTabs && <span className="flex-1 truncate px-1 text-[11.5px] text-text-100">Terminal</span>}
      {withTabs && (
        <div ref={tabs} className="flex min-w-0 flex-1 items-center gap-1 overflow-hidden">
          {sessions.map((s, i) => (
            <div key={s.id} data-sid={s.id} role="button" onClick={() => setActive(s.id)} title={cwd}
              className={cn("group relative flex h-[24px] shrink items-center rounded-[5px] text-[11.5px]",   // squeezed first; only a very narrow tab goes into the V list
                s.id === active ? "min-w-[40px]" : "min-w-[26px]",
                s.id === active ? "bg-bg-400 text-text-000" : "text-text-300 hover:bg-hover hover:text-text-100", s.exited && "opacity-60",
                hidden.includes(s.id) && "hidden")}>
              {/* a tab is two parts, each with its own room: the title (it gives way first, down to a few letters) and the close button (always whole) */}
              <span className={cn("min-w-0 max-w-[140px] flex-1 truncate pl-1.5", sessions.length > 1 && s.id === active ? "pr-0.5" : "pr-1.5")}>{termName(i)}</span>
              {sessions.length > 1 && (
                <button aria-label="Close terminal" onClick={(e) => { e.stopPropagation(); closeSession(s.id); }}
                  className={cn("flex h-[16px] w-[16px] items-center justify-center rounded-[4px] hover:bg-hover",
                    s.id === active ? "mr-0.5 shrink-0" : "absolute right-[2px] top-[4px] bg-bg-400 opacity-0 group-hover:opacity-100")}>
                  <I.X size={10} />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
      {withTabs && hidden.length > 0 && (
        <Menu open={listOpen} onOpenChange={setListOpen}>
          <MenuTrigger asChild><button className={hb} title="More terminals"><I.ChevD size={12} /></button></MenuTrigger>
          <MenuContent align="end" className="min-w-[220px]">
            {sessions.map((s, i) => [s, i] as const).filter(([s]) => hidden.includes(s.id)).map(([s, i]) => (
              <div key={s.id} className="flex items-center rounded-[5px] hover:bg-active">
                <button className="min-w-0 flex-1 truncate px-2 py-[5px] text-left text-[12px] text-text-100" onClick={() => { setActive(s.id); setListOpen(false); }}>{termName(i)}</button>
                <button aria-label="Close terminal" title="Close terminal" onClick={() => closeSession(s.id)}
                  className="mr-0.5 flex h-[26px] w-[26px] shrink-0 items-center justify-center rounded-[5px] text-text-300 hover:bg-hover hover:text-text-000"><I.X size={15} /></button>
              </div>
            ))}
          </MenuContent>
        </Menu>
      )}
      {withTabs && <Tip content={`New terminal in ${basename(cwd) || cwd}`}><button aria-label="New terminal" onClick={add} className={hb}><I.Plus size={13} /></button></Tip>}
      {withTabs && (
        <Menu>
          <MenuTrigger asChild><button className={hb} title="Terminal settings"><I.Dots size={13} /></button></MenuTrigger>
          <MenuContent align="end" className="min-w-[210px]">
            <MenuSub>
              <MenuSubTrigger>{sub("Cursor style", { block: "Block", bar: "Bar", underline: "Underline" }[prefs.cursor])}</MenuSubTrigger>
              <MenuSubContent>
                {([["block", "Block"], ["bar", "Bar"], ["underline", "Underline"]] as const).map(([k, label]) => (
                  <MenuItem key={k} checked={prefs.cursor === k} onSelect={() => setPrefs({ cursor: k })}>{label}</MenuItem>
                ))}
              </MenuSubContent>
            </MenuSub>
            <MenuItem checked={prefs.blink} onSelect={() => setPrefs({ blink: !prefs.blink })}>Blink cursor</MenuItem>
            <MenuItem checked={prefs.copy} onSelect={() => setPrefs({ copy: !prefs.copy })}>Copy on select</MenuItem>
            <MenuSub>
              <MenuSubTrigger>{sub("Scrollback", `${prefs.scrollback.toLocaleString("en-US")} lines`)}</MenuSubTrigger>
              <MenuSubContent>
                {[1000, 5000, 10000].map((n) => (
                  <MenuItem key={n} checked={prefs.scrollback === n} onSelect={() => setPrefs({ scrollback: n })}>{n.toLocaleString("en-US")} lines</MenuItem>
                ))}
              </MenuSubContent>
            </MenuSub>
          </MenuContent>
        </Menu>
      )}
      {chrome && <Tip content={chrome.expanded ? "Restore" : "Expand"}><button className={hb} onClick={chrome.onExpand}>{chrome.expanded ? <I.Shrink size={12} /> : <I.Expand size={12} />}</button></Tip>}
      {chrome && <Tip content="Close"><button className={hb} onClick={chrome.onClose}><I.X size={14} /></button></Tip>}
    </div>
  );

  if (err.startsWith("unavailable") || (err && !sessions.length)) {
    return (
      <div className="flex h-full flex-col">
        {chrome && header(false)}
        <div className="shrink-0 px-3 py-1 text-[10.5px] text-text-400">Real terminal unavailable ({err.replace(/^unavailable:\s*/, "").slice(0, 120)}). Using the simple command box.</div>
        <div className="min-h-0 flex-1">{fallback}</div>
      </div>
    );
  }
  return (
    <div className="flex h-full flex-col">
      {header(true)}
      {on
        ? <div ref={host} className="min-h-0 flex-1 overflow-hidden px-2 py-1" onClick={() => on.term.focus()} />
        : <div className="flex flex-1 items-center justify-center text-[11.5px] text-text-400">No terminal open. Use + to start one.</div>}
    </div>
  );
}
