from __future__ import annotations

from PySide6 import QtWidgets

from ..theme import tokens

VARIANT_PROPERTY = "variant"
ACRYLIC = "acrylic"
TOOLBAR_SECTION = "toolbarSection"
SECTION_TITLE = "sectionTitle"
MUTED = "muted"
HEADING = "heading"
LINK = "link"
PANEL = "panel"


def repolish(widget: QtWidgets.QWidget) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def set_variant(widget: QtWidgets.QWidget, variant: str) -> QtWidgets.QWidget:
    widget.setProperty(VARIANT_PROPERTY, variant)
    repolish(widget)
    return widget


def fixed_size_policy(widget: QtWidgets.QWidget) -> QtWidgets.QWidget:
    widget.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
    return widget


def expanding_size_policy(widget: QtWidgets.QWidget) -> QtWidgets.QWidget:
    widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
    return widget


def apply_margins(layout, margins=None, spacing: int | None = None):
    if margins is None:
        layout.setContentsMargins(0, 0, 0, 0)
    elif isinstance(margins, int):
        layout.setContentsMargins(margins, margins, margins, margins)
    else:
        layout.setContentsMargins(*margins)
    layout.setSpacing(tokens.SPACE_MD if spacing is None else spacing)
    return layout


def clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget:
            widget.hide()
            widget.deleteLater()
        child = item.layout()
        if child:
            clear_layout(child)
