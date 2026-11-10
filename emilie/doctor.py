"""/doctor: probe what the CURRENT model and provider really support, instead of assuming.

Each probe is one small real call (a few hundred tokens in total): plain chat, streaming (+ usage reporting),
tool calling with valid JSON arguments, a tool result round-trip, and vision. The result is stored in
~/.emilie/model_profiles.json, keyed "provider:model", so Emilie (and you) can see what each model can do.
Pure functions over a client object, so they are testable with a fake client.
"""
import base64
import io
import json
import time
from dataclasses import dataclass

from . import paths

PROFILES = paths.HOME_DIR / "model_profiles.json"

ADD_TOOL = {"name": "add_numbers", "description": "Add two integers and return the sum.",
            "input_schema": {"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
                             "required": ["a", "b"]}}


@dataclass
class Result:
    key: str               # chat | stream | stream_usage | tools | tool_roundtrip | vision
    label: str
    ok: bool | None        # None = skipped / unknown
    detail: str = ""
    secs: float = 0.0


def _png(color=(220, 20, 20), size=48) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (size, size), color).save(buf, "PNG")
    return buf.getvalue()


# ------------------------------------------------------------------ one normalised call
def _call(client, kind: str, model: str, messages: list, tools: list | None = None, max_tokens: int = 400):
    """-> (text, [(id, name, args_dict | None, raw_args)], assistant_message_for_history)"""
    if kind == "anthropic":
        kw = dict(model=model, max_tokens=max_tokens, messages=messages)
        if tools:
            kw["tools"] = tools
        r = client.messages.create(**kw)
        text = "".join(b.text for b in r.content if b.type == "text")
        calls = [(b.id, b.name, b.input, json.dumps(b.input)) for b in r.content if b.type == "tool_use"]
        return text, calls, {"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in r.content]}
    kw = dict(model=model, max_tokens=max_tokens, messages=messages)
    if tools:
        kw["tools"] = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                         "parameters": t["input_schema"]}} for t in tools]
    r = client.chat.completions.create(**kw)
    m = r.choices[0].message
    calls = []
    for c in m.tool_calls or []:
        raw = c.function.arguments or ""
        try:
            args = json.loads(raw or "{}")
        except json.JSONDecodeError:
            args = None
        calls.append((c.id, c.function.name, args, raw))
    hist = {"role": "assistant", "content": m.content}
    if m.tool_calls:
        hist["tool_calls"] = [{"id": c[0], "type": "function", "function": {"name": c[1], "arguments": c[3] or "{}"}}
                              for c in calls]
    return m.content or "", calls, hist


def _timed(fn):
    t = time.time()
    try:
        out = fn()
        return out, None, time.time() - t
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:160]}", time.time() - t


# ------------------------------------------------------------------ probes
def probe_chat(client, kind, model) -> Result:
    out, err, dt = _timed(lambda: _call(client, kind, model, [{"role": "user", "content": "Reply with exactly one word: pong"}], max_tokens=200))
    if err:
        return Result("chat", "basic chat", False, err, dt)
    return Result("chat", "basic chat", bool(out[0].strip()), out[0].strip()[:40] or "empty answer", dt)


def probe_stream(client, kind, model) -> list[Result]:
    msgs = [{"role": "user", "content": "Count from 1 to 5, separated by spaces."}]

    def run():
        n, usage = 0, False
        if kind == "anthropic":
            with client.messages.stream(model=model, max_tokens=200, messages=msgs) as s:
                for _ in s.text_stream:
                    n += 1
                usage = bool(getattr(s.get_final_message(), "usage", None))
            return n, usage
        try:
            it = client.chat.completions.create(model=model, messages=msgs, max_tokens=200, stream=True,
                                                stream_options={"include_usage": True})
        except Exception as e:                      # some providers reject stream_options
            if "stream_options" not in str(e) and getattr(e, "status_code", 0) != 400:
                raise
            it = client.chat.completions.create(model=model, messages=msgs, max_tokens=200, stream=True)
        for ch in it:
            u = getattr(ch, "usage", None)
            if u and (u.prompt_tokens or u.completion_tokens):
                usage = True
            if ch.choices and ch.choices[0].delta.content:
                n += 1
        return n, usage

    out, err, dt = _timed(run)
    if err:
        return [Result("stream", "streaming", False, err, dt), Result("stream_usage", "token usage while streaming", None, "skipped")]
    n, usage = out
    return [Result("stream", "streaming", n > 1, f"{n} chunks" if n > 1 else "answer arrived in one piece", dt),
            Result("stream_usage", "token usage while streaming", usage,
                   "reported" if usage else "not reported: Emilie estimates tokens (cost/context are approximate)")]


