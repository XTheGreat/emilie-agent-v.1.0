"""Claude-specific request features for the Anthropic provider: prompt caching and extended thinking.

Both are built here as plain functions so they can be tested without the network.
- Prompt caching marks the (stable) system prompt + tools and the tail of the conversation, so later rounds of a
  long session re-read them from cache instead of paying full price. Only for the official API (no custom base URL):
  an Anthropic-compatible proxy may reject cache_control.
- Extended thinking is OPT-IN (/thinking <tokens>): it lets Claude reason before answering, at a token cost.
"""
import copy

MIN_THINKING = 1024                      # the API minimum for budget_tokens
_CACHEABLE = {"text", "tool_result", "image", "document"}
EPHEMERAL = {"type": "ephemeral"}


def with_cache_tail(messages: list[dict]) -> list[dict]:
    """A copy of the messages whose last block carries a cache breakpoint. The stored history is never modified."""
    if not messages:
        return messages
    out = list(messages)
    last = copy.deepcopy(out[-1])
    c = last.get("content")
    if isinstance(c, str):
        last["content"] = [{"type": "text", "text": c, "cache_control": EPHEMERAL}]
    elif isinstance(c, list) and c and isinstance(c[-1], dict) and c[-1].get("type") in _CACHEABLE:
        c[-1]["cache_control"] = EPHEMERAL
    else:
        return messages                  # nothing safe to mark (e.g. the last block is a thinking block)
    out[-1] = last
    return out


def request_kwargs(system: str, tool_schemas: list, messages: list, max_output: int,
                   base_url: str | None, thinking_budget: int = 0) -> dict:
    """The keyword arguments for client.messages.stream(...), without the model name."""
    cache = not base_url
    kw = {
        "max_tokens": max_output,
        "system": [{"type": "text", "text": system, "cache_control": EPHEMERAL}] if cache else system,
        "tools": tool_schemas,
        "messages": with_cache_tail(messages) if cache else messages,
    }
    if thinking_budget and thinking_budget >= MIN_THINKING:
        kw["thinking"] = {"type": "enabled", "budget_tokens": int(thinking_budget)}
        kw["max_tokens"] = max_output + int(thinking_budget)      # max_tokens must be larger than the budget
    return kw


def usage_tokens(usage) -> tuple[int, int]:
    """(input incl. cached, output) from an Anthropic usage object."""
    inp = (getattr(usage, "input_tokens", 0) or 0) + (getattr(usage, "cache_read_input_tokens", 0) or 0) \
        + (getattr(usage, "cache_creation_input_tokens", 0) or 0)
    return inp, getattr(usage, "output_tokens", 0) or 0
