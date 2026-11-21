from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ...i18n import t
from ..label_artwork import label_icon
from ..theme import tokens
from .style_utils import set_variant
from .buttons import icon_button
from .item_feedback import ButtonItemFeedback, paint_item_button


class SidebarLabelDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.accent = view.palette().highlight().color()
        self.compact = False

    def sizeHint(self, option, index):
        return QtCore.QSize(0, max(tokens.NAVIGATION_HEIGHT, option.fontMetrics.height() + tokens.SPACE_LG * 2))

    def add_rect(self, rect):
        size = tokens.ICON_BUTTON_SIZE
        return QtCore.QRect(rect.right() - size - tokens.SPACE_SM, rect.center().y() - size // 2, size, size)

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        name, mode, count, active = index.data(QtCore.Qt.UserRole)
        rect = option.rect.adjusted(tokens.SPACE_XS, tokens.SPACE_XS, -tokens.SPACE_XS, -tokens.SPACE_XS)
        painter.setBrush(option.palette.alternateBase() if active else QtCore.Qt.NoBrush)
        painter.setPen(self.accent if active else QtCore.Qt.transparent)
        painter.drawRoundedRect(rect, tokens.RADIUS_MD, tokens.RADIUS_MD)
        paint_item_button(painter, option, index, active)
        if option.state & QtWidgets.QStyle.State_HasFocus:
            painter.setPen(option.palette.mid().color())
            painter.drawRect(rect.adjusted(tokens.SPACE_XS, tokens.SPACE_XS, -tokens.SPACE_XS, -tokens.SPACE_XS))
        pad = tokens.SPACE_XS if self.compact else tokens.SPACE_SM
        content = rect.adjusted(pad, 0, -pad, 0)
        icon_rect = QtCore.QRect(content.left(), content.center().y() - tokens.ICON_SIZE // 2, tokens.ICON_SIZE, tokens.ICON_SIZE)
        if self.compact:
            icon_rect.moveCenter(content.center())
        label_icon(self.view.definitions.get(name), "settings" if mode == "automatic" else "label_add").paint(painter, icon_rect)
        content.adjust(tokens.ICON_SIZE + tokens.SPACE_XS, 0, 0, 0)
        painter.setPen(option.palette.text().color())
        if not self.compact:
            count_width = option.fontMetrics.horizontalAdvance(str(count))
            painter.drawText(content, QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, str(count))
            content.adjust(0, 0, -count_width - tokens.SPACE_SM, 0)
            painter.drawText(content, QtCore.Qt.AlignVCenter, option.fontMetrics.elidedText(name, QtCore.Qt.ElideRight, content.width()))
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
        self.definitions = {}
        self.feedback = ButtonItemFeedback(self, lambda index: bool(index.data(QtCore.Qt.UserRole) and index.data(QtCore.Qt.UserRole)[3]))
        self.add_button = icon_button("add", t("label_quick_add"), self._add_hovered, parent=self.viewport())
        self.add_button.hide()
        self.verticalScrollBar().valueChanged.connect(self._position_add)
        self._scroll_restore = QtCore.QTimer(self)
        self._scroll_restore.setSingleShot(True)
        self._scroll_restore.timeout.connect(self._restore_scroll)
        self._saved_scroll = None

    def _add_hovered(self):
        if self._hovered.isValid() and self.isEnabled():
            self.labelToggleRequested.emit(self._hovered.data())

    def _position_add(self, *_args):
        if self.delegate.compact or not self._hovered.isValid() or not self.isEnabled():
            self.add_button.hide()
            return
        rect = self.delegate.add_rect(self.visualRect(QtCore.QModelIndex(self._hovered)))
        self.add_button.setGeometry(rect)
        self.add_button.setVisible(self.viewport().rect().contains(rect))
        self.add_button.raise_()

    def _restore_scroll(self):
        if self._saved_scroll is not None:
            value, self._saved_scroll = self._saved_scroll, None
            self.verticalScrollBar().setValue(value)
        self._position_add()

    def _activate(self, index, modifiers=QtCore.Qt.NoModifier) -> None:
        signal = self.labelToggleRequested if modifiers & QtCore.Qt.ShiftModifier else self.labelRequested
        signal.emit(index.data())

    def mouseReleaseEvent(self, event) -> None:
        index = self.indexAt(event.position().toPoint())
        if (not self.delegate.compact and event.button() == QtCore.Qt.LeftButton and index.isValid()
                and self.delegate.add_rect(self.visualRect(index)).contains(event.position().toPoint())):
            self.labelToggleRequested.emit(index.data())
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event) -> None:
        self._hovered = QtCore.QPersistentModelIndex(self.indexAt(event.position().toPoint()))
        self._position_add()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        if self.add_button.underMouse():
            return
        self._hovered = QtCore.QPersistentModelIndex()
        self.add_button.hide()
        super().leaveEvent(event)

    def viewportEvent(self, event):
        if event.type() == QtCore.QEvent.ToolTip:
            index = self.indexAt(event.pos())
            if not self.delegate.compact and index.isValid() and self.delegate.add_rect(self.visualRect(index)).contains(event.pos()):
                QtWidgets.QToolTip.showText(event.globalPos(), t("label_quick_add"), self)
                return True
        return super().viewportEvent(event)

    def update_labels(self, entries, accent: str) -> None:
        entries = list(entries)
        accent = QtGui.QColor(accent)
        theme_changed = accent != self.delegate.accent
        self.delegate.accent = accent
        if entries == self._entries:
            if theme_changed:
                self.viewport().update()
            return
        if self._saved_scroll is None:
            self._saved_scroll = self.verticalScrollBar().value()
        self._entries = entries
        model = self.label_model
        current = self.currentIndex().data()
        wanted = {entry[0] for entry in entries}
        for row in reversed(range(model.rowCount())):
            if model.item(row).text() not in wanted:
                model.removeRow(row)
        for row, entry in enumerate(entries):
            name, mode, count, active = entry
            existing = next((index for index in range(row, model.rowCount()) if model.item(index).text() == name), None)
            if existing is None:
                item = QtGui.QStandardItem(name)
                item.setEditable(False)
                model.insertRow(row, item)
            elif existing != row:
                model.insertRow(row, model.takeRow(existing))
            item = model.item(row)
            if item.data(QtCore.Qt.UserRole) != entry:
                item.setData(entry, QtCore.Qt.UserRole)
                tooltip = t("value0_value1_matching_mods_value2", value0=name, value1=mode.capitalize(), value2=str(count))
                item.setToolTip(tooltip)
                item.setAccessibleText(tooltip)
            if name == current and self.currentIndex() != item.index():
                self.setCurrentIndex(item.index())
        self.verticalScrollBar().setValue(self._saved_scroll)
        self._scroll_restore.start(tokens.IMMEDIATE_MS)

    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter, QtCore.Qt.Key_Space) and self.currentIndex().isValid():
            self._activate(self.currentIndex(), event.modifiers())
            event.accept()
            return
        super().keyPressEvent(event)

    def set_compact(self, compact: bool) -> None:
        self.delegate.compact = compact
        self._position_add()
        self.viewport().update()
