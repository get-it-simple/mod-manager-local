from __future__ import annotations

from ...i18n import t

from PySide6 import QtCore, QtGui, QtWidgets

from ..theme import tokens
from ..widgets.archive_browser import ArchiveBrowser
from ..widgets.style_utils import apply_margins
from ..widgets.toolbar import IconToolbar


class ArchiveImportDialog(QtWidgets.QDialog):
    importRequested = QtCore.Signal()
    pasteRequested = QtCore.Signal()
    dropRequested = QtCore.Signal(object)
    closing = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t('import_mods_from_archives'))
        self.resize(*tokens.ARCHIVE_DIALOG_SIZE)
        self.setAcceptDrops(True)
        self.working = False
        self.browser = ArchiveBrowser(self)
        self.status = QtWidgets.QLabel(t('select_files_to_import_paste_or_drop_an_image_to_assign_a_preview'), self)
        self.status.setWordWrap(True)
        self.actions = IconToolbar(self)
        section = self.actions.add_section("import", t('import'))
        section.add_text_action("import", t('add'), "import", t('import_the_selected_mods_from_all_archives'), self.importRequested.emit)
        section.add_text_action("cancel", t('cancel_action'), "remove", t('cancel_without_importing'), self.reject)
        self.actions.add_stretch()
        for button in self.findChildren(QtWidgets.QPushButton):
            button.setAutoDefault(False)
        self.actions.button("import").setDefault(True)
        layout = apply_margins(QtWidgets.QVBoxLayout(self), margins=tokens.DETAIL_MARGIN, spacing=tokens.SPACE_LG)
        layout.addWidget(self.browser, 1)
        layout.addWidget(self.status)
        layout.addWidget(self.actions)
        QtGui.QShortcut(QtGui.QKeySequence.Paste, self, activated=self.pasteRequested.emit)
        self.browser.model.dataChanged.connect(self.update_import_enabled)
        self.browser.model.modelReset.connect(self.update_import_enabled)

    def update_import_enabled(self, *_args) -> None:
        selected = any(archive.mode == "together" or archive.selected for archive in self.browser.archives)
        self.actions.set_enabled("import", bool(selected) and not self.working)

    def set_working(self, working: bool) -> None:
        self.working = working
        self.browser.setEnabled(not working)
        self.actions.set_enabled("cancel", not working)
        self.update_import_enabled()

    def reject(self) -> None:
        if not self.working:
            self.closing.emit()
            super().reject()

    def accept(self) -> None:
        if not self.working:
            self.closing.emit()
            super().accept()

    def closeEvent(self, event) -> None:
        if self.working:
            event.ignore()
        else:
            self.closing.emit()
            super().closeEvent(event)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls() or event.mimeData().hasImage():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        self.dropRequested.emit(event.mimeData())
        event.acceptProposedAction()
