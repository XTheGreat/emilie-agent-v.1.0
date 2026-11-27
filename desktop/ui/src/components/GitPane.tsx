// The Git panel: source control for the session's repository, like an editor's. The branch (switch, create, delete),
// sync with the remote (fetch, pull, push), a commit box (commit, commit all, commit and push, amend, or let Emilie
// write the message with /commit), the staged and unstaged files (stage, unstage, discard, each with its diff),
// conflicts, stashes and the recent commits (what each changed; "Show diff" opens it in the Changes panel).
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { get, post } from "@/lib/api";
import { openExternal, openPath } from "@/lib/desktop";
import { useStore } from "@/lib/store";
import type { Diff } from "@/lib/types";
import { cn } from "@/lib/util";
import * as I from "./icons";
import {
  askEmilie, btnPrimary, btnSm, Card, Chevron, copy, Empty, Heading, Hint, IconBtn, Output, remember, RowBtn, rowCls,
  splitPath, useJob, useRefreshOn,
} from "./PaneKit";
import { DiffView } from "./Transcript";
import { Menu, MenuContent, MenuItem, MenuLabel, MenuSep, MenuSub, MenuSubContent, MenuSubTrigger, MenuTrigger, Spinner } from "./ui";

interface GFile { path: string; status: string; orig?: string }
interface Branch { name: string; current: boolean; upstream: string; track: string; when: string }
interface Commit { hash: string; full: string; subject: string; author: string; when: string; refs: string[] }
interface Stash { ref: string; subject: string; when: string }
interface Scm {
  repo: boolean; can_init?: boolean; root?: string; error?: string; branch?: string; detached?: boolean; oid?: string;
  initial?: boolean; upstream?: string; ahead?: number; behind?: number; staged?: GFile[]; changed?: GFile[];
  untracked?: number; conflicts?: GFile[]; state?: string; stash_count?: number; branches?: Branch[];
  remote_branches?: { name: string; when: string }[]; remotes?: string[]; web?: string; commits?: Commit[]; stashes?: Stash[];
}
interface CommitInfo {
  hash: string; full: string; author: string; email: string; when: string; date: string; message: string;
  files: { path: string; orig: string; status: string; added: number; removed: number }[];
}
type DiffState = Diff & { nodiff?: string } | "loading" | { error: string };

const WORD: Record<string, string> = { M: "Modified", A: "Added", D: "Deleted", R: "Renamed", U: "Untracked (new)", C: "Copied" };
const tone = (s: string) => (s === "M" ? "text-warn" : s === "A" || s === "U" ? "text-ok" : s === "D" ? "text-danger" : s === "R" ? "text-link" : "text-danger");
const join = (root: string, rel: string) => {
  const sep = root.includes("\\") ? "\\" : "/";
  return root.replace(/[\\/]+$/, "") + sep + rel.split("/").join(sep);
};

interface Mem { msg: string; job: string | null; jobKind: string; open: Record<string, boolean> }
const mem = new Map<string, Mem>();

