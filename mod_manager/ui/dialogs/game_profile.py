from __future__ import annotations

from ...i18n import t
from ...platform_utils import is_windows
from ...quick_tools import parse_quick_tools

from PySide6 import QtCore, QtWidgets

from ...settings_schema import GAME_PROFILE_FIELDS, QUICK_TOOLS, coerce_game_profile
from ..theme import tokens
from ..widgets.form import FormBuilder
from ..widgets.quick_tools_editor import QuickToolsEditor
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
            if spec.key == QUICK_TOOLS:
                continue
            field = self.form.add_spec(spec, self.profile.get(spec.key), self._browse)
            field.setMinimumWidth(tokens.PROFILE_FIELD_MIN_WIDTH)
        self.quick_tools = QuickToolsEditor(parse_quick_tools(self.profile.get(QUICK_TOOLS), strict=False),
                                            self._browse_application, host)
        self.form.layout.addWidget(self.quick_tools)
        self.scroll = QtWidgets.QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.scroll.setWidget(host)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.scroll, 1)
        layout.addWidget(buttons)
        margins = layout.contentsMargins()
        self.setMinimumWidth(host.minimumSizeHint().width() + margins.left() + margins.right() + tokens.SCROLLBAR_WIDTH)

    def _browse(self, key: str) -> None:
        spec = next(spec for spec in GAME_PROFILE_FIELDS if spec.key == key)
        path = prompts.choose_directory(self, spec.label)
        if path:
            self.form.fields[key].setText(path)

    def _browse_application(self, field: QtWidgets.QLineEdit) -> None:
        file_filter = t("quick_tool_windows_files") if is_windows() else ""
        path = prompts.choose_open_file(self, t("quick_tool_browse"), file_filter)
        if path:
            field.setText(path)

    def _values(self) -> dict:
        values = coerce_game_profile(self.form.values())
        values[QUICK_TOOLS] = parse_quick_tools(self.quick_tools.values(), ignore_blank=True)
        return values

    def accept(self) -> None:
        try:
            values = self._values()
        except ValueError as error:
            prompts.show_error(self, TITLE, str(error))
            return
        if not values.get("name"):
            prompts.show_error(self, TITLE, MISSING_NAME)
            return
        super().accept()

    def values(self) -> dict | None:
        if self.exec() != QtWidgets.QDialog.Accepted:
            return None
        return self._values()
