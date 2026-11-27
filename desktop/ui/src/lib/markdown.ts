import { Marked } from "marked";
import DOMPurify from "dompurify";
import hljs from "highlight.js/lib/common";
import { escapeHtml } from "./util";

// A reply drawn again (another session opened and this one back, "Show earlier") takes its code blocks from here instead
// of highlighting them again (the output is identical). A code block still being written (no closing fence yet) changes
// on every update of a streaming reply: it is not kept, so it never pushes the finished ones out.
const hlCache = new Map<string, string>();
function cachedHighlight(text: string, language: string, keep: boolean): string {
  const key = language + "\0" + text;
  const hit = hlCache.get(key);
  if (hit !== undefined) return hit;
  const out = hljs.highlight(text, { language, ignoreIllegals: true }).value;
  if (keep && text.length < 20_000) {
    if (hlCache.size >= 300) hlCache.delete(hlCache.keys().next().value as string);
    hlCache.set(key, out);
  }
  return out;
}

const marked = new Marked({ gfm: true, breaks: false });

marked.use({
  renderer: {
    code({ text, lang, raw }) {
      const language = (lang || "").trim().split(/\s+/)[0].toLowerCase();
      let body: string;
      if (language && hljs.getLanguage(language)) {
        try {
          body = cachedHighlight(text, language, /\n[ \t]*(`{3,}|~{3,})[ \t]*\n?$/.test(raw || ""));
        } catch {
          body = escapeHtml(text);
        }
      } else {
        body = escapeHtml(text);
      }
      return (
        `<div class="codeblock"><div class="codeblock-head"><span>${escapeHtml(language || "text")}</span>` +
        `<button type="button" data-copy="1">Copy</button></div><pre><code class="hljs">${body}</code></pre></div>`
      );
    },
    link({ href, title, tokens }) {
      const inner = this.parser.parseInline(tokens);
      const t = title ? ` title="${escapeHtml(title)}"` : "";
      return `<a href="${escapeHtml(href || "")}" data-ext="1"${t}>${inner}</a>`;
    },
  },
});

const THINK = /^\s*<think>([\s\S]*?)(<\/think>|$)/i;
const SANITIZE = {
  ADD_ATTR: ["data-copy", "data-ext", "open"],
  FORBID_TAGS: ["style", "form", "input", "textarea", "select", "iframe", "script"],
  RETURN_DOM_FRAGMENT: true as const,
};

/** Sanitized nodes for one top-level Markdown block. They can be moved directly into the transcript. */
export interface MdBlock { src: string; nodes: ChildNode[] }

/** Markdown -> safe HTML, as its top-level pieces. <say> lines (Emilie's voice) become ♪ lines like in the terminal.
 *  `prev` is the result for an earlier text of the same reply: a piece whose source did not change is reused as it is
 *  (the same object), so a reply that is still streaming only has its last piece parsed and sanitized again. */
export function markdownBlocks(src: string, prev: readonly MdBlock[] = []): MdBlock[] {
  let text = src || "";
  let think = "";
  const m = text.match(THINK);
  if (m) {
    think = m[1].trim();
    text = text.slice(m[0].length);
  }
  text = text.replace(/<say>([\s\S]*?)<\/say>/gi, (_all, s: string) => `\n\n<p class="say">♪ ${escapeHtml(s.trim())}</p>\n\n`);
  const out: MdBlock[] = [];
  const add = (src: string, html: () => string) => {
    const p = prev[out.length];
    out.push(p && p.src === src ? p : { src, nodes: Array.from(DOMPurify.sanitize(html(), SANITIZE).childNodes) });
  };
  if (think) {
    add("\0think\0" + think, () =>
      `<details class="mb-3 text-[13px] font-sans text-text-400"><summary class="cursor-pointer select-none">Thought process</summary>` +
      `<div class="mt-2 whitespace-pre-wrap">${escapeHtml(think)}</div></details>`);
  }
  const tokens = marked.lexer(text);
  // a link definition ("[1]: https://…") can change any piece that uses it: pieces made with other definitions are not reused
  const defs = Object.keys(tokens.links || {}).length ? "\0" + JSON.stringify(tokens.links) : "";
  for (const tok of tokens) {
    if (tok.type === "space" || tok.type === "def") continue;          // they draw nothing
    add(tok.type + "\0" + tok.raw + defs, () => marked.parser([tok]));
  }
  return out;
}

/** Markdown -> safe HTML (all the pieces of markdownBlocks). */
export function renderMarkdown(src: string): string {
  const template = document.createElement("template");
  for (const block of markdownBlocks(src)) {
    for (const node of block.nodes) template.content.appendChild(node);
  }
  return template.innerHTML;
}

export function highlight(code: string, ext: string): string {
  const lang = { py: "python", js: "javascript", ts: "typescript", tsx: "typescript", jsx: "javascript", md: "markdown",
    yml: "yaml", sh: "bash", ps1: "powershell", rs: "rust", kt: "kotlin", cs: "csharp", h: "c", hpp: "cpp" }[ext] || ext;
  if (lang && hljs.getLanguage(lang) && code.length < 300_000) {
    try {
      return hljs.highlight(code, { language: lang, ignoreIllegals: true }).value;
    } catch {
      /* fall through */
    }
  }
  return escapeHtml(code);
}
