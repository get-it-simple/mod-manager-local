from __future__ import annotations

import logging
from pathlib import Path

try:
    from app_paths import DATA_DIR
    _LOG_PATH = DATA_DIR / "mod-manager.log"
except Exception:
    _LOG_PATH = Path(__file__).resolve().parent.parent / "mod-manager.log"

logger = logging.getLogger("mod_manager")

def _setup() -> None:
    if logger.handlers:
        return
    logger.setLevel(logging.DEBUG)
    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(_LOG_PATH, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(fh)
    except Exception:
        pass

_setup()
