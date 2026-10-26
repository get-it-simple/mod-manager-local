from __future__ import annotations

from ...i18n import t

from PySide6 import QtWidgets

from ..models.error_model import ErrorHistoryModel
from ..theme import tokens
from ..widgets.error_history import ErrorHistoryWidget
from ..widgets.style_utils import apply_margins


class ErrorHistoryDialog(QtWidgets.QDialog):
    def __init__(self, model: ErrorHistoryModel, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t('session_errors'))
        self.resize(*tokens.LARGE_DIALOG_SIZE)
        self.content = ErrorHistoryWidget(model, self)
        self.content.closeRequested.connect(self.close)
        apply_margins(QtWidgets.QVBoxLayout(self), margins=None).addWidget(self.content)
