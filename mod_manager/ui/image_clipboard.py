from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6 import QtWidgets

from ..dragdrop import read_clipboard_image as read_native_clipboard_image
from ..i18n import t


def clipboard_has_image() -> bool:
    mime = QtWidgets.QApplication.clipboard().mimeData()
    return mime is not None and mime.hasImage()


def read_clipboard_image() -> Path | None:
    image = QtWidgets.QApplication.clipboard().image().copy()
    if image.isNull():
        return read_native_clipboard_image()
    path = None
    saved = False
    try:
        with tempfile.NamedTemporaryFile(prefix="mods_clip_", suffix=".png", delete=False) as handle:
            path = Path(handle.name)
        if not image.save(str(path), "PNG"):
            raise OSError(t('cannot_prepare_the_preview_image'))
        saved = True
        return path
    finally:
        if path is not None and not saved:
            path.unlink(missing_ok=True)
