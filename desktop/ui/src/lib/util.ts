export function cn(...parts: (string | false | null | undefined | 0)[]): string {
  return parts.filter(Boolean).join(" ");
}

export function basename(p: string): string {
  if (!p) return "";
  const s = p.replace(/[\\/]+$/, "");
  const i = Math.max(s.lastIndexOf("/"), s.lastIndexOf("\\"));
  const b = i >= 0 ? s.slice(i + 1) : s;
  return b || s;
}

export function dirname(p: string): string {
  const s = p.replace(/[\\/]+$/, "");
  const i = Math.max(s.lastIndexOf("/"), s.lastIndexOf("\\"));
  return i > 0 ? s.slice(0, i) : s;
}

export function shortPath(p: string, home?: string): string {
  if (!p) return "";
  if (home && p.toLowerCase().startsWith(home.toLowerCase())) return "~" + p.slice(home.length);
  return p;
}

export function folderLabel(p: string): string {
  const b = basename(p);
  return /^[a-zA-Z]:$/.test(b) ? b : b || p;
}

export function ago(ts: number): string {
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  if (s < 86400 * 30) return `${Math.floor(s / 86400)}d`;
  return new Date(ts * 1000).toLocaleDateString();
}

const MONTH = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Claude's card dates: "just now", "6h ago", "2d ago", then "Nov 9" after a week. */
export function agoShort(ts: number): string {
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  if (s < 86400 * 7) return `${Math.floor(s / 86400)}d ago`;
  const d = new Date(ts * 1000);
  return `${MONTH[d.getMonth()]} ${d.getDate()}` + (d.getFullYear() !== new Date().getFullYear() ? `, ${d.getFullYear()}` : "");
}

/** Claude's project dates: "15 hours ago", "3 days ago". */
export function agoLong(ts: number): string {
  const s = Math.max(0, Date.now() / 1000 - ts);
  const n = (v: number, unit: string) => `${v} ${unit}${v === 1 ? "" : "s"} ago`;
  if (s < 60) return "just now";
  if (s < 3600) return n(Math.floor(s / 60), "minute");
  if (s < 86400) return n(Math.floor(s / 3600), "hour");
  if (s < 86400 * 30) return n(Math.floor(s / 86400), "day");
  if (s < 86400 * 365) return n(Math.floor(s / (86400 * 30)), "month");
  return n(Math.floor(s / (86400 * 365)), "year");
}

export function fmtTokens(n: number): string {
  if (!n) return "0";
  return n >= 1000 ? `${(n / 1000).toFixed(n >= 100000 ? 0 : 1)}k` : String(Math.round(n));
}

export function fmtSecs(s: number): string {
  s = Math.max(0, Math.round(s));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
}

export function uid(prefix = "c"): string {
  return prefix + Math.random().toString(36).slice(2, 10) + Date.now().toString(36).slice(-4);
}

export function prettyModel(id: string | undefined | null): string {
  if (!id) return "Model";
  const last = id.split("/").pop() || id;
  const m = last.match(/^claude-(opus|sonnet|haiku|fable)-(\d+)-(\d+)/i);
  if (m) return `${m[1][0].toUpperCase()}${m[1].slice(1)} ${m[2]}.${m[3]}`;
  return last;
}

export interface Attachment {
  id: string;
  kind: "image" | "file";
  name: string;
  mime?: string;
  b64?: string;
  url?: string;
  path?: string;
  size?: number;
}

export function readFile(file: File): Promise<Attachment> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => {
      const url = String(r.result);
      const b64 = url.slice(url.indexOf(",") + 1);
      resolve({ id: uid("a"), kind: "image", name: file.name || "image.png", mime: file.type || "image/png", b64, url });
    };
    r.onerror = () => reject(r.error);
    r.readAsDataURL(file);
  });
}

export function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    ta.remove();
    return ok;
  }
}

export const VERBS = ["Cooking", "Tangling", "Baking", "Whisking", "Simmering", "Pondering", "Brewing", "Conjuring",
  "Noodling", "Marinating", "Frosting", "Kneading", "Sprinkling", "Caramelizing", "Percolating", "Daydreaming"];
// Emilie's spinner from the terminal: one flower that opens and closes
export const FRAMES = ["∘", "✢", "✥", "✤", "❀", "✿", "✾", "❁", "❋", "❁", "✾", "✿", "❀", "✤", "✥", "✢"];

/** Which tabs go into the "more" list when the strip is `width` px wide. The selected tab always keeps its place; the others
 *  are shown, in order, while they fit at their smallest width. */
export function tabsThatDoNotFit<T>(ids: T[], active: T | null, width: number, minActive: number, minOther: number, gap = 4): T[] {
  let used = ids.includes(active as T) ? minActive : 0;
  const out: T[] = [];
  for (const id of ids) {
    if (id === active) continue;
    if (used + (used ? gap : 0) + minOther <= width) used += (used ? gap : 0) + minOther;
    else out.push(id);
  }
  return out;
}
