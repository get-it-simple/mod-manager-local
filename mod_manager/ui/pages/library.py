from __future__ import annotations

from PySide6 import QtCore, QtWidgets
from ... import settings_schema

from ..controllers import ACTIONS, SELECTION
from ..controllers.mod_context_menu import ModContextMenu
from ..models import (
    FavoriteDelegate,
    ModListView,
    ModTableModel,
    TileDelegate,
    configure_header,
)
from ..theme import tokens
from ..widgets import IconToolbar, PageControl, attach_completer, fixed_size_policy, select_box
from ..widgets.workspace import EmptyState
from ..widgets.detail_view import DetailPanel
from ..widgets.buttons import text_button
from ..widgets.style_utils import set_variant
from ..view_modes import MOD_ORDER_OPTIONS, order_label_for_key
from ..localization import system_action_text as _sys_str
from .toolbar_specs import MODS_ACTION_SECTIONS, MODS_TOOLBAR_SECTIONS, SELECTION_ACTIONS


def build_mods_toolbar(window) -> IconToolbar:
    toolbar = IconToolbar(window.mods_tab)
    toolbar.build(MODS_TOOLBAR_SECTIONS)

    import_section = toolbar.sections["import"]
    import_button = import_section.add_text_action("import_files", "Import files", "import", "Import mod files", window._import_mod_files)
    set_variant(import_button, "primary")
    import_section.add_action("import_folder", "folder", "Import a mod folder", window._import_mod_folder)

    window.search_box = window._filter_box("Search")
    window.label_filter_box = window._filter_box("Label")
    for box, width in ((window.search_box, tokens.SEARCH_MIN_WIDTH), (window.label_filter_box, tokens.LABEL_FILTER_MIN_WIDTH)):
        box.setMinimumWidth(width)
        box.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        box.setMinimumContentsLength(0)
    window.filter_boxes = (window.search_box, window.label_filter_box)
    filter_section = toolbar.sections["filter"]
    filter_section.add_widget(window.search_box, 2)
    filter_section.add_widget(window.label_filter_box, 1)
    window.favorite_filter_button = toolbar.button("favorite_filter")
    window.favorite_filter_button.setCheckable(True)

    window.order_box = select_box()
    window.order_box.setMinimumWidth(tokens.ORDER_MIN_WIDTH)
    window.order_box.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
    window.order_box.setMinimumContentsLength(0)
    window.order_box.addItems(list(MOD_ORDER_OPTIONS))
    window.order_box.setCurrentText(order_label_for_key(window.mod_sort_key))
    window.order_box.activated.connect(window._activate_mod_order)
    order_section = toolbar.sections["order"]
    order_section.add_widget(window.order_box)
    window.order_direction_button = order_section.add_action(
        "order_direction", "toggle", "Sort ascending", window._toggle_mod_order_direction
    )

    window.view_list_button = toolbar.button("view_list")
    window.view_tiles_button = toolbar.button("view_tiles")
    for button in (window.view_list_button, window.view_tiles_button):
        button.setCheckable(True)
    window._set_icon_button_checked(window.view_list_button, not window._is_tile_view())
    window._set_icon_button_checked(window.view_tiles_button, window._is_tile_view())

    toolbar.connect({
        "search": window._mods_search,
        "clear": window._mods_clear,
        "favorite_filter": window._toggle_favorite_filter,
        "view_list": lambda: window._set_view_mode("list"),
        "view_tiles": lambda: window._set_view_mode("tiles"),
    })
    window.registry.extend(ACTIONS, toolbar.buttons.values())
    toolbar.add_stretch()
    window._update_mod_order_direction_button()
    return toolbar


def build_mods_actions(window) -> IconToolbar:
    toolbar = IconToolbar(window.mods_tab)
    toolbar.build(MODS_ACTION_SECTIONS)
    toolbar.sections["state"].add_text_action("toggle_selected", "Toggle selected", "toggle", "Toggle selected mods")

    page_section = toolbar.sections["page"]
    page_section.add_action("prev_page", "back", "Previous mods page", lambda: window._change_mod_page(-1))
    window.page_control = page_section.add_widget(PageControl())
    window.page_control.pageRequested.connect(window._set_mod_page)
    window.page_label = window.page_control
    page_section.add_action("next_page", "forward", "Next mods page", lambda: window._change_mod_page(1))

    window.label_edit = QtWidgets.QLineEdit()
    window.label_edit.setPlaceholderText("Label")
    window.label_edit.setMaximumWidth(tokens.LABEL_EDIT_MAX_WIDTH)
    fixed_size_policy(window.label_edit)
    window.label_edit_model = QtCore.QStringListModel(window.label_edit)
    attach_completer(window.label_edit, window.label_edit_model)
    label_section = toolbar.sections["label"]
    label_section._actions_layout.insertWidget(0, window.label_edit)
    window.label_edit.setParent(label_section)

    toolbar.button("install_page").setAccessibleName(_sys_str("install"))
    toolbar.button("uninstall_page").setAccessibleName(_sys_str("uninstall"))

    toolbar.connect({
        "install_page": window._install_page,
        "uninstall_page": window._uninstall_page,
        "toggle_selected": window._toggle_selected_mods,
        "add_label": window._add_label_selected,
        "remove_label": window._remove_label_selected,
        "favorite_selected": window._toggle_favorite_selected,
        "set_image": window._set_mod_image,
    })
    window.registry.extend(ACTIONS, toolbar.buttons.values())
    for key in SELECTION_ACTIONS:
        button = toolbar.button(key)
        button.setEnabled(False)
        window.registry.add(SELECTION, button)
    toolbar.add_stretch()
    return toolbar


