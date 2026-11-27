from . import paths
import os
from pathlib import Path


def _load_env() -> None:
    # the project .env first, then ~/.emilie/.env (it survives reinstalling Emilie); a real env var beats both
    for f in (Path(__file__).resolve().parent.parent / ".env", paths.HOME_DIR / ".env"):
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if v.strip():
                    os.environ.setdefault(k.strip(), v.strip())


_load_env()

from . import providers  # noqa: E402

_R = providers.resolve()
PROVIDER = _R["kind"]                                   # anthropic | openai (OpenAI-compatible)
PROVIDER_ID = _R["id"]                                  # preset name, e.g. "openrouter"
API_KEY = _R["key"]
BASE_URL = _R["base"]
MODEL = _R["model"]
VISION_MODEL = (paths.env("VISION_MODEL") or None) if PROVIDER_ID == "env" else None