export function GitPane({ cwd }: { cwd: string }) {
  const m = remember(mem, cwd, () => ({ msg: "", job: null, jobKind: "", open: { staged: true, changed: true, conflicts: true, stashes: false, history: true } }));
  const toast = useStore((s) => s.toast);
  const [st, setSt] = useState<Scm | null>(null);
  const [err, setErr] = useState("");
  const [msg, setMsgState] = useState(m.msg);
  const setMsg = (v: string) => { m.msg = v; setMsgState(v); };
  const [sec, setSec] = useState(m.open);
  const toggleSec = (k: string) => setSec((s) => { const n = { ...s, [k]: !s[k] }; m.open = n; return n; });
  const [busy, setBusy] = useState("");
  const [jobId, setJobId] = useState<string | null>(m.job);
  const [jobKind, setJobKind] = useState(m.jobKind);
  const [shown, setShown] = useState("");                         // the file whose diff is open ("staged:path" / "changed:path")
  const [diffOf, setDiffOf] = useState<{ key: string; d: DiffState } | null>(null);
  const diff: DiffState | null = diffOf && diffOf.key === shown ? diffOf.d : shown ? "loading" : null;
  const [openCommit, setOpenCommit] = useState("");
  const [info, setInfo] = useState<Record<string, CommitInfo | "loading" | string>>({});
  const [creating, setCreating] = useState(false);
  const [newBranch, setNewBranch] = useState("");
  const [bq, setBq] = useState("");
  const [allCommits, setAllCommits] = useState(false);
  const seq = useRef(0);

  const load = useCallback(async () => {
    if (!cwd) return;
    const n = ++seq.current;
    try {
      const r = await get<Scm>("/api/git/scm", { cwd });
      if (n === seq.current) { setSt(r); setErr(r.error || ""); }
    } catch (e: any) {
      if (n === seq.current) setErr(e.message);
    }
  }, [cwd]);
  useEffect(() => { load(); }, [load]);
  useRefreshOn(cwd, load);
  useEffect(() => {
    const t = window.setInterval(() => { if (!document.hidden) load(); }, 10000);
    return () => clearInterval(t);
  }, [load]);

  const staged = st?.staged || [], changed = st?.changed || [], conflicts = st?.conflicts || [];
  const root = st?.root || cwd;
  // what the open diff depends on: reload it when the file list changes, not on every refresh
  const sig = useMemo(() => JSON.stringify([st?.oid, staged, changed]), [st]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!shown) return;
    const key = shown;
    const [where, ...rest] = key.split(":");
    const path = rest.join(":");
    const f = (where === "staged" ? staged : changed).find((x) => x.path === path);
    if (!f) { setShown(""); return; }
    let dead = false;
    get<Diff & { nodiff?: string }>("/api/git/file", { cwd, path, staged: where === "staged" ? "1" : "", untracked: f.status === "U" ? "1" : "" })
      .then((r) => { if (!dead) setDiffOf({ key, d: r }); })
      .catch((e) => { if (!dead) setDiffOf({ key, d: { error: e.message } }); });
    return () => { dead = true; };
  }, [shown, sig]);   // eslint-disable-line react-hooks/exhaustive-deps

  const act = async (label: string, path: string, body: object, done?: string) => {
    setBusy(label);
    try {
      await post(path, { cwd, ...body });
      if (done) toast(done);
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy("");
      load();
    }
  };
  const stage = (paths: string[] = []) => act("stage", "/api/git/stage", { paths });
  const unstage = (paths: string[] = []) => act("unstage", "/api/git/unstage", { paths });
  const discard = async (files: GFile[]) => {
    if (!files.length) return;
    const tracked = files.filter((f) => f.status !== "U").map((f) => f.path);
    const fresh = files.filter((f) => f.status === "U").map((f) => f.path);
    const what = files.length === 1 ? `"${files[0].path}"` : `${files.length} files`;
    const body = !tracked.length
      ? `${what} ${fresh.length === 1 ? "is a new file: it is" : "are new files: they are"} deleted.`
      : !fresh.length ? `${what}: the changes that are not staged are thrown away.`
        : `The changes that are not staged are thrown away in ${tracked.length === 1 ? "1 file" : `${tracked.length} files`}, and ${fresh.length === 1 ? "1 new file is" : `${fresh.length} new files are`} deleted.`;
    const ok = await useStore.getState().confirm(!tracked.length ? "Delete new files?" : "Discard changes?", `${body} This cannot be undone.`,
      { danger: true, ok: !tracked.length ? "Delete" : "Discard" });
    if (ok) act("discard", "/api/git/discard", { paths: tracked, untracked: fresh });
  };

  // ------------------------------------------------------------ commit / sync run as jobs (hooks and the network take time)
  const startJob = async (kind: string, path: string, body: object) => {
    try {
      const r = await post<{ job: string }>(path, { cwd, ...body });
      m.job = r.job; m.jobKind = kind;
      setJobId(r.job); setJobKind(kind);
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  const { job, lines } = useJob(jobId, (j) => {
    m.job = null;
    if (j.error) {
      toast(j.error.split("\n").filter(Boolean).slice(-1)[0] || j.error, "error");
    } else if (jobKind.startsWith("commit") || jobKind === "amend") {
      setMsg("");
      toast(`Committed ${j.result?.hash || ""}${j.result?.push ? " and pushed" : ""}`);
      setJobId(null);
    } else {
      toast({ fetch: "Fetched", pull: "Pulled", push: "Pushed" }[jobKind] || "Done");
      setJobId(null);
    }
    load();
  });
  const running = !!job?.running || (!!jobId && !job);
  const sync = (action: "fetch" | "pull" | "push") => startJob(action, "/api/git/sync", { action });
  const commit = (o: { push?: boolean; amend?: boolean } = {}) => {
    if (!msg.trim() && !o.amend) { toast("Write a commit message first (or let Emilie write it)", "error"); return; }
    startJob(o.push ? "commit-push" : o.amend ? "amend" : "commit", "/api/git/commit",
      { message: msg, all: staged.length === 0, push: !!o.push, amend: !!o.amend });
  };

  // ------------------------------------------------------------ branches
  const checkout = (name: string, remote = false) => act("branch", "/api/git/branch", { action: remote ? "track" : "checkout", name }, `Switched to ${remote ? name.split("/").slice(1).join("/") : name}`);
  const create = async () => {
    const name = newBranch.trim();
    if (!name) return;
    await act("branch", "/api/git/branch", { action: "create", name }, `Created and switched to ${name}`);
    setCreating(false);
    setNewBranch("");
  };
  const delBranch = async (name: string) => {
    const s = useStore.getState();
    if (!(await s.confirm("Delete branch?", `The branch "${name}" is deleted (its commits stay reachable from other branches that contain them).`, { danger: true, ok: "Delete" }))) return;
    try {
      await post("/api/git/branch", { cwd, action: "delete", name });
      toast(`Deleted ${name}`);
    } catch (e: any) {
      if (/not fully merged/i.test(e.message) && await s.confirm("Not merged", `"${name}" has commits that are in no other branch. Delete it anyway? Those commits are lost.`, { danger: true, ok: "Delete anyway" })) {
        await act("branch", "/api/git/branch", { action: "delete", name, force: true }, `Deleted ${name}`);
      } else if (!/not fully merged/i.test(e.message)) toast(e.message, "error");
    }
    load();
  };
  const stash = async (action: "push" | "pop" | "apply" | "drop", ref = "") => {
    if (action === "drop" && !(await useStore.getState().confirm("Drop stash?", `${ref} is deleted with the changes in it.`, { danger: true, ok: "Drop" }))) return;
    act("stash", "/api/git/stash", { action, ref }, { push: "Changes stashed", pop: "Stash applied and dropped", apply: "Stash applied", drop: "Stash dropped" }[action]);
  };

  // ------------------------------------------------------------ history
  const toggleCommit = (h: string) => {
    if (openCommit === h) { setOpenCommit(""); return; }
    setOpenCommit(h);
    if (info[h] && info[h] !== "loading") return;
    setInfo((x) => ({ ...x, [h]: "loading" }));
    get<CommitInfo>("/api/git/commit", { cwd, hash: h })
      .then((r) => setInfo((x) => ({ ...x, [h]: r })))
      .catch((e) => setInfo((x) => ({ ...x, [h]: e.message })));
  };
  const showInChanges = (h: string) => {
    const s = useStore.getState();
    useStore.setState({ diffGo: { commit: h, n: (s.diffGo?.n || 0) + 1 } });
    s.showPane("diff");
  };

  if (!cwd) return <Empty icon={<I.BranchSm size={22} />} title="No folder">Open a session in a folder to see its git repository.</Empty>;
  if (!st && !err) return <div className="p-3"><Spinner /></div>;
  if (st && !st.repo) {
    return (
      <Empty icon={<I.BranchSm size={22} />} title="Not a git repository"
        action={st.can_init && <button className={btnPrimary} disabled={!!busy} onClick={() => act("init", "/api/git/init", {}, "Repository created")}>Initialize repository</button>}>
        This folder is not under version control yet. A repository lets you commit, branch and go back to any earlier version.
      </Empty>
    );
  }

  const branches = st?.branches || [];
  const bl = bq.trim().toLowerCase();
  const locals = branches.filter((b) => !bl || b.name.toLowerCase().includes(bl));
  const remotes = (st?.remote_branches || []).filter((b) => (!bl || b.name.toLowerCase().includes(bl)) && !branches.some((l) => l.upstream === b.name));
  const branchLabel = st?.detached ? `detached at ${st.oid}` : st?.branch || "(no branch)";
  const commits = st?.commits || [];
  const shownCommits = allCommits ? commits : commits.slice(0, 15);
  const nothing = !staged.length && !changed.length && !conflicts.length;

  return (
    <div className="flex h-full flex-col text-[11.5px]">
      {/* the branch and sync */}
      <div className="flex h-[32px] shrink-0 items-center gap-0.5 border-b border-border-300 px-2 dark:border-[#353535]">
        <Menu onOpenChange={(o) => o && setBq("")}>
          <MenuTrigger asChild>
            <button title="Switch branch" className="flex h-[24px] min-w-0 items-center gap-1.5 rounded-[5px] px-1.5 text-[12px] text-text-100 hover:bg-hover data-[state=open]:bg-hover">
              <I.BranchSm size={12} className="shrink-0 text-text-300" /><span className="truncate">{branchLabel}</span><I.ChevD size={10} className="shrink-0 text-text-400" />
            </button>
          </MenuTrigger>
          <MenuContent align="start" className="w-[290px]">
            <input autoFocus value={bq} onChange={(e) => setBq(e.target.value)} placeholder="Switch to a branch" onKeyDown={(e) => e.stopPropagation()}
              className="mb-1 w-full bg-transparent px-2 py-1.5 text-[12px] text-text-100 outline-none placeholder:text-text-500" />
            <MenuSep />
            <div className="max-h-[280px] overflow-y-auto">
              {locals.map((b) => (
                <MenuItem key={b.name} checked={b.current} shortcut={b.track || b.when} onSelect={() => !b.current && checkout(b.name)}>{b.name}</MenuItem>
              ))}
              {!locals.length && <div className="px-2 py-1.5 text-[11.5px] text-text-500">No branch matches.</div>}
              {remotes.length > 0 && <><MenuSep /><MenuLabel>Remote branches</MenuLabel></>}
              {remotes.slice(0, 80).map((b) => <MenuItem key={b.name} shortcut={b.when} onSelect={() => checkout(b.name, true)}>{b.name}</MenuItem>)}
            </div>
            <MenuSep />
            <MenuItem icon={<I.GitBranchPlus />} onSelect={() => { setCreating(true); setNewBranch(""); }}>Create branch…</MenuItem>
            {branches.some((b) => !b.current) && (
              <MenuSub>
                <MenuSubTrigger icon={<I.Trash />}>Delete branch</MenuSubTrigger>
                <MenuSubContent className="max-h-[300px] overflow-y-auto">
                  {branches.filter((b) => !b.current).map((b) => <MenuItem key={b.name} danger onSelect={() => delBranch(b.name)}>{b.name}</MenuItem>)}
                </MenuSubContent>
              </MenuSub>
            )}
          </MenuContent>
        </Menu>
        {!!st?.upstream && ((st.ahead || 0) > 0 || (st.behind || 0) > 0) && (
          <span className="shrink-0 tabular-nums text-[10.5px] text-text-400" title={`${st.ahead} to push, ${st.behind} to pull (${st.upstream})`}>
            {(st.ahead || 0) > 0 && `↑${st.ahead}`}{(st.ahead || 0) > 0 && (st.behind || 0) > 0 && " "}{(st.behind || 0) > 0 && `↓${st.behind}`}
          </span>
        )}
        <span className="flex-1" />
        {(busy || running) && <Spinner size={12} className="mr-1" />}
        <IconBtn tip="Fetch from the remote" disabled={running || !st?.remotes?.length} onClick={() => sync("fetch")}><I.FetchIcon size={13} /></IconBtn>
        <IconBtn tip={st?.upstream ? `Pull from ${st.upstream}` : "Pull (no upstream branch yet)"} disabled={running || !st?.upstream} onClick={() => sync("pull")}><I.PullIcon size={13} /></IconBtn>
        <IconBtn tip={st?.upstream ? `Push to ${st.upstream}` : st?.remotes?.length ? "Publish this branch" : "No remote to push to"} disabled={running || !st?.remotes?.length || st?.initial} onClick={() => sync("push")}>
          <I.PushIcon size={13} />
        </IconBtn>
        <Menu>
          <MenuTrigger asChild><button aria-label="More" className="flex h-[22px] w-[22px] items-center justify-center rounded-[5px] text-text-300 hover:bg-hover hover:text-text-000"><I.Dots size={13} /></button></MenuTrigger>
          <MenuContent align="end" className="min-w-[230px]">
            <MenuItem icon={<I.Sparkles />} disabled={nothing} onSelect={() => askEmilie("/review")}>Review the changes with Emilie</MenuItem>
            <MenuItem icon={<I.GitPullRequest />} disabled={st?.initial} onSelect={() => askEmilie("/pr")}>Write a pull request with Emilie</MenuItem>
            <MenuSep />
            <MenuItem icon={<I.Archive />} disabled={nothing || st?.initial} onSelect={() => stash("push")}>Stash all changes</MenuItem>
            <MenuItem icon={<I.Undo />} disabled={!st?.stash_count} onSelect={() => stash("pop")}>Pop the latest stash</MenuItem>
            <MenuSep />
            {st?.web && <MenuItem icon={<I.External />} onSelect={() => openExternal(st.web!)}>Open on GitHub</MenuItem>}
            <MenuItem icon={<I.FolderSm />} onSelect={() => openPath(root)}>Open the repository folder</MenuItem>
            <MenuItem icon={<I.Refresh />} onSelect={load}>Refresh</MenuItem>
          </MenuContent>
        </Menu>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2.5 pb-3">
        {err && <div className="mt-2 rounded-[7px] bg-danger-soft px-2.5 py-1.5 text-[11px] text-danger selectable">{err}</div>}
        {creating && (
          <div className="mt-2 flex items-center gap-1.5">
            <input autoFocus value={newBranch} onChange={(e) => setNewBranch(e.target.value)} placeholder="New branch name"
              onKeyDown={(e) => { if (e.key === "Enter") create(); if (e.key === "Escape") setCreating(false); }}
              className="h-[24px] min-w-0 flex-1 rounded-[6px] border border-border-300 bg-bg-200/40 px-2 text-[11.5px] text-text-100 outline-none focus:border-border-400 selectable" />
            <button className={btnPrimary} disabled={!newBranch.trim()} onClick={create}>Create</button>
            <button className={btnSm} onClick={() => setCreating(false)}>Cancel</button>
          </div>
        )}
        {st?.state && (
          <div className="mt-2 flex items-center gap-2 rounded-[7px] bg-warn-soft px-2.5 py-1.5 text-[11px] text-warn">
            <I.GitMerge size={13} className="shrink-0" />
            <span className="min-w-0 flex-1">{st.state[0].toUpperCase() + st.state.slice(1)}: {conflicts.length ? "resolve the conflicts, stage them, then commit." : "stage the result and commit to finish."}</span>
            {!!conflicts.length && <button className={btnSm} onClick={() => askEmilie(`Resolve the merge conflicts in: ${conflicts.map((c) => c.path).join(", ")}. Keep the intent of both sides, remove every conflict marker, then stage the files (do not commit).`)}>Ask Emilie</button>}
          </div>
        )}

        {/* the commit box */}
        <div className="mt-2.5 rounded-[8px] border border-border-300 bg-bg-200/40 focus-within:border-border-400">
          <textarea value={msg} onChange={(e) => setMsg(e.target.value)} rows={Math.min(8, Math.max(2, msg.split("\n").length))}
            placeholder={`Commit message (Ctrl+Enter to commit on ${st?.branch || "this branch"})`} spellCheck
            onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); commit(); } }}
            className="block w-full resize-none bg-transparent px-2.5 py-2 text-[12px] leading-[17px] text-text-100 outline-none placeholder:text-text-500 selectable" />
        </div>
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          <div className="flex">
            <button className={cn(btnPrimary, "rounded-r-none")} disabled={running || (nothing && !st?.initial)} onClick={() => commit()}
              title={staged.length ? `Commit the ${staged.length} staged file${staged.length > 1 ? "s" : ""}` : "Stage everything and commit"}>
              <I.Check size={12} />{staged.length || nothing ? "Commit" : "Commit all"}
            </button>
            <Menu>
              <MenuTrigger asChild>
                <button aria-label="More ways to commit" disabled={running} className={cn(btnPrimary, "rounded-l-none border-l border-black/15 px-1.5 dark:border-white/15")}><I.ChevD size={10} /></button>
              </MenuTrigger>
              <MenuContent align="start" className="min-w-[210px]">
                <MenuItem icon={<I.PushIcon />} disabled={nothing || !st?.remotes?.length} onSelect={() => commit({ push: true })}>Commit and push</MenuItem>
                <MenuItem icon={<I.Pencil />} disabled={st?.initial} onSelect={() => commit({ amend: true })}>Amend the last commit</MenuItem>
              </MenuContent>
            </Menu>
          </div>
          <button className={btnSm} disabled={nothing} onClick={() => askEmilie(("/commit " + msg).trim())}
            title="Emilie reads the changes, writes the message in the style of your recent commits and commits (never pushes)">
            <I.Sparkles size={11} />Commit with Emilie
          </button>
        </div>

        {(running || job?.error) && (
          <Card className="mt-2.5">
            <div className="flex items-center gap-2 px-3 py-[5px] text-[11px]">
              <span className={cn("min-w-0 flex-1 truncate", job?.error ? "text-danger" : "text-text-300")}>
                {job?.error ? `git ${jobKind.replace("commit-push", "commit and push")} failed` : `Running git ${jobKind.replace("commit-push", "commit and push")}…`}
              </span>
              {job?.running && <button className={btnSm} onClick={() => post("/api/job/stop", { id: jobId })}>Stop</button>}
              {!running && <IconBtn tip="Close" onClick={() => setJobId(null)}><I.X size={11} /></IconBtn>}
            </div>
            <Output lines={lines} className="max-h-[180px] border-t border-border-200" />
          </Card>
        )}

        {!!conflicts.length && (
          <>
            <Heading title="Merge conflicts" note={conflicts.length} open={sec.conflicts} onToggle={() => toggleSec("conflicts")} />
            {sec.conflicts && (
              <Card>
                {conflicts.map((f, i) => {
                  const [name, dir] = splitPath(f.path);
                  return (
                    <div key={f.path} className={cn(rowCls, "h-[24px] pl-2.5", i > 0 && "border-t border-border-200")} title={f.path}>
                      <I.GitMerge size={11} className="shrink-0 text-danger" />
                      <span className="min-w-0 shrink truncate text-danger">{name}</span>
                      <span className="min-w-0 flex-1 truncate text-[10px] text-text-500">{dir}</span>
                      <RowBtn tip="Open the file" onClick={() => useStore.getState().openFile(join(root, f.path))}><I.External size={11} /></RowBtn>
                      <RowBtn tip="Ask Emilie to resolve it" onClick={() => askEmilie(`Resolve the merge conflict in ${f.path}: keep the intent of both sides, remove the conflict markers, then stage the file (do not commit).`)}><I.Sparkles size={11} /></RowBtn>
                      <RowBtn tip="Mark as resolved (stage)" onClick={() => stage([f.path])}><I.Plus size={12} /></RowBtn>
                    </div>
                  );
                })}
              </Card>
            )}
          </>
        )}

        {!!staged.length && (
          <>
            <Heading title="Staged changes" note={staged.length} open={sec.staged} onToggle={() => toggleSec("staged")}
              right={<IconBtn tip="Unstage all" disabled={!!busy} onClick={() => unstage()}><I.Minus size={12} /></IconBtn>} />
            {sec.staged && (
              <Card>
                {staged.map((f, i) => (
                  <FileRow key={f.path} f={f} first={i === 0} open={shown === "staged:" + f.path} diff={shown === "staged:" + f.path ? diff : null}
                    onToggle={() => setShown(shown === "staged:" + f.path ? "" : "staged:" + f.path)}>
                    <RowBtn tip="Open the file" onClick={() => useStore.getState().openFile(join(root, f.path))}><I.External size={11} /></RowBtn>
                    <RowBtn tip="Unstage" onClick={() => unstage([f.path])}><I.Minus size={12} /></RowBtn>
                  </FileRow>
                ))}
              </Card>
            )}
          </>
        )}

        <Heading title="Changes" note={changed.length || ""} open={sec.changed} onToggle={() => toggleSec("changed")}
          right={changed.length > 0 && (
            <>
              <IconBtn tip="Discard all changes" danger disabled={!!busy} onClick={() => discard(changed)}><I.Undo size={12} /></IconBtn>
              <IconBtn tip="Stage all changes" disabled={!!busy} onClick={() => stage()}><I.Plus size={13} /></IconBtn>
            </>
          )} />
        {sec.changed && !changed.length && <Hint>{staged.length ? "Everything is staged." : "No changes. The working tree matches the last commit."}</Hint>}
        {sec.changed && !!changed.length && (
          <Card>
            {changed.map((f, i) => (
              <FileRow key={f.path} f={f} first={i === 0} open={shown === "changed:" + f.path} diff={shown === "changed:" + f.path ? diff : null}
                onToggle={() => setShown(shown === "changed:" + f.path ? "" : "changed:" + f.path)}>
                {f.status !== "D" && <RowBtn tip="Open the file" onClick={() => useStore.getState().openFile(join(root, f.path))}><I.External size={11} /></RowBtn>}
                <RowBtn tip={f.status === "U" ? "Delete this new file" : "Discard changes"} danger onClick={() => discard([f])}><I.Undo size={11} /></RowBtn>
                <RowBtn tip="Stage" onClick={() => stage([f.path])}><I.Plus size={12} /></RowBtn>
              </FileRow>
            ))}
          </Card>
        )}

        {!!st?.stashes?.length && (
          <>
            <Heading title="Stashes" note={st.stashes.length} open={sec.stashes} onToggle={() => toggleSec("stashes")} />
            {sec.stashes && (
              <Card>
                {st.stashes.map((s, i) => (
                  <div key={s.ref} className={cn(rowCls, "py-[5px]", i > 0 && "border-t border-border-200")}>
                    <I.Archive size={11} className="shrink-0 text-text-400" />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-text-100" title={s.subject}>{s.subject}</div>
                      <div className="truncate text-[10px] text-text-500">{s.ref} · {s.when}</div>
                    </div>
                    <RowBtn tip="Apply (keep the stash)" onClick={() => stash("apply", s.ref)}><I.Check size={12} /></RowBtn>
                    <RowBtn tip="Pop (apply and drop)" onClick={() => stash("pop", s.ref)}><I.Undo size={11} /></RowBtn>
                    <RowBtn tip="Drop" danger onClick={() => stash("drop", s.ref)}><I.Trash size={11} /></RowBtn>
                  </div>
                ))}
              </Card>
            )}
          </>
        )}

        <Heading title="History" note={commits.length ? commits.length : ""} open={sec.history} onToggle={() => toggleSec("history")} />
        {sec.history && !commits.length && <Hint>{st?.initial ? "No commits yet. Your first commit starts the history." : "No commits."}</Hint>}
        {sec.history && !!commits.length && (
          <Card>
            {shownCommits.map((c, i) => {
              const on = openCommit === c.hash;
              const ci = info[c.hash];
              return (
                <div key={c.hash} className={cn(i > 0 && "border-t border-border-200")}>
                  <div role="button" onClick={() => toggleCommit(c.hash)} className={cn(rowCls, "items-start py-[5px]")}>
                    <span className="mt-[3px]"><Chevron on={on} /></span>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-text-100" title={c.subject}>{c.subject}</div>
                      <div className="flex min-w-0 items-center gap-1 text-[10px] text-text-500">
                        <span className="shrink-0 font-mono">{c.hash}</span><span className="truncate">· {c.author} · {c.when}</span>
                      </div>
                    </div>
                    {c.refs.slice(0, 2).map((r) => (
                      <span key={r} className={cn("mt-[1px] max-w-[110px] shrink-0 truncate rounded-full px-1.5 text-[9.5px] leading-[15px]",
                        r.startsWith("HEAD") ? "bg-accent-soft text-accent" : r.startsWith("tag:") ? "bg-warn-soft text-warn" : "bg-bg-400 text-text-300")}
                        title={r}>{r.replace(/^HEAD -> /, "").replace(/^tag: /, "")}</span>
                    ))}
                  </div>
                  {on && (
                    <div className="border-t border-border-200 bg-bg-100/60 pb-2">
                      {ci === "loading" || !ci ? <div className="px-3 py-2"><Spinner size={12} /></div>
                        : typeof ci === "string" ? <div className="px-3 py-2 text-[11px] text-danger">{ci}</div> : (
                          <>
                            {ci.message.includes("\n") && <pre className="whitespace-pre-wrap break-words px-3 pt-2 font-sans text-[11px] leading-[15px] text-text-300 selectable">{ci.message.split("\n").slice(1).join("\n").trim()}</pre>}
                            <div className="px-3 pt-1.5 text-[10.5px] text-text-500">{ci.author} &lt;{ci.email}&gt; · {ci.date}</div>
                            <div className="mt-1.5">
                              {ci.files.slice(0, 60).map((f) => {
                                const [name, dir] = splitPath(f.path);
                                return (
                                  <div key={f.path} role="button" onClick={() => f.status !== "D" && useStore.getState().openFile(join(root, f.path))}
                                    className="group flex min-w-0 items-center gap-1.5 py-[2px] pl-[26px] pr-3 text-[11px] hover:bg-hover/50" title={f.orig ? `${f.orig} → ${f.path}` : f.path}>
                                    <span className={cn("w-[10px] shrink-0 font-mono text-[10px]", tone(f.status))}>{f.status}</span>
                                    <span className="min-w-0 shrink truncate text-text-100">{name}</span>
                                    <span className="min-w-0 flex-1 truncate text-[10px] text-text-500">{dir}</span>
                                    {f.added > 0 && <span className="shrink-0 tabular-nums text-[10px] text-ok">+{f.added}</span>}
                                    {f.removed > 0 && <span className="shrink-0 tabular-nums text-[10px] text-danger">−{f.removed}</span>}
                                  </div>
                                );
                              })}
                              {ci.files.length > 60 && <div className="py-[2px] pl-[26px] text-[10.5px] text-text-500">and {ci.files.length - 60} more files</div>}
                            </div>
                            <div className="flex flex-wrap gap-1.5 px-3 pt-2">
                              <button className={btnSm} onClick={() => showInChanges(c.hash)}><I.FileDiff size={11} />Show diff</button>
                              <button className={btnSm} onClick={() => copy(c.full, "Commit hash copied")}><I.Copy size={11} />Copy hash</button>
                              {st?.web && <button className={btnSm} onClick={() => openExternal(`${st.web}/commit/${c.full}`)}><I.External size={11} />GitHub</button>}
                            </div>
                          </>
                        )}
                    </div>
                  )}
                </div>
              );
            })}
            {commits.length > 15 && (
              <button onClick={() => setAllCommits(!allCommits)} className="w-full border-t border-border-200 py-[5px] text-center text-[10.5px] text-text-400 hover:text-text-100">
                {allCommits ? "Show fewer" : `Show ${commits.length - 15} more`}
              </button>
            )}
          </Card>
        )}
      </div>
    </div>
  );
}

