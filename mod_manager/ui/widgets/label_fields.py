from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ...settings_schema import LABEL_NAME_FIELD, LABEL_MODE_FIELD
from ..theme import tokens
from .style_utils import apply_margins


def text_control_width(widget: QtWidgets.QWidget, text: str) -> int:
    contents = QtCore.QSize(widget.fontMetrics().horizontalAdvance(text), widget.fontMetrics().height())
    if isinstance(widget, QtWidgets.QComboBox):
        option = QtWidgets.QStyleOptionComboBox()
        widget.initStyleOption(option)
        control = QtWidgets.QStyle.CT_ComboBox
    else:
        option = QtWidgets.QStyleOptionFrame()
        widget.initStyleOption(option)
        control = QtWidgets.QStyle.CT_LineEdit
    return widget.style().sizeFromContents(control, option, contents, widget).width() + tokens.SPACE_LG


class LabelFields(QtWidgets.QWidget):
    def __init__(self, name_edit, mode_box, parent=None):
        super().__init__(parent)
        self.fields = ((LABEL_NAME_FIELD, name_edit), (LABEL_MODE_FIELD, mode_box))
        self.cells = []
        self.grid = apply_margins(QtWidgets.QGridLayout(self), margins=None, spacing=tokens.SPACE_LG)
        self.grid.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)
        self._columns = 0
        for spec, widget in self.fields:
            cell = QtWidgets.QWidget(self)
            row = apply_margins(QtWidgets.QHBoxLayout(cell), margins=None, spacing=tokens.SPACE_SM)
            label = QtWidgets.QLabel(spec.label)
            label.setToolTip(spec.tooltip)
            label.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
            widget.setToolTip(spec.tooltip)
            widget.setAccessibleName(spec.label)
            row.addWidget(label)
            row.addWidget(widget, 1)
            self.cells.append(cell)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        self._update_metrics()

    def _update_metrics(self) -> None:
        for _spec, widget in self.fields:
            widget.setMinimumWidth(text_control_width(widget, "0" * tokens.LABEL_FIELD_MIN_CHARS))
        self._reflow()
        self.updateGeometry()

    def _reflow(self) -> None:
        required = sum(cell.minimumSizeHint().width() for cell in self.cells) + self.grid.spacing()
        columns = 2 if self.width() >= required else 1
        if columns != self._columns:
            self._columns = columns
            for index, cell in enumerate(self.cells):
                self.grid.removeWidget(cell)
                self.grid.addWidget(cell, index // columns, index % columns)
            self.grid.setColumnStretch(0, 1)
            self.grid.setColumnStretch(1, 1 if columns == 2 else 0)
        self.grid.invalidate()
        self.setFixedHeight(self.grid.sizeHint().height())

    def minimumSizeHint(self):
        return QtCore.QSize(max(cell.minimumSizeHint().width() for cell in self.cells), self.minimumHeight())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() in (QtCore.QEvent.FontChange, QtCore.QEvent.StyleChange) and hasattr(self, "fields"):
            self._update_metrics()
