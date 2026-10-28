from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from . import accent as accent_module
from . import colors
from .stylesheet import build_stylesheet

PALETTE_ROLES = (
    ("Window", "bg"),
    ("WindowText", "fg"),
    ("Base", "panel"),
    ("AlternateBase", "alt_panel"),
    ("Text", "fg"),
    ("Button", "button"),
    ("ButtonText", "fg"),
    ("ToolTipBase", "tooltip_bg"),
    ("ToolTipText", "tooltip_fg"),
)

TEXT_ROLES = ("WindowText", "Text", "ButtonText", "ToolTipText")
_APPLICATION_BASE_FONT: QtGui.QFont | None = None


def custom_color(cfg: dict, mode_key: str, color_key: str) -> str | None:
    if colors.normalize_color_mode(cfg.get(mode_key)) != "custom":
        return None
    return colors.normalize_hex(cfg.get(color_key))


def custom_accent(cfg: dict) -> str | None:
    return custom_color(cfg, "gui_accent_color_mode", "gui_accent_color")


def custom_text(cfg: dict) -> str | None:
    return custom_color(cfg, "gui_text_color_mode", "gui_text_color")


class ThemeManager(QtCore.QObject):
    changed = QtCore.Signal()

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._system_palette: QtGui.QPalette | None = None
        self._palette = colors.build_palette("light")
        self._stylesheet = ""
        self._applying = False
        global _APPLICATION_BASE_FONT
        app = QtWidgets.QApplication.instance()
        if _APPLICATION_BASE_FONT is None:
            _APPLICATION_BASE_FONT = QtGui.QFont(app.font()) if app is not None else QtGui.QFont()
        self._base_font = QtGui.QFont(_APPLICATION_BASE_FONT)

    @property
    def palette(self) -> colors.Palette:
        return self._palette

    @property
    def stylesheet(self) -> str:
        return self._stylesheet

    @property
    def base_font(self) -> QtGui.QFont:
        return QtGui.QFont(self._base_font)

    @property
    def system_accent(self) -> str:
        return accent_module.system_accent(self.system_palette())

    @property
    def mode(self) -> str:
        return colors.normalize_mode(self.cfg.get("gui_theme"))

    @property
    def is_applying(self) -> bool:
        return self._applying

    def start(self) -> None:
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.paletteChanged.connect(self.on_system_appearance_changed)
        style_hints = QtGui.QGuiApplication.styleHints()
        if hasattr(style_hints, "colorSchemeChanged"):
            style_hints.colorSchemeChanged.connect(self.on_system_appearance_changed)
        self.apply()

    def on_system_appearance_changed(self, *_args) -> None:
        if self._applying:
            return
        self._system_palette = None
        self.apply()

    def system_palette(self) -> QtGui.QPalette:
        if self._system_palette is None:
            app = QtWidgets.QApplication.instance()
            self._system_palette = QtGui.QPalette(app.palette() if app else QtGui.QPalette())
        return QtGui.QPalette(self._system_palette)

    def resolve(self) -> colors.Palette:
        source = self.system_palette()
        mode = accent_module.resolve_mode(self.cfg.get("gui_theme"), source)
        accent = custom_accent(self.cfg) or accent_module.system_accent(source)
        return colors.build_palette(mode, accent, custom_text(self.cfg))

    def qt_palette(self, theme: colors.Palette) -> QtGui.QPalette:
        source = self.system_palette()
        palette = source if self.mode == "system" else QtGui.QPalette()
        if self.mode != "system":
            for role_name, field in PALETTE_ROLES:
                palette.setColor(getattr(QtGui.QPalette, role_name), QtGui.QColor(getattr(theme, field)))
        palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor(theme.accent))
        palette.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor(theme.accent_text))
        text_override = custom_text(self.cfg)
        if text_override:
            for role_name in TEXT_ROLES:
                palette.setColor(getattr(QtGui.QPalette, role_name), QtGui.QColor(text_override))
        return palette

    def apply(self) -> colors.Palette:
        self._applying = True
        try:
            theme = self.resolve()
            self._palette = theme
            self._stylesheet = build_stylesheet(theme)
            app = QtWidgets.QApplication.instance()
            if app is not None:
                app.setPalette(self.qt_palette(theme))
                app.setFont(build_font(self.cfg, self._base_font) or QtGui.QFont(self._base_font))
                app.setStyleSheet(self._stylesheet)
        finally:
            self._applying = False
        self.changed.emit()
        return self._palette


def build_font(cfg: dict, current: QtGui.QFont) -> QtGui.QFont | None:
    family = str(cfg.get("gui_font_family") or "").strip()
    try:
        size = int(cfg.get("gui_font_size") or 0)
    except (TypeError, ValueError):
        size = 0
    if not family and size <= 0:
        return None
    font = QtGui.QFont(current)
    if family:
        font.setFamily(family)
    if size > 0:
        font.setPointSize(size)
    return font
