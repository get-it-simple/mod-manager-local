from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ...i18n import t
from .. import icons
from ..theme import tokens
from .label_rule_draft import FragmentDraft
from .label_fields import text_control_width


class FragmentsModel(QtCore.QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.draft = FragmentDraft()

    def rowCount(self, parent=QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.draft.rules)

    def columnCount(self, parent=QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else 4

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        row, column = index.row(), index.column()
        if role == QtCore.Qt.DecorationRole and column == 1:
            return icons.standard_icon("remove" if self.draft.rule_excluded(row) else "add")
        if role == QtCore.Qt.ToolTipRole:
            text = self.draft.edited if self.draft.editing == row else self.draft.rules[row][1]
            return t("exclusion_rule" if self.draft.rule_excluded(row) else "inclusion_rule", value=text)
        if role in (QtCore.Qt.DisplayRole, QtCore.Qt.EditRole, QtCore.Qt.ToolTipRole, QtCore.Qt.AccessibleTextRole):
            if column == 0:
                return str(self.draft.rule_number(row))
            if column == 1:
                return self.draft.edited if self.draft.editing == row else self.draft.rules[row][1]
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
            if delegate.mode_rect(rect).contains(event.position().toPoint()):
                delegate.fragments.toggle_rule(index.row())
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
        return self.fragments.view.fontMetrics().horizontalAdvance(f"{self.fragments.draft.rule_number(row)}  ")

    def mode_rect(self, rect):
        chip = self.chip_rect(rect)
        return QtCore.QRect(chip.left(), chip.top(), tokens.ICON_BUTTON_SIZE, chip.height())

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = self.chip_rect(option.rect)
        selected = bool(option.state & QtWidgets.QStyle.State_Selected)
        painter.setBrush(option.palette.highlight() if selected else option.palette.alternateBase())
        painter.setPen(option.palette.mid().color())
        painter.drawRoundedRect(rect, tokens.RADIUS_MD, tokens.RADIUS_MD)
        painter.setPen(option.palette.text().color())
        mode_rect = self.mode_rect(option.rect)
        icon_rect = QtCore.QRect(mode_rect.center() - QtCore.QPoint(tokens.ICON_SIZE // 2, tokens.ICON_SIZE // 2), QtCore.QSize(tokens.ICON_SIZE, tokens.ICON_SIZE))
        index.data(QtCore.Qt.DecorationRole).paint(painter, icon_rect)
        text_rect = rect.adjusted(tokens.ICON_BUTTON_SIZE + tokens.SPACE_SM, 0, -tokens.ICON_BUTTON_SIZE * 2, 0)
        painter.drawText(text_rect, QtCore.Qt.AlignVCenter, str(self.fragments.draft.rule_number(index.row())))
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
        width += tokens.ICON_BUTTON_SIZE * 3 + tokens.SPACE_SM * 2 + tokens.SPACE_XS * 2
        available = self.fragments.view.viewport().width() - self.fragments.view.spacing() * 2
        width = min(max(tokens.FRAGMENT_CHIP_MIN_WIDTH, width), max(1, available))
        height = max(tokens.FRAGMENT_CHIP_HEIGHT, self.fragments.new_edit.sizeHint().height() + tokens.SPACE_XS * 4)
        return QtCore.QSize(width, height)

    def updateEditorGeometry(self, editor, option, index):
        rect = self.chip_rect(option.rect)
        rect.adjust(tokens.ICON_BUTTON_SIZE + tokens.SPACE_SM + self.number_width(index.row()), 0, -tokens.ICON_BUTTON_SIZE * 2 - tokens.SPACE_SM, 0)
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


