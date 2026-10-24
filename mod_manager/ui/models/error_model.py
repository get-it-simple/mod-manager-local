from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from PySide6 import QtCore

from ...models import OperationFailure, OperationResult
from ..theme import tokens


@dataclass(frozen=True)
class ErrorEntry:
    time: str
    profile: str
    action: str
    mod: str
    message: str
    failure: OperationFailure | None = None

    def details(self) -> str:
        lines = [f"Time: {self.time}", f"Profile: {self.profile}",
                 f"Action: {self.action}", f"Mod: {self.mod}"]
        if self.failure:
            lines.extend((f"Source: {self.failure.src}", f"Destination: {self.failure.dest}"))
        return "\n".join(lines) + f"\n\n{self.message}"


class ErrorHistoryModel(QtCore.QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.entries: list[ErrorEntry] = []

    def rowCount(self, parent=QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.entries)

    def columnCount(self, parent=QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else len(tokens.ERROR_COLUMNS)

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
            return tokens.ERROR_COLUMNS[section][1]
        return None

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        entry = self.entries[index.row()]
        if role == QtCore.Qt.UserRole:
            return entry
        if role == QtCore.Qt.ToolTipRole:
            return entry.details()
        if role == QtCore.Qt.DisplayRole:
            filename = entry.failure.dest.name if entry.failure else "-"
            return (entry.time, entry.profile, entry.action, entry.mod, filename)[index.column()]
        return None

    def append_result(self, result: OperationResult, profile: str) -> None:
        time = datetime.now().isoformat(sep=" ", timespec="seconds")
        entries = [
            ErrorEntry(time, profile, item.action, item.name,
                       failure.message if failure else item.message, failure)
            for item in result.items if not item.success
            for failure in (item.failures or (None,))
        ]
        if entries:
            start = len(self.entries)
            self.beginInsertRows(QtCore.QModelIndex(), start, start + len(entries) - 1)
            self.entries.extend(entries)
            self.endInsertRows()
