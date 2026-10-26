from __future__ import annotations

from ...i18n import t

from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from ..theme import tokens
from .style_utils import apply_margins


class PreviewConfirmationContent(QtWidgets.QWidget):
    def __init__(self, source: Path, count: int, clipboard: bool, parent=None):
        super().__init__(parent)
        layout = apply_margins(QtWidgets.QVBoxLayout(self), spacing=tokens.SPACE_2XL)
        if clipboard:
            text = t('use_the_image_from_the_clipboard_as_the_preview')
        else:
            text = t('apply_this_preview_image')
        if count > 1:
            text += t('the_same_image_will_be_applied_to_all_value0_selected_mods_replacing_the', value0=f'{count}')
        else:
            text += t('the_selected_mod_s_existing_preview_will_be_replaced')
        self.message = QtWidgets.QLabel(text, self)
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.preview = QtWidgets.QLabel(self)
        self.preview.setAlignment(QtCore.Qt.AlignCenter)
        self.preview.setFixedHeight(tokens.PREVIEW_CONFIRM_IMAGE_SIZE)
        reader = QtGui.QImageReader(str(source))
        reader.setAutoTransform(True)
        size = reader.size()
        if size.isValid():
            size.scale(tokens.PREVIEW_CONFIRM_IMAGE_SIZE, tokens.PREVIEW_CONFIRM_IMAGE_SIZE, QtCore.Qt.KeepAspectRatio)
            reader.setScaledSize(size)
        self.preview.setPixmap(QtGui.QPixmap.fromImage(reader.read()))
        self.preview.setAccessibleName(t('preview_image_to_apply'))
        layout.addWidget(self.preview)
