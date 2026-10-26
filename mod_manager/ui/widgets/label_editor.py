from __future__ import annotations

from ...i18n import t

from PySide6 import QtCore, QtGui, QtWidgets

from ...settings_schema import LABEL_NAME_FIELD, LABEL_MODE_FIELD, LABEL_TERMS_FIELD, LABEL_MEMBERS_FIELD
from ..theme import tokens
from .detail_view import DetailPanel
from .select import select_box
from .style_utils import apply_margins
from .toolbar import IconToolbar
from .completer import FullTextDelegate
from .label_fragments import FragmentEditor
from .label_lists import LabelListView, LabelMatchesModel, matching_mods_view
from .buttons import icon_button


class ModChoicesModel(QtCore.QAbstractListModel):
    checkedChanged = QtCore.Signal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.names: list[str] = []
        self.checked: set[str] = set()

    def set_choices(self, names: list[str], checked: set[str]) -> None:
        self.beginResetModel()
        self.names = list(names)
        self.checked = set(checked)
        self.endResetModel()

    def rowCount(self, parent=QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.names)

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        name = self.names[index.row()]
        if role in (QtCore.Qt.DisplayRole, QtCore.Qt.ToolTipRole):
            return name
        if role == QtCore.Qt.CheckStateRole:
            return QtCore.Qt.Checked if name in self.checked else QtCore.Qt.Unchecked
        return None

    def flags(self, index):
        return super().flags(index) | QtCore.Qt.ItemIsUserCheckable

    def setData(self, index, value, role=QtCore.Qt.EditRole) -> bool:
        if not index.isValid() or role != QtCore.Qt.CheckStateRole:
            return False
        checked = value == QtCore.Qt.Checked or value == QtCore.Qt.Checked.value
        name = self.names[index.row()]
        if checked:
            self.checked.add(name)
        else:
            self.checked.discard(name)
        self.dataChanged.emit(index, index, [role])
        self.checkedChanged.emit(name, checked)
        return True


class LabelEditor(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.list_view = LabelListView()
        self.list_model = QtGui.QStandardItemModel(self)
        self.list_view.setModel(self.list_model)
        self.details = DetailPanel()
        self.name_edit = QtWidgets.QLineEdit()
        self.mode_box = select_box()
        self.mode_box.addItems(LABEL_MODE_FIELD.choices)
        self.terms_edit = FragmentEditor()
        self.details.add_heading(t('label_settings'))
        form_host = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(form_host)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(tokens.SPACE_LG)
        form.setVerticalSpacing(tokens.SPACE_SM)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)
        for spec, widget in ((LABEL_NAME_FIELD, self.name_edit), (LABEL_MODE_FIELD, self.mode_box), (LABEL_TERMS_FIELD, self.terms_edit)):
            label = QtWidgets.QLabel(spec.label)
            label.setToolTip(spec.tooltip)
            widget.setToolTip(spec.tooltip)
            widget.setAccessibleName(spec.label)
            form.addRow(label, widget)
        self.form = form
        self.details.add_widget(form_host)
        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText(t('find_mods_in_the_lists_below'))
        self.search_edit.setToolTip(t('search_the_complete_mod_catalog_and_matching_mods_by_name'))
        self.details.add_widget(self.search_edit)
        self.manual_heading = QtWidgets.QLabel(LABEL_MEMBERS_FIELD.label)
        self.manual_heading.setToolTip(LABEL_MEMBERS_FIELD.tooltip)
        self.details.add_widget(self.manual_heading)
        self.manual_model = ModChoicesModel(self)
        self.manual_proxy = self._proxy(self.manual_model)
        self.manual_view = self._list(self.manual_proxy)
        self.manual_view.setToolTip(LABEL_MEMBERS_FIELD.tooltip)
        self.details.add_widget(self.manual_view)
        self.matches_heading = QtWidgets.QLabel()
        self.details.add_widget(self.matches_heading)
        self.matches_model = LabelMatchesModel(self)
        self.matches_proxy = self._proxy(self.matches_model)
        self.matches_view = matching_mods_view(self.matches_proxy)
        self.details.add_widget(self.matches_view)
        self.search_edit.textChanged.connect(self.manual_proxy.setFilterFixedString)
        self.search_edit.textChanged.connect(self.matches_proxy.setFilterFixedString)
        self.toolbar = IconToolbar()
        actions = self.toolbar.add_section("labels", t('labels'))
        actions.add_text_action("add", t('new_label'), "add", t('new_label'))
        actions.add_action("delete", "delete", t('delete_label'))
        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        self.retry = icon_button("reset", t("retry_label_save"))
        self.reload = icon_button("reset", t("reload_saved_labels"))
        self.retry.hide()
        self.reload.hide()
        status_row = apply_margins(QtWidgets.QHBoxLayout(), margins=None, spacing=tokens.SPACE_SM)
        status_row.addWidget(self.status, 1)
        status_row.addWidget(self.retry)
        status_row.addWidget(self.reload)
        self.splitter = QtWidgets.QSplitter()
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self.list_view)
        self.splitter.addWidget(self.details)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 3)
        self.splitter.setSizes([tokens.LABEL_LIST_DEFAULT_WIDTH, tokens.DEFAULT_WIDTH - tokens.LABEL_LIST_DEFAULT_WIDTH])
        layout = apply_margins(QtWidgets.QVBoxLayout(self), margins=None, spacing=tokens.SPACE_LG)
        layout.addWidget(self.splitter, 1)
        layout.addLayout(status_row)
        layout.addWidget(self.toolbar)

    def _proxy(self, model):
        proxy = QtCore.QSortFilterProxyModel(self)
        proxy.setSourceModel(model)
        proxy.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)
        return proxy

    def _list(self, model):
        view = QtWidgets.QListView()
        view.setModel(model)
        view.setItemDelegate(FullTextDelegate(view))
        view.setMinimumHeight(tokens.LABEL_EDITOR_LIST_HEIGHT)
        view.setUniformItemSizes(True)
        return view

    def set_automatic(self, automatic: bool) -> None:
        self.form.setRowVisible(self.terms_edit, automatic or self.terms_edit.draft.editing is not None)
        self.manual_heading.setVisible(not automatic)
        self.manual_view.setVisible(not automatic)
        self.matches_view.setColumnHidden(1, not automatic)
