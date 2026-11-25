// Everything shown in a conversation: messages, tool calls, command output, the working line.
import { highlight } from "@/lib/markdown";
import { memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { Block, Checkpoint, Diff, Item, Todo } from "@/lib/types";
import { markdownBlocks, type MdBlock } from "@/lib/markdown";
import { openExternal, openPath } from "@/lib/desktop";
import { cn, copyText } from "@/lib/util";
import { currentLive, useLiveInfo, useStore } from "@/lib/store";
import { media, post } from "@/lib/api";
import {
  Ban, Book, Bot, Check, ChevronDown, ChevronRight, Copy, FileText, Globe, ListTodo, Loader, Pencil, Plug, Rewind,
  Search, Terminal, Wrench, Circle, CircleCheck, CircleDot, AlertCircle, FileIcon, Sparkles, Split, Pin, PinOff, Volume,
  Alert, CircleX, Info,
} from "./icons";
import { Tip } from "./ui";
import { Bloom, MarkSlot, Shimmer, WorkMark, type WorkKind } from "./WorkMarks";

// ------------------------------------------------------------------ markdown with copy buttons and safe links
/** What a Markdown element shows: its pieces (markdownBlocks) and the elements each piece became. */
type Drawn = { blocks: MdBlock[]; nodes: ChildNode[][] };

/** Brings `el` up to `text` piece by piece: the pieces that did not change keep their elements as they are, only the
 *  ones from the first change on are rebuilt. The pieces are placed straight in `el`, in order, exactly as one HTML string
 *  would place them, so the .md styles (:first-child, p + p, …) apply as before. */
function drawBlocks(el: HTMLElement, d: Drawn, text: string): void {
  const next = markdownBlocks(text, d.blocks);
  let k = 0;
  while (k < next.length && k < d.blocks.length && next[k] === d.blocks[k]) k++;
  if (k === next.length && k === d.blocks.length) return;
  for (let i = k; i < d.nodes.length; i++) for (const n of d.nodes[i]) n.remove();
  const nodes = d.nodes.slice(0, k);
  const tpl = document.createElement("template");
  for (let i = k; i < next.length; i++) {
    tpl.innerHTML = next[i].html;
    nodes.push(Array.from(tpl.content.childNodes));
    el.append(tpl.content);
  }
  d.blocks = next;
  d.nodes = nodes;
}

/** A reply, drawn piece by piece. While it streams only the piece that is still growing (the last paragraph, list or
 *  code block) is parsed and redrawn, so an update costs as little at the end of a long reply as at its start, and the
 *  text already on screen is never rebuilt: nothing above it re-lays out and a selection in it survives. Redraws come at
 *  most every 40 ms (less often when one is slow, e.g. a long code block), the newest text each time. */
export const Markdown = memo(function Markdown({ text, className, streaming }: { text: string; className?: string; streaming?: boolean }) {
  const box = useRef<HTMLDivElement>(null);
  const drawn = useRef<Drawn>({ blocks: [], nodes: [] });
  const latest = useRef(text);
  latest.current = text;
  const pace = useRef({ timer: 0, at: 0, cost: 0 });
  const redraw = useCallback(() => {
    const p = pace.current;
    p.timer = 0;
    if (!box.current) return;
    const t0 = performance.now();
    drawBlocks(box.current, drawn.current, latest.current);
    p.at = performance.now();
    p.cost = p.at - t0;
  }, []);
  useLayoutEffect(() => {
    const p = pace.current;
    if (!streaming) {                          // finished (or never streamed): the whole text now, before it is painted
      clearTimeout(p.timer);
      redraw();
      return;
    }
    if (p.timer) return;                       // a redraw is already on its way and takes the newest text
    const wait = Math.max(40, p.cost * 4) - (performance.now() - p.at);
    if (wait <= 0) redraw();
    else p.timer = window.setTimeout(redraw, wait);
  }, [text, streaming, redraw]);
  useEffect(() => () => {
    clearTimeout(pace.current.timer);
    pace.current.timer = 0;
  }, []);
  return (
    <div
      ref={box}
      className={cn("md selectable", className)}
      onClick={(e) => {
        const t = e.target as HTMLElement;
        const btn = t.closest("[data-copy]") as HTMLElement | null;
        if (btn) {
          const code = btn.closest(".codeblock")?.querySelector("code")?.textContent || "";
          copyText(code).then(() => {
            btn.textContent = "Copied";
            setTimeout(() => (btn.textContent = "Copy"), 1400);
          });
          return;
        }
        const a = t.closest("a") as HTMLAnchorElement | null;
        if (a && a.getAttribute("href")) {
          e.preventDefault();
          const href = a.getAttribute("href")!;
          if (/^https?:|^mailto:/i.test(href)) openExternal(href);
          else openPath(href).catch(() => {});
        }
      }}
    />
  );
});

// ------------------------------------------------------------------ the list
export function ItemView({ item, checkpoints, onRewind, endOfTurn = true }: {
  item: Item; checkpoints?: Checkpoint[]; onRewind?: (n: number) => void; endOfTurn?: boolean;
}) {
  switch (item.kind) {
    case "user":
      return <UserMessage item={item} checkpoint={checkpoints?.find((c) => c.mark !== null && c.mark === item.mi)} onRewind={onRewind} />;
    case "assistant":
      return <AssistantMessage item={item} actions={endOfTurn} />;
    case "thinking":
      return <Thinking text={item.text} />;
    case "tool":
      return <ToolRow item={item} />;
    case "notice":
      return <Notice item={item} />;
    case "note": {
      if (item.level === "stopped") {
        // a stopped turn as Claude shows it: a quiet grey "Stopped", no card and no red icon
        return (
          <div className="py-0.5 text-[12px] leading-[18px] text-text-500">
            <span className="text-text-400">{item.text}</span>
            {item.detail && <span> · {item.detail}</span>}
          </div>
        );
      }
      const err = item.level === "error";
      return (
        <div className="flex items-start gap-2 py-0.5 text-[12px] leading-[18px] text-text-400">
          <span className="mt-[2px] shrink-0">{err ? <CircleX size={13} className="text-danger" /> : <Info size={13} className="text-text-500" />}</span>
          <span className={cn("min-w-0 flex-1 whitespace-pre-wrap", err && "text-danger")}>{item.text}</span>
        </div>
      );
    }
    case "denied":
      return (
        <div className="flex items-center gap-2 py-0.5 text-[12px] text-text-500">
          <Ban size={14} className="text-danger/80" />
          <span><span className="font-medium text-text-300">{item.label}</span>{item.target ? <span className="font-mono"> {item.target}</span> : null} · {item.reason}</span>
        </div>
      );
    case "turn":
      return null;                                     // "done in 3s" is the terminal's; the window does not show it
    default:
      return null;
  }
}

const PASTE = /\[Pasted text #(\d+) \+(\d+) lines\]/g;

function UserText({ text }: { text: string }) {
  const parts: React.ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(PASTE)) {
    if (m.index! > last) parts.push(text.slice(last, m.index));
    parts.push(
      <span key={m.index} className="mx-0.5 inline-flex items-center gap-1 rounded-md border border-border-300 bg-bg-100 px-1.5 py-[1px] align-middle text-[11.5px] text-text-300">
        <FileText size={12} />Pasted text · {m[2]} lines
      </span>,
    );
    last = m.index! + m[0].length;
  }
  parts.push(text.slice(last));
  return <>{parts}</>;
}

function UserMessage({ item, checkpoint, onRewind }: { item: Extract<Item, { kind: "user" }>; checkpoint?: Checkpoint; onRewind?: (n: number) => void }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const long = item.text.length > 1400 || item.text.split("\n").length > 22;
  const shown = long && !open ? item.text.slice(0, 900).split("\n").slice(0, 14).join("\n") + "…" : item.text;
  const isCmd = /^[/!#] ?/.test(item.text) && !item.text.includes("\n");
  return (
    <div className="group flex flex-col items-end">
      {!!item.images?.length && (
        <div className="mb-1.5 flex max-w-[85%] flex-wrap justify-end gap-1.5">
          {item.images.map((src, i) => (
            <img key={i} src={src} alt="" className="max-h-40 max-w-[220px] rounded-lg border border-border-300 object-cover" />
          ))}
        </div>
      )}
      {!item.images?.length && !!(item.n_images || item.hidden_images) && (
        <div className="mb-1 text-[11px] text-text-500">{item.n_images || item.hidden_images} image{(item.n_images || item.hidden_images) === 1 ? "" : "s"} attached</div>
      )}
      {(item.text || item.command) && (
        <div className={cn("relative max-w-[85%] rounded-[10px] bg-user-bubble pl-[11px] pr-[12px] py-[8px] text-[12.5px] leading-[1.55] text-text-100 whitespace-pre-wrap break-words selectable",
          isCmd && "font-mono text-[12px]", item.failed && "opacity-60")}>
          {item.command && <span className="mr-1.5 rounded-md bg-accent-soft px-1.5 py-[1px] font-mono text-[11.5px] text-accent">{item.command}</span>}
          <UserText text={shown} />
          {long && (
            <button className="mt-1 block text-[11.5px] text-text-400 hover:text-text-100" onClick={() => setOpen(!open)}>
              {open ? "Show less" : "Show more"}
            </button>
          )}
        </div>
      )}
      {!!item.files?.length && (
        <div className="mt-1 flex max-w-[85%] flex-wrap justify-end gap-1">
          {item.files.map((f) => (
            <span key={f} className="inline-flex items-center gap-1 rounded-md border border-border-300 px-1.5 py-0.5 text-[11px] text-text-400" title={f}>
              <FileIcon size={12} />{f.split(/[\\/]/).pop()}
            </span>
          ))}
        </div>
      )}
      <div className="mt-1 flex h-6 items-center gap-1 text-[11px] text-text-500">
        {item.queued && <span className="rounded bg-bg-300 px-1.5">Queued</span>}
        {item.failed && <span className="text-danger">Not sent</span>}
        {item.spoken && <span>spoken</span>}
        <span className="flex text-text-300 opacity-0 transition-opacity group-hover:opacity-100">
          <Tip content={copied ? "Copied" : "Copy"}>
            <button className="flex h-[18px] w-[18px] items-center justify-center rounded-[4px] hover:bg-hover hover:text-text-100" onClick={() => copyText(item.prompt || item.text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1200); })}>
              {copied ? <Check size={11} strokeWidth={1.9} /> : <Copy size={11} strokeWidth={1.9} />}
            </button>
          </Tip>
          {checkpoint && onRewind && (
            <Tip content="Rewind: restore the files and the chat to just before this message">
              <button className="flex h-[18px] w-[18px] items-center justify-center rounded-[4px] hover:bg-hover hover:text-text-100" onClick={() => onRewind(checkpoint.n)}><Rewind size={11} strokeWidth={1.9} /></button>
            </Tip>
          )}
        </span>
      </div>
    </div>
  );
}

