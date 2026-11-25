// App state (zustand). Every event from the server goes through onEvent() and updates one session ("live").
import { create } from "zustand";
import { useShallow } from "zustand/react/shallow";
import { get as apiGet, post } from "./api";
import { bridge, notify } from "./desktop";
import type { AppState, Folder, Item, Live, ModelRow, Request, Section, SessionMeta, Status, View } from "./types";
import { type Attachment, basename, uid } from "./util";
import { runInApp } from "./slash";

export type PaneKind = "files" | "terminal" | "browser" | "diff" | "tasks" | "checkpoints";
export interface PaneTab { key: string; kind: PaneKind | "file"; path?: string; title: string }

export type SearchTab = "all" | "artifacts" | "chats" | "code" | "projects" | "scheduled";
export type Dialog =
  | { kind: "search"; tab?: SearchTab; q?: string }
  | { kind: "whatsnew" }
  | { kind: "shortcuts" }
  | { kind: "help" }
  | { kind: "trust"; path: string; resolve: (ok: boolean) => void }
  | { kind: "folder"; title?: string; resolve: (p: string | null) => void }
  | { kind: "rename"; id: string; cwd: string; title: string }
  | { kind: "connector"; wid: string; name: string; status: string; error?: string; tools?: number; done: (list: any[]) => void }
  | { kind: "confirm"; title: string; body: string; danger?: boolean; ok?: string; resolve: (ok: boolean) => void };

export interface Toast { id: string; text: string; kind: "info" | "error" | "ok" }
export interface TermRun { tid: string; cwd: string; command: string; lines: string[]; code: number | null; at: number }

export interface HomeOpts { cwd: string | null; chat: boolean; worktree: boolean; mode: string; model: string | null; effort: string | null }

export type LiveX = Live & { turnTokens: number; loaded: boolean };

export interface Store {
  boot: "loading" | "ready" | "error";
  bootError: string;
  connected: boolean;
  state: AppState | null;
  settings: Record<string, any>;
  schema: Section[] | null;
  sessions: SessionMeta[];
  folders: Folder[];
  scratch: string;
  lives: Record<string, LiveX>;
  view: View;
  back: View[];
  fwd: View[];
  opening: string | null;
  pane: PaneKind | null;
  paneTabs: PaneTab[];
  paneActive: string | null;
  paneMax: boolean;
  browserGo: { url: string; n: number } | null;       // the agent asked the Browser panel to open an address
  envFloat: boolean;                 // the Environment panel shown floating (while a viewer tab is open)
  settingsOpen: string | null;
  dialog: Dialog | null;
  home: HomeOpts;
  toasts: Toast[];
  models: { rows: ModelRow[]; loading: boolean; error?: string | null; loaded: boolean };
  terms: TermRun[];
  doctor: any[];
  drafts: Record<string, string>;

  init(): Promise<void>;
  refreshState(): Promise<void>;
  refreshSessions(): Promise<void>;
  loadSettings(): Promise<void>;
  setSetting(key: string, value: any): Promise<boolean>;
  navigate(v: View, replace?: boolean): void;
  goBack(): void;
  goForward(): void;
  setHome(p: Partial<HomeOpts>): void;
  openSession(meta: SessionMeta): Promise<void>;
  newSession(text: string, atts: Attachment[], pastes: { n: number; text: string }[]): Promise<string | null>;
  startWith(what: "talk" | "call"): Promise<void>;     // from the New session page: start a session, then talk / call
  setTalk(wid: string, on: boolean): void;
  setCall(wid: string, on: boolean): void;
  ensureTrusted(path: string): Promise<boolean>;
  pickFolder(title?: string): Promise<string | null>;
  confirm(title: string, body: string, opts?: { danger?: boolean; ok?: string }): Promise<boolean>;
  ensureLoaded(wid: string): Promise<void>;
  send(wid: string, text: string, atts: Attachment[], pastes: { n: number; text: string }[]): Promise<void>;
  stop(wid: string): void;
  answer(wid: string, id: string, value: any): void;
  setOpt(wid: string, opts: Record<string, any>): Promise<void>;
  closeSession(wid: string): Promise<void>;
  restartSession(wid: string): Promise<void>;
  deleteSession(meta: SessionMeta): Promise<void>;
  loadModels(refresh?: boolean): Promise<void>;
  toast(text: string, kind?: Toast["kind"]): void;
  setPane(p: PaneKind | null): void;
  openFile(path: string): void;
  closeTab(key: string): void;
  activateTab(key: string): void;
  onEvent(ev: any): void;
}

