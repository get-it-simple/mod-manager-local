from __future__ import annotations

from ...i18n import t

from typing import Callable

from PySide6 import QtCore, QtWidgets

from ..theme import tokens
from .buttons import icon_button, text_button
from .section import section_title_label
from .style_utils import TOOLBAR_SECTION, apply_margins, set_variant
from .flow_layout import FlowLayout


class ToolbarSection(QtWidgets.QFrame):
    def __init__(self, key: str, title: str, toolbar: "IconToolbar"):
        super().__init__(toolbar)
        self.key = key
        self._toolbar = toolbar
        set_variant(self, TOOLBAR_SECTION)
        layout = apply_margins(
            QtWidgets.QVBoxLayout(self),
            margins=tokens.TOOLBAR_SECTION_MARGIN,
            spacing=tokens.SPACE_XS,
        )
        layout.setAlignment(QtCore.Qt.AlignTop)
        self.title_label = section_title_label(title, self)
        self._actions_layout = FlowLayout(constrain_items=True)
        self._actions_layout.setSpacing(tokens.SPACE_SM)
        layout.addWidget(self.title_label)
        layout.addLayout(self._actions_layout)

    def sizeHint(self):
        size = super().sizeHint()
        widest = max((widget.sizeHint().width() for widget in self.widgets()), default=0)
        limit = max(tokens.TOOLBAR_SECTION_MAX_WIDTH, widest + tokens.TOOLBAR_SECTION_MARGIN * 2)
        if self.property("wideSection"):
            limit = self._toolbar.width()
        width = min(size.width(), limit + (self.property("expandedWidth") or 0))
        return QtCore.QSize(width, self.heightForWidth(width))

    @property
    def title(self) -> str:
        return self.title_label.text()

    def add_action(
        self,
        key: str,
        icon_name: str,
        tooltip: str,
        handler: Callable | None = None,
        checkable: bool = False,
        accessible_name: str = "",
    ) -> QtWidgets.QPushButton:
        if key in ("install_page", "uninstall_page"):
            return self.add_text_action(key, "", icon_name, tooltip, handler)
        button = icon_button(icon_name, tooltip, handler, self, checkable=checkable, accessible_name=accessible_name)
        return self.add_button(key, button)

    def add_text_action(
        self,
        key: str,
        text: str,
        icon_name: str,
        tooltip: str,
        handler: Callable | None = None,
    ) -> QtWidgets.QPushButton:
        button = text_button(text, tooltip, handler, self, icon_name=icon_name)
        return self.add_button(key, button)

    def add_actions(self, specs) -> None:
        for spec in specs:
            self.add_action(*spec)

    def add_button(self, key: str, button: QtWidgets.QAbstractButton) -> QtWidgets.QAbstractButton:
        button.setParent(self)
        self._actions_layout.addWidget(button)
        self._toolbar.register(key, button)
        return button

    def add_widget(self, widget: QtWidgets.QWidget, stretch: int = 0) -> QtWidgets.QWidget:
        widget.setParent(self)
        widget.setProperty("toolbarStretch", stretch)
        self._actions_layout.addWidget(widget)
        return widget

    def add_separator(self) -> QtWidgets.QFrame:
        separator = QtWidgets.QFrame(self)
        separator.setFrameShape(QtWidgets.QFrame.VLine)
        separator.setFrameShadow(QtWidgets.QFrame.Plain)
        self._actions_layout.addWidget(separator)
        return separator

    def widgets(self) -> list[QtWidgets.QWidget]:
        return [
            self._actions_layout.itemAt(index).widget()
            for index in range(self._actions_layout.count())
            if self._actions_layout.itemAt(index).widget() is not None
        ]


class IconToolbar(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = FlowLayout(self, constrain_items=True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.buttons: dict[str, QtWidgets.QAbstractButton] = {}
        self.sections: dict[str, ToolbarSection] = {}

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_height()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._update_height()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() in (QtCore.QEvent.FontChange, QtCore.QEvent.StyleChange) and hasattr(self, "_layout"):
            self._layout.invalidate()
            self._update_height()

    def _update_height(self) -> None:
        self.setMinimumHeight(self._layout.heightForWidth(self.width()))

    def add_section(self, key: str, title: str, stretch: int = 0) -> ToolbarSection:
        section = ToolbarSection(key, title, self)
        section.setProperty("toolbarStretch", stretch)
        section.setProperty("alignTrailing", key == "page")
        self.sections[key] = section
        self._layout.addWidget(section)
        return section

    def build(self, specs) -> None:
        for key, title, actions in specs:
            self.add_section(key, title).add_actions(actions)

    def add_stretch(self, stretch: int = 1) -> None:
        self._layout.invalidate()

    def register(self, key: str, button: QtWidgets.QAbstractButton) -> None:
        self.buttons[key] = button

    def button(self, key: str) -> QtWidgets.QAbstractButton | None:
        return self.buttons.get(key)

    def connect(self, handlers: dict) -> None:
        for key, handler in handlers.items():
            button = self.button(key)
            if button is not None:
                button.clicked.connect(lambda _checked=False, run=handler: run())

    def set_enabled(self, key: str, enabled: bool) -> None:
        button = self.button(key)
        if button is not None:
            button.setEnabled(bool(enabled))

    def apply_states(self, states: dict) -> None:
        for key, enabled in states.items():
            self.set_enabled(key, enabled)

    def disable_all(self) -> None:
        for button in self.buttons.values():
            button.setEnabled(False)

    def section_order(self) -> list[str]:
        return list(self.sections)
