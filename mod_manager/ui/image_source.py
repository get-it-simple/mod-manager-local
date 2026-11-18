from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6 import QtGui

from ..dragdrop import read_clipboard_paths
from ..i18n import t
from ..log import logger
from ..mods import is_image_file
from .image_clipboard import read_clipboard_image


@dataclass
class PreviewSource:
    path: Path
    release: Callable | None = None

    def close(self) -> None:
        release, self.release = self.release, None
        if release:
            try:
                release()
            except OSError as exc:
                logger.warning(t("cannot_release_temporary_preview_s"), exc)


def read_preview_image(path: Path) -> QtGui.QImage:
    reader = QtGui.QImageReader(str(path))
    reader.setAutoTransform(True)
    return reader.read()


def clipboard_source(paths_reader=None, image_reader=None, *, strict=False) -> PreviewSource | None:
    paths = (paths_reader or read_clipboard_paths)()
    if paths:
        if len(paths) == 1 and is_image_file(paths[0]):
            return PreviewSource(Path(paths[0]), getattr(paths, "close", None))
        release = getattr(paths, "close", None)
        if release:
            release()
        if strict:
            raise ValueError(t("paste_one_image_at_a_time") if len(paths) > 1 else t("label_icon_unreadable"))
        return None
    path = (image_reader or read_clipboard_image)()
    return PreviewSource(path, lambda: path.unlink(missing_ok=True)) if path else None
