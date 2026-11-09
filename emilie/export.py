"""/export: the conversation as a readable markdown file (works for both message formats: OpenAI-style and Anthropic)."""
import json
import time
from pathlib import Path


def _short(v, n: int) -> str:
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _blocks(content) -> list[dict]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return [b for b in (content or []) if isinstance(b, dict)]


def to_markdown(messages: list[dict], model: str = "", cwd: str = "") -> str:
    out = ["# Emilie conversation", "", f"- date: {time.strftime('%Y-%m-%d %H:%M')}"]
    if model:
        out.append(f"- model: {model}")
    if cwd:
        out.append(f"- folder: {cwd}")
    out.append("")
    for m in messages:
        role = m.get("role")
        if role == "tool":                                           # OpenAI tool result
            out += [f"<details><summary>tool result</summary>\n\n```\n{_short(m.get('content', ''), 1500)}\n```\n</details>", ""]
            continue
        texts, calls, results = [], [], []
        for b in _blocks(m.get("content")):
            t = b.get("type")
            if t == "text" and b.get("text", "").strip():
                texts.append(b["text"].strip())
            elif t == "tool_use":
                calls.append(f"`{b.get('name')}({_short(b.get('input', {}), 160)})`")
            elif t == "tool_result":
                results.append(_short(b.get("content", ""), 1500))
            elif t in ("image", "image_url", "video_url"):
                texts.append("*[image]*")
        for c in m.get("tool_calls", []) or []:                      # OpenAI assistant tool calls
            fn = c.get("function", {})
            calls.append(f"`{fn.get('name')}({_short(fn.get('arguments', ''), 160)})`")
        if role == "user" and results and not texts:
            for r in results:
                out += [f"<details><summary>tool result</summary>\n\n```\n{r}\n```\n</details>", ""]
            continue
        if role == "user" and texts:
            out += ["## You", "", "\n\n".join(texts), ""]
        elif role == "assistant":
            if texts:
                out += ["## Emilie", "", "\n\n".join(texts), ""]
            for c in calls:
                out += [f"> ran {c}", ""]
    return "\n".join(out).rstrip() + "\n"


def save(messages: list[dict], target: str, model: str = "", cwd: str = "") -> tuple[Path | None, str]:
    """-> (path, message). Never overwrites an existing file."""
    p = Path(target).expanduser() if target else Path(f"emilie-export-{time.strftime('%Y%m%d-%H%M%S')}.md")
    if p.suffix == "":
        p = p.with_suffix(".md")
    if p.exists():
        return None, f"{p} already exists: pick another name"
    if not messages:
        return None, "nothing to export yet"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(to_markdown(messages, model, cwd), encoding="utf-8")
    except OSError as e:
        return None, f"could not write {p}: {e}"
    return p.resolve(), f"saved {len(messages)} messages to {p.resolve()}"