const LIVE = (wid: string, p: Partial<LiveX> = {}): LiveX => ({
  wid, sid: null, cwd: "", title: "", items: [], status: {}, commands: [], busy: false, working: null, request: null,
  todos: [], stale: false, closed: false, turnTokens: 0, loaded: false, ...p,
});

let sessionsTimer: number | undefined;
const voiceQuiet: Record<string, number> = {};

export const useStore = create<Store>()((set, get) => {
  // the panels (changes, browser, files, terminal) belong to the session on screen: leave it and they close
  const closePanes = () => { if (get().paneTabs.length || get().pane) set({ pane: null, paneActive: null, paneTabs: [], paneMax: false }); };
  const sessionOf = (v: View) => (v.kind === "session" ? v.wid : "");
  const closePanesIfLeft = (from: View, to: View) => { if (sessionOf(from) !== sessionOf(to) && (sessionOf(from) || to.kind === "home")) closePanes(); };

  const patch = (wid: string, fn: (l: LiveX) => LiveX) => {
    const l = get().lives[wid];
    if (!l) return;
    set({ lives: { ...get().lives, [wid]: fn(l) } });
  };
  const soonSessions = () => {
    clearTimeout(sessionsTimer);
    sessionsTimer = window.setTimeout(() => get().refreshSessions(), 400);
  };
  const addLive = (r: any): string => {
    applyEvents();                       // what arrived before this answer goes first (as it did before events waited for a frame)
    const wid = r.wid as string;
    const snap = r.snapshot || {};
    const live = LIVE(wid, {
      sid: r.session_id, cwd: r.cwd || "", title: r.title || r.status?.title || "", status: r.status || {},
      commands: r.commands || [], items: snap.items || [], todos: snap.todos || r.status?.todos || [],
      busy: !!(snap.busy ?? r.status?.busy), request: snap.request || r.request || null, stale: !!r.stale,
      working: snap.busy ? { since: Date.now(), tokens: 0, streaming: !!snap.stream_id } : null, loaded: !!r.snapshot,
    });
    set({ lives: { ...get().lives, [wid]: live } });
    return wid;
  };
  const enabled = (k: string, dflt = true) => (get().settings[k] ?? dflt) !== false;

  return {
    boot: "loading", bootError: "", connected: false, state: null, settings: {}, schema: null, sessions: [], folders: [],
    scratch: "", lives: {}, view: { kind: "home" }, back: [], fwd: [], opening: null, pane: null, paneTabs: [], paneActive: null, paneMax: false, browserGo: null, envFloat: false, settingsOpen: null,
    dialog: null, home: { cwd: null, chat: false, worktree: false, mode: "ask", model: null, effort: null },
    toasts: [], models: { rows: [], loading: false, loaded: false }, terms: [], doctor: [], drafts: {},

    async init() {
      try {
        const [state, st] = await Promise.all([apiGet<AppState & { workers: any[] }>("/api/state"),
          apiGet<{ values: any; schema: Section[] }>("/api/settings")]);
        const v = st.values || {};
        const firstFolder = (state.folders || []).find((f) => f.exists)?.path || null;
        set({
          state, settings: v, schema: st.schema, boot: "ready",
          home: { cwd: firstFolder, chat: false, worktree: false, mode: v.desktop_mode || "ask", model: null, effort: null },
        });
        for (const w of state.workers || []) if (w.session_id) addLive({ ...w, snapshot: null });
        await get().refreshSessions();
      } catch (e: any) {
        set({ boot: "error", bootError: e?.message || String(e) });
      }
    },

    async refreshState() {
      try {
        const state = await apiGet<AppState>("/api/state");
        set({ state });
      } catch { /* the stream reconnect will retry */ }
    },

    async refreshSessions() {
      try {
        const r = await apiGet<{ sessions: SessionMeta[]; folders: Folder[]; scratch: string }>("/api/sessions");
        set({ sessions: r.sessions, folders: r.folders, scratch: r.scratch });
        const h = get().home;
        if (!h.cwd && !h.chat) {
          const f = r.folders.find((x) => x.exists);
          if (f) set({ home: { ...h, cwd: f.path } });
        }
      } catch { /* ignore */ }
    },

    async loadSettings() {
      const st = await apiGet<{ values: any; schema: Section[] }>("/api/settings");
      set({ settings: st.values, schema: st.schema });
    },

    async setSetting(key, value) {
      const prev = get().settings;
      set({ settings: { ...prev, [key]: value } });
      try {
        const r = await post<{ values: any; errors: Record<string, string> }>("/api/settings", { key, value });
        set({ settings: r.values });
        if (r.errors && r.errors[key]) {
          get().toast(r.errors[key], "error");
          return false;
        }
        return true;
      } catch (e: any) {
        set({ settings: prev });
        get().toast(e.message, "error");
        return false;
      }
    },

    navigate(v, replace = false) {
      const cur = get().view;
      if (JSON.stringify(cur) === JSON.stringify(v)) return;
      set({ view: v, back: replace ? get().back : [...get().back.slice(-50), cur], fwd: [] });
      closePanesIfLeft(cur, v);
      if (v.kind === "session") get().ensureLoaded(v.wid);
    },
    goBack() {
      const b = get().back;
      if (!b.length) return;
      const v = b[b.length - 1];
      closePanesIfLeft(get().view, v);
      set({ view: v, back: b.slice(0, -1), fwd: [get().view, ...get().fwd] });
      if (v.kind === "session" && !get().lives[v.wid]) set({ view: { kind: "home" } });
    },
    goForward() {
      const f = get().fwd;
      if (!f.length) return;
      const v = f[0];
      closePanesIfLeft(get().view, v);
      set({ view: v, fwd: f.slice(1), back: [...get().back, get().view] });
      if (v.kind === "session" && !get().lives[v.wid]) set({ view: { kind: "home" } });
    },
    setHome(p) {
      set({ home: { ...get().home, ...p } });
    },

    async ensureTrusted(path) {
      if (!path) return true;
      const sc = get().scratch;
      if (sc && path.toLowerCase() === sc.toLowerCase()) return true;
      try {
        const r = await apiGet<{ trusted: boolean; exists?: boolean }>("/api/trust", { path });
        if (r.exists === false) {                       // moved or deleted: nothing to trust, say so plainly
          const name = path.split(/[\\/]/).filter(Boolean).pop() || path;
          get().toast(`The folder "${name}" no longer exists. Put it back to continue, or delete its sessions.`, "error");
          return false;
        }
        if (r.trusted) return true;
      } catch { /* ask anyway */ }
      const ok = await new Promise<boolean>((resolve) => set({ dialog: { kind: "trust", path, resolve } }));
      set({ dialog: null });
      if (!ok) return false;
      try {
        await post("/api/trust", { path });
      } catch (e: any) {
        get().toast(e.message, "error");
        return false;
      }
      return true;
    },

    async pickFolder(title) {
      if (bridge) return bridge.pickFolder();
      const p = await new Promise<string | null>((resolve) => set({ dialog: { kind: "folder", title, resolve } }));
      set({ dialog: null });
      return p;
    },

    async confirm(title, body, opts = {}) {
      const ok = await new Promise<boolean>((resolve) =>
        set({ dialog: { kind: "confirm", title, body, danger: opts.danger, ok: opts.ok, resolve } }));
      set({ dialog: null });
      return ok;
    },

    async ensureLoaded(wid) {
      const l = get().lives[wid];
      if (!l || l.loaded) return;
      try {
        const [snap, commands] = await Promise.all([post("/api/session/snapshot", { wid }), post("/api/session/commands", { wid })]);
        applyEvents();                   // a piece of a reply that arrived before the snapshot must not be added after it again
        patch(wid, (x) => ({ ...x, items: snap.items || [], todos: snap.todos || [], request: snap.request || null,
          busy: !!snap.busy, commands: commands || x.commands, loaded: true,
          working: snap.busy ? x.working || { since: Date.now(), tokens: 0, streaming: !!snap.stream_id } : null }));
      } catch (e: any) {
        patch(wid, (x) => ({ ...x, closed: true, loaded: true }));
      }
    },

    async openSession(meta) {
      const live = Object.values(get().lives).find((l) => l.sid === meta.id && !l.closed);
      if (live) return get().navigate({ kind: "session", wid: live.wid });
      if (!meta.chat && !(await get().ensureTrusted(meta.cwd))) return;
      set({ opening: meta.id });
      try {
        const r = await post("/api/session/open", { id: meta.id, cwd: meta.cwd });
        const wid = addLive(r);
        get().navigate({ kind: "session", wid });
      } catch (e: any) {
        const msg = String(e?.message || "");
        // the project folder was moved or deleted: say so plainly instead of the raw server error
        get().toast(/folder not found/i.test(msg)
          ? `The folder of this session no longer exists (${meta.cwd.split(/[\\/]/).filter(Boolean).pop() || meta.cwd}). Put it back to continue, or delete the session.`
          : msg, "error");
      } finally {
        set({ opening: null });
      }
    },

    async newSession(text, atts, pastes) {
      // a command with a screen (/model, /help, /skills, …) opens it here, without starting a session for it
      if (text.startsWith("/") && !atts.length && runInApp(text, { s: get(), set, live: null })) return null;
      const h = get().home;
      let cwd = h.chat ? null : h.cwd;
      if (!h.chat && !cwd) {
        cwd = await get().pickFolder("Choose a folder for this session");
        if (!cwd) return null;
        set({ home: { ...get().home, cwd } });
      }
      if (cwd && !(await get().ensureTrusted(cwd))) return null;
      set({ opening: "new" });
      try {
        const r = await post("/api/session/open", {
          cwd, chat: h.chat, worktree: h.worktree, mode: h.mode, model: h.model || undefined, effort: h.effort || undefined,
        });
        const wid = addLive(r);
        set({ drafts: { ...get().drafts, home: "" } });
        if (h.worktree) {                                   // a worktree is for this session only, not for every new one after it
          set({ home: { ...get().home, worktree: false } });
          const wt = (r as any).worktree;
          if (wt) get().toast(wt.dirty ? `Worktree ${wt.branch}: changes not yet committed in the original folder were not copied` : `Working in a new worktree (${wt.branch})`);
        }
        get().navigate({ kind: "session", wid });
        if (text.trim() || atts.length) await get().send(wid, text, atts, pastes);
        soonSessions();
        return wid;
      } catch (e: any) {
        get().toast(e.message, "error");
        return null;
      } finally {
        set({ opening: null });
      }
    },

    async startWith(what) {
      if (get().opening) return;
      const wid = await get().newSession("", [], []);
      if (wid) (what === "talk" ? get().setTalk : get().setCall)(wid, true);
    },

    setTalk(wid, on) {
      post("/api/session/talk", { wid, on }).catch((e) => get().toast(e.message, "error"));
    },

    setCall(wid, on) {
      post("/api/session/call", { wid, on }).catch((e) => get().toast(e.message, "error"));
    },

    async send(wid, text, atts, pastes) {
      const l = get().lives[wid];
      if (!l) return;
      // a command with a screen in the app opens it instead of printing text into the conversation (slash.ts)
      if (text.startsWith("/") && !atts.length && runInApp(text, { s: get(), set, live: l })) return;
      const cid = uid();
      const images = atts.filter((a) => a.kind === "image");
      const files = atts.filter((a) => a.kind === "file" && a.path).map((a) => a.path!);
      const item: Item = { kind: "user", id: "opt-" + cid, cid, text, images: images.map((a) => a.url!).filter(Boolean),
        files, queued: l.busy };
      patch(wid, (x) => ({ ...x, items: [...x.items, item] }));
      try {
        await post("/api/session/send", { wid, cid, text, files, pastes,
          images: images.map((a) => ({ mime: a.mime, b64: a.b64, name: a.name })) });
      } catch (e: any) {
        patch(wid, (x) => ({ ...x, items: x.items.map((i) => (i.kind === "user" && i.cid === cid ? { ...i, failed: true, queued: false } : i)) }));
        get().toast(e.message, "error");
        if (e.status === 410) patch(wid, (x) => ({ ...x, closed: true }));
      }
    },

    stop(wid) {
      post("/api/session/stop", { wid }).catch(() => {});
    },

    answer(wid, id, value) {
      patch(wid, (x) => (x.request?.id === id ? { ...x, request: null } : x));
      post("/api/session/answer", { wid, id, value }).catch((e) => get().toast(e.message, "error"));
    },

    async setOpt(wid, opts) {
      patch(wid, (x) => ({ ...x, status: { ...x.status, ...opts } as Partial<Status> }));
      try {
        await post("/api/session/set", { wid, ...opts });
      } catch (e: any) {
        get().toast(e.message, "error");
      }
    },

    async closeSession(wid) {
      try {
        await post("/api/session/close", { wid });
      } catch { /* already gone */ }
      const lives = { ...get().lives };
      delete lives[wid];
      set({ lives });
      if (get().view.kind === "session" && (get().view as any).wid === wid) { closePanes(); set({ view: { kind: "home" } }); }
      soonSessions();
    },

    async restartSession(wid) {
      try {
        const r = await post("/api/session/restart", { wid });
        const lives = { ...get().lives };
        delete lives[wid];
        set({ lives });
        const nw = addLive(r);
        get().navigate({ kind: "session", wid: nw }, true);
      } catch (e: any) {
        get().toast(e.message, "error");
      }
    },

    async deleteSession(meta) {
      const ok = await get().confirm("Delete session?",
        `"${meta.title || "Untitled"}" will be removed from this computer. Emilie keeps a backup in the sessions archive.`,
        { danger: true, ok: "Delete" });
      if (!ok) return;
      try {
        await post("/api/sessions/delete", { id: meta.id, cwd: meta.cwd });
        const l = Object.values(get().lives).find((x) => x.sid === meta.id);
        if (l) {
          const lives = { ...get().lives };
          delete lives[l.wid];
          set({ lives });
          if (get().view.kind === "session" && (get().view as any).wid === l.wid) { closePanes(); set({ view: { kind: "home" } }); }
        }
        get().refreshSessions();
      } catch (e: any) {
        get().toast(e.message, "error");
      }
    },

    async loadModels(refresh = false) {
      if (get().models.loading) return;
      set({ models: { ...get().models, loading: true } });
      try {
        const r = await apiGet<{ models: ModelRow[]; error?: string }>("/api/models", refresh ? { refresh: 1 } : undefined);
        set({ models: { rows: r.models, loading: false, error: r.error, loaded: true } });
      } catch (e: any) {
        set({ models: { ...get().models, loading: false, error: e.message, loaded: true } });
      }
    },

    toast(text, kind = "info") {
      const t = { id: uid("t"), text, kind };
      set({ toasts: [...get().toasts.slice(-3), t] });
      window.setTimeout(() => set({ toasts: get().toasts.filter((x) => x.id !== t.id) }), kind === "error" ? 7000 : 3500);
    },

    setPane(p) {
      // the title bar icons: open that tool as its own panel next to the others; clicking it again closes just that one
      if (!p) return set({ pane: null, paneActive: null, paneTabs: [] });
      const tabs = get().paneTabs;
      if (tabs.some((t) => t.key === p)) {
        const rest = tabs.filter((t) => t.key !== p);
        const next = rest[rest.length - 1] || null;
        return set({ paneTabs: rest, paneActive: next?.key || null, pane: (next?.kind === "file" ? "files" : next?.kind as PaneKind) || null,
          paneMax: rest.length ? get().paneMax : false });
      }
      const title = { files: "Files", terminal: "Terminal", browser: "Browser", diff: "Changes", tasks: "Tasks", checkpoints: "Checkpoints" }[p];
      set({ paneTabs: [...tabs, { key: p, kind: p, title }], paneActive: p, pane: p });
    },
    openFile(path) {
      const key = "file:" + path;
      const tabs = get().paneTabs;
      const title = basename(path) || path;
      set({ paneTabs: tabs.some((t) => t.key === key) ? tabs : [...tabs, { key, kind: "file", path, title }], paneActive: key, pane: "files" });
    },
    closeTab(key) {
      const rest = get().paneTabs.filter((t) => t.key !== key);
      const active = get().paneActive === key ? rest[rest.length - 1]?.key || null : get().paneActive;
      set({ paneTabs: rest, paneActive: active, pane: active ? (get().pane || "files") : null, paneMax: active ? get().paneMax : false });
    },
    activateTab(key) {
      set({ paneActive: key, pane: get().pane || "files" });
    },

    // ------------------------------------------------------------------ server events
    onEvent(ev) {
      const t: string = ev.t;
      const wid: string = ev.wid;
      switch (t) {
        case "item": {
          const it: Item = ev.item;
          patch(wid, (l) => {
            const items = l.items.slice();
            const at = it.kind === "user" && it.cid ? items.findIndex((x) => x.kind === "user" && x.cid === it.cid)
              : items.findIndex((x) => x.id === it.id);
            if (at >= 0) {
              const old = items[at] as any;
              const merged = { ...old, ...it, images: (it as any).images?.length ? (it as any).images : old.images, queued: false,
                at: (it as any).at ?? old.at } as Item;
              // a queued message stayed where it was typed while the previous turn went on below it: now that its own
              // turn starts it moves to the end, where the conversation really is (as the saved history has it)
              if (old.kind === "user" && old.queued) {
                items.splice(at, 1);
                items.push(merged);
              } else items[at] = merged;
            } else items.push({ ...it, at: (it as any).at ?? Date.now() } as Item);   // when it arrived: "5 minutes ago"
            return { ...l, items };
          });
          break;
        }
        case "delta":
          patch(wid, (l) => {
            const items = l.items.slice();
            let i = items.length - 1;
            while (i >= 0 && items[i].id !== ev.id) i--;
            if (i >= 0) {
              const old = items[i] as any;
              items[i] = { ...old, text: old.text + ev.text };
            } else items.push({ kind: "assistant", id: ev.id, text: ev.text, streaming: true, at: Date.now() });
            return { ...l, items };
          });
          break;
        case "stream_start":
          patch(wid, (l) => ({ ...l, working: { ...(l.working || { since: Date.now(), tokens: 0 }), streaming: true, activity: null, voiceOn: !!ev.voice } }));
          break;
        case "voice_phase": {                       // what the voice is doing: "" quiet, "replying" (making it), "speaking"
          const p = (ev.phase || "") as "" | "replying" | "speaking";
          window.clearTimeout(voiceQuiet[wid]);
          const apply = () => patch(wid, (l) => {
            if (!p) return { ...l, working: l.working && !l.busy ? null : l.working ? { ...l.working, voice: "" } : null };
            return { ...l, working: { ...(l.working || { since: Date.now(), tokens: 0, streaming: false, activity: null }), voice: p } };
          });
          if (p) apply();
          else voiceQuiet[wid] = window.setTimeout(apply, 700);   // a gap between two clips must not make the status blink off
          break;
        }
        case "stream_end":
          patch(wid, (l) => ({
            ...l, turnTokens: l.turnTokens + (ev.discarded ? 0 : ev.tokens || 0),
            working: l.working ? { ...l.working, streaming: false, tokens: l.turnTokens + (ev.tokens || 0) } : null,
            items: ev.discarded ? l.items.filter((x) => x.id !== ev.id)
              : l.items.map((x) => (x.id === ev.id ? { ...x, streaming: false, at: Date.now() } as Item : x)),
          }));
          break;
        case "drop_user":                           // a quiet /command: it was answered with a popup, so its typed line goes
          patch(wid, (l) => ({ ...l, items: l.items.filter((x) => !(x.kind === "user" && x.cid === ev.cid)) }));
          break;
        case "toast":
          get().toast(String(ev.text || ""), ev.level === "error" ? "error" : undefined);
          break;
        case "stream_discard":
          patch(wid, (l) => ({ ...l, items: l.items.filter((x) => x.id !== ev.id) }));
          break;
        case "progress":
          patch(wid, (l) => (l.working ? { ...l, working: { ...l.working, tokens: l.turnTokens + (ev.tokens || 0) } } : l));
          break;
        case "activity":
          patch(wid, (l) => ({ ...l, working: l.working ? { ...l.working, activity: ev.text } : ev.text ? { since: Date.now(), tokens: 0, streaming: false, activity: ev.text } : null }));
          break;
        case "tool_end":
          patch(wid, (l) => ({ ...l, items: l.items.map((x) => (x.id === ev.id ? { ...x, ...ev.patch } as Item : x)) }));
          break;
        case "tool_child":
          patch(wid, (l) => ({ ...l, items: l.items.map((x) => (x.id === ev.id && x.kind === "tool"
            ? { ...x, children: [...(x.children || []), ev.child].slice(-200) } : x)) }));
          break;
        case "todos":
          patch(wid, (l) => ({ ...l, todos: ev.items || [] }));
          break;
        case "request": {
          const req: Request = { id: ev.id, ...ev.request };
          patch(wid, (l) => ({ ...l, request: req }));
          if (enabled("desktop_notify")) {
            const what = req.kind === "plan" ? "Emilie's plan is ready for review" : req.kind === "permission"
              ? `Allow ${req.label}? ${req.target.slice(0, 120)}` : req.title;
            notify("Emilie needs you", what);
          }
          break;
        }
        case "request_done":
          patch(wid, (l) => (l.request?.id === ev.id ? { ...l, request: null } : l));
          break;
        case "queued":
          patch(wid, (l) => ({ ...l, items: l.items.map((x) => (x.kind === "user" && x.cid === ev.cid
            ? { ...x, queued: !!ev.busy || ev.position > 1 } : x)) }));
          break;
        case "unqueued": {
          const cids = new Set<string>(ev.cids || []);
          patch(wid, (l) => ({ ...l, items: l.items.filter((x) => !(x.kind === "user" && x.cid && cids.has(x.cid))) }));
          if (cids.size) get().toast("Queued messages were cancelled");
          break;
        }
        case "turn_start":
          patch(wid, (l) => ({ ...l, busy: true, turnTokens: 0, working: { since: Date.now(), tokens: 0, streaming: false, activity: null },
            items: l.items.map((x) => (x.kind === "user" && x.cid === ev.cid ? { ...x, queued: false } : x)) }));
          bridge?.setBusy(true);
          break;
        case "turn_end": {
          const l0 = get().lives[wid];
          patch(wid, (l) => ({
            ...l, busy: false, working: l.working?.voice ? { ...l.working, streaming: false } : null,
            items: l.turnTokens > 0 ? [...l.items, { kind: "turn", id: uid("turn"), secs: ev.secs, tokens: l.turnTokens, stopped: ev.stopped }] : l.items,
          }));
          if (!Object.values(get().lives).some((x) => x.busy)) bridge?.setBusy(false);
          if (l0 && l0.turnTokens > 0 && enabled("desktop_notify")) notify(l0.title || "Emilie", ev.stopped ? "Stopped" : "Finished. Your turn.");
          soonSessions();
          break;
        }
        case "status": {
          const st: Status = ev.status || {};
          patch(wid, (l) => ({
            ...l, status: st, busy: !!st.busy, sid: st.session_id || l.sid, title: st.title && st.title !== "(empty)" ? st.title : l.title,
            todos: st.todos ?? l.todos, cwd: st.cwd || l.cwd,
            request: st.request ? (l.request?.id === st.request.id ? l.request : st.request) : l.request,
            working: st.busy ? l.working || { since: Date.now(), tokens: 0, streaming: false } : l.working?.voice ? l.working : null,   // the voice may still be on its way after the turn
          }));
          break;
        }
        case "snapshot": {
          const s = ev.snapshot || {};
          // a snapshot redraws the conversation: keep the arrival times the window already knows
          patch(wid, (l) => {
            const seen = new Map(l.items.map((x: any) => [x.id, x.at]));
            const items = (s.items || []).map((x: any) => (x.at || !seen.get(x.id) ? x : { ...x, at: seen.get(x.id) }));
            // still working after a redraw: keep (or start) the working line, so a busy Emilie never shows no status
            return { ...l, items, todos: s.todos || [], request: s.request || null, busy: !!s.busy, loaded: true, status: ev.status || l.status,
              working: s.busy ? l.working || { since: Date.now(), tokens: 0, streaming: !!s.stream_id } : null };
          });
          break;
        }
        case "session_changed":
          patch(wid, (l) => ({ ...l, sid: ev.new, title: "" }));
          soonSessions();
          break;
        case "title":
          patch(wid, (l) => ({ ...l, title: ev.title }));
          set({ sessions: get().sessions.map((s) => (s.id === ev.session_id ? { ...s, title: ev.title } : s)) });
          break;
        case "commands":
          patch(wid, (l) => ({ ...l, commands: ev.commands || l.commands }));
          break;
        case "prefs":
          if (ev.key === "mode") break;
          set({ settings: { ...get().settings, [ev.key]: ev.value } });
          break;
        case "settings":
          set({ settings: { ...get().settings, [ev.key]: ev.value } });
          break;
        case "provider_changed":
          get().refreshState();
          set({ lives: Object.fromEntries(Object.entries(get().lives).map(([k, l]) => [k, { ...l, stale: true }])), models: { rows: [], loading: false, loaded: false } });
          break;
        case "sessions_changed":
          soonSessions();
          break;
        case "browser": {                       // the agent's browser_open: show that page in the Browser panel
          const v = get().view;
          if (!(v.kind === "session" && v.wid === wid)) {            // a session in the background must not open panels over another one
            get().toast("A session in the background opened a web page. Open that session to see it.");
            break;
          }
          const tabs = get().paneTabs;
          set({ paneTabs: tabs.some((t) => t.key === "browser") ? tabs : [...tabs, { key: "browser", kind: "browser", title: "Browser" }],
            paneActive: "browser", pane: "browser", browserGo: { url: String(ev.url || ""), n: (get().browserGo?.n || 0) + 1 } });
          get().setSetting("desktop_browser_url", String(ev.url || ""));
          break;
        }
        case "worker_exit":
          patch(wid, (l) => ({ ...l, closed: true, busy: false, working: null }));
          soonSessions();
          break;
        case "closed": {
          const v = get().view;
          if (v.kind === "session" && v.wid === wid) patch(wid, (l) => ({ ...l, closed: true, busy: false, working: null }));
          else {
            const lives = { ...get().lives };
            delete lives[wid];
            set({ lives });
          }
          break;
        }
        case "exit":
          get().closeSession(wid);
          break;
        case "term":
          set({ terms: get().terms.map((r) => (r.tid === ev.tid ? { ...r, lines: [...r.lines, ev.line].slice(-4000) } : r)) });
          break;
        case "term_end":
          set({ terms: get().terms.map((r) => (r.tid === ev.tid ? { ...r, code: ev.code } : r)) });
          break;
        case "doctor":
          set({ doctor: [...get().doctor, ev.row] });
          break;
        case "error":
          get().toast(ev.message || "error", "error");
          break;
        default:
          break;
      }
    },
  };
});

