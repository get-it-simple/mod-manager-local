from __future__ import annotations

from PySide6 import QtCore, QtGui

from ...models import ModItem
from ...labels import label_names
from .. import icons
from ..theme import colors, tokens
from . import columns

COLUMNS = tokens.MOD_COLUMNS
HEADERS = columns.titles(COLUMNS)


class ModTableModel(QtCore.QAbstractTableModel):
    HEADERS = HEADERS
    COLUMNS = COLUMNS

    def __init__(self, accent_color: QtGui.QColor | str | None = None, parent=None):
        super().__init__(parent)
        self.mods: list[ModItem] = []
        self.labels: dict[str, str] = {}
        self.label_memberships: dict[str, tuple[str, ...]] = {}
        self.records: dict[str, dict] = {}
        self.favorites: set[str] = set()
        self.set_accent(accent_color or colors.FALLBACK_ACCENT)

    def set_accent(self, accent_color) -> None:
        self._installed_icon = icons.check_icon(accent_color)
        self._empty_icon = icons.check_icon(accent_color, transparent=True)

    def refresh_accent(self, accent_color) -> None:
        self.set_accent(accent_color)
        self.layoutChanged.emit()

    def set_data(self, mods: list[ModItem], labels: dict, records: dict, favorites: set[str] | None = None) -> None:
        self.beginResetModel()
        self.mods = list(mods)
        self.labels = dict(labels or {})
        self.label_memberships = {mod.name: label_names(labels or {}, mod.name) for mod in mods}
        self.records = dict(records or {})
        self.favorites = set(favorites or ())
        self.endResetModel()

    def rowCount(self, parent=QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.mods)

    def columnCount(self, parent=QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.COLUMNS)

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
            return self.HEADERS[section]
        return None

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        mod = self.mods[index.row()]
        column = index.column()
        if role == QtCore.Qt.ToolTipRole and column in (1, 2):
            return mod.name if column == 1 else self.labels.get(mod.name, "-")
        if role == QtCore.Qt.UserRole:
            return mod
        if role == QtCore.Qt.DecorationRole and column == 0:
            return self._installed_icon if mod.installed else self._empty_icon
        if role == QtCore.Qt.TextAlignmentRole:
            return columns.alignment(self.COLUMNS, column)
        if role != QtCore.Qt.DisplayRole:
            return None
        record = self.records.get(mod.name, {})
        values = ("", mod.name, self.labels.get(mod.name, "-"), record.get("last_managed") or "-")
        return values[column]
