from __future__ import annotations

from ...i18n import t

from dataclasses import dataclass, field

from PySide6 import QtCore, QtGui, QtWidgets

from ...labels import unique_names
from ...settings_schema import LABEL_TERMS_FIELD
from .. import icons
from ..theme import tokens
from .style_utils import apply_margins
from .label_fields import text_control_width


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
            raise ValueError(t('enter_a_nonempty_fragment_or_delete_its_row'))

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
                return t('edit_fragment')
            return t('delete_fragment')
        return None

    def flags(self, index):
        flags = super().flags(index)
        if index.isValid() and index.column() == 1 and index.row() == self.draft.editing:
            flags |= QtCore.Qt.ItemIsEditable
        return flags


class FragmentListView(QtWidgets.QListView):
    def mouseReleaseEvent(self, event):
        index = self.indexAt(event.position().toPoint())
        if event.button() == QtCore.Qt.LeftButton and index.isValid():
            delegate = self.itemDelegate()
            rect = self.visualRect(index)
            if delegate.action_rect(rect, 1).contains(event.position().toPoint()):
                delegate.fragments.delete_fragment(index.row())
                event.accept()
                return
            self.setCurrentIndex(index)
            delegate.fragments.start_edit(index.row())
            event.accept()
            return
        super().mouseReleaseEvent(event)


class FragmentDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, editor):
        super().__init__(editor.view)
        self.fragments = editor

    def chip_rect(self, rect):
        return rect.adjusted(tokens.SPACE_XS, tokens.SPACE_XS, -tokens.SPACE_XS, -tokens.SPACE_XS)

    def action_rect(self, rect, offset):
        chip = self.chip_rect(rect)
        return QtCore.QRect(chip.right() - tokens.ICON_BUTTON_SIZE * offset, chip.top(), tokens.ICON_BUTTON_SIZE, chip.height())

    def number_width(self, row):
        return self.fragments.view.fontMetrics().horizontalAdvance(f"{row + 1}  ")

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = self.chip_rect(option.rect)
        selected = bool(option.state & QtWidgets.QStyle.State_Selected)
        painter.setBrush(option.palette.highlight() if selected else option.palette.alternateBase())
        painter.setPen(option.palette.mid().color())
        painter.drawRoundedRect(rect, tokens.RADIUS_MD, tokens.RADIUS_MD)
        painter.setPen(option.palette.text().color())
        text_rect = rect.adjusted(tokens.SPACE_SM, 0, -tokens.ICON_BUTTON_SIZE * 2, 0)
        painter.drawText(text_rect, QtCore.Qt.AlignVCenter, f"{index.row() + 1}")
        text_rect.adjust(self.number_width(index.row()), 0, -tokens.SPACE_SM, 0)
        text = index.data()
        if len(text) > tokens.FRAGMENT_CHIP_MAX_CHARS:
            text = text[:tokens.FRAGMENT_CHIP_MAX_CHARS - 1] + "…"
        painter.drawText(text_rect, QtCore.Qt.AlignVCenter, option.fontMetrics.elidedText(text, QtCore.Qt.ElideRight, text_rect.width()))
        for offset, icon_name in ((2, "edit"), (1, "delete")):
            icon_rect = self.action_rect(option.rect, offset)
            icon_rect = QtCore.QRect(icon_rect.center() - QtCore.QPoint(tokens.ICON_SIZE // 2, tokens.ICON_SIZE // 2), QtCore.QSize(tokens.ICON_SIZE, tokens.ICON_SIZE))
            icons.standard_icon(icon_name).paint(painter, icon_rect)
        painter.restore()

    def sizeHint(self, option, index):
        text = index.data()[:tokens.FRAGMENT_CHIP_MAX_CHARS] or "0"
        width = text_control_width(self.fragments.new_edit, text) + self.number_width(index.row())
        width += tokens.ICON_BUTTON_SIZE * 2 + tokens.SPACE_SM * 2 + tokens.SPACE_XS * 2
        available = self.fragments.view.viewport().width() - self.fragments.view.spacing() * 2
        width = min(max(tokens.FRAGMENT_CHIP_MIN_WIDTH, width), max(1, available))
        height = max(tokens.FRAGMENT_CHIP_HEIGHT, self.fragments.new_edit.sizeHint().height() + tokens.SPACE_XS * 4)
        return QtCore.QSize(width, height)

    def updateEditorGeometry(self, editor, option, index):
        rect = self.chip_rect(option.rect)
        rect.adjust(tokens.SPACE_SM + self.number_width(index.row()), 0, -tokens.ICON_BUTTON_SIZE * 2 - tokens.SPACE_SM, 0)
        editor.setGeometry(rect)

    def editorEvent(self, event, model, option, index):
        if event.type() == QtCore.QEvent.KeyPress:
            if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter, QtCore.Qt.Key_F2):
                self.fragments.start_edit(index.row())
                return True
            if event.key() == QtCore.Qt.Key_Delete:
                self.fragments.delete_fragment(index.row())
                return True
        return super().editorEvent(event, model, option, index)

    def createEditor(self, parent, option, index):
        editor = QtWidgets.QLineEdit(parent)
        editor.setAccessibleName(t('fragment_value0', value0=f'{index.row() + 1}'))
        editor.textChanged.connect(self.fragments._edited)
        return editor

    def setEditorData(self, editor, index):
        text = index.data(QtCore.Qt.EditRole)
        if editor.text() != text:
            with QtCore.QSignalBlocker(editor):
                editor.setText(text)

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
        self._fitting = False
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        self.setToolTip(LABEL_TERMS_FIELD.tooltip)
        self.setAccessibleName(LABEL_TERMS_FIELD.label)
        self.model = FragmentsModel(self)
        self.view = FragmentListView()
        self.view.setModel(self.model)
        self.view.setModelColumn(1)
        self.view.setItemDelegate(FragmentDelegate(self))
        self.view.setViewMode(QtWidgets.QListView.ListMode)
        self.view.setFlow(QtWidgets.QListView.LeftToRight)
        self.view.setWrapping(True)
        self.view.setResizeMode(QtWidgets.QListView.Adjust)
        self.view.setMovement(QtWidgets.QListView.Static)
        self.view.activated.connect(lambda index: self.start_edit(index.row()))
        self.view.setSpacing(tokens.SPACE_XS)
        self.view.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.view.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.view.setMinimumWidth(0)
        self.view.viewport().installEventFilter(self)
        self.new_edit = QtWidgets.QLineEdit()
        self.new_edit.setPlaceholderText(t('new_fragment_enter_to_add_another'))
        self.new_edit.setAccessibleName(t('new_name_fragment'))
        self.new_edit.setToolTip(t('fragment_autosave_help'))
        self.new_edit.textChanged.connect(self._pending)
        self.new_edit.returnPressed.connect(self.add_pending)
        self.next_id = QtWidgets.QLabel()
        self.next_id.setAccessibleName(t('new_fragment_number'))
        self.heading = QtWidgets.QLabel(LABEL_TERMS_FIELD.label)
        self.heading.setToolTip(LABEL_TERMS_FIELD.tooltip)
        new_row = apply_margins(QtWidgets.QHBoxLayout(), margins=None, spacing=tokens.SPACE_SM)
        new_row.addWidget(self.heading)
        new_row.addWidget(self.next_id)
        new_row.addWidget(self.new_edit, 1)
        layout = apply_margins(QtWidgets.QVBoxLayout(self), margins=None, spacing=tokens.SPACE_SM)
        layout.addLayout(new_row)
        layout.addWidget(self.view)
        self.model.modelReset.connect(self._update_metrics)
        self._update_metrics()

    def _update_metrics(self) -> None:
        self.next_id.setText(str(self.model.rowCount() + 1))
        self.next_id.setFixedWidth(self.next_id.fontMetrics().horizontalAdvance(self.next_id.text()))
        self.view.setVisible(bool(self.model.rowCount()))
        self._fit_chips()

    def _fit_chips(self) -> None:
        if self._fitting or not hasattr(self, "new_edit"):
            return
        self._fitting = True
        try:
            self.view.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            self.view.doItemsLayout()
            rows = self._chip_rows()
            if len(rows) > tokens.FRAGMENT_VISIBLE_ROWS:
                self.view.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
                self.view.doItemsLayout()
                rows = self._chip_rows()
            visible = rows[:tokens.FRAGMENT_VISIBLE_ROWS]
            height = visible[-1].bottom() - visible[0].top() + 1 if visible else 0
            height += self.view.spacing() * 2 + self.view.frameWidth() * 2
            self.view.setFixedHeight(height)
            self.view.doItemsLayout()
            if self.draft.editing is not None:
                self.view.scrollTo(self.model.index(self.draft.editing, 1))
            self.layout().invalidate()
            self.setFixedHeight(self.layout().sizeHint().height())
            self.updateGeometry()
        finally:
            self._fitting = False

    def _chip_rows(self) -> list[QtCore.QRect]:
        rows = {}
        for row in range(self.model.rowCount()):
            rect = self.view.visualRect(self.model.index(row, 1))
            rows[rect.top()] = rows.get(rect.top(), QtCore.QRect()).united(rect)
        return [rows[top] for top in sorted(rows)]

    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.Resize:
            self._fit_chips()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_chips()

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
        if self.draft.editing is not None:
            index = self.model.index(self.draft.editing, 1)
            self.model.dataChanged.emit(index, index)
            self._fit_chips()
        self.changed.emit()

    def start_edit(self, row: int) -> None:
        if self.draft.editing == row:
            self.confirm_edit()
            return
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
