"""Built-in provider presets + saved API keys.

Pick a provider with `emilie --setup` (or `/provider`), paste the key once, done.
Keys live in ~/.emilie/keys.json (chmod 600), never in the repo.
Environment variables (EMILIE_* in .env) still override everything, so old setups keep working.
"""
from . import paths
import json
import os
from pathlib import Path
from .i18n import t as tr_, N_

HOME = paths.HOME_DIR
KEYS = HOME / "keys.json"
SETTINGS = HOME / "settings.json"

# id -> kind (openai = OpenAI-compatible API | anthropic), base_url, default model, key hint
PRESETS: dict[str, dict] = {
    "anthropic":  {"label": N_('Anthropic (Claude)'), "kind": "anthropic", "base": None,
                   "model": "claude-sonnet-5-5", "hint": "console.anthropic.com", "env": "ANTHROPIC_API_KEY"},
    "openai":     {"label": "OpenAI", "kind": "openai", "base": "https://api.openai.com/v1",
                   "model": "gpt-4.1", "hint": "platform.openai.com/api-keys", "env": "OPENAI_API_KEY"},
    "openrouter": {"label": N_('OpenRouter (many models)'), "kind": "openai", "base": "https://openrouter.ai/api/v1",
                   "model": "openai/gpt-4o-mini", "hint": "openrouter.ai/keys", "env": "OPENROUTER_API_KEY"},
    "nvidia":     {"label": N_("NVIDIA (build.nvidia.com)"), "kind": "openai", "base": "https://integrate.api.nvidia.com/v1",
                   "model": "nvidia/nemotron-3.5-super-vl-120b-a12b", "hint": "build.nvidia.com -> your profile -> API keys (nvapi-...)",
                   "env": "NVIDIA_API_KEY"},
    "deepseek":   {"label": "DeepSeek", "kind": "openai", "base": "https://api.deepseek.com/v1",
                   "model": "deepseek-chat", "hint": "platform.deepseek.com", "env": "DEEPSEEK_API_KEY"},
    "gemini":     {"label": N_('Google Gemini'), "kind": "openai",
                   "base": "https://generativelanguage.googleapis.com/v1beta/openai/",
                   "model": "gemini-2.5-flash", "hint": "aistudio.google.com/apikey", "env": "GEMINI_API_KEY"},
    "groq":       {"label": "Groq", "kind": "openai", "base": "https://api.groq.com/openai/v1",
                   "model": "llama-3.3-70b-versatile", "hint": "console.groq.com/keys", "env": "GROQ_API_KEY"},
    "bankai":     {"label": "Bankai", "kind": "openai", "base": "https://bankai.web.id/api",
                   "model": "deepseek-v4.1-flash-mod", "hint": "bankai.web.id dashboard (sk-qwen-...)", "env": None},
    "ollama":     {"label": N_('Ollama (local, no key)'), "kind": "openai", "base": "http://localhost:11434/v1",
                   "model": "qwen2.5-coder", "hint": N_('no key needed'), "env": None, "nokey": True},
    "custom":     {"label": N_('Custom (any OpenAI-compatible URL, e.g. a router)'), "kind": "openai", "base": None,
                   "model": None, "hint": N_('you will be asked for the base URL and model'), "env": None},
}


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def load_keys() -> dict:
    return _read(KEYS)