/** A reply. The copy row only follows the last reply of a turn, so text between tool calls keeps even spacing. */
function AssistantMessage({ item, actions }: { item: Extract<Item, { kind: "assistant" }>; actions: boolean }) {
  const [, poke] = useState(0);                         // re-render on hover so "5 minutes ago" is current
  return (
    <div className="group relative" onMouseEnter={() => poke(Date.now())}>
      {item.spontaneous && <div className="mb-1 flex items-center gap-1 text-[11px] text-text-500"><Sparkles size={12} />said on her own</div>}
      <Markdown text={item.text} streaming={item.streaming} />
      {!item.streaming && actions && <ReplyActions item={item} />}
    </div>
  );
}

/** "just now", "5 minutes ago", "2 hours ago", "yesterday", "3 days ago" */
export function ago(ms: number): string {
  const s = Math.max(0, (Date.now() - ms) / 1000);
  if (s < 45) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return m <= 1 ? "1 minute ago" : `${m} minutes ago`;
  const h = Math.round(m / 60);
  if (h < 24) return h === 1 ? "1 hour ago" : `${h} hours ago`;
  const d = Math.round(h / 24);
  return d === 1 ? "yesterday" : `${d} days ago`;
}

/** Markdown as plain words, for reading aloud: no code, no symbols, links as their text. */
function spoken(md: string): string {
  return md.replace(/```[\s\S]*?```/g, " ").replace(/`([^`]*)`/g, "$1").replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/^\s{0,3}(#{1,6}|>|[-*+]|\d+\.)\s+/gm, "").replace(/[*_~|]+/g, "").replace(/\s+/g, " ").trim().slice(0, 4000);
}

/** The row under the last reply of a turn, as in Claude Code: copy, fork from here, pin, read aloud, and when. */
function ReplyActions({ item }: { item: Extract<Item, { kind: "assistant" }> }) {
  const live = useLiveInfo();                                        // not the whole session: this row must not redraw on every word
  const rawPins = useStore((s) => s.settings.desktop_pinned);       // the stored value itself (a fresh [] would loop)
  const pins: string[] = Array.isArray(rawPins) ? rawPins : [];
  const pinned = !!live.sid && pins.includes(live.sid);
  const [copied, setCopied] = useState(false);
  const [forking, setForking] = useState(false);
  const btn = "flex h-[18px] w-[18px] items-center justify-center rounded-[4px] text-text-300 transition-colors hover:bg-hover hover:text-text-100 disabled:opacity-40";
  const s = useStore.getState();
  const fork = async () => {
    if (!live.wid || forking) return;
    setForking(true);
    try {
      const r = await post<{ sid: string; cwd: string; title: string }>("/api/session/fork", { wid: live.wid, mi: item.mi ?? null });
      await s.refreshSessions();
      const now = Date.now() / 1000;
      await s.openSession({ id: r.sid, cwd: r.cwd, title: r.title || live.title || "", updated: now, created: now, n: 0, model: "" });
      s.toast("Forked: this is a new session with the conversation up to that reply.", "info");
    } catch (e: any) {
      s.toast(e?.message || "Could not fork the session", "error");
    } finally {
      setForking(false);
    }
  };
  const togglePin = () => {
    const sid = live.sid;
    if (!sid) return;
    s.setSetting("desktop_pinned", pinned ? pins.filter((x) => x !== sid) : [sid, ...pins]);
  };
  const speak = () => {
    if (!live.wid) return;
    post("/api/session/voice_test", { wid: live.wid, text: spoken(item.text) })
      .then(() => s.toast("Reading it aloud…", "info"))
      .catch((e) => s.toast(e?.message || "Could not read it aloud", "error"));
  };
  return (
    <div className="mt-[7px] flex h-[18px] items-center text-text-300 opacity-0 transition-opacity duration-150 focus-within:opacity-100 group-hover:opacity-100">
      <Tip content={copied ? "Copied" : "Copy"}>
        <button aria-label="Copy" className={btn} onClick={() => copyText(item.text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1200); })}>
          {copied ? <Check size={11} strokeWidth={1.9} /> : <Copy size={11} strokeWidth={1.9} />}
        </button>
      </Tip>
      <Tip content="Fork from here: a new session with the conversation up to this reply">
        <button aria-label="Fork from here" className={btn} disabled={!live.wid || forking} onClick={fork}><Split size={11} strokeWidth={1.9} className="rotate-90" /></button>
      </Tip>
      <Tip content={pinned ? "Unpin this session" : "Pin this session to the top of the sidebar"}>
        <button aria-label={pinned ? "Unpin" : "Pin"} className={cn(btn, pinned && "text-text-100")} disabled={!live.sid} onClick={togglePin}>
          {pinned ? <PinOff size={11} strokeWidth={1.9} className="rotate-45" /> : <Pin size={11} strokeWidth={1.9} className="rotate-45" />}
        </button>
      </Tip>
      <Tip content="Read aloud in Emilie's voice">
        <button aria-label="Read aloud" className={btn} disabled={!live.wid} onClick={speak}><Volume size={11} strokeWidth={1.9} /></button>
      </Tip>
      {item.at && <span className="ml-[9px] text-[11px] text-text-400">{ago(item.at)}</span>}
    </div>
  );
}

function Thinking({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="text-[12px] leading-[17px] text-text-400">
      <button className="flex items-center gap-[3px] hover:text-text-200" onClick={() => setOpen(!open)} aria-expanded={open}>
        Thinking<ChevronRight size={12} className={cn("transition-transform duration-150", open && "rotate-90")} />
      </button>
      {open && <div className="mt-1.5 border-l border-border-300 pl-3 whitespace-pre-wrap text-text-300 selectable">{text}</div>}
    </div>
  );
}

// ------------------------------------------------------------------ tool calls
function toolIcon(name: string) {
  if (name.startsWith("mcp__")) return <Plug size={15} />;
  if (["bash", "bash_bg", "bg_output", "bg_stop", "notebook_run"].includes(name)) return <Terminal size={15} />;
  if (["write_file", "edit_file", "notebook_edit", "docx_edit", "docx_create", "xlsx_write"].includes(name)) return <Pencil size={15} />;
  if (["read_file", "docx_read", "xlsx_read", "pptx_read"].includes(name)) return <FileText size={15} />;
  if (["grep", "glob"].includes(name)) return <Search size={15} />;
  if (["web_fetch", "web_search"].includes(name)) return <Globe size={15} />;
  if (["task", "tasks"].includes(name)) return <Bot size={15} />;
  if (["todo_write", "exit_plan_mode"].includes(name)) return <ListTodo size={15} />;
  if (name === "use_skill") return <Book size={15} />;
  return <Wrench size={15} />;
}

type ToolItem = Extract<Item, { kind: "tool" }>;

const RUN = new Set(["bash", "bash_bg", "notebook_run", "bg_output", "bg_stop"]);
const READ = new Set(["read_file", "docx_read", "xlsx_read", "pptx_read"]);
const CREATE = new Set(["write_file", "docx_create"]);
const EDIT = new Set(["edit_file", "notebook_edit", "docx_edit", "xlsx_write"]);
const SEARCH = new Set(["grep", "glob"]);
const AGENT = new Set(["task", "tasks"]);

const baseName = (t: ToolItem) =>
  String(t.input?.path || t.input?.file_path || t.input?.notebook_path || t.target || "").split(/[\\/]/).filter(Boolean).pop() || "a file";
const clip = (s: string, n = 48) => (s.length > n ? s.slice(0, n - 1) + "…" : s);
const host = (u: string) => { try { return new URL(u).host.replace(/^www\./, ""); } catch { return clip(u, 40); } };
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** What kind of step a tool call is, for the one-line summary. */
function category(t: ToolItem): string {
  if (RUN.has(t.name)) return "run";
  if (READ.has(t.name)) return "read";
  if (CREATE.has(t.name)) return "create";
  if (EDIT.has(t.name)) return "edit";
  if (SEARCH.has(t.name)) return "search";
  if (t.name === "web_search") return "websearch";
  if (t.name === "web_fetch") return "webfetch";
  if (AGENT.has(t.name)) return "agent";
  if (t.name === "todo_write") return "todo";
  if (t.name === "use_skill") return "skill";
  if (t.name.startsWith("mcp__")) return "mcp";
  return "other:" + t.label;
}

interface Part { text: string; added: number; removed: number }

/** "ran 3 commands", "read 2 files", "edited worker.py" (+6 −2): how Claude Code sums up a run of tool calls,
 *  in the order the steps first happened. */
function summarize(tools: ToolItem[]): Part[] {
  const groups = new Map<string, ToolItem[]>();
  for (const t of tools) {
    const k = category(t);
    const g = groups.get(k);
    if (g) g.push(t); else groups.set(k, [t]);
  }
  const parts: Part[] = [];
  for (const [k, ts] of groups) {
    const n = ts.length;
    const files = [...new Set(ts.map(baseName))];
    const counts = k === "create" || k === "edit";
    const added = counts ? ts.reduce((a, t) => a + (t.diff?.added || 0), 0) : 0;
    const removed = counts ? ts.reduce((a, t) => a + (t.diff?.removed || 0), 0) : 0;
    let text: string;
    if (k === "run") text = n === 1 ? "ran a command" : `ran ${n} commands`;
    else if (k === "read") text = files.length === 1 ? `read ${files[0]}` : `read ${files.length} files`;
    else if (k === "create") text = files.length === 1 ? `created ${files[0]}` : `created ${files.length} files`;
    else if (k === "edit") text = files.length === 1 ? `edited ${files[0]}` : `edited ${files.length} files`;
    else if (k === "search") text = n === 1 ? `searched for ${clip(String(ts[0].input?.pattern || ts[0].target || "files"), 32)}` : `ran ${n} searches`;
    else if (k === "websearch") text = n === 1 ? "searched the web" : `searched the web ${n} times`;
    else if (k === "webfetch") text = n === 1 ? `fetched ${host(String(ts[0].input?.url || ts[0].target || ""))}` : `fetched ${n} pages`;
    else if (k === "agent") text = n === 1 ? "ran a sub-agent" : `ran ${n} sub-agents`;
    else if (k === "todo") text = "updated the task list";
    else if (k === "skill") text = n === 1 && ts[0].input?.name ? `loaded the ${ts[0].input.name} skill` : `loaded ${n === 1 ? "a skill" : `${n} skills`}`;
    else if (k === "mcp") text = n === 1 ? `used ${ts[0].label}` : `used ${n} connector tools`;
    else text = n === 1 ? `used ${ts[0].label}` : `used ${ts[0].label} ${n} times`;
    parts.push({ text, added, removed });
  }
  return parts;
}

/** The step that is running now, in the present tense. */
function activeText(t: ToolItem): string {
  const k = category(t);
  if (k === "run") return `running ${clip(String(t.input?.command || t.target || "a command"), 56)}`;
  if (k === "read") return `reading ${baseName(t)}`;
  if (k === "create") return `creating ${baseName(t)}`;
  if (k === "edit") return `editing ${baseName(t)}`;
  if (k === "search") return `searching for ${clip(String(t.input?.pattern || t.target || "files"), 40)}`;
  if (k === "websearch") return `searching the web for ${clip(String(t.input?.query || t.target || ""), 40)}`;
  if (k === "webfetch") return `fetching ${host(String(t.input?.url || t.target || ""))}`;
  if (k === "agent") {
    const last = t.children?.[t.children.length - 1];
    return last ? `running a sub-agent · ${last.label} ${clip(last.target, 40)}` : "running a sub-agent";
  }
  if (k === "todo") return "updating the task list";
  if (k === "skill") return "loading a skill";
  if (k === "mcp") return mcpWords(t).now;
  return `using ${t.label}`;
}

interface StepWords { verb: string; subject: string; now: string }

/** An MCP tool call in plain words ("Opened a page localhost", "Ran page script on localhost"). */
function mcpWords(t: ToolItem): StepWords {
  const parts = t.name.split("__");
  const tool = parts.slice(2).join("_").toLowerCase();
  const inp: any = t.input || {};
  const url = String(inp.url || inp.href || inp.page || "");
  const where = url ? host(url) : "";
  if (/navigate|goto|visit|new_page|open_page|browser_open|open_url/.test(tool)) return { verb: "Opened a page", subject: where, now: "opening a page" };
  if (/evaluate|script|run_code|execute|eval/.test(tool)) return { verb: "Ran page script", subject: where ? `on ${where}` : "", now: "running page script" };
  if (/screenshot|snapshot|capture/.test(tool)) return { verb: "Captured the page", subject: where, now: "capturing the page" };
  if (/click|press|type|fill|hover|drag|select|scroll|upload/.test(tool)) return { verb: "Interacted with the page", subject: "", now: "interacting with the page" };
  if (/resolve|library|docs|get-library/.test(tool)) return { verb: "Looked up docs", subject: String(inp.libraryName || inp.context7CompatibleLibraryID || inp.query || ""), now: "looking up docs" };
  if (/memory|remember|entities|nodes|observation/.test(tool)) return { verb: "Used memory", subject: "", now: "using memory" };
  return { verb: `Used ${parts[1] || "a connector"}`, subject: tool.replace(/_/g, " "), now: `using ${t.label}` };
}

/** One tool call as words: a past-tense verb and what it acted on (the subject is shown brighter). */
function stepWords(t: ToolItem): StepWords {
  const k = category(t);
  const file = baseName(t);
  if (k === "mcp") return mcpWords(t);
  if (k === "run") {
    const cmd = String(t.input?.command || t.target || "").trim();
    const first = cmd.split(/\s+/)[0]?.replace(/^["']|["']$/g, "");
    return { verb: first ? `Ran a \u201c${clip(first, 24)}\u201d command` : "Ran a command", subject: "", now: activeText(t) };
  }
  if (k === "read") return { verb: "Read", subject: file, now: activeText(t) };
  if (k === "create") return { verb: "Created", subject: file, now: activeText(t) };
  if (k === "edit") return { verb: "Edited", subject: file, now: activeText(t) };
  if (k === "search") return { verb: "Searched for", subject: clip(String(t.input?.pattern || t.target || "files"), 40), now: activeText(t) };
  if (k === "websearch") return { verb: "Searched the web for", subject: clip(String(t.input?.query || t.target || ""), 40), now: activeText(t) };
  if (k === "webfetch") return { verb: "Fetched", subject: host(String(t.input?.url || t.target || "")), now: activeText(t) };
  if (k === "agent") return { verb: "Ran a sub-agent", subject: clip(String(t.input?.description || t.target || ""), 40), now: activeText(t) };
  if (k === "todo") return { verb: "Updated the task list", subject: "", now: activeText(t) };
  if (k === "skill") return { verb: "Loaded the", subject: `${t.input?.name || "a"} skill`, now: activeText(t) };
  return { verb: `Used ${t.label}`, subject: clip(t.target || "", 40), now: activeText(t) };
}

/** One step inside an opened group: a row in a card, with its own chevron that opens what it did (output, diff, the
 *  steps a sub-agent took, thumbnails). Steps inside steps: a row opens into more rows. */
function StepRow({ t, first }: { t: ToolItem; first: boolean }) {
  const d = t.diff;
  const autoOpen = !!d && d.added + d.removed > 0 && d.added + d.removed <= 24 && !d.approx;
  const [open, setOpen] = useState<boolean | null>(null);
  const isOpen = open ?? autoOpen;
  const running = t.status === "running";
  const bad = t.status === "error" || t.status === "denied";
  const w = stepWords(t);
  const isAgent = category(t) === "agent";
  const steps = (t.children || []).filter((c) => !/^sub-agent/i.test(c.label || ""));     // its first line only repeats the task
  return (
    <div className={cn(!first && "border-t border-border-200")}>
      <button onClick={() => setOpen(!isOpen)} aria-expanded={isOpen}
        className="flex w-full min-w-0 items-center gap-2 px-3 py-[7px] text-left text-[12px] leading-[17px] text-text-300 hover:bg-hover/50">
        <span className={cn("min-w-0 flex-1 truncate", running && "shimmer-text")}>
          {running ? cap(w.now) : w.verb}{!running && w.subject && <span className="ml-1.5 text-text-100">{w.subject}</span>}
        </span>
        {d && (d.added > 0 || d.removed > 0) && <span className="shrink-0 font-mono text-[11px]"><span className="text-ok">+{d.added}</span> <span className="text-danger">{"\u2212"}{d.removed}</span></span>}
        {bad && <span className="shrink-0 text-[11px] text-danger">{t.status === "denied" ? "denied" : "failed"}</span>}
        {t.status === "interrupted" && <span className="shrink-0 text-[11px] text-text-500">interrupted</span>}
        <ChevronRight size={12} className={cn("shrink-0 text-text-500 transition-transform duration-150", isOpen && "rotate-90")} />
      </button>
      {isOpen && isAgent && (
        <div className="border-t border-border-200 bg-bg-100/30">
          {steps.map((c, i) => <ChildRow key={i} c={c} first={i === 0} />)}
          <DetailRow title={running ? "Working\u2026" : "Brief and report"} first={!steps.length}><ToolDetails item={t} flat /></DetailRow>
        </div>
      )}
      {isOpen && !isAgent && <div className="border-t border-border-200"><ToolDetails item={t} flat /></div>}
    </div>
  );
}

/** What a sub-agent's step was, in words (its steps come as a label and a target, e.g. Glob with a pattern, Read with a path). */
export function childWords(c: { label?: string; target?: string }): { verb: string; subject: string; full: string } {
  const label = String(c.label || "").trim();
  const target = String(c.target || "").trim();
  const file = target.split(/[\\/]/).filter(Boolean).pop() || target;
  const k = label.toLowerCase();
  if (k === "glob" || k === "grep" || k === "search") return { verb: "Searched for", subject: clip(target, 44), full: target };
  if (k === "read") return { verb: "Read", subject: file, full: target };
  if (k === "write") return { verb: "Created", subject: file, full: target };
  if (k === "update" || k === "edit") return { verb: "Edited", subject: file, full: target };
  if (k === "bash" || k === "bash(bg)") { const f = target.split(/\s+/)[0]; return { verb: f ? `Ran a \u201c${clip(f, 24)}\u201d command` : "Ran a command", subject: "", full: target }; }
  if (k === "fetch") return { verb: "Fetched", subject: host(target), full: target };
  if (k === "websearch") return { verb: "Searched the web for", subject: clip(target, 44), full: target };
  return { verb: label || "Step", subject: clip(target, 44), full: target };
}

/** A step of a sub-agent: one row; its chevron opens the full text of what it did when that does not fit on the row. */
function ChildRow({ c, first }: { c: { label?: string; target?: string }; first: boolean }) {
  const w = childWords(c);
  const more = w.full.length > 44 || w.full !== w.subject;
  const [open, setOpen] = useState(false);
  return (
    <div className={cn(!first && "border-t border-border-200")}>
      <button onClick={() => more && setOpen(!open)} aria-expanded={open}
        className={cn("flex w-full min-w-0 items-center gap-2 py-[6px] pl-6 pr-3 text-left text-[12px] leading-[17px] text-text-300", more && "hover:bg-hover/50")}>
        <span className="min-w-0 flex-1 truncate">{w.verb}{w.subject && <span className="ml-1.5 text-text-100">{w.subject}</span>}</span>
        {more && <ChevronRight size={12} className={cn("shrink-0 text-text-500 transition-transform duration-150", open && "rotate-90")} />}
      </button>
      {open && <div className="border-t border-border-200 px-6 py-2 font-mono text-[11.5px] leading-[16px] text-text-400 whitespace-pre-wrap break-all selectable">{w.full}</div>}
    </div>
  );
}

/** A plain row that opens into something (the sub-agent's brief and report). */
function DetailRow({ title, first, children }: { title: string; first: boolean; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={cn(!first && "border-t border-border-200")}>
      <button onClick={() => setOpen(!open)} aria-expanded={open}
        className="flex w-full items-center gap-2 py-[6px] pl-6 pr-3 text-left text-[12px] leading-[17px] text-text-400 hover:bg-hover/50">
        <span className="flex-1">{title}</span>
        <ChevronRight size={12} className={cn("shrink-0 text-text-500 transition-transform duration-150", open && "rotate-90")} />
      </button>
      {open && <div className="border-t border-border-200">{children}</div>}
    </div>
  );
}

function ThoughtRow({ text, first }: { text: string; first: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={cn(!first && "border-t border-border-200")}>
      <button onClick={() => setOpen(!open)} aria-expanded={open}
        className="flex w-full items-center gap-2 px-3 py-[7px] text-left text-[12px] leading-[17px] text-text-400 hover:bg-hover/50">
        <span className="flex-1">Thought</span>
        <ChevronRight size={12} className={cn("shrink-0 text-text-500 transition-transform duration-150", open && "rotate-90")} />
      </button>
      {open && <div className="border-t border-border-200 px-3 py-2 text-[12px] leading-[17px] text-text-300 whitespace-pre-wrap selectable">{text}</div>}
    </div>
  );
}

function Stat({ added, removed }: { added: number; removed: number }) {
  if (!added && !removed) return null;
  return <>{added > 0 && <span className="ml-1 text-ok">+{added}</span>}{removed > 0 && <span className="ml-1 text-danger">−{removed}</span>}</>;
}

/** A run of tool calls (and the thinking between them) shown as one quiet line, like Claude Code:
 *  "Ran 3 commands, edited worker.py +6 −2 ›". Click it to see each call, its output and its diff. */
/** A small picture from a tool call (a screenshot, an image it opened). Click: open it full size in the viewer. */
function Thumb({ path, big }: { path: string; big?: boolean }) {
  const [failed, setFailed] = useState(false);
  if (failed) return null;
  const name = path.split(/[\\/]/).pop() || path;
  return (
    <Tip content={`${name} · click to open`}>
      <button onClick={() => useStore.getState().openFile(path)} aria-label={`Open ${name}`}
        className={cn("block overflow-hidden rounded-[5px] border border-border-300 bg-bg-200 transition-opacity hover:opacity-85",
          big ? "max-w-full" : "h-[30px] w-[48px]")}>
        <img src={media("/media/file", { path })} alt={name} draggable={false} onError={() => setFailed(true)}
          className={big ? "block max-h-[320px] max-w-full object-contain" : "h-full w-full object-cover object-top"} />
      </button>
    </Tip>
  );
}

/** The steps of a run of tool calls (and the thinking between them) as one card. */
export function StepCard({ members }: { members: Item[] }) {
  return (
    <div className="mt-1.5 overflow-hidden rounded-[9px] border border-border-300 bg-bg-200/40">
      {members.map((m, i) => (m.kind === "tool" ? <StepRow key={m.id} t={m} first={i === 0} /> : m.kind === "thinking" ? <ThoughtRow key={m.id} text={m.text} first={i === 0} /> : null))}
    </div>
  );
}

export function ToolGroup({ members }: { members: Item[] }) {
  const [open, setOpen] = useState(false);
  const tools = members.filter((m): m is ToolItem => m.kind === "tool");
  const running = tools.find((t) => t.status === "running");
  const done = tools.filter((t) => t.status !== "running");
  const parts = summarize(done);
  const failed = done.filter((t) => t.status === "error").length;
  const stopped = done.some((t) => t.status === "interrupted");
  const line = parts.map((p, i) => (
    <span key={i}>{i ? ", " : ""}{i === 0 ? cap(p.text) : p.text}<Stat added={p.added} removed={p.removed} /></span>
  ));
  const pics = [...new Set(tools.flatMap((t) => t.images || []))].slice(-3);
  return (
    <div className="text-[12px] leading-[17px]">
      <div className="flex items-center gap-2">
        <button onClick={() => setOpen(!open)} aria-expanded={open}
          className="flex min-w-0 max-w-full items-center gap-[3px] text-left text-text-400 hover:text-text-200">
          <span className="min-w-0 truncate">
            {running ? (
              <span className="shimmer-text">{line.length ? <>{line}, {activeText(running)}</> : cap(activeText(running))}…</span>
            ) : line}
            {failed > 0 && <span className="text-danger"> · {failed} failed</span>}
            {stopped && <span> · interrupted</span>}
          </span>
          {running && <Elapsed since={(running as any).at ?? Date.now()} />}
          <ChevronRight size={12} className={cn("shrink-0 transition-transform duration-150", open && "rotate-90")} />
        </button>
        {/* like Claude Code's "captured page" thumbnail: the picture is right there; click to see it full size */}
        {pics.length > 0 && (
          <div className="ml-auto flex shrink-0 gap-1">
            {pics.map((p) => <Thumb key={p} path={p} />)}
          </div>
        )}
      </div>
      {open && <StepCard members={members} />}
    </div>
  );
}

export type Row = { key: string; item: Item } | { key: string; group: Item[] } | { key: string; lines: Item[] };

/** The items a row holds, whatever its kind. */
export function rowItems(r: Row): Item[] {
  return "group" in r ? r.group : "lines" in r ? r.lines : [r.item];
}

const isLine = (it: Item | undefined) => !!it && it.kind === "notice" && it.level === "line";

/** Turns the conversation into what is drawn: tool calls next to each other (and the thinking between them)
 *  become one ToolGroup line; everything else stays its own row. */
export function groupItems(all: Item[]): Row[] {
  const out: Row[] = [];
  // an empty reply (the model said nothing between two tool calls) draws nothing, so it must not split the run either
  const items = all.filter((it) => !(it.kind === "assistant" && !it.streaming && !String(it.text || "").trim()));
  const groupable = (it: Item | undefined) => !!it && it.kind === "tool" && it.name !== "exit_plan_mode";
  // A row is known by the id of its first item, not by where it is: a message that moves (a queued one whose turn
  // starts) or goes away must not give every row after it a new key, which would rebuild all of them, replies and all.
  // An id met again (it should not happen) gets a count.
  const seen = new Map<string, number>();
  const keyOf = (it: Item) => {
    const n = seen.get(it.id) || 0;
    seen.set(it.id, n + 1);
    return n ? `${it.id}#${n}` : it.id;
  };
  items.forEach((it, i) => {
    let next = i + 1;
    while (it.kind === "thinking" && items[next]?.kind === "thinking") next++;
    const joins = groupable(it) || (it.kind === "thinking" && groupable(items[next]));
    const last = out[out.length - 1];
    if (isLine(it)) {                       // what one command printed, line by line: one card (NoticeLines)
      if (last && "lines" in last) last.lines.push(it);
      else out.push({ key: keyOf(it), lines: [it] });
      return;
    }
    if (joins && last && "group" in last) last.group.push(it);
    else if (joins) out.push({ key: keyOf(it), group: [it] });
    else out.push({ key: keyOf(it), item: it });
  });
  return out;
}

