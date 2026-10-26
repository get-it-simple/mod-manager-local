from __future__ import annotations

from ...i18n import t

from PySide6 import QtCore, QtWidgets

from ...labels import AUTOMATIC, matching_fragment_ids
from .. import icons
from ..theme import tokens


LABEL_MODE_ROLE = QtCore.Qt.UserRole + 1
LABEL_COUNT_ROLE = QtCore.Qt.UserRole + 2


def update_label_item(item, name: str, mode: str, count: int) -> None:
    item.setText(f"{name} · {mode.capitalize()} · {count}")
    item.setToolTip(t('value0_value1_matching_mods_value2', value0=f'{name}', value1=f'{mode.capitalize()}', value2=f'{count}'))
    item.setData(name, QtCore.Qt.UserRole)
    item.setData(mode, LABEL_MODE_ROLE)
    item.setData(count, LABEL_COUNT_ROLE)


class LabelListDelegate(QtWidgets.QStyledItemDelegate):
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.icon = icons.standard_icon("settings" if index.data(LABEL_MODE_ROLE) == AUTOMATIC else "edit")
        option.features |= QtWidgets.QStyleOptionViewItem.HasDecoration
        option.decorationSize = QtCore.QSize(tokens.ICON_SIZE, tokens.ICON_SIZE)
        if self.parent().compact:
            option.text = str(index.data(LABEL_COUNT_ROLE))


class LabelListView(QtWidgets.QListView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setItemDelegate(LabelListDelegate(self))
        self.setUniformItemSizes(True)
        self.setTextElideMode(QtCore.Qt.ElideRight)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

    @property
    def compact(self) -> bool:
        return self.viewport().width() <= max(tokens.LABEL_LIST_MIN_WIDTH, self.minimumWidth())

    def setModel(self, model):
        super().setModel(model)
        model.dataChanged.connect(self._update_minimum)
        model.modelReset.connect(self._update_minimum)
        model.rowsInserted.connect(self._update_minimum)
        model.rowsRemoved.connect(self._update_minimum)
        self._update_minimum()

    def _update_minimum(self, *_args) -> None:
        model = self.model()
        counts = [str(model.index(row, 0).data(LABEL_COUNT_ROLE) or 0) for row in range(model.rowCount())] if model else []
        width = max((self.fontMetrics().horizontalAdvance(count) for count in counts), default=self.fontMetrics().horizontalAdvance("0"))
        self.setMinimumWidth(width + tokens.ICON_SIZE + tokens.SPACE_LG * 3 + self.frameWidth() * 2 + tokens.SCROLLBAR_WIDTH)
        self.viewport().update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.viewport().update()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QtCore.QEvent.FontChange, QtCore.QEvent.StyleChange):
            self._update_minimum()


class LabelMatchesModel(QtCore.QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.names: list[str] = []
        self.terms: list[str] = []

    def set_matches(self, names: list[str], terms: list[str]) -> None:
        self.beginResetModel()
        self.names = list(names)
        self.terms = list(terms)
        self.endResetModel()

    def rowCount(self, parent=QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.names)

    def columnCount(self, parent=QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else 2

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return (t('mod_name'), t('fragments'))[section]
        return super().headerData(section, orientation, role)

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        if role in (QtCore.Qt.DisplayRole, QtCore.Qt.ToolTipRole, QtCore.Qt.AccessibleTextRole):
            name = self.names[index.row()]
            return name if index.column() == 0 else ", ".join(map(str, matching_fragment_ids(name, self.terms)))
        return None


def matching_mods_view(model) -> QtWidgets.QTableView:
    view = QtWidgets.QTableView()
    view.setModel(model)
    view.verticalHeader().hide()
    view.verticalHeader().setDefaultSectionSize(tokens.TABLE_ROW_HEIGHT)
    view.setShowGrid(False)
    view.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
    view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
    view.setMinimumHeight(tokens.LABEL_EDITOR_LIST_HEIGHT)
    view.setMinimumWidth(0)
    view.setWordWrap(False)
    view.setTextElideMode(QtCore.Qt.ElideRight)
    header = view.horizontalHeader()
    header.setStretchLastSection(False)
    header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
    header.setSectionResizeMode(1, QtWidgets.QHeaderView.Fixed)
    view.setColumnWidth(1, tokens.LABEL_FRAGMENTS_COLUMN_WIDTH)
    return view
