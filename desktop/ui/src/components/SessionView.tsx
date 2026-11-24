// One open session: the conversation, with tasks, Emilie's question and the message box floating at the bottom.
import { memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useStore } from "@/lib/store";
import type { Item, Live, Todo } from "@/lib/types";
import { post } from "@/lib/api";
import { cn } from "@/lib/util";
import { ArrowUp, Alert, Refresh } from "./icons";
import { Composer } from "./Composer";
import { EnvPanel } from "./EnvPanel";
import { ContextRing, ModeChip, ModelEffortChip } from "./Pickers";
import { ChooseDialog, RequestCard, TaskList } from "./Requests";
import { groupItems, ItemView, NoticeLines, rowItems, ToolGroup, Working, type Row } from "./Transcript";
import { Button, Spinner } from "./ui";

const MODE_ORDER = ["ask", "trust", "plan"];

export function SessionView({ live, envFloat }: { live: Live & { loaded?: boolean }; envFloat?: boolean }) {
  const s = useStore.getState();
  const scroller = useRef<HTMLDivElement>(null);
  const dock = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const [showJump, setShowJump] = useState(false);
  const [dockH, setDockH] = useState(96);
  const typingAt = useRef(0);

  // how tall the floating message box is (it grows with the text, tasks and questions)
  useLayoutEffect(() => {
    const el = dock.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setDockH(el.offsetHeight));
    ro.observe(el);
    setDockH(el.offsetHeight);
    return () => ro.disconnect();
  }, []);

  const items = live.items;
  // "turn" markers ("done in 3s") are not drawn; they only tell where a turn ended
  // a tool call still marked "running" after the turn ended (stopped half way) is interrupted: nothing animates for it
  const shown = useMemo(() => (live.busy || !items.some((i) => i.kind === "tool" && i.status === "running") ? items
    : items.map((i) => (i.kind === "tool" && i.status === "running" ? { ...i, status: "interrupted" } as Item : i))), [items, live.busy]);
  const rows = useMemo(() => groupItems(shown.filter((i) => i.kind !== "turn")), [shown]);
  // The run of tool calls that is going on now is drawn by the status line at the bottom (icon, what it is doing, seconds
  // and a chevron beside it). Once she moves on to something else it becomes the summary line above, with the steps under it.
  const liveGroup = useMemo(() => {
    const last = rows[rows.length - 1];
    return live.busy && live.working && !live.request && last && "group" in last ? last.group : undefined;   // stays live in the gaps between tool calls, until she starts writing
  }, [rows, live.busy, live.working, live.request]);
  const taskLists = useMemo(() => tasksByTurn(rows), [rows]);
  const [cap, setCap] = useState(80);
  useEffect(() => { setCap(80); }, [live.wid]);
  const start = Math.max(0, rows.length - cap);
  const voiceBusy = !!live.working?.voice;
  const endIds = useMemo(() => {
    const out = new Set<string>();
    let last = -1;
    items.forEach((it, i) => { if (it.kind === "assistant") last = i; });
    items.forEach((it, i) => {
      if (it.kind !== "assistant") return;
      if (voiceBusy && i === last) return;               // the voice is still on its way: no copy / share row until it is done
      const next = items[i + 1];
      if (next ? next.kind === "turn" || next.kind === "user" : !live.busy) out.add(it.id);
    });
    return out;
  }, [items, live.busy, voiceBusy]);
  const history = useMemo(() => items.filter((i) => i.kind === "user").map((i: any) => String(i.text)).filter(Boolean).slice(-50), [items]);

  // follow the bottom while new output arrives, unless the user scrolled up
  // (not on every render: reading scrollHeight forces a layout of the whole column; the column's own size tells when to follow)
  const column = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const el = scroller.current, col = column.current;
    if (!el || !col) return;
    const follow = () => { if (stick.current) el.scrollTop = el.scrollHeight; };
    follow();
    const ro = new ResizeObserver(follow);
    ro.observe(col);
    return () => ro.disconnect();
  }, [live.wid]);
  useEffect(() => {
    stick.current = true;
    requestAnimationFrame(() => {
      const el = scroller.current;
      if (el) el.scrollTop = el.scrollHeight;
    });
  }, [live.wid]);
  // Following the bottom is decided by what the USER does, never by how the scroll position moved: content that grows
  // or shrinks (a status line coming and going, rows measured late) moves the position by itself and must neither
  // pull the view back down nor let it go. Wheel up lets go at once; reaching the bottom again (by wheel, keys or the
  // scrollbar) picks it up again; dragging the scrollbar follows where the thumb is.
  const dragging = useRef(false);
  const frame = useRef(0);
  const onScroll = () => {
    if (frame.current) return;                      // at most once per frame, however many scroll events came
    frame.current = requestAnimationFrame(() => {
      frame.current = 0;
      const el = scroller.current;
      if (!el) return;
      const gap = el.scrollHeight - el.scrollTop - el.clientHeight;
      if (dragging.current) stick.current = gap < 6;
      else if (gap < 6) stick.current = true;
      setShowJump((v) => { const n = !stick.current && gap >= 6; return v === n ? v : n; });
    });
  };
  const onWheel = (e: React.WheelEvent) => { if (e.deltaY < 0) stick.current = false; };
  const onPointerDown = (e: React.PointerEvent) => {
    if (e.target !== scroller.current) return;               // the scrollbar itself, not the conversation
    dragging.current = true;
    window.addEventListener("pointerup", () => { dragging.current = false; }, { once: true });
  };
  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const key = (e: KeyboardEvent) => { if (["PageUp", "Home", "ArrowUp"].includes(e.key) && document.activeElement === el) stick.current = false; };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, []);
  const jump = () => {
    stick.current = true;
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  };

  const send = useCallback((text: string, atts: any[], pastes: any[]) => {
    stick.current = true;
    s.send(live.wid, text, atts, pastes);
  }, [live.wid]);
  const runCommand = (cmd: string) => send(cmd, [], []);
  const rewind = useCallback((n: number) => send(`/rewind ${n} both`, [], []), [send]);
  const st = live.status;
  const mode = st.mode || "ask";
  const req = live.request;

  return (
    <div className="relative h-full min-w-0 flex-1">
      {/* The conversation fills the whole height and scrolls behind the message box (its scrollbar runs down to the
          bottom of the window, as in Claude Code); `dockH` keeps the last message clear of the box. */}
      <div ref={scroller} onScroll={onScroll} onWheel={onWheel} onPointerDown={onPointerDown} className="absolute inset-0 overflow-y-auto [scrollbar-gutter:stable_both-edges]">
        {/* Claude Code's geometry, measured: the conversation sits 14px inside the message box on the left and 13px on the
            right (where your messages end); Emilie's text stops 43px earlier so lines stay short and easy to read. */}
        <div ref={column} className="mx-auto flex w-full flex-col gap-3 pl-[34px] pr-[33px] pt-5"
          style={{ maxWidth: "calc(var(--col-w) + 40px)", paddingBottom: dockH + 16 }}>
          {!live.loaded && !items.length && <div className="flex justify-center py-16"><Spinner size={20} /></div>}
          {live.loaded && !items.length && !live.busy && (
            <div className="py-16 text-center text-[12.5px] text-text-500">Send a message to start. Type / for commands and skills, @ to mention a file.</div>
          )}
          {/* one flat keyed list, so a task list moving down with its turn is moved, not redrawn */}
          {start > 0 && (
            <button onClick={() => setCap((c) => c + 80)}
              className="mx-auto rounded-full border border-border-300 px-3 py-1 text-[11.5px] text-text-300 hover:bg-hover hover:text-text-100">
              Show {Math.min(80, start)} earlier ({start} hidden)
            </button>
          )}
          {rows.slice(start).flatMap((r, j) => {
            const i = start + j;
            const row = (
              <RowView key={r.key} r={r} checkpoints={st.checkpoints} onRewind={rewind} endOfTurn={"item" in r && endIds.has(r.item.id)}
                fresh={i >= rows.length - 3} />
            );
            const t = taskLists.get(i);
            if (liveGroup && i === rows.length - 1) return t ? [<div key={t.key} className="item-in pr-[43px]"><TaskList todos={t.todos} /></div>] : [];
            return t ? [row, <div key={t.key} className="item-in pr-[43px]"><TaskList todos={t.todos} /></div>] : [row];
          })}
          {(live.busy || !!live.working?.voice) && live.working && !req && (
            <Working since={live.working.since} tool={live.busy ? lastRunningTool(items) : undefined}
              replying={(() => { const l = items[items.length - 1]; return l?.kind === "assistant" && !!l.streaming; })()} activity={live.working.activity} streaming={live.working.streaming}
              voice={live.working.voice} voiceOn={live.working.voiceOn}
              thinking={items[items.length - 1]?.kind === "thinking"} group={liveGroup}
              thought={(() => { const l = items[items.length - 1]; return l?.kind === "thinking" ? String(l.text || "") : undefined; })()} />
          )}
        </div>
      </div>
      {/* the message box and what sits on it float over the conversation; the 10px sides leave the scrollbar free */}
      <div ref={dock} className="pointer-events-none absolute inset-x-[10px] bottom-0 z-10">
        {showJump && (
          <button onClick={jump} aria-label="Jump to latest"
            className="pointer-events-auto absolute -top-10 left-1/2 flex h-7 w-7 -translate-x-1/2 items-center justify-center rounded-full border border-border-400 bg-bg-300 text-text-200 shadow-menu hover:text-text-000">
            <ArrowUp size={14} className="rotate-180" />
          </button>
        )}
        <div className="h-4 bg-gradient-to-t from-bg-100 to-transparent" />
        <div className="pointer-events-auto bg-bg-100 px-[10px] pb-[2px]">
        {live.stale && !live.closed && (
          <Banner text="The provider changed. Restart this session to use it (the conversation is kept)."
            action={<Button size="sm" onClick={() => s.restartSession(live.wid)}><Refresh size={12} />Restart</Button>} />
        )}
        {live.closed && (
          <Banner text="This session's process has ended. Reopen it to continue (the conversation is saved)."
            action={<Button size="sm" onClick={() => reopen(live)}><Refresh size={12} />Reopen</Button>} />
        )}

        {req && req.kind !== "choose" && <RequestCard req={req} onAnswer={(v) => s.answer(live.wid, req.id, v)} />}
        <Composer
          draftKey={live.wid}
          busy={live.busy}
          disabled={live.closed}
          commands={live.commands}
          cwd={live.cwd}
          history={history}
          placeholder={live.busy ? "Queue another message…" : "Type / for commands"}
          onSend={send}
          onStop={() => s.stop(live.wid)}
          onCycleMode={() => s.setOpt(live.wid, { mode: MODE_ORDER[(MODE_ORDER.indexOf(mode) + 1) % 3] })}
          talk={st.talk}
          onTalk={(on) => s.setTalk(live.wid, on)}
          call={!!st.call}
          onCall={(on) => s.setCall(live.wid, on)}
          onTyping={() => {
            if (st.call && Date.now() - typingAt.current > 3000) {
              typingAt.current = Date.now();
              post("/api/session/typing", { wid: live.wid }).catch(() => {});
            }
          }}
          autoFocus
          footer={
            <>
              <div className="flex-1" />
              <ModelEffortChip model={st.model || ""} effort={st.effort || "medium"}
                onModel={(m) => s.setOpt(live.wid, { model: m })} onEffort={(e) => s.setOpt(live.wid, { effort: e })} />
              <ModeChip value={mode} onChange={(m) => s.setOpt(live.wid, { mode: m })} />
              <ContextRing live={live} onCommand={runCommand} />
            </>
          }
        />
        </div>
      </div>
      {envFloat && (
        <EnvPanel live={live} onCommand={runCommand} floating maxHeight={`calc(100% - ${dockH + 16}px)`}
          onClose={() => useStore.setState({ envFloat: false })} />
      )}
      {req && req.kind === "choose" && <ChooseDialog req={req} onAnswer={(v) => s.answer(live.wid, req.id, v)} />}
    </div>
  );
}

