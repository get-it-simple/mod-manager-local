from __future__ import annotations

from PySide6 import QtWidgets

from ...i18n import t
from .buttons import text_button
from .style_utils import apply_margins


class LibraryStatus(QtWidgets.QWidget):
    def __init__(self, retry, parent=None):
        super().__init__(parent)
        self.message = QtWidgets.QLabel(self)
        self.message.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        self.retry = text_button(t("retry_refresh"), t("retry_refresh"), retry, self, icon_name="reset")
        layout = apply_margins(QtWidgets.QHBoxLayout(self))
        layout.addWidget(self.message, 1)
        layout.addWidget(self.retry)
        self.hide()

    def update_state(self, error: str) -> None:
        self.message.setText(error)
        self.message.setToolTip(error)
        self.retry.setVisible(bool(error))
        self.setVisible(bool(error))
