from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ...i18n import t
from .. import icons
from ..theme import tokens
from .label_rule_draft import FragmentDraft
from .label_fields import text_control_width


FRAGMENT_MODES = {False: ("include", "add"), True: ("exclude", "exclude")}


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
        if column == 1 and role in (QtCore.Qt.ToolTipRole, QtCore.Qt.AccessibleTextRole):
            text = self.draft.edited if self.draft.editing == row else self.draft.rules[row][1]
            return t("exclusion_rule" if self.draft.rule_excluded(row) else "inclusion_rule", value=text)
        if role in (QtCore.Qt.DisplayRole, QtCore.Qt.EditRole, QtCore.Qt.AccessibleTextRole):
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
            mode = delegate.mode_at(rect, event.position().toPoint())
            if mode is not None:
                delegate.fragments.set_rule_mode(index.row(), mode)
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

    def mode_rect(self, rect, excluded):
        chip = self.chip_rect(rect)
        left = chip.left() + int(excluded) * tokens.ICON_BUTTON_SIZE
        return QtCore.QRect(left, chip.top(), tokens.ICON_BUTTON_SIZE, chip.height())

    def mode_at(self, rect, point) -> bool | None:
        return next((mode for mode in FRAGMENT_MODES if self.mode_rect(rect, mode).contains(point)), None)

    def text_rect(self, rect, row):
        left = self.mode_rect(rect, True).right() + 1 + tokens.SPACE_SM + self.number_width(row)
        right = self.action_rect(rect, 2).left() - tokens.SPACE_SM
        chip = self.chip_rect(rect)
        return QtCore.QRect(left, chip.top(), max(0, right - left), chip.height())

    def _paint_modes(self, painter, option, row):
        active = self.fragments.draft.rule_excluded(row)
        for excluded, (_name, icon) in FRAGMENT_MODES.items():
            rect = self.mode_rect(option.rect, excluded)
            if excluded == active:
                painter.setBrush(option.palette.highlight())
                border = QtWidgets.QApplication.palette().highlight().color()
                painter.setPen(QtGui.QPen(border, tokens.BORDER_WIDTH))
                gap = tokens.SPACE_XS
                inset = rect.adjusted(gap, gap, -gap, -gap)
                painter.drawRoundedRect(inset, tokens.RADIUS_MD, tokens.RADIUS_MD)
            icon_rect = QtCore.QRect(QtCore.QPoint(), QtCore.QSize(tokens.ICON_SIZE, tokens.ICON_SIZE))
            icon_rect.moveCenter(rect.center())
            icons.standard_icon(icon).paint(painter, icon_rect)

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = self.chip_rect(option.rect)
        selected = bool(option.state & QtWidgets.QStyle.State_Selected)
        painter.setBrush(option.palette.highlight() if selected else option.palette.alternateBase())
        painter.setPen(option.palette.mid().color())
        painter.drawRoundedRect(rect, tokens.RADIUS_MD, tokens.RADIUS_MD)
        row = index.row()
        self._paint_modes(painter, option, row)
        painter.setPen(option.palette.text().color())
        text_rect = self.text_rect(option.rect, row)
        number_width = self.number_width(row)
        number_rect = QtCore.QRect(text_rect.x() - number_width, text_rect.y(), number_width, text_rect.height())
        painter.drawText(number_rect, QtCore.Qt.AlignVCenter, str(self.fragments.draft.rule_number(row)))
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
        width += tokens.ICON_BUTTON_SIZE * 4 + tokens.SPACE_SM * 2 + tokens.SPACE_XS * 2
        available = self.fragments.view.viewport().width() - self.fragments.view.spacing() * 2
        width = min(max(tokens.FRAGMENT_CHIP_MIN_WIDTH, width), max(1, available))
        height = max(tokens.FRAGMENT_CHIP_HEIGHT, self.fragments.new_edit.sizeHint().height() + tokens.SPACE_XS * 4)
        return QtCore.QSize(width, height)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(self.text_rect(option.rect, index.row()))

    def helpEvent(self, event, view, option, index):
        if event.type() != QtCore.QEvent.ToolTip or not index.isValid():
            return super().helpEvent(event, view, option, index)
        mode = self.mode_at(option.rect, event.pos())
        if mode is not None:
            name, _icon = FRAGMENT_MODES[mode]
            QtWidgets.QToolTip.showText(event.globalPos(), t(f"{name}_fragment_help"),
                                        view.viewport(), self.mode_rect(option.rect, mode))
            return True
        return super().helpEvent(event, view, option, index)

    def editorEvent(self, event, model, option, index):
        if event.type() == QtCore.QEvent.KeyPress:
            if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter, QtCore.Qt.Key_F2):
                self.fragments.start_edit(index.row())
                return True
            if event.key() == QtCore.Qt.Key_Delete:
                self.fragments.delete_fragment(index.row())
                return True
            if event.key() == QtCore.Qt.Key_Space:
                row = index.row()
                self.fragments.set_rule_mode(row, not self.fragments.draft.rule_excluded(row))
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
