from __future__ import annotations

from dataclasses import dataclass
from math import cos, pi

from PySide6 import QtCore, QtGui

from ..theme import colors, tokens


@dataclass
class OperationVisual:
    elapsed: int = 0
    finished_at: int | None = None
    success: bool = False

    @property
    def result_at(self) -> int:
        return max(tokens.OPERATION_FADE_MS + tokens.OPERATION_CYCLE_MS, self.finished_at or 0)

    @property
    def result_progress(self) -> float:
        if self.finished_at is None:
            return 0.0
        return tokens.clamp((self.elapsed - self.result_at) / tokens.OPERATION_RESULT_MS, 0.0, 1.0)

    @property
    def content_opacity(self) -> float:
        if self.elapsed < tokens.OPERATION_FADE_MS:
            return 1.0 - self.elapsed / tokens.OPERATION_FADE_MS
        if self.finished_at is None:
            return 0.0
        restore_at = self.result_at + tokens.OPERATION_RESULT_MS + tokens.OPERATION_HOLD_MS
        return tokens.clamp((self.elapsed - restore_at) / tokens.OPERATION_FADE_MS, 0.0, 1.0)

    @property
    def done(self) -> bool:
        end = self.result_at + tokens.OPERATION_RESULT_MS + tokens.OPERATION_HOLD_MS + tokens.OPERATION_FADE_MS
        return self.finished_at is not None and self.elapsed >= end


def paint_operation(painter, rect, frame: OperationVisual, palette, accent_color) -> None:
    opacity = 1.0 - frame.content_opacity
    if opacity <= 0 or frame.elapsed < tokens.OPERATION_FADE_MS:
        return
    painter.save()
    painter.setOpacity(opacity)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    size = max(0, min(tokens.OPERATION_INDICATOR_SIZE, rect.height() - tokens.OPERATION_INDICATOR_INSET * 2,
                      rect.width() - tokens.OPERATION_INDICATOR_INSET * 2))
    bounds = QtCore.QRectF(0, 0, size, size)
    bounds.moveCenter(QtCore.QRectF(rect).center())
    accent = QtGui.QColor(accent_color)
    result = frame.result_progress
    if frame.finished_at is not None and frame.elapsed >= frame.result_at:
        if not frame.success:
            accent = QtGui.QColor(colors.STATE_BAD)
        target = min(tokens.OPERATION_RESULT_SIZE, rect.height() - tokens.OPERATION_INDICATOR_INSET * 2,
                     rect.width() - tokens.OPERATION_INDICATOR_INSET * 2)
        grown = size + (target - size) * (1 - (1 - result) ** 3)
        bounds.setSize(QtCore.QSizeF(grown, grown))
        bounds.moveCenter(QtCore.QRectF(rect).center())
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(accent)
        painter.drawEllipse(bounds)
        pen = QtGui.QPen(QtGui.QColor(colors.readable_on(accent.name())), tokens.SPINNER_STROKE)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        path = QtGui.QPainterPath()
        def point(x, y):
            return QtCore.QPointF(bounds.left() + bounds.width() * x, bounds.top() + bounds.height() * y)
        if frame.success:
            path.moveTo(point(0.28, 0.51))
            path.lineTo(point(0.44, 0.67))
            path.lineTo(point(0.73, 0.35))
        else:
            path.moveTo(point(0.34, 0.34))
            path.lineTo(point(0.66, 0.66))
            path.moveTo(point(0.66, 0.34))
            path.lineTo(point(0.34, 0.66))
        painter.setOpacity(opacity * result)
        painter.drawPath(path)
    else:
        phase = max(0, frame.elapsed - tokens.OPERATION_FADE_MS) / tokens.OPERATION_CYCLE_MS % 1.0
        pen = QtGui.QPen(palette.color(QtGui.QPalette.ColorRole.Mid), tokens.BORDER_WIDTH)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawEllipse(bounds)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(accent)
        sweep = (0.5 - cos(phase * 2 * pi) / 2) * tokens.FULL_CIRCLE_DEGREES
        painter.drawPie(bounds, round(-phase * tokens.FULL_CIRCLE_DEGREES * tokens.QT_ARC_UNITS),
                        max(tokens.QT_ARC_UNITS, round(sweep * tokens.QT_ARC_UNITS)))
    painter.restore()
