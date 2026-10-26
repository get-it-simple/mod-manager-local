from __future__ import annotations

import math

from PySide6 import QtCore, QtGui, QtWidgets

from .theme import tokens

STANDARD_ICONS = {
    "add": "SP_DialogApplyButton",
    "back": "SP_ArrowBack",
    "clear": "SP_DialogResetButton",
    "delete": "SP_TrashIcon",
    "folder": "SP_DirOpenIcon",
    "forward": "SP_ArrowForward",
    "image": "SP_FileIcon",
    "import": "SP_FileDialogNewFolder",
    "install": "SP_DialogApplyButton",
    "list": "SP_FileDialogDetailedView",
    "menu": "SP_TitleBarMenuButton",
    "open": "SP_DirIcon",
    "remove": "SP_DialogCancelButton",
    "save": "SP_DialogSaveButton",
    "search": "SP_FileDialogContentsView",
    "toggle": "SP_BrowserReload",
    "uninstall": "SP_DialogDiscardButton",
}

CUSTOM_ICONS = {
    "broken",
    "delete",
    "edit",
    "favorite",
    "favorite_filled",
    "filter_apply",
    "filter_clear",
    "settings",
    "submit",
}

FALLBACK_ICON = "SP_FileIcon"


def standard_icon(name: str, style=None) -> QtGui.QIcon:
    if name in CUSTOM_ICONS or name in tokens.GLYPH_PATHS:
        app = QtWidgets.QApplication.instance()
        palette = app.palette() if app is not None else QtGui.QPalette()
        color = palette.color(QtGui.QPalette.ButtonText)
        icon = QtGui.QIcon()
        for factor in tokens.ICON_SCALE_FACTORS:
            size = tokens.ICON_SIZE * factor
            icon.addPixmap(glyph_icon(name, color, size).pixmap(size, size))
        return icon
    style = style or QtWidgets.QApplication.style()
    pixmap_name = STANDARD_ICONS.get(name, FALLBACK_ICON)
    return style.standardIcon(getattr(QtWidgets.QStyle, pixmap_name))


def _painter(pixmap: QtGui.QPixmap) -> QtGui.QPainter:
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    return painter


def _transparent_pixmap(size: int) -> QtGui.QPixmap:
    pixmap = QtGui.QPixmap(size, size)
    pixmap.fill(QtCore.Qt.transparent)
    return pixmap


def _round_pen(color, width: float) -> QtGui.QPen:
    return QtGui.QPen(QtGui.QColor(color), width, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin)


def _path(points) -> QtGui.QPainterPath:
    path = QtGui.QPainterPath()
    path.moveTo(*points[0])
    for point in points[1:]:
        path.lineTo(*point)
    return path


def _star_path(size: int) -> QtGui.QPainterPath:
    center = size / 2
    path = QtGui.QPainterPath()
    for index in range(tokens.STAR_POINTS * 2):
        radius = tokens.STAR_OUTER_RADIUS if index % 2 == 0 else tokens.STAR_INNER_RADIUS
        radius *= size / tokens.ICON_SIZE
        angle = math.radians(tokens.STAR_START_DEGREES + index * tokens.STAR_STEP_DEGREES)
        point = QtCore.QPointF(center + math.cos(angle) * radius, center + math.sin(angle) * radius)
        if index == 0:
            path.moveTo(point)
        else:
            path.lineTo(point)
    path.closeSubpath()
    return path


def _scaled_path(points, size: int) -> QtGui.QPainterPath:
    scale = size / tokens.ICON_SIZE
    return _path([(x * scale, y * scale) for x, y in points])


