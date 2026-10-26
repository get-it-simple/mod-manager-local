from __future__ import annotations

from ...i18n import t

MODS_TOOLBAR_SECTIONS = (
    ("filter", t('search'), (
        ("search", "filter_apply", t('apply_search_label_and_favorite_filters')),
        ("clear", "filter_clear", t('clear_search_label_and_favorite_filters')),
        ("favorite_filter", "favorite", t('show_favorite_mods_only')),
    )),
    ("order", t('order'), ()),
    ("view", t('view'), (
        ("view_list", "list", t('show_mods_as_a_list')),
        ("view_tiles", "tiles", t('show_mods_as_tiles')),
    )),
    ("import", t('import'), ()),
)

MODS_ACTION_SECTIONS = (
    ("state", t('install_action'), (
        ("install_page", "install", t('install_all_mods_on_the_current_page')),
        ("uninstall_page", "uninstall", t('uninstall_all_mods_on_the_current_page')),
    )),
    ("label", t('label'), (
        ("add_label", "add", t('add_label_to_selected_mods')),
        ("remove_label", "remove", t('remove_label_from_selected_mods')),
        ("favorite_selected", "favorite", t('add_or_remove_selected_mods_from_favorites')),
    )),
    ("preview", t('preview'), (
        ("set_image", "image", t('set_preview_image_for_selected_mods_from_the_clipboard_or_a_file_confirm')),
    )),
    ("page", t('page'), ()),
)

PRESETS_TOOLBAR_SECTIONS = (
    ("preset", t('presets'), (
        ("save", "save", t('save_the_installed_mods_as_a_preset')),
        ("toggle", "toggle", t('toggle_selected_presets')),
        ("delete", "delete", t('delete_selected_presets')),
    )),
    ("page", t('page'), ()),
)

BROKEN_TOOLBAR_SECTIONS = (
    ("cleanup", t('broken_links'), (
        ("remove_selected", "remove", t('remove_selected_broken_links')),
        ("remove_all", "delete", t('remove_all_broken_links')),
    )),
)

GAMES_TOOLBAR_SECTIONS = (
    ("choose", t('game'), (
        ("select", "submit", t('select_the_highlighted_game')),
    )),
    ("profiles", t('profiles'), (
        ("edit", "edit", t('edit_the_highlighted_game_profile')),
        ("delete", "delete", t('delete_the_highlighted_game_profile')),
    )),
)

SETTINGS_TOOLBAR_SECTIONS = (
    ("settings", t('settings'), (
        ("save_settings", "save", t('save_settings')),
    )),
)

SELECTION_ACTIONS = ("install_selected", "uninstall_selected", "add_label", "remove_label", "favorite_selected", "set_image")


def section_keys(specs) -> tuple[str, ...]:
    return tuple(key for key, _title, _actions in specs)


def button_keys(specs) -> tuple[str, ...]:
    return tuple(key for _section, _title, actions in specs for key, _icon, _tooltip in actions)
