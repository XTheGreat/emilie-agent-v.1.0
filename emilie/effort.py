"""/effort: one lever to limit token usage.

Each level sets all of these at once:
  max_output     limit of answer tokens per model call
  tool_out_chars limit on the length of tool output sent back to the model
  read_lines     default line limit of read_file
  max_rounds     limit of rounds (model calls) per message, prevents runaway loops
  compact_at     the history is summarised automatically when the estimated context passes this
  style          answer-style instruction appended to the system prompt
"""
from . import paths
import json
from dataclasses import dataclass
from pathlib import Path
from .i18n import N_

HOME_DIR = paths.HOME_DIR
SETTINGS = HOME_DIR / "settings.json"


@dataclass(frozen=True)
class Effort:
    name: str
    max_output: int
    tool_out_chars: int
    read_lines: int
    max_rounds: int
    compact_at: int
    style: str
    desc: str


LEVELS: dict[str, Effort] = {
    "low": Effort("low", 1024, 4_000, 150, 6, 12_000,
                  "Answer very briefly (at most 3 sentences). Get straight to the point, no filler. "
                  "Avoid tool calls that are not really needed.",
                  N_('saver: short answers, small tool output')),
    "medium": Effort("medium", 4096, 10_000, 500, 15, 40_000,
                     "Answer concisely and to the point; explain only as needed.",
                     N_('balanced (default)')),
    "high": Effort("high", 8192, 20_000, 2000, 30, 90_000,
                   "Work carefully, explain important decisions, and verify the result.",
                   N_('thorough: looser answer and context limits')),
    "max": Effort("max", 16384, 40_000, 2000, 60, 160_000,
                  "Very thorough: check edge cases and verify by running tests when available.",
                  N_('no limits: loosest caps, spends tokens freely')),
}
DEFAULT = "medium"


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS.read_text())
    except (OSError, ValueError):
        return {}


def save_settings(**kv) -> None:
    HOME_DIR.mkdir(parents=True, exist_ok=True)
    data = load_settings()
    data.update(kv)
    SETTINGS.write_text(json.dumps(data, indent=2))


def load_effort() -> Effort:
    return LEVELS.get(load_settings().get("effort", DEFAULT), LEVELS[DEFAULT])
