// The HTTP panel: an API tester. Method, address, query parameters, headers and a body (JSON, text or form); the
// request is sent by Emilie's background process (no CORS, local servers reachable), and the response comes back with
// its status, time, size, headers and body (JSON pretty-printed, HTML previewable, images shown). Requests are kept
// per project; one can be copied as curl or put in the message to Emilie.
import { useEffect, useMemo, useState } from "react";
import { post } from "@/lib/api";
import { highlight } from "@/lib/markdown";
import { useStore } from "@/lib/store";
import { cn, uid } from "@/lib/util";
import { insertIntoComposer } from "./Composer";
import * as I from "./icons";
import { agoSecs, btnPrimary, btnSm, Card, copy, fmtBytes, Heading, Hint, IconBtn, Pill, remember, RowBtn, rowCls } from "./PaneKit";
import { Menu, MenuContent, MenuItem, MenuSep, MenuTrigger, Spinner } from "./ui";

type KV = { k: string; v: string; on: boolean };
type BodyType = "none" | "json" | "text" | "form";
interface Req { method: string; url: string; headers: KV[]; body: string; bodyType: BodyType; form: KV[] }
interface Resp {
  status?: number; reason?: string; url?: string; redirected?: boolean; headers?: [string, string][]; ms: number; size?: number;
  cut?: boolean; type?: string; body?: string; image?: string; binary?: boolean; error?: string;
}
interface Hist { id: string; method: string; url: string; status?: number; ms: number; at: number; req: Req }
interface Opts { insecure: boolean; follow: boolean; timeout: number }
interface Saved { req: Req; history: Hist[]; opts: Opts }

const METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"];
const M_TONE: Record<string, string> = { GET: "text-ok", POST: "text-warn", PUT: "text-link", PATCH: "text-link", DELETE: "text-danger", HEAD: "text-text-300", OPTIONS: "text-text-300" };
const EMPTY: Req = { method: "GET", url: "", headers: [{ k: "", v: "", on: true }], body: "", bodyType: "none", form: [{ k: "", v: "", on: true }] };
const mem = new Map<string, { resp: Resp | null; tab: string; rtab: string }>();

function load(key: string): Saved {
  try {
    const s = JSON.parse(localStorage.getItem(key) || "null");
    if (s?.req) return { req: { ...EMPTY, ...s.req }, history: s.history || [], opts: { insecure: false, follow: true, timeout: 30, ...s.opts } };
  } catch { /* fresh */ }
  return { req: EMPTY, history: [], opts: { insecure: false, follow: true, timeout: 30 } };
}

