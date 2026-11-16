from __future__ import annotations

from datetime import datetime

from PySide6 import QtCore, QtGui, QtWidgets

from ...i18n import t
from ..theme import tokens
from .style_utils import apply_margins
from .toolbar import IconToolbar


class TrashView(QtWidgets.QWidget):
    restoreRequested = QtCore.Signal()
    deleteRequested = QtCore.Signal()
    refreshRequested = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.entries = []
        self.model = QtGui.QStandardItemModel(self)
        self.table = QtWidgets.QTableView(self)
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.status = QtWidgets.QLabel(t("trash_empty"), self)
        self.status.setWordWrap(True)
        self.toolbar = IconToolbar(self)
        section = self.toolbar.add_section("trash", t("trash"))
        section.add_text_action("restore", t("trash_restore"), "reset", t("trash_restore_help"), self.restoreRequested.emit)
        section.add_text_action("delete", t("trash_delete"), "delete", t("trash_delete_help"), self.deleteRequested.emit)
        section.add_text_action("refresh", t("refresh"), "refresh", t("refresh"), self.refreshRequested.emit)
        self.toolbar.add_stretch()
        layout = apply_margins(QtWidgets.QVBoxLayout(self), spacing=tokens.SPACE_LG)
        layout.addWidget(self.status)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.toolbar)
        self.table.selectionModel().selectionChanged.connect(self.update_actions)
        self.pending = set()
        self.update_actions()

    def selected_entries(self):
        return [self.entries[index.row()] for index in self.table.selectionModel().selectedRows()
                if index.row() < len(self.entries)]

    def update_actions(self, *_args) -> None:
        selected = self.selected_entries()
        available = bool(selected) and not any(entry.identifier in self.pending for entry in selected)
        self.toolbar.set_enabled("restore", available and all(not entry.missing for entry in selected))
        self.toolbar.set_enabled("delete", available)

    def set_entries(self, entries) -> None:
        selected = {entry.identifier for entry in self.selected_entries()}
        self.entries = list(entries)
        self.model.clear()
        self.model.setHorizontalHeaderLabels([t("mod"), t("game"), t("trash_deleted_at"), t("trash_expires_at"), t("state")])
        for entry in entries:
            state = t("trash_incomplete") if entry.missing else t("trash_ready")
            deleted = datetime.fromisoformat(entry.data["deleted_at"]).astimezone().strftime("%Y-%m-%d %H:%M")
            expires = datetime.fromisoformat(entry.data["expires_at"]).astimezone().strftime("%Y-%m-%d %H:%M")
            values = (entry.name, entry.data["profile_name"], deleted, expires, state)
            items = [QtGui.QStandardItem(value) for value in values]
            for item in items:
                item.setToolTip(str(entry.root) + "\n" + state)
            self.model.appendRow(items)
            if entry.identifier in selected:
                index = self.model.index(self.model.rowCount() - 1, 0)
                self.table.selectionModel().select(index, QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Rows)
        self.status.setText(t("trash_help") if entries else t("trash_empty"))
        self.status.setVisible(not entries)
        self.update_actions()
