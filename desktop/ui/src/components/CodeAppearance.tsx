// Settings > Appearance > Code, like Claude Code's: a colour theme for light mode and one for dark mode (searchable lists
// with a live preview), the code font, and the code font size. They apply to open files, diffs, code blocks, command
// output and the terminal (see lib/codeThemes.ts).
import { useEffect, useMemo, useRef, useState } from "react";
import { useStore } from "@/lib/store";
import { DARK_THEMES, DEFAULT_CODE_PX, FONT_SIZES, LIGHT_THEMES, themeById, type CodeTheme } from "@/lib/codeThemes";
import { cn } from "@/lib/util";
import { Input, Select } from "./ui";

export function CodeAppearancePanel() {
  const settings = useStore((s) => s.settings);
  const setSetting = useStore((s) => s.setSetting);
  const light = themeById(LIGHT_THEMES, settings.desktop_code_light as string);
  const dark = themeById(DARK_THEMES, settings.desktop_code_dark as string);
  const px = Number(settings.desktop_code_size) || 0;
  const [font, setFont] = useState(String(settings.desktop_code_font || ""));
  useEffect(() => setFont(String(settings.desktop_code_font || "")), [settings.desktop_code_font]);
  const mono = font.trim() ? `"${font.trim().replace(/["\\;{}]/g, "")}", ` : "";

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))" }}>
        <div className="flex min-w-0 flex-col gap-2">
          <ThemePicker themes={LIGHT_THEMES} value={light} onChange={(t) => setSetting("desktop_code_light", t.id === "claude-light" ? "" : t.id)} />
          <Preview t={light} fontFamily={mono} size={px || DEFAULT_CODE_PX} />
        </div>
        <div className="flex min-w-0 flex-col gap-2">
          <ThemePicker themes={DARK_THEMES} value={dark} onChange={(t) => setSetting("desktop_code_dark", t.id === "claude-dark" ? "" : t.id)} />
          <Preview t={dark} fontFamily={mono} size={px || DEFAULT_CODE_PX} />
        </div>
      </div>

      <div className="flex items-center gap-4 border-t border-border-200 pt-3">
        <div className="min-w-[150px] flex-1">
          <div className="text-[12.5px] text-text-100">Code font</div>
          <div className="mt-0.5 text-[11.5px] text-text-400">Use your own monospace font for code and the terminal.</div>
        </div>
        <div className="w-[200px] shrink-0">
          <Input value={font} onChange={(e) => setFont(e.target.value)} placeholder="e.g. JetBrains Mono"
            onBlur={() => font.trim() !== String(settings.desktop_code_font || "") && setSetting("desktop_code_font", font.trim())}
            onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()} />
        </div>
      </div>

      <div className="flex items-center gap-4 border-t border-border-200 pt-3">
        <div className="min-w-[150px] flex-1">
          <div className="text-[12.5px] text-text-100">Code font size</div>
          <div className="mt-0.5 text-[11.5px] text-text-400">Applies to open files, diffs, code blocks, command output, and the terminal.</div>
        </div>
        <Select value={String(px)} className="min-w-[150px]"
          options={FONT_SIZES.map((n) => ({ value: String(n), label: n === 0 ? `Default · ${DEFAULT_CODE_PX} px` : `${n} px` }))}
          onChange={(v) => setSetting("desktop_code_size", Number(v) || 0)} />
      </div>
    </div>
  );
}

/** A searchable list of themes in a dropdown, as in Claude Code. */
function ThemePicker({ themes, value, onChange }: { themes: CodeTheme[]; value: CodeTheme; onChange: (t: CodeTheme) => void }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const down = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const key = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", down);
    document.addEventListener("keydown", key);
    return () => { document.removeEventListener("mousedown", down); document.removeEventListener("keydown", key); };
  }, [open]);
  const shown = useMemo(() => themes.filter((t) => t.name.toLowerCase().includes(q.trim().toLowerCase())), [themes, q]);
  return (
    <div ref={box} className="relative">
      <button onClick={() => { setOpen(!open); setQ(""); }}
        className="flex h-[28px] w-full items-center justify-between gap-2 rounded-[6px] bg-bg-400 px-2.5 text-[12px] text-text-100 hover:brightness-110">
        <span className="truncate">{value.name}</span>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="shrink-0 text-text-400"><path d="m6 9 6 6 6-6" /></svg>
      </button>
      {open && (
        <div className="absolute left-0 right-0 top-[32px] z-30 overflow-hidden rounded-[8px] border border-border-300 bg-menu shadow-menu">
          <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search"
            className="h-[30px] w-full border-b border-border-200 bg-transparent px-3 text-[12px] text-text-100 outline-none placeholder:text-text-500 selectable" />
          <div className="max-h-[260px] overflow-y-auto py-1">
            {shown.map((t) => (
              <button key={t.id} onClick={() => { onChange(t); setOpen(false); }}
                className={cn("flex h-[26px] w-full items-center justify-between gap-2 px-3 text-left text-[12px] text-text-100 hover:bg-hover", t.id === value.id && "bg-bg-400")}>
                <span className="truncate">{t.name}</span>
                {t.id === value.id && <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" className="shrink-0 text-accent"><path d="m5 12 5 5 9-10" /></svg>}
              </button>
            ))}
            {!shown.length && <div className="px-3 py-2 text-[11.5px] text-text-400">No theme matches.</div>}
          </div>
        </div>
      )}
    </div>
  );
}

/** The small diff from Claude Code's preview, drawn with the theme's own colours. */
function Preview({ t, fontFamily, size }: { t: CodeTheme; fontFamily: string; size: number }) {
  const addBg = t.dark ? "rgba(63,185,80,0.18)" : "rgba(46,160,67,0.16)";
  const delBg = t.dark ? "rgba(248,81,73,0.20)" : "rgba(207,34,46,0.13)";
  const bar = (c: string) => <span style={{ width: 3, alignSelf: "stretch", background: c, flex: "none" }} />;
  const ln = (n: number, bg: string | undefined, mark: string | undefined, children: React.ReactNode) => (
    <div style={{ display: "flex", background: bg, minHeight: size * 1.6 }}>
      {mark ? bar(mark) : <span style={{ width: 3, flex: "none" }} />}
      <span style={{ width: 28, textAlign: "right", paddingRight: 10, color: t.comment, flex: "none", userSelect: "none" }}>{n}</span>
      <span style={{ whiteSpace: "pre" }}>{children}</span>
    </div>
  );
  const c = (color: string, text: string) => <span style={{ color }}>{text}</span>;
  return (
    <div className="overflow-hidden rounded-[8px] border border-border-300"
      style={{ background: t.bg, color: t.fg, fontFamily: `${fontFamily}"Cascadia Code", "Cascadia Mono", Consolas, monospace`, fontSize: size, lineHeight: 1.6, padding: "8px 0" }}>
      {ln(1, undefined, undefined, <>{c(t.keyword, "function")} {c(t.fn, "greet")}({c(t.attr, "name")}: {c(t.type, "string")}) {"{"}</>)}
      {ln(2, delBg, t.dark ? "#f85149" : "#cf222e", <>  {c(t.keyword, "return")} {c(t.string, '"Hello, "')} + name;</>)}
      {ln(2, addBg, t.dark ? "#3fb950" : "#2da44e", <>  {c(t.keyword, "return")} {c(t.string, "`Hello, ${name}!`")};</>)}
      {ln(3, undefined, undefined, "}")}
    </div>
  );
}
