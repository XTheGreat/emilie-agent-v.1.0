"""Claude-specific request features for the Anthropic provider: prompt caching and how deeply Claude thinks.

Both are built here as plain functions so they can be tested without the network.
- Prompt caching marks the (stable) system prompt + tools and the tail of the conversation, so later rounds of a
  long session re-read them from cache instead of paying full price. Only for the official API (no custom base URL):
  an Anthropic-compatible proxy may reject cache_control.
- Thinking follows the effort level (/effort). Current models (Opus/Sonnet 4.6 and later, Haiku 5.5, Fable, Mythos)
  think adaptively and take output_config.effort: low / medium / high, and /effort max asks for "xhigh", the level
  Anthropic recommends for coding and agent work ("max" on the 4.6 models, which have no xhigh). A fixed thinking
  budget (budget_tokens) is rejected with a 400 on those models, so /thinking <tokens> only applies to older ones.
"""
import copy
import re

MIN_THINKING = 1024                      # the API minimum for budget_tokens (older models)
_CACHEABLE = {"text", "tool_result", "image", "document"}
EPHEMERAL = {"type": "ephemeral"}

# adaptive thinking + output_config.effort: Fable / Mythos, Opus / Sonnet / Haiku 5.x, Opus / Sonnet 4.6 and later
_ADAPTIVE = re.compile(r"claude-(?:fable|mythos)-\d|claude-(?:opus|sonnet|haiku)-(?:[5-9]|4-[6-9])", re.I)
_NO_XHIGH = re.compile(r"claude-(?:opus|sonnet)-4-6", re.I)      # xhigh arrived with Opus 4.7
EFFORT_LEVELS = {"low": "low", "medium": "medium", "high": "high", "max": "xhigh"}
# max_tokens counts the thinking as well as the answer: room for it on top of the effort level's answer cap
THINK_ROOM = {"low": 4096, "medium": 8192, "high": 16384, "max": 32768}


def adaptive(model: str | None) -> bool:
    """True for the Claude models that think adaptively and take output_config.effort."""
    return bool(_ADAPTIVE.search(model or ""))


def effort_param(model: str | None, effort: str) -> str:
    """The API's effort value for one of Emilie's levels (low / medium / high / max)."""
    level = EFFORT_LEVELS.get(effort, "medium")
    return "max" if level == "xhigh" and _NO_XHIGH.search(model or "") else level


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
                   base_url: str | None, thinking_budget: int = 0, model: str | None = None,
                   effort: str = "medium") -> dict:
    """The keyword arguments for client.messages.stream(...), without the model name."""
    cache = not base_url
    kw = {
        "max_tokens": max_output,
        "system": [{"type": "text", "text": system, "cache_control": EPHEMERAL}] if cache else system,
        "tools": tool_schemas,
        "messages": with_cache_tail(messages) if cache else messages,
    }
    if adaptive(model):
        # adaptive is valid on every one of these models (and needed on Opus 4.7/4.8, which do not think without it);
        # the thinking blocks of earlier answers stay in the history unchanged, as the API requires
        kw["thinking"] = {"type": "adaptive"}
        kw["output_config"] = {"effort": effort_param(model, effort)}
        kw["max_tokens"] = max_output + THINK_ROOM.get(effort, THINK_ROOM["medium"])
    elif thinking_budget and thinking_budget >= MIN_THINKING:
        kw["thinking"] = {"type": "enabled", "budget_tokens": int(thinking_budget)}
        kw["max_tokens"] = max_output + int(thinking_budget)      # max_tokens must be larger than the budget
    return kw


def usage_tokens(usage) -> tuple[int, int]:
    """(input incl. cached, output) from an Anthropic usage object."""
    inp = (getattr(usage, "input_tokens", 0) or 0) + (getattr(usage, "cache_read_input_tokens", 0) or 0) \
        + (getattr(usage, "cache_creation_input_tokens", 0) or 0)
    return inp, getattr(usage, "output_tokens", 0) or 0
