from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ...i18n import t
from ...keyboard import COMMANDS, KEYS, default_bindings, normalize_combo
from ..theme import tokens
from .buttons import icon_button, text_button
from .style_utils import apply_margins, set_variant


def display_combo(combo: str) -> str:
    return "+".join({"plus": "+", "minus": "−", "equal": "=", "win": t('win')}.get(part, part.capitalize())
                    for part in combo.split("+") if part)


class ShortcutEditor(QtWidgets.QFrame):
    changed = QtCore.Signal()

    def __init__(self, combo: str = "", parent=None):
        super().__init__(parent)
        self._combo = ""
        self._before = ""
        set_variant(self, "shortcutField")
        self.command = QtWidgets.QCheckBox(self)
        self.command.setToolTip(t("shortcut_enabled"))
        self.capture = QtWidgets.QLineEdit(self)
        self.capture.setReadOnly(True)
        self.capture.setPlaceholderText(t("press_shortcut"))
        self.capture.setToolTip(t("shortcut_capture_help"))
        self.capture.installEventFilter(self)
        self.clear_button = icon_button("clear", t("clear_shortcut"), self.clear, self)
        layout = apply_margins(QtWidgets.QHBoxLayout(self), tokens.SPACE_SM, tokens.SPACE_SM)
        layout.addWidget(self.command)
        layout.addWidget(self.capture, 1)
        layout.addWidget(self.clear_button)
        self.setFocusProxy(self.capture)
        self.set_combo(combo)

    def combo(self) -> str:
        return self._combo

    def set_combo(self, combo: str) -> None:
        self._combo = combo
        self.capture.setText(display_combo(combo))
        self.clear_button.setEnabled(bool(combo))

    def clear(self) -> None:
        self.set_combo("")
        self.capture.setFocus()
        self.changed.emit()

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QtCore.QEvent.FocusIn:
            self._before = self._combo
        if event.type() == QtCore.QEvent.ShortcutOverride:
            event.accept()
            return True
        if event.type() != QtCore.QEvent.KeyPress:
            return super().eventFilter(watched, event)
        if event.key() == QtCore.Qt.Key_Escape:
            self.set_combo(self._before)
        elif event.key() in (QtCore.Qt.Key_Backspace, QtCore.Qt.Key_Delete):
            self.set_combo("")
        else:
            names = {QtCore.Qt.Key_Plus: "plus", QtCore.Qt.Key_Minus: "minus", QtCore.Qt.Key_Equal: "equal",
                     QtCore.Qt.Key_Escape: "escape", QtCore.Qt.Key_PageUp: "pageup", QtCore.Qt.Key_PageDown: "pagedown"}
            key = names.get(event.key(), QtGui.QKeySequence(event.key()).toString().lower().replace(" ", ""))
            if key not in KEYS:
                return True
            modifiers = [name for flag, name in (
                (QtCore.Qt.ControlModifier, "ctrl"), (QtCore.Qt.AltModifier, "alt"),
                (QtCore.Qt.ShiftModifier, "shift"), (QtCore.Qt.MetaModifier, "win"),
            ) if event.modifiers() & flag]
            self.set_combo(normalize_combo("+".join(modifiers + [key])))
        self.changed.emit()
        event.accept()
        return True


class ShortcutSettings(QtWidgets.QWidget):
    changed = QtCore.Signal()

    def __init__(self, values: dict, parent=None):
        super().__init__(parent)
        self.rows = {}
        layout = apply_margins(QtWidgets.QVBoxLayout(self), margins=None, spacing=tokens.SPACE_LG)
        self.toggle = QtWidgets.QToolButton(self)
        self.toggle.setText(t("shortcuts_label"))
        self.toggle.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
        self.toggle.setCheckable(True)
        self.toggle.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.arrow = QtWidgets.QToolButton(self)
        self.arrow.setArrowType(QtCore.Qt.DownArrow)
        self.arrow.setAccessibleName(t("expand_shortcuts"))
        self.arrow.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.arrow.clicked.connect(self.toggle.toggle)
        self.content = QtWidgets.QWidget(self)
        content_layout = apply_margins(QtWidgets.QVBoxLayout(self.content), margins=None, spacing=tokens.SPACE_SM)
        layout.addWidget(self.toggle)
        layout.addWidget(self.arrow)
        layout.addWidget(self.content)
        self.toggle.toggled.connect(self._expand)
        hint = QtWidgets.QLabel(t("keyboard_help"))
        hint.setWordWrap(True)
        content_layout.addWidget(hint)
        for command in COMMANDS:
            editor = ShortcutEditor(parent=self.content)
            enabled = editor.command
            enabled.setText(t(command.label))
            editor.setAccessibleName(t(command.label))
            editor.capture.setAccessibleName(t(command.label))
            enabled.toggled.connect(self.changed)
            editor.changed.connect(self.changed)
            content_layout.addWidget(editor)
            self.rows[command.id] = (editor, enabled)
        self.restore = text_button(t("restore_defaults"), t("restore_shortcuts_help"),
                                   lambda: self.set_values(default_bindings()), icon_name="reset")
        content_layout.addWidget(self.restore)
        self._expand(False)
        self.set_values(values)

    def _expand(self, expanded: bool) -> None:
        from ..motion import motion_for
        motion = motion_for(self)
        if motion:
            motion.expand(self.content, expanded)
        else:
            self.content.setVisible(expanded)
        self.arrow.setArrowType(QtCore.Qt.UpArrow if expanded else QtCore.Qt.DownArrow)
        self.arrow.setAccessibleName(t("collapse_shortcuts") if expanded else t("expand_shortcuts"))
        self.updateGeometry()

    def values(self) -> dict:
        return {key: {"combo": editor.combo(), "enabled": enabled.isChecked()}
                for key, (editor, enabled) in self.rows.items()}

    def set_values(self, values: dict) -> None:
        defaults = default_bindings()
        for key, (editor, enabled) in self.rows.items():
            value = values.get(key, defaults[key])
            editor.set_combo(value.get("combo", ""))
            enabled.setChecked(value.get("enabled", True))
        self.changed.emit()
