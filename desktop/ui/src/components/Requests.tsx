// Questions Emilie asks while working: permission for a tool, approval of a plan, and pickers (/model, /resume, ...).
import { useEffect, useRef, useState } from "react";
import type { Request, Todo } from "@/lib/types";
import { basename, cn } from "@/lib/util";
import { Alert, ChevronRight, CircleCheck, CircleDashed, CircleEllipsis, ListTodo, Shield } from "./icons";
import { DiffView, Markdown, TodoList } from "./Transcript";
import { Button, Kbd, Modal } from "./ui";

export function RequestCard({ req, onAnswer }: { req: Request; onAnswer: (v: any) => void }) {
  if (req.kind === "plan") return <PlanCard plan={req.plan} onAnswer={onAnswer} />;
  if (req.kind === "permission") return <PermissionCard req={req} onAnswer={onAnswer} />;
  return null;
}

function useKeys(map: Record<string, () => void>, ref: React.RefObject<HTMLElement | null>) {
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const h = (e: KeyboardEvent) => {
      const f = map[e.key.toLowerCase()];
      if (f && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        f();
      }
    };
    el.addEventListener("keydown", h);
    return () => el.removeEventListener("keydown", h);
  });
}

function PermissionCard({ req, onAnswer }: { req: Extract<Request, { kind: "permission" }>; onAnswer: (v: string) => void }) {
  const box = useRef<HTMLDivElement>(null);
  const first = useRef<HTMLButtonElement>(null);
  useEffect(() => first.current?.focus(), [req.id]);
  const n = req.name;
  const file = basename(String(req.input?.path || req.target || ""));
  const title =
    n === "bash" || n === "bash_bg" ? "Allow Emilie to run this command?"
      : n === "write_file" ? `Allow Emilie to write ${file}?`
        : ["edit_file", "notebook_edit", "docx_edit", "xlsx_write"].includes(n) ? `Allow Emilie to edit ${file}?`
          : n === "docx_create" ? `Allow Emilie to create ${file}?`
            : n === "notebook_run" ? `Allow Emilie to run the notebook ${file}?`
              : n === "web_fetch" ? "Allow Emilie to open this web page?"
                : n.startsWith("mcp__") ? `Allow Emilie to use ${req.label}?` : `Allow ${req.label}?`;
  const keys: Record<string, () => void> = { "1": () => onAnswer("y"), y: () => onAnswer("y"), "4": () => onAnswer("n"), n: () => onAnswer("n"), escape: () => onAnswer("n") };
  if (req.can_always) Object.assign(keys, { "2": () => onAnswer("a"), a: () => onAnswer("a"), "3": () => onAnswer("t"), t: () => onAnswer("t") });
  useKeys(keys, box);
  const showTarget = !req.diff || n === "bash" || n === "bash_bg";
  return (
    <div ref={box} className="mx-auto mb-2 w-full overflow-hidden rounded-[9px] border border-composer-border bg-bg-300 shadow-menu animate-pop" style={{ maxWidth: "var(--col-w)" }}>
      <div className="flex items-center gap-2 px-4 pt-3.5 pb-2">
        <Shield size={16} className="text-accent" />
        <div className="text-[13px] font-medium text-text-100">{title}</div>
      </div>
      <div className="max-h-[42vh] overflow-auto px-4">
        {showTarget && (
          <div className="rounded-lg bg-bg-200 px-3 py-2 font-mono text-[11.5px] text-text-100 whitespace-pre-wrap break-all selectable">{req.target}</div>
        )}
        {req.diff && <div className="mt-2 overflow-hidden rounded-lg border border-border-300"><DiffView diff={req.diff} max={300} /></div>}
        {req.reason && (
          <div className="mt-2 flex items-start gap-2 rounded-lg bg-warn-soft px-3 py-2 text-[12px] text-warn">
            <Alert size={15} className="mt-[1px] shrink-0" />{req.reason}
          </div>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2 px-4 py-3">
        <Button ref={first} variant="primary" onClick={() => onAnswer("y")}>Allow once <Kbd>1</Kbd></Button>
        {req.can_always && (
          <>
            <Button onClick={() => onAnswer("a")}>Always allow {
              n === "bash" || n === "bash_bg" ? "commands"
                : ["edit_file", "notebook_edit", "docx_edit", "xlsx_write"].includes(n) ? "edits"
                  : n === "write_file" || n === "docx_create" ? "new files"
                    : n === "web_fetch" ? "web pages"
                      : n === "notebook_run" ? "notebook runs" : req.label
            } this session <Kbd>2</Kbd></Button>
            <Button onClick={() => onAnswer("t")}>Trust this folder <Kbd>3</Kbd></Button>
          </>
        )}
        <div className="flex-1" />
        <Button variant="ghost" onClick={() => onAnswer("n")}>Deny <Kbd>Esc</Kbd></Button>
      </div>
    </div>
  );
}

function PlanCard({ plan, onAnswer }: { plan: string; onAnswer: (v: string) => void }) {
  const box = useRef<HTMLDivElement>(null);
  const first = useRef<HTMLButtonElement>(null);
  useEffect(() => first.current?.focus(), [plan]);
  useKeys({ y: () => onAnswer("y"), "1": () => onAnswer("y"), t: () => onAnswer("t"), "2": () => onAnswer("t"), n: () => onAnswer("n"), "3": () => onAnswer("n"), escape: () => onAnswer("n") }, box);
  return (
    <div ref={box} className="mx-auto mb-2 w-full overflow-hidden rounded-[9px] border border-composer-border bg-bg-300 shadow-menu animate-pop" style={{ maxWidth: "var(--col-w)" }}>
      <div className="flex items-center gap-2 border-b border-border-200 px-4 py-3">
        <ListTodo size={16} className="text-link" />
        <div className="text-[13px] font-medium text-text-100">Ready to start? Here is Emilie's plan</div>
      </div>
      <div className="max-h-[46vh] overflow-auto px-5 py-4"><Markdown text={plan || "(empty plan)"} className="text-[13px]" /></div>
      <div className="flex flex-wrap items-center gap-2 border-t border-border-200 px-4 py-3">
        <Button ref={first} variant="primary" onClick={() => onAnswer("y")}>Approve, ask before each change <Kbd>1</Kbd></Button>
        <Button onClick={() => onAnswer("t")}>Approve and run on her own <Kbd>2</Kbd></Button>
        <div className="flex-1" />
        <Button variant="ghost" onClick={() => onAnswer("n")}>Keep planning <Kbd>3</Kbd></Button>
      </div>
    </div>
  );
}

export function ChooseDialog({ req, onAnswer }: { req: Extract<Request, { kind: "choose" }>; onAnswer: (v: any) => void }) {
  const [idx, setIdx] = useState(req.idx || 0);
  const list = useRef<HTMLDivElement>(null);
  useEffect(() => setIdx(req.idx || 0), [req.id]);
  useEffect(() => {
    list.current?.querySelector(`[data-i="${idx}"]`)?.scrollIntoView({ block: "nearest" });
  }, [idx]);
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setIdx((i) => Math.min(req.rows.length - 1, i + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setIdx((i) => Math.max(0, i - 1)); }
    else if (e.key === "PageDown") { e.preventDefault(); setIdx((i) => Math.min(req.rows.length - 1, i + 10)); }
    else if (e.key === "PageUp") { e.preventDefault(); setIdx((i) => Math.max(0, i - 10)); }
    else if (e.key === "Enter") { e.preventDefault(); onAnswer(["enter", idx]); }
    else if (req.keys.includes(e.key.toLowerCase())) { e.preventDefault(); onAnswer([e.key.toLowerCase(), idx]); }
  };
  return (
    <Modal open onOpenChange={(o) => !o && onAnswer(null)} title={req.title} description={req.hint} wide>
      <div ref={list} tabIndex={0} autoFocus onKeyDown={onKey} className="mx-4 mb-4 mt-2 max-h-[56vh] overflow-y-auto rounded-lg border border-border-300 bg-bg-100 p-1 outline-none">
        {req.rows.map((html, i) => (
          <div key={i} data-i={i} onMouseEnter={() => setIdx(i)} onClick={() => onAnswer(["enter", i])}
            className={cn("cursor-default rounded-lg px-2.5 py-1.5 font-mono text-[11.5px] whitespace-pre", i === idx && "bg-hover")}
            dangerouslySetInnerHTML={{ __html: html }} />
        ))}
      </div>
    </Modal>
  );
}

/** Emilie's task list, as in Claude Code: part of the conversation, right under the latest message (not a box pinned
 *  over the message box). A quiet bordered box; the current task in white with a ··· circle, the next ones grey with a
 *  dashed circle, finished ones ticked and struck through. Once everything is done it folds to one line. */
export function TaskList({ todos }: { todos: Todo[] }) {
  const done = todos.filter((t) => t.status === "completed").length;
  const all = todos.length > 0 && done === todos.length;
  const [open, setOpen] = useState(!all);
  useEffect(() => setOpen(!all), [all]);
  if (!todos.length) return null;
  return (
    <div data-tasklist className="rounded-[10px] border border-[var(--task-border)] px-[14px] py-[10px] text-[12.5px] leading-[21px]">
      {all && (
        <button className="flex w-full items-center gap-[9px] text-left text-text-400 hover:text-text-200" onClick={() => setOpen(!open)}>
          <CircleCheck size={14} className="shrink-0" />
          <span className="flex-1">All {todos.length} tasks done</span>
          <ChevronRight size={13} className={cn("shrink-0 transition-transform duration-150", open && "rotate-90")} />
        </button>
      )}
      {open && (
        <ul className={cn("flex flex-col", all && "mt-1")}>
          {todos.map((t, i) => (
            <li key={i} className={cn("flex items-start gap-[9px]",
              t.status === "in_progress" ? "text-text-100" : t.status === "completed" ? "text-text-500" : "text-text-400")}>
              <span className="mt-[3.5px] shrink-0">
                {t.status === "completed" ? <CircleCheck size={14} /> : t.status === "in_progress" ? <CircleEllipsis size={14} /> : <CircleDashed size={14} />}
              </span>
              <span className={cn("min-w-0", t.status === "completed" && "line-through decoration-text-500/60")}>{t.content}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
