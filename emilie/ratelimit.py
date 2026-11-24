"""Riding out a provider's rate limit (HTTP 429) instead of failing the turn.

Free and shared endpoints (NVIDIA build.nvidia.com, OpenRouter's free models, Groq, a busy Anthropic) answer 429 "Too
Many Requests", 529 "overloaded" or 503 whenever the account or the model is over its limit, and on shared endpoints
that happens far below the published request rate when the model is busy. These limits work in windows of a minute or
more, so retrying after a few seconds (the old 2 s and 6 s) only collects the next 429 and a long turn ends in
"RateLimitError". Here:

- retry_wait(): the wait before the next try: what the provider asked for (Retry-After, x-ratelimit-reset-*, "try
  again in 20s") when it says so, else growing waits with jitter (5, 10, 20, 40, 60, 60 ... s), so parallel calls do
  not retry in lockstep.
- a cool-down shared by every Emilie process on this computer, per provider and model (each desktop session runs in
  its own process, and so does the terminal): after a 429 nobody calls that model until the wait is over, so sessions
  and sub-agents do not keep each other throttled. Kept in ~/.emilie/ratelimit.json.
- pacing: after a 429 the calls to that model are spaced out (a gap that grows with every 429, halves after a run of
  successful calls and is forgotten after a quiet while), so a long turn settles under the limit instead of hitting
  it every few steps.

Nothing here raises: a missing or broken state file only means no shared cool-down.
"""
from __future__ import annotations

import email.utils
import json
import os
import random
import re
import threading
import time
from datetime import datetime
from pathlib import Path

from .paths import HOME_DIR

STATE: Path = HOME_DIR / "ratelimit.json"
DEFAULT_RETRIES = 6           # settings.json "retries": how often a busy / rate-limited call is tried again
MAX_WAIT = 120.0              # one wait is never longer than this, whatever the provider asks
GIVE_UP_AFTER = 600.0         # a provider asking for more (a daily limit) is not waited for: retrying cannot help
GAP_MIN, GAP_MAX = 3.0, 20.0  # pacing after a 429: the first gap between calls and the largest one (seconds)
GAP_RELAX_AFTER = 4           # successful calls in a row before the gap is halved
GAP_FORGET = 300.0            # no 429 for this long: no pacing any more

_lock = threading.Lock()
_last: dict[str, float] = {}  # this process: when the latest call to a model was let through
_ok: dict[str, int] = {}      # this process: successful calls in a row since the last 429

class CoolingDown(RuntimeError):
    """An optional call (a session title, a camera glance) was skipped: the model is rate-limited right now."""


_QUOTA = re.compile(r"exceeded your current quota|insufficient[_ ]quota|insufficient (credits|balance|funds)|billing|"
                    r"per[- ]day|daily (limit|quota)|free-models-per-day", re.I)
_RATE = re.compile(r"rate.?limit|too many requests|\b429\b|requests per min|throttl", re.I)
_BUSY = re.compile(r"overload|temporar|try again|capacity|service unavailable|bad gateway|gateway time", re.I)
_BUSY_NAMES = ("connection", "internalserver", "overloaded", "serviceunavailable")


def key(provider: str | None, model: str | None) -> str:
    """Limits are per model on shared endpoints, so switching models (/model, /fallback) is not held back."""
    return f"{provider or '?'}:{model or '?'}"


def classify(e: BaseException) -> str | None:
    """'rate' (a 429 / rate limit), 'busy' (overloaded, a 5xx, a dropped connection), 'timeout', 'quota' (a used-up
    quota or daily limit: waiting minutes cannot help) or None (a wrong key, a bad request: retrying cannot help)."""
    if isinstance(e, (KeyboardInterrupt, SystemExit, GeneratorExit, CoolingDown)):
        return None
    name, text = type(e).__name__.lower(), str(e)
    code = getattr(e, "status_code", None)
    if isinstance(code, int):
        if code == 429:
            return "quota" if _QUOTA.search(text) else "rate"
        if code == 408:
            return "timeout"
        return "busy" if code in (409, 425, 500, 502, 503, 504, 529) else None
    if "timeout" in name or "timed out" in text.lower():
        return "timeout"
    if "ratelimit" in name or _RATE.search(text):
        return "quota" if _QUOTA.search(text) else "rate"
    if any(n in name for n in _BUSY_NAMES) or _BUSY.search(text):
        return "busy"
    return None


def describe(e: BaseException) -> str:
    """The provider's own words for a failed call ("This model is currently experiencing high demand ..."), instead
    of the SDK's 'Error code: 503 - [{...}]'. Google wraps its error in a list; others send {"error": {...}}."""
    body, msg = getattr(e, "body", None), None
    if isinstance(body, list) and body:
        body = body[0]
    if isinstance(body, dict):
        err = body.get("error", body)
        msg = err.get("message") if isinstance(err, dict) else err if isinstance(err, str) else None
    if not msg:
        m = re.search(r"""['"]message['"]\s*:\s*['"]([^'"]+)""", str(e))
        msg = m.group(1) if m else None
    return " ".join(str(msg or e).split())


# ------------------------------------------------------------------ what the provider asked for
def _duration(v) -> float | None:
    """'6s', '1m30s', '250ms', '0.5' -> seconds."""
    s = str(v or "").strip().lower()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        pass
    parts = re.fullmatch(r"(?:(\d+(?:\.\d+)?)h)?(?:(\d+(?:\.\d+)?)m(?!s))?(?:(\d+(?:\.\d+)?)s)?(?:(\d+(?:\.\d+)?)ms)?", s)
    if not parts or not any(parts.groups()):
        return None
    h, m, sec, ms = (float(x or 0) for x in parts.groups())
    return h * 3600 + m * 60 + sec + ms / 1000


