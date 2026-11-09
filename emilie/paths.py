"""Where Emilie keeps its data: ~/.emilie (and ~/.emilie_history). Environment variables are EMILIE_*."""
import os
from pathlib import Path

HOME = Path.home()
HOME_DIR = HOME / ".emilie"
HISTORY = HOME / ".emilie_history"
IMAGES_DIR = HOME_DIR / "images"      # every image the user attaches is saved here, so tools can find it by path


def env(name: str, default: str | None = None) -> str | None:
    """EMILIE_<name>, else default."""
    return os.environ.get("EMILIE_" + name) or default
