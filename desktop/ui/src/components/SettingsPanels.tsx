// The settings that need their own widget (provider, MCP servers, skills, rules, icon, voice, camera, schedule, ...).
import { useEffect, useMemo, useState } from "react";
import { useStore, recentLive } from "@/lib/store";
import type { Field } from "@/lib/types";
import { get as apiGet, post } from "@/lib/api";
import { bridge, openExternal, openPath } from "@/lib/desktop";
import { ago, basename, cn, prettyModel } from "@/lib/util";
import * as I from "./icons";
import { CodeAppearancePanel } from "./CodeAppearance";
import { Badge, Button, Input, Menu, MenuContent, MenuItem, MenuSep, MenuTrigger, Segmented, Spinner, Switch, TextArea, Tip } from "./ui";
import { EmilieIcon, type IconMode } from "./EmilieIcon";
import { ModelChip } from "./Pickers";
import { UsagePanel } from "./UsagePanel";

type P = { field: Field };
const row = "flex items-center gap-3 rounded-lg px-3 py-2";

// ------------------------------------------------------------------ persona
function PersonaPanel(_: P) {
  const [d, setD] = useState<{ enabled: boolean; text: string; file: string; default: string; project_file: string | null } | null>(null);
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);
  const toast = useStore((s) => s.toast);
  useEffect(() => {
    apiGet("/api/persona").then((r) => { setD(r); setText(r.text); });
  }, []);
  if (!d) return <Spinner />;
  const save = async (body: any) => {
    setSaving(true);
    try {
      const r = await post("/api/persona", body);
      setD(r);
      setText(r.text);
      toast("Saved. It applies from the next message.", "ok");
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setSaving(false);
    }
  };
  return (
    <div>
      {d.project_file && <div className="mb-2 text-[11.5px] text-warn">This project has its own persona: {d.project_file}</div>}
      <TextArea value={text} onChange={(e) => setText(e.target.value)} rows={10} className="font-mono text-[11.5px]" />
      <div className="mt-2 flex items-center gap-2">
        <Button size="sm" variant="primary" loading={saving} disabled={text === d.text} onClick={() => save({ text })}>Save</Button>
        <Button size="sm" variant="ghost" onClick={() => save({ reset: true })}>Reset to the default Emilie</Button>
        <div className="flex-1" />
        <button className="text-[11px] text-text-500 hover:text-text-200" onClick={() => openPath(d.file, true)}>{d.file}</button>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ Emilie icon
function IconPanel({ field }: P) {
  const value = useStore((s) => s.settings.desktop_icon) || "video";
  const setSetting = useStore((s) => s.setSetting);
  const modes: { v: IconMode; label: string; desc: string }[] = [
    { v: "video", label: "Video", desc: "The animated logo" },
    { v: "image", label: "Image", desc: "A still picture, lowest CPU" },
    { v: "ascii", label: "ASCII (CLI)", desc: "Characters, like the terminal" },
    { v: "pixel", label: "Pixel", desc: "Big pixels, like half-blocks" },
  ];
  return (
    <div className="grid grid-cols-4 gap-3">
      {modes.map((m) => (
        <button key={m.v} onClick={() => setSetting(field.key, m.v)}
          className={cn("flex flex-col items-center gap-2 rounded-xl border p-3 text-center transition-colors hover:bg-hover",
            value === m.v ? "border-accent ring-2 ring-accent/25" : "border-border-300")}>
          <EmilieIcon size={64} mode={m.v} />
          <div className="text-[12px] font-medium text-text-100">{m.label}</div>
          <div className="text-[10.5px] leading-tight text-text-500">{m.desc}</div>
        </button>
      ))}
    </div>
  );
}

function LogoPanel({ field }: P) {
  const logo = useStore((s) => s.settings.logo);
  const setSetting = useStore((s) => s.setSetting);
  const [path, setPath] = useState("");
  const choose = async () => {
    if (bridge) {
      const p = await bridge.pickFile({ title: "Choose a video or image", filters: [{ name: "Video or image", extensions: ["mp4", "webm", "mov", "m4v", "gif", "png", "jpg", "jpeg", "webp"] }] });
      if (p) setSetting(field.key, p);
    }
  };
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="min-w-0 flex-1 truncate rounded-lg bg-bg-200 px-3 py-1.5 font-mono text-[11.5px] text-text-300" title={logo || ""}>
        {logo || "Default (assets/logo.mp4)"}
      </div>
      {bridge ? <Button size="sm" onClick={choose}>Choose file…</Button> : (
        <>
          <Input value={path} onChange={(e) => setPath(e.target.value)} placeholder="C:\\path\\to\\logo.mp4" className="h-8 w-60" />
          <Button size="sm" onClick={() => path && setSetting(field.key, path)}>Use</Button>
        </>
      )}
      {logo && <Button size="sm" variant="ghost" onClick={() => setSetting(field.key, null)}>Reset</Button>}
    </div>
  );
}

// ------------------------------------------------------------------ provider and API key
interface Preset { id: string; label: string; kind: string; base: string | null; model: string | null; hint: string; nokey: boolean; has_key: boolean; saved_model?: string; saved_base?: string }

