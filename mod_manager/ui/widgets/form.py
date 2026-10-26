from __future__ import annotations

from ...i18n import t

from typing import Callable

from PySide6 import QtCore, QtGui, QtWidgets

from ...settings_schema import CHOICE, COLOR, FLAG, FONT, INT, PATH, TEXT, SHORTCUTS, FieldSpec
from .shortcut_editor import ShortcutSettings
from ..theme import tokens
from .buttons import icon_button
from .section import section_title_label
from .select import select_box
from .style_utils import apply_margins, expanding_size_policy, fixed_size_policy, set_variant


_font_families: list[str] | None = None


def system_font_families() -> list[str]:
    global _font_families
    if _font_families is None:
        try:
            families = QtGui.QFontDatabase.families()
        except TypeError:
            families = QtGui.QFontDatabase().families()
        _font_families = sorted({str(family) for family in families if family}, key=str.lower)
    return list(_font_families)


def read_field(widget: QtWidgets.QWidget):
    if isinstance(widget, ShortcutSettings):
        return widget.values()
    if isinstance(widget, QtWidgets.QCheckBox):
        return widget.isChecked()
    if isinstance(widget, QtWidgets.QComboBox):
        return widget.currentData() if widget.property("usesChoiceData") else widget.currentText()
    return widget.text()


def write_field(widget: QtWidgets.QWidget, value) -> None:
    if isinstance(widget, ShortcutSettings):
        widget.set_values(value)
    elif isinstance(widget, QtWidgets.QCheckBox):
        widget.setChecked(bool(value))
    elif isinstance(widget, QtWidgets.QComboBox):
        if widget.property("usesChoiceData"):
            widget.setCurrentIndex(widget.findData(value))
        else:
            widget.setCurrentText(str(value or ""))
    else:
        widget.setText(str(value or ""))


def build_field(spec: FieldSpec, value, parent=None) -> QtWidgets.QWidget:
    if spec.kind == SHORTCUTS:
        return ShortcutSettings(value, parent)
    if spec.kind == FLAG:
        widget = QtWidgets.QCheckBox(parent)
        widget.setChecked(bool(value))
        return widget
    if spec.kind == CHOICE:
        widget = select_box(parent)
        if spec.key == "gui_language":
            widget.setProperty("usesChoiceData", True)
            for language in spec.choices:
                widget.addItem(t("english_language") if language == "en" else language, language)
            widget.setCurrentIndex(widget.findData(value or spec.choices[0]))
        else:
            widget.addItems(list(spec.choices))
            widget.setCurrentText(str(value or spec.choices[0]))
    elif spec.kind == FONT:
        widget = select_box(parent)
        widget.addItem("")
        widget.addItems(system_font_families())
        if value and widget.findText(str(value)) < 0:
            widget.addItem(str(value))
        widget.setCurrentText(str(value or ""))
    elif spec.kind == COLOR:
        widget = QtWidgets.QLineEdit(str(value or ""), parent)
        widget.setReadOnly(True)
    else:
        widget = QtWidgets.QLineEdit(str(value if value is not None else ""), parent)
    if spec.kind == INT:
        widget.setFixedWidth(tokens.FORM_SHORT_FIELD_WIDTH)
        return fixed_size_policy(widget)
    if spec.kind in {CHOICE, FONT, COLOR}:
        widget.setMaximumWidth(tokens.FORM_MEDIUM_FIELD_WIDTH)
    return expanding_size_policy(widget)


class FormSection(QtWidgets.QFrame):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        set_variant(self, "formSection")
        outer = apply_margins(
            QtWidgets.QVBoxLayout(self),
            margins=tokens.TOOLBAR_SECTION_MARGIN,
            spacing=tokens.SPACE_SM,
        )
        self.title_label = section_title_label(title, self) if title else None
        if self.title_label is not None:
            outer.addWidget(self.title_label)
        self.form_layout = QtWidgets.QFormLayout()
        self.form_layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        self.form_layout.setHorizontalSpacing(tokens.SPACE_LG)
        self.form_layout.setVerticalSpacing(tokens.SPACE_SM)
        outer.addLayout(self.form_layout)