def save_provider(pid: str, key: str | None = None, base: str | None = None, model: str | None = None) -> None:
    """Remember the chosen provider (+ key / custom base url / model)."""
    HOME.mkdir(parents=True, exist_ok=True)
    keys = load_keys()
    entry = keys.get(pid, {})
    if key is not None:
        entry["key"] = key
    if base:
        entry["base"] = base
    if model:
        entry["model"] = model
    keys[pid] = entry
    fd = os.open(KEYS, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(keys, f, indent=2)
    os.chmod(KEYS, 0o600)
    st = _read(SETTINGS)
    st["provider"] = pid
    st.pop("model", None)                    # model names differ per provider: back to that provider's default
    SETTINGS.write_text(json.dumps(st, indent=2))


def resolve() -> dict:
    """{id, kind, base, model, key}. A provider chosen with `emilie --setup` wins; else legacy EMILIE_* env."""
    pid = _read(SETTINGS).get("provider")
    if pid in PRESETS:
        p, saved = PRESETS[pid], load_keys().get(pid, {})
        key = saved.get("key") or (os.environ.get(p["env"]) if p.get("env") else None)
        if p.get("nokey"):
            key = key or "ollama"
        if key:
            return {"id": pid, "kind": p["kind"], "base": saved.get("base") or p["base"],
                    "model": saved.get("model") or p["model"], "key": key}
    env_key = paths.env("API_KEY")
    if env_key:
        return {"id": "env", "kind": paths.env("PROVIDER", "anthropic"),
                "base": paths.env("BASE_URL") or None,
                "model": paths.env("MODEL", "claude-sonnet-5-5"), "key": env_key}
    anth = os.environ.get("ANTHROPIC_API_KEY")
    return {"id": "anthropic" if anth else None, "kind": "anthropic", "base": None,
            "model": "claude-sonnet-5-5", "key": anth}


def openrouter_models() -> list[dict]:
    """Public OpenRouter catalogue: [{id, inp, out, ctx}] (USD per 1M tokens). [] if offline."""
    import urllib.request
    try:
        data = json.load(urllib.request.urlopen("https://openrouter.ai/api/v1/models", timeout=15))["data"]
        out = []
        for m in data:
            pr, arch = m.get("pricing") or {}, m.get("architecture") or {}
            if pr.get("prompt") is None or pr.get("completion") is None:
                continue
            if arch.get("output_modalities") not in (None, ["text"]) or ":batch" in m["id"]:
                continue                                   # chat/text models only (no image/audio/batch variants)
            out.append({"id": m["id"], "inp": float(pr["prompt"]) * 1e6, "out": float(pr["completion"]) * 1e6,
                        "ctx": m.get("context_length") or 0})
        return out
    except Exception:
        return []


def choose_openrouter_model(default: str) -> str | None:
    """Show free + cheapest models with prices; user picks by number, id or search text."""
    ms = openrouter_models()
    if not ms:
        print(tr_('(could not load the model list; type a model id, see openrouter.ai/models)'))
        return None
    free = sorted((m for m in ms if m["inp"] == 0 and m["out"] == 0), key=lambda m: -m["ctx"])
    paid = sorted((m for m in ms if m["inp"] > 0 or m["out"] > 0), key=lambda m: m["inp"] + m["out"])
    shown = free[:12] + paid[:12]

    def table(rows, start=1):
        print(tr_('  {0:>3}  {1:<46} {2:<30} context', '#', 'model', 'price per 1M tokens (in/out)'))
        for i, m in enumerate(rows, start):
            price = ("FREE" if m["inp"] == 0 and m["out"] == 0 else
                     tr_('varies (router, unpredictable)') if m["inp"] < 0 else f"${m['inp']:.2f} / ${m['out']:.2f}")
            print(f"  {i:>3}  {m['id']:<46} {price:<30} {m['ctx'] // 1000}k")
    print(tr_('\nOpenRouter models ({0} total). Free ones first, then the cheapest paid ones:\n', len(ms)))
    table(shown)
    byid = {m["id"]: m for m in ms}
    while True:
        raw = input(tr_("\nNumber, exact model id, or search text (e.g. 'claude'; Enter = default): ")).strip()
        if not raw:
            raw = default
        if raw.isdigit() and 1 <= int(raw) <= len(shown):
            pick = shown[int(raw) - 1]
        elif raw in byid:
            pick = byid[raw]
        else:
            hits = [m for m in ms if raw.lower() in m["id"].lower()][:25]
            if not hits:
                print(tr_('no match, try another search'))
                continue
            print()
            table(hits)
            shown = hits
            continue
        if pick["inp"] == 0 and pick["out"] == 0:
            print(tr_('-> {0}  (FREE)', pick['id']))
            return pick["id"]
        if pick["inp"] < 0:
            print(tr_('-> {0} is a router with VARIABLE price (it may pick expensive models). Not recommended.', pick['id']))
        ok = input(tr_('-> {0} is PAID: ${1:.2f} in / ${2:.2f} out per 1M tokens. Use it? [y/N] ', pick['id'], pick['inp'], pick['out'])).strip().lower()
        if ok in ("y", "yes"):
            return pick["id"]


def has_key() -> bool:
    return bool(resolve()["key"])


def setup(pid: str | None = None) -> bool:
    """Interactive setup in a plain terminal (key is typed hidden, never lands in history)."""
    import getpass
    import difflib
    ids = list(PRESETS)

    def unknown(name: str) -> None:
        near = difflib.get_close_matches(name.lower(), ids, n=1, cutoff=0.5)
        print(tr_("Unknown provider '{name}'.", name=name) + (tr_(" Did you mean '{0}'?", near[0]) if near else ""))
        print(tr_('Valid names: ') + ", ".join(ids))

    if pid is not None and pid.lower() not in PRESETS:
        unknown(pid)
        pid = None
    elif pid is not None:
        pid = pid.lower()
    if pid is None:
        print(tr_('\nChoose a provider:\n'))
        cur = resolve()["id"]
        for i, k in enumerate(ids, 1):
            have = tr_('key saved') if load_keys().get(k, {}).get("key") or PRESETS[k].get("nokey") else ""
            print(f"  {i}. {tr_(PRESETS[k]['label']):<52} {have}{'  <- current' if k == cur else ''}")
        for attempt in range(3):
            try:
                raw = input(tr_('\nNumber or name (Enter to cancel): ')).strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                return False
            if not raw:
                print(tr_('cancelled, nothing changed'))
                return False
            pid = ids[int(raw) - 1] if raw.isdigit() and 1 <= int(raw) <= len(ids) else raw
            if pid in PRESETS:
                break
            unknown(raw)
            pid = None
        if pid is None:
            print(tr_('too many wrong answers, nothing changed'))
            return False
    p = PRESETS[pid]
    base = model = key = None
    try:
        if pid == "custom":
            base = input(tr_('Base URL (e.g. http://localhost:20128/v1): ')).strip()
            model = input(tr_('Model name: ')).strip()
        if not p.get("nokey"):
            print(tr_('\nGet a key at: {0}', tr_(p['hint'])) if pid != "custom" else "")
            saved = load_keys().get(pid, {}).get("key")
            if saved and pid != "custom":                       # already saved: Enter keeps it, no need to paste again
                key = getpass.getpass(tr_("A key is already saved for this provider. Enter = keep it, or paste a new one (hidden): ")).strip() or saved
            else:
                key = getpass.getpass(tr_('Paste API key (hidden') + (tr_(', Enter if none') if pid == "custom" else "") + "): ").strip()
            if not key and pid == "custom":
                key = "none"
            if not key:
                print(tr_('no key entered, nothing saved'))
                return False
        if pid == "openrouter":
            model = choose_openrouter_model(p["model"])
        elif pid != "custom" and not p.get("nokey"):
            print(tr_('\nDefault model: {0}  (paid providers bill this to YOUR key; check prices on their site)', p['model']))
            m = input(tr_('Model to use (Enter = default): ')).strip()
            model = m or None
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    save_provider(pid, key, base, model)
    print(tr_('\nSaved. Provider: {0}  (key stored in {KEYS}, chmod 600)', tr_(p['label']), KEYS=KEYS))
    print(tr_("Change the model later with /model <name>. Check the price on the provider's site first.\n"))
    return True