export function ProviderPanel({ onDone, compact }: { onDone?: () => void; compact?: boolean } & Partial<P>) {
  const [info, setInfo] = useState<{ current: string | null; model: string; presets: Preset[] } | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [key, setKey] = useState("");
  const [base, setBase] = useState("");
  const [model, setModel] = useState("");
  const [busy, setBusy] = useState(false);
  const [test, setTest] = useState<any>(null);
  const toast = useStore((s) => s.toast);
  const doctor = useStore((s) => s.doctor);
  useEffect(() => {
    apiGet("/api/providers").then((r) => { setInfo(r); setSel(r.current || "anthropic"); });
  }, []);
  const p = info?.presets.find((x) => x.id === sel);
  useEffect(() => {
    if (!p) return;
    setKey("");
    setBase(p.saved_base || (p.id === "custom" ? "" : p.base || ""));
    setModel(p.saved_model || "");
    setTest(null);                     // results of another provider's test do not belong under this one
  }, [sel]);
  // the test always runs on the provider in use: until the picked one is in use, there is nothing to test
  const inUse = !!p && p.id === info?.current;
  if (!info) return <Spinner />;
  const save = async () => {
    setBusy(true);
    try {
      const r = await post("/api/providers", { id: sel, key, base: p?.id === "custom" ? base : undefined, model });
      setInfo(r);
      setKey("");
      setTest(null);
      toast(`Provider: ${p?.label}`, "ok");
      useStore.getState().refreshState();
      useStore.getState().loadSettings();
      onDone?.();
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  };
  const runTest = async () => {
    useStore.setState({ doctor: [] });
    setTest({ running: true });
    try {
      setTest(await post("/api/providers/test", {}));
    } catch (e: any) {
      setTest({ error: e.message });
    }
  };
  return (
    <div className="flex flex-col gap-3">
      <div className={cn("grid gap-1.5", compact ? "grid-cols-2" : "grid-cols-3")}>
        {info.presets.map((x) => (
          <button key={x.id} onClick={() => setSel(x.id)}
            className={cn("flex items-center gap-2 rounded-lg border px-3 py-2 text-left text-[12px] transition-colors hover:bg-hover",
              sel === x.id ? "border-accent bg-accent-soft/40" : "border-border-300")}>
            <span className="min-w-0 flex-1 truncate text-text-100">{x.label}</span>
            {x.id === info.current && <Badge tone="accent">current</Badge>}
            {x.id !== info.current && x.has_key && <I.Check size={13} className="text-ok" />}
          </button>
        ))}
      </div>
      {p && (
        <div className="flex flex-col gap-2.5 rounded-xl border border-border-300 bg-bg-100 p-3.5">
          {p.id === "custom" && (
            <label className="flex flex-col gap-1 text-[11.5px] text-text-400">Base URL
              <Input value={base} onChange={(e) => setBase(e.target.value)} placeholder="http://localhost:20128/v1" />
            </label>
          )}
          {!p.nokey && (
            <label className="flex flex-col gap-1 text-[11.5px] text-text-400">
              API key {p.has_key && <span className="text-text-500">(saved; leave empty to keep it)</span>}
              <Input type="password" value={key} onChange={(e) => setKey(e.target.value)} placeholder={p.has_key ? "••••••••••••" : "Paste your API key"} autoComplete="off" />
              {p.hint && <span className="text-[11px] text-text-500">Get one at: {p.hint}</span>}
            </label>
          )}
          <label className="flex flex-col gap-1 text-[11.5px] text-text-400">Model <span className="text-text-500">(empty = {p.model || "the provider's default"})</span>
            <Input value={model} onChange={(e) => setModel(e.target.value)} placeholder={p.model || "model name"} />
          </label>
          <div className="flex items-center gap-2">
            <Button variant="primary" loading={busy} onClick={save}>{p.id === info.current ? "Save" : "Use this provider"}</Button>
            {!compact && (
              <Tip content={inUse ? `A few small real calls to ${info.model}` : "Click “Use this provider” first: the test runs on the provider Emilie uses"}>
                {/* a span: a disabled button gets no pointer events, so its tooltip would never show */}
                <span className="inline-flex">
                  <Button variant="ghost" onClick={runTest} disabled={!!test?.running || !inUse}>Test the current model</Button>
                </span>
              </Tip>
            )}
            <span className="text-[11px] text-text-500">Keys are stored in ~/.emilie/keys.json on this computer.</span>
          </div>
        </div>
      )}
      {test && (
        <div className="rounded-xl border border-border-300 p-3 text-[12px]">
          {(test.rows || doctor).map((r: any) => (
            <div key={r.key + r.label} className="flex items-center gap-2 py-0.5">
              {r.ok === true ? <I.CircleCheck size={14} className="text-ok" /> : r.ok === false ? <I.CircleX size={14} className="text-danger" /> : <I.Circle size={14} className="text-text-500" />}
              <span className="text-text-200">{r.label}</span><span className="text-text-500">{r.detail}</span>
              {!!r.secs && <span className="ml-auto text-[11px] text-text-500">{r.secs}s</span>}
            </div>
          ))}
          {test.running && <div className="flex items-center gap-2 text-text-400"><Spinner />Testing with a few small calls (~2000 tokens)…</div>}
          {test.error && <div className="text-danger">{test.error}</div>}
          {test.advice?.map((a: string) => <div key={a} className="mt-1 text-warn">! {a}</div>)}
        </div>
      )}
    </div>
  );
}

function ModelPanel(_: P) {
  const model = useStore((s) => s.settings.model || s.state?.provider.model || "");
  const setSetting = useStore((s) => s.setSetting);
  return (
    <div className="flex items-center gap-3">
      <div className="rounded-lg border border-border-300"><ModelChip value={model} onChange={(m) => setSetting("model", m)} /></div>
      <span className="font-mono text-[11px] text-text-500">{model}</span>
    </div>
  );
}

// ------------------------------------------------------------------ permission rules
function RulesPanel(_: P) {
  const perms = useStore((s) => s.settings.permissions) || {};
  const setSetting = useStore((s) => s.setSetting);
  const [add, setAdd] = useState({ allow: "", deny: "" });
  const lists: ("allow" | "deny")[] = ["allow", "deny"];
  const save = (kind: "allow" | "deny", rules: string[]) => setSetting("permissions", { ...perms, [kind]: rules });
  return (
    <div className="grid grid-cols-2 gap-4">
      {lists.map((k) => {
        const rules: string[] = Array.isArray(perms[k]) ? perms[k] : [];
        return (
          <div key={k}>
            <div className="mb-1.5 text-[12px] font-medium text-text-200">{k === "allow" ? "Always allow" : "Always block"}</div>
            <div className="flex flex-col gap-1">
              {rules.map((r) => (
                <div key={r} className="group flex items-center gap-2 rounded-md bg-bg-200 px-2.5 py-1 font-mono text-[11.5px]">
                  <span className="min-w-0 flex-1 truncate">{r}</span>
                  <button className="text-text-500 opacity-0 hover:text-danger group-hover:opacity-100" onClick={() => save(k, rules.filter((x) => x !== r))}><I.X size={13} /></button>
                </div>
              ))}
              {!rules.length && <div className="text-[11.5px] text-text-500">No rules.</div>}
            </div>
            <div className="mt-2 flex gap-1.5">
              <Input value={add[k]} onChange={(e) => setAdd({ ...add, [k]: e.target.value })} placeholder={k === "allow" ? "bash(git *)" : "read_file(*.env*)"}
                className="h-8 font-mono text-[11.5px]" onKeyDown={(e) => {
                  if (e.key === "Enter" && add[k].trim()) { save(k, [...rules.filter((x) => x !== add[k].trim()), add[k].trim()]); setAdd({ ...add, [k]: "" }); }
                }} />
              <Button size="sm" onClick={() => { if (add[k].trim()) { save(k, [...rules.filter((x) => x !== add[k].trim()), add[k].trim()]); setAdd({ ...add, [k]: "" }); } }}>Add</Button>
            </div>
          </div>
        );
      })}
      <div className="col-span-2 text-[11px] text-text-500">
        A rule is a tool name or tool(pattern): <code>web_fetch</code>, <code>bash(git *)</code>, <code>mcp__browser__*</code>, <code>read_file(*.env*)</code>. Block rules win. Dangerous commands still ask.
      </div>
    </div>
  );
}

function TrustedPanel(_: P) {
  const [folders, setFolders] = useState<Record<string, string> | null>(null);
  const load = () => apiGet("/api/trust", { path: "" }).then((r) => setFolders(r.folders || {}));
  useEffect(() => { load(); }, []);
  if (!folders) return <Spinner />;
  const list = Object.entries(folders);
  return (
    <div className="flex flex-col gap-1">
      {!list.length && <div className="text-[11.5px] text-text-500">None yet. Emilie asks the first time you open a folder.</div>}
      {list.map(([p, when]) => (
        <div key={p} className="group flex items-center gap-2 rounded-md bg-bg-200 px-2.5 py-1.5 text-[11.5px]">
          <I.FolderIcon size={14} className="text-text-400" />
          <span className="min-w-0 flex-1 truncate font-mono" title={p}>{p}</span>
          <span className="text-text-500">{when}</span>
          <button className="text-text-500 opacity-0 hover:text-danger group-hover:opacity-100" title="Stop trusting"
            onClick={() => post("/api/trust", { path: p, remove: true }).then(load)}><I.X size={13} /></button>
        </div>
      ))}
    </div>
  );
}

function HooksPanel(_: P) {
  const hooks = useStore((s) => s.settings.hooks) || {};
  const file = useStore((s) => s.state?.settings_file);
  const n = Object.values(hooks).reduce((a: number, v: any) => a + (Array.isArray(v) ? v.length : 0), 0);
  return (
    <div className="flex items-center gap-3 text-[12px] text-text-300">
      <span>{n ? `${n} hook(s): ${Object.keys(hooks).join(", ")}` : "No hooks. Commands that run before or after a tool (PreToolUse / PostToolUse)."}</span>
      <div className="flex-1" />
      {file && <Button size="sm" onClick={() => openPath(file)}>Edit settings.json</Button>}
    </div>
  );
}

// ------------------------------------------------------------------ MCP servers
function McpPanel(_: P) {
  const live = useStore((s) => recentLive(s));
  const toast = useStore((s) => s.toast);
  const [cfg, setCfg] = useState<any>(null);
  const [status, setStatus] = useState<any[] | null>(null);
  const [scope, setScope] = useState<"user" | "project">("user");
  const [form, setForm] = useState<{ name: string; type: "command" | "url"; command: string; args: string; env: string; url: string; headers: string } | null>(null);
  const cwd = live?.cwd;
  const load = () => apiGet("/api/mcp/config", { cwd }).then(setCfg).catch((e) => toast(e.message, "error"));
  const loadStatus = (reload = false) => live && !live.closed &&
    post("/api/session/mcp", { wid: live.wid, reload }).then(setStatus).catch(() => setStatus(null));
  useEffect(() => { load(); loadStatus(); }, [live?.wid]);
  if (!cfg) return <Spinner />;
  const servers: Record<string, any> = cfg[scope]?.servers || {};
  const write = async (next: Record<string, any>) => {
    try {
      setCfg(await post("/api/mcp/config", { scope, cwd, servers: next }));
      toast("Saved. Reload the servers to apply.", "ok");
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  const submit = () => {
    if (!form?.name.trim()) return;
    const entry: any = form.type === "url"
      ? { url: form.url.trim(), ...(form.headers.trim() ? { headers: Object.fromEntries(form.headers.split("\n").filter((l) => l.includes(":")).map((l) => [l.split(":")[0].trim(), l.slice(l.indexOf(":") + 1).trim()])) } : {}) }
      : { command: form.command.trim(), args: form.args.split(/\n/).map((x) => x.trim()).filter(Boolean),
        ...(form.env.trim() ? { env: Object.fromEntries(form.env.split("\n").filter((l) => l.includes("=")).map((l) => [l.split("=")[0].trim(), l.slice(l.indexOf("=") + 1).trim()])) } : {}) };
    write({ ...servers, [form.name.trim()]: entry });
    setForm(null);
  };
  const st = (name: string) => status?.find((x) => x.name === name);
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <Segmented value={scope} onChange={(v) => setScope(v as any)} options={[{ value: "user", label: "All projects" }, ...(cfg.project ? [{ value: "project", label: "This project" }] : [])]} />
        <div className="flex-1" />
        {live && <Button size="sm" variant="ghost" onClick={() => { setStatus(null); loadStatus(true); }}><I.Refresh size={14} />Reload in this session</Button>}
        <Button size="sm" onClick={() => setForm({ name: "", type: "command", command: "npx", args: "-y\n@playwright/mcp@latest", env: "", url: "", headers: "" })}><I.Plus size={14} />Add server</Button>
      </div>
      <div className="flex flex-col gap-1.5">
        {!Object.keys(servers).length && <div className="text-[11.5px] text-text-500">No servers in {cfg[scope]?.path}.</div>}
        {Object.entries(servers).map(([name, c]) => {
          const s = st(name);
          return (
            <div key={name} className="group rounded-lg border border-border-300 px-3 py-2">
              <div className="flex items-center gap-2">
                <I.Plug size={14} className="text-text-400" />
                <span className="text-[12px] font-medium text-text-100">{name}</span>
                {s && <Badge tone={s.status === "ready" ? "ok" : s.status === "failed" ? "danger" : "warn"}>{s.status}{s.status === "ready" ? ` · ${s.tools.length} tools` : ""}</Badge>}
                <div className="flex-1" />
                {live && !live.closed && (
                  <button title="Reconnect" className="text-text-500 opacity-0 hover:text-text-100 group-hover:opacity-100"
                    onClick={() => post("/api/session/mcp", { wid: live.wid, reconnect: name }).then(setStatus).catch((e) => toast(e.message, "error"))}><I.Refresh size={14} /></button>
                )}
                <button title="Remove" className="text-text-500 opacity-0 hover:text-danger group-hover:opacity-100"
                  onClick={async () => { if (await useStore.getState().confirm(`Remove ${name}?`, "It is deleted from the configuration. You can add it again with Add server.", { danger: true, ok: "Remove" })) { const n = { ...servers }; delete n[name]; write(n); } }}><I.Trash size={14} /></button>
              </div>
              <div className="mt-1 truncate font-mono text-[11px] text-text-500">{c.url || [c.command, ...(c.args || [])].join(" ")}</div>
              {s?.error && <div className="mt-1 text-[11px] text-danger">{s.error}</div>}
            </div>
          );
        })}
      </div>
      {form && (
        <div className="flex flex-col gap-2 rounded-xl border border-border-300 bg-bg-100 p-3">
          <div className="flex gap-2">
            <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="name, e.g. browser" className="h-8 w-48" />
            <Segmented value={form.type} onChange={(v) => setForm({ ...form, type: v as any })} options={[{ value: "command", label: "Command" }, { value: "url", label: "Remote URL" }]} />
          </div>
          {form.type === "command" ? (
            <>
              <Input value={form.command} onChange={(e) => setForm({ ...form, command: e.target.value })} placeholder="command (npx, uvx, python, …)" className="h-8 font-mono text-[11.5px]" />
              <TextArea value={form.args} onChange={(e) => setForm({ ...form, args: e.target.value })} rows={3} placeholder="arguments, one per line" className="font-mono text-[11.5px]" />
              <TextArea value={form.env} onChange={(e) => setForm({ ...form, env: e.target.value })} rows={2} placeholder="environment, KEY=value per line (optional)" className="font-mono text-[11.5px]" />
            </>
          ) : (
            <>
              <Input value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} placeholder="https://…/mcp" className="h-8 font-mono text-[11.5px]" />
              <TextArea value={form.headers} onChange={(e) => setForm({ ...form, headers: e.target.value })} rows={2} placeholder="headers, Name: value per line (optional), ${TOKEN} reads an environment variable" className="font-mono text-[11.5px]" />
            </>
          )}
          <div className="flex gap-2">
            <Button size="sm" variant="primary" onClick={submit}>Save</Button>
            <Button size="sm" variant="ghost" onClick={() => setForm(null)}>Cancel</Button>
          </div>
        </div>
      )}
      <div className="text-[11px] text-text-500">MCP tools ask for permission first, except in Trust mode. Node.js tools need Node.js installed.</div>
    </div>
  );
}

// ------------------------------------------------------------------ plugins
type PluginInfo = { id: string; name: string; version: string; description: string; author: string; path: string;
  enabled: boolean; skills: number; commands: number; mcp: string[] };

/** Plugins (Claude Code's Customize > Plugins): folders in ~/.emilie/plugins that bring skills, commands and connectors. */
function PluginsPanel(_: P) {
  const toast = useStore((s) => s.toast);
  const [items, setItems] = useState<PluginInfo[] | null>(null);
  const [adding, setAdding] = useState(false);
  const [source, setSource] = useState("");
  const [busy, setBusy] = useState(false);
  const apply = (r: any) => setItems(r.items || []);
  useEffect(() => { apiGet("/api/plugins").then(apply).catch((e) => toast(e.message, "error")); }, []);
  if (!items) return <Spinner />;
  const call = async (path: string, body: any, ok?: string) => {
    setBusy(true);
    let r: any = null;
    try { r = await post(path, body); apply(r); if (ok) toast(ok, "ok"); } catch (e: any) { toast(e.message, "error"); }
    setBusy(false);
    return r;
  };
  const install = async () => {
    const src = source.trim();
    if (!src) return;
    const web = /^https:/i.test(src);
    if (!(await useStore.getState().confirm(`Install this plugin?`,
      `${web ? "Emilie will download" : "Emilie will copy"} ${src}. A plugin can add skills, commands and connectors that run programs on this computer, so install only ones you trust.`,
      { ok: "Install" }))) return;
    const r: any = await call("/api/plugins/install", { source: src });
    if (r?.many) toast(`${r.many.length} plugins added, all switched off. Turn on the ones you want from their ⋯ menu.`, "ok");
    else if (r) toast("Plugin installed. Reload skills and connectors in a session to use it.", "ok");
    setSource(""); setAdding(false);
  };
  const remove = async (p: PluginInfo) => {
    if (await useStore.getState().confirm(`Remove ${p.name}?`, "The plugin's folder is deleted from this computer. You can install it again later.", { danger: true, ok: "Remove" }))
      call("/api/plugins/remove", { id: p.id });
  };
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <span className="text-[12px] text-text-100">Installed</span>
        <span className="rounded-full bg-bg-400 px-1.5 text-[10.5px] text-text-300">{items.length}</span>
        <div className="flex-1" />
        <Button size="sm" variant="ghost" onClick={() => apiGet("/api/plugins").then(apply)}><I.Refresh size={14} />Refresh</Button>
        <Button size="sm" onClick={() => setAdding(!adding)}><I.Plus size={14} />Add</Button>
      </div>
      {adding && (
        <div className="flex flex-col gap-2 rounded-xl border border-border-300 bg-bg-100 p-3">
          <Input value={source} onChange={(e) => setSource(e.target.value)} className="h-8 font-mono text-[11.5px]"
            placeholder="A folder (D:\\my-plugin) or a GitHub address (https://github.com/user/repo)" />
          <div className="flex gap-2">
            <Button size="sm" variant="primary" disabled={busy || !source.trim()} onClick={install}>{busy ? "Installing…" : "Install"}</Button>
            <Button size="sm" variant="ghost" onClick={() => setAdding(false)}>Cancel</Button>
          </div>
        </div>
      )}
      {!items.length && (
        <div className="flex items-center gap-3 rounded-lg border border-border-300 px-3 py-3 text-[12px] text-text-400">
          <I.Plug size={14} />No plugins installed yet. Use Add to install one.
        </div>
      )}
      <div className="flex flex-col">
        {items.map((p) => (
          <div key={p.id} className="group flex items-center gap-3 border-b border-border-200 py-2.5 last:border-0">
            <span className="flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-lg bg-bg-400 text-text-300"><I.Plug size={14} /></span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="text-[12.5px] font-medium text-text-100">{p.name}</span>
                {p.version && <span className="text-[10.5px] text-text-500">v{p.version}</span>}
                {!p.enabled && <Badge tone="warn">Disabled</Badge>}
                {p.skills > 0 && <Badge tone="ok">{p.skills} skill{p.skills > 1 ? "s" : ""}</Badge>}
                {p.commands > 0 && <Badge tone="ok">{p.commands} command{p.commands > 1 ? "s" : ""}</Badge>}
                {p.mcp.length > 0 && <Badge tone="ok">{p.mcp.length} connector{p.mcp.length > 1 ? "s" : ""}</Badge>}
              </div>
              <div className="truncate text-[11.5px] text-text-400" title={p.description}>
                {p.author ? `By ${p.author}` : "Local plugin"}{p.description ? ` · ${p.description}` : ""}
              </div>
            </div>
            <Menu>
              <MenuTrigger asChild>
                <button className="rounded-md p-1 text-text-400 hover:bg-hover hover:text-text-100" aria-label="Plugin actions"><I.Ellipsis size={14} /></button>
              </MenuTrigger>
              <MenuContent align="end">
                <MenuItem onSelect={() => call("/api/plugins/toggle", { id: p.id, enabled: !p.enabled })}>{p.enabled ? "Disable" : "Enable"}</MenuItem>
                <MenuItem onSelect={() => openPath(p.path)}>Open folder</MenuItem>
                <MenuSep />
                <MenuItem danger onSelect={() => remove(p)}>Remove</MenuItem>
              </MenuContent>
            </Menu>
          </div>
        ))}
      </div>
      <div className="text-[11px] text-text-500">
        Folder layout: plugin.json, skills/&lt;name&gt;/SKILL.md, commands/&lt;name&gt;.md and .mcp.json. Changes apply after you reload skills and connectors in a session.
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ skills
function SkillsPanel(_: P) {
  const live = useStore((s) => recentLive(s));
  const home = useStore((s) => s.home);
  const cwd = live?.cwd || (home.chat ? "" : home.cwd || "");
  const [data, setData] = useState<any>(null);
  const [q, setQ] = useState("");
  const load = () => apiGet("/api/skills", { cwd }).then(setData);
  useEffect(() => { load(); }, [cwd]);
  const items = useMemo(() => (data?.items || []).filter((x: any) => !q || (x.name + " " + x.description).toLowerCase().includes(q.toLowerCase())), [data, q]);
  if (!data) return <Spinner />;
  const insert = (name: string) => {
    const st = useStore.getState();
    useStore.setState({ settingsOpen: null });
    // On the Customize page there is no message box: go back to the session (or New) first, then type the skill.
    if (st.view.kind === "customize") st.navigate(live ? { kind: "session", wid: live.wid } : { kind: "home" });
    setTimeout(() => window.dispatchEvent(new CustomEvent("emilie:insert", { detail: `/${name} ` })), 80);
  };
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search skills and commands" className="h-8" />
        <Button size="sm" variant="ghost" onClick={load}><I.Refresh size={14} />Reload</Button>
        <Button size="sm" variant="ghost" onClick={() => openPath(data.folders[0])}>Open skills folder</Button>
      </div>
      <div className="text-[11px] text-text-500">For {data.cwd}. Click a skill to use it in the message box. Add your own in ~/.emilie/skills/&lt;name&gt;/SKILL.md or .emilie/skills in a project.</div>
      <div className="flex flex-col divide-y divide-border-200 rounded-xl border border-border-300">
        {items.map((x: any) => (
          <button key={x.kind + x.name} onClick={() => insert(x.name)} className="flex items-start gap-3 px-3 py-2.5 text-left hover:bg-hover">
            {x.kind === "skill" ? <I.Book size={15} className="mt-0.5 shrink-0 text-text-400" /> : <I.Slash size={15} className="mt-0.5 shrink-0 text-text-400" />}
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="font-mono text-[12px] text-text-100">/{x.name}</span>
                {x.phase_label && <Badge>{x.phase_label}</Badge>}
                <Badge tone={x.source === "builtin" ? "neutral" : "accent"}>{x.source}</Badge>
              </div>
              <div className="mt-0.5 line-clamp-2 text-[11.5px] text-text-400">{x.description}</div>
            </div>
          </button>
        ))}
        {!items.length && <div className="px-3 py-4 text-[12px] text-text-500">Nothing found.</div>}
      </div>
      {data.skipped?.length > 0 && <div className="text-[11px] text-warn">{data.skipped.length} skill folder(s) were skipped: {data.skipped.join("; ")}</div>}
    </div>
  );
}

// ------------------------------------------------------------------ voice, camera, companion
function VoiceTestPanel(_: P) {
  const [text, setText] = useState("Hello! This is Emilie.");
  const toast = useStore((s) => s.toast);
  return (
    <div className="flex gap-2">
      <Input value={text} onChange={(e) => setText(e.target.value)} className="h-8" />
      <Button size="sm" onClick={() => post("/api/voice/test", { text }).then(() => toast("Sending a test line…")).catch((e) => toast(e.message, "error"))}>
        <I.Volume size={14} />Speak
      </Button>
    </div>
  );
}

function CameraPanel(_: P) {
  const [d, setD] = useState<{ available: boolean; devices: string[]; configured: string | null } | null>(null);
  const [photo, setPhoto] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const toast = useStore((s) => s.toast);
  useEffect(() => { apiGet("/api/camera").then(setD).catch(() => setD({ available: false, devices: [], configured: null })); }, []);
  if (!d) return <Spinner />;
  return (
    <div className="flex flex-col gap-2">
      {!d.available && <div className="text-[11.5px] text-warn">No camera found. The camera needs ffmpeg: winget install Gyan.FFmpeg</div>}
      <div className="flex flex-wrap items-center gap-2">
        <select value={d.configured || ""} onChange={(e) => post("/api/camera/device", { device: e.target.value || null }).then(setD)}
          className="h-8 rounded-lg border border-border-300 bg-bg-000 px-2 text-[12px]">
          <option value="">Automatic</option>
          {d.devices.map((x) => <option key={x} value={x}>{x}</option>)}
        </select>
        <Button size="sm" loading={busy} disabled={!d.available} onClick={async () => {
          setBusy(true);
          try {
            const r = await post("/api/camera/photo", {});
            setPhoto(`data:${r.mime};base64,${r.b64}`);
          } catch (e: any) {
            toast(e.message, "error");
          } finally {
            setBusy(false);
          }
        }}><I.Camera size={14} />Test photo</Button>
      </div>
      {photo && <img src={photo} alt="" className="max-h-48 self-start rounded-lg border border-border-300" />}
    </div>
  );
}

function CompanionPanel(_: P) {
  const [lines, setLines] = useState<string[] | null>(null);
  const confirm = useStore((s) => s.confirm);
  useEffect(() => { apiGet("/api/companion").then((r) => setLines(r.lines)).catch(() => setLines([])); }, []);
  if (!lines) return <Spinner />;
  return (
    <div>
      <div className="max-h-40 overflow-y-auto rounded-lg bg-bg-200 px-3 py-2 text-[11.5px] text-text-300 whitespace-pre-wrap selectable">{lines.join("\n") || "Nothing yet."}</div>
      <Button size="sm" variant="ghost" className="mt-2 text-danger" onClick={async () => {
        if (await confirm("Forget everything?", "Emilie forgets what she learned about you on video calls. This cannot be undone.", { danger: true, ok: "Forget" }))
          setLines((await post("/api/companion", { forget: true })).lines);
      }}>Forget everything</Button>
    </div>
  );
}

// ------------------------------------------------------------------ scheduled tasks
function SchedulePanel(_: P) {
  const [d, setD] = useState<{ supported: boolean; rows: string[] } | null>(null);
  const [f, setF] = useState({ name: "", kind: "daily", at: "09:00", prompt: "", folder: "", trust: false });
  const toast = useStore((s) => s.toast);
  const pickFolder = useStore((s) => s.pickFolder);
  const load = () => apiGet("/api/schedule").then(setD);
  useEffect(() => { load(); }, []);
  if (!d) return <Spinner />;
  if (!d.supported) return <div className="text-[12px] text-text-500">Scheduled tasks use the Windows Task Scheduler (Windows only).</div>;
  const act = async (body: any) => {
    try {
      const r = await post("/api/schedule", body);
      setD(r);
      toast(r.message, "ok");
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        {d.rows.map((r) => {
          const name = r.split("  ·  ")[0];
          const real = !r.startsWith("no scheduled");
          return (
            <div key={r} className="group flex items-center gap-2 rounded-md bg-bg-200 px-2.5 py-1.5 text-[11.5px]">
              <I.Clock size={14} className="text-text-400" /><span className="min-w-0 flex-1 truncate">{r}</span>
              {real && <button className="text-text-400 hover:text-text-100" onClick={() => act({ action: "run", name })}>Run now</button>}
              {real && <button className="text-text-500 hover:text-danger" onClick={() => act({ action: "rm", name })}><I.Trash size={13} /></button>}
            </div>
          );
        })}
      </div>
      <div className="grid grid-cols-[1fr_auto_auto] gap-2 rounded-xl border border-border-300 p-3">
        <Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="name (letters, digits, - _)" className="h-8" />
        <select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })} className="h-8 rounded-lg border border-border-300 bg-bg-000 px-2 text-[12px]">
          {["daily", "hourly", "weekly", "once"].map((k) => <option key={k}>{k}</option>)}
        </select>
        <Input value={f.at} onChange={(e) => setF({ ...f, at: e.target.value })} placeholder="HH:MM" className="h-8 w-24" />
        <TextArea value={f.prompt} onChange={(e) => setF({ ...f, prompt: e.target.value })} rows={2} placeholder="What should Emilie do?" className="col-span-3" />
        <div className="col-span-3 flex items-center gap-2">
          <Button size="sm" onClick={async () => { const p = await pickFolder("Folder for the scheduled task"); if (p) setF({ ...f, folder: p }); }}><I.FolderIcon size={14} />{f.folder ? basename(f.folder) : "Folder…"}</Button>
          <label className="flex items-center gap-1.5 text-[11.5px] text-text-300"><Switch checked={f.trust} onChange={(v) => setF({ ...f, trust: v })} />Allow edits (trust)</label>
          <div className="flex-1" />
          <Button size="sm" variant="primary" disabled={!f.name || !f.prompt || !f.folder} onClick={() => act({ action: "add", ...f })}>Add</Button>
        </div>
      </div>
      <div className="text-[11px] text-text-500">Without “Allow edits” a scheduled run is read-only: anything that would ask for permission is denied.</div>
    </div>
  );
}

