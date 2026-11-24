// Shapes shared with the Python side (emilie/desktop/convert.py, worker.py, hub.py).

export type Block =
  | { t: "text"; html: string }
  | { t: "md"; md: string }
  | { t: "panel"; title: string; subtitle?: string; color?: string | null; body: Block[] }
  | { t: "table"; head: string[] | null; rows: string[][]; title?: string }
  | { t: "rule"; title: string }
  | { t: "pre"; html: string };

export interface Diff {
  text: string;
  added: number;
  removed: number;
  new_file?: boolean;
  path?: string;
  approx?: boolean;
  append?: boolean;
}

export type ToolStatus = "running" | "ok" | "error" | "interrupted" | "denied";

export type Item =
  | {
      kind: "user"; id: string; cid?: string; text: string; files?: string[]; images?: string[];
      n_images?: number; hidden_images?: number; command?: string | null; prompt?: string | null;
      queued?: boolean; spoken?: boolean; mi?: number; failed?: boolean;
    }
  | { kind: "assistant"; id: string; text: string; streaming?: boolean; spontaneous?: boolean; mi?: number; at?: number }
  | { kind: "thinking"; id: string; text: string; mi?: number }
  | {
      kind: "tool"; id: string; name: string; label: string; target: string; input: any; status: ToolStatus;
      summary: string[]; output: string; diff?: Diff | null; secs?: number; mi?: number;
      children?: { label: string; target: string }[];
      images?: string[];                  // pictures the call produced or opened (screenshots, images read)
    }
  | { kind: "note"; id: string; text: string; level: string; detail?: string; images?: string[]; mi?: number }
  | { kind: "notice"; id: string; blocks: Block[]; level: "line" | "panel"; text?: string; mi?: number }
  | { kind: "denied"; id: string; label: string; target?: string; reason: string; mi?: number }
  | { kind: "turn"; id: string; secs: number; tokens?: number; exact?: boolean; stopped?: boolean };

export interface Todo { content: string; status: "pending" | "in_progress" | "completed"; activeForm?: string }

/** What fills the context (estimated tokens), for the Context section of the Environment panel. */
export interface CtxParts {
  messages: number; system_tools: number; mcp_tools: number; system_prompt: number; skills: number; memory: number;
  mcp_servers: { name: string; tools: number; tokens: number }[];
  window: number | null;            // the model's window when known (/config context_limit or a known small model)
  compact_default: number;          // the effort level's auto-compact point (used when compact_at is not set)
}

export interface Checkpoint { n: number; label: string; mark: number | null; files: string[]; nfiles: number; at: number }

export interface Status {
  session_id: string; cwd: string; title: string; model: string; active_model: string; mode: "ask" | "trust" | "plan";
  effort: string; busy: boolean; queued: number; ctx_tokens: number; ctx_limit: number; ctx_pct: number; ctx_parts: CtxParts | null;
  messages: number; usage: { in: number; out: number; calls: number; exact: boolean }; todos: Todo[];
  checkpoints: Checkpoint[]; talk: string; call: boolean; voice: boolean; provider: string; salvaged: number;
  memory: string[]; request: Request | null;
}

export type Request =
  | { id: string; kind: "permission"; name: string; label: string; target: string; reason: string; diff: Diff | null; input: any; can_always: boolean }
  | { id: string; kind: "plan"; plan: string }
  | { id: string; kind: "choose"; title: string; rows: string[]; plain: string[]; idx: number; hint: string; keys: string[] };

export interface Command { name: string; desc: string; kind: "builtin" | "skill" | "command" }

export interface Live {
  wid: string;
  sid: string | null;
  cwd: string;
  title: string;
  items: Item[];
  status: Partial<Status>;
  commands: Command[];
  busy: boolean;
  working: { since: number; tokens: number; activity?: string | null; streaming: boolean; voiceOn?: boolean; voice?: "" | "replying" | "speaking" } | null;
  request: Request | null;
  todos: Todo[];
  stale: boolean;
  closed: boolean;
}

export interface SessionMeta {
  id: string; cwd: string; title: string; updated: number; created: number; n: number; model: string;
  live?: boolean; wid?: string; busy?: boolean; waiting?: boolean; chat?: boolean;
}

export interface Folder { path: string; name: string; exists: boolean }

export interface AppState {
  version: string; platform: string; home: string; user: string; has_key: boolean;
  provider: { id: string | null; label: string; kind: string; model: string };
  settings: Record<string, any>; folders: Folder[]; scratch: string; root: string; python: string; log: string;
  data_dir: string; settings_file: string; commands: Command[];
  efforts: { name: string; desc: string; max_output: number }[];
}

export interface Field {
  key: string; type: string; label: string; desc?: string; choices?: { value: string; label: string; desc?: string }[];
  default?: any; min?: number; max?: number; step?: number; placeholder?: string; nullable?: boolean;
  allow_custom?: boolean; live?: boolean;
}
export interface Section { id: string; label: string; icon: string; group?: number; groups: { title: string; fields: Field[] }[] }

export interface ModelRow { id: string; vision?: boolean; price?: string; grade?: string | null; mult?: number | null }

export type View =
  | { kind: "home" }
  | { kind: "session"; wid: string }
  | { kind: "projects" }
  | { kind: "artifacts" }
  | { kind: "customize"; tab?: "plugins" | "skills" | "connectors" | "scheduled" };
