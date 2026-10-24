from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ... import settings_schema
from ...settings_schema import INT, SETTINGS_SECTIONS
from ...workers import _run_save_settings
from .. import icons
from ..dialogs import prompts
from ..theme import colors, tokens
from ..widgets import FormBuilder, IconToolbar, apply_margins, write_field
from ..widgets.workspace import WorkspacePage
from ..widgets.style_utils import set_variant
from .widget_registry import ACTIONS

TITLE = "Settings"
SAVED_MESSAGE = "Settings saved."
PREVIEW_LABEL = "Theme preview"
FONT_PREVIEW_LABEL = "Font preview"
FONT_PREVIEW_TEXT = "Aa — The quick brown fox 0123456789"
ACCENT_KEY = "gui_accent_color"
TEXT_KEY = "gui_text_color"
MODE_SUFFIX = "_mode"

COLOR_ACTIONS = {
    ACCENT_KEY: ("choose_accent", "image", "Choose the accent colour"),
    TEXT_KEY: ("choose_text", "image", "Choose the text colour"),
}

THEME_KEYS = (
    "gui_theme",
    "gui_accent_color_mode",
    ACCENT_KEY,
    "gui_text_color_mode",
    TEXT_KEY,
    "gui_font_family",
    "gui_font_size",
)


class SettingsController(QtCore.QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.page = WorkspacePage(TITLE, "Changes apply only when you save. Drafts remain here while you navigate.")
        self._build()

    @property
    def cfg(self) -> dict:
        return self.window.cfg

    @property
    def fields(self) -> dict:
        return self.form.fields

    def _build(self) -> None:
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        wrapper = QtWidgets.QWidget()
        wrapper_layout = QtWidgets.QVBoxLayout(wrapper)
        wrapper_layout.setAlignment(QtCore.Qt.AlignTop)
        host = QtWidgets.QWidget()
        self.form = FormBuilder(host)

        values = settings_schema.read_settings(self.cfg)
        for title, specs in SETTINGS_SECTIONS:
            self.form.add_section(title)
            pending_int = None
            for spec in specs:
                action = None
                if spec.key in COLOR_ACTIONS:
                    key, icon_name, tooltip = COLOR_ACTIONS[spec.key]
                    action = (key, icon_name, tooltip, lambda k=spec.key: self.choose_color(k))
                if spec.kind == INT and spec.depends_on is None:
                    if pending_int is None:
                        pending_int = (spec, values[spec.key])
                    else:
                        self.form.add_spec_pair(pending_int, (spec, values[spec.key]))
                        pending_int = None
                    continue
                if pending_int is not None:
                    pending_spec, pending_value = pending_int
                    self.form.add_spec(pending_spec, pending_value)
                    pending_int = None
                self.form.add_spec(spec, values[spec.key], action=action)
            if pending_int is not None:
                pending_spec, pending_value = pending_int
                self.form.add_spec(pending_spec, pending_value)
            if title == "Appearance":
                self.form.add_widget(FONT_PREVIEW_LABEL, self._build_font_preview())
                self.form.add_widget(PREVIEW_LABEL, self._build_preview_row())

        for key in (ACCENT_KEY, TEXT_KEY):
            self.fields[key + MODE_SUFFIX].currentTextChanged.connect(self._on_color_mode_changed)
        self.update_color_rows()
        self.update_preview()
        self.fields["gui_font_family"].currentTextChanged.connect(self.update_font_preview)
        self.fields["gui_font_size"].textChanged.connect(self.update_font_preview)
        self.update_font_preview()

        self.toolbar = IconToolbar(self.page)
        section = self.toolbar.add_section("settings", "Settings")
        button = section.add_text_action("save_settings", "Save", "save", "Save settings", self.save)
        set_variant(button, "primary")
        section.add_text_action("reset_settings", "Reset changes", "reset", "Restore the last saved settings", self.reset)
        self.window.registry.extend(ACTIONS, self.toolbar.buttons.values())
        self.toolbar.add_stretch()

        wrapper_layout.addWidget(host)
        wrapper_layout.addStretch(1)
        scroll.setWidget(wrapper)
        layout = self.page.body
        layout.addWidget(scroll)
        layout.addWidget(self.toolbar)

    def _preview_badge(self, tooltip: str, handler, text: str = "") -> QtWidgets.QToolButton:
        badge = QtWidgets.QToolButton()
        badge.setText(text)
        badge.setAutoRaise(True)
        badge.setIconSize(QtCore.QSize(tokens.PREVIEW_ICON_SIZE, tokens.PREVIEW_ICON_SIZE))
        badge.setCursor(QtCore.Qt.PointingHandCursor)
        badge.setToolTip(tooltip)
        badge.clicked.connect(handler)
        return badge

    def _build_preview_row(self) -> QtWidgets.QWidget:
        self.accent_badge = self._preview_badge("Click to toggle accent color mode", lambda: self.toggle_color_mode(ACCENT_KEY))
        self.accent_button = QtWidgets.QPushButton("Active")
        self.accent_button.setEnabled(False)
        self.text_badge = self._preview_badge("Click to toggle text color mode", lambda: self.toggle_color_mode(TEXT_KEY), "Aa")
        container = QtWidgets.QWidget()
        row = apply_margins(QtWidgets.QHBoxLayout(container), margins=None)
        row.addWidget(self.accent_badge)
        row.addWidget(self.accent_button)
        row.addWidget(self.text_badge)
        row.addStretch(1)
        return container

    def _build_font_preview(self) -> QtWidgets.QLabel:
        self.font_preview = QtWidgets.QLabel(FONT_PREVIEW_TEXT)
        self.font_preview.setMinimumHeight(tokens.FONT_PREVIEW_MIN_HEIGHT)
        self.font_preview.setAlignment(QtCore.Qt.AlignCenter)
        return self.font_preview

    def update_font_preview(self, _value: str = "") -> None:
        font = self.window.theme.base_font
        family = self.fields["gui_font_family"].currentText().strip()
        if family:
            font.setFamily(family)
        try:
            size = int(self.fields["gui_font_size"].text())
        except ValueError:
            size = 0
        if size > 0:
            font.setPointSize(size)
        self.font_preview.setFont(font)

    def fallback_color(self, key: str) -> QtGui.QColor:
        palette = self.window.theme.palette
        return QtGui.QColor(palette.accent if key == ACCENT_KEY else palette.fg)

    def color(self, key: str) -> QtGui.QColor:
        if self.fields[key + MODE_SUFFIX].currentText() == "custom":
            value = QtGui.QColor(self.fields[key].text())
            if value.isValid():
                return value
        return self.fallback_color(key)

    def choose_color(self, key: str) -> None:
        current = QtGui.QColor(self.fields[key].text())
        if not current.isValid():
            current = self.fallback_color(key)
        chosen = prompts.choose_color(self.window, current, f"Choose {settings_schema.label_for(key).lower()}")
        if chosen.isValid():
            self.fields[key].setText(chosen.name())
            self.update_preview()

    def toggle_color_mode(self, key: str) -> None:
        combo = self.fields[key + MODE_SUFFIX]
        combo.setCurrentText("custom" if combo.currentText() == "system" else "system")

    def update_color_rows(self) -> None:
        for spec in settings_schema.all_specs():
            if spec.depends_on:
                other_key, required = spec.depends_on
                self.form.set_row_visible(spec.key, self.fields[other_key].currentText() == required)

    def _on_color_mode_changed(self, _text: str = "") -> None:
        self.update_color_rows()
        self.update_preview()

    def update_preview(self) -> None:
        accent = self.color(ACCENT_KEY)
        text = self.color(TEXT_KEY)
        preview = colors.build_palette(self.window.theme.palette.mode, accent.name(), text.name())
        pad_v, pad_h = tokens.BUTTON_PADDING
        self.accent_badge.setIcon(icons.check_icon(accent, size=tokens.PREVIEW_ICON_SIZE))
        self.accent_button.setStyleSheet(
            f"background-color: {preview.accent_fill};"
            f"border: {tokens.BORDER_WIDTH}px solid {preview.accent_border};"
            f"border-radius: {tokens.RADIUS_LG}px;"
            f"padding: {pad_v}px {pad_h}px; color: {preview.fg};"
        )
        self.text_badge.setStyleSheet(f"color: {preview.fg}; font-weight: 600;")

    def theme_settings(self, cfg: dict | None = None) -> tuple:
        source = self.cfg if cfg is None else cfg
        return tuple(str(source.get(key, "") or "") for key in THEME_KEYS)

    def save(self) -> None:
        old_theme = self.theme_settings()
        values = self.form.values()
        try:
            settings_schema.coerce_settings(values)
        except ValueError as error:
            prompts.show_error(self.window, TITLE, str(error))
            return

        def done(new_cfg):
            self.window.apply_saved_settings(new_cfg, old_theme != self.theme_settings(new_cfg))

        self.window._run_action("Saving settings...", lambda: _run_save_settings(self.cfg, values), done)

    def reset(self) -> None:
        for key, value in settings_schema.read_settings(self.cfg).items():
            write_field(self.fields[key], value)
        self.update_color_rows()
        self.update_preview()
        self.update_font_preview()
