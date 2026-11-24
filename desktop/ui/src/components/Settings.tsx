// Settings as a floating window, like the Claude Code desktop app: a search box and grouped sections on the left,
// rows with the label and description on the left and the control on the right. Drawn from the server's schema
// (emilie/desktop/schema.py), so a new setting needs no UI code.
import { useShallow } from "zustand/react/shallow";
import { useEffect, useMemo, useRef, useState } from "react";
import { Dialog as D } from "radix-ui";
import { useStore } from "@/lib/store";
import type { Field, Section } from "@/lib/types";
import { cn } from "@/lib/util";
import * as I from "./icons";
import { Input, Segmented, Select, Switch, TextArea } from "./ui";
import { CUSTOM } from "./SettingsPanels";

const ICONS: Record<string, React.ReactNode> = {
  user: <I.User size={13} />, cpu: <I.Cpu size={13} />, palette: <I.Palette size={13} />, sparkles: <I.Sparkles size={13} />,
  mic: <I.Mic size={13} />, bell: <I.Bell size={13} />, shield: <I.Shield size={13} />, case: <I.CustomizeIcon size={13} />,
  code: <I.CodeBrackets size={13} />, monitor: <I.Monitor size={13} />, settings: <I.Settings size={13} />,
  gauge: <I.Gauge size={13} />,
};

