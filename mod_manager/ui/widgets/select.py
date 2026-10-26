from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ..theme import tokens


def fit_popup(view: QtWidgets.QAbstractItemView, anchor: QtWidgets.QWidget) -> None:
    screen = anchor.screen()
    if screen is None or not view.isVisible():
        return
    available = screen.availableGeometry().adjusted(tokens.FILTER_POPUP_MARGIN, tokens.FILTER_POPUP_MARGIN,
                                                   -tokens.FILTER_POPUP_MARGIN, -tokens.FILTER_POPUP_MARGIN)
    popup = view.window()
    width = min(available.width(), max(anchor.width(), view.sizeHintForColumn(0) + tokens.SCROLLBAR_WIDTH + tokens.SPACE_LG))
    height = min(popup.height(), available.height())
    origin = anchor.mapToGlobal(QtCore.QPoint())
    x = max(available.left(), min(origin.x(), available.right() - width + 1))
    y = max(available.top(), min(popup.y(), available.bottom() - height + 1))
    popup.setGeometry(x, y, width, height)


class SelectBox(QtWidgets.QComboBox):
    def showPopup(self) -> None:
        super().showPopup()
        fit_popup(self.view(), self)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(
            QtGui.QPen(
                self.palette().color(QtGui.QPalette.ButtonText),
                tokens.COMBO_CHEVRON_PEN,
                QtCore.Qt.SolidLine,
                QtCore.Qt.RoundCap,
                QtCore.Qt.RoundJoin,
            )
        )
        center = QtCore.QPoint(
            self.width() - tokens.COMBO_CHEVRON_RIGHT_INSET,
            self.height() // 2,
        )
        path = QtGui.QPainterPath()
        path.moveTo(center.x() - tokens.COMBO_CHEVRON_HALF_WIDTH, center.y() - tokens.COMBO_CHEVRON_HALF_HEIGHT)
        path.lineTo(center.x(), center.y() + tokens.COMBO_CHEVRON_HALF_HEIGHT)
        path.lineTo(center.x() + tokens.COMBO_CHEVRON_HALF_WIDTH, center.y() - tokens.COMBO_CHEVRON_HALF_HEIGHT)
        painter.drawPath(path)


def select_box(parent=None, editable: bool = False) -> SelectBox:
    box = SelectBox(parent)
    box.setEditable(editable)
    return box
