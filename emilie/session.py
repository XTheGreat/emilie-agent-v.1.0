"""Save / resume sessions per working folder (~/.emilie/sessions/<folder-hash>/<id>.json)."""
import hashlib
import json
import time
import uuid
from pathlib import Path

from .effort import HOME_DIR

ROOT = HOME_DIR / "sessions"


def _dir(cwd: str) -> Path:
    d = ROOT / hashlib.sha1(str(Path(cwd).resolve()).encode()).hexdigest()[:10]
    d.mkdir(parents=True, exist_ok=True)
    return d


def new_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]


def _title(messages: list[dict]) -> str:
    for m in messages:
        c = m.get("content")
        if m.get("role") == "user":
            if isinstance(c, str):
                return " ".join(c.split())[:70]
            if isinstance(c, list):
                for p in c:
                    if isinstance(p, dict) and p.get("type") == "text":
                        return " ".join(p["text"].split())[:70]
    return "(empty)"


def save(cwd: str, sid: str, messages: list[dict], model: str, created: float) -> None:
    if not messages:
        return
    data = {"id": sid, "cwd": str(Path(cwd).resolve()), "created": created, "updated": time.time(),
            "title": _title(messages), "model": model, "messages": messages}
    tmp = _dir(cwd) / f"{sid}.json.tmp"
    tmp.write_text(json.dumps(data, ensure_ascii=False, default=str))
    tmp.replace(_dir(cwd) / f"{sid}.json")


def list_sessions(cwd: str, limit: int = 12) -> list[dict]:
    out = []
    for f in _dir(cwd).glob("*.json"):
        try:
            d = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        out.append({"id": d["id"], "title": d.get("title", ""), "updated": d.get("updated", 0),
                    "n": len(d.get("messages", []))})
    return sorted(out, key=lambda x: x["updated"], reverse=True)[:limit]


def load(cwd: str, sid: str) -> dict | None:
    try:
        return json.loads((_dir(cwd) / f"{sid}.json").read_text())
    except (OSError, ValueError):
        return None


def ago(ts: float) -> str:
    s = int(time.time() - ts)
    for n, u in ((86400, "days"), (3600, "hours"), (60, "min")):
        if s >= n:
            return f"{s // n} {u} ago"
    return "just now"
