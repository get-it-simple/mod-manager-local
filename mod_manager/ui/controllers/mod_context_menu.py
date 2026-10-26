from __future__ import annotations

from ...i18n import t

from typing import Callable

from PySide6 import QtCore, QtGui, QtWidgets

from ...folder_actions import select_in_explorer
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
            self._action(menu, names, "install", t('install_action'), "install", window._install_selected_mods)
        if any(mod.installed for mod in mods):
            self._action(menu, names, "uninstall", t('uninstall_action'), "uninstall", window._uninstall_selected_mods)
        menu.addSeparator()
        favorite = all(name in window.current_mod_favorites for name in names)
        self._action(
            menu, names, "favorite", t('remove_from_favorites') if favorite else t('add_to_favorites'),
            "favorite_filled" if favorite else "favorite", window._toggle_favorite_selected,
        )
        self._action(menu, names, "add_label", t('assign_label'), "label_add", self._assign_label)
        self._action(menu, names, "set_image", t('set_preview_image'), "image", window._set_mod_image)
        if len(mods) == 1:
            menu.addSeparator()
            mod = mods[0]
            self._action(menu, names, "source", t('show_source_in_explorer'), "folder", lambda: select_in_explorer(mod.src))
            self._action(menu, names, "destination", t('show_game_location_in_explorer'), "folder_forward", lambda: select_in_explorer(mod.dest))
        menu.addSeparator()
        self._action(menu, names, "show_details", t('show_details'), "details_show", lambda: window._set_details_visible(True))

    def _assign_label(self) -> None:
        label, accepted = prompts.choose_text(self.window, t('text_bb1f28b586be'), t('label'))
        if accepted and label.strip():
            self.window._change_label_selected(label.strip())
