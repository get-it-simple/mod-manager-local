from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from .select import fit_popup
from ..theme import tokens


class CompletionPopupFit(QtCore.QObject):
    def __init__(self, completer):
        super().__init__(completer)
        self.completer = completer
        self.timer = QtCore.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.fit)
        completer.popup().installEventFilter(self)

    def fit(self) -> None:
        anchor = self.completer.widget()
        if anchor is not None:
            fit_popup(self.completer.popup(), anchor)

    def eventFilter(self, watched, event):
        if event.type() in (QtCore.QEvent.Show, QtCore.QEvent.LayoutRequest):
            self.timer.start(tokens.IMMEDIATE_MS)
        return False


class FullTextDelegate(QtWidgets.QStyledItemDelegate):
    def helpEvent(self, event, view, option, index) -> bool:
        text = index.data(QtCore.Qt.DisplayRole)
        if text:
            QtWidgets.QToolTip.showText(event.globalPos(), str(text), view)
            return True
        return super().helpEvent(event, view, option, index)


def configure_completer(completer: QtWidgets.QCompleter | None) -> None:
    if completer is None:
        return
    completer.setCompletionMode(QtWidgets.QCompleter.PopupCompletion)
    completer.setFilterMode(QtCore.Qt.MatchContains)
    completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
    popup = completer.popup()
    if not isinstance(popup.itemDelegate(), FullTextDelegate):
        popup.setItemDelegate(FullTextDelegate(popup))
        completer.popup_fit = CompletionPopupFit(completer)


def configure_filter_box(box: QtWidgets.QComboBox) -> QtWidgets.QComboBox:
    box.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
    box.view().setItemDelegate(FullTextDelegate(box.view()))
    configure_completer(box.completer())
    return box


def attach_completer(line_edit: QtWidgets.QLineEdit, model: QtCore.QStringListModel) -> QtWidgets.QCompleter:
    completer = QtWidgets.QCompleter(model, line_edit)
    configure_completer(completer)
    line_edit.setCompleter(completer)
    return completer


def owns_event_source(line_edit: QtWidgets.QLineEdit, obj) -> bool:
    completer = line_edit.completer()
    return obj is line_edit or (completer is not None and obj is completer.popup())


def complete(line_edit: QtWidgets.QLineEdit) -> bool:
    completer = line_edit.completer()
    text = line_edit.text()
    if completer is None or not text:
        return False
    popup = completer.popup()
    index = popup.currentIndex() if popup is not None else None
    completion = index.data() if index is not None and index.isValid() else None
    if not completion:
        completer.setCompletionPrefix(text)
        completion = completer.currentCompletion()
    if not completion:
        return False
    line_edit.setText(completion)
    if popup is not None:
        popup.hide()
    return True
