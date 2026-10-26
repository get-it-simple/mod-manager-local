from __future__ import annotations

from itertools import groupby
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from ...i18n import t
from ...preset_plan import PresetPlan
from ..theme import tokens
from .style_utils import apply_margins


class PresetReviewModel(QtCore.QAbstractTableModel):
    def __init__(self, plan: PresetPlan, parent=None):
        super().__init__(parent)
        self.rows = []
        self.headings = []
        for (_preset, action), changes in groupby(plan.changes, lambda entry: (entry.preset, entry.action)):
            self.headings.append(len(self.rows))
            self.rows.append((t(action + "_action"), "", ""))
            self.rows.append((t("status"), t("name"), t("extension")))
            for change in changes:
                mod = change.mod
                status = t("missing_action") if mod is None else t("installed" if mod.installed else "not_installed")
                extensions = ", ".join(dict.fromkeys(file.src.suffix for file in mod.install_files if not file.is_dir)) if mod else Path(change.name).suffix
                folder = mod is not None and mod.is_dir
                name = change.name if folder else Path(change.name).stem
                self.rows.append((status, name, t("folder") if folder else extensions))

    def rowCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else 3

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        if role in (QtCore.Qt.DisplayRole, QtCore.Qt.ToolTipRole, QtCore.Qt.AccessibleTextRole):
            return self.rows[index.row()][index.column()]
        if role == QtCore.Qt.FontRole and (index.row() in self.headings or index.row() - 1 in self.headings):
            font = QtGui.QFont()
            font.setBold(True)
            return font
        return None


class PresetReview(QtWidgets.QDialog):
    def __init__(self, parent, plan: PresetPlan):
        super().__init__(parent)
        self.setWindowTitle(t("preset_preview"))
        self.resize(*tokens.DIALOG_SIZE)
        layout = apply_margins(QtWidgets.QVBoxLayout(self), tokens.DETAIL_MARGIN, tokens.SPACE_LG)
        self.table = QtWidgets.QTableView(self)
        self.review_model = PresetReviewModel(plan, self.table)
        self.table.setModel(self.review_model)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().hide()
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        for row in self.review_model.headings:
            self.table.setSpan(row, 0, 1, 3)
        layout.addWidget(self.table, 1)
        buttons = QtWidgets.QDialogButtonBox(self)
        apply_button = buttons.addButton(t("apply_plan"), QtWidgets.QDialogButtonBox.AcceptRole)
        apply_button.setDefault(True)
        buttons.addButton(t("cancel_action"), QtWidgets.QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
