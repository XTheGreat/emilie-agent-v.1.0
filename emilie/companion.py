"""What makes her feel like a person on the video call (Alt+V): time sense, a mood of the day, closeness that grows,
and a small private memory of the user. Spec: docs/VIDEO_CALL_COMPANION.md

The memory is plain text in ~/.emilie/companion.json (mode 600): no pictures, no audio, no video. `/camera memory` shows it,
`/camera forget` deletes it, `/camera memory off` stops saving it. Nothing here calls a model; agent.py does that.
"""
from . import paths
import json
import os
import random
import re
import threading
import time
from datetime import datetime

from . import effort

FILE = paths.HOME_DIR / "companion.json"
MAX_FACTS, MAX_MOMENTS, MAX_LINES = 40, 20, 14
SEED_CHANCE = 0.45                   # chance that a glance also gets a topic idea picked by the code
_lock = threading.RLock()

EMPTY = {"calls": 0, "closeness": 0.0, "last_call_end": 0.0, "last_outcome": "", "last_seen": "", "last_seen_at": 0.0,
         "facts": [], "moments": [], "recent_lines": []}


# ------------------------------------------------------------------ storage
def enabled() -> bool:
    return effort.load_settings().get("companion_memory", True) is not False


def load() -> dict:
    st = json.loads(json.dumps(EMPTY))
    if not enabled():
        return st
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return st
    if isinstance(data, dict):
        for k, v in EMPTY.items():
            if isinstance(data.get(k), type(v)):
                st[k] = data[k]
    return st


def save(st: dict) -> None:
    if not enabled():
        return
    with _lock:
        try:
            FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
            os.chmod(tmp, 0o600)
            os.replace(tmp, FILE)
        except OSError:
            pass


def forget() -> bool:
    try:
        FILE.unlink()
        return True
    except OSError:
        return False


# ------------------------------------------------------------------ time and mood
def part_of_day(h: int) -> str:
    if h < 5:
        return "the middle of the night"
    if h < 9:
        return "early morning"
    if h < 12:
        return "morning"
    if h < 15:
        return "midday / early afternoon"
    if h < 18:
        return "afternoon"
    if h < 22:
        return "evening"
    return "late at night"


DAY_MOODS = [        # (weight, what she feels like today)
    (3, "cheerful and chatty today, small things make you smile"),
    (2, "a bit dreamy today, a little spacey, you wander off into thoughts"),
    (3, "calm and gentle today, unhurried"),
    (2, "playful and teasing today, a little restless"),
    (2, "a bit tired today, soft-spoken, slower to react"),
    (2, "thoughtful today, you ask deeper questions than usual"),
    (2, "cozy and affectionate today, you want to stay close"),
]

LIFE = {        # little things she may have been doing (flavour only, she may mention them)
    "the middle of the night": ["lying awake listening to the quiet", "reading under a blanket", "watching the rain"],
    "early morning": ["making tea", "opening the window for the fresh air", "still waking up"],
    "morning": ["tidying up her room", "writing little notes", "trying a new recipe"],
    "midday / early afternoon": ["eating something sweet", "reading a book", "resting from the afternoon sleepiness"],
    "afternoon": ["drawing a little", "baking something", "listening to music"],
    "evening": ["cooking dinner", "watching the sky turn orange", "stretching after a long day"],
    "late at night": ["drinking warm milk", "thinking about the day", "listening to soft music"],
}


def day_mood(now: datetime) -> str:
    rng = random.Random(now.toordinal() * 7919 + 17)         # same all day, different from day to day
    return rng.choices([m for _, m in DAY_MOODS], weights=[w for w, _ in DAY_MOODS])[0]


