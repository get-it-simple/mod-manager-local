from __future__ import annotations

from dataclasses import dataclass, field

from PySide6 import QtCore, QtWidgets

from ...labels import unique_names
from .. import icons
from ..theme import tokens
from .style_utils import apply_margins


@dataclass
class FragmentDraft:
    terms: list[str] = field(default_factory=list)
    pending: str = ""
    editing: int | None = None
    edited: str = ""

    def preview_terms(self) -> list[str]:
        terms = list(self.terms)
        if self.editing is not None:
            terms[self.editing] = self.edited
        if self.pending.strip():
            terms.append(self.pending)
        return [term.strip() for term in terms]

    def committed_terms(self) -> list[str]:
        self.validate_edit()
        return unique_names(self.preview_terms())

    def validate_edit(self) -> None:
        if self.editing is not None and not self.edited.strip():
            raise ValueError("Enter a nonempty fragment, or delete its row.")

    @property
    def unfinished(self) -> bool:
        return self.editing is not None or bool(self.pending)


class FragmentsModel(QtCore.QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.draft = FragmentDraft()

    def rowCount(self, parent=QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.draft.terms)

    def columnCount(self, parent=QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else 4

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        row, column = index.row(), index.column()
        if role in (QtCore.Qt.DisplayRole, QtCore.Qt.EditRole, QtCore.Qt.ToolTipRole, QtCore.Qt.AccessibleTextRole):
            if column == 0:
                return str(row + 1)
            if column == 1:
                return self.draft.edited if self.draft.editing == row else self.draft.terms[row]
            if column == 2:
                return "Save" if self.draft.editing == row else "Edit fragment"
            return "Delete fragment"
        return None

    def flags(self, index):
        flags = super().flags(index)
        if index.isValid() and index.column() == 1 and index.row() == self.draft.editing:
            flags |= QtCore.Qt.ItemIsEditable
        return flags


class FragmentDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, editor):
        super().__init__(editor.view)
        self.fragments = editor

    def paint(self, painter, option, index):
        if index.column() < 2:
            super().paint(painter, option, index)
            return
        button = QtWidgets.QStyleOptionButton()
        button.rect = option.rect.adjusted(tokens.SPACE_XS, tokens.SPACE_XS, -tokens.SPACE_XS, -tokens.SPACE_XS)
        button.state = QtWidgets.QStyle.State_Enabled if option.state & QtWidgets.QStyle.State_Enabled else QtWidgets.QStyle.State_None
        if option.state & QtWidgets.QStyle.State_MouseOver:
            button.state |= QtWidgets.QStyle.State_MouseOver
        saving = index.column() == 2 and index.row() == self.fragments.draft.editing
        button.text = "Save" if saving else ""
        button.icon = icons.standard_icon("save" if saving else "edit" if index.column() == 2 else "delete")
        button.iconSize = QtCore.QSize(tokens.ICON_SIZE, tokens.ICON_SIZE)
        self.fragments.view.style().drawControl(QtWidgets.QStyle.CE_PushButton, button, painter, self.fragments.view)

    def createEditor(self, parent, option, index):
        editor = QtWidgets.QLineEdit(parent)
        editor.setAccessibleName(f"Fragment {index.row() + 1}")
        editor.textChanged.connect(self.fragments._edited)
        return editor

    def setEditorData(self, editor, index):
        with QtCore.QSignalBlocker(editor):
            editor.setText(index.data(QtCore.Qt.EditRole))

    def setModelData(self, editor, model, index):
        pass

    def eventFilter(self, editor, event):
        if event.type() == QtCore.QEvent.KeyPress:
            if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
                self.fragments.confirm_edit()
                return True
            if event.key() == QtCore.Qt.Key_Escape:
                self.fragments.cancel_edit()
                return True
        if event.type() == QtCore.QEvent.FocusOut:
            return False
        return super().eventFilter(editor, event)


class FragmentEditor(QtWidgets.QWidget):
    changed = QtCore.Signal()
    validationFailed = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = FragmentsModel(self)
        self.view = QtWidgets.QTableView()
        self.view.setModel(self.model)
        self.view.setItemDelegate(FragmentDelegate(self))
        self.view.horizontalHeader().hide()
        self.view.verticalHeader().hide()
        self.view.verticalHeader().setDefaultSectionSize(tokens.TABLE_ROW_HEIGHT)
        self.view.setShowGrid(False)
        self.view.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.view.setMinimumWidth(0)
        self.view.setFixedHeight(tokens.LABEL_FRAGMENT_LIST_HEIGHT)
        header = self.view.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.view.setColumnWidth(0, tokens.LABEL_FRAGMENT_ID_WIDTH)
        self.view.setColumnWidth(2, tokens.LABEL_FRAGMENT_SAVE_WIDTH)
        self.view.setColumnWidth(3, tokens.ICON_BUTTON_SIZE)
        self.view.clicked.connect(self._activate)
        self.view.activated.connect(self._activate)
        self.new_edit = QtWidgets.QLineEdit()
        self.new_edit.setPlaceholderText("New fragment — Enter to add another")
        self.new_edit.setAccessibleName("New name fragment")
        self.new_edit.setToolTip("Enter a name fragment. Press Enter to add another, or Save to include this text.")
        self.new_edit.textChanged.connect(self._pending)
        self.new_edit.returnPressed.connect(self.add_pending)
        self.next_id = QtWidgets.QLabel()
        self.next_id.setAccessibleName("New fragment number")
        self.next_id.setFixedWidth(tokens.LABEL_FRAGMENT_ID_WIDTH)
        new_row = apply_margins(QtWidgets.QHBoxLayout(), margins=None, spacing=0)
        new_row.addWidget(self.next_id)
        new_row.addWidget(self.new_edit)
        layout = apply_margins(QtWidgets.QVBoxLayout(self), margins=None, spacing=tokens.SPACE_SM)
        layout.addWidget(self.view)
        layout.addLayout(new_row)
        self.model.modelReset.connect(self._update_metrics)
        self._update_metrics()

    def _update_metrics(self) -> None:
        self.next_id.setText(str(self.model.rowCount() + 1))
        id_width = max(tokens.LABEL_FRAGMENT_ID_WIDTH, self.fontMetrics().horizontalAdvance(self.next_id.text()) + tokens.SPACE_LG)
        self.next_id.setFixedWidth(id_width)
        self.view.setColumnWidth(0, id_width)
        save_width = self.fontMetrics().horizontalAdvance("Save") + tokens.ICON_SIZE + tokens.SPACE_LG * 2
        self.view.setColumnWidth(2, max(tokens.LABEL_FRAGMENT_SAVE_WIDTH, save_width))
        self.view.verticalHeader().setDefaultSectionSize(max(tokens.TABLE_ROW_HEIGHT, self.fontMetrics().height() + tokens.SPACE_LG))

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() in (QtCore.QEvent.FontChange, QtCore.QEvent.StyleChange) and hasattr(self, "next_id"):
            self._update_metrics()

    @property
    def draft(self) -> FragmentDraft:
        return self.model.draft

    def bind(self, draft: FragmentDraft) -> None:
        self._close_edit()
        self.model.beginResetModel()
        self.model.draft = draft
        self.model.endResetModel()
        with QtCore.QSignalBlocker(self.new_edit):
            self.new_edit.setText(draft.pending)
        self._open_edit()

    def _close_edit(self) -> None:
        if self.draft.editing is not None:
            self.view.closePersistentEditor(self.model.index(self.draft.editing, 1))

    def _open_edit(self) -> None:
        if self.draft.editing is not None:
            self.view.openPersistentEditor(self.model.index(self.draft.editing, 1))

    def focus_edit(self) -> None:
        if self.draft.editing is None:
            self.new_edit.setFocus()
        else:
            index = self.model.index(self.draft.editing, 1)
            self.view.scrollTo(index)
            editor = self.view.indexWidget(index)
            if editor is not None:
                editor.setFocus()

    def _pending(self, text: str) -> None:
        self.draft.pending = text
        self.changed.emit()

    def _edited(self, text: str) -> None:
        self.draft.edited = text
        self.changed.emit()

    def _activate(self, index) -> None:
        if index.column() == 2:
            if index.row() == self.draft.editing:
                self.confirm_edit()
            else:
                self.start_edit(index.row())
        elif index.column() == 3:
            self.delete_fragment(index.row())

    def start_edit(self, row: int) -> None:
        target = self.draft.terms[row]
        if not self.confirm_edit(focus_new=False):
            return
        row = next(index for index, term in enumerate(self.draft.terms) if term.casefold() == target.casefold())
        self.draft.editing = row
        self.draft.edited = self.draft.terms[row]
        self.model.dataChanged.emit(self.model.index(row, 1), self.model.index(row, 2))
        self._open_edit()
        self.focus_edit()
        self.changed.emit()

    def confirm_edit(self, focus_new: bool = True) -> bool:
        if self.draft.editing is not None:
            try:
                self.draft.validate_edit()
            except ValueError as error:
                self.validationFailed.emit(str(error))
                self.focus_edit()
                return False
            self._close_edit()
            self.model.beginResetModel()
            self.draft.terms[self.draft.editing] = self.draft.edited.strip()
            self.draft.terms = unique_names(self.draft.terms)
            self.draft.editing = None
            self.draft.edited = ""
            self.model.endResetModel()
            self.changed.emit()
        if focus_new:
            self.new_edit.setFocus()
        return True

    def add_pending(self) -> None:
        if not self.confirm_edit():
            return
        self.model.beginResetModel()
        self.draft.terms = unique_names([*self.draft.terms, self.draft.pending])
        self.draft.pending = ""
        self.model.endResetModel()
        self.new_edit.clear()
        self.changed.emit()
        self.new_edit.setFocus()

    def cancel_edit(self) -> None:
        self._close_edit()
        self.model.beginResetModel()
        self.draft.editing = None
        self.draft.edited = ""
        self.model.endResetModel()
        self.changed.emit()
        self.new_edit.setFocus()

    def delete_fragment(self, row: int) -> None:
        self._close_edit()
        self.model.beginResetModel()
        self.draft.terms.pop(row)
        if self.draft.editing == row:
            self.draft.editing = None
            self.draft.edited = ""
        elif self.draft.editing is not None and self.draft.editing > row:
            self.draft.editing -= 1
        self.model.endResetModel()
        self._open_edit()
        self.changed.emit()
