from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ...i18n import t
from ...keyboard import COMMANDS, KEYS, MODIFIERS, default_bindings, normalize_combo
from ..theme import tokens
from .buttons import text_button
from .style_utils import apply_margins


def display_combo(combo: str) -> str:
    return "+".join({"plus": "+", "minus": "−", "equal": "=", "win": t('win')}.get(part, part.capitalize())
                    for part in combo.split("+") if part)


class ShortcutEditor(QtWidgets.QFrame):
    changed = QtCore.Signal()

    def __init__(self, combo: str = "", parent=None):
        super().__init__(parent)
        self._combo = ""
        self._before = ""
        self._syncing = False
        self.capture = QtWidgets.QLineEdit(self)
        self.capture.setReadOnly(True)
        self.capture.setPlaceholderText(t("press_shortcut"))
        self.capture.setToolTip(t("shortcut_capture_help"))
        self.capture.installEventFilter(self)
        layout = apply_margins(QtWidgets.QVBoxLayout(self), margins=None, spacing=tokens.SPACE_SM)
        layout.addWidget(self.capture)
        row = apply_margins(QtWidgets.QHBoxLayout(), spacing=tokens.SPACE_SM)
        self.modifiers = []
        for modifier in MODIFIERS:
            box = QtWidgets.QComboBox(self)
            box.addItem("—", "")
            box.addItem(modifier.capitalize(), modifier)
            box.setAccessibleName(modifier.capitalize())
            box.currentIndexChanged.connect(self._select)
            row.addWidget(box)
            self.modifiers.append(box)
        self.key = QtWidgets.QComboBox(self)
        self.key.addItem("—", "")
        for key in KEYS:
            self.key.addItem(display_combo(key), key)
        self.key.currentIndexChanged.connect(self._select)
        row.addWidget(self.key, 1)
        layout.addLayout(row)
        self.set_combo(combo)

    def combo(self) -> str:
        return self._combo

    def set_combo(self, combo: str) -> None:
        self._syncing = True
        self._combo = combo
        parts = combo.split("+")
        self.capture.setText(display_combo(combo))
        for box, modifier in zip(self.modifiers, MODIFIERS):
            box.setCurrentIndex(1 if modifier in parts else 0)
        self.key.setCurrentIndex(max(0, self.key.findData(next((part for part in parts if part not in MODIFIERS), ""))))
        self._syncing = False

    def _select(self, *_args) -> None:
        if self._syncing:
            return
        parts = [box.currentData() for box in self.modifiers if box.currentData()]
        if self.key.currentData():
            parts.append(self.key.currentData())
        self._combo = "+".join(parts)
        self.capture.setText(display_combo(self._combo))
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
        hint = QtWidgets.QLabel(t("keyboard_help"))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        for command in COMMANDS:
            row = QtWidgets.QWidget(self)
            row_layout = apply_margins(QtWidgets.QVBoxLayout(row), margins=None, spacing=tokens.SPACE_SM)
            enabled = QtWidgets.QCheckBox(t(command.label), row)
            enabled.setToolTip(t("shortcut_enabled"))
            editor = ShortcutEditor(parent=row)
            editor.setAccessibleName(t(command.label))
            enabled.toggled.connect(self.changed)
            editor.changed.connect(self.changed)
            row_layout.addWidget(enabled)
            row_layout.addWidget(editor)
            layout.addWidget(row)
            self.rows[command.id] = (editor, enabled)
        self.restore = text_button(t("restore_defaults"), t("restore_shortcuts_help"),
                                   lambda: self.set_values(default_bindings()), icon_name="reset")
        layout.addWidget(self.restore)
        self.set_values(values)

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
