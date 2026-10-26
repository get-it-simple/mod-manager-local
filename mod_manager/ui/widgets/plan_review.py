from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ...i18n import t
from ..theme import tokens
from .style_utils import apply_margins


class PlanTree(QtWidgets.QTreeView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.tree_model = QtGui.QStandardItemModel(self)
        self.setModel(self.tree_model)
        self.setHeaderHidden(True)
        self.setUniformRowHeights(True)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.setItemsExpandable(False)
        self.setExpandsOnDoubleClick(False)

    def set_rows(self, rows) -> None:
        self.tree_model.clear()
        branches = {}
        for parts in rows:
            parent = self.tree_model.invisibleRootItem()
            prefix = ()
            for part in parts:
                prefix += (str(part),)
                if prefix not in branches:
                    item = QtGui.QStandardItem(str(part))
                    item.setToolTip(str(part))
                    parent.appendRow(item)
                    branches[prefix] = item
                parent = branches[prefix]
        self.expandAll()


class PlanReview(QtWidgets.QDialog):
    def __init__(self, parent, title: str, rows, summary: str = ""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(*tokens.DIALOG_SIZE)
        layout = apply_margins(QtWidgets.QVBoxLayout(self), tokens.DETAIL_MARGIN, tokens.SPACE_LG)
        self.summary = QtWidgets.QLabel(summary)
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.tree = PlanTree(self)
        self.tree.set_rows(rows)
        layout.addWidget(self.tree, 1)
        buttons = QtWidgets.QDialogButtonBox(self)
        apply = buttons.addButton(t("apply_plan"), QtWidgets.QDialogButtonBox.AcceptRole)
        buttons.addButton(t("cancel_action"), QtWidgets.QDialogButtonBox.RejectRole)
        apply.setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
