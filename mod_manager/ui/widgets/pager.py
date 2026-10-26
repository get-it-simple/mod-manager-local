from __future__ import annotations

from ...i18n import t

from PySide6 import QtCore, QtGui, QtWidgets

from ..theme import tokens
from .style_utils import apply_margins

PAGE_LABEL = t('page_page_pages')


def page_text(page: int, pages: int) -> str:
    return PAGE_LABEL.format(page=page, pages=pages)


class PageControl(QtWidgets.QWidget):
    pageRequested = QtCore.Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._page = 1
        self._pages = 1
        layout = apply_margins(QtWidgets.QHBoxLayout(self), margins=None, spacing=tokens.SPACE_SM)
        layout.addWidget(QtWidgets.QLabel(t('page'), self))
        self.input = QtWidgets.QLineEdit("1", self)
        self.input.setAlignment(QtCore.Qt.AlignCenter)
        self.input.setFixedWidth(tokens.PAGE_INPUT_WIDTH)
        self.validator = QtGui.QIntValidator(1, 1, self.input)
        self.input.setValidator(self.validator)
        self.input.returnPressed.connect(self._submit)
        layout.addWidget(self.input)
        self.total = QtWidgets.QLabel("/ 1", self)
        layout.addWidget(self.total)

    def _submit(self) -> None:
        text = self.input.text().strip()
        state, _text, _position = self.validator.validate(text, 0)
        if state != QtGui.QValidator.Acceptable:
            self.input.setText(str(self._page))
            return
        self.pageRequested.emit(int(text))

    def set_page(self, page: int, pages: int) -> None:
        self._pages = max(1, int(pages))
        self._page = max(1, min(int(page), self._pages))
        self.validator.setRange(1, self._pages)
        self.input.setText(str(self._page))
        self.total.setText(f"/ {self._pages}")

    def text(self) -> str:
        return page_text(self._page, self._pages)


PageLabel = PageControl
