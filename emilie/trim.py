"""Old tool results are the biggest thing a long session pays for again and again: every read_file / grep / bash / web
page stays in the history and is sent with EVERY later model call until the history is summarised.

slim() returns the history as it is SENT: tool results older than the last KEEP of them are cut down to a short stub.
The stored history is never changed (the screen, the saved session, /rewind and the summary all keep the full text).

To keep the provider's prompt cache working (a cache needs the start of the request to be identical to last time) the
cut-off moves in big steps, not one result per call: it only moves forward once at least BATCH characters would be
saved by it. Between two moves the sent history is exactly the same, call after call."""

KEEP = 6            # the newest tool-result messages are always sent in full
MIN_CHARS = 600     # a result shorter than this is not worth a stub
BATCH = 12_000      # the cut-off only moves once this many characters would go
HEAD = 200          # how much of a trimmed result is kept


def _is_result(m: dict) -> bool:
    if m.get("role") == "tool":
        return True
    c = m.get("content")
    return m.get("role") == "user" and isinstance(c, list) and any(
        isinstance(b, dict) and b.get("type") == "tool_result" for b in c)


def _stub(text: str) -> str:
    return (text[:HEAD].rstrip() + f"\n…[older tool result trimmed: {len(text)} chars. If you need the detail "
            "(or want to edit that file), read it or run the tool again.]")


def _size(m: dict) -> int:
    """Characters this message would lose when trimmed."""
    c = m.get("content")
    if m.get("role") == "tool":
        return len(c) - HEAD if isinstance(c, str) and len(c) > MIN_CHARS else 0
    return sum(len(b["content"]) - HEAD for b in c if isinstance(b, dict) and b.get("type") == "tool_result"
               and isinstance(b.get("content"), str) and len(b["content"]) > MIN_CHARS)


def _slim_one(m: dict) -> dict:
    c = m.get("content")
    if m.get("role") == "tool":
        return {**m, "content": _stub(c)} if isinstance(c, str) and len(c) > MIN_CHARS else m
    if not isinstance(c, list):
        return m
    out, changed = [], False
    for b in c:
        if isinstance(b, dict) and b.get("type") == "tool_result" and isinstance(b.get("content"), str) \
                and len(b["content"]) > MIN_CHARS:
            out.append({**b, "content": _stub(b["content"])})
            changed = True
        else:
            out.append(b)
    return {**m, "content": out} if changed else m


def slim(messages: list, state: dict) -> list:
    """The messages to send. `state` holds the cut-off between calls (a reference to the last trimmed message)."""
    idx = [i for i, m in enumerate(messages) if isinstance(m, dict) and _is_result(m)]
    if len(idx) <= KEEP:
        return messages
    mark = state.get("mark")
    cut = next((i + 1 for i, m in enumerate(messages) if m is mark), 0) if mark is not None else 0
    want = idx[-KEEP]                                   # everything before this message may be trimmed
    if want > cut and sum(_size(m) for m in messages[cut:want] if isinstance(m, dict) and _is_result(m)) >= BATCH:
        cut = want
        state["mark"] = messages[cut - 1]
    if cut <= 0:
        return messages
    return [_slim_one(m) if i < cut and isinstance(m, dict) and _is_result(m) else m for i, m in enumerate(messages)]


def saved_chars(messages: list, state: dict) -> int:
    """Characters slim() currently leaves out of the sent history (for the context gauge and the compaction limit)."""
    mark = state.get("mark")
    if mark is None:
        return 0
    cut = next((i + 1 for i, m in enumerate(messages) if m is mark), 0)
    return sum(_size(m) for m in messages[:cut] if isinstance(m, dict) and _is_result(m))
