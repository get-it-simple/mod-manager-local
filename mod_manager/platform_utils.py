from __future__ import annotations

import platform
import stat
from pathlib import Path

def is_windows() -> bool:
    return platform.system().lower().startswith("win")


def is_junction(path: Path) -> bool:
    check = getattr(path, "is_junction", None)
    if check is not None:
        return check()
    if not is_windows():
        return False
    try:
        return path.lstat().st_reparse_tag == stat.IO_REPARSE_TAG_MOUNT_POINT
    except (OSError, AttributeError):
        return False
