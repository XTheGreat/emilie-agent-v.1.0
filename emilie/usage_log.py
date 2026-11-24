"""Token usage across all sessions, by provider and model (Settings -> Usage in the app).

Every model call (the conversation, sub-agents, helper calls) appends one line to ~/.emilie/usage.jsonl:
    {"t": 1763625600.1, "p": "nvidia", "m": "nvidia/nemotron-...", "i": 12345, "o": 678, "x": 1}
t = time, p = provider id, m = model, i/o = input/output tokens, x = 1 when the provider reported the numbers
(0 = Emilie estimated them because the provider sent none).

Each session runs in its own process, so a line is written with one call under a short file lock. The reader
(the desktop hub, a long-lived process) keeps per-day totals in memory and only parses lines added since its last read.
"""
from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict
from pathlib import Path

from .paths import HOME_DIR

FILE: Path = HOME_DIR / "usage.jsonl"
_wlock = threading.Lock()


def _lock(f, on: bool) -> None:
    """Lock byte 0 of the file (other processes wait a moment); best effort, never raises."""
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            for _ in range(50):
                try:
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK if on else msvcrt.LK_UNLCK, 1)
                    return
                except OSError:
                    if not on:
                        return
                    time.sleep(0.01)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX if on else fcntl.LOCK_UN)
    except Exception:
        pass


def record(provider: str, model: str, inp: int, out: int, exact: bool = True) -> None:
    """Add one call to the log. Never raises: counting must not break a conversation."""
    try:
        inp, out = int(inp or 0), int(out or 0)
        if inp <= 0 and out <= 0:
            return
        line = json.dumps({"t": round(time.time(), 1), "p": str(provider or "?"), "m": str(model or "?"),
                           "i": inp, "o": out, "x": 1 if exact else 0}, ensure_ascii=False) + "\n"
        FILE.parent.mkdir(parents=True, exist_ok=True)
        with _wlock, open(FILE, "a+b") as f:
            _lock(f, True)
            try:
                f.seek(0, os.SEEK_END)
                f.write(line.encode("utf-8"))
                f.flush()
            finally:
                _lock(f, False)
    except Exception:
        pass


def _label(pid: str) -> str:
    """'nvidia' -> 'NVIDIA' (the provider's name without its hint in brackets)."""
    try:
        from .providers import PRESETS
        p = PRESETS.get(pid)
        if p:
            return str(p["label"]).split(" (")[0]
    except Exception:
        pass
    return {"env": "Custom", "?": "Unknown"}.get(pid, pid)


class Ledger:
    """Per-day totals read from usage.jsonl; read() only parses what was appended since the last call."""

    def __init__(self, path: Path = FILE):
        self.path = path
        self.off = 0
        self.first: float | None = None
        # (day, provider, model) -> [calls, input, output, estimated calls]
        self.days: dict[tuple[str, str, str], list[int]] = defaultdict(lambda: [0, 0, 0, 0])
        self.lock = threading.Lock()

    def read(self) -> None:
        try:
            size = self.path.stat().st_size
        except OSError:
            return
        if size < self.off:                       # the file was replaced or emptied: start over
            self.off, self.first = 0, None
            self.days.clear()
        if size == self.off:
            return
        with open(self.path, "rb") as f:
            f.seek(self.off)
            chunk = f.read(size - self.off)
        end = chunk.rfind(b"\n")
        if end < 0:                               # half a line: wait for the rest
            return
        self.off += end + 1
        for raw in chunk[:end].splitlines():
            try:
                r = json.loads(raw)
                t = float(r["t"])
            except (ValueError, KeyError, TypeError):
                continue
            day = time.strftime("%Y-%m-%d", time.localtime(t))
            b = self.days[(day, str(r.get("p") or "?"), str(r.get("m") or "?"))]
            b[0] += 1
            b[1] += int(r.get("i") or 0)
            b[2] += int(r.get("o") or 0)
            b[3] += 0 if r.get("x", 1) else 1
            self.first = t if self.first is None else min(self.first, t)

    def summary(self, days: int | None = 30) -> dict:
        """Totals for the last `days` days (None = everything): per provider/model, overall and per day (or per
        week when the range is long), zero-filled so a chart can draw every day."""
        with self.lock:
            self.read()
            today = time.strftime("%Y-%m-%d")
            if days:
                start = time.strftime("%Y-%m-%d", time.localtime(time.time() - (days - 1) * 86400))
            else:
                start = min((d for d, _, _ in self.days), default=today)
            models: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0, 0, 0])
            per_day: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
            per_day_model: dict[str, dict[str, int]] = defaultdict(dict)
            for (d, p, m), b in self.days.items():
                if d < start or d > today:
                    continue
                mm = models[(p, m)]
                for i in range(4):
                    mm[i] += b[i]
                pd = per_day[d]
                pd[0] += b[0]; pd[1] += b[1]; pd[2] += b[2]
                key = f"{_label(p)} · {m}"
                per_day_model[d][key] = per_day_model[d].get(key, 0) + b[1] + b[2]
            # every day from start to today; weeks (Monday first) past 120 days so the chart stays readable
            span = []
            t = time.mktime(time.strptime(start, "%Y-%m-%d")) + 43200
            while True:
                d = time.strftime("%Y-%m-%d", time.localtime(t))
                if d > today:
                    break
                span.append(d)
                t += 86400
            weekly = len(span) > 120
            buckets: dict[str, dict] = {}
            for d in span:
                k = d
                if weekly:
                    tt = time.strptime(d, "%Y-%m-%d")
                    k = time.strftime("%Y-%m-%d", time.localtime(time.mktime(tt) - tt.tm_wday * 86400 + 43200))
                b = buckets.setdefault(k, {"day": k, "calls": 0, "in": 0, "out": 0, "models": {}})
                pd = per_day.get(d)
                if pd:
                    b["calls"] += pd[0]; b["in"] += pd[1]; b["out"] += pd[2]
                    for name, n in per_day_model[d].items():
                        b["models"][name] = b["models"].get(name, 0) + n
            rows = [{"provider": p, "label": _label(p), "model": m, "calls": b[0], "in": b[1], "out": b[2],
                     "estimated": b[3]} for (p, m), b in models.items()]
            rows.sort(key=lambda r: r["in"] + r["out"], reverse=True)
            tot = {"calls": sum(r["calls"] for r in rows), "in": sum(r["in"] for r in rows),
                   "out": sum(r["out"] for r in rows), "estimated": sum(r["estimated"] for r in rows)}
            return {"since": self.first, "start": start, "end": today, "days": days, "weekly": weekly,
                    "models": rows, "total": tot, "series": list(buckets.values()), "file": str(self.path)}


LEDGER = Ledger()
