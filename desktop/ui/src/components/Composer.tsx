// The message box: text, attachments, / commands, @ files, mic, send / stop. Same behaviour as the terminal input.
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useStore } from "@/lib/store";
import type { Command } from "@/lib/types";
import { get as apiGet, post } from "@/lib/api";
import { bridge, pathOfFile } from "@/lib/desktop";
import { type Attachment, basename, cn, readFile, uid } from "@/lib/util";
import { AtSign, Camera, FileIcon, MicSm, Paperclip, Phone, PhoneOff, PlusSm, ReturnKey, Slash, X } from "./icons";
import { Menu, MenuContent, MenuItem, MenuSep, MenuTrigger, Tip } from "./ui";

const LONG_LINES = 4, LONG_CHARS = 500;

export interface ComposerProps {
  draftKey: string;
  busy?: boolean;
  disabled?: boolean;
  commands: Command[];
  cwd: string | null;
  placeholder: string;
  onSend: (text: string, atts: Attachment[], pastes: { n: number; text: string }[]) => void;
  onStop?: () => void;
  onCycleMode?: () => void;
  history?: string[];
  talk?: string;
  onTalk?: (on: boolean) => void;
  call?: boolean;
  onCall?: (on: boolean) => void;
  autoFocus?: boolean;
  onTyping?: () => void;
  footer?: React.ReactNode;
}

type MenuState = { kind: "slash" | "mention"; items: { value: string; label: string; desc?: string; kind?: string }[]; idx: number; start: number; end: number } | null;

