from __future__ import annotations

from PySide6 import QtCore

from .. import icons
from ..theme import colors, tokens
from . import columns
from .mod_model import OPERATION_ROLE

COLUMNS = tokens.PRESET_COLUMNS
HEADERS = columns.titles(COLUMNS)

ACTIVE = "active"
INACTIVE = "inactive"


class PresetTableModel(QtCore.QAbstractTableModel):
    HEADERS = HEADERS
    COLUMNS = COLUMNS
    operation_column = 0

    def __init__(self, palette: colors.Palette | None = None, parent=None):
        super().__init__(parent)
        self.presets: dict[str, list[str]] = {}
        self.keys: list[str] = []
        self.records: dict[str, dict] = {}
        self.installed: set[str] = set()
        self.operation_frames = {}
        self.set_palette(palette or colors.build_palette("light"))

    def set_palette(self, palette: colors.Palette) -> None:
        self.activity_color = palette.accent
        self._active_icon = icons.state_icon(True, palette)
        self._inactive_icon = icons.state_icon(False, palette)

    def set_data(self, presets: dict, keys: list[str], records: dict, installed: set[str] | None = None) -> None:
        self.beginResetModel()
        self.presets = dict(presets or {})
        self.keys = list(keys or [])
        self.operation_frames = {name: frame for name, frame in self.operation_frames.items() if name in self.keys}
        self.records = dict(records or {})
        self.installed = set(installed or set())
        self.endResetModel()

    def is_active(self, name: str) -> bool:
        mods = self.presets.get(name, [])
        return bool(mods) and all(mod_name in self.installed for mod_name in mods)

    def rowCount(self, parent=QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.keys)

    def columnCount(self, parent=QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.COLUMNS)

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
            return self.HEADERS[section]
        return None

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        name = self.keys[index.row()]
        if role == OPERATION_ROLE:
            return self.operation_frames.get(name)
        column = index.column()
        active = self.is_active(name)
        if column == 1:
            if role == QtCore.Qt.UserRole:
                return ACTIVE if active else INACTIVE
            if role == QtCore.Qt.DecorationRole:
                return self._active_icon if active else self._inactive_icon
        if role == QtCore.Qt.TextAlignmentRole:
            return columns.alignment(self.COLUMNS, column)
        if role != QtCore.Qt.DisplayRole:
            return None
        record = self.records.get(name, {})
        values = (name, "", str(len(self.presets.get(name, []))), record.get("last_managed") or "-")
        return values[column]
