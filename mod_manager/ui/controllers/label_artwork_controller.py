from __future__ import annotations

from PySide6 import QtCore, QtGui

from ...i18n import t
from ..dialogs import prompts
from ..label_artwork import import_label_icon
from ..image_source import clipboard_source


class LabelArtworkController(QtCore.QObject):
    def __init__(self, labels):
        super().__init__(labels)
        self.labels = labels
        editor = labels.editor.artwork
        editor.chooseRequested.connect(self.choose)
        editor.removeRequested.connect(self.remove)
        editor.displayChanged.connect(self.set_display)

    def available(self):
        labels = self.labels
        return (labels.profile_id in labels.drafts and not labels._loading and labels.selected in labels.state.definitions
                and not labels.window.busy and not labels.window.runner.barrier_pending
                and labels.window.workspace.current_page == "labels")

    def paste(self):
        if not self.available():
            return False
        try:
            source = clipboard_source(strict=True)
        except (OSError, ValueError) as error:
            self.labels.editor.status.setText(str(error))
            return True
        if source is None:
            return False
        try:
            self.apply(str(source.path))
        finally:
            source.close()
        return True

    def choose(self):
        labels = self.labels
        if not self.available():
            return
        try:
            source = clipboard_source()
        except OSError as error:
            labels.editor.status.setText(str(error))
            return
        if source is not None:
            try:
                if self.apply(str(source.path)):
                    return
            finally:
                source.close()
        formats = " ".join("*." + bytes(value).decode("ascii") for value in QtGui.QImageReader.supportedImageFormats())
        path = prompts.choose_open_file(labels.window, t("label_icon"), t("label_icon_files", formats=formats))
        if not path:
            return
        self.apply(path)

    def apply(self, path):
        labels = self.labels
        if not self.available():
            return
        try:
            reference = import_label_icon(path)
        except (OSError, ValueError) as error:
            labels.editor.status.setText(str(error))
            return
        labels.state.definitions[labels.selected].icon = reference
        self._changed()
        return True

    def remove(self):
        labels = self.labels
        if labels._loading or not labels.selected:
            return
        definition = labels.state.definitions[labels.selected]
        definition.icon = ""
        definition.icon_only = False
        self._changed()

    def set_display(self, icon_only):
        labels = self.labels
        if labels._loading or not labels.selected:
            return
        labels.state.definitions[labels.selected].icon_only = icon_only
        self._changed()

    def _changed(self):
        labels = self.labels
        labels.editor.artwork.set_definition(labels.state.definitions[labels.selected])
        labels._preview()