export function Composer(p: ComposerProps) {
  const toast = useStore((s) => s.toast);
  const [text, setText] = useState(() => useStore.getState().drafts[p.draftKey] || "");
  const [atts, setAtts] = useState<Attachment[]>([]);
  const [pastes, setPastes] = useState<{ n: number; text: string; lines: number }[]>([]);
  const [menu, setMenu] = useState<MenuState>(null);
  const [drag, setDrag] = useState(false);
  const [hist, setHist] = useState(-1);
  const ta = useRef<HTMLTextAreaElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const mentionTimer = useRef<number | undefined>(undefined);

  useEffect(() => {
    setText(useStore.getState().drafts[p.draftKey] || "");
    setAtts([]);
    setPastes([]);
    setMenu(null);
  }, [p.draftKey]);
  useEffect(() => {
    const t = window.setTimeout(() => useStore.setState({ drafts: { ...useStore.getState().drafts, [p.draftKey]: text } }), 300);
    return () => clearTimeout(t);
  }, [text, p.draftKey]);
  useEffect(() => {
    if (p.autoFocus) ta.current?.focus();
  }, [p.autoFocus, p.draftKey]);
  const insertRef = useRef<(s: string) => void>(() => {});
  useEffect(() => {
    const onFocusReq = () => ta.current?.focus();
    window.addEventListener("emilie:focus-composer", onFocusReq);
    const onInsert = (e: Event) => insertRef.current((e as CustomEvent).detail);
    window.addEventListener("emilie:insert", onInsert);
    return () => {
      window.removeEventListener("emilie:focus-composer", onFocusReq);
      window.removeEventListener("emilie:insert", onInsert);
    };
  }, []);
  useLayoutEffect(() => {
    const el = ta.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = Math.min(el.scrollHeight, Math.round(window.innerHeight * 0.4)) + "px";
  }, [text]);

  const insert = (s: string) => {
    const el = ta.current;
    if (!el) return setText((t) => t + s);
    const a = el.selectionStart, b = el.selectionEnd;
    const next = text.slice(0, a) + s + text.slice(b);
    setText(next);
    requestAnimationFrame(() => {
      el.focus();
      el.selectionStart = el.selectionEnd = a + s.length;
      updateMenu(next, a + s.length);
    });
  };

  insertRef.current = insert;

  // ------------------------------------------------------------------ / and @ menus
  const updateMenu = (value: string, caret: number) => {
    const before = value.slice(0, caret);
    if (/^\/[^\s]*$/.test(before)) {
      const q = before.toLowerCase();
      const items = p.commands
        .filter((c) => c.name.toLowerCase().startsWith(q) || (q.length > 2 && c.name.toLowerCase().includes(q.slice(1))))
        .slice(0, 60)
        .map((c) => ({ value: c.name, label: c.name, desc: c.desc, kind: c.kind }));
      setMenu(items.length ? { kind: "slash", items, idx: 0, start: 0, end: caret } : null);
      return;
    }
    const m = before.match(/(?:^|\s)@([^\s@]*)$/);
    if (m && p.cwd) {
      const start = caret - m[1].length - 1;
      clearTimeout(mentionTimer.current);
      mentionTimer.current = window.setTimeout(async () => {
        try {
          const r = await apiGet<{ items: { path: string; dir: boolean }[] }>("/api/fs/complete", { cwd: p.cwd, q: m[1] });
          const items = r.items.map((x) => ({ value: x.path, label: x.path, kind: x.dir ? "folder" : "file" }));
          setMenu(items.length ? { kind: "mention", items, idx: 0, start, end: caret } : null);
        } catch {
          setMenu(null);
        }
      }, 90);
      return;
    }
    setMenu(null);
  };

  const pick = (i: number) => {
    if (!menu) return;
    const it = menu.items[i];
    if (!it) return;
    const add = menu.kind === "slash" ? it.value + " " : "@" + it.value + (it.kind === "folder" ? "" : " ");
    const next = text.slice(0, menu.start) + add + text.slice(menu.end);
    setText(next);
    setMenu(null);
    requestAnimationFrame(() => {
      const el = ta.current!;
      el.focus();
      el.selectionStart = el.selectionEnd = menu.start + add.length;
      if (it.kind === "folder") updateMenu(next, menu.start + add.length);
    });
  };

  // ------------------------------------------------------------------ attachments
  const addFiles = async (files: File[]) => {
    for (const f of files) {
      if (f.type.startsWith("image/")) {
        try {
          const a = await readFile(f);
          a.path = pathOfFile(f) || undefined;
          setAtts((x) => [...x, a]);
        } catch {
          toast(`could not read ${f.name}`, "error");
        }
      } else {
        const path = pathOfFile(f);
        if (path) setAtts((x) => [...x, { id: uid("a"), kind: "file", name: f.name, path, size: f.size }]);
        else toast("In the browser only images can be attached; drop files into the folder or mention them with @", "error");
      }
    }
  };
  const attachPaths = async (paths: string[]) => {
    if (!paths.length) return;
    try {
      const r = await post<{ items: any[] }>("/api/fs/attach", { paths });
      setAtts((x) => [...x, ...r.items.map((it) => ({
        id: uid("a"), kind: it.kind, name: it.name, path: it.path, mime: it.mime, b64: it.b64, size: it.size,
        url: it.b64 ? `data:${it.mime};base64,${it.b64}` : undefined,
      }) as Attachment)]);
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  const pickFiles = async () => {
    if (bridge) return attachPaths(await bridge.pickFiles({ title: "Add files or photos" }));
    fileInput.current?.click();
  };
  const takePhoto = async () => {
    toast("Taking a photo…");
    try {
      const r = await post<{ mime: string; b64: string; name: string }>("/api/camera/photo", {});
      setAtts((x) => [...x, { id: uid("a"), kind: "image", name: r.name, mime: r.mime, b64: r.b64, url: `data:${r.mime};base64,${r.b64}` }]);
    } catch (e: any) {
      toast(e.message, "error");
    }
  };

  const onPaste = (e: React.ClipboardEvent) => {
    const files = Array.from(e.clipboardData.files || []);
    if (files.length) {
      e.preventDefault();
      addFiles(files);
      return;
    }
    const t = e.clipboardData.getData("text/plain");
    if (!t) return;
    const lines = t.replace(/\n$/, "").split("\n").length;
    if (lines >= LONG_LINES || t.length > LONG_CHARS) {
      e.preventDefault();
      const n = (pastes.reduce((m, x) => Math.max(m, x.n), 0) || 0) + 1;
      setPastes((x) => [...x, { n, text: t.replace(/\r\n/g, "\n").replace(/\n$/, ""), lines }]);
    }
  };

  // ------------------------------------------------------------------ send
  const canSend = !!(text.trim() || atts.length || pastes.length) && !p.disabled;
  const send = () => {
    if (!canSend) return;
    let out = text.trim();
    if (pastes.length) out = [out, ...pastes.map((x) => `[Pasted text #${x.n} +${x.lines} lines]`)].filter(Boolean).join("\n\n");
    p.onSend(out, atts, pastes.map(({ n, text }) => ({ n, text })));
    setText("");
    setAtts([]);
    setPastes([]);
    setMenu(null);
    setHist(-1);
    useStore.setState({ drafts: { ...useStore.getState().drafts, [p.draftKey]: "" } });
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.nativeEvent.isComposing) return;
    if (menu) {
      if (e.key === "ArrowDown") { e.preventDefault(); setMenu({ ...menu, idx: (menu.idx + 1) % menu.items.length }); return; }
      if (e.key === "ArrowUp") { e.preventDefault(); setMenu({ ...menu, idx: (menu.idx - 1 + menu.items.length) % menu.items.length }); return; }
      if (e.key === "Tab" || (e.key === "Enter" && !e.shiftKey)) {
        const it = menu.items[menu.idx];
        const exact = menu.kind === "slash" && text.trim() === it?.value;
        if (!(exact && e.key === "Enter")) { e.preventDefault(); pick(menu.idx); return; }
      }
      if (e.key === "Escape") { e.preventDefault(); setMenu(null); return; }
    }
    if (e.key === "Tab" && e.shiftKey) { e.preventDefault(); p.onCycleMode?.(); return; }
    if (e.key === "Enter" && !e.shiftKey && !e.altKey) { e.preventDefault(); send(); return; }
    if (e.key === "Escape" && p.busy) { e.preventDefault(); p.onStop?.(); return; }
    const h = p.history || [];
    if (e.key === "ArrowUp" && h.length && (text === "" || hist >= 0) && ta.current?.selectionStart === 0) {
      e.preventDefault();
      const i = Math.min(h.length - 1, hist + 1);
      setHist(i);
      setText(h[h.length - 1 - i]);
      return;
    }
    if (e.key === "ArrowDown" && hist >= 0) {
      e.preventDefault();
      const i = hist - 1;
      setHist(i);
      setText(i < 0 ? "" : h[h.length - 1 - i]);
    }
  };

  const talkOn = !!p.talk && p.talk !== "off";
  const sendable = canSend;
  const hasAtt = atts.length > 0 || pastes.length > 0;
  const iconBtn = "flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-[5px] text-text-100 transition-colors hover:bg-hover data-[state=open]:bg-hover disabled:opacity-40";
  return (
    <div className="relative mx-auto w-full" style={{ maxWidth: "var(--col-w)" }}>
      {menu && <CommandMenu menu={menu} onPick={pick} onHover={(i) => setMenu({ ...menu, idx: i })} />}
      <div
        className={cn("relative rounded-[9px] border border-composer-border bg-composer transition-colors focus-within:border-border-400",
          drag && "border-accent")}
        onDragOver={(e) => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); setDrag(true); } }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          setDrag(false);
          if (e.dataTransfer.files.length) {
            e.preventDefault();
            addFiles(Array.from(e.dataTransfer.files));
          }
        }}
      >
        {hasAtt && (
          <div className="flex flex-wrap gap-1.5 px-2 pt-2">
            {atts.map((a) => (
              <div key={a.id} className="group relative">
                {a.kind === "image" && a.url ? (
                  <img src={a.url} alt={a.name} className="h-12 w-12 rounded-md border border-border-400 object-cover" />
                ) : (
                  <div className="flex h-12 w-40 items-center gap-2 rounded-md border border-border-400 bg-bg-300 px-2" title={a.path}>
                    <FileIcon size={15} className="shrink-0 text-text-400" />
                    <div className="min-w-0">
                      <div className="truncate text-[11.5px] text-text-100">{a.name}</div>
                      <div className="truncate text-[10px] text-text-400">{a.path ? basename(a.path.replace(/[\\/][^\\/]*$/, "")) : "file"}</div>
                    </div>
                  </div>
                )}
                <button onClick={() => setAtts((x) => x.filter((y) => y.id !== a.id))} aria-label="Remove"
                  className="absolute -right-1.5 -top-1.5 hidden h-4 w-4 items-center justify-center rounded-full border border-border-400 bg-bg-300 text-text-200 group-hover:flex">
                  <X size={10} />
                </button>
              </div>
            ))}
            {pastes.map((x) => (
              <div key={x.n} className="group relative flex h-12 w-40 flex-col justify-center rounded-md border border-border-400 bg-bg-300 px-2" title={x.text.slice(0, 400)}>
                <div className="text-[11.5px] text-text-100">Pasted text</div>
                <div className="text-[10px] text-text-400">{x.lines} lines · {x.text.length.toLocaleString()} chars</div>
                <button onClick={() => setPastes((y) => y.filter((z) => z.n !== x.n))} aria-label="Remove"
                  className="absolute -right-1.5 -top-1.5 hidden h-4 w-4 items-center justify-center rounded-full border border-border-400 bg-bg-300 text-text-200 group-hover:flex">
                  <X size={10} />
                </button>
              </div>
            ))}
          </div>
        )}
        <div className="flex items-end gap-[3px] px-[5px] pt-[5px] pb-[4px]">
          <Menu>
            <MenuTrigger asChild>
              <button aria-label="Add" className={iconBtn}><PlusSm size={13} /></button>
            </MenuTrigger>
            <MenuContent side="top" align="start" className="min-w-[210px]">
              <MenuItem icon={<Paperclip />} onSelect={pickFiles}>Add files or photos</MenuItem>
              <MenuItem icon={<Camera />} onSelect={takePhoto}>Take a photo</MenuItem>
              <MenuSep />
              <MenuItem icon={<AtSign />} onSelect={() => insert(text && !text.endsWith(" ") ? " @" : "@")} disabled={!p.cwd}>Mention a file</MenuItem>
              <MenuItem icon={<Slash />} onSelect={() => { setText("/"); requestAnimationFrame(() => { ta.current?.focus(); updateMenu("/", 1); }); }}>Commands and skills</MenuItem>
              {p.onCall && (
                <>
                  <MenuSep />
                  <MenuItem icon={p.call ? <PhoneOff /> : <Phone />} onSelect={() => p.onCall!(!p.call)} shortcut="Alt+V">
                    {p.call ? "End video call" : "Start video call"}
                  </MenuItem>
                </>
              )}
            </MenuContent>
          </Menu>
          <input ref={fileInput} type="file" multiple accept="image/*" className="hidden"
            onChange={(e) => { addFiles(Array.from(e.target.files || [])); e.target.value = ""; }} />
          <textarea
            ref={ta}
            value={text}
            rows={1}
            disabled={p.disabled}
            placeholder={p.placeholder}
            onChange={(e) => {
              setText(e.target.value);
              setHist(-1);
              updateMenu(e.target.value, e.target.selectionStart);
              p.onTyping?.();
            }}
            onClick={(e) => updateMenu(text, (e.target as HTMLTextAreaElement).selectionStart)}
            onKeyDown={onKeyDown}
            onPaste={onPaste}
            className="block max-h-[40vh] min-h-[22px] min-w-0 flex-1 resize-none bg-transparent px-1 py-[3px] text-[12px] leading-[16px] text-text-100 outline-none placeholder:text-text-500 selectable"
          />
          {p.call && (
            <span className="mb-[3px] flex h-[16px] items-center gap-1 rounded-[4px] bg-danger-soft px-1.5 text-[10.5px] text-danger">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-danger" />On call
            </span>
          )}
          {p.busy && !sendable ? (
            <Tip content="Stop  Esc">
              <button onClick={p.onStop} aria-label="Stop" className={iconBtn}>
                <span className="h-[9px] w-[9px] rounded-[2px] bg-text-100" />
              </button>
            </Tip>
          ) : sendable ? (
            <Tip content={p.busy ? "Queue message  Enter" : "Send  Enter"}>
              <button onClick={send} aria-label="Send" className={iconBtn}><ReturnKey size={13} /></button>
            </Tip>
          ) : null}
          <Tip content={!p.onTalk ? "Talk mode is available once the session has started" : talkOn ? `Talk mode: ${p.talk} (click to stop)` : "Talk: speak, pause to send"}>
            <button aria-label="Talk" onClick={() => p.onTalk?.(!talkOn)}
              className={cn(iconBtn, talkOn && "bg-accent-soft text-accent hover:bg-accent-soft")}>
              <MicSm size={13} />
            </button>
          </Tip>
        </div>
      </div>
      {p.footer && <div className="mt-[5px] flex h-[22px] min-w-0 items-center gap-[2px] overflow-hidden px-[7px]">{p.footer}</div>}
    </div>
  );
}

