from __future__ import annotations

from functools import lru_cache

from PySide6 import QtCore, QtGui

from ..i18n import t
from ..label_icons import icon_path, store_icon
from . import icons
from .theme import tokens


@lru_cache(maxsize=256)
def _file_icon(path: str) -> QtGui.QIcon:
    reader = QtGui.QImageReader(path)
    reader.setAutoTransform(True)
    size = reader.size()
    if not size.isValid():
        return QtGui.QIcon()
    extent = tokens.LABEL_ICON_PREVIEW_SIZE * max(tokens.ICON_SCALE_FACTORS)
    ratio = min(extent / size.width(), extent / size.height())
    scaled = QtCore.QSize(max(1, round(size.width() * ratio)), max(1, round(size.height() * ratio)))
    reader.setScaledSize(scaled)
    image = reader.read()
    if image.isNull():
        return QtGui.QIcon()
    image = image.scaled(scaled, QtCore.Qt.IgnoreAspectRatio, QtCore.Qt.SmoothTransformation)
    canvas = QtGui.QPixmap(extent, extent)
    canvas.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(canvas)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    rect = QtCore.QRectF((extent - image.width()) // 2, (extent - image.height()) // 2,
                        image.width(), image.height())
    radius = min(tokens.LABEL_ICON_RADIUS * extent / tokens.ICON_SIZE, min(rect.width(), rect.height()) / 2)
    clip = QtGui.QPainterPath()
    clip.addRoundedRect(rect, radius, radius)
    painter.setClipPath(clip)
    painter.drawImage(rect, image)
    painter.end()
    return QtGui.QIcon(canvas)


def custom_label_icon(definition) -> QtGui.QIcon:
    try:
        path = icon_path(definition.icon) if definition is not None else None
        return _file_icon(str(path)) if path is not None else QtGui.QIcon()
    except (OSError, ValueError, RuntimeError):
        return QtGui.QIcon()


def label_icon(definition, fallback: str = "label") -> QtGui.QIcon:
    custom = custom_label_icon(definition)
    return custom if not custom.isNull() else icons.standard_icon(fallback)


def invalidate_label_icons() -> None:
    _file_icon.cache_clear()


def import_label_icon(path: str) -> str:
    reader = QtGui.QImageReader(path)
    reader.setAutoTransform(True)
    image = reader.read()
    if image.isNull():
        raise ValueError(t("label_icon_unreadable"))
    buffer = QtCore.QBuffer()
    buffer.open(QtCore.QIODevice.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise OSError(t("label_icon_unreadable"))
    reference = store_icon(bytes(buffer.data()))
    _file_icon.cache_clear()
    return reference
