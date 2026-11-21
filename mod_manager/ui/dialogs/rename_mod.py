from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtWidgets

from ...i18n import t
from ...renames import validate_name
from ..theme import tokens
from ..widgets.buttons import text_button
from ..widgets.style_utils import apply_margins, set_variant


class RenameModDialog(QtWidgets.QDialog):
    def __init__(self, parent, mod):
        super().__init__(parent)
        self.mod = mod
        self.suffix = "" if mod.is_dir else Path(mod.name).suffix
        self.setWindowTitle(t("rename_mod"))
        self.setMinimumWidth(tokens.RENAME_DIALOG_WIDTH)
        self.name_edit = QtWidgets.QLineEdit(mod.name if mod.is_dir else Path(mod.name).stem, self)
        self.name_edit.setAccessibleName(t("rename_new_name"))
        self.name_edit.setToolTip(t("rename_mod_help"))
        self.name_edit.selectAll()
        self.status = QtWidgets.QLabel(self)
        self.status.setWordWrap(True)
        self.save_button = text_button(t("save"), t("rename_mod_help"), self.accept, icon_name="save")
        self.cancel_button = text_button(t("cancel"), t("cancel"), self.reject)
        set_variant(self.save_button, "primary")
        self.save_button.setDefault(True)
        row = apply_margins(QtWidgets.QHBoxLayout(), margins=None, spacing=tokens.SPACE_SM)
        row.addWidget(self.name_edit, 1)
        if self.suffix:
            row.addWidget(QtWidgets.QLabel(self.suffix, self))
        actions = apply_margins(QtWidgets.QHBoxLayout(), margins=None, spacing=tokens.SPACE_SM)
        actions.addStretch()
        actions.addWidget(self.save_button)
        actions.addWidget(self.cancel_button)
        layout = apply_margins(QtWidgets.QVBoxLayout(self), margins=tokens.PAGE_MARGIN, spacing=tokens.SPACE_LG)
        label = QtWidgets.QLabel(t("rename_new_name"), self)
        label.setBuddy(self.name_edit)
        layout.addWidget(label)
        layout.addLayout(row)
        layout.addWidget(self.status)
        layout.addLayout(actions)
        self.name_edit.setFocus()

    @property
    def new_name(self):
        return self.name_edit.text().strip() + self.suffix

    def accept(self):
        try:
            validate_name(self.mod, self.new_name)
        except ValueError as error:
            self.status.setText(str(error))
            self.name_edit.setFocus()
            return
        super().accept()
