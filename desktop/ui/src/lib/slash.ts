// Slash commands that have a screen in the app open that screen instead of printing text into the conversation, as in
// the Claude Code desktop app: /model, /effort and /mode open their pickers, /cost the token-usage popover, /context the
// Environment panel, /skills, /mcp and /schedule the Customize page, /config and the other settings commands the
// Settings page, /help the help dialog, /resume the session search. A command with arguments those screens do not take
// (/skills reload, /config effort high, …) still goes to Emilie, like every other command.
import type { LiveX, Store } from "./store";
import { post } from "./api";

// "model-toggle": Ctrl+Shift+I, as in Claude: opens the model picker (with the effort levels in it), or closes it
export type PickerName = "model" | "model-toggle" | "effort" | "mode" | "context";

/** Opens a picker of the message box: the chips listen for this event (Pickers.tsx). */
export function openPicker(name: PickerName) {
  window.dispatchEvent(new CustomEvent("emilie:open", { detail: name }));
}

/** Settings sections for the commands that are settings, typed without arguments. */
const SETTINGS_FOR: Record<string, string> = {
  "/config": "general", "/settings": "general", "/language": "general", "/reply": "general",
  "/provider": "model", "/fallback": "model", "/thinking": "model",
  "/permissions": "privacy", "/allow": "privacy", "/deny": "privacy",
  "/persona": "persona", "/voice": "capabilities", "/camera": "capabilities", "/logo": "appearance",
  "/usage": "usage",
};
const CUSTOMIZE_FOR: Record<string, "plugins" | "skills" | "connectors" | "scheduled"> = {
  "/plugins": "plugins", "/skills": "skills", "/mcp": "connectors", "/schedule": "scheduled",
};
const EFFORTS = ["low", "medium", "high", "max"];
const MODE_LABEL: Record<string, string> = { ask: "Ask first", trust: "Trust", plan: "Plan" };
const cap = (s: string) => s.replace(/^./, (c) => c.toUpperCase());

export interface SlashCtx {
  s: Store;
  set: (p: Partial<Store>) => void;
  live: LiveX | null;                                   // the open session; null on the New session page
}

/** Runs a typed command in the window when it has a screen. True = handled here, nothing goes to Emilie. */
export function runInApp(text: string, { s, set, live }: SlashCtx): boolean {
  const m = text.trim().match(/^(\/[\w-]+)(?:\s+([\s\S]*))?$/);
  if (!m) return false;
  const cmd = m[1].toLowerCase();
  const arg = (m[2] || "").trim();
  const word = arg.toLowerCase();

  // ---- the message box's own pickers
  if (cmd === "/model") {
    if (!arg) return openPicker("model"), true;
    if (live) s.setOpt(live.wid, { model: arg });
    else s.setHome({ model: arg });
    s.toast(`Model set to ${arg}`);
    return true;
  }
  if (cmd === "/effort") {
    if (!arg) return openPicker("effort"), true;
    if (!EFFORTS.includes(word)) return s.toast(`Unknown effort level “${arg}”: low, medium, high or max`, "error"), true;
    if (live) s.setOpt(live.wid, { effort: word });
    else s.setHome({ effort: word });
    s.toast(`Effort set to ${cap(word)}`);
    return true;
  }
  if (cmd === "/mode" || ((cmd === "/plan" || cmd === "/trust") && !arg)) {
    if (cmd === "/mode" && !arg) return openPicker("mode"), true;
    const cur = (live ? live.status.mode : s.home.mode) || "ask";
    const next = cmd === "/mode" ? word : cur === cmd.slice(1) ? "ask" : cmd.slice(1);
    if (!MODE_LABEL[next]) return s.toast(`Unknown mode “${arg}”: ask, trust or plan`, "error"), true;
    if (live) s.setOpt(live.wid, { mode: next });
    else s.setHome({ mode: next });
    s.toast(`Mode: ${MODE_LABEL[next]}`);
    return true;
  }

  // ---- context and usage
  if (cmd === "/context" && !arg) {
    if (!live) return s.toast("The context starts with the session: it is empty for now."), true;
    if (s.settings.desktop_env_panel === false) s.setSetting("desktop_env_panel", true);
    set({ envFloat: true });                             // docked when there is room (App), floating otherwise
    return true;
  }
  if (cmd === "/cost" && !arg) {
    if (!live) return set({ settingsOpen: "usage" }), true;
    return openPicker("context"), true;
  }
  if (cmd === "/rewind" && !arg) {
    if (!live?.status.checkpoints?.length) return s.toast("Nothing to rewind yet: only turns that changed files can be rewound."), true;
    return openPicker("context"), true;                // its popover lists the turns that changed files
  }

  // ---- pages and dialogs
  if (SETTINGS_FOR[cmd] && !arg) return set({ settingsOpen: SETTINGS_FOR[cmd] }), true;
  if (CUSTOMIZE_FOR[cmd] && !arg) return s.navigate({ kind: "customize", tab: CUSTOMIZE_FOR[cmd] }), true;
  if (cmd === "/help" && !arg) return set({ dialog: { kind: "help" } }), true;
  if (cmd === "/resume" && !arg) return set({ dialog: { kind: "search", tab: "all" } }), true;

  // ---- things in this conversation
  if (cmd === "/todos" && !arg) {
    const lists = document.querySelectorAll<HTMLElement>("[data-tasklist]");
    const last = lists[lists.length - 1];
    if (!live || !last) return s.toast("No task list in this session yet."), true;
    last.scrollIntoView({ block: "center", behavior: "smooth" });
    last.classList.remove("flash");
    void last.offsetWidth;                               // restart the highlight
    last.classList.add("flash");
    return true;
  }
  if (cmd === "/memory" && !arg) {
    const files = live?.status.memory || [];
    if (!files.length) return s.toast("No memory file yet. /init writes an EMILIE.md for this project."), true;
    files.forEach((f) => s.openFile(f));
    return true;
  }
  if (cmd === "/voice" && (word === "on" || word === "off")) {   // a switch: a popup, not a line in the conversation
    const on = word === "on";
    s.setSetting("voice", on).then((ok) => { if (ok) s.toast(on ? "Voice on" : "Voice off"); });
    return true;
  }
  if (cmd === "/persona" && ["on", "off", "show", "reset"].includes(word)) {   // her character: no session needed for it
    if (word === "show") return set({ settingsOpen: "persona" }), true;
    if (word === "reset") {
      void s.confirm("Reset the character sheet?", "persona.md goes back to the default Emilie. Your edits to it are lost.", { danger: true, ok: "Reset" })
        .then((ok) => { if (ok) post("/api/persona", { reset: true }).then(() => s.toast("Persona reset to the default Emilie")).catch((e) => s.toast(e.message, "error")); });
      return true;
    }
    post("/api/persona", { enabled: word === "on" })
      .then(() => s.toast(`Persona ${word}. It applies from the next message.`)).catch((e) => s.toast(e.message, "error"));
    return true;
  }
  if (cmd === "/talk" && !arg) {
    if (!live) return s.startWith("talk"), true;
    s.setTalk(live.wid, !(live.status.talk && live.status.talk !== "off"));
    return true;
  }
  return false;
}
