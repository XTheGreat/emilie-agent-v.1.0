// Search (SearchPalette.tsx), What's new, trust a folder, pick a folder, rename, confirm, keyboard shortcuts, help.
import { useEffect, useMemo, useRef, useState } from "react";
import { SearchPalette } from "./SearchPalette";
import { currentLive, useStore } from "@/lib/store";
import { get as apiGet, post } from "@/lib/api";
import { ArrowLeft, FolderIcon, FolderPlus, Shield } from "./icons";
import { insertIntoComposer } from "./Composer";
import { Button, Input, Kbd, Modal, Segmented, Spinner } from "./ui";

export function Dialogs() {
  const d = useStore((s) => s.dialog);
  const close = () => useStore.setState({ dialog: null });
  if (!d) return null;
  switch (d.kind) {
    case "search": return <SearchPalette onClose={close} tab={d.tab} q={d.q} />;
    case "whatsnew": return <WhatsNewDialog onClose={close} />;
    case "shortcuts": return <ShortcutsDialog onClose={close} />;
    case "help": return <HelpDialog onClose={close} />;
    case "trust": return <TrustDialog path={d.path} resolve={d.resolve} />;
    case "folder": return <FolderBrowser title={d.title} resolve={d.resolve} />;
    case "rename": return <RenameDialog id={d.id} cwd={d.cwd} title={d.title} onClose={close} />;
    case "connector": return <ConnectorDialog d={d} onClose={close} />;
    case "confirm":
      return (
        <Modal open onOpenChange={(o) => !o && d.resolve(false)} title={d.title} hideClose>
          <div className="px-6 pt-2 pb-4 text-[12.5px] leading-relaxed text-text-300">{d.body}</div>
          <div className="flex justify-end gap-3 px-5 pb-4">
            <button className="h-[28px] px-3 rounded-[6px] text-[12px] font-medium text-text-200 bg-bg-400 hover:bg-active transition-colors" onClick={() => d.resolve(false)}>Cancel</button>
            <button className={`h-[28px] px-3.5 rounded-[6px] text-[12px] font-medium transition-colors ${d.danger ? "bg-danger/10 border border-danger text-danger hover:bg-danger/20" : "bg-text-000 text-bg-100 hover:opacity-90"}`} autoFocus onClick={() => d.resolve(true)}>{d.ok || "OK"}</button>
          </div>
        </Modal>
      );
    default:
      return null;
  }
}

/** One connector (MCP server) of the session, as in Claude: its state, and Reconnect / Connect (restarts just that server). */
function ConnectorDialog({ d, onClose }: { d: Extract<NonNullable<ReturnType<typeof useStore.getState>["dialog"]>, { kind: "connector" }>; onClose: () => void }) {
  const toast = useStore((s) => s.toast);
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState({ status: d.status, error: d.error, tools: d.tools });
  const reconnect = async () => {
    setBusy(true);
    try {
      let list: any[] = await post("/api/session/mcp", { wid: d.wid, reconnect: d.name });
      // a server that has to download first (npx) can still be starting: look again for up to ~20 s
      for (let i = 0; i < 10 && list.find((x) => x.name === d.name)?.status === "starting"; i++) {
        setNow({ status: "starting", error: "", tools: 0 });
        await new Promise((r) => setTimeout(r, 2000));
        list = await post("/api/session/mcp", { wid: d.wid });
      }
      d.done(list);
      const me = list.find((x) => x.name === d.name);
      if (me) setNow({ status: me.status, error: me.error, tools: me.tools?.length });
      else toast(`${d.name} is not in the configuration any more.`, "error");
    } catch (e: any) {
      toast(e.message, "error");
    }
    setBusy(false);
  };
  const ready = now.status === "ready";
  const text = ready ? `Connected${now.tools ? ` · ${now.tools} tools` : ""}`
    : now.status === "starting" ? "Connecting…" : now.error ? now.error : "Not connected";
  return (
    <Modal open onOpenChange={(o) => !o && onClose()} title={d.name} wide>
      <div className="flex items-start justify-between gap-4 px-5 pb-5 pt-2">
        <div className="min-w-0 text-[12px] text-text-300">
          <div className={ready ? "text-ok" : now.status === "starting" ? "text-text-300" : "text-warn"}>{text}</div>
        </div>
        <div className="flex shrink-0 gap-2">
          <Button size="sm" variant="ghost" disabled={busy} onClick={reconnect}>{busy ? "…" : "Reconnect"}</Button>
          {!ready && <Button size="sm" variant="primary" disabled={busy} onClick={reconnect}>Connect</Button>}
        </div>
      </div>
    </Modal>
  );
}

