from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ...i18n import t
from .. import icons
from ..theme import tokens
from .style_utils import set_variant


class SidebarLabelDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.accent = view.palette().highlight().color()
        self.compact = False

    def sizeHint(self, option, index):
        return QtCore.QSize(0, max(tokens.NAVIGATION_HEIGHT, option.fontMetrics.height() + tokens.SPACE_LG * 2))

    def add_rect(self, rect):
        size = tokens.ICON_SIZE + tokens.SPACE_XS
        return QtCore.QRect(rect.right() - size - tokens.SPACE_SM, rect.center().y() - size // 2, size, size)

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
        if ((option.state & QtWidgets.QStyle.State_MouseOver or index == self.view._hovered)
                and option.state & QtWidgets.QStyle.State_Enabled):
            overlay = self.add_rect(option.rect)
            painter.fillRect(overlay, option.palette.alternateBase())
            icons.standard_icon("add").paint(painter, overlay)
        painter.restore()


class SidebarLabels(QtWidgets.QListView):
    labelRequested = QtCore.Signal(str)
    labelToggleRequested = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        set_variant(self, "transparentList")
        self.viewport().setAutoFillBackground(False)
        self.label_model = QtGui.QStandardItemModel(self)
        self._hovered = QtCore.QPersistentModelIndex()
        self.setModel(self.label_model)
        self.delegate = SidebarLabelDelegate(self)
        self.setItemDelegate(self.delegate)
        self.setMinimumSize(0, 0)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.setUniformItemSizes(True)
        self.setAccessibleName(t("labels"))
        self.setMouseTracking(True)
        self.clicked.connect(lambda index: self._activate(index, QtWidgets.QApplication.keyboardModifiers()))
        self._entries = []

    def _activate(self, index, modifiers=QtCore.Qt.NoModifier) -> None:
        signal = self.labelToggleRequested if modifiers & QtCore.Qt.ShiftModifier else self.labelRequested
        signal.emit(index.data())

    def mouseReleaseEvent(self, event) -> None:
        index = self.indexAt(event.position().toPoint())
        if (event.button() == QtCore.Qt.LeftButton and index.isValid()
                and self.delegate.add_rect(self.visualRect(index)).contains(event.position().toPoint())):
            self.labelToggleRequested.emit(index.data())
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event) -> None:
        self._hovered = QtCore.QPersistentModelIndex(self.indexAt(event.position().toPoint()))
        self.viewport().update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = QtCore.QPersistentModelIndex()
        self.viewport().update()
        super().leaveEvent(event)

    def viewportEvent(self, event):
        if event.type() == QtCore.QEvent.ToolTip:
            index = self.indexAt(event.pos())
            if index.isValid() and self.delegate.add_rect(self.visualRect(index)).contains(event.pos()):
                QtWidgets.QToolTip.showText(event.globalPos(), t("label_quick_add"), self)
                return True
        return super().viewportEvent(event)

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
            self._activate(self.currentIndex(), event.modifiers())
            event.accept()
            return
        super().keyPressEvent(event)

    def set_compact(self, compact: bool) -> None:
        self.delegate.compact = compact
        self.viewport().update()
