from __future__ import annotations

from typing import Callable

from PySide6 import QtCore, QtGui, QtWidgets

from ...folder_actions import select_in_explorer
from ...labels import AUTOMATIC, ResolvedLabels, label_names
from ..dialogs import prompts


class ModContextMenu(QtCore.QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.menu: QtWidgets.QMenu | None = None
        self._revision = 0
        self._targets = tuple((target, view) for view in (window.mods_table, window.tiles_view) for target in (view, view.viewport()))
        for target, _view in self._targets:
            target.installEventFilter(self)
        window.mods_model.modelAboutToBeReset.connect(self.close)
        window.runner.busyChanged.connect(self._busy_changed)

    def _busy_changed(self, busy: bool) -> None:
        if busy:
            self.close()

    def close(self) -> None:
        self._revision += 1
        menu, self.menu = self.menu, None
        if menu is not None:
            menu.close()
            menu.deleteLater()

    def shutdown(self) -> None:
        self.close()
        for target, _view in self._targets:
            target.removeEventFilter(self)
        self._targets = ()

    def _hidden(self, menu: QtWidgets.QMenu) -> None:
        if self.menu is menu:
            self.menu = None
        menu.deleteLater()

    def eventFilter(self, obj, event) -> bool:
        view = next((view for target, view in self._targets if obj is target), None)
        if view is None:
            return super().eventFilter(obj, event)
        if event.type() in (QtCore.QEvent.MouseButtonPress, QtCore.QEvent.MouseButtonRelease, QtCore.QEvent.MouseButtonDblClick):
            if event.button() == QtCore.Qt.RightButton:
                event.accept()
                return True
        if event.type() == QtCore.QEvent.ContextMenu:
            if event.reason() == QtGui.QContextMenuEvent.Keyboard:
                pos = view.visualRect(view.currentIndex()).center()
            else:
                pos = obj.mapTo(view.viewport(), event.pos())
            self.open(view, pos)
            event.accept()
            return True
        return super().eventFilter(obj, event)

    def open(self, view, pos: QtCore.QPoint) -> None:
        self.close()
        window = self.window
        if window.busy or not window._is_mods_tab_active() or view is not window._current_mod_view():
            return
        index = view.indexAt(pos)
        if not index.isValid():
            return
        selected = index.row() in window._selected_rows(view)
        names = tuple(window._selected_mod_names()) if selected else (window.current_mods_shown[index.row()].name,)
        self.menu = menu = QtWidgets.QMenu(window)
        menu.setToolTipsVisible(True)
        menu.aboutToHide.connect(lambda: self._hidden(menu))
        self._populate(menu, names)
        menu.popup(view.viewport().mapToGlobal(pos))

    def _action(
        self, menu: QtWidgets.QMenu, names: tuple[str, ...], key: str,
        text: str, icon: str, callback: Callable,
    ) -> QtGui.QAction:
        action = menu.addAction(self.window._icon(icon), text)
        action.setData(key)
        action.setProperty("iconName", icon)
        action.setIconVisibleInMenu(True)
        revision = self._revision
        action.triggered.connect(lambda _checked=False: self._invoke(revision, names, callback))
        return action

    def _invoke(self, revision: int, names: tuple[str, ...], callback: Callable) -> None:
        window = self.window
        if revision != self._revision or window.busy or not window._is_mods_tab_active():
            return
        if not set(names).issubset(mod.name for mod in window.current_mods_shown):
            return
        self.close()
        window._select_mod_names(list(names))
        callback()

    def _populate(self, menu: QtWidgets.QMenu, names: tuple[str, ...]) -> None:
        window = self.window
        mods = [mod for mod in window.current_mods_shown if mod.name in names]
        if any(not mod.installed for mod in mods):
            self._action(menu, names, "install", "Install", "install", window._install_selected_mods)
        if any(mod.installed for mod in mods):
            self._action(menu, names, "uninstall", "Uninstall", "uninstall", window._uninstall_selected_mods)
        if len(names) > 1:
            self._action(menu, names, "toggle", "Toggle selected", "toggle", window._toggle_selected_mods)
        menu.addSeparator()
        favorite = all(name in window.current_mod_favorites for name in names)
        self._action(
            menu, names, "favorite", "Remove from favorites" if favorite else "Add to favorites",
            "favorite_filled" if favorite else "favorite", window._toggle_favorite_selected,
        )
        self._action(menu, names, "add_label", "Assign label…", "label_add", self._assign_label)
        remove_menu = menu.addMenu(window._icon("label_remove"), "Remove label")
        remove_menu.menuAction().setData("remove_label")
        remove_menu.menuAction().setIconVisibleInMenu(True)
        labels = sorted({label for name in names for label in label_names(window.current_mod_labels, name)})
        if isinstance(window.current_mod_labels, ResolvedLabels):
            labels = [label for label in labels if window.current_mod_labels.state.definitions[label].mode != AUTOMATIC]
        remove_menu.setEnabled(bool(labels))
        for label in labels:
            self._action(
                remove_menu, names, "remove_label", label, "label_remove",
                lambda label=label: window._change_label_selected(label, remove=True),
            )
        self._action(menu, names, "manage_labels", "Manage labels…", "label_add", lambda: window._navigate("labels"))
        self._action(menu, names, "set_image", "Set preview image…", "image", window._set_mod_image)
        if len(mods) == 1:
            menu.addSeparator()
            mod = mods[0]
            self._action(menu, names, "source", "Show source in Explorer", "folder", lambda: select_in_explorer(mod.src))
            self._action(menu, names, "destination", "Show game location in Explorer", "folder_forward", lambda: select_in_explorer(mod.dest))
        menu.addSeparator()
        self._action(menu, names, "show_details", "Show details", "details_show", lambda: window._set_details_visible(True))

    def _assign_label(self) -> None:
        label, accepted = prompts.choose_text(self.window, "Assign label", "Label", self.window.label_edit.text())
        if accepted and label.strip():
            self.window._change_label_selected(label.strip())
