from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ...i18n import t
from ..label_artwork import label_icon
from ..theme import tokens
from ..widgets.select import select_box
from ..widgets.style_utils import apply_margins


class LabelChoiceDialog(QtWidgets.QDialog):
    def __init__(self, parent, names, definitions=None):
        super().__init__(parent)
        self.setWindowTitle(t("assign_label"))
        self.resize(tokens.LABEL_CHOICE_DIALOG_WIDTH, self.minimumSizeHint().height())
        self.names = {name.casefold(): name for name in names}
        self.choice = select_box(self, editable=True)
        self.choice.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        self.choice.setAccessibleName(t("label"))
        self.choice.setToolTip(t("label_choice_help"))
        for name in names:
            self.choice.addItem(label_icon((definitions or {}).get(name)), name)
        completer = self.choice.completer()
        completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
        completer.setFilterMode(QtCore.Qt.MatchContains)
        completer.setCompletionMode(QtWidgets.QCompleter.PopupCompletion)
        self.buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.choice.editTextChanged.connect(self._validate)
        layout = apply_margins(QtWidgets.QVBoxLayout(self), spacing=tokens.SPACE_LG)
        layout.addWidget(QtWidgets.QLabel(t("label")))
        layout.addWidget(self.choice)
        layout.addWidget(self.buttons)
        self._validate()

    @property
    def selected_label(self):
        return self.names.get(self.choice.currentText().strip().casefold(), "")

    def _validate(self, *_args):
        self.buttons.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(bool(self.selected_label))

    def accept(self):
        if self.selected_label:
            super().accept()
