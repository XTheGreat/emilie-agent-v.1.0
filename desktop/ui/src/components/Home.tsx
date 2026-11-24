// "New session", laid out like the Claude Code desktop app: a small card listing your folders, a second card below,
// and the message box at the bottom. Emilie's icon sits centred above the cards; /logo size (or Settings → Appearance
// → Icon size) makes it bigger or smaller.
import { useShallow } from "zustand/react/shallow";
import { useEffect, useRef, useState } from "react";
import { useStore, folderName } from "@/lib/store";
import { cn } from "@/lib/util";
import { BranchSm, Check, ChevD, LaptopIcon, MessageSquare, PlusSm } from "./icons";
import { Composer, insertIntoComposer } from "./Composer";
import { EmilieIcon } from "./EmilieIcon";
import { ComputerChip, ContextRing, FolderChip, ModeChip, ModelEffortChip, WorktreeToggle } from "./Pickers";
import { Menu, MenuContent, MenuItem, MenuLabel, MenuSep, MenuTrigger, Spinner } from "./ui";

const MODE_ORDER = ["ask", "trust", "plan"];

/** Emilie's icon follows /logo size (the terminal's number, 12 to 80 columns; about 3.2px each, so 26 ≈ the default
 *  84px). It never grows past what fits above the centred cards, so a short window keeps it whole. */
function useIconSize(cols: number): { size: number; gap: number } {
  const [h, setH] = useState(window.innerHeight);
  useEffect(() => {
    const f = () => setH(window.innerHeight);
    window.addEventListener("resize", f);
    return () => window.removeEventListener("resize", f);
  }, []);
  const want = cols ? Math.round(cols * 3.2) : 84;
  const gap = Math.max(40, Math.min(72, Math.round(want * 0.62)));
  const size = Math.max(40, Math.min(want, 320, Math.round(h / 2 - 120 - gap)));
  return { size, gap };
}

/** "Choose folder ∨" under the folder card, built like Claude Code's "Choose environment": exactly as wide as the
 *  card and lined up with its edges, a search field on top, a small "Recent" label, plain rows with a check on the
 *  current one, and "+ Open another folder…" at the bottom. */
function ChooseFolderMenu({ folders, cwd, chat, onPick, onBrowse }: {
  folders: { path: string; name: string }[]; cwd: string | null; chat: boolean;
  onPick: (p: string | null, chat: boolean) => void; onBrowse: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (!open) return;
    setQ("");
    const t = setTimeout(() => input.current?.focus(), 30);
    return () => clearTimeout(t);
  }, [open]);
  const ql = q.trim().toLowerCase();
  const shown = folders.filter((f) => !ql || f.name.toLowerCase().includes(ql) || f.path.toLowerCase().includes(ql)).slice(0, 40);
  const choose = (p: string) => {
    onPick(p, false);
    setOpen(false);
  };
  return (
    <Menu open={open} onOpenChange={setOpen}>
      <MenuTrigger asChild>
        <button className="flex h-[26px] w-full items-center gap-1 px-2 text-left text-[12px] text-text-100 hover:bg-hover aria-expanded:bg-hover">
          Choose folder <ChevD size={9} strokeWidth={1.7} className="text-text-400" />
        </button>
      </MenuTrigger>
      {/* the trigger sits inside the card's 1px border: -1 and the card's width line the menu up with the card */}
      <MenuContent align="start" alignOffset={-1} sideOffset={8} className="w-[243px] min-w-0 p-0"
        onCloseAutoFocus={(e) => e.preventDefault()}>
        <div className="border-b border-[var(--dropdown-sep)] px-[12px]">
          <input ref={input} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search folders" spellCheck={false}
            onKeyDown={(e) => {
              if (e.key === "Enter" && shown[0]) {
                e.preventDefault();
                choose(shown[0].path);
              }
              // typing stays in the field (the menu would otherwise jump to an item by its first letter)
              if (!["Escape", "ArrowDown", "ArrowUp", "Tab"].includes(e.key)) e.stopPropagation();
            }}
            className="h-[31px] w-full bg-transparent text-[12px] text-text-100 outline-none placeholder:text-text-500 selectable" />
        </div>
        <div className="max-h-[300px] overflow-y-auto p-[5px]">
          <MenuLabel>Recent</MenuLabel>
          {shown.map((f) => (
            <MenuItem key={f.path} checked={!chat && (cwd || "").toLowerCase() === f.path.toLowerCase()} onSelect={() => choose(f.path)}>
              <span title={f.path}>{f.name}</span>
            </MenuItem>
          ))}
          {!shown.length && <div className="px-[7px] py-[3px] text-[11.5px] text-text-500">No recent folder matches “{q.trim()}”</div>}
          <MenuSep />
          <MenuItem checked={chat} onSelect={() => onPick(null, true)}>No folder (chat)</MenuItem>
          <MenuSep />
          <MenuItem icon={<PlusSm />} onSelect={onBrowse}>Open another folder…</MenuItem>
        </div>
      </MenuContent>
    </Menu>
  );
}

