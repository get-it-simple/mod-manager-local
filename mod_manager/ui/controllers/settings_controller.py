from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ... import settings_schema
from ...settings_schema import INT, SETTINGS_SECTIONS
from ...i18n import t
from ...workers import _run_save_settings
from .. import icons
from ..dialogs import prompts
from ..theme import colors, tokens
from ..widgets import FormBuilder, IconToolbar, apply_margins, write_field
from ..widgets.workspace import WorkspacePage
from ..widgets.font_preview import FontPreview
from ..widgets.style_utils import set_variant
from .widget_registry import ACTIONS

TITLE = t('settings')
SAVED_MESSAGE = t('settings_saved')
PREVIEW_LABEL = t('theme_preview')
FONT_PREVIEW_LABEL = t('font_preview')
FONT_PREVIEW_TEXT = t('aa_the_quick_brown_fox_0123456789')
ACCENT_KEY = "gui_accent_color"
TEXT_KEY = "gui_text_color"
MODE_SUFFIX = "_mode"

COLOR_ACTIONS = {
    ACCENT_KEY: ("choose_accent", "image", t('choose_the_accent_colour')),
    TEXT_KEY: ("choose_text", "image", t('choose_the_text_colour')),
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
        self.page = WorkspacePage(TITLE, t('changes_apply_only_when_you_save_drafts_remain_here_while_you_navigate'))
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
            if title == t('appearance'):
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
        section = self.toolbar.add_section("settings", t('settings'))
        button = section.add_text_action("save_settings", t('save'), "save", t('save_settings'), self.save)
        set_variant(button, "primary")
        section.add_text_action("reset_settings", t('reset_changes'), "reset", t('restore_the_last_saved_settings'), self.reset)
        self.window.registry.extend(ACTIONS, self.toolbar.buttons.values())
        self.toolbar.add_stretch()

        wrapper_layout.addWidget(host)
        wrapper_layout.addStretch(1)
        scroll.setWidget(wrapper)
        layout = self.page.body
        layout.addWidget(scroll)
        layout.addWidget(self.toolbar)
        self.draft_status = QtWidgets.QLabel(t("all_saved"))
        layout.addWidget(self.draft_status)
        for field in self.fields.values():
            signal = next((getattr(field, name) for name in ("changed", "toggled", "currentTextChanged", "textChanged")
                           if hasattr(field, name)), None)
            if signal is not None:
                signal.connect(self.update_dirty)

    def update_dirty(self, *_args) -> None:
        saved = settings_schema.read_settings(self.cfg)
        values = self.form.values()
        dirty = any(str(values[key]) != str(saved[key]) for key in values)
        self.draft_status.setText(t("unsaved_changes") if dirty else t("all_saved"))
        if hasattr(self.window, "workspace"):
            self.window.workspace.set_dirty("settings", dirty)

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
        self.accent_badge = self._preview_badge(t('click_to_toggle_accent_color_mode'), lambda: self.toggle_color_mode(ACCENT_KEY))
        self.accent_button = QtWidgets.QPushButton(t('active'))
        self.accent_button.setEnabled(False)
        self.text_badge = self._preview_badge(t('click_to_toggle_text_color_mode'), lambda: self.toggle_color_mode(TEXT_KEY), t('aa'))
        container = QtWidgets.QWidget()
        row = apply_margins(QtWidgets.QHBoxLayout(container), margins=None)
        row.addWidget(self.accent_badge)
        row.addWidget(self.accent_button)
        row.addWidget(self.text_badge)
        row.addStretch(1)
        return container

    def _build_font_preview(self) -> QtWidgets.QWidget:
        self.font_preview = FontPreview(FONT_PREVIEW_TEXT)
        container = QtWidgets.QWidget()
        row = apply_margins(QtWidgets.QVBoxLayout(container), margins=None)
        row.addWidget(self.font_preview)
        self.font_preview.heightChanged.connect(container.setMinimumHeight)
        self.font_preview.heightChanged.connect(self._refresh_font_layout)
        container.setMinimumHeight(self.font_preview.minimumHeight())
        return container

    def _refresh_font_layout(self, _height: int) -> None:
        section = self.form.sections[t('appearance')]
        section.form_layout.invalidate()
        section.layout().invalidate()
        section.updateGeometry()

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
        chosen = prompts.choose_color(self.window, current, t('choose_value0', value0=f'{settings_schema.label_for(key).lower()}'))
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

        self.window._run_action(t('saving_settings'), lambda: _run_save_settings(self.cfg, values), done)

    def reset(self) -> None:
        for key, value in settings_schema.read_settings(self.cfg).items():
            write_field(self.fields[key], value)
        self.update_color_rows()
        self.update_preview()
        self.update_font_preview()
        if hasattr(self, "draft_status"):
            self.update_dirty()
