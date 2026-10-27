from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ...i18n import t
from .. import icons
from ..theme import tokens


class SidebarLabelDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, view):
        super().__init__(view)
        self.accent = view.palette().highlight().color()
        self.compact = False

    def sizeHint(self, option, index):
        return QtCore.QSize(0, max(tokens.NAVIGATION_HEIGHT, option.fontMetrics.height() + tokens.SPACE_LG * 2))

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        name, mode, count, active = index.data(QtCore.Qt.UserRole)
        rect = option.rect.adjusted(tokens.SPACE_XS, tokens.SPACE_XS, -tokens.SPACE_XS, -tokens.SPACE_XS)
        painter.setBrush(option.palette.alternateBase() if active else QtCore.Qt.NoBrush)
        painter.setPen(self.accent if active else QtCore.Qt.transparent)
        painter.drawRoundedRect(rect, tokens.RADIUS_MD, tokens.RADIUS_MD)
        if option.state & QtWidgets.QStyle.State_HasFocus:
            painter.setPen(option.palette.mid().color())
            painter.drawRect(rect.adjusted(tokens.SPACE_XS, tokens.SPACE_XS, -tokens.SPACE_XS, -tokens.SPACE_XS))
        pad = tokens.SPACE_XS if self.compact else tokens.SPACE_SM
        content = rect.adjusted(pad, 0, -pad, 0)
        icon_rect = QtCore.QRect(content.left(), content.center().y() - tokens.ICON_SIZE // 2, tokens.ICON_SIZE, tokens.ICON_SIZE)
        icons.standard_icon("settings" if mode == "automatic" else "label_add").paint(painter, icon_rect)
        content.adjust(tokens.ICON_SIZE + tokens.SPACE_XS, 0, 0, 0)
        painter.setPen(option.palette.text().color())
        count_width = option.fontMetrics.horizontalAdvance(str(count))
        painter.drawText(content, QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, str(count))
        if not self.compact:
            content.adjust(0, 0, -count_width - tokens.SPACE_SM, 0)
            painter.drawText(content, QtCore.Qt.AlignVCenter, option.fontMetrics.elidedText(name, QtCore.Qt.ElideRight, content.width()))
        painter.restore()


class SidebarLabels(QtWidgets.QListView):
    labelRequested = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.label_model = QtGui.QStandardItemModel(self)
        self.setModel(self.label_model)
        self.delegate = SidebarLabelDelegate(self)
        self.setItemDelegate(self.delegate)
        self.setMinimumSize(0, 0)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.setUniformItemSizes(True)
        self.setAccessibleName(t("labels"))
        self.clicked.connect(lambda index: self.labelRequested.emit(index.data()))
        self._entries = []

    def update_labels(self, entries, accent: str) -> None:
        self.delegate.accent = QtGui.QColor(accent)
        if entries != self._entries:
            scroll = self.verticalScrollBar().value()
            current = self.currentIndex().data()
            self._entries = list(entries)
            self.label_model.clear()
            for name, mode, count, active in entries:
                item = QtGui.QStandardItem(name)
                item.setData((name, mode, count, active), QtCore.Qt.UserRole)
                item.setToolTip(t("value0_value1_matching_mods_value2", value0=name, value1=mode.capitalize(), value2=str(count)))
                item.setAccessibleText(item.toolTip())
                self.label_model.appendRow(item)
                if name == current:
                    self.setCurrentIndex(item.index())
            self.verticalScrollBar().setValue(scroll)
        self.viewport().update()

    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter, QtCore.Qt.Key_Space) and self.currentIndex().isValid():
            self.labelRequested.emit(self.currentIndex().data())
            event.accept()
            return
        super().keyPressEvent(event)

    def set_compact(self, compact: bool) -> None:
        self.delegate.compact = compact
        self.viewport().update()
