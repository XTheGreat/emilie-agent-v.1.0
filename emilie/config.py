from . import paths
import os
from pathlib import Path


def _load_env() -> None:
    f = Path(__file__).resolve().parent.parent / ".env"
    if not f.exists():
        return
    for line in f.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
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
