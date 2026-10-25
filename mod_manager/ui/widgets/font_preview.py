from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ..theme import tokens


class FontPreview(QtWidgets.QLabel):
    heightChanged = QtCore.Signal(int)

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        self.setWordWrap(True)
        self.setMinimumWidth(0)
        policy = self.sizePolicy()
        policy.setHorizontalPolicy(QtWidgets.QSizePolicy.Ignored)
        self.setSizePolicy(policy)
        self._fit_height()

    def heightForWidth(self, width: int) -> int:
        margins = self.contentsMargins()
        text_width = max(1, width - margins.left() - margins.right() - self.margin() * 2)
        bounds = self.fontMetrics().boundingRect(0, 0, text_width, 0, QtCore.Qt.TextWordWrap, self.text())
        return max(tokens.FONT_PREVIEW_MIN_HEIGHT, bounds.height() + margins.top() + margins.bottom() + self.margin() * 2)

    def _fit_height(self) -> None:
        height = self.heightForWidth(self.width())
        if self.minimumHeight() != height:
            self.setMinimumHeight(height)
            self.heightChanged.emit(height)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_height()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() in (QtCore.QEvent.FontChange, QtCore.QEvent.StyleChange):
            self._fit_height()
