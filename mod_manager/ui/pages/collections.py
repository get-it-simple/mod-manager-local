from __future__ import annotations

from ...i18n import t

from PySide6 import QtWidgets

from ..controllers import ACTIONS
from ..models import BrokenTableModel, PresetTableModel, configure_header
from ..widgets import IconToolbar, PageControl
from ..widgets.workspace import EmptyState, WorkspacePage
from ..widgets.item_feedback import AnimatedItemDelegate, ItemFeedback
from .toolbar_specs import BROKEN_TOOLBAR_SECTIONS, PRESETS_TOOLBAR_SECTIONS


def build_presets(window) -> None:
    window.presets_page = WorkspacePage(t('presets'), t('save_and_restore_sets_of_installed_mods'))
    layout = window.presets_page.body
    window.presets_model = PresetTableModel(window.theme.palette, window)
    window.presets_table = QtWidgets.QTableView()
    window.presets_table.setModel(window.presets_model)
    window.presets_table.setItemDelegate(AnimatedItemDelegate(window.presets_table))
    ItemFeedback(window.presets_table)
    window.presets_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
    window.presets_table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
    configure_header(window.presets_table, PresetTableModel.COLUMNS)
    window.presets_table.doubleClicked.connect(window._toggle_preset_at_index)
    window.presets_stack = QtWidgets.QStackedWidget()
    window.presets_stack.addWidget(window.presets_table)
    window.presets_empty = EmptyState(t('no_presets_yet'), t('install_the_mods_you_want_enter_a_preset_name_and_save_the_set_below'))
    window.presets_stack.addWidget(window.presets_empty)
    layout.addWidget(window.presets_stack, 1)

    window.presets_toolbar = IconToolbar(window.presets_page)
    window.presets_toolbar.build(PRESETS_TOOLBAR_SECTIONS)
    page_section = window.presets_toolbar.sections["page"]
    page_section.add_action("prev_page", "back", t('previous_presets_page'), lambda: window._change_preset_page(-1))
    window.preset_page_control = page_section.add_widget(PageControl())
    window.preset_page_control.pageRequested.connect(window._set_preset_page)
    window.preset_page_label = window.preset_page_control
    page_section.add_action("next_page", "forward", t('next_presets_page'), lambda: window._change_preset_page(1))

    window.preset_name = QtWidgets.QLineEdit()
    window.preset_name.setPlaceholderText(t('preset_name'))
    preset_section = window.presets_toolbar.sections["preset"]
    preset_section._actions_layout.insertWidget(0, window.preset_name)
    window.preset_name.setParent(preset_section)

    window.presets_toolbar.connect({
        "save": window._save_preset,
        "toggle": window._toggle_selected_presets,
        "delete": window._delete_selected_presets,
    })
    window.registry.extend(ACTIONS, window.presets_toolbar.buttons.values())
    window.presets_toolbar.add_stretch()
    layout.addWidget(window.presets_toolbar)


def build_broken(window) -> None:
    window.broken_page = WorkspacePage(t('cleanup'), t('remove_broken_managed_links_while_preserving_your_source_mods'))
    layout = window.broken_page.body
    window.broken_model = BrokenTableModel(window)
    window.broken_table = QtWidgets.QTableView()
    window.broken_table.setModel(window.broken_model)
    window.broken_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
    window.broken_table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
    configure_header(window.broken_table, BrokenTableModel.COLUMNS)
    window.broken_table.horizontalHeader().setStretchLastSection(True)
    window.broken_stack = QtWidgets.QStackedWidget()
    window.broken_stack.addWidget(window.broken_table)
    window.broken_empty = EmptyState(t('no_broken_links'), t('managed_links_for_this_game_are_ready_to_use'))
    window.broken_stack.addWidget(window.broken_empty)
    layout.addWidget(window.broken_stack, 1)
    window.broken_toolbar = IconToolbar(window.broken_page)
    window.broken_toolbar.build(BROKEN_TOOLBAR_SECTIONS)
    window.broken_toolbar.connect({
        "remove_selected": window._remove_selected_broken,
        "remove_all": window._remove_all_broken,
    })
    window.registry.extend(ACTIONS, window.broken_toolbar.buttons.values())
    window.broken_toolbar.add_stretch()
    layout.addWidget(window.broken_toolbar)
