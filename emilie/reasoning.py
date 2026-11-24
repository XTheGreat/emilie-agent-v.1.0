"""How hard an OpenAI-compatible model thinks, from the effort level (/effort).

The effort level used to set only budgets (answer length, tool output, rounds, compaction). Models that reason before
they answer also take a switch for how much they think, and every provider names it differently:

  provider     field sent in the request body                 low        medium     high / max
  openai       reasoning_effort                               "low"      -          "high"
  gemini       reasoning_effort (Gemini's thinking level)     "low"      -          "high"
  groq         reasoning_effort                               "low"      -          "high"
  openrouter   reasoning: {effort}                            "low"      -          "high"
  nvidia       chat_template_kwargs.enable_thinking           false      -          true + reasoning_effort "high"

Medium sends nothing: the model's own default applies (Gemini 3 and Nemotron 3 already think fully by default, so for
them low is the level that changes most: fast, short, cheap). Other providers (DeepSeek, Ollama, a custom URL) get
nothing: their models choose by name (deepseek-reasoner) or the field is unknown there.

A model that cannot reason rejects the field on some providers (OpenAI, Groq: 400 "unsupported parameter"); the agent
then asks again without it and leaves that model alone for the rest of the session (rejected()). Claude, on the
Anthropic provider, uses its native effort parameter instead (claude.py).
"""
from __future__ import annotations

import re

_EFFORT = {"low": "low", "high": "high", "max": "high"}         # medium: the provider's default
# thinking counts against max_tokens there: at high / max the answer gets room on top of the thinking
_ROOM = {"gemini": {"high": 16384, "max": 32768}, "nvidia": {"high": 16384, "max": 32768}}
_FIELDS = re.compile(r"reasoning|chat_template_kwargs|enable_thinking|thinking|unrecognized request argument|"
                     r"unsupported parameter|extra inputs are not permitted|extra_forbidden", re.I)


def openai_extra(provider: str | None, model: str | None, effort: str) -> tuple[dict, int]:
    """(fields to add to the request body, smallest max_tokens to ask for: 0 = no change) for this provider,
    model and effort level. ({}, 0) when there is nothing to say."""
    level = _EFFORT.get(effort)
    if not level:
        return {}, 0
    p = (provider or "").lower()
    if p in ("openai", "gemini", "groq"):
        extra = {"reasoning_effort": level}
    elif p == "openrouter":
        extra = {"reasoning": {"effort": level}}
    elif p == "nvidia":
        on = effort in ("high", "max")
        extra = {"chat_template_kwargs": {"enable_thinking": on}}
        if on:
            extra["reasoning_effort"] = "high"
    else:
        return {}, 0
    return extra, _ROOM.get(p, {}).get(effort, 0)


def echoes(provider: str | None, model: str | None) -> bool:
    """DeepSeek's reasoning models want their own thinking (reasoning_content) sent back on an assistant message that
    made tool calls; without it the next request is refused with HTTP 400. Other providers do not take the field."""
    return "deepseek" in f"{provider or ''} {model or ''}".lower()


def for_request(messages: list[dict], provider: str | None, model: str | None) -> list[dict]:
    """The history as it goes to the provider: reasoning_content kept for the models that need it, left out for the rest."""
    if echoes(provider, model):
        return messages
    return [{k: v for k, v in m.items() if k != "reasoning_content"} if "reasoning_content" in m else m for m in messages]


def rejected(e: BaseException) -> bool:
    """A 400 / 422 that blames one of the thinking fields (the model or the server does not take it)."""
    return getattr(e, "status_code", None) in (400, 422) and bool(_FIELDS.search(str(e)))