function ToolRow({ item }: { item: Extract<Item, { kind: "tool" }> }) {
  const d = item.diff;
  const autoOpen = !!d && d.added + d.removed > 0 && d.added + d.removed <= 24 && !d.approx;
  const [open, setOpen] = useState<boolean | null>(null);
  const isOpen = open ?? autoOpen;
  const running = item.status === "running";
  const bad = item.status === "error" || item.status === "denied" || item.status === "interrupted";
  const summary = item.summary?.[0] || "";
  return (
    <div className="text-[12px]">
      <button onClick={() => setOpen(!isOpen)}
        className="group flex w-full min-w-0 items-center gap-2 rounded-lg py-1 pr-1 text-left text-text-300 hover:text-text-100">
        <span className={cn("flex h-5 w-5 shrink-0 items-center justify-center", running ? "text-accent" : bad ? "text-danger" : "text-text-400")}>
          {running ? <Loader size={15} className="animate-spin" /> : toolIcon(item.name)}
        </span>
        <span className="shrink-0 font-medium text-text-200">{item.label}</span>
        <span className="min-w-0 flex-1 truncate font-mono text-[11.5px] text-text-400" title={item.target}>{item.target}</span>
        {d && (d.added > 0 || d.removed > 0) && (
          <span className="shrink-0 font-mono text-[11px]">
            <span className="text-ok">+{d.added}</span> <span className="text-danger">−{d.removed}</span>
          </span>
        )}
        {!d && summary && !running && (
          <span className={cn("max-w-[38%] shrink truncate text-[11.5px]", bad ? "text-danger" : "text-text-500")}>{summary}</span>
        )}
        {item.status === "interrupted" && <span className="text-[11px] text-text-500">interrupted</span>}
        <span className="shrink-0 text-text-500 opacity-0 group-hover:opacity-100">{isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}</span>
      </button>
      {!!item.children?.length && (
        <div className="ml-[9px] border-l-[1.5px] border-border-300 pl-4">
          {item.children.slice(isOpen ? 0 : -4).map((c, i) => (
            <div key={i} className="truncate py-0.5 text-[11.5px] text-text-500">
              {c.label && <span className="text-text-400">{c.label} </span>}<span className="font-mono">{c.target}</span>
            </div>
          ))}
        </div>
      )}
      {isOpen && <ToolDetails item={item} />}
    </div>
  );
}