/** The tool that is running right now (the newest one still marked running), if any. */
function lastRunningTool(items: Item[]): string | undefined {
  for (let i = items.length - 1; i >= 0 && i >= items.length - 12; i--) {
    const it = items[i];
    if (it.kind === "tool" && it.status === "running") return it.name;
    if (it.kind === "user" || it.kind === "turn") break;
  }
  return undefined;
}

/** Rows that use the narrower text width: replies, thinking, tool lines (command output cards keep the full width). */
function sameRow(a: Row, b: Row): boolean {
  if ("group" in a || "group" in b) return "group" in a && "group" in b && a.group.length === b.group.length && a.group.every((m, i) => m === b.group[i]);
  if ("lines" in a || "lines" in b) return "lines" in a && "lines" in b && a.lines.length === b.lines.length && a.lines.every((m, i) => m === b.lines[i]);
  return a.item === (b as any).item;
}

const RowView = memo(function RowView({ r, checkpoints, onRewind, endOfTurn, fresh }:
  { r: Row; checkpoints: any; onRewind: (n: number) => void; endOfTurn: boolean; fresh: boolean }) {
  return (
    <div className={cn(fresh && "item-in", prose(r) && "pr-[43px]")}>
      {"group" in r ? <ToolGroup members={r.group} />
        : "lines" in r ? <NoticeLines items={r.lines} />
        : <ItemView item={r.item} checkpoints={checkpoints} onRewind={onRewind} endOfTurn={endOfTurn} />}
    </div>
  );
}, (a, b) => a.checkpoints === b.checkpoints && a.endOfTurn === b.endOfTurn && a.fresh === b.fresh && a.onRewind === b.onRewind && sameRow(a.r, b.r));

