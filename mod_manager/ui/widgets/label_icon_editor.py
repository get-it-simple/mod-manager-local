from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ...settings_schema import LABEL_ICON_FIELD, LABEL_ICON_ONLY_FIELD
from ...i18n import t
from ..label_artwork import label_icon
from ..theme import tokens
from .buttons import icon_button
from .flow_layout import FlowLayout, WrappingWidget
from .select import select_box
from .style_utils import apply_margins


class LabelIconEditor(WrappingWidget):
    chooseRequested = QtCore.Signal()
    removeRequested = QtCore.Signal()
    displayChanged = QtCore.Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = FlowLayout(self, constrain_items=True)
        layout.setSpacing(tokens.SPACE_SM)
        actions = QtWidgets.QWidget(self)
        row = apply_margins(QtWidgets.QHBoxLayout(actions), margins=None, spacing=tokens.SPACE_SM)
        caption = QtWidgets.QLabel(LABEL_ICON_FIELD.label)
        caption.setToolTip(LABEL_ICON_FIELD.tooltip)
        self.preview = QtWidgets.QLabel()
        self.preview.setFixedSize(tokens.LABEL_ICON_PREVIEW_SIZE, tokens.LABEL_ICON_PREVIEW_SIZE)
        self.preview.setAlignment(QtCore.Qt.AlignCenter)
        self.choose = icon_button("image", LABEL_ICON_FIELD.tooltip, self.chooseRequested.emit)
        self.remove = icon_button("clear", t("remove_label_icon"), self.removeRequested.emit)
        row.addWidget(caption)
        row.addWidget(self.preview)
        row.addWidget(self.choose)
        row.addWidget(self.remove)
        layout.addWidget(actions)
        self.display = select_box()
        self.display.addItems(LABEL_ICON_ONLY_FIELD.choices)
        self.display.setToolTip(LABEL_ICON_ONLY_FIELD.tooltip)
        self.display.setAccessibleName(LABEL_ICON_ONLY_FIELD.label)
        self.display.currentIndexChanged.connect(lambda index: self.displayChanged.emit(bool(index)))
        display_group = QtWidgets.QWidget(self)
        display_row = apply_margins(QtWidgets.QHBoxLayout(display_group), margins=None, spacing=tokens.SPACE_SM)
        display_caption = QtWidgets.QLabel(LABEL_ICON_ONLY_FIELD.label)
        display_caption.setToolTip(LABEL_ICON_ONLY_FIELD.tooltip)
        display_row.addWidget(display_caption)
        display_row.addWidget(self.display, 1)
        layout.addWidget(display_group)

    def set_definition(self, definition):
        with QtCore.QSignalBlocker(self.display):
            self.display.setCurrentIndex(int(definition.icon_only))
        self.remove.setEnabled(bool(definition.icon))
        self.display.setEnabled(bool(definition.icon))
        self.preview.setPixmap(label_icon(definition).pixmap(
            tokens.LABEL_ICON_PREVIEW_SIZE, tokens.LABEL_ICON_PREVIEW_SIZE))
        self.preview.setToolTip(LABEL_ICON_FIELD.tooltip)