// ------------------------------------------------------------------ files, about
function FilesPanel(_: P) {
  const st = useStore((s) => s.state);
  if (!st) return null;
  const rows: [string, string][] = [["Data folder", st.data_dir], ["Settings", st.settings_file], ["App log", st.log], ["Emilie's code", st.root]];
  return (
    <div className="flex flex-col gap-1">
      {rows.map(([k, p]) => (
        <div key={k} className="flex items-center gap-3 rounded-md px-1 py-1 text-[12px]">
          <span className="w-28 shrink-0 text-text-400">{k}</span>
          <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-text-300" title={p}>{p}</span>
          <Button size="sm" variant="ghost" onClick={() => openPath(p)}>Open</Button>
        </div>
      ))}
    </div>
  );
}

/** "Delete all history": two confirmations (like Claude's "Delete sessions stored by Anthropic"), then every saved
 *  conversation is erased for good. Settings, keys, memory and skills stay. */
function HistoryPanel(_: P) {
  const [busy, setBusy] = useState(false);
  const run = async () => {
    const st = useStore.getState();
    if (!(await st.confirm("Delete all chat history?",
      "Every conversation saved on this computer will be permanently deleted, including the ones you deleted earlier. Your settings, memory and skills are not affected. This can't be undone.",
      { danger: true, ok: "Delete all history" }))) return;
    if (!(await st.confirm("Are you absolutely sure?",
      "This is the last step. All your conversations will be erased for good and cannot be recovered.",
      { danger: true, ok: "Yes, delete everything" }))) return;
    setBusy(true);
    try {
      const r = await post("/api/sessions/delete_all", { confirm: "DELETE" });
      useStore.setState({ lives: {}, settingsOpen: null });
      useStore.getState().navigate({ kind: "home" });
      useStore.getState().refreshSessions();
      useStore.getState().toast(`History deleted (${r.deleted} files).`, "ok");
    } catch (e: any) {
      useStore.getState().toast(e.message, "error");
    }
    setBusy(false);
  };
  return (
    <div className="flex items-center gap-4 rounded-md px-1 py-1">
      <div className="min-w-0 flex-1">
        <div className="text-[12.5px] text-text-100">Delete all history</div>
        <div className="mt-0.5 text-[11.5px] leading-[16px] text-text-400">
          Permanently delete every saved conversation on this computer. Settings, memory and skills stay. You are asked twice.
        </div>
      </div>
      <button disabled={busy} onClick={run}
        className="h-[28px] shrink-0 rounded-[6px] border border-danger bg-danger/10 px-3 text-[12px] font-medium text-danger hover:bg-danger/20 disabled:opacity-50">
        {busy ? "Deleting…" : "Delete…"}
      </button>
    </div>
  );
}

