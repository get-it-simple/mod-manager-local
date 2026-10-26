from __future__ import annotations

from ...i18n import t

from PySide6 import QtWidgets

from ...settings_schema import GAME_PROFILE_FIELDS
from ..theme import tokens
from ..widgets.form import FormBuilder
from . import prompts

TITLE = t('game_profile')
MISSING_NAME = t('enter_game_name')


class GameProfileDialog(QtWidgets.QDialog):
    def __init__(self, parent, profile: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle(TITLE)
        self.profile = dict(profile or {})
        host = QtWidgets.QWidget(self)
        self.form = FormBuilder(host)
        for spec in GAME_PROFILE_FIELDS:
            field = self.form.add_spec(spec, self.profile.get(spec.key), self._browse)
            field.setMinimumWidth(tokens.PROFILE_FIELD_MIN_WIDTH)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(host)
        layout.addWidget(buttons)

    def _browse(self, key: str) -> None:
        spec = next(spec for spec in GAME_PROFILE_FIELDS if spec.key == key)
        path = prompts.choose_directory(self, spec.label)
        if path:
            self.form.fields[key].setText(path)

    def values(self) -> dict | None:
        if self.exec() != QtWidgets.QDialog.Accepted:
            return None
        values = self.form.values()
        values = {key: value.strip() if isinstance(value, str) else value for key, value in values.items()}
        if not values.get("name"):
            prompts.show_error(self, TITLE, MISSING_NAME)
            return None
        return values
