from __future__ import annotations

from collections.abc import Callable

from PySide6 import QtCore, QtWidgets

from ...i18n import t
from ...quick_tools import QuickTool
from ...settings_schema import QUICK_TOOL_LABEL_FIELD, QUICK_TOOL_PATH_FIELD, QUICK_TOOLS_FIELD
from ..theme import tokens
from .buttons import icon_button, text_button
from .form import FormSection, build_field
from .style_utils import apply_margins


class QuickToolRow(QtWidgets.QWidget):
    def __init__(self, tool: QuickTool, browse: Callable, remove: Callable, parent=None):
        super().__init__(parent)
        layout = apply_margins(QtWidgets.QHBoxLayout(self), spacing=tokens.SPACE_SM)
        self.label = self._field(QUICK_TOOL_LABEL_FIELD, tool["label"])
        self.path = self._field(QUICK_TOOL_PATH_FIELD, tool["path"])
        self.browse = icon_button("folder", t("quick_tool_browse"), lambda: browse(self.path), self)
        self.remove = icon_button("remove", t("quick_tool_remove"), lambda: remove(self), self)
        layout.addWidget(self.label, 1)
        layout.addWidget(self.path, 2)
        for button in (self.browse, self.remove):
            button.setAutoDefault(False)
            layout.addWidget(button)

    def _field(self, spec, value: str) -> QtWidgets.QLineEdit:
        field = build_field(spec, value, self)
        field.setAccessibleName(spec.label)
        field.setPlaceholderText(spec.label)
        field.setToolTip(spec.tooltip)
        return field

    def value(self) -> QuickTool:
        return {"label": self.label.text().strip(), "path": self.path.text().strip()}


class QuickToolsEditor(FormSection):
    def __init__(self, tools: list[QuickTool], browse: Callable, parent=None):
        spec = QUICK_TOOLS_FIELD
        super().__init__(spec.label, parent)
        self.setToolTip(spec.tooltip)
        self.title_label.setToolTip(spec.tooltip)
        self.rows: list[QuickToolRow] = []
        self._browse = browse
        self.add = text_button(t("quick_tool_add"), spec.tooltip, self._add_blank_row, self, icon_name="add")
        self.add.setAutoDefault(False)
        self.form_layout.addRow(self.add)
        for tool in tools:
            self._add_row(tool)

    def _add_row(self, tool: QuickTool) -> QuickToolRow:
        row = QuickToolRow(tool, self._browse, self._remove_row, self)
        self.rows.append(row)
        self.form_layout.insertRow(len(self.rows) - 1, row)
        return row

    def _add_blank_row(self) -> None:
        self._add_row({"label": "", "path": ""}).label.setFocus(QtCore.Qt.OtherFocusReason)

    def _remove_row(self, row: QuickToolRow) -> None:
        self.rows.remove(row)
        self.form_layout.takeRow(row)
        row.hide()
        row.deleteLater()
        self.add.setFocus(QtCore.Qt.OtherFocusReason)

    def values(self) -> list[QuickTool]:
        return [row.value() for row in self.rows]