function ToolDetails({ item, flat }: { item: Extract<Item, { kind: "tool" }>; flat?: boolean }) {
  if (item.images?.length) {
    return (
      <>
        <div className={cn("flex flex-wrap gap-2", flat ? "p-3" : "mb-1 ml-6 mt-1")}>{item.images.map((p) => <Thumb key={p} path={p} big />)}</div>
        <ToolOutput item={item} flat={flat} />
      </>
    );
  }
  return <ToolOutput item={item} flat={flat} />;
}

function ToolOutput({ item, flat }: { item: Extract<Item, { kind: "tool" }>; flat?: boolean }) {
  const n = item.name;
  const box = flat ? "overflow-hidden" : "mt-1 mb-2 ml-6 overflow-hidden rounded-lg border border-border-300 bg-bg-200";
  const file = String(item.input?.path || item.input?.file_path || "");
  if (item.diff && item.diff.text) return <div className={box}>{file && <FileBar path={file} />}<DiffView diff={item.diff} file={file || undefined} /></div>;
  if (n === "todo_write" && Array.isArray(item.input?.todos)) return <div className={cn(box, "p-3")}><TodoList todos={item.input.todos} /></div>;
  if (n === "exit_plan_mode") return <div className={cn(box, "p-4")}><Markdown text={String(item.input?.plan || "")} /></div>;
  const out = String(item.output || "");
  if (n === "bash" || n === "bash_bg" || n === "notebook_run") {
    const m = out.match(/^exit=(-?\d+)\n?/);
    const body = m ? out.slice(m[0].length) : out;
    const cmd = String(item.input?.command || item.target || "");
    return (
      <div className={box}>
        {/* the command in its own box (it scrolls when long), what it printed under it */}
        <div className="relative m-2 rounded-[8px] border border-border-300 bg-bg-100">
          <pre className="max-h-[220px] overflow-auto px-3 py-2 pr-14 font-mono text-[11.5px] leading-[1.5] text-text-200 whitespace-pre-wrap break-words selectable">
            <span className="select-none text-text-500">$ </span><span dangerouslySetInnerHTML={{ __html: commandHtml(cmd) }} />
          </pre>
          {m && <span className={cn("absolute right-3 top-2 text-[10.5px]", m[1] === "0" ? "text-text-500" : "text-danger")}>exit {m[1]}</span>}
        </div>
        <Pre text={body || "(no output)"} />
      </div>
    );
  }
  if (n === "task" || n === "tasks") {
    return (
      <div className={cn(box, "p-4")}>
        {item.input?.prompt && <div className="mb-2 text-[11.5px] text-text-400 whitespace-pre-wrap selectable">{String(item.input.prompt).slice(0, 2000)}</div>}
        {out ? <Markdown text={out} className="text-[12.5px]" /> : <div className="text-[12px] text-text-500">Working…</div>}
      </div>
    );
  }
  const input = item.input && Object.keys(item.input).length ? JSON.stringify(item.input, null, 2) : "";
  return (
    <div className={box}>
      {input && !["read_file", "glob", "grep", "web_search", "web_fetch"].includes(n) && (
        <div className="border-b border-border-200"><Pre text={input} small /></div>
      )}
      {n === "read_file" && file && <FileBar path={file} />}
      {out && (n === "read_file" || n === "grep")
        ? <CodeOutput text={out} path={String(item.input?.path || item.target || "")} grep={n === "grep"} />
        : <Pre text={out || (item.status === "running" ? "Running…" : "(no output)")} />}
    </div>
  );
}