function FileRow({ f, first, open, diff, onToggle, children }: {
  f: GFile; first: boolean; open: boolean; diff: DiffState | null; onToggle: () => void; children: React.ReactNode;
}) {
  const [name, dir] = splitPath(f.path);
  return (
    <div className={cn(!first && "border-t border-border-200")}>
      <div role="button" onClick={onToggle} title={f.orig ? `${f.orig} → ${f.path}` : f.path} className={cn(rowCls, "h-[24px] gap-1.5 pl-2 pr-2.5")}>
        <Chevron on={open} />
        <span className={cn("min-w-0 shrink truncate", tone(f.status), f.status === "D" && "line-through decoration-1")}>{name}</span>
        <span className="min-w-0 flex-1 truncate text-[10px] text-text-500">{f.orig ? `${splitPath(f.orig)[0]} → ` : ""}{dir}</span>
        {children}
        <span className={cn("w-[11px] shrink-0 text-center font-mono text-[10.5px]", tone(f.status))} title={WORD[f.status] || f.status}>{f.status}</span>
      </div>
      {open && (
        <div className="border-t border-border-200 bg-bg-100">
          {(!diff || diff === "loading") && <div className="px-3 py-2"><Spinner size={12} /></div>}
          {diff && diff !== "loading" && "error" in diff && <div className="px-3 py-2 text-[11px] text-danger">{diff.error}</div>}
          {diff && diff !== "loading" && !("error" in diff) && (diff.text ? <DiffView diff={diff} file={f.path} />
            : <div className="px-3 py-2 text-[11px] text-text-500">{diff.nodiff || "No changes to show"}</div>)}
        </div>
      )}
    </div>
  );
}