def doing_now(now: datetime) -> str:
    rng = random.Random(now.toordinal() * 31 + now.hour // 3)   # changes every three hours
    return rng.choice(LIFE[part_of_day(now.hour)])


def closeness_label(c: float) -> str:
    if c < 0.15:
        return "you are still getting to know each other: friendly but a little shy and polite"
    if c < 0.4:
        return "you are warming up to each other: relaxed, curious about them"
    if c < 0.7:
        return "comfortable friends: you tease a little, you have small inside jokes"
    return "very close: relaxed, affectionate, you can be silly and honest with them"


def gap_words(seconds: float) -> str:
    m = seconds / 60
    if m < 2:
        return "just now"
    if m < 90:
        return f"{int(m)} minutes ago"
    h = m / 60
    if h < 30:
        return f"about {int(h)} hours ago"
    d = h / 24
    return "yesterday" if d < 2 else f"{int(d)} days ago"


# ------------------------------------------------------------------ the call
def begin_call(st: dict, now: float | None = None) -> None:
    """Closeness fades slowly when you are away for a long time (never below zero)."""
    now = now or time.time()
    last = st.get("last_call_end") or 0
    if last:
        days = (now - last) / 86400
        if days > 3:
            st["closeness"] = max(0.0, st["closeness"] - 0.004 * (days - 3))
    st["calls"] = st.get("calls", 0) + 1


def context(st: dict, now: datetime | None = None) -> str:
    """The private notes block that goes into every glance. Colour, not a script."""
    now = now or datetime.now()
    t = now.timestamp()
    out = ["# What you know right now (private; let it colour how you speak, never recite it as a list)"]
    out.append(f"It is {now.strftime('%A %H:%M')} for the user ({part_of_day(now.hour)}). "
               f"Today you feel {day_mood(now)}. You were just {doing_now(now)}.")
    n, last = st.get("calls", 0), st.get("last_call_end") or 0
    if n <= 1 and not last:
        out.append("This is your very first video call with them.")
    else:
        when = gap_words(t - last) if last else "a while ago"
        out.append(f"This is call number {n}. The last call ended {when}"
                   + (f" ({st['last_outcome']})." if st.get("last_outcome") else "."))
    out.append(f"Between you two: {closeness_label(st.get('closeness', 0.0))}.")
    if st.get("facts"):
        out.append("What you know about them:\n" + "\n".join(f"- {f}" for f in st["facts"][-25:]))
    if st.get("moments"):
        out.append("Moments you shared:\n" + "\n".join(f"- {m}" for m in st["moments"][-8:]))
    if st.get("last_seen"):
        out.append(f"Last time you looked at them ({gap_words(t - (st.get('last_seen_at') or t))}) you noted: "
                   f"\"{st['last_seen']}\". Compare with now; mention a change only if it is notable and kind.")
    if st.get("recent_lines"):
        out.append("Things you said on your own lately (do not repeat them or their idea):\n"
                   + "\n".join(f"- {x}" for x in st["recent_lines"][-8:]))
    return "\n".join(out)


def pick_seed(st: dict, now: datetime | None = None, rng: random.Random | None = None) -> str:
    """Sometimes (not always) a topic idea chosen by the code, so she does not fall into one routine."""
    rng = rng or random
    if rng.random() > SEED_CHANCE:
        return ""
    now = now or datetime.now()
    ideas = [
        "Ask how their day is going, or how they feel right now.",
        "Ask what they plan to do next, or later today.",
        f"Mention something small from your own day (you were just {doing_now(now)}).",
        "Ask a playful, random question you have always wondered about.",
        "Make a light comment about the time of day, the weather, or the room.",
        "Say a small passing thought out loud, like people do when comfortable together.",
    ]
    if st.get("facts"):
        ideas += ["Follow up on something you know about them: " + rng.choice(st["facts"][-25:])] * 3
    if st.get("moments"):
        ideas.append("Bring up a moment you shared: " + rng.choice(st["moments"][-8:]))
    return rng.choice(ideas)


def record_line(st: dict, text: str) -> None:
    st["recent_lines"] = (st.get("recent_lines", []) + [text[:160]])[-MAX_LINES:]


def record_seen(st: dict, seen: str, now: float | None = None) -> None:
    seen = " ".join(seen.split())[:200]
    if seen:
        st["last_seen"], st["last_seen_at"] = seen, now or time.time()


# ------------------------------------------------------------------ what she learned (end of call)
def _norm(s: str) -> set:
    return set(re.findall(r"\w+", s.lower()))


def _dup(a: str, items: list) -> bool:
    na = _norm(a)
    for b in items:
        nb = _norm(b)
        if na and nb and len(na & nb) / len(na | nb) >= 0.7:
            return True
    return False


def merge_reflection(st: dict, data: dict, when: datetime | None = None) -> None:
    when = when or datetime.now()
    for f in data.get("facts") or []:
        if isinstance(f, str) and 3 <= len(f.strip()) <= 160 and not _dup(f, st["facts"]):
            st["facts"].append(f.strip())
    st["facts"] = st["facts"][-MAX_FACTS:]
    for m in data.get("moments") or []:
        if isinstance(m, str) and 3 <= len(m.strip()) <= 200 and not _dup(m, st["moments"]):
            st["moments"].append(f"({when.strftime('%Y-%m-%d')}) {m.strip()}")
    st["moments"] = st["moments"][-MAX_MOMENTS:]
    try:
        d = float(data.get("closeness_delta", 0))
    except (TypeError, ValueError):
        d = 0.0
    st["closeness"] = min(1.0, max(0.0, st.get("closeness", 0.0) + max(-0.05, min(0.1, d))))
    if data.get("outcome") in ("warm", "neutral", "lonely", "alone"):
        st["last_outcome"] = data["outcome"]
    st["last_call_end"] = when.timestamp()


# ------------------------------------------------------------------ what the user said about leaving
BYE = re.compile(
    r"(?<!\w)(?:dadah|daa+h|bye+|good\s*night|gnight|gtg|got\s+to\s+go|selamat\s+tidur|met\s+tidur|tidur\s+dulu|pamit\s+dulu|"
    r"jaa?\s*ne|oyasumi|mata\s+ne|sampai\s+(?:nanti|jumpa|besok|ketemu)|see\s+(?:you|ya)|"
    r"(?:(?:aku|gue|gw|saya)\s+)?(?:(?:mau|harus)\s+)?(?:pergi|pamit|off|keluar|cabut|tidur)\s+(?:dulu|ya|dl|nih|sekarang|ah))(?!\w)", re.I)
BRB = re.compile(
    r"(?<!\w)(?:brb|(?:se)?bentar(?:\s+(?:ya|dulu|yaa))?|tunggu\s+(?:sebentar|bentar)|ke\s+(?:toilet|kamar\s+mandi|wc)|"
    r"angkat\s+telepon|be\s+right\s+back|back\s+in\s+a\s+(?:bit|minute)|just\s+a\s+(?:sec|moment|minute))(?!\w)", re.I)


def detect_intent(text: str) -> str | None:
    """'bye' / 'brb' / None, from what the user typed or said. Plain words, no model. Only short messages count: a long
    message is about something else ("aku pergi ke toko tadi dan ..." is not a goodbye)."""
    t = text.strip()
    if not t or t.startswith("/") or len(t) > 80:
        return None
    if BYE.search(t):
        return "bye"
    if BRB.search(t):
        return "brb"
    return None


# ------------------------------------------------------------------ for /camera memory
def describe(st: dict) -> list[str]:
    now = datetime.now()
    out = [f"calls: {st.get('calls', 0)} · closeness: {st.get('closeness', 0.0):.2f} ({closeness_label(st.get('closeness', 0.0)).split(':')[0]})",
           f"today she feels: {day_mood(now)}",
           f"saving: {'on' if enabled() else 'OFF (nothing is kept between calls)'} · file: {FILE}"]
    if st.get("last_call_end"):
        out.append(f"last call ended {gap_words(time.time() - st['last_call_end'])} ({st.get('last_outcome') or '-'})")
    for title, key in (("she knows", "facts"), ("shared moments", "moments"), ("last seen", None)):
        if key and st.get(key):
            out.append(f"{title}:")
            out += [f"  - {x}" for x in st[key]]
        elif key is None and st.get("last_seen"):
            out.append(f"{title}: {st['last_seen']}")
    return out
