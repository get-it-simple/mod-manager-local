from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ...quick_tools import QuickTool
from ...settings_schema import QUICK_TOOLS_FIELD
from ..theme import tokens
from .buttons import text_button
from .style_utils import apply_margins, clear_layout


class QuickToolsBar(QtWidgets.QWidget):
    launchRequested = QtCore.Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)
        self.setAccessibleName(QUICK_TOOLS_FIELD.label)
        self._tools = ()
        self._profile_id = ""
        self.buttons: list[QtWidgets.QPushButton] = []
        self.scroll = QtWidgets.QScrollArea(self)
        self.scroll.setSizeAdjustPolicy(QtWidgets.QAbstractScrollArea.AdjustIgnored)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.scroll.setFocusPolicy(QtCore.Qt.NoFocus)
        content = QtWidgets.QWidget()
        self._row = apply_margins(QtWidgets.QHBoxLayout(content), (0, 0, 0, tokens.SCROLLBAR_WIDTH), tokens.SPACE_SM)
        self._row.setSizeConstraint(QtWidgets.QLayout.SetMinimumSize)
        self.scroll.setWidget(content)
        self.scroll.viewport().installEventFilter(self)
        separator = QtWidgets.QFrame(self)
        separator.setFrameShape(QtWidgets.QFrame.VLine)
        separator.setFrameShadow(QtWidgets.QFrame.Plain)
        separator.setFixedSize(tokens.BORDER_WIDTH, tokens.ICON_BUTTON_SIZE)
        layout = apply_margins(QtWidgets.QHBoxLayout(self))
        layout.addWidget(self.scroll, 1)
        layout.addWidget(separator, 0, QtCore.Qt.AlignVCenter)
        self.hide()

    def set_tools(self, profile_id: str, tools: list[QuickTool]) -> None:
        entries = tuple((tool["label"], tool["path"]) for tool in tools)
        if (profile_id, entries) == (self._profile_id, self._tools):
            return
        self._profile_id, self._tools = profile_id, entries
        clear_layout(self._row)
        self._row.addStretch()
        self.buttons.clear()
        for label, path in entries:
            button = text_button(label, f"{label}\n{path}", lambda label=label, path=path: self.launchRequested.emit(label, path))
            button.installEventFilter(self)
            self._row.addWidget(button, 0, QtCore.Qt.AlignVCenter)
            self.buttons.append(button)
        self.setVisible(bool(entries))
        self._fit_labels()
        self.scroll.horizontalScrollBar().setValue(0)

    def _fit_labels(self) -> None:
        padding = (tokens.BUTTON_PADDING[1] + tokens.BORDER_WIDTH) * 2
        width = max(0, min(self.scroll.viewport().width(), tokens.QUICK_TOOL_BUTTON_MAX_WIDTH) - padding)
        for button in self.buttons:
            label = button.accessibleName()
            text = button.fontMetrics().elidedText(label, QtCore.Qt.ElideRight, width)
            button.setText(text.replace("&", "&&"))

    def eventFilter(self, obj, event) -> bool:
        kind = event.type()
        if obj is self.scroll.viewport():
            if kind == QtCore.QEvent.Resize:
                self._fit_labels()
            elif kind == QtCore.QEvent.Wheel and self._scroll_with_wheel(event):
                return True
        elif kind == QtCore.QEvent.FocusIn and obj in self.buttons:
            self.scroll.ensureWidgetVisible(obj, 0, 0)
        return super().eventFilter(obj, event)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() in (QtCore.QEvent.FontChange, QtCore.QEvent.StyleChange):
            self._fit_labels()

    def _scroll_with_wheel(self, event) -> bool:
        bar = self.scroll.horizontalScrollBar()
        if bar.maximum() == bar.minimum():
            return False
        pixels = event.pixelDelta()
        angle = event.angleDelta()
        delta = pixels.x() or pixels.y() or (angle.x() or angle.y()) * bar.singleStep() // tokens.WHEEL_ANGLE_STEP
        bar.setValue(bar.value() - delta)
        event.accept()
        return True
