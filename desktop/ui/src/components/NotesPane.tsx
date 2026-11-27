// The Notes panel: a Markdown scratchpad for each project (plans, decisions, commands to remember), saved as you type
// on this computer and outside the project, so it never ends up in a commit; and the TODO / FIXME / HACK / XXX / BUG
// comments of the project's files, each opening at its line or going to Emilie as a task.
import { useEffect, useMemo, useRef, useState } from "react";
import { get, post } from "@/lib/api";
import { useStore } from "@/lib/store";
import { cn } from "@/lib/util";
import { insertIntoComposer } from "./Composer";
import * as I from "./icons";
import { askEmilie, btnSm, Card, Chevron, Empty, Hint, IconBtn, Pill, remember, RowBtn, rowCls, SearchField, splitPath } from "./PaneKit";
import { Markdown } from "./Transcript";
import { Spinner } from "./ui";

interface Todo { line: number; tag: string; who: string; text: string }
interface TodoFile { rel: string; abs: string; items: Todo[] }
interface Mem { text: string | null; tab: "notes" | "todos"; preview: boolean; todos: { files: TodoFile[]; total: number; truncated: boolean } | null; q: string; tag: string }
const mem = new Map<string, Mem>();
const TAG_TONE: Record<string, string> = { TODO: "bg-accent-soft text-accent", FIXME: "bg-danger-soft text-danger", BUG: "bg-danger-soft text-danger", HACK: "bg-warn-soft text-warn", XXX: "bg-warn-soft text-warn" };