def _until(v) -> float | None:
    """A reset moment as epoch seconds / milliseconds, an ISO time or seconds from now -> seconds from now."""
    s = str(v or "").strip()
    if not s:
        return None
    try:
        n = float(s)
        return n / 1000 - time.time() if n > 1e12 else n - time.time() if n > 1e9 else n
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() - time.time()
    except ValueError:
        return _duration(s)


def asked_wait(e: BaseException) -> float | None:
    """Seconds the provider asked to wait (retry-after-ms, retry-after as seconds or an HTTP date, the reset time of the
    exhausted x-ratelimit-* limit, or "try again in 20s" in the message). None when it did not say."""
    try:
        h = e.response.headers                           # type: ignore[attr-defined]
        get = lambda n: h.get(n)                         # noqa: E731
    except Exception:
        get = lambda n: None                             # noqa: E731
    try:
        if get("retry-after-ms"):
            return float(get("retry-after-ms")) / 1000
    except (TypeError, ValueError):
        pass
    ra = get("retry-after")
    if ra:
        try:
            return float(ra)
        except ValueError:
            try:
                return email.utils.parsedate_to_datetime(ra).timestamp() - time.time()
            except (TypeError, ValueError, IndexError):
                pass
    resets = {k: _duration(get(f"x-ratelimit-reset-{k}")) for k in ("requests", "tokens")}
    resets = {k: v for k, v in resets.items() if v is not None}
    spent = [v for k, v in resets.items() if str(get(f"x-ratelimit-remaining-{k}") or "").strip() == "0"]
    if spent or resets:
        return max(spent or resets.values())
    for name in ("x-ratelimit-reset", "ratelimit-reset", "anthropic-ratelimit-requests-reset"):
        r = _until(get(name))
        if r is not None:
            return r
    m = re.search(r"try again in\s+(\d+(?:\.\d+)?)\s*(ms|s|sec|seconds?|m|min|minutes?)\b", str(e), re.I)
    if m:
        n, unit = float(m.group(1)), m.group(2).lower()
        return n / 1000 if unit == "ms" else n * 60 if unit.startswith("m") else n
    return None


def retry_wait(attempt: int, e: BaseException) -> tuple[float, float | None]:
    """(seconds to wait before the next try, what the provider itself asked for or None). attempt counts from 0.
    Never shorter than the growing floor, so a provider that keeps saying '1s' does not burn every try in seconds."""
    kind = classify(e)
    if kind == "timeout":                                # a timeout already took minutes: just try once more
        return 2.0, None
    floor = (5.0 if kind == "rate" else 3.0) * 2 ** attempt
    asked = asked_wait(e)
    if asked is not None and asked > 0:
        return min(MAX_WAIT, max(asked + random.uniform(0.3, 1.5), floor / 2)), asked
    return min(60.0, floor) * random.uniform(0.85, 1.15), None


# ------------------------------------------------------------------ shared cool-down + pacing
def _read() -> dict:
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(d: dict) -> None:
    now = time.time()
    d = {k: v for k, v in d.items() if isinstance(v, dict)
         and (float(v.get("until", 0) or 0) > now or now - float(v.get("at", 0) or 0) < GAP_FORGET)}
    tmp = STATE.with_name(f"{STATE.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(d), encoding="utf-8")
        os.replace(tmp, STATE)                           # readers never see half a file
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _entry(d: dict, k: str) -> dict:
    s = d.get(k)
    return s if isinstance(s, dict) else {}


def cooldown_left(k: str) -> float:
    """Seconds until this model may be called again (0 = now)."""
    return max(0.0, float(_entry(_read(), k).get("until", 0) or 0) - time.time())


def note_limited(k: str, wait: float, rate: bool = True) -> None:
    """A 429 (rate=True) or an overloaded / failing server: nobody calls this model for `wait` seconds; after a 429
    the calls that follow are spaced out."""
    with _lock:
        d = _read()
        s = _entry(d, k)
        now = time.time()
        s["until"] = max(float(s.get("until", 0) or 0), now + max(0.0, wait))
        if rate:
            gap = float(s.get("gap", 0) or 0) if now - float(s.get("at", 0) or 0) < GAP_FORGET else 0.0
            s["gap"] = min(GAP_MAX, max(GAP_MIN, gap * 2))
            s["at"] = now
        d[k] = s
        _ok[k] = 0
        _write(d)


def note_ok(k: str) -> None:
    """A call went through. After a run of them the pacing gap is halved, and dropped below the first gap."""
    with _lock:
        _ok[k] = n = _ok.get(k, 0) + 1
        if n % GAP_RELAX_AFTER:
            return
        d = _read()
        s = _entry(d, k)
        if not s.get("gap"):
            return
        half = float(s["gap"]) / 2
        s["gap"] = half if half >= GAP_MIN else 0.0
        d[k] = s
        _write(d)


def wait_needed(k: str) -> float:
    """Seconds to wait before the next call to this model may go out: the shared cool-down, then the pacing gap.
    Reserves the slot, so parallel callers (sub-agents) leave a gap between them instead of all going at once."""
    with _lock:
        now = time.time()
        s = _entry(_read(), k)
        gap = float(s.get("gap", 0) or 0)
        if now - float(s.get("at", 0) or 0) >= GAP_FORGET:
            gap = 0.0                                    # quiet for a while: the limit is not being hit any more
        start = max(now, float(s.get("until", 0) or 0), _last.get(k, 0.0) + gap)
        _last[k] = start
        return start - now
