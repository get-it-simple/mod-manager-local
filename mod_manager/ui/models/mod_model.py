from __future__ import annotations

from PySide6 import QtCore, QtGui

from ...models import ModItem
from ...labels import label_names
from .. import icons
from ..theme import colors, tokens
from ..widgets.operation_feedback import OperationVisual
from . import columns

COLUMNS = tokens.MOD_COLUMNS
HEADERS = columns.titles(COLUMNS)
DISPLAY_ROLE = QtCore.Qt.DisplayRole
TOOLTIP_ROLE = QtCore.Qt.ToolTipRole
ITEM_ROLE = QtCore.Qt.UserRole
DECORATION_ROLE = QtCore.Qt.DecorationRole
ALIGNMENT_ROLE = QtCore.Qt.TextAlignmentRole
BUSY_ROLE = QtCore.Qt.UserRole + 1
OPERATION_ROLE = QtCore.Qt.UserRole + 2
DATA_ROLES = frozenset((DISPLAY_ROLE, TOOLTIP_ROLE, ITEM_ROLE, DECORATION_ROLE, ALIGNMENT_ROLE, BUSY_ROLE, OPERATION_ROLE))


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
        self.active_mods: set[str] = set()
        self.operation_frames: dict[str, OperationVisual] = {}
        self.activity_phase = 0.0
        self.set_accent(accent_color or colors.FALLBACK_ACCENT)

    def set_accent(self, accent_color) -> None:
        self.activity_color = QtGui.QColor(accent_color)
        self._installed_icon = icons.check_icon(accent_color)
        self._empty_icon = icons.check_icon(accent_color, transparent=True)

    def refresh_accent(self, accent_color) -> None:
        self.set_accent(accent_color)
        self.layoutChanged.emit()

    def set_data(self, mods: list[ModItem], labels: dict, records: dict, favorites: set[str] | None = None) -> None:
        self.beginResetModel()
        self.mods = list(mods)
        visible_names = {mod.name for mod in mods}
        self.operation_frames = {name: frame for name, frame in self.operation_frames.items() if name in visible_names}
        self.labels = dict(labels or {})
        self.label_memberships = {mod.name: label_names(labels or {}, mod.name) for mod in mods}
        self.records = dict(records or {})
        self.favorites = set(favorites or ())
        self.endResetModel()

    def rowCount(self, parent=QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.mods)

    def set_active_mods(self, names: set[str]) -> None:
        changed = self.active_mods.symmetric_difference(names)
        self.active_mods = set(names)
        for row, mod in enumerate(self.mods):
            if mod.name in changed:
                index = self.index(row, 0)
                self.dataChanged.emit(index, index, [BUSY_ROLE, DECORATION_ROLE])

    def columnCount(self, parent=QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.COLUMNS)

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
            return self.HEADERS[section]
        return None

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if role not in DATA_ROLES or not index.isValid():
            return None
        mod = self.mods[index.row()]
        column = index.column()
        if role == TOOLTIP_ROLE and column in (1, 2):
            return mod.name if column == 1 else self.labels.get(mod.name, "-")
        if role == ITEM_ROLE:
            return mod
        if role == BUSY_ROLE:
            return mod.name in self.active_mods
        if role == OPERATION_ROLE:
            return self.operation_frames.get(mod.name)
        if role == DECORATION_ROLE and column == 0:
            return self._installed_icon if mod.installed else self._empty_icon
        if role == ALIGNMENT_ROLE:
            return columns.alignment(self.COLUMNS, column)
        if role != DISPLAY_ROLE:
            return None
        record = self.records.get(mod.name, {})
        values = ("", mod.name, self.labels.get(mod.name, "-"), record.get("last_managed") or "-")
        return values[column]