function Pre({ text, small }: { text: string; small?: boolean }) {
  return (
    <pre className={cn("max-h-[360px] overflow-auto px-3 py-2.5 font-mono leading-[1.5] text-text-200 whitespace-pre-wrap break-words selectable",
      small ? "text-[10.5px] text-text-400" : "text-[11.5px]")}>{text}</pre>
  );
}

/** A command, coloured. A heredoc (python - <<'E' … E, cat > a.tsx <<EOF) has its body coloured in its own language. */
function commandHtml(cmd: string): string {
  const m = cmd.match(/^([^\n]*?<<-?\s*(['"]?)([A-Za-z_]\w*)\2[^\n]*)\n([\s\S]*?)\n(\3[ \t]*)(?=\n|$)([\s\S]*)$/);
  if (!m) return highlight(cmd, "bash");
  const [, head, , , body, end, rest] = m;
  const redirect = head.match(/>\s*["']?[^\s"'<>]+\.([A-Za-z0-9]+)/);
  const lang = redirect ? redirect[1].toLowerCase() : /\b(python3?|py)\b/.test(head) ? "py" : /\bnode\b/.test(head) ? "js" : "";
  return [highlight(head, "bash"), highlight(body, lang || "txt"), highlight(end, "bash") + (rest ? commandHtml(rest.replace(/^\n/, "")).replace(/^/, "\n") : "")].join("\n");
}

/** The file a tool read or wrote, above its code: the path (relative to the project) opens it in the Files panel. */
function FileBar({ path }: { path: string }) {
  const cwd = useStore((st) => currentLive(st)?.cwd || "");
  const [copied, setCopied] = useState(false);
  const abs = /^([a-zA-Z]:[\\/]|[\\/])/.test(path) || !cwd ? path : `${cwd.replace(/[\\/]+$/, "")}\\${path.replace(/\//g, "\\")}`;
  const root = cwd.replace(/[\\/]+$/, "").toLowerCase().replace(/\//g, "\\");
  const norm = abs.replace(/\//g, "\\");
  const shown = root && norm.toLowerCase().startsWith(root + "\\") ? norm.slice(root.length + 1) : norm;
  const copy = () => { navigator.clipboard?.writeText(abs).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1400); }).catch(() => {}); };
  return (
    <div className="flex items-center gap-2 border-b border-border-200 px-3 py-1.5 text-[11.5px]">
      <button onClick={() => useStore.getState().openFile(abs)} title={`Open ${abs} in the Files panel`}
        className="min-w-0 flex-1 truncate text-left text-text-200 underline-offset-2 hover:text-text-000 hover:underline">{shown}</button>
      <button onClick={copy} title="Copy the path" aria-label="Copy the path"
        className="shrink-0 text-[10.5px] text-text-400 hover:text-text-100">{copied ? "Copied" : "Copy path"}</button>
    </div>
  );
}

/** Code a tool returned, coloured by the code theme: read_file ("  12<TAB>line") and grep ("path:12: line") keep their
 *  numbers / paths dim, the code beside them is highlighted by the file's extension. Other lines stay plain. */
function CodeOutput({ text, path, grep }: { text: string; path?: string; grep?: boolean }) {
  const rows = useMemo(() => {
    const extOf = (f: string) => (f.split(/[\\/]/).pop() || "").split(".").pop()?.toLowerCase() || "";
    return text.split("\n").map((line) => {
      const g = grep ? line.match(/^(.+?:\d+: )(.*)$/) : null;
      if (g) return { head: g[1], html: highlight(g[2], extOf(g[1].replace(/:\d+: $/, ""))), plain: "" };
      const m = !grep ? line.match(/^(\s*\d+)\t(.*)$/) : null;
      if (m) return { head: m[1] + "  ", html: highlight(m[2], extOf(path || "")), plain: "" };
      return { head: "", html: "", plain: line };
    });
  }, [text, path, grep]);
  return (
    <pre className="max-h-[360px] overflow-auto px-3 py-2.5 font-mono text-[11.5px] leading-[1.5] text-text-200 whitespace-pre-wrap break-words selectable">
      {rows.map((l, i) => (
        <div key={i} className={l.head && !grep ? "pl-[7ch] -indent-[7ch]" : undefined}>
          {l.head && <span className="text-text-500">{l.head}</span>}
          {l.html ? <span dangerouslySetInnerHTML={{ __html: l.html }} /> : l.plain || (l.head ? "" : "\u00a0")}
        </div>
      ))}
    </pre>
  );
}

/** How the Changes pane shows a file's diff (its "…" menu): long lines wrap or scroll, one column or side by side,
 *  line numbers, and whether lines that only differ in whitespace count as changes. */
export interface DiffViewOpts { wrap: boolean; split: boolean; nums: boolean; ws: boolean }

type DRow = { k: "hunk" | "ctx" | "add" | "del"; t: string; o: number | ""; n: number | "" };

/** A removed line followed by an added one that only differs in spaces is no change: it becomes a context line. */
function hideWhitespace(lines: string[]): string[] {
  const sq = (s: string) => s.replace(/\s+/g, " ").trim();
  const out: string[] = [];
  let i = 0;
  while (i < lines.length) {
    if (lines[i].startsWith("-") && !lines[i].startsWith("---")) {
      let j = i;
      while (j < lines.length && lines[j].startsWith("-") && !lines[j].startsWith("---")) j++;
      let k = j;
      while (k < lines.length && lines[k].startsWith("+") && !lines[k].startsWith("+++")) k++;
      const dels = lines.slice(i, j), adds = lines.slice(j, k);
      if (dels.length === adds.length && dels.length && dels.every((d, x) => sq(d.slice(1)) === sq(adds[x].slice(1)))) {
        adds.forEach((a) => out.push(" " + a.slice(1)));
      } else out.push(...dels, ...adds);
      i = k;
    } else { out.push(lines[i]); i++; }
  }
  return out;
}

function toRows(lines: string[]): DRow[] {
  let oldNo = 0, newNo = 0;
  const rows: DRow[] = [];
  for (const l of lines) {
    if (l.startsWith("---") || l.startsWith("+++")) continue;
    if (l.startsWith("@@")) {
      const m = l.match(/^@@ -(\d+)(?:,\d+)? \+(\d+)/);
      if (m) { oldNo = +m[1]; newNo = +m[2]; }
      rows.push({ k: "hunk", t: l, o: "", n: "" });
    } else if (l.startsWith("+")) rows.push({ k: "add", t: l.slice(1), o: "", n: newNo++ });
    else if (l.startsWith("-")) rows.push({ k: "del", t: l.slice(1), o: oldNo++, n: "" });
    else rows.push({ k: "ctx", t: l.slice(1) || " ", o: oldNo++, n: newNo++ });
  }
  return rows;
}

export const DiffView = memo(function DiffView({ diff, max = 400, file, flat, view }: { diff: Diff; max?: number; file?: string; flat?: boolean; view?: DiffViewOpts }) {
  // flat: the Changes pane: line numbers, no scrollbar of its own (the pane scrolls); view: how it is laid out
  const [all, setAll] = useState(false);
  const ext = ((diff.path || file || "").split(".").pop() || "").toLowerCase();       // the colours follow the file type
  const wrap = view ? view.wrap : true, split = !!(flat && view?.split), nums = view ? view.nums : true, ws = !!view?.ws;
  const lines = useMemo(() => {
    const l = diff.text.split("\n");
    return flat && ws ? hideWhitespace(l) : l;
  }, [diff.text, flat, ws]);
  const shown = useMemo(() => (all ? lines : lines.slice(0, max)), [lines, all, max]);
  const code = (t: string) => <span className="tx" dangerouslySetInnerHTML={{ __html: highlight(t, ext) }} />;
  // The highlighted rows are built once per text, not on every re-render (resizing a pane re-renders its parents).
  const rows = useMemo(() => {
    const rs = toRows(shown);
    if (!split) {
      return rs.map((r, i) => (
        <div key={i} className={cn("ln pr-3", r.k === "ctx" ? "" : r.k)}>
          {flat && nums && <span className="no">{r.k === "hunk" ? "" : r.k === "del" ? r.o : r.n}</span>}
          <span className="mk">{r.k === "add" ? "+" : r.k === "del" ? "−" : ""}</span>
          {r.k === "hunk" ? <span className="tx">{r.t}</span> : code(r.t)}
        </div>
      ));
    }
    // side by side: a run of removed lines sits beside the run of added lines that replaced them
    const side = (r: DRow | null, which: "o" | "n") => (
      <div className={cn("ln pr-2", r ? (r.k === "ctx" ? "" : r.k) : "empty")}>
        {nums && <span className="no">{r ? r[which] : ""}</span>}
        <span className="mk">{r?.k === "add" ? "+" : r?.k === "del" ? "−" : ""}</span>
        {r ? code(r.t) : <span className="tx" />}
      </div>
    );
    const out: React.ReactNode[] = [];
    for (let i = 0; i < rs.length;) {
      const r = rs[i];
      if (r.k === "hunk") { out.push(<div key={i} className="ln hunk"><span className="mk" /><span className="tx">{r.t}</span></div>); i++; continue; }
      if (r.k === "ctx") { out.push(<div key={i} className="sp">{side(r, "o")}{side(r, "n")}</div>); i++; continue; }
      const dels: DRow[] = [], adds: DRow[] = [];
      let j = i;
      while (j < rs.length && rs[j].k === "del") dels.push(rs[j++]);
      while (j < rs.length && rs[j].k === "add") adds.push(rs[j++]);
      for (let x = 0; x < Math.max(dels.length, adds.length); x++) {
        out.push(<div key={`${i}-${x}`} className="sp">{side(dels[x] || null, "o")}{side(adds[x] || null, "n")}</div>);
      }
      i = j;
    }
    return out;
  }, [shown, split, nums, flat, ext]);   // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className={cn("diff py-1 selectable", flat ? (wrap ? "wrap" : "overflow-x-auto") : "wrap max-h-[480px] overflow-y-auto overflow-x-hidden", split && "split")} style={{ background: "var(--code-bg-custom, transparent)" }}>
      {diff.path && (
        <div className="flex items-center gap-2 px-3 pb-1 pt-1 font-sans text-[11px] text-text-400">
          <FileText size={13} />{diff.path}{diff.new_file && <span className="text-ok">new file</span>}{diff.approx && <span className="text-text-500">(as requested)</span>}
        </div>
      )}
      {flat && !wrap ? <div className="inline-block min-w-full">{rows}</div> : rows}
      {lines.length > max && !all && (
        <button className="mx-3 my-1 font-sans text-[11px] text-text-400 hover:text-text-100" onClick={() => setAll(true)}>
          Show {lines.length - max} more lines
        </button>
      )}
    </div>
  );
});

export function TodoList({ todos }: { todos: Todo[] }) {
  return (
    <ul className="flex flex-col gap-1">
      {todos.map((t, i) => (
        <li key={i} className={cn("flex items-start gap-2 text-[12px]", t.status === "completed" ? "text-text-500" : "text-text-200")}>
          <span className="mt-[2px] shrink-0">
            {t.status === "completed" ? <CircleCheck size={15} className="text-ok" /> : t.status === "in_progress" ? <CircleDot size={15} className="text-accent" /> : <Circle size={15} className="text-text-500" />}
          </span>
          <span className={cn(t.status === "completed" && "line-through decoration-text-500/60", t.status === "in_progress" && "font-medium text-text-100")}>
            {t.status === "in_progress" && t.activeForm ? t.activeForm : t.content}
          </span>
        </li>
      ))}
    </ul>
  );
}

// ------------------------------------------------------------------ what commands print
/** What a printed line is, read from its colours (the terminal palette, emilie/theme.py): done, failed, a warning or
 *  plain information. A line that starts with its own mark (✓ ✗ ● ⎿ …) keeps it instead of getting an icon, and so
 *  does an indented line: a row of a list the command printed ("  ● en  English", "    id  Bahasa Indonesia"). */
type LineKind = "ok" | "error" | "warn" | "info" | "own";
function lineKind(it: Extract<Item, { kind: "notice" }>): LineKind {
  const t = (it.text || "").trimStart();
  const html = it.blocks.map((b) => ("html" in b ? b.html : "")).join("");
  if (/^[✓✗–●!⎿•·]/.test(t) || /^[ \t]/.test(html.replace(/<[^>]+>/g, ""))) return "own";
  if (/#d9534f/i.test(html) || /^(error|unknown command|usage:)/i.test(t)) return "error";
  if (/#d99a2b/i.test(html)) return "warn";
  if (/#3fa66b/i.test(html)) return "ok";
  return "info";
}
const LINE_ICON: Record<Exclude<LineKind, "own">, React.ReactNode> = {
  ok: <CircleCheck size={13} className="text-ok" />,
  error: <CircleX size={13} className="text-danger" />,
  warn: <Alert size={13} className="text-warn" />,
  info: <Info size={13} className="text-text-500" />,
};

/** What one command printed, line by line, as one quiet card (the terminal prints coloured lines): a status icon on
 *  each line, the text in the secondary colour, hairlines between lines. */
export function NoticeLines({ items }: { items: Item[] }) {
  return (
    <div className="notice-lines overflow-hidden rounded-[9px] border border-border-300 bg-bg-200/60 text-[12px] leading-[18px]">
      {items.map((it, i) => {
        if (it.kind !== "notice") return null;
        const k = lineKind(it);
        return (
          <div key={it.id} className={cn("flex items-start gap-2.5 px-3 py-[6px]", i > 0 && "border-t border-border-200")}>
            {k !== "own" && <span className="mt-[2.5px] shrink-0">{LINE_ICON[k]}</span>}
            <div className="min-w-0 flex-1 text-text-300"><Blocks blocks={it.blocks} /></div>
          </div>
        );
      })}
    </div>
  );
}

function Notice({ item }: { item: Extract<Item, { kind: "notice" }> }) {
  if (item.level === "line") return <NoticeLines items={[item]} />;
  return <div className="text-[12px]"><Blocks blocks={item.blocks} top /></div>;
}

/** top: the blocks of a printed panel (not inside another one); a bare table then gets the same card as a panel. */
export function Blocks({ blocks, top }: { blocks: Block[]; top?: boolean }) {
  return (
    <div className="blocks flex flex-col gap-2 selectable">
      {blocks.map((b, i) => {
        switch (b.t) {
          case "text":
            return <div key={i} className="whitespace-pre-wrap break-words" dangerouslySetInnerHTML={{ __html: b.html }} />;
          case "md":
            return <Markdown key={i} text={b.md} className="text-[13px]" />;
          case "pre":
            return <pre key={i} className="overflow-x-auto" dangerouslySetInnerHTML={{ __html: b.html }} />;
          case "rule":
            return (
              <div key={i} className="flex items-center gap-3 py-1 text-[11px] text-text-500">
                <div className="h-px flex-1 bg-border-300" />
                {b.title && <span dangerouslySetInnerHTML={{ __html: b.title }} />}
                <div className="h-px flex-1 bg-border-300" />
              </div>
            );
          case "table": {
            const table = (
              <div key={i} className="overflow-x-auto">
                {b.title && <div className="np-title mb-1.5 text-[12px] font-medium text-text-100" dangerouslySetInnerHTML={{ __html: b.title }} />}
                <table>
                  {b.head && <thead><tr>{b.head.map((h, j) => <th key={j} dangerouslySetInnerHTML={{ __html: h }} />)}</tr></thead>}
                  <tbody>{b.rows.map((r, j) => <tr key={j}>{r.map((c, k) => <td key={k} dangerouslySetInnerHTML={{ __html: c }} />)}</tr>)}</tbody>
                </table>
              </div>
            );
            return top ? <div key={i} className="np-card rounded-[9px] border border-border-300 bg-bg-200/60 px-3.5 py-2.5">{table}</div> : table;
          }
          case "panel":
            // one neutral card for every panel: a title bar, the body and a footer note, like the app's own cards
            return (
              <div key={i} className="np-card overflow-hidden rounded-[9px] border border-border-300 bg-bg-200/60">
                {b.title && <div className="np-title border-b border-border-200 px-3.5 py-2 text-[12px] font-medium text-text-100" dangerouslySetInnerHTML={{ __html: b.title }} />}
                <div className="px-3.5 py-2.5"><Blocks blocks={b.body} /></div>
                {b.subtitle && <div className="np-sub border-t border-border-200 px-3.5 py-1.5 text-[11px] text-text-400" dangerouslySetInnerHTML={{ __html: b.subtitle }} />}
              </div>
            );
          default:
            return null;
        }
      })}
    </div>
  );
}

// ------------------------------------------------------------------ "Cooking…" line while she works
// The marks themselves (the flower, the pencil, the globe, the wrench, …) and their motion: WorkMarks.tsx.

/** The mark for a tool that is RUNNING now (not only while it is being drafted). */
export function toolKind(name: string): WorkKind {
  if (["write_file", "edit_file", "notebook_edit", "docx_edit", "docx_create", "xlsx_write"].includes(name)) return "write";
  if (["bash", "bash_bg", "bg_output", "bg_stop", "notebook_run"].includes(name)) return "command";
  if (["todo_write", "exit_plan_mode"].includes(name)) return "plan";
  if (["task", "tasks"].includes(name)) return "helper";
  if (["read_file", "docx_read", "xlsx_read", "pptx_read", "use_skill"].includes(name)) return "read";
  if (["grep", "glob"].includes(name)) return "search";
  if (["web_fetch", "web_search"].includes(name)) return "web";
  return "tool";
}
/** What she is drafting right now ("Writing index.html · 214 lines…") also picks the mark for that kind of work. */
const DRAFT_KINDS: [RegExp, WorkKind][] = [
  [/^connecting tools/i, "connect"],
  [/^Searching the web/, "web"], [/^Fetching /, "web"], [/^Searching /, "search"], [/^Reading /, "read"],
  [/^Writing the plan/, "plan"], [/^Writing /, "write"], [/^Editing /, "write"], [/^Preparing a command/, "command"],
  [/^Planning /, "plan"], [/^Briefing /, "helper"], [/^Preparing /, "tool"],
];

function DraftLine({ text }: { text: string }) {
  const m = text.match(/^(Writing|Editing) (?!the plan)(.+?)(?: · (.+?))?…$/);
  return (
    <span className="flex min-w-0 items-center gap-1.5 whitespace-nowrap">
      {m ? (
        <>
          <Shimmer>{m[1]}</Shimmer>
          <span className="max-w-[260px] truncate rounded-[5px] border border-border-300 bg-bg-200 px-1.5 font-mono text-[11px] text-text-200">{m[2]}</span>
          {m[3] && <span className="tabular-nums text-text-500">{m[3]}</span>}
        </>
      ) : <Shimmer>{text.charAt(0).toUpperCase() + text.slice(1)}</Shimmer>}
    </span>
  );
}

/** What a running tool is doing, as a short present-tense phrase for the status line. */
function toolWord(name: string): string {
  switch (toolKind(name)) {
    case "command": return "Running a command…";
    case "write": return "Writing a file…";
    case "read": return name === "use_skill" ? "Loading a skill…" : "Reading a file…";
    case "search": return "Searching the project…";
    case "web": return name === "web_search" ? "Searching the web…" : "Fetching a page…";
    case "plan": return "Planning the tasks…";
    case "helper": return "Waiting for a helper…";
    default: return name.startsWith("mcp__") ? "Using a connector tool…" : "Using a tool…";
  }
}

/** How long this turn has been going ("12s", "1m 5s"), counting up every second next to the status word. */
function Elapsed({ since }: { since: number }) {
  const [, tick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, []);
  const sec = Math.max(0, Math.floor((Date.now() - since) / 1000));
  return <span className="shrink-0 tabular-nums text-text-500">{sec < 60 ? `${sec}s` : `${Math.floor(sec / 60)}m ${sec % 60}s`}</span>;
}

/** The line at the bottom while Emilie works: the flower and a word. "Thinking" while she reasons, what she is
 *  writing while she drafts a tool call, otherwise a word that changes every few seconds. No timer or token count:
 *  the window stays quiet, the flower alone says she is busy. */
export function Working({ since, activity, thinking, voice, voiceOn, streaming, tool, replying, group, thought }: {
  since: number; tool?: string; replying?: boolean; tokens?: number; activity?: string | null; streaming?: boolean; thinking?: boolean;
  voice?: "" | "replying" | "speaking"; voiceOn?: boolean;
  group?: Item[];      // the run of tool calls that is going on right now: this line is its header, with a chevron beside it
  thought?: string;    // what she is thinking right now: the chevron opens it
}) {
  const [ready, setReady] = useState(Date.now() - since > 400);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (ready) return;
    const t = setTimeout(() => setReady(true), Math.max(0, 400 - (Date.now() - since)));
    return () => clearTimeout(t);
  }, [ready, since]);
  if (!ready && !activity && !voice) return <div className="h-6" />;
  // With the voice on the words are held back and appear together with the voice, so the line says which step it is at:
  // writing the reply, making the voice, then speaking (with a little level meter).
  const step = !activity && voice === "speaking" ? "Speaking" : !activity && voice === "replying" ? "Making the voice…"
    : !activity && voiceOn && streaming ? "Writing the reply…" : "";
  if (step) {
    return (
      <div className="flex h-6 items-center gap-2 text-[12px]" aria-live="polite">
        <MarkSlot id="bloom"><Bloom mode={voice === "speaking" ? "reply" : "think"} /></MarkSlot>
        <span key={step} className="word-in min-w-0">{voice === "speaking" ? <span className="text-text-200">{step}</span> : <Shimmer>{step}</Shimmer>}</span>
        {voice === "speaking" && <span className="eq" aria-hidden="true"><i /><i /><i /><i /></span>}
        <Elapsed since={since} />
      </div>
    );
  }
  const running = group?.find((m): m is ToolItem => m.kind === "tool" && m.status === "running");
  const hasGroup = !!group?.length;      // also in the gap between two tool calls: the run is not over, so the chevron stays beside
  const lastTool = [...(group || [])].reverse().find((m): m is ToolItem => m.kind === "tool");
  const hasThought = !hasGroup && !!thinking && !!thought && !activity;
  // The word says what is REALLY happening, in this order: drafting a tool call (activity), a tool running, the model
  // reasoning, the reply being written, and otherwise waiting for the model to answer. Nothing is picked at random.
  const word = running ? cap(activeText(running)) + "…"
    : (tool ? toolWord(tool) : activity) || (thinking ? "Thinking…" : replying ? "Writing the reply…" : hasGroup ? "Working…" : "Waiting for the model…");
  const kind = running ? toolKind(running.name) : tool ? toolKind(tool) : activity ? DRAFT_KINDS.find(([re]) => re.test(activity))?.[1]
    : hasGroup && !thinking && !replying && lastTool ? toolKind(lastTool.name) : undefined;
  // the flower, or the mark of the work going on; a new kind of work springs in while the old mark shrinks away
  const mark = (
    <MarkSlot id={kind || "bloom"}>
      {kind ? <WorkMark kind={kind} /> : <Bloom mode={thinking ? "think" : replying ? "reply" : "wait"} />}
    </MarkSlot>
  );
  const label = (
    <span key={activity && !tool ? "draft" : word} className="word-in min-w-0">
      {activity && !tool ? <DraftLine text={activity} /> : <Shimmer>{word}</Shimmer>}
    </span>
  );
  if (hasGroup || hasThought) {
    // chevron BESIDE the line while it is going on; it opens what she is doing now (the steps, or the thought)
    const t0 = hasGroup ? ((group![0] as any).at ?? since) : since;
    return (
      <div aria-live="polite">
        <button onClick={() => setOpen(!open)} aria-expanded={open}
          className="flex h-6 max-w-full min-w-0 items-center gap-2 text-left text-[12px] text-text-300 hover:text-text-100">
          {mark}{label}<Elapsed since={t0} />
          <ChevronRight size={12} className={cn("shrink-0 transition-transform duration-150", open && "rotate-90")} />
        </button>
        {open && hasGroup && <StepCard members={group!} />}
        {open && hasThought && (
          <div className="mt-1.5 border-l border-border-300 pl-3 text-[12px] leading-[17px] text-text-300 whitespace-pre-wrap selectable">{thought}</div>
        )}
      </div>
    );
  }
  return (
    <div className="flex h-6 items-center gap-2 text-[12px]" aria-live="polite">
      {mark}{label}<Elapsed since={since} />
    </div>
  );
}

export function ErrorHint({ text }: { text: string }) {
  return <div className="flex items-center gap-2 text-[12px] text-danger"><AlertCircle size={14} />{text}</div>;
}