def build_mods(window) -> None:
    layout = window.mods_tab.body
    spec = next(spec for spec in settings_schema.all_specs() if spec.key == "mod_details_visible")
    window.details_button = text_button(spec.label, spec.tooltip, window._toggle_details, icon_name="details")
    window.details_button.setCheckable(True)
    window.details_button.setChecked(bool(window.cfg.get(spec.key, True)))
    window.mods_tab.header.addWidget(window.details_button)
    window.registry.add(ACTIONS, window.details_button)
    window.mods_toolbar = window._build_mods_toolbar()
    layout.addWidget(window.mods_toolbar)

    window.mods_model = ModTableModel(window.theme.palette.accent, window)
    window.mods_stack = QtWidgets.QStackedWidget()
    window.mods_table = QtWidgets.QTableView()
    window.mods_table.setModel(window.mods_model)
    window.mods_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
    window.mods_table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
    window.mods_table.setMouseTracking(True)
    window.mods_table.setAcceptDrops(True)
    window.mods_table.viewport().setAcceptDrops(True)
    window.mods_table.viewport().installEventFilter(window)
    configure_header(window.mods_table, ModTableModel.COLUMNS)
    window._apply_state_column_width()
    mods_header = window.mods_table.horizontalHeader()
    mods_header.setSectionsClickable(True)
    mods_header.sectionClicked.connect(window._sort_mods_by_section)
    window.mods_table.doubleClicked.connect(lambda _idx: window._toggle_selected_mods())
    window.mods_table.selectionModel().selectionChanged.connect(lambda _a, _b: window._on_mod_selection_changed())
    window.favorite_delegate = FavoriteDelegate(window.mods_table)
    window.favorite_delegate.favoriteToggled.connect(window._toggle_favorite_name)
    window.mods_table.setItemDelegateForColumn(1, window.favorite_delegate)

    window.tile_delegate = TileDelegate(window.cfg, window.theme.palette, window)
    window.tiles_view = ModListView()
    window.tiles_view.setModel(window.mods_model)
    window.tiles_view.setSelectionModel(window.mods_table.selectionModel())
    window.tiles_view.setItemDelegate(window.tile_delegate)
    window.tiles_view.setViewMode(QtWidgets.QListView.IconMode)
    window.tiles_view.setResizeMode(QtWidgets.QListView.Adjust)
    window.tiles_view.setMovement(QtWidgets.QListView.Static)
    window.tiles_view.setUniformItemSizes(True)
    window.tiles_view.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
    window.tiles_view.setMouseTracking(True)
    window.tiles_view.setAcceptDrops(True)
    window.tiles_view.viewport().setAcceptDrops(True)
    window.tiles_view.viewport().installEventFilter(window)
    window.tiles_view.zoomRequested.connect(window._zoom_tiles)
    window.tiles_view.doubleClicked.connect(lambda _idx: window._toggle_selected_mods())
    window.tile_delegate.favoriteToggled.connect(window._toggle_favorite_name)

    window.detail_scroll = DetailPanel()
    window.detail_frame = window.detail_scroll.frame
    window.detail_layout = window.detail_scroll.layout
    window.detail_scroll.setMinimumWidth(tokens.DETAIL_PANEL_MIN_WIDTH)
    window.tile_splitter = QtWidgets.QSplitter()
    window.tile_splitter.setHandleWidth(tokens.SPLITTER_WIDTH)
    window.tile_splitter.setChildrenCollapsible(False)
    window.mods_stack.addWidget(window.mods_table)
    window.mods_stack.addWidget(window.tiles_view)
    window.library_empty = EmptyState("No mods to show", "Import files or a folder, or clear the current filters.")
    window.mods_stack.addWidget(window.library_empty)
    window.tile_splitter.addWidget(window.mods_stack)
    window.tile_splitter.addWidget(window.detail_scroll)
    window.tile_splitter.setStretchFactor(0, tokens.TILE_LIST_STRETCH)
    window.tile_splitter.setStretchFactor(1, tokens.TILE_DETAIL_STRETCH)
    window.tile_splitter.splitterMoved.connect(lambda _pos, _index: window._save_tile_splitter_sizes())
    QtCore.QTimer.singleShot(tokens.IMMEDIATE_MS, window._restore_tile_splitter_sizes)

    layout.addWidget(window.tile_splitter, 1)

    window.mods_actions = window._build_mods_actions()
    layout.addWidget(window.mods_actions)
    window.mod_menu = ModContextMenu(window)
    window._show_mod_view()

