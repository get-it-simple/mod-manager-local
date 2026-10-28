from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from .operation_feedback import paint_operation


class OperationCover(QtWidgets.QWidget):
    def __init__(self, panel, theme):
        super().__init__(panel.viewport())
        self.panel = panel
        self.theme = theme
        self.frame = None
        self._before = QtGui.QPixmap()
        self._after = QtGui.QPixmap()
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.hide()
        panel.viewport().installEventFilter(self)

    def snapshot(self):
        origin = self.panel.frame.mapFrom(self.panel.viewport(), QtCore.QPoint())
        return self.panel.frame.grab(QtCore.QRect(origin, self.panel.viewport().size()))

    def set_frame(self, frame):
        if frame is not self.frame:
            self._before = self.snapshot() if frame is not None else QtGui.QPixmap()
            self._after = QtGui.QPixmap()
        self.frame = frame
        self.setGeometry(self.parentWidget().rect())
        self.setVisible(frame is not None)
        if frame is not None:
            self.raise_()
            self.update()

    def refresh_content(self):
        self._after = QtGui.QPixmap()
        self.update()

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.Type.Resize:
            self.setGeometry(obj.rect())
            self.refresh_content()
        return False

    def paintEvent(self, event):
        frame = self.frame
        if frame is None:
            return
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtGui.QColor(self.theme.palette.panel))
        if frame.content_opacity > 0:
            if frame.finished_at is not None and frame.elapsed >= frame.result_at:
                if self._after.isNull():
                    self._after = self.snapshot()
                image = self._after
            else:
                image = self._before
            painter.setOpacity(frame.content_opacity)
            painter.drawPixmap(self.rect(), image)
            painter.setOpacity(1.0)
        paint_operation(painter, self.rect(), frame, self.palette(), self.theme.palette.accent)
        painter.end()

    def shutdown(self):
        self.set_frame(None)
        self.panel.viewport().removeEventFilter(self)