function prose(r: Row): boolean {
  return !("item" in r) || ["assistant", "thinking", "tool", "turn", "note", "denied", "notice"].includes(r.item.kind);
}

/** Where task lists go: under the last row of the turn that wrote them (row index → list). The turn in progress has
 *  its list under the latest message; once your next message starts a new turn, that list stays where it was instead
 *  of following the conversation down. Each turn shows the last list it wrote; a queued message (not sent to Emilie
 *  yet) does not start a turn. */
function tasksByTurn(rows: Row[]): Map<number, { key: string; todos: Todo[] }> {
  const out = new Map<number, { key: string; todos: Todo[] }>();
  let cur: { key: string; todos: Todo[] } | null = null;
  const close = (last: number) => {
    if (cur && last >= 0) out.set(last, cur);
    cur = null;
  };
  rows.forEach((r, i) => {
    if ("item" in r && r.item.kind === "user" && !r.item.queued && !r.item.failed) close(i - 1);
    for (const it of rowItems(r)) {
      if (it.kind !== "tool" || it.name !== "todo_write" || !Array.isArray(it.input?.todos)) continue;
      if (it.status !== "ok" && it.status !== "running" && it.status !== "interrupted") continue;      // a rejected list changed nothing
      const todos = (it.input.todos as Todo[]).filter((t) => t && typeof t === "object" && t.content);
      cur = todos.length ? { key: cur?.key || `tasks:${it.id}`, todos } : null;   // the key stays with the turn's list
    }
  });
  close(rows.length - 1);
  return out;
}

function reopen(live: Live) {
  const s = useStore.getState();
  const meta = s.sessions.find((x) => x.id === live.sid);
  const lives = { ...s.lives };
  delete lives[live.wid];
  useStore.setState({ lives });
  if (meta) s.openSession(meta);
  else if (live.sid) s.openSession({ id: live.sid, cwd: live.cwd, title: live.title, updated: 0, created: 0, n: 0, model: "" });
}

function Banner({ text, action }: { text: string; action?: React.ReactNode }) {
  return (
    <div className="mx-auto mb-2 flex w-full items-center gap-2.5 rounded-lg border border-warn/40 bg-warn-soft px-3 py-1.5 text-[11.5px] text-text-200" style={{ maxWidth: "var(--col-w)" }}>
      <Alert size={13} className="shrink-0 text-warn" />
      <span className="flex-1">{text}</span>
      {action}
    </div>
  );
}
