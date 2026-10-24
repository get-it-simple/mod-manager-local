from __future__ import annotations

from typing import Callable

from PySide6 import QtCore, QtWidgets

from .. import icons
from ..theme import tokens
from .style_utils import ACRYLIC, fixed_size_policy, set_variant


def _connect(button: QtWidgets.QAbstractButton, on_click: Callable | None) -> None:
    if on_click is not None:
        button.clicked.connect(lambda _checked=False: on_click())


def _base_button(text: str, tooltip: str, accessible_name: str, parent=None) -> QtWidgets.QPushButton:
    button = QtWidgets.QPushButton(text, parent)
    set_variant(button, ACRYLIC)
    button.setAccessibleName(accessible_name)
    button.setToolTip(tooltip or accessible_name)
    button.setCursor(QtCore.Qt.PointingHandCursor)
    button.setMinimumHeight(tokens.ICON_BUTTON_SIZE)
    return fixed_size_policy(button)


def icon_button(
    icon_name: str,
    tooltip: str,
    on_click: Callable | None = None,
    parent=None,
    checkable: bool = False,
    accessible_name: str = "",
) -> QtWidgets.QPushButton:
    button = _base_button("", tooltip, accessible_name or tooltip, parent)
    button.setIcon(icons.standard_icon(icon_name))
    button.setProperty("iconName", icon_name)
    button.setIconSize(QtCore.QSize(tokens.ICON_SIZE, tokens.ICON_SIZE))
    button.setFixedSize(tokens.ICON_BUTTON_SIZE, tokens.ICON_BUTTON_SIZE)
    button.setCheckable(checkable)
    _connect(button, on_click)
    return button


def text_button(
    text: str,
    tooltip: str,
    on_click: Callable | None = None,
    parent=None,
    icon_name: str = "",
    accessible_name: str = "",
) -> QtWidgets.QPushButton:
    button = _base_button(text, tooltip, accessible_name or text, parent)
    if icon_name:
        button.setIcon(icons.standard_icon(icon_name))
        button.setProperty("iconName", icon_name)
        button.setIconSize(QtCore.QSize(tokens.ICON_SIZE, tokens.ICON_SIZE))
    _connect(button, on_click)
    return button