export const currentLive = (s: Store): LiveX | null => (s.view.kind === "session" ? s.lives[s.view.wid] || null : null);

export interface LiveInfo { wid: string | null; sid: string | null; cwd: string; title: string; closed: boolean; hasItems: boolean }

/** The few things about the session on screen that the parts AROUND the conversation show (title bar, sidebar, menus).
 *  The whole session (currentLive) is a new object on every word of a reply; a component reading it redraws ~20 times
 *  a second while she writes. This one redraws only when one of these fields changes. */
export function useLiveInfo(): LiveInfo {
  return useStore(useShallow((s): LiveInfo => {
    const l = currentLive(s);
    return { wid: l?.wid ?? null, sid: l?.sid ?? null, cwd: l?.cwd ?? "", title: l?.title ?? "", closed: !!l?.closed, hasItems: !!l?.items.length };
  }));
}

/** useLiveInfo for the parts that show nothing without a session: null then (and `wid` is set otherwise). */
export function useLiveOnScreen(): (LiveInfo & { wid: string }) | null {
  const info = useLiveInfo();
  return info.wid ? (info as LiveInfo & { wid: string }) : null;
}

// ------------------------------------------------------------------ server events, a frame at a time
// While she writes, the server sends a piece of the reply every 50 ms, plus progress, activity and status lines, each as
// its own message. Applied one by one, every message would redraw the window on its own. They are queued and applied
// together once per frame instead (one redraw for all of them), and pieces of the same reply that arrived together are
// joined into one. A hidden window gets no frames: a timer applies them then.
let evQueue: any[] = [];
let evFrame = 0;
let evTimer = 0;