class FormBuilder:
    def __init__(self, parent: QtWidgets.QWidget):
        self.host = parent
        self.layout = apply_margins(QtWidgets.QVBoxLayout(parent), margins=None, spacing=tokens.SPACE_MD)
        self.fields: dict[str, QtWidgets.QWidget] = {}
        self.rows: dict[str, QtWidgets.QWidget] = {}
        self.labels: dict[str, QtWidgets.QLabel] = {}
        self.buttons: dict[str, QtWidgets.QAbstractButton] = {}
        self.sections: dict[str, FormSection] = {}
        self._current_section: FormSection | None = None
        self._row_layouts: dict[str, QtWidgets.QFormLayout] = {}

    def add_section(self, title: str) -> QtWidgets.QLabel:
        section = FormSection(title, self.host)
        self.sections[title] = section
        self._current_section = section
        self.layout.addWidget(section)
        return section.title_label

    def _form_layout(self) -> QtWidgets.QFormLayout:
        if self._current_section is None:
            self.add_section("")
        return self._current_section.form_layout

    def _build_spec_widgets(self, spec: FieldSpec, value, on_browse: Callable | None = None, action=None):
        field = build_field(spec, value, self.host)
        field.setToolTip(spec.tooltip)

        container = QtWidgets.QWidget(self.host)
        row = apply_margins(QtWidgets.QHBoxLayout(container), margins=None, spacing=tokens.SPACE_SM)
        if spec.kind in {PATH, TEXT, SHORTCUTS}:
            row.addWidget(field, 1)
        else:
            row.addWidget(field, 0, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        if spec.kind == PATH and on_browse is not None:
            button = icon_button("folder", t('browse_for_the_value0', value0=f'{spec.label.lower()}'), lambda key=spec.key: on_browse(key), container)
            self.buttons[f"browse_{spec.key}"] = button
            row.addWidget(button)
        if action is not None:
            key, icon_name, tooltip, handler = action
            button = icon_button(icon_name, tooltip, handler, container)
            self.buttons[key] = button
            row.addWidget(button)
        if spec.kind not in {PATH, TEXT, SHORTCUTS}:
            row.addStretch(1)

        label = QtWidgets.QLabel(spec.label, self.host)
        label.setToolTip(spec.tooltip)
        label.setMinimumWidth(tokens.FORM_LABEL_MIN_WIDTH)
        return field, label, container

    def _register_spec(
        self,
        spec: FieldSpec,
        field: QtWidgets.QWidget,
        label: QtWidgets.QLabel,
        row_widget: QtWidgets.QWidget,
        form_layout: QtWidgets.QFormLayout,
    ) -> None:
        self.fields[spec.key] = field
        self.labels[spec.key] = label
        self.rows[spec.key] = row_widget
        self._row_layouts[spec.key] = form_layout

    def add_spec(self, spec: FieldSpec, value, on_browse: Callable | None = None, action=None) -> QtWidgets.QWidget:
        field, label, container = self._build_spec_widgets(spec, value, on_browse, action)
        form_layout = self._form_layout()
        if spec.kind == SHORTCUTS:
            form_layout.addRow(container)
            label.hide()
            if self._current_section.title_label is not None:
                self._current_section.title_label.hide()
        else:
            form_layout.addRow(label, container)
        self._register_spec(spec, field, label, container, form_layout)
        return field

    def add_spec_pair(
        self,
        first: tuple[FieldSpec, object],
        second: tuple[FieldSpec, object],
    ) -> tuple[QtWidgets.QWidget, QtWidgets.QWidget]:
        first_spec, first_value = first
        second_spec, second_value = second
        first_field, first_label, first_container = self._build_spec_widgets(first_spec, first_value)
        second_field, second_label, second_container = self._build_spec_widgets(second_spec, second_value)
        fixed_size_policy(first_container)
        fixed_size_policy(second_container)

        pair = QtWidgets.QWidget(self.host)
        pair_layout = apply_margins(QtWidgets.QHBoxLayout(pair), margins=None, spacing=0)
        pair_layout.addWidget(first_container)
        pair_layout.addSpacing(tokens.FORM_PAIR_SPACING)
        pair_layout.addWidget(second_label)
        pair_layout.addSpacing(tokens.SPACE_LG)
        pair_layout.addWidget(second_container)
        pair_layout.addStretch(1)

        form_layout = self._form_layout()
        form_layout.addRow(first_label, pair)
        self._register_spec(first_spec, first_field, first_label, pair, form_layout)
        self._register_spec(second_spec, second_field, second_label, pair, form_layout)
        return first_field, second_field

    def add_widget(self, label: str, widget: QtWidgets.QWidget) -> QtWidgets.QWidget:
        self._form_layout().addRow(label, widget)
        return widget

    def add_row_widget(self, widget: QtWidgets.QWidget) -> QtWidgets.QWidget:
        self._form_layout().addRow(widget)
        return widget

    def set_row_visible(self, key: str, visible: bool) -> None:
        row = self.rows.get(key)
        if row is not None:
            self._row_layouts[key].setRowVisible(row, visible)

    def is_row_visible(self, key: str) -> bool:
        row = self.rows.get(key)
        return bool(row is not None and self._row_layouts[key].isRowVisible(row))

    def values(self) -> dict:
        return {key: read_field(widget) for key, widget in self.fields.items()}
