from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ..theme import tokens


class FlowLayout(QtWidgets.QLayout):
    def __init__(self, parent=None, constrain_items: bool = False):
        super().__init__(parent)
        self.constrain_items = constrain_items
        self._items: list[QtWidgets.QLayoutItem] = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(tokens.SPACE_LG)

    def addItem(self, item) -> None:
        self._items.append(item)

    def insertWidget(self, index: int, widget) -> None:
        self.addChildWidget(widget)
        self._items.insert(index, QtWidgets.QWidgetItem(widget))

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < self.count() else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < self.count() else None

    def expandingDirections(self):
        return QtCore.Qt.Horizontal

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._arrange(QtCore.QRect(0, 0, width, 0), False)

    def minimumHeightForWidth(self, width: int) -> int:
        return self.heightForWidth(width)

    def setGeometry(self, rect) -> None:
        super().setGeometry(rect)
        self._arrange(rect, True)

    def sizeHint(self):
        widths = [item.sizeHint().width() for item in self._items]
        return QtCore.QSize(sum(widths) + max(0, len(widths) - 1) * self.spacing(), self.minimumSize().height())

    def minimumSize(self):
        size = QtCore.QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return QtCore.QSize(0, size.height()) if self.constrain_items else size

    def _arrange(self, rect: QtCore.QRect, apply: bool) -> int:
        rows: list[list[QtWidgets.QLayoutItem]] = [[]]
        used = 0
        for item in self._items:
            width = min(item.sizeHint().width(), rect.width()) if self.constrain_items else item.sizeHint().width()
            spacing = self.spacing() if rows[-1] else 0
            if rows[-1] and used + spacing + width > rect.width():
                rows.append([])
                used = 0
                spacing = 0
            rows[-1].append(item)
            used += spacing + width
        y = rect.y()
        for row in rows:
            if not row:
                continue
            widths = [min(item.sizeHint().width(), rect.width()) if self.constrain_items else item.sizeHint().width() for item in row]
            height = max(
                max(item.minimumSize().height(), item.heightForWidth(width))
                if self.constrain_items and item.hasHeightForWidth() else item.sizeHint().height()
                for item, width in zip(row, widths)
            )
            remaining = max(0, rect.width() - sum(widths) - self.spacing() * (len(row) - 1))
            expanding = [i for i, item in enumerate(row) if item.widget().property("toolbarStretch")]
            x = rect.x()
            for index, item in enumerate(row):
                width = widths[index]
                if index in expanding:
                    width += remaining // len(expanding)
                elif not expanding and index == len(row) - 1 and item.widget().property("alignTrailing"):
                    x += remaining
                if apply:
                    item.setGeometry(QtCore.QRect(x, y, width, height))
                x += width + self.spacing()
            y += height + self.spacing()
        return max(0, y - rect.y() - self.spacing())
