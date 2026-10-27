from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ..theme import tokens


def draw_spinner(painter, rect, color, phase: float) -> None:
    painter.save()
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    pen = QtGui.QPen(color, tokens.SPINNER_STROKE)
    pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
    inset = tokens.SPINNER_STROKE / 2
    painter.drawArc(QtCore.QRectF(rect).adjusted(inset, inset, -inset, -inset),
                    -round(phase * tokens.FULL_CIRCLE_DEGREES * tokens.QT_ARC_UNITS),
                    tokens.SPINNER_ARC_DEGREES * tokens.QT_ARC_UNITS)
    painter.restore()


class ActivityIndicator(QtWidgets.QWidget):
    def __init__(self, status_bar: QtWidgets.QStatusBar):
        super().__init__(status_bar)
        self.status_bar = status_bar
        self.phase = 0.0
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        status_bar.installEventFilter(self)
        self.hide()

    def reposition(self) -> None:
        parent = self.status_bar
        width = max(0, min(tokens.ACTIVITY_WIDTH, parent.width() - tokens.PAGE_MARGIN * 2))
        self.setGeometry((parent.width() - width) // 2, parent.height() - tokens.ACTIVITY_HEIGHT,
                         width, tokens.ACTIVITY_HEIGHT)

    def eventFilter(self, obj, event):
        if event.type() in (QtCore.QEvent.Type.Resize, QtCore.QEvent.Type.Show):
            self.reposition()
        return False

    def set_phase(self, phase: float) -> None:
        self.phase = phase
        self.update()

    def paintEvent(self, event) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(self.palette().highlight())
        segment = self.width() * tokens.ACTIVITY_SEGMENT_FRACTION
        left = (self.width() + segment) * self.phase - segment
        painter.drawRoundedRect(QtCore.QRectF(left, 0, segment, self.height()),
                                tokens.ACTIVITY_HEIGHT / 2, tokens.ACTIVITY_HEIGHT / 2)

    def shutdown(self) -> None:
        self.status_bar.removeEventFilter(self)
        self.hide()
