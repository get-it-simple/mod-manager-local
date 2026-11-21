from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import os
import re
import tempfile

from .i18n import t


def validate_icon_reference(value: str) -> str:
    if not isinstance(value, str) or (value and not re.fullmatch(r"label-icons/[a-f0-9]{64}[.]png", value)):
        raise ValueError(t("label_icon_invalid"))
    return value


def icon_path(reference: str) -> Path | None:
    from . import storage

    validate_icon_reference(reference)
    if not reference:
        return None
    root = storage.PROFILE_DATA_DIR
    candidate = root / reference
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise ValueError(t("label_icon_invalid"))
    return candidate


def store_icon(data: bytes) -> str:
    reference = f"label-icons/{sha256(data).hexdigest()}.png"
    target = icon_path(reference)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return reference