function CommandMenu({ menu, onPick, onHover }: { menu: NonNullable<MenuState>; onPick: (i: number) => void; onHover: (i: number) => void }) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    box.current?.querySelector(`[data-i="${menu.idx}"]`)?.scrollIntoView({ block: "nearest" });
  }, [menu.idx]);
  return (
    <div ref={box} className="absolute bottom-full left-0 right-0 z-40 mb-1.5 max-h-[300px] overflow-y-auto rounded-lg border border-border-300 bg-menu p-1 shadow-menu animate-pop">
      {menu.items.map((it, i) => (
        <div key={it.value + i} data-i={i} onMouseDown={(e) => { e.preventDefault(); onPick(i); }} onMouseEnter={() => onHover(i)}
          className={cn("flex h-[26px] items-center gap-3 rounded-[5px] px-2", i === menu.idx && "bg-active")}>
          <span className={cn("shrink-0 font-mono text-[11.5px] text-text-100", menu.kind === "slash" && "min-w-[110px]")}>{it.label}</span>
          {it.desc && <span className="min-w-0 flex-1 truncate text-[11px] text-text-400">{it.desc}</span>}
          {it.kind && it.kind !== "builtin" && <span className="text-[10px] text-text-500">{it.kind}</span>}
        </div>
      ))}
    </div>
  );
}

export function focusComposer() {
  window.dispatchEvent(new Event("emilie:focus-composer"));
}

export function insertIntoComposer(text: string) {
  window.dispatchEvent(new CustomEvent("emilie:insert", { detail: text }));
}