export function Home() {
  const s = useStore(useShallow((st) => ({ folders: st.folders, home: st.home, newSession: st.newSession, opening: st.opening, pickFolder: st.pickFolder, setHome: st.setHome, settings: st.settings, startWith: st.startWith, state: st.state })));
  const h = s.home;
  const st = s.state;
  const model = h.model || s.settings.model || st?.provider.model || "";
  const effort = h.effort || s.settings.effort || "medium";
  const pick = (p: string | null, chat: boolean) => s.setHome({ cwd: chat ? h.cwd : p, chat });
  const recent = s.folders.filter((f) => f.exists);
  const top = recent.slice(0, 3);
  if (h.cwd && !h.chat && !top.some((f) => f.path.toLowerCase() === h.cwd!.toLowerCase())) {
    top.unshift({ path: h.cwd, name: folderName(h.cwd), exists: true });
    top.length = Math.min(top.length, 3);
  }
  const icon = useIconSize(Number(s.settings.logo_cols) || 0);

  return (
    <div className="flex h-full min-w-0 flex-1 flex-col">
      <div className="flex min-h-0 flex-1 flex-col items-center justify-center px-5">
        <div className="relative w-[243px]">
          {/* floats above the cards, so the cards stay exactly centred like Claude's */}
          {s.settings.desktop_show_icon !== false && (
            <div className="absolute bottom-full left-1/2 -translate-x-1/2" style={{marginLeft:70, marginBottom: icon.gap - 69 }}>
              <EmilieIcon size={icon.size} ring={false} />
            </div>
          )}
          <div className="rounded-[9px] border border-card-border py-[3px]">
            {top.map((f) => {
              const on = !h.chat && (h.cwd || "").toLowerCase() === f.path.toLowerCase();
              return (
                <button key={f.path} onClick={() => pick(f.path, false)} title={f.path}
                  className="flex h-[26px] w-full items-center gap-[7px] px-2 text-left text-[12px] text-text-100 hover:bg-hover">
                  <LaptopIcon size={12} className="shrink-0" />
                  <span className="min-w-0 flex-1 truncate">{f.name}</span>
                  {on && <Check size={12} className="shrink-0" />}
                </button>
              );
            })}
            {h.chat && (
              <div className="flex h-[26px] items-center gap-[7px] px-2 text-[12px] text-text-100">
                <MessageSquare size={12} className="shrink-0" /><span className="flex-1">No folder</span><Check size={12} />
              </div>
            )}
            {(top.length > 0 || h.chat) && <div className="my-[3px] h-px bg-card-border" />}
            <ChooseFolderMenu folders={recent} cwd={h.chat ? null : h.cwd} chat={h.chat} onPick={pick}
              onBrowse={async () => {
                const p = await s.pickFolder("Choose a folder");
                if (p) pick(p, false);
              }} />
          </div>
          <button onClick={() => insertIntoComposer("/review ")}
            className={cn("mt-[10px] flex h-[30px] w-full items-center gap-[7px] whitespace-nowrap rounded-[9px] border border-card-border px-2 text-left text-[11.5px] hover:bg-hover",
              h.chat && "invisible")}>
            <BranchSm size={12} className="shrink-0 text-text-100" />
            <span className="shrink-0 text-text-100">Review changes</span>
            <span className="truncate text-text-400">Find bugs before you commit</span>
          </button>
          {s.opening === "new" && (
            <div className="absolute -bottom-8 left-0 right-0 flex items-center justify-center gap-2 text-[11.5px] text-text-400"><Spinner size={12} />Starting the session…</div>
          )}
        </div>
      </div>
      <div className="shrink-0 px-5 pb-[2px]">
        <Composer
          draftKey="home"
          commands={st?.commands || []}
          cwd={h.chat ? null : h.cwd}
          placeholder={h.chat ? "Talk with Emilie" : "Describe a task or ask a question"}
          onSend={(text, atts, pastes) => s.newSession(text, atts, pastes)}
          onCycleMode={() => s.setHome({ mode: MODE_ORDER[(MODE_ORDER.indexOf(h.mode) + 1) % 3] })}
          // talk and video call work before the first message too: they start the session, then turn on
          talk="off"
          onTalk={(on) => on && s.startWith("talk")}
          call={false}
          onCall={(on) => on && s.startWith("call")}
          disabled={s.opening === "new"}
          autoFocus
          footer={
            <>
              <ComputerChip cwd={h.chat ? null : h.cwd} onPickFolder={(p) => pick(p, false)} />
              <span className="w-[6px]" />
              <FolderChip cwd={h.cwd} chat={h.chat} onPick={pick} />
              <span className="w-[6px]" />
              {!h.chat && <WorktreeToggle on={h.worktree} onChange={(v) => s.setHome({ worktree: v })} />}
              <div className="flex-1" />
              <ModelEffortChip model={model} effort={effort} onModel={(m) => s.setHome({ model: m })} onEffort={(e) => s.setHome({ effort: e })} />
              <ModeChip value={h.mode} onChange={(m) => s.setHome({ mode: m })} />
              <ContextRing />
            </>
          }
        />
      </div>
    </div>
  );
}