export function NotesPane({ cwd }: { cwd: string }) {
  const m = remember(mem, cwd, (): Mem => ({ text: null, tab: "notes", preview: false, todos: null, q: "", tag: "" }));
  const toast = useStore((s) => s.toast);
  const [tab, setTabState] = useState(m.tab);
  const setTab = (t: Mem["tab"]) => { m.tab = t; setTabState(t); };
  const [text, setTextState] = useState<string | null>(m.text);
  const [preview, setPreviewState] = useState(m.preview);
  const setPreview = (v: boolean) => { m.preview = v; setPreviewState(v); };
  const [saved, setSaved] = useState<"" | "saving" | "saved" | "error">("");
  const dirty = useRef(false);
  const timer = useRef(0);
  const [todos, setTodos] = useState(m.todos);
  const [scanning, setScanning] = useState(false);
  const [q, setQ] = useState(m.q);
  const [tag, setTag] = useState(m.tag);
  const [shut, setShut] = useState<Record<string, boolean>>({});
  useEffect(() => { m.q = q; m.tag = tag; }, [q, tag]);   // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!cwd || m.text !== null) return;
    get<{ text: string }>("/api/notes", { cwd }).then((r) => { m.text = r.text; setTextState(r.text); }).catch((e) => toast(e.message, "error"));
  }, [cwd]);   // eslint-disable-line react-hooks/exhaustive-deps

  const save = async (t: string) => {
    clearTimeout(timer.current);
    if (!dirty.current) return;
    dirty.current = false;
    setSaved("saving");
    try {
      await post("/api/notes", { cwd, text: t });
      setSaved("saved");
    } catch (e: any) {
      setSaved("error");
      toast(e.message, "error");
    }
  };
  const setText = (t: string) => {
    m.text = t;
    setTextState(t);
    dirty.current = true;
    setSaved("");
    clearTimeout(timer.current);
    timer.current = window.setTimeout(() => save(t), 700);
  };
  useEffect(() => () => { if (dirty.current && m.text !== null) save(m.text); }, []);   // eslint-disable-line react-hooks/exhaustive-deps

  const scan = async () => {
    setScanning(true);
    try {
      const r = await get<Mem["todos"]>("/api/notes/todos", { cwd });
      m.todos = r;
      setTodos(r);
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setScanning(false);
    }
  };
  useEffect(() => { if (tab === "todos" && !todos && cwd) scan(); }, [tab, cwd]);   // eslint-disable-line react-hooks/exhaustive-deps

  const files = useMemo(() => {
    const ql = q.trim().toLowerCase();
    return (todos?.files || []).map((f) => ({ ...f, items: f.items.filter((t) => (!tag || t.tag === tag) && (!ql || t.text.toLowerCase().includes(ql) || f.rel.toLowerCase().includes(ql) || t.who.toLowerCase().includes(ql))) }))
      .filter((f) => f.items.length);
  }, [todos, q, tag]);
  const tagCounts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const f of todos?.files || []) for (const t of f.items) c[t.tag] = (c[t.tag] || 0) + 1;
    return c;
  }, [todos]);

  if (!cwd) return <Empty icon={<I.StickyNote size={22} />} title="No folder">Open a session in a folder to keep notes for its project.</Empty>;

  return (
    <div className="flex h-full flex-col text-[11.5px]">
      <div className="flex items-center gap-1 px-2.5 pt-2">
        <Pill on={tab === "notes"} onClick={() => setTab("notes")}><I.StickyNote size={11} />Notes</Pill>
        <Pill on={tab === "todos"} onClick={() => setTab("todos")}><I.ListChecks size={11} />TODOs{todos ? <span className="tabular-nums text-text-500">{todos.total}</span> : null}</Pill>
        <span className="flex-1" />
        {tab === "notes" && (
          <>
            <span className={cn("mr-1 text-[10.5px]", saved === "error" ? "text-danger" : "text-text-500")}>
              {saved === "saving" ? "Saving…" : saved === "saved" ? "Saved" : saved === "error" ? "Not saved" : ""}
            </span>
            <IconBtn tip={preview ? "Edit" : "Show it formatted"} active={preview} onClick={() => setPreview(!preview)}>{preview ? <I.Pencil size={11} /> : <I.Eye size={12} />}</IconBtn>
            <IconBtn tip="Put the notes in the message to Emilie" disabled={!text?.trim()} onClick={() => { insertIntoComposer(`\nMy notes for this project:\n${text}\n`); toast("Added to the message box"); }}><I.AtSign size={11} /></IconBtn>
          </>
        )}
        {tab === "todos" && <IconBtn tip="Scan the files again" onClick={scan}>{scanning ? <Spinner size={11} /> : <I.Refresh size={12} />}</IconBtn>}
      </div>

      {tab === "notes" && (
        <div className="min-h-0 flex-1 px-2.5 pb-2.5 pt-2">
          {text === null ? <Spinner /> : preview ? (
            <div className="h-full overflow-y-auto rounded-[8px] border border-border-300 bg-bg-200/40 px-4 py-3">
              {text.trim() ? <Markdown text={text} /> : <Hint>Nothing written yet.</Hint>}
            </div>
          ) : (
            <textarea value={text} onChange={(e) => setText(e.target.value)} spellCheck
              onKeyDown={(e) => { if (e.key === "s" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); dirty.current = true; save(text); } }}
              onBlur={() => save(text)}
              placeholder={"Plans, decisions, links, commands to remember… (Markdown)\n\nOnly you see these notes: they stay on this computer, outside the project, so they never end up in a commit.\nThe @ button puts them in your message when Emilie should read them."}
              className="block h-full w-full resize-none rounded-[8px] border border-border-300 bg-bg-200/40 px-3 py-2.5 font-mono text-[11.5px] leading-[18px] text-text-100 outline-none focus:border-border-400 placeholder:font-sans placeholder:text-text-500 selectable" />
          )}
        </div>
      )}

      {tab === "todos" && (
        <div className="min-h-0 flex-1 overflow-y-auto px-2.5 pb-3">
          <div className="mt-2 flex flex-wrap items-center gap-1">
            <Pill on={!tag} onClick={() => setTag("")}>All</Pill>
            {Object.keys(tagCounts).sort().map((t) => (
              <Pill key={t} on={tag === t} onClick={() => setTag(tag === t ? "" : t)}>{t}<span className="tabular-nums text-text-500">{tagCounts[t]}</span></Pill>
            ))}
            <div className="ml-1 flex min-w-[120px] flex-1"><SearchField value={q} onChange={setQ} placeholder="Filter" /></div>
          </div>
          {!todos && <div className="p-2"><Spinner /></div>}
          {todos && !todos.total && <Empty icon={<I.ListChecks size={22} />} title="No TODO comments">No TODO, FIXME, HACK, XXX or BUG comment in the project's files.</Empty>}
          {todos && !!todos.total && !files.length && <Hint className="mt-3">Nothing matches this filter.</Hint>}
          {todos?.truncated && <Hint className="mt-2">Only the first ones are shown.</Hint>}
          <div className="mt-2 flex flex-col gap-2">
            {files.map((f) => {
              const on = !shut[f.rel];
              const [name, dir] = splitPath(f.rel);
              return (
                <Card key={f.rel}>
                  <div role="button" onClick={() => setShut((s) => ({ ...s, [f.rel]: on }))} className={cn(rowCls, "py-[6px]")} title={f.abs}>
                    <Chevron on={on} />
                    <span className="max-w-[60%] shrink-0 truncate text-text-100">{name}</span>
                    <span className="min-w-0 flex-1 truncate text-[10.5px] text-text-500">{dir}</span>
                    <span className="shrink-0 tabular-nums text-[10.5px] text-text-500">{f.items.length}</span>
                  </div>
                  {on && (
                    <div className="border-t border-border-200">
                      {f.items.map((t, i) => (
                        <div key={t.line} role="button" onClick={() => useStore.getState().openFile(f.abs, t.line)}
                          className={cn("group flex min-w-0 items-start gap-2 py-[4px] pl-[12px] pr-2.5 hover:bg-hover/50", i > 0 && "border-t border-border-200")}>
                          <span className={cn("mt-[1px] shrink-0 rounded-[4px] px-1 font-mono text-[9.5px] font-semibold leading-[14px]", TAG_TONE[t.tag] || "bg-bg-400 text-text-300")}>{t.tag}</span>
                          <span className="min-w-0 flex-1 break-words text-[11px] leading-[16px] text-text-200">
                            {t.text || <span className="text-text-500">(no text)</span>}{t.who && <span className="ml-1.5 text-[10px] text-text-500">{t.who}</span>}
                          </span>
                          <RowBtn tip="Ask Emilie to do it" onClick={() => askEmilie(`Do this ${t.tag} in ${f.rel}:${t.line}: "${t.text}". When it is done, remove the ${t.tag} comment.`)}><I.Sparkles size={11} /></RowBtn>
                          <span className="mt-[1px] shrink-0 tabular-nums text-[10px] text-text-500">{t.line}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </Card>
              );
            })}
          </div>
          {!!files.length && (
            <div className="mt-2.5 flex justify-end">
              <button className={btnSm} onClick={() => askEmilie(`Go through the ${tag || "TODO"} comments of this project and tell me which are worth doing first and why (do not change anything yet).`)}>
                <I.Sparkles size={11} />Ask Emilie to prioritize
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