function applyEvents(): void {
  cancelAnimationFrame(evFrame);
  clearTimeout(evTimer);
  evFrame = evTimer = 0;
  const batch = evQueue;
  evQueue = [];
  const { onEvent } = useStore.getState();
  for (let i = 0; i < batch.length; i++) {
    let ev = batch[i];
    if (ev?.t === "delta") {
      let text = ev.text;
      while (batch[i + 1]?.t === "delta" && batch[i + 1].wid === ev.wid && batch[i + 1].id === ev.id) text += batch[++i].text;
      if (text !== ev.text) ev = { ...ev, text };
    }
    try {
      onEvent(ev);
    } catch (e) {
      console.error("event", ev?.t, e);
    }
  }
}

/** Hand a server event to the store (applied with the others of this frame). */
export function queueEvent(ev: any): void {
  evQueue.push(ev);
  if (evFrame || evTimer) return;
  evFrame = requestAnimationFrame(applyEvents);
  evTimer = window.setTimeout(applyEvents, 100);
}

/** The session in view or, on a page such as Customize, the session the user came from (null if they came from New). */
export const recentLive = (s: Store): LiveX | null => {
  const cur = currentLive(s);
  if (cur || s.view.kind === "home") return cur;
  for (let i = s.back.length - 1; i >= 0; i--) {
    const v = s.back[i];
    if (v.kind === "session") return s.lives[v.wid] || null;
    if (v.kind === "home") return null;
  }
  return null;
};

export function folderName(p: string | null | undefined, scratch?: string): string {
  if (!p) return "No folder";
  if (scratch && p.toLowerCase() === scratch.toLowerCase()) return "No folder";
  return basename(p) || p;
}
