// The Search panel: text searched in every file of the project, the matches grouped by file. Click a match to open the
// file at that line in the Files panel; a match, or a whole file, can be put in the message you are writing.
import { useEffect, useState } from "react";
import { get } from "@/lib/api";
import { currentLive, useStore } from "@/lib/store";
import { cn } from "@/lib/util";
import { insertIntoComposer } from "./Composer";
import * as I from "./icons";
import { Tip } from "./ui";

interface Match { line: number; pre: string; hit: string; post: string }
interface Found { rel: string; abs: string; matches: Match[]; more: number }
interface Result { files: Found[]; total: number; truncated: boolean }

// what was typed stays when the panel is closed and opened again (per project folder)
const memory = new Map<string, { q: string; cc: boolean; word: boolean }>();

const attachFile = (f: Found) => insertIntoComposer(`@${f.rel} `);
// one line goes in as text: an @mention would send the whole file
const attachLine = (f: Found, m: Match) => insertIntoComposer(`\n${f.rel}:${m.line}\n\`\`\`\n${m.pre}${m.hit}${m.post}\n\`\`\`\n`);

export function SearchPane({ cwd }: { cwd: string }) {
  const chat = useStore((st) => !!currentLive(st) && !currentLive(st)!.closed);
  const [q, setQ] = useState(() => memory.get(cwd)?.q || "");
  const [cc, setCc] = useState(() => !!memory.get(cwd)?.cc);
  const [word, setWord] = useState(() => !!memory.get(cwd)?.word);
  const [res, setRes] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [shut, setShut] = useState<Record<string, boolean>>({});
  const [again, setAgain] = useState(0);                     // Enter: search again (the files may have changed)

  useEffect(() => {
    memory.set(cwd, { q, cc, word });
    setErr("");
    if (!cwd || q.trim().length < 2) { setRes(null); setBusy(false); return; }
    let dead = false;
    setBusy(true);
    const timer = window.setTimeout(() => {
      get<Result>("/api/fs/search", { cwd, q, case: cc ? "1" : "", word: word ? "1" : "" })
        .then((r) => { if (!dead) { setRes(r); setShut({}); setBusy(false); } })
        .catch((e) => { if (!dead) { setRes(null); setErr(e.message); setBusy(false); } });
    }, 300);
    return () => { dead = true; clearTimeout(timer); };
  }, [cwd, q, cc, word, again]);

  if (!cwd) return <Hint>Open a session in a folder to search its files.</Hint>;

  const toggle = (on: boolean, set: (v: boolean) => void, label: string, tip: string) => (
    <Tip content={tip}>
      <button aria-label={tip} aria-pressed={on} onClick={() => set(!on)}
        className={cn("flex h-[20px] min-w-[22px] items-center justify-center rounded-[5px] px-1 text-[10.5px]",
          on ? "bg-active text-text-000" : "text-text-400 hover:bg-hover hover:text-text-100")}>{label}</button>
    </Tip>
  );

  return (
    <div className="flex h-full flex-col text-[11.5px]">
      <div className="px-2.5 pt-2">
        <div className="flex items-center gap-1 rounded-[7px] border border-border-300 bg-bg-200/40 py-[3px] pl-2 pr-1 focus-within:border-border-400">
          <I.SearchSm size={11} className="shrink-0 text-text-500" />
          <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} spellCheck={false} placeholder="Search in files"
            onKeyDown={(e) => { if (e.key === "Enter") setAgain((n) => n + 1); }}
            className="h-[20px] min-w-0 flex-1 bg-transparent px-1 text-[11.5px] text-text-100 outline-none selectable" />
          {toggle(cc, setCc, "Aa", "Match case")}
          {toggle(word, setWord, "ab", "Whole word")}
        </div>
        <div className="px-1 pb-1.5 pt-1.5 text-[11px] text-text-500">
          {busy ? "Searching…" : !res ? "Type at least 2 characters."
            : !res.total ? "No matches."
              : `${res.total} line${res.total > 1 ? "s" : ""} in ${res.files.length} file${res.files.length > 1 ? "s" : ""}${res.truncated ? " · not all shown, narrow the search" : ""}`}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2.5 pb-3">
        {err && <div className="px-1 text-[11px] text-danger">{err}</div>}
        <div className="flex flex-col gap-2">
          {res?.files.map((f) => {
            const on = !shut[f.rel];
            const cut = f.rel.lastIndexOf("/");
            return (
              // shrink-0: a card must keep its height in the scrolling column
              <div key={f.rel} className="shrink-0 overflow-hidden rounded-[9px] border border-border-300 bg-bg-200/40">
                <div role="button" onClick={() => setShut((s) => ({ ...s, [f.rel]: on }))} title={f.abs}
                  className="group flex min-w-0 items-center gap-2 px-3 py-[7px] hover:bg-hover/50">
                  <span className="shrink-0 max-w-[60%] truncate text-text-100">{f.rel.slice(cut + 1)}</span>
                  <span className="min-w-0 flex-1 truncate text-[10.5px] text-text-500">{cut > 0 ? f.rel.slice(0, cut) : ""}</span>
                  {chat && <AttachButton tip="Attach the file to the chat" onClick={() => attachFile(f)} />}
                  <span className="shrink-0 tabular-nums text-[10.5px] text-text-500">{f.matches.length + f.more}</span>
                  <I.ChevR size={10} className={cn("shrink-0 text-text-500 transition-transform duration-150", on && "rotate-90")} />
                </div>
                {on && (
                  <div className="border-t border-border-200">
                    {f.matches.map((m, i) => (
                      <div key={m.line} role="button" onClick={() => useStore.getState().openFile(f.abs, m.line)}
                        className={cn("group flex min-w-0 items-center gap-2 py-[4px] pl-[12px] pr-3 hover:bg-hover/50", i > 0 && "border-t border-border-200")}>
                        <span className="w-[30px] shrink-0 text-right tabular-nums text-[10.5px] text-text-500">{m.line}</span>
                        <span className="min-w-0 flex-1 truncate whitespace-pre font-mono text-[10.5px] text-text-300">
                          {m.pre}<mark className="rounded-[2px] bg-accent/25 text-text-000">{m.hit}</mark>{m.post}
                        </span>
                        {chat && <AttachButton tip="Attach this line to the chat" onClick={() => attachLine(f, m)} />}
                      </div>
                    ))}
                    {!!f.more && <div className="border-t border-border-200 py-[4px] pl-[50px] pr-3 text-[10.5px] text-text-500">{f.more} more in this file</div>}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

const Hint = ({ children }: { children: React.ReactNode }) => <div className="px-3.5 py-3 text-[11px] leading-[16px] text-text-500">{children}</div>;

function AttachButton({ tip, onClick }: { tip: string; onClick: () => void }) {
  return (
    <button aria-label={tip} title={tip} onClick={(e) => { e.stopPropagation(); onClick(); }}
      className="shrink-0 rounded-[4px] p-0.5 text-text-400 opacity-0 hover:text-text-100 focus-visible:opacity-100 group-hover:opacity-100">
      <I.AtSign size={11} />
    </button>
  );
}