def glyph_icon(name: str, color, size: int = tokens.ICON_SIZE) -> QtGui.QIcon:
    pixmap = _transparent_pixmap(size)
    painter = _painter(pixmap)
    pen = _round_pen(color, tokens.GLYPH_PEN * size / tokens.ICON_SIZE)
    painter.setPen(pen)
    painter.setBrush(QtCore.Qt.NoBrush)
    scale = size / tokens.ICON_SIZE

    if name in tokens.GLYPH_PATHS:
        for points in tokens.GLYPH_PATHS[name]:
            painter.drawPath(_scaled_path(points, size))
        if name in tokens.GLYPH_CIRCLES:
            painter.drawEllipse(QtCore.QRectF(*(part * scale for part in tokens.GLYPH_CIRCLES[name])))
    elif name in {"favorite", "favorite_filled"}:
        path = _star_path(size)
        if name == "favorite_filled":
            painter.setBrush(QtGui.QColor(color))
        painter.drawPath(path)
    elif name == "settings":
        center = QtCore.QPointF(tokens.GLYPH_CENTER * scale, tokens.GLYPH_CENTER * scale)
        painter.drawEllipse(center, tokens.GLYPH_LARGE_RADIUS * scale, tokens.GLYPH_LARGE_RADIUS * scale)
        painter.drawEllipse(center, tokens.GLYPH_SMALL_RADIUS * scale, tokens.GLYPH_SMALL_RADIUS * scale)
        for index in range(tokens.STAR_POINTS + 3):
            angle = math.radians(index * 45)
            inner = tokens.GLYPH_LARGE_RADIUS * scale
            outer = (tokens.GLYPH_LARGE_RADIUS + tokens.GLYPH_MARGIN) * scale
            painter.drawLine(
                QtCore.QPointF(center.x() + math.cos(angle) * inner, center.y() + math.sin(angle) * inner),
                QtCore.QPointF(center.x() + math.cos(angle) * outer, center.y() + math.sin(angle) * outer),
            )
    elif name == "delete":
        left = tokens.TRASH_LEFT * scale
        right = tokens.TRASH_RIGHT * scale
        top = tokens.TRASH_TOP * scale
        bottom = tokens.TRASH_BOTTOM * scale
        painter.drawLine(left, top, right, top)
        painter.drawLine((left + right) / 2 - scale, top - 2 * scale, (left + right) / 2 + scale, top - 2 * scale)
        painter.drawRoundedRect(QtCore.QRectF(left + scale, top + scale, right - left - 2 * scale, bottom - top), scale, scale)
        painter.drawLine(left + 3 * scale, top + 3 * scale, left + 3 * scale, bottom - scale)
        painter.drawLine(right - 3 * scale, top + 3 * scale, right - 3 * scale, bottom - scale)
    elif name in {"filter_apply", "filter_clear"}:
        painter.drawPath(_scaled_path(tokens.FILTER_PATH, size))
        if name == "filter_apply":
            painter.drawPath(_scaled_path(tokens.CHECK_SMALL_PATH, size))
        else:
            for start, end in tokens.CROSS_SMALL_PATH:
                painter.drawLine(
                    QtCore.QPointF(start[0] * scale, start[1] * scale),
                    QtCore.QPointF(end[0] * scale, end[1] * scale),
                )
    elif name == "edit":
        painter.drawPath(_scaled_path(tokens.EDIT_PATH, size))
    elif name == "submit":
        painter.drawPath(_scaled_path(tokens.SUBMIT_PATH, size))
        painter.drawLine(3 * scale, 4 * scale, 3 * scale, 14 * scale)
    elif name == "broken":
        painter.drawPath(_scaled_path(tokens.BROKEN_LEFT_PATH, size))
        painter.drawPath(_scaled_path(tokens.BROKEN_RIGHT_PATH, size))
        painter.drawPath(_scaled_path(tokens.BROKEN_SLASH_PATH, size))

    painter.end()
    return QtGui.QIcon(pixmap)


def _check_pixmap(color, size: int, transparent: bool) -> QtGui.QPixmap:
    pixmap = _transparent_pixmap(size)
    if not transparent:
        painter = _painter(pixmap)
        painter.setPen(_round_pen(color, max(tokens.CHECK_PEN_MIN, size * tokens.CHECK_PEN_RATIO)))
        painter.drawPath(_path([(size * x, size * y) for x, y in tokens.CHECK_PATH]))
        painter.end()
    return pixmap


def check_icon(color, size: int = tokens.ICON_SIZE, transparent: bool = False) -> QtGui.QIcon:
    icon = QtGui.QIcon()
    for factor in tokens.ICON_SCALE_FACTORS:
        icon.addPixmap(_check_pixmap(color, size * factor, transparent))
    return icon


def sort_direction_icon(descending: bool, color, size: int = tokens.ICON_SIZE) -> QtGui.QIcon:
    pixmap = _transparent_pixmap(size)
    painter = _painter(pixmap)
    painter.setPen(_round_pen(color, tokens.SORT_ARROW_PEN))
    x = size // 2
    head = tokens.SORT_ARROW_HEAD
    margin = tokens.SORT_ARROW_MARGIN
    head_y = tokens.SORT_ARROW_HEAD_Y
    if descending:
        tip = size - margin - 1
        painter.drawLine(x, margin, x, tip)
        painter.drawLine(x, tip, x - head, size - head_y)
        painter.drawLine(x, tip, x + head, size - head_y)
    else:
        tip = margin + 1
        painter.drawLine(x, size - margin, x, tip)
        painter.drawLine(x, tip, x - head, head_y)
        painter.drawLine(x, tip, x + head, head_y)
    painter.end()
    return QtGui.QIcon(pixmap)


def state_icon(active: bool, palette, size: int = tokens.STATE_ICON_SIZE) -> QtGui.QIcon:
    pixmap = _transparent_pixmap(size)
    painter = _painter(pixmap)
    painter.setPen(_round_pen(palette.state_ok if active else palette.muted, tokens.STATE_ICON_PEN))
    if active:
        painter.drawPath(_path(tokens.STATE_CHECK_PATH))
    else:
        for (x1, y1), (x2, y2) in tokens.STATE_CROSS_PATH:
            painter.drawLine(x1, y1, x2, y2)
    painter.end()
    return QtGui.QIcon(pixmap)
