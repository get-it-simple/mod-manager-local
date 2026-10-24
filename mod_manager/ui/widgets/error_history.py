from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ..models import configure_header
from ..models.error_model import ErrorHistoryModel
from ..theme import tokens
from .style_utils import apply_margins


class ErrorHistoryWidget(QtWidgets.QWidget):
    closeRequested = QtCore.Signal()

    def __init__(self, model: ErrorHistoryModel, parent=None):
        super().__init__(parent)
        self.table = QtWidgets.QTableView(self)
        self.table.setModel(model)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        configure_header(self.table, tokens.ERROR_COLUMNS)
        self.details = QtWidgets.QPlainTextEdit(self)
        self.details.setReadOnly(True)
        self.details.setAccessibleName("Full error details")
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close, parent=self)
        buttons.rejected.connect(self.closeRequested)
        layout = apply_margins(QtWidgets.QVBoxLayout(self), margins=tokens.DETAIL_MARGIN)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.details, 1)
        layout.addWidget(buttons)
        self.table.selectionModel().currentRowChanged.connect(self._show_entry)
        model.rowsInserted.connect(self._rows_inserted)
        if model.rowCount():
            self.table.selectRow(0)

    def _show_entry(self, current, previous) -> None:
        entry = current.data(QtCore.Qt.UserRole)
        self.details.setPlainText(entry.details() if entry else "")

    def _rows_inserted(self, parent, first: int, last: int) -> None:
        if not self.table.currentIndex().isValid():
            self.table.selectRow(first)
