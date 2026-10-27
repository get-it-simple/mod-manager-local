from __future__ import annotations

from PySide6 import QtWidgets

from ...i18n import t
from .buttons import text_button
from .style_utils import apply_margins


class LibraryStatus(QtWidgets.QWidget):
    def __init__(self, retry, parent=None):
        super().__init__(parent)
        self.message = QtWidgets.QLabel(self)
        self.message.setWordWrap(True)
        self.retry = text_button(t("retry_refresh"), t("retry_refresh"), retry, self, icon_name="reset")
        layout = apply_margins(QtWidgets.QHBoxLayout(self))
        layout.addWidget(self.message, 1)
        layout.addWidget(self.retry)
        self.hide()

    def update_state(self, loading: bool, error: str, has_snapshot: bool):
        self.message.setText(error or (t("updating_library") if has_snapshot else t("loading_library")))
        self.retry.setVisible(bool(error))
        self.setVisible(loading or bool(error))