def probe_tools(client, kind, model) -> list[Result]:
    msgs = [{"role": "user", "content": "Use the add_numbers tool to add 17 and 25. Call the tool; do not compute it yourself."}]
    out, err, dt = _timed(lambda: _call(client, kind, model, msgs, [ADD_TOOL]))
    if err:
        return [Result("tools", "tool calling", False, err, dt), Result("tool_roundtrip", "tool result round-trip", None, "skipped")]
    text, calls, hist = out
    if not calls:
        return [Result("tools", "tool calling", False, "the model answered in text instead of calling the tool", dt),
                Result("tool_roundtrip", "tool result round-trip", None, "skipped")]
    cid, name, args, raw = calls[0]
    if args is None:
        return [Result("tools", "tool calling", False, f"arguments are not valid JSON: {raw[:60]!r}", dt),
                Result("tool_roundtrip", "tool result round-trip", None, "skipped")]
    ok_args = name == "add_numbers" and {int(args.get("a", -1)), int(args.get("b", -1))} == {17, 25}
    first = Result("tools", "tool calling", ok_args, f"{name}({raw[:50]})" if ok_args else f"wrong call: {name}({raw[:50]})", dt)

    if kind == "anthropic":
        follow = msgs + [hist, {"role": "user", "content": [{"type": "tool_result", "tool_use_id": cid, "content": "42"}]}]
    else:
        follow = msgs + [hist, {"role": "tool", "tool_call_id": cid, "content": "42"}]
    out2, err2, dt2 = _timed(lambda: _call(client, kind, model, follow, [ADD_TOOL]))
    if err2:
        return [first, Result("tool_roundtrip", "tool result round-trip", False, err2, dt2)]
    return [first, Result("tool_roundtrip", "tool result round-trip", "42" in out2[0], out2[0].strip()[:50] or "empty answer", dt2)]


def probe_vision(client, kind, model) -> Result:
    b64 = base64.b64encode(_png()).decode()
    q = "What is the main colour of this image? Answer with one word."
    if kind == "anthropic":
        content = [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}}, {"type": "text", "text": q}]
    else:
        content = [{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}, {"type": "text", "text": q}]
    out, err, dt = _timed(lambda: _call(client, kind, model, [{"role": "user", "content": content}], max_tokens=200))
    if err:
        return Result("vision", "vision (images)", False, err, dt)
    ok = "red" in out[0].lower()
    return Result("vision", "vision (images)", ok, out[0].strip()[:40] or "empty answer", dt)


def run_all(client, kind: str, model: str, progress=lambda r: None) -> list[Result]:
    results: list[Result] = []
    for step in (lambda: [probe_chat(client, kind, model)], lambda: probe_stream(client, kind, model),
                 lambda: probe_tools(client, kind, model), lambda: [probe_vision(client, kind, model)]):
        for r in step():
            results.append(r)
            progress(r)
        if results and results[0].key == "chat" and results[0].ok is False and len(results) == 1:
            break                                    # the model/key does not answer at all: the rest would only repeat it
    return results


# ------------------------------------------------------------------ stored profiles
def save_profile(provider_id: str, model: str, results: list[Result]) -> None:
    try:
        data = json.loads(PROFILES.read_text())
    except (OSError, ValueError):
        data = {}
    data[f"{provider_id}:{model}"] = {r.key: r.ok for r in results} | {"checked": time.strftime("%Y-%m-%d")}
    paths.HOME_DIR.mkdir(parents=True, exist_ok=True)
    PROFILES.write_text(json.dumps(data, indent=2))


def load_profile(provider_id: str, model: str) -> dict:
    try:
        return json.loads(PROFILES.read_text()).get(f"{provider_id}:{model}", {})
    except (OSError, ValueError):
        return {}


def advice(results: list[Result]) -> list[str]:
    by = {r.key: r for r in results}
    out = []
    if by.get("tools") and by["tools"].ok is False:
        out.append("This model cannot call tools reliably: Emilie will mostly chat. Try another model for coding work.")
    if by.get("tool_roundtrip") and by["tool_roundtrip"].ok is False:
        out.append("It calls tools but loses the result afterwards: long tool loops may go wrong.")
    if by.get("vision") and by["vision"].ok is False:
        out.append("No vision: pasted images will not be understood (set a vision model if your provider has one).")
    if by.get("stream_usage") and by["stream_usage"].ok is False:
        out.append("Token usage is not reported while streaming: /cost and /context are estimates.")
    return out