/** The query of an address as rows, and back. */
function paramsOf(url: string): KV[] {
  const i = url.indexOf("?");
  if (i < 0) return [];
  return url.slice(i + 1).split("#")[0].split("&").filter(Boolean).map((p) => {
    const [k, ...v] = p.split("=");
    const dec = (s: string) => { try { return decodeURIComponent(s.replace(/\+/g, " ")); } catch { return s; } };
    return { k: dec(k), v: dec(v.join("=")), on: true };
  });
}
function withParams(url: string, ps: KV[]): string {
  const base = url.split("?")[0];
  const hash = url.includes("#") ? url.slice(url.indexOf("#")) : "";
  const q = ps.filter((p) => p.k).map((p) => `${encodeURIComponent(p.k)}=${encodeURIComponent(p.v)}`).join("&");
  return base + (q ? "?" + q : "") + hash;
}
const sh = (s: string) => `'${s.replace(/'/g, `'\\''`)}'`;

function bodyOf(r: Req): string {
  if (r.bodyType === "none" || r.method === "GET" || r.method === "HEAD") return "";
  if (r.bodyType === "form") return r.form.filter((f) => f.on && f.k).map((f) => `${encodeURIComponent(f.k)}=${encodeURIComponent(f.v)}`).join("&");
  return r.body;
}
function headersOf(r: Req): [string, string][] {
  const hs: [string, string][] = r.headers.filter((h) => h.on && h.k.trim()).map((h) => [h.k.trim(), h.v]);
  const ct = { json: "application/json", text: "text/plain; charset=utf-8", form: "application/x-www-form-urlencoded", none: "" }[r.bodyType];
  if (ct && bodyOf(r) && !hs.some(([k]) => k.toLowerCase() === "content-type")) hs.push(["Content-Type", ct]);
  return hs;
}
function curl(r: Req): string {
  const body = bodyOf(r);
  return [`curl -X ${r.method} ${sh(r.url)}`, ...headersOf(r).map(([k, v]) => `-H ${sh(`${k}: ${v}`)}`), ...(body ? [`--data-raw ${sh(body)}`] : [])].join(" \\\n  ");
}

export function HttpPane({ cwd }: { cwd: string }) {
  const key = "emilie.http:" + (cwd || "~");
  const m = remember(mem, key, () => ({ resp: null as Resp | null, tab: "params", rtab: "body" }));
  const toast = useStore((s) => s.toast);
  const [saved] = useState(() => load(key));
  const [req, setReq] = useState<Req>(saved.req);
  const [history, setHistory] = useState<Hist[]>(saved.history);
  const [opts, setOpts] = useState<Opts>(saved.opts);
  const [resp, setRespState] = useState<Resp | null>(m.resp);
  const setResp = (r: Resp | null) => { m.resp = r; setRespState(r); };
  const [tab, setTabState] = useState(m.tab);
  const setTab = (t: string) => { m.tab = t; setTabState(t); };
  const [rtab, setRtabState] = useState(m.rtab);
  const setRtab = (t: string) => { m.rtab = t; setRtabState(t); };
  const [sending, setSending] = useState(false);
  const [histOpen, setHistOpen] = useState(true);
  const [preview, setPreview] = useState(false);

  useEffect(() => {
    const t = window.setTimeout(() => {
      try { localStorage.setItem(key, JSON.stringify({ req, history: history.slice(0, 40), opts })); } catch { /* full */ }
    }, 300);
    return () => clearTimeout(t);
  }, [req, history, opts, key]);

  const set = (p: Partial<Req>) => setReq((r) => ({ ...r, ...p }));
  const params = useMemo(() => paramsOf(req.url), [req.url]);
  const canBody = req.method !== "GET" && req.method !== "HEAD";

  const send = async () => {
    if (!req.url.trim() || sending) return;
    setSending(true);
    try {
      const r = await post<Resp>("/api/http/send", { method: req.method, url: req.url.trim(), headers: headersOf(req), body: bodyOf(req), ...opts });
      setResp(r);
      setPreview(false);
      setHistory((h) => [{ id: uid("h"), method: req.method, url: req.url.trim(), status: r.status, ms: r.ms, at: Date.now() / 1000, req },
        ...h.filter((x) => !(x.method === req.method && x.url === req.url.trim()))].slice(0, 40));
    } catch (e: any) {
      setResp({ error: e.message, ms: 0 });
    } finally {
      setSending(false);
    }
  };

  const pretty = useMemo(() => {
    const b = resp?.body || "";
    if (!b) return { text: "", lang: "" };
    const json = /json/i.test(resp?.type || "") || /^\s*[[{]/.test(b);
    if (json) { try { return { text: JSON.stringify(JSON.parse(b), null, 2), lang: "json" }; } catch { /* not JSON after all */ } }
    if (/html/i.test(resp?.type || "")) return { text: b, lang: "html" };
    if (/xml/i.test(resp?.type || "")) return { text: b, lang: "xml" };
    return { text: b, lang: "" };
  }, [resp]);
  const html = useMemo(() => (pretty.lang && pretty.text.length < 300000 ? highlight(pretty.text, pretty.lang) : ""), [pretty]);

  const attach = () => {
    if (!resp) return;
    const reqBody = bodyOf(req);
    const head = (resp.headers || []).filter(([k]) => /^(content-type|location|www-authenticate|set-cookie|x-)/i.test(k)).map(([k, v]) => `${k}: ${v}`).join("\n");
    const b = (pretty.text || resp.body || "").slice(0, 4000);
    insertIntoComposer(`\nI sent ${req.method} ${req.url}${reqBody ? ` with this body:\n\`\`\`\n${reqBody.slice(0, 2000)}\n\`\`\`` : ""}\n` +
      (resp.error ? `It failed: ${resp.error}\n` : `The answer was ${resp.status} ${resp.reason || ""} in ${resp.ms} ms${head ? `\n${head}` : ""}\n\`\`\`${pretty.lang}\n${b}${(resp.body || "").length > 4000 ? "\n…" : ""}\n\`\`\`\n`));
    toast("Added to the message box");
  };

  const tone = !resp?.status ? "" : resp.status < 300 ? "bg-ok/15 text-ok" : resp.status < 400 ? "bg-accent-soft text-link" : resp.status < 500 ? "bg-warn-soft text-warn" : "bg-danger-soft text-danger";
  const nHeaders = req.headers.filter((h) => h.on && h.k).length;

  return (
    <div className="flex h-full flex-col text-[11.5px]">
      {/* the request line */}
      <div className="flex items-center gap-1.5 px-2.5 pt-2">
        <div className="flex min-w-0 flex-1 items-center rounded-[7px] border border-border-300 bg-bg-200/40 focus-within:border-border-400">
          <Menu>
            <MenuTrigger asChild>
              <button className={cn("flex h-[26px] shrink-0 items-center gap-1 rounded-l-[7px] border-r border-border-300 pl-2 pr-1.5 font-mono text-[11px] font-semibold hover:bg-hover", M_TONE[req.method])}>
                {req.method}<I.ChevD size={9} className="text-text-400" />
              </button>
            </MenuTrigger>
            <MenuContent align="start" className="min-w-[120px]">
              {METHODS.map((x) => (
                // a method that carries a body starts with a JSON one
                <MenuItem key={x} checked={x === req.method} onSelect={() => set({ method: x, ...(["POST", "PUT", "PATCH"].includes(x) && req.bodyType === "none" ? { bodyType: "json" as BodyType } : {}) })}>
                  <span className={cn("font-mono text-[11px] font-semibold", M_TONE[x])}>{x}</span>
                </MenuItem>
              ))}
            </MenuContent>
          </Menu>
          <input value={req.url} onChange={(e) => set({ url: e.target.value })} placeholder="http://localhost:3000/api/…" spellCheck={false}
            onKeyDown={(e) => { if (e.key === "Enter") send(); }}
            className="h-[26px] min-w-0 flex-1 bg-transparent px-2 font-mono text-[11px] text-text-100 outline-none placeholder:text-text-500 selectable" />
        </div>
        <button className={cn(btnPrimary, "h-[26px] px-3")} disabled={!req.url.trim() || sending} onClick={send}>{sending ? <Spinner size={11} className="text-current" /> : <I.SendIcon size={12} />}Send</button>
        <Menu>
          <MenuTrigger asChild><button aria-label="Options" className="flex h-[26px] w-[22px] items-center justify-center rounded-[5px] text-text-300 hover:bg-hover hover:text-text-000"><I.Dots size={13} /></button></MenuTrigger>
          <MenuContent align="end" className="min-w-[250px]">
            <MenuItem checked={opts.follow} onSelect={(e) => { e.preventDefault(); setOpts({ ...opts, follow: !opts.follow }); }}>Follow redirects</MenuItem>
            <MenuItem checked={opts.insecure} onSelect={(e) => { e.preventDefault(); setOpts({ ...opts, insecure: !opts.insecure }); }}>Allow self-signed certificates</MenuItem>
            <MenuSep />
            {[10, 30, 120].map((t) => <MenuItem key={t} checked={opts.timeout === t} onSelect={() => setOpts({ ...opts, timeout: t })}>Time out after {t} s</MenuItem>)}
            <MenuSep />
            <MenuItem disabled={!req.url} onSelect={() => copy(curl(req), "Copied as curl")}>Copy as curl</MenuItem>
            <MenuItem onSelect={() => { setReq(EMPTY); setResp(null); }}>New request</MenuItem>
          </MenuContent>
        </Menu>
      </div>

      {/* what goes with it */}
      <div className="mt-1.5 flex items-center gap-1 px-2.5">
        <Pill on={tab === "params"} onClick={() => setTab("params")}>Params{params.length ? <span className="tabular-nums text-text-500">{params.length}</span> : null}</Pill>
        <Pill on={tab === "headers"} onClick={() => setTab("headers")}>Headers{nHeaders ? <span className="tabular-nums text-text-500">{nHeaders}</span> : null}</Pill>
        <Pill on={tab === "body"} onClick={() => setTab("body")}>Body{canBody && req.bodyType !== "none" ? <span className="h-[5px] w-[5px] rounded-full bg-accent" /> : null}</Pill>
      </div>
      <div className="max-h-[38%] shrink-0 overflow-y-auto px-2.5 pt-1.5">
        {tab === "params" && <KVRows rows={params.length ? params : []} onChange={(ps) => set({ url: withParams(req.url, ps) })} placeholder="parameter" noToggle />}
        {tab === "headers" && <KVRows rows={req.headers} onChange={(headers) => set({ headers })} placeholder="header" />}
        {tab === "body" && (
          !canBody ? <Hint>A {req.method} request has no body. Choose POST, PUT or PATCH to send one.</Hint> : (
            <div>
              <div className="mb-1.5 flex items-center gap-1">
                {(["none", "json", "text", "form"] as BodyType[]).map((t) => <Pill key={t} on={req.bodyType === t} onClick={() => set({ bodyType: t })}>{{ none: "None", json: "JSON", text: "Text", form: "Form" }[t]}</Pill>)}
                <span className="flex-1" />
                {req.bodyType === "json" && <button className={btnSm} onClick={() => { try { set({ body: JSON.stringify(JSON.parse(req.body), null, 2) }); } catch (e: any) { toast("Not valid JSON: " + e.message, "error"); } }}><I.Braces size={10} />Format</button>}
              </div>
              {(req.bodyType === "json" || req.bodyType === "text") && (
                <textarea value={req.body} onChange={(e) => set({ body: e.target.value })} spellCheck={false} rows={6}
                  placeholder={req.bodyType === "json" ? '{\n  "name": "Ana"\n}' : "Text to send"}
                  onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); send(); } }}
                  className="block w-full resize-y rounded-[7px] border border-border-300 bg-bg-200/40 px-2.5 py-1.5 font-mono text-[11px] leading-[16px] text-text-100 outline-none focus:border-border-400 placeholder:text-text-500 selectable" />
              )}
              {req.bodyType === "form" && <KVRows rows={req.form} onChange={(form) => set({ form })} placeholder="field" />}
            </div>
          )
        )}
      </div>

      {/* the answer */}
      <div className="mt-2 min-h-0 flex-1 overflow-y-auto border-t border-border-300 px-2.5 pb-3 dark:border-[#353535]">
        {!resp && !sending && <Hint className="mt-3">Type an address and press Enter. Requests go out from this computer, so local servers work without CORS.</Hint>}
        {sending && <div className="mt-3 flex items-center gap-2 text-[11px] text-text-400"><Spinner size={12} />Waiting for {req.url.replace(/^https?:\/\//, "").split("/")[0]}…</div>}
        {resp?.error && !sending && (
          <div className="mt-2.5 rounded-[8px] bg-danger-soft px-2.5 py-2 text-[11px] text-danger selectable">
            <div className="font-medium">The request failed{resp.ms ? ` after ${resp.ms} ms` : ""}</div>
            <div className="mt-0.5">{resp.error}</div>
          </div>
        )}
        {resp?.status !== undefined && !sending && (
          <>
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <span className={cn("rounded-[5px] px-1.5 py-[1px] font-mono text-[11px] font-semibold", tone)}>{resp.status} {resp.reason}</span>
              <span className="text-[10.5px] text-text-500">{resp.ms} ms · {fmtBytes(resp.size || 0)}{resp.cut ? " (cut)" : ""}{resp.redirected ? " · redirected" : ""}</span>
              <span className="flex-1" />
              <Pill on={rtab === "body"} onClick={() => setRtab("body")}>Body</Pill>
              <Pill on={rtab === "headers"} onClick={() => setRtab("headers")}>Headers <span className="tabular-nums text-text-500">{resp.headers?.length || 0}</span></Pill>
              <IconBtn tip="Copy the body" disabled={!resp.body} onClick={() => copy(pretty.text || resp.body || "", "Body copied")}><I.Copy size={11} /></IconBtn>
              <IconBtn tip="Attach the request and answer to the message" onClick={attach}><I.AtSign size={11} /></IconBtn>
            </div>
            {resp.redirected && resp.url && <div className="mt-1 truncate font-mono text-[10px] text-text-500" title={resp.url}>→ {resp.url}</div>}
            {rtab === "headers" && (
              <Card className="mt-2">
                {(resp.headers || []).map(([k, v], i) => (
                  <div key={i} className={cn("flex min-w-0 gap-2 px-3 py-[3px] font-mono text-[10.5px]", i > 0 && "border-t border-border-200")}>
                    <span className="w-[40%] shrink-0 truncate text-text-400" title={k}>{k}</span>
                    <span className="min-w-0 flex-1 break-all text-text-100 selectable">{v}</span>
                  </div>
                ))}
              </Card>
            )}
            {rtab === "body" && (
              <div className="mt-2">
                {resp.image && <img src={resp.image} alt="" className="max-h-[360px] max-w-full rounded-[7px] border border-border-300" />}
                {resp.binary && <Hint>Binary content ({resp.type || "unknown type"}, {fmtBytes(resp.size || 0)}).</Hint>}
                {!resp.image && !resp.binary && !resp.body && <Hint>(empty body)</Hint>}
                {pretty.lang === "html" && !!resp.body && (
                  <div className="mb-1.5 flex gap-1"><Pill on={!preview} onClick={() => setPreview(false)}>Source</Pill><Pill on={preview} onClick={() => setPreview(true)}>Preview</Pill></div>
                )}
                {preview && pretty.lang === "html"
                  ? <iframe sandbox="" srcDoc={resp.body} title="preview" className="h-[360px] w-full rounded-[7px] border border-border-300 bg-white" />
                  : !!resp.body && (
                    <pre className="max-h-[520px] overflow-auto whitespace-pre-wrap break-words rounded-[7px] border border-border-300 px-2.5 py-2 font-mono text-[10.5px] leading-[15px] text-text-100 selectable"
                      style={{ background: "var(--code-bg-custom, var(--code-bg))" }}>
                      {html ? <code className="hljs" dangerouslySetInnerHTML={{ __html: html }} /> : pretty.text}
                    </pre>
                  )}
              </div>
            )}
          </>
        )}

        {!!history.length && (
          <>
            <Heading title="History" note={history.length} open={histOpen} onToggle={() => setHistOpen(!histOpen)}
              right={<button className="text-[10.5px] text-text-500 hover:text-text-100" onClick={() => setHistory([])}>Clear</button>} />
            {histOpen && (
              <Card>
                {history.map((h, i) => (
                  <div key={h.id} role="button" onClick={() => { setReq({ ...EMPTY, ...h.req }); setResp(null); }} title={h.url}
                    className={cn(rowCls, "h-[24px] gap-1.5", i > 0 && "border-t border-border-200")}>
                    <span className={cn("w-[44px] shrink-0 font-mono text-[10px] font-semibold", M_TONE[h.method])}>{h.method}</span>
                    <span className="min-w-0 flex-1 truncate font-mono text-[10.5px] text-text-200">{h.url.replace(/^https?:\/\//, "")}</span>
                    <RowBtn tip="Remove" onClick={() => setHistory((x) => x.filter((y) => y.id !== h.id))}><I.X size={10} /></RowBtn>
                    {h.status !== undefined && <span className={cn("shrink-0 font-mono text-[10px]", h.status < 300 ? "text-ok" : h.status < 400 ? "text-link" : h.status < 500 ? "text-warn" : "text-danger")}>{h.status}</span>}
                    <span className="w-[54px] shrink-0 text-right text-[10px] text-text-500">{agoSecs(h.at)}</span>
                  </div>
                ))}
              </Card>
            )}
          </>
        )}
      </div>
    </div>
  );
}

/** Key / value rows with an always-empty last row to type a new one into. */
function KVRows({ rows, onChange, placeholder, noToggle }: { rows: KV[]; onChange: (r: KV[]) => void; placeholder: string; noToggle?: boolean }) {
  const list = rows.length && !rows[rows.length - 1].k && !rows[rows.length - 1].v ? rows : [...rows, { k: "", v: "", on: true }];
  const put = (i: number, p: Partial<KV>) => {
    const n = list.map((r, j) => (j === i ? { ...r, ...p } : r));
    onChange(n.filter((r, j) => r.k || r.v || j === n.length - 1));
  };
  const field = "h-[22px] min-w-0 rounded-[5px] border border-transparent bg-bg-200/60 px-1.5 font-mono text-[10.5px] text-text-100 outline-none focus:border-border-400 placeholder:text-text-500 selectable";
  return (
    <div className="flex flex-col gap-1">
      {list.map((r, i) => {
        const last = i === list.length - 1;
        return (
          <div key={i} className="group flex items-center gap-1">
            {!noToggle && (
              <input type="checkbox" checked={r.on} disabled={last} onChange={(e) => put(i, { on: e.target.checked })} aria-label="Send it"
                className="h-[12px] w-[12px] shrink-0 accent-[var(--accent)]" />
            )}
            <input value={r.k} onChange={(e) => put(i, { k: e.target.value })} placeholder={last ? `New ${placeholder}` : placeholder} spellCheck={false}
              className={cn(field, "w-[38%]", !r.on && "opacity-50")} />
            <input value={r.v} onChange={(e) => put(i, { v: e.target.value })} placeholder="value" spellCheck={false}
              className={cn(field, "flex-1", !r.on && "opacity-50")} />
            {!last
              ? <button aria-label="Remove" onClick={() => onChange(list.filter((_, j) => j !== i))} className="flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded text-text-500 hover:text-danger"><I.X size={10} /></button>
              : <span className="w-[18px] shrink-0" />}
          </div>
        );
      })}
    </div>
  );
}