function WhatsNewDialog({ onClose }: { onClose: () => void }) {
  const [data, setData] = useState<{ version: string; commits: { hash: string; date: string; subject: string }[] } | null>(null);
  useEffect(() => {
    apiGet("/api/whatsnew").then(setData).catch(() => setData({ version: "?", commits: [] }));
  }, []);
  return (
    <Modal open onOpenChange={(o) => !o && onClose()} title="What's new" description={data ? `Emilie ${data.version} · latest changes in this copy` : undefined} wide>
      <div className="max-h-[60vh] overflow-y-auto px-6 pt-2 pb-5">
        {!data && <Spinner />}
        {data && !data.commits.length && <div className="text-[12px] text-text-500">No change history found (not a git checkout).</div>}
        <ul className="flex flex-col">
          {data?.commits.map((c) => (
            <li key={c.hash} className="flex gap-3 border-b border-border-200 py-2.5 last:border-0">
              <span className="w-[86px] shrink-0 text-[11.5px] text-text-500">{c.date}</span>
              <span className="min-w-0 flex-1 text-[12px] text-text-200 selectable">{c.subject}</span>
            </li>
          ))}
        </ul>
      </div>
    </Modal>
  );
}

function TrustDialog({ path, resolve }: { path: string; resolve: (ok: boolean) => void }) {
  return (
    <Modal open onOpenChange={(o) => !o && resolve(false)} title="Do you trust the files in this folder?" hideClose>
      <div className="px-6 pt-2 pb-5 text-[12.5px] leading-relaxed text-text-300">
        <div className="mb-3 flex items-center gap-2 rounded-lg bg-bg-200 px-3 py-2 font-mono text-[11.5px] text-text-100 break-all">
          <Shield size={15} className="shrink-0 text-accent" />{path}
        </div>
        Emilie will read files here and, with your permission, change them and run commands. The folder's own
        instructions (EMILIE.md), skills and MCP servers are loaded too, so only trust folders you know.
      </div>
      <div className="flex justify-end gap-2 border-t border-border-200 px-5 py-3">
        <Button variant="ghost" onClick={() => resolve(false)}>Cancel</Button>
        <Button variant="primary" autoFocus onClick={() => resolve(true)}>Trust folder</Button>
      </div>
    </Modal>
  );
}

