// Talking to the local server (emilie/desktop/hub.py). The token comes from the URL the window was opened with.

const params = new URLSearchParams(location.search);
let token = params.get("token") || sessionStorage.getItem("emilie-token") || "";
if (params.get("token")) {
  sessionStorage.setItem("emilie-token", token);
  params.delete("token");
  const rest = params.toString();
  history.replaceState(null, "", location.pathname + (rest ? "?" + rest : ""));
}
export const shell = params.get("shell") || "";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function call<T>(path: string, method: string, body?: unknown): Promise<T> {
  let r: Response;
  try {
    r = await fetch(path, {
      method,
      headers: { "X-Emilie-Token": token, ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    throw new ApiError("Emilie's background process is not reachable", 0);
  }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new ApiError((data as any).error || r.statusText || `HTTP ${r.status}`, r.status);
  return data as T;
}

function qs(q?: Record<string, unknown>): string {
  if (!q) return "";
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? "?" + s : "";
}

export const get = <T = any>(path: string, q?: Record<string, unknown>) => call<T>(path + qs(q), "GET");
export const post = <T = any>(path: string, body: unknown = {}) => call<T>(path, "POST", body);
export const media = (path: string, q?: Record<string, unknown>) => path + qs({ ...q, token });

export type EventHandler = (ev: any) => void;

/** One event stream for everything; reconnects by itself. onOpen(again) runs after every (re)connect. */
export function connectEvents(onEvent: EventHandler, onOpen: (again: boolean) => void, onDown: () => void): () => void {
  let es: EventSource | null = null;
  let opened = false;
  let closed = false;
  let retry: number | undefined;
  const open = () => {
    if (closed) return;
    es = new EventSource(`/api/events${qs({ token })}`);
    es.onopen = () => {
      onOpen(opened);
      opened = true;
    };
    es.onmessage = (m) => {
      try {
        onEvent(JSON.parse(m.data));
      } catch (e) {
        console.error("bad event", e, m.data?.slice?.(0, 200));
      }
    };
    es.onerror = () => {
      onDown();
      if (es && es.readyState === EventSource.CLOSED) {
        es = null;
        retry = window.setTimeout(open, 1500);
      }
    };
  };
  open();
  return () => {
    closed = true;
    clearTimeout(retry);
    es?.close();
  };
}
