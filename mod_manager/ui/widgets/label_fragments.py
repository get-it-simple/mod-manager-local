from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ...i18n import t
from ...settings_schema import LABEL_TERMS_FIELD
from ..theme import tokens
from .flow_layout import FlowLayout
from .segmented_control import SegmentedControl
from .style_utils import apply_margins
from .label_rule_draft import FragmentDraft
from .label_fragment_view import FRAGMENT_MODES, FragmentsModel, FragmentListView, FragmentDelegate


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
        self.new_edit.setMinimumHeight(tokens.ICON_BUTTON_SIZE)
        self.new_edit.setPlaceholderText(t('new_fragment_enter_to_add_another'))
        self.new_edit.setAccessibleName(t('new_name_fragment'))
        self.new_edit.setToolTip(t('fragment_autosave_help'))
        self.new_edit.textChanged.connect(self._pending)
        self.new_edit.returnPressed.connect(self.add_pending)
        self.mode_control = SegmentedControl(
            (name, t(f"fragment_mode_{name}"), icon, t(f"{name}_fragment_help"))
            for name, icon in FRAGMENT_MODES.values()
        )
        self.mode_control.valueChanged.connect(self.set_pending_mode)
        self.next_id = QtWidgets.QLabel()
        self.next_id.setAccessibleName(t('new_fragment_number'))
        self.heading = QtWidgets.QLabel(LABEL_TERMS_FIELD.label)
        self.heading.setToolTip(LABEL_TERMS_FIELD.tooltip)
        input_group = QtWidgets.QWidget()
        input_group.setProperty("toolbarStretch", 1)
        input_row = apply_margins(QtWidgets.QHBoxLayout(input_group), margins=None, spacing=tokens.SPACE_SM)
        input_row.addWidget(self.next_id)
        input_row.addWidget(self.new_edit, 1)
        header = FlowLayout()
        header.setSpacing(tokens.SPACE_SM)
        header.addWidget(self.heading)
        header.addWidget(self.mode_control)
        header.addWidget(input_group)
        layout = apply_margins(QtWidgets.QVBoxLayout(self), margins=None, spacing=tokens.SPACE_SM)
        layout.addLayout(header)
        layout.addWidget(self.view)
        self.model.modelReset.connect(self._update_metrics)
        self._update_metrics()

    def _update_metrics(self) -> None:
        values = self.draft.exclusions if self.draft.pending_excluded else self.draft.terms
        self.next_id.setText(str(len(values) + 1))
        self.mode_control.set_value(FRAGMENT_MODES[self.draft.pending_excluded][0])
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
            self.setFixedHeight(self.layout().totalHeightForWidth(self.width()))
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

    def set_pending_mode(self, mode: str) -> None:
        excluded = mode == FRAGMENT_MODES[True][0]
        if excluded == self.draft.pending_excluded:
            return
        self.draft.pending_excluded = excluded
        self._update_metrics()
        self.changed.emit()
        self.new_edit.setFocus()

    def set_rule_mode(self, row: int, excluded: bool) -> None:
        if self.draft.rule_excluded(row) == excluded:
            if self.draft.editing == row:
                self.focus_edit()
            return
        if self.draft.editing != row and not self.start_edit(row):
            return
        self.draft.edited_excluded = excluded
        self.focus_edit()
        self.model.dataChanged.emit(self.model.index(row, 1), self.model.index(row, 1))
        self.changed.emit()

    def _edited(self, text: str) -> None:
        self.draft.edited = text
        if self.draft.editing is not None:
            index = self.model.index(self.draft.editing, 1)
            self.model.dataChanged.emit(index, index)
            self._fit_chips()
        self.changed.emit()

    def start_edit(self, row: int) -> bool:
        if self.draft.editing == row:
            return self.confirm_edit()
        target = self.draft.rules[row]
        if not self.confirm_edit(focus_new=False):
            return False
        row = self.draft.rules.index(target)
        self.draft.editing = row
        self.draft.edited_excluded, self.draft.edited = self.draft.rules[row]
        self.model.dataChanged.emit(self.model.index(row, 1), self.model.index(row, 2))
        self._open_edit()
        self.focus_edit()
        self.changed.emit()
        return True

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
            rules = self.draft.rules
            rules[self.draft.editing] = (self.draft.edited_excluded, self.draft.edited.strip())
            self.draft.set_rules(rules)
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
        self.draft.set_rules([*self.draft.rules, (self.draft.pending_excluded, self.draft.pending)])
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
        rules = self.draft.rules
        rules.pop(row)
        self.draft.set_rules(rules)
        if self.draft.editing == row:
            self.draft.editing = None
            self.draft.edited = ""
        elif self.draft.editing is not None and self.draft.editing > row:
            self.draft.editing -= 1
        self.model.endResetModel()
        self._open_edit()
        self.changed.emit()
