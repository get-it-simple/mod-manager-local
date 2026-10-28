from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ...i18n import t
from .. import icons
from ..theme import tokens
from .style_utils import set_variant


class FilterChipDelegate(QtWidgets.QStyledItemDelegate):
    def close_rect(self, rect):
        return QtCore.QRect(rect.right() - tokens.ICON_BUTTON_SIZE, rect.top(), tokens.ICON_BUTTON_SIZE, rect.height())

    def sizeHint(self, option, index):
        view = self.parent()
        width = option.fontMetrics.horizontalAdvance(index.data()) + tokens.ICON_BUTTON_SIZE * 2 + tokens.SPACE_LG * 2
        height = max(tokens.ICON_BUTTON_SIZE, option.fontMetrics.height() + tokens.SPACE_LG * 2)
        return QtCore.QSize(min(width, max(tokens.ICON_BUTTON_SIZE * 2, view.viewport().width())), height)

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = option.rect.adjusted(tokens.SPACE_XS, tokens.SPACE_XS, -tokens.SPACE_XS, -tokens.SPACE_XS)
        painter.setBrush(option.palette.alternateBase())
        painter.setPen(option.palette.highlight().color() if option.state & QtWidgets.QStyle.State_HasFocus else option.palette.mid().color())
        painter.drawRoundedRect(rect, tokens.RADIUS_MD, tokens.RADIUS_MD)
        icon_rect = QtCore.QRect(rect.left() + tokens.SPACE_SM, rect.center().y() - tokens.ICON_SIZE // 2, tokens.ICON_SIZE, tokens.ICON_SIZE)
        icons.standard_icon("label_add" if index.data(QtCore.Qt.UserRole) == "label" else "search").paint(painter, icon_rect)
        close = self.close_rect(rect)
        close_icon = QtCore.QRect(close.center() - QtCore.QPoint(tokens.ICON_SIZE // 2, tokens.ICON_SIZE // 2), QtCore.QSize(tokens.ICON_SIZE, tokens.ICON_SIZE))
        icons.standard_icon("remove").paint(painter, close_icon)
        text_rect = rect.adjusted(tokens.ICON_BUTTON_SIZE, 0, -tokens.ICON_BUTTON_SIZE, 0)
        group = QtGui.QPalette.Active if option.state & QtWidgets.QStyle.State_Enabled else QtGui.QPalette.Disabled
        painter.setPen(option.palette.color(group, QtGui.QPalette.Text))
        painter.drawText(text_rect, QtCore.Qt.AlignVCenter, option.fontMetrics.elidedText(index.data(), QtCore.Qt.ElideRight, text_rect.width()))
        painter.restore()


class FilterChipView(QtWidgets.QListView):
    removeRequested = QtCore.Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        set_variant(self, "transparentList")
        self.viewport().setAutoFillBackground(False)
        self.setFlow(QtWidgets.QListView.LeftToRight)
        self.setWrapping(False)
        self.setResizeMode(QtWidgets.QListView.Adjust)
        self.setMovement(QtWidgets.QListView.Static)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setMinimumWidth(0)
        self.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        self.setItemDelegate(FilterChipDelegate(self))
        self.setAccessibleName(t("active_filters"))
        self._update_height()

    def _update_height(self) -> None:
        height = max(tokens.ICON_BUTTON_SIZE, self.fontMetrics().height() + tokens.SPACE_LG * 2)
        self.setFixedHeight(height + tokens.SCROLLBAR_WIDTH + self.frameWidth() * 2)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QtCore.QEvent.FontChange, QtCore.QEvent.StyleChange):
            self._update_height()

    def wheelEvent(self, event):
        bar = self.horizontalScrollBar()
        if bar.maximum() > 0:
            pixels = event.pixelDelta()
            angle = event.angleDelta()
            delta = pixels.x() or pixels.y() or (angle.x() or angle.y()) * tokens.FILTER_SCROLL_STEP / tokens.WHEEL_ANGLE_STEP
            bar.setValue(bar.value() - round(delta))
            event.accept()
            return
        super().wheelEvent(event)

    def remove_index(self, index) -> None:
        if index.isValid():
            self.removeRequested.emit(index.data(QtCore.Qt.UserRole), index.data())

    def mouseReleaseEvent(self, event):
        index = self.indexAt(event.position().toPoint())
        if event.button() == QtCore.Qt.LeftButton and index.isValid():
            if self.itemDelegate().close_rect(self.visualRect(index)).contains(event.position().toPoint()):
                self.remove_index(index)
                event.accept()
                return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Delete, QtCore.Qt.Key_Backspace):
            self.remove_index(self.currentIndex())
            event.accept()
            return
        super().keyPressEvent(event)
