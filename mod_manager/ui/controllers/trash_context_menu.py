from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ...folder_actions import open_folder
from ...i18n import t


class TrashContextMenu(QtCore.QObject):
    def __init__(self, controller):
        super().__init__(controller)
        self.controller = controller
        self.view = controller.view
        self.menu = None
        self.revision = 0
        self.targets = tuple((target, view) for view in (self.view.table, self.view.tiles)
                             for target in (view, view.viewport()))
        for target, _view in self.targets:
            target.installEventFilter(self)
        self.view.model.modelAboutToBeReset.connect(self.close)

    def close(self):
        self.revision += 1
        menu, self.menu = self.menu, None
        if menu is not None:
            menu.close()
            menu.deleteLater()

    def shutdown(self):
        self.close()
        for target, _view in self.targets:
            target.removeEventFilter(self)
        self.targets = ()

    def eventFilter(self, obj, event):
        view = next((view for target, view in self.targets if target is obj), None)
        if view is None:
            return False
        if event.type() == QtCore.QEvent.Hide:
            self.close()
            return False
        if event.type() in (QtCore.QEvent.MouseButtonPress, QtCore.QEvent.MouseButtonRelease,
                            QtCore.QEvent.MouseButtonDblClick) and event.button() == QtCore.Qt.RightButton:
            return True
        if event.type() == QtCore.QEvent.ContextMenu:
            pos = (view.visualRect(view.currentIndex()).center()
                   if event.reason() == QtGui.QContextMenuEvent.Keyboard else obj.mapTo(view.viewport(), event.pos()))
            self.open(view, pos)
            return True
        return False

    def open(self, view, pos):
        self.close()
        index = view.indexAt(pos)
        if not index.isValid() or not self.view.isEnabled():
            return
        selection = view.selectionModel()
        if index.row() not in {value.row() for value in selection.selectedIndexes()}:
            selection.select(index, QtCore.QItemSelectionModel.ClearAndSelect | QtCore.QItemSelectionModel.Rows)
            selection.setCurrentIndex(index, QtCore.QItemSelectionModel.NoUpdate)
        entries = self.view.selected_entries()
        self.view.update_actions()
        self.menu = menu = QtWidgets.QMenu(self.view)
        revision = self.revision
        identifiers = tuple(entry.identifier for entry in entries)

        def invoke(callback, key):
            if revision != self.revision:
                return
            current = self.view.selected_entries()
            if tuple(entry.identifier for entry in current) != identifiers:
                return
            self.view.update_actions()
            if key in ("restore", "delete") and not self.view.toolbar.button(key).isEnabled():
                return
            self.close()
            callback()

        for key, title, icon, callback in (
                ("restore", t("trash_restore"), "reset", self.controller.restore),
                ("delete", t("trash_delete"), "delete", self.controller.delete_selected)):
            action = menu.addAction(self.controller.window._icon(icon), title)
            action.setIconVisibleInMenu(True)
            action.setData(key)
            action.setEnabled(self.view.toolbar.button(key).isEnabled())
            action.triggered.connect(lambda _checked=False, run=callback, name=key: invoke(run, name))
        if len(entries) == 1:
            entry = entries[0]
            folder = entry.path / "payload"
            action = menu.addAction(self.controller.window._icon("folder"), t("trash_open_folder"))
            action.setIconVisibleInMenu(True)
            action.setData("folder")
            action.setEnabled(folder.is_dir())
            action.triggered.connect(lambda: invoke(lambda: open_folder(str(folder), create=False), "folder"))
        menu.aboutToHide.connect(menu.deleteLater)
        menu.destroyed.connect(lambda: self._forget(menu))
        menu.popup(view.viewport().mapToGlobal(pos))

    def _forget(self, menu):
        if self.menu is menu:
            self.menu = None
