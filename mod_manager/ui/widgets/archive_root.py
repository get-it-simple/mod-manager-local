from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from ...i18n import t
from ...imports import set_archive_root
from ..theme import tokens
from .buttons import text_button
from .style_utils import apply_margins


class ArchiveRootPicker(QtWidgets.QWidget):
    rootChanged = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.archive = None
        self.title = QtWidgets.QLabel(self)
        self.tree = QtWidgets.QTreeView(self)
        self.model = QtGui.QStandardItemModel(self)
        self.tree.setModel(self.model)
        self.tree.setHeaderHidden(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.apply = text_button(t("archive_root_use"), t("archive_root_help"), self.choose)
        self.reset = text_button(t("archive_root_reset"), t("archive_root_reset"), self.reset_root)
        actions = apply_margins(QtWidgets.QHBoxLayout(), spacing=tokens.SPACE_SM)
        actions.addWidget(self.title, 1)
        actions.addWidget(self.apply)
        actions.addWidget(self.reset)
        layout = apply_margins(QtWidgets.QVBoxLayout(self), spacing=tokens.SPACE_SM)
        layout.addLayout(actions)
        layout.addWidget(self.tree)
        self.tree.selectionModel().currentChanged.connect(self._selection_changed)

    def set_archive(self, archive) -> None:
        self.archive = archive
        enabled = bool(archive and archive.mode == "together" and archive.preserve_structure)
        self.setVisible(enabled)
        if not enabled:
            return
        self.title.setText(t("archive_root_current", path=archive.import_root.as_posix()))
        self.model.clear()
        root = QtGui.QStandardItem(archive.source_name or archive.name)
        root.setData(".", QtCore.Qt.UserRole)
        self.model.appendRow(root)
        branches = {Path("."): root}
        members = [member for unit in archive.units for member in unit.members]
        for path in sorted(set(members).union(archive.artwork)):
            parent = root
            for level, part in enumerate(path.parts):
                relative = Path(*path.parts[:level + 1])
                if relative not in branches:
                    item = QtGui.QStandardItem(part)
                    item.setToolTip(relative.as_posix())
                    if level < len(path.parts) - 1:
                        item.setData(relative.as_posix(), QtCore.Qt.UserRole)
                    parent.appendRow(item)
                    branches[relative] = item
                parent = branches[relative]
        self.tree.expandAll()
        selected = branches.get(archive.import_root, root)
        self.tree.setCurrentIndex(selected.index())
        self._selection_changed()

    def _selection_changed(self, *_args) -> None:
        self.apply.setEnabled(self.tree.currentIndex().data(QtCore.Qt.UserRole) is not None)

    def choose(self) -> None:
        relative = self.tree.currentIndex().data(QtCore.Qt.UserRole)
        if relative is not None and self.archive is not None:
            set_archive_root(self.archive, Path(relative))
            self.title.setText(t("archive_root_current", path=relative))
            self.rootChanged.emit()

    def reset_root(self) -> None:
        if self.archive is not None:
            set_archive_root(self.archive, Path("."))
            self.set_archive(self.archive)
            self.rootChanged.emit()
