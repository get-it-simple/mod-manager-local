from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from .. import icons
from ..theme import tokens
from .buttons import text_button
from .style_utils import apply_margins, set_variant


class SegmentedControl(QtWidgets.QFrame):
    valueChanged = QtCore.Signal(str)

    def __init__(self, options, parent=None):
        super().__init__(parent)
        set_variant(self, "segmentedControl")
        layout = apply_margins(QtWidgets.QHBoxLayout(self), tokens.SPACE_XS, 0)
        self.group = QtWidgets.QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons = {}
        for value, text, icon, tooltip in options:
            button = text_button(text, tooltip, icon_name=icon)
            button.setCheckable(True)
            set_variant(button, "segment")
            button.clicked.connect(lambda _checked=False, value=value: self.valueChanged.emit(value))
            self.group.addButton(button)
            self.buttons[value] = button
            layout.addWidget(button)
        self.set_value(next(iter(self.buttons)))

    def set_value(self, value: str) -> None:
        self.buttons[value].setChecked(True)

    def refresh_icons(self) -> None:
        for button in self.buttons.values():
            name = button.property("iconName")
            if name:
                button.setIcon(icons.standard_icon(name))