function FolderBrowser({ title, resolve }: { title?: string; resolve: (p: string | null) => void }) {
  const [path, setPath] = useState("");
  const [data, setData] = useState<{ path: string; parent: string | null; dirs: { name: string; path: string }[] } | null>(null);
  const [err, setErr] = useState("");
  const [newName, setNewName] = useState<string | null>(null);
  const load = (p: string) => {
    setErr("");
    apiGet("/api/fs/dirs", { path: p }).then((d) => { setData(d); setPath(d.path); }).catch((e) => setErr(e.message));
  };
  useEffect(() => load(""), []);
  const mk = async () => {
    if (!newName?.trim() || !path) return;
    try {
      const r = await post("/api/fs/mkdir", { path: path.replace(/[\\/]+$/, "") + "\\" + newName.trim() });
      setNewName(null);
      load(r.path);
    } catch (e: any) {
      setErr(e.message);
    }
  };
  return (
    <Modal open onOpenChange={(o) => !o && resolve(null)} title={title || "Choose a folder"} wide>
      <div className="px-6 pt-2">
        <div className="flex items-center gap-2">
          <Button size="sm" variant="ghost" disabled={!path} onClick={() => load(data?.parent || "")}><ArrowLeft size={14} />Up</Button>
          <Input value={path} onChange={(e) => setPath(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load(path)} placeholder="Type a path and press Enter" className="h-8 font-mono text-[11.5px]" />
        </div>
        {err && <div className="mt-2 text-[11.5px] text-danger">{err}</div>}
        <div className="mt-3 h-[44vh] overflow-y-auto rounded-lg border border-border-300 bg-bg-100 p-1">
          {!data && <div className="p-3"><Spinner /></div>}
          {data?.dirs.map((d) => (
            <div key={d.path} onDoubleClick={() => load(d.path)} onClick={() => load(d.path)}
              className="flex cursor-default items-center gap-2 rounded-lg px-2.5 py-1.5 text-[12px] text-text-200 hover:bg-hover">
              <FolderIcon size={15} className="text-text-400" />{d.name}
            </div>
          ))}
          {data && !data.dirs.length && <div className="p-3 text-[12px] text-text-500">No sub-folders.</div>}
        </div>
      </div>
      <div className="flex items-center gap-2 px-5 py-3">
        {newName === null ? (
          <Button variant="ghost" size="sm" disabled={!path} onClick={() => setNewName("")}><FolderPlus size={14} />New folder</Button>
        ) : (
          <div className="flex items-center gap-2">
            <Input autoFocus value={newName} onChange={(e) => setNewName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && mk()} placeholder="Folder name" className="h-8 w-48" />
            <Button size="sm" onClick={mk}>Create</Button>
          </div>
        )}
        <div className="flex-1" />
        <Button variant="ghost" onClick={() => resolve(null)}>Cancel</Button>
        <Button variant="primary" disabled={!path} onClick={() => resolve(path)}>Use this folder</Button>
      </div>
    </Modal>
  );
}

function RenameDialog({ id, cwd, title, onClose }: { id: string; cwd: string; title: string; onClose: () => void }) {
  const [v, setV] = useState(title);
  const save = async () => {
    try {
      await post("/api/sessions/rename", { id, cwd, title: v });
      useStore.getState().refreshSessions();
      const l = Object.values(useStore.getState().lives).find((x) => x.sid === id);
      if (l) useStore.setState({ lives: { ...useStore.getState().lives, [l.wid]: { ...l, title: v } } });
      onClose();
    } catch (e: any) {
      useStore.getState().toast(e.message, "error");
    }
  };
  return (
    <Modal open onOpenChange={(o) => !o && onClose()} title="Rename session">
      <div className="px-6 pt-3 pb-4"><Input autoFocus value={v} onChange={(e) => setV(e.target.value)} onKeyDown={(e) => e.key === "Enter" && save()} /></div>
      <div className="flex justify-end gap-2 border-t border-border-200 px-5 py-3">
        <Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button variant="primary" onClick={save}>Save</Button>
      </div>
    </Modal>
  );
}

const KEYS: [string, string][] = [
  ["Enter", "Send"], ["Shift+Enter", "New line"], ["Esc", "Stop Emilie"], ["Shift+Tab", "Switch mode: ask → trust → plan"],
  ["/", "Commands and skills"], ["@", "Mention a file"], ["↑", "Previous message"], ["Ctrl+N", "New session"],
  ["Ctrl+K", "Search sessions"], ["Ctrl+,", "Settings"], ["Ctrl+B", "Toggle the sidebar"], ["Ctrl+J", "Terminal"],
  ["Ctrl+Shift+E", "Files"], ["Ctrl+Shift+I", "Model and effort"], ["Alt+← / Alt+→", "Back / forward"],
  ["Alt+V", "Video call: start / end"], ["Ctrl+= / Ctrl+-", "Zoom"], ["F12", "Developer tools (desktop app)"],
];

function ShortcutsDialog({ onClose }: { onClose: () => void }) {
  return (
    <Modal open onOpenChange={(o) => !o && onClose()} title="Keyboard shortcuts">
      <ShortcutList />
    </Modal>
  );
}

function ShortcutList() {
  return (
    <div className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 px-6 pt-3 pb-6 text-[12px]">
      {KEYS.map(([k, d]) => (
        <div key={k} className="contents"><div><Kbd>{k}</Kbd></div><div className="text-text-300">{d}</div></div>
      ))}
    </div>
  );
}

const KIND_TITLE: Record<string, string> = { builtin: "Commands", skill: "Skills", command: "Your commands" };
const NO_COMMANDS: never[] = [];                 // one stable empty list (a new [] per render would loop the store hook)

/** /help: every command and what it does (a click puts it in the message box), and the keyboard shortcuts. */
function HelpDialog({ onClose }: { onClose: () => void }) {
  const commands = useStore((s) => {
    const live = currentLive(s);
    return (live?.commands?.length ? live.commands : s.state?.commands) || NO_COMMANDS;
  });
  const [tab, setTab] = useState("commands");
  const [q, setQ] = useState("");
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => { if (tab === "commands") setTimeout(() => input.current?.focus(), 30); }, [tab]);
  const groups = useMemo(() => {
    const ql = q.trim().toLowerCase().replace(/^\//, "");
    const hit = commands.filter((c) => !ql || c.name.toLowerCase().includes(ql) || c.desc.toLowerCase().includes(ql));
    return Object.keys(KIND_TITLE).map((k) => [k, hit.filter((c) => (c.kind || "builtin") === k)] as const).filter(([, l]) => l.length);
  }, [commands, q]);
  const use = (name: string) => {
    onClose();
    insertIntoComposer(name + " ");
  };
  return (
    <Modal open onOpenChange={(o) => !o && onClose()} title="Help" wide
      description="Commands start with / in the message box. The ones with a screen in the app open it.">
      <div className="flex items-center gap-2 px-5 pt-2 pb-2">
        <Segmented value={tab} onChange={setTab} options={[{ value: "commands", label: "Commands" }, { value: "keys", label: "Keyboard shortcuts" }]} />
        {tab === "commands" && <Input ref={input} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search commands" className="ml-auto max-w-[220px]" />}
      </div>
      {tab === "keys" ? <ShortcutList /> : (
        <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-4" style={{ maxHeight: "min(58vh, 520px)" }}>
          {!groups.length && <div className="px-2 py-6 text-center text-[12px] text-text-400">No command matches “{q.trim()}”</div>}
          {groups.map(([k, list]) => (
            <div key={k} className="mb-2">
              <div className="px-2 pb-1 pt-2 text-[10.5px] font-medium uppercase tracking-wide text-text-500">{KIND_TITLE[k]}</div>
              {list.map((c) => (
                <button key={c.name} onClick={() => use(c.name)}
                  className="flex w-full items-baseline gap-3 rounded-[6px] px-2 py-[5px] text-left hover:bg-hover">
                  <span className="w-[118px] shrink-0 truncate font-mono text-[11.5px] text-text-100">{c.name}</span>
                  <span className="min-w-0 flex-1 text-[11.5px] leading-[16px] text-text-400">{c.desc}</span>
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
    </Modal>
  );
}