function AboutPanel(_: P) {
  const st = useStore((s) => s.state);
  return (
    <div className="flex items-center gap-4">
      <EmilieIcon size={72} />
      <div className="text-[12px] text-text-300">
        <div className="text-[14px] font-semibold text-text-100">Emilie</div>
        <div>Version {st?.version} · desktop app (Electron + React)</div>
        <div className="text-text-500">Python: {st?.python}</div>
        <div className="mt-2 flex gap-2">
          <Button size="sm" onClick={() => useStore.setState({ dialog: { kind: "whatsnew" } })}>What's new</Button>
          <Button size="sm" variant="ghost" onClick={() => openExternal("https://github.com/XTheGreat/emilie-agent-v.1.0")}>GitHub</Button>
        </div>
      </div>
    </div>
  );
}

export const CUSTOM: Record<string, (p: P) => React.ReactNode> = {
  persona: PersonaPanel, icon: IconPanel, logo: LogoPanel, provider: (p) => <ProviderPanel {...p} />, model: ModelPanel,
  rules: RulesPanel, trusted: TrustedPanel, hooks: HooksPanel, mcp: McpPanel, skills: SkillsPanel, plugins: PluginsPanel,
  "voice-test": VoiceTestPanel, camera: CameraPanel, companion: CompanionPanel, schedule: SchedulePanel,
  files: FilesPanel, history: HistoryPanel, codeappearance: CodeAppearancePanel, about: AboutPanel, usage: UsagePanel,
};

export { prettyModel, ago };