export function Settings() {
  const s = useStore(useShallow((st) => ({ loadSettings: st.loadSettings, schema: st.schema, settingsOpen: st.settingsOpen })));
  const [q, setQ] = useState("");
  const body = useRef<HTMLDivElement>(null);
  const close = () => useStore.setState({ settingsOpen: null });
  const sec = s.schema?.find((x) => x.id === s.settingsOpen) || s.schema?.[0];
  useEffect(() => { s.loadSettings().catch(() => {}); }, []);
  useEffect(() => { body.current?.scrollTo({ top: 0 }); }, [sec?.id, q]);

  const hits = useMemo(() => {
    const ql = q.trim().toLowerCase();
    if (!ql || !s.schema) return null;
    const out: { sec: Section; fields: Field[] }[] = [];
    for (const x of s.schema) {
      const fields = x.groups.flatMap((g) => g.fields).filter((f) =>
        `${f.label} ${f.desc || ""} ${x.label} ${f.key}`.toLowerCase().includes(ql));
      if (fields.length) out.push({ sec: x, fields });
    }
    return out;
  }, [q, s.schema]);

  if (!s.schema || !sec) return null;
  let lastGroup = s.schema[0]?.group;
  return (
    <D.Root open onOpenChange={(o) => !o && close()}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-[60] bg-black/60 animate-fade-in" />
        <D.Content aria-describedby={undefined}
          className="fixed left-1/2 top-1/2 z-[61] flex -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-[10px] border border-border-200 bg-bg-200 text-text-100 shadow-menu outline-none animate-pop"
          style={{ width: "min(776px, calc(100vw - 32px))", height: "min(607px, calc(100vh - 48px))" }}>
          <div className="flex h-[33px] shrink-0 items-center justify-between border-b border-border-400 pl-3 pr-1.5">
            <D.Title className="text-[12px] font-semibold">Settings</D.Title>
            <D.Close asChild>
              <button aria-label="Close" className="flex h-[24px] w-[24px] items-center justify-center rounded-[5px] text-text-100 hover:bg-hover">
                <I.X size={14} />
              </button>
            </D.Close>
          </div>
          <div className="flex min-h-0 flex-1">
            <nav className="flex w-[160px] shrink-0 flex-col overflow-y-auto border-r border-border-300 bg-bg-100 px-[10px] py-2">
              <label className="mb-2 flex h-[22px] shrink-0 items-center gap-1.5 rounded-[5px] bg-bg-300 px-2">
                <I.SearchSm size={11} className="text-text-400" />
                <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search"
                  className="min-w-0 flex-1 bg-transparent text-[11.5px] text-text-100 outline-none placeholder:text-text-400 selectable" />
              </label>
              {s.schema.map((x) => {
                const sep = x.group !== lastGroup;
                lastGroup = x.group;
                return (
                  <div key={x.id}>
                    {sep && <div className="mx-1 my-2 h-px bg-border-300" />}
                    <button onClick={() => { setQ(""); useStore.setState({ settingsOpen: x.id }); }}
                      className={cn("flex h-[25px] w-full items-center gap-2 rounded-[6px] px-2 text-left text-[11.5px] text-text-100 transition-colors",
                        !q && x.id === sec.id ? "bg-active dark:bg-[#3b3b3b]" : "hover:bg-hover")}>
                      <span className="flex w-[13px] justify-center">{ICONS[x.icon] || <I.Settings size={13} />}</span>{x.label}
                    </button>
                  </div>
                );
              })}
            </nav>
            <div ref={body} className="min-w-0 flex-1 overflow-y-auto px-[13px] pb-6 pt-[14px]">
              {hits ? (
                hits.length ? hits.map(({ sec: x, fields }) => (
                  <section key={x.id} className="mb-5">
                    <h2 className="mb-0.5 text-[12px] font-semibold">{x.label}</h2>
                    <Rows fields={fields} />
                  </section>
                )) : <div className="pt-6 text-center text-[11.5px] text-text-400">No settings match “{q}”.</div>
              ) : (
                <>
                  <h2 className="mb-0.5 text-[12px] font-semibold">{sec.label}</h2>
                  {sec.groups.map((g, gi) => (
                    <section key={gi} className={cn(gi > 0 && "mt-4")}>
                      {g.title && <h3 className="mb-0.5 mt-2 text-[11px] font-semibold text-text-300">{g.title}</h3>}
                      <Rows fields={g.fields} />
                    </section>
                  ))}
                </>
              )}
            </div>
          </div>
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}

function Rows({ fields }: { fields: Field[] }) {
  return (
    <div className="divide-y divide-border-200">
      {fields.map((f) => <FieldRow key={f.key} f={f} />)}
    </div>
  );
}

function FieldRow({ f }: { f: Field }) {
  const custom = f.type.startsWith("custom:") ? CUSTOM[f.type.slice(7)] : null;
  if (custom) {
    const C = custom;
    return (
      <div className="py-[9px]">
        {f.label && <div className="text-[11.5px] font-medium text-text-100">{f.label}</div>}
        {f.desc && <div className="mt-px text-[10.5px] leading-snug text-text-400">{f.desc}</div>}
        <div className={cn((f.label || f.desc) && "mt-2")}><C field={f} /></div>
      </div>
    );
  }
  const wide = f.type === "textarea";
  const desc = f.key === "desktop_accent" && f.desc ? f.desc.replace(/Emilie's pink/i, "Original") : f.desc;
  return (
    <div className={cn("flex gap-4 py-[9px]", wide ? "flex-col" : "items-center")}>
      <div className="min-w-0 flex-1">
        <div className="text-[11.5px] font-medium text-text-100">{f.label}</div>
        {desc && <div className="mt-px text-[10.5px] leading-snug text-text-400">{desc}</div>}
        {f.live === false && <div className="mt-px text-[10px] text-text-500">Applies to new sessions</div>}
      </div>
      <div className={cn("shrink-0", wide && "w-full")}><Control f={f} /></div>
    </div>
  );
}

function Control({ f }: { f: Field }) {
  const value = useStore((s) => s.settings[f.key]);
  const setSetting = useStore((s) => s.setSetting);
  const v = value ?? f.default;
  switch (f.type) {
    case "toggle":
      return <Switch checked={!!v} onChange={(x) => setSetting(f.key, x)} />;
    case "segmented": {
      const opts = (f.choices || []).map((c) => ({
        value: c.value,
        label: f.key === "desktop_accent" && (c.value === "sakura" || c.label === "Sakura") ? "Original" : c.label,
      }));
      return <Segmented value={String(v ?? "")} onChange={(x) => setSetting(f.key, x)} options={opts} />;
    }
    case "select":
      return <SelectControl f={f} value={v} />;
    case "number":
      return <TextControl f={f} value={v} type="number" />;
    case "password":
      return <TextControl f={f} value={v} type="password" />;
    case "textarea":
      return <TextControl f={f} value={v} type="textarea" />;
    default:
      return <TextControl f={f} value={v} type="text" />;
  }
}

function SelectControl({ f, value }: { f: Field; value: any }) {
  const setSetting = useStore((s) => s.setSetting);
  const known = (f.choices || []).some((c) => c.value === value);
  const [custom, setCustom] = useState(!known && value != null && value !== "");
  if (custom) {
    return (
      <div className="flex items-center gap-2">
        <TextControl f={f} value={value} type="text" />
        <button className="text-[11px] text-text-400 hover:text-text-100" onClick={() => setCustom(false)}>List</button>
      </div>
    );
  }
  const opts = (f.choices || []).map((c) => ({ value: c.value, label: c.label }));
  if (f.allow_custom) opts.push({ value: "__custom__", label: "Other…" });
  return <Select value={String(value ?? "")} options={opts} onChange={(x) => (x === "__custom__" ? setCustom(true) : setSetting(f.key, x))} />;
}

function TextControl({ f, value, type }: { f: Field; value: any; type: "text" | "number" | "password" | "textarea" }) {
  const setSetting = useStore((s) => s.setSetting);
  const [v, setV] = useState(value == null ? "" : String(value));
  useEffect(() => setV(value == null ? "" : String(value)), [value]);
  const commit = () => {
    const cur = value == null ? "" : String(value);
    if (v === cur) return;
    if (type === "number") setSetting(f.key, v.trim() === "" ? null : Number(v));
    else setSetting(f.key, v);
  };
  if (type === "textarea") return <TextArea value={v} rows={6} onChange={(e) => setV(e.target.value)} onBlur={commit} placeholder={f.placeholder} />;
  return (
    <Input type={type} value={v} min={f.min} max={f.max} step={f.step ?? (type === "number" ? 1 : undefined)}
      placeholder={f.placeholder ?? (f.default != null ? String(f.default) : "")}
      onChange={(e) => setV(e.target.value)} onBlur={commit} onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
      className={cn(type === "number" ? "w-[100px]" : "w-[166px]")} />
  );
}
