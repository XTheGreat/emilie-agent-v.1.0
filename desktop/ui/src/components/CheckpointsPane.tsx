// The Checkpoints panel: every turn that changed files, newest first. Open one to see what it changed; go back to just
// before it (the files only, or the files and the conversation). It is /rewind with the changes shown first.
import { useEffect, useState } from "react";
import { post } from "@/lib/api";
import { currentLive, useStore } from "@/lib/store";
import type { Checkpoint, Diff } from "@/lib/types";
import { cn } from "@/lib/util";
import { ChevR } from "./icons";
import { DiffView } from "./Transcript";

interface CkFile { path: string; rel: string; status: "A" | "M" | "D"; diff: Diff | null; binary?: boolean }
const NONE: Checkpoint[] = [];

const ago = (at: number) => {
  const s = Math.max(0, Math.floor(Date.now() / 1000 - at));
  return !at ? "" : s < 60 ? "just now" : s < 3600 ? `${Math.floor(s / 60)} min ago` : s < 86400 ? `${Math.floor(s / 3600)} h ago` : `${Math.floor(s / 86400)} d ago`;
};
const Chevron = ({ on }: { on: boolean }) => <ChevR size={10} className={cn("shrink-0 text-text-500 transition-transform duration-150", on && "rotate-90")} />;

export function CheckpointsPane() {
  const wid = useStore((st) => currentLive(st)?.wid || "");
  const cps = useStore((st) => currentLive(st)?.status.checkpoints || NONE);
  const busy = useStore((st) => !!currentLive(st)?.busy);
  const closed = useStore((st) => !!currentLive(st)?.closed);
  const [open, setOpen] = useState(0);                       // the opened checkpoint's n
  const [files, setFiles] = useState<CkFile[] | null>(null);
  const [shown, setShown] = useState("");                    // the opened file

  // a new turn (or a rewind) renumbers them: close what was open
  const key = cps.map((c) => c.at).join(",");
  useEffect(() => { setOpen(0); }, [wid, key]);
  useEffect(() => {
    setFiles(null);
    setShown("");
    if (!open || !wid) return;
    let dead = false;
    post<{ files: CkFile[] }>("/api/session/checkpoint", { wid, n: open })
      .then((r) => { if (!dead) { setFiles(r.files || []); if (r.files?.length === 1) setShown(r.files[0].path); } })
      .catch((e) => { if (!dead) { setFiles([]); useStore.getState().toast(e.message, "error"); } });
    return () => { dead = true; };
  }, [open, wid, busy]);

  const rewind = async (c: Checkpoint, what: "files" | "both") => {
    const later = c.n - 1;
    const ok = await useStore.getState().confirm(
      what === "files" ? "Restore the files?" : "Restore files and conversation?",
      `The files go back to how they were before "${c.label || "this turn"}"${later ? `, undoing this turn and ${later} later one${later > 1 ? "s" : ""}` : ""}.`
        + (what === "both" ? " The conversation from that point on is removed." : " The conversation stays.")
        + " Changes you made to those files yourself since then are overwritten.",
      { danger: true, ok: "Restore" });
    if (ok) useStore.getState().send(wid, `/rewind ${c.n} ${what}`, [], []);
  };

  const btn = "btn-contrast rounded-[5px] px-2 py-[3px] text-[11px]";

  return (
    <div className="h-full overflow-y-auto px-2.5 pb-3 pt-1 text-[11.5px]">
      <div className="px-1 pb-1.5 pt-2.5 text-text-300">Turns that changed files</div>
      {!cps.length && (
        <div className="px-1 text-[11px] leading-[16px] text-text-500">
          {closed ? "Reopen the session to use checkpoints." : "Nothing yet. A checkpoint is made each time Emilie changes a file. They last while the session stays open."}
        </div>
      )}
      <div className="flex flex-col gap-2">
        {cps.map((c) => {
          const on = open === c.n;
          return (
            <div key={`${c.at}-${c.n}`} className="overflow-hidden rounded-[9px] border border-border-300 bg-bg-200/40">
              <div role="button" onClick={() => setOpen(on ? 0 : c.n)} className="flex min-w-0 items-center gap-2 px-3 py-[7px] hover:bg-hover/50">
                <span className="min-w-0 flex-1 truncate text-text-100" title={c.label}>{c.label || "(no message)"}</span>
                <span className="shrink-0 text-[10.5px] text-text-500">{c.nfiles} file{c.nfiles > 1 ? "s" : ""} · {ago(c.at)}</span>
                <Chevron on={on} />
              </div>
              {on && (
                <>
                  <div className="border-t border-border-200">
                    {files === null && <div className="px-3 py-2 text-[11px] text-text-500">Loading…</div>}
                    {files?.map((f, i) => (
                      <div key={f.path} className={cn(i > 0 && "border-t border-border-200")}>
                        <div role="button" onClick={() => setShown(shown === f.path ? "" : f.path)} className="flex min-w-0 items-center gap-2 py-[5px] pl-[18px] pr-3 text-[11px] hover:bg-hover/50">
                          <span className={cn("min-w-0 flex-1 truncate", f.status === "A" ? "text-ok" : f.status === "D" ? "text-danger" : "text-text-100")} title={f.path}>{f.rel}</span>
                          {!!f.diff?.added && <span className="shrink-0 tabular-nums text-[10.5px] text-ok">+{f.diff.added}</span>}
                          {!!f.diff?.removed && <span className="shrink-0 tabular-nums text-[10.5px] text-danger">−{f.diff.removed}</span>}
                          <button onClick={(e) => { e.stopPropagation(); useStore.getState().openFile(f.path); }} title="Open the file" disabled={f.status === "D"}
                            className="shrink-0 text-text-400 hover:text-text-100 disabled:opacity-30">↗</button>
                          <Chevron on={shown === f.path} />
                        </div>
                        {shown === f.path && (
                          <div className="border-t border-border-200 bg-bg-100">
                            {f.diff?.text ? <DiffView diff={f.diff} file={f.path} />
                              : <div className="px-3 py-2 text-[11px] text-text-500">{f.binary ? "Not a text file." : "The same as before this turn."}</div>}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                  <div className="flex flex-wrap items-center gap-2 border-t border-border-200 px-3 py-2">
                    <span className="mr-auto text-[10.5px] text-text-500">Go back to before this turn</span>
                    <button className={btn} disabled={busy || closed} onClick={() => rewind(c, "files")}>Files only</button>
                    <button className={btn} disabled={busy || closed || c.mark === null} onClick={() => rewind(c, "both")}
                      title={c.mark === null ? "The conversation of this turn can no longer be rewound" : undefined}>Files and chat</button>
                  </div>
                </>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
