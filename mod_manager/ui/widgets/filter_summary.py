from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ...i18n import t
from ..theme import tokens
from .buttons import icon_button
from .filter_chips import FilterChipView
from .style_utils import apply_margins


class FilterSummary(QtWidgets.QWidget):
    removeRequested = QtCore.Signal(str, str)
    clearRequested = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.count_label = QtWidgets.QLabel()
        self.view = FilterChipView()
        self.model = QtGui.QStandardItemModel(self)
        self.view.setModel(self.model)
        self.view.removeRequested.connect(self.removeRequested)
        self.clear_button = icon_button("filter_clear", t("clear_filters"), self.clearRequested.emit)
        self.clear_button.setEnabled(False)
        self._chips = []
        layout = apply_margins(QtWidgets.QHBoxLayout(self), margins=None, spacing=tokens.SPACE_SM)
        layout.addWidget(self.count_label)
        layout.addWidget(self.view, 1)
        layout.addWidget(self.clear_button)

    def update_filters(self, count: int, total: int, chips, active: bool, busy: bool = False) -> None:
        self.count_label.setText(t("showing_mods", count=count, total=total))
        self.clear_button.setEnabled(active and not busy)
        self.view.setEnabled(not busy)
        if self._chips == chips:
            return
        added = any(chip not in self._chips for chip in chips)
        scroll = self.view.horizontalScrollBar().value()
        current_row = self.view.currentIndex().row()
        self._chips = list(chips)
        self.model.clear()
        for kind, value in chips:
            item = QtGui.QStandardItem(value)
            item.setEditable(False)
            item.setData(kind, QtCore.Qt.UserRole)
            item.setToolTip(t("label_chip" if kind == "label" else "search_chip", value=value) + "\n" + t("remove_filter"))
            item.setAccessibleText(t("label_chip" if kind == "label" else "search_chip", value=value))
            self.model.appendRow(item)
        self.view.doItemsLayout()
        self.view.setCurrentIndex(self.model.index(max(0, min(current_row, self.model.rowCount() - 1)), 0))
        if added:
            QtCore.QTimer.singleShot(tokens.IMMEDIATE_MS, self._reveal_last)
        else:
            self.view.horizontalScrollBar().setValue(scroll)

    def _reveal_last(self) -> None:
        self.view.doItemsLayout()
        self.view.scrollTo(self.model.index(self.model.rowCount() - 1, 0))
        self.view.horizontalScrollBar().setValue(self.view.horizontalScrollBar().maximum())
