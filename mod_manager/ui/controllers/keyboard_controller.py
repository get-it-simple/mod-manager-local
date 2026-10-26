from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ...i18n import t
from ...keyboard import COMMANDS, effective_combos, validate_bindings
from ..dialogs import prompts
from ..widgets.shortcut_editor import ShortcutEditor, display_combo


def key_sequence(combo: str) -> QtGui.QKeySequence:
    return QtGui.QKeySequence("+".join({"plus": "+", "minus": "-", "equal": "=", "win": "Meta", "escape": "Esc"}.get(part, part)
                                     for part in combo.split("+")))


class KeyboardController(QtCore.QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.shortcuts = []
        self.bindings = {}
        QtWidgets.QApplication.instance().installEventFilter(self)
        self.reload()

    def reload(self) -> None:
        bindings = validate_bindings(self.window.cfg.get("keyboard_shortcuts", {}))
        for shortcut in self.shortcuts:
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        self.shortcuts.clear()
        self.bindings = bindings
        for command in COMMANDS:
            binding = bindings[command.id]
            if binding["enabled"] and binding["combo"]:
                for combo in effective_combos(command, binding["combo"]):
                    shortcut = QtGui.QShortcut(key_sequence(combo), self.window)
                    shortcut.setAutoRepeat(False)
                    shortcut.activated.connect(lambda name=command.id: self.activate(name))
                    self.shortcuts.append(shortcut)
        self.refresh_hints()

    def text(self, command: str) -> str:
        binding = self.bindings[command]
        return display_combo(binding["combo"]) if binding["enabled"] and binding["combo"] else ""

    def refresh_hints(self) -> None:
        window = self.window
        targets = {"search": window.mods_toolbar.button("search"), "install": window.mods_actions.button("install_selected"),
                   "uninstall": window.mods_actions.button("uninstall_selected"), "details": window.details_button,
                   "import_files": window.mods_toolbar.button("import_files"), "import_folder": window.mods_toolbar.button("import_folder"),
                   "help": window.keyboard_help_button, "save": window.settings.toolbar.button("save_settings")}
        for command, button in targets.items():
            if button is not None:
                original = button.property("commandTooltip") or button.toolTip()
                button.setProperty("commandTooltip", original)
                shortcut = self.text(command)
                button.setToolTip(f"{original} ({shortcut})" if shortcut else original)
                if not button.text():
                    button.setAccessibleName(button.toolTip())

    def eventFilter(self, obj, event) -> bool:
        if event.type() != QtCore.QEvent.ShortcutOverride or not isinstance(obj, QtWidgets.QWidget):
            return False
        current = obj
        while current is not None:
            if isinstance(current, ShortcutEditor):
                event.accept()
                return False
            current = current.parentWidget()
        if obj.window() is self.window and self.window._editing_text():
            pressed = QtGui.QKeySequence(event.keyCombination())
            allowed = ("search", "save", "help", "refresh")
            if not any(pressed == key_sequence(self.bindings[name]["combo"])
                       and self.bindings[name]["enabled"] for name in allowed):
                event.accept()
        return False

    def activate(self, name: str) -> None:
        window = self.window
        app = QtWidgets.QApplication.instance()
        if window.busy or app.activeModalWidget() is not None or app.activeWindow() is not window:
            return
        command = next(command for command in COMMANDS if command.id == name)
        page = window.workspace.current_page
        if command.context == "library" and page != "library":
            return
        if command.context == "editor" and page not in ("labels", "settings"):
            return
        if window._editing_text() and name not in ("search", "save", "refresh", "help"):
            return
        actions = {
            "search": lambda: (window.search_box.lineEdit().setFocus(), window.search_box.lineEdit().selectAll()),
            "refresh": self.refresh_page,
            "save": lambda: window.labels_controller.save() if page == "labels" else window.settings.save(),
            "help": self.show_help,
            "back": window._nav_back, "forward": window._nav_forward,
            "zoom_in": lambda: window._zoom_tiles(1), "zoom_out": lambda: window._zoom_tiles(-1),
            "paste": window._handle_paste, "install": window._install_selected_mods,
            "uninstall": window._uninstall_selected_mods, "import_files": window._import_mod_files,
            "import_folder": window._import_mod_folder,
            "details": lambda: window._set_details_visible(not window.details_button.isChecked()),
            "view": lambda: window._set_view_mode("list" if window._is_tile_view() else "tiles"),
        }
        actions[name]()

    def refresh_page(self) -> None:
        window = self.window
        {"library": window.refresh_mods, "presets": window.refresh_presets, "cleanup": window.refresh_broken,
         "games": window.games.refresh_lists, "labels": window.labels_controller.activate,
         "settings": window.settings.update_dirty}[window.workspace.current_page]()

    def show_help(self) -> None:
        prompts.show_info(self.window, t("keyboard_shortcuts"), "\n".join(
            f"{t(command.label)}: {self.text(command.id) or t('disabled_shortcut')}" for command in COMMANDS))

    def shutdown(self) -> None:
        QtWidgets.QApplication.instance().removeEventFilter(self)
        for shortcut in self.shortcuts:
            shortcut.setEnabled(False)
