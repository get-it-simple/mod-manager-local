from __future__ import annotations

MODS_TOOLBAR_SECTIONS = (
    ("filter", "Search", (
        ("search", "filter_apply", "Apply search, label and favorite filters"),
        ("clear", "filter_clear", "Clear search, label and favorite filters"),
        ("favorite_filter", "favorite", "Show favorite mods only"),
    )),
    ("order", "Order", ()),
    ("view", "View", (
        ("view_list", "list", "Show mods as a list"),
        ("view_tiles", "tiles", "Show mods as tiles"),
    )),
    ("import", "Import", ()),
)

MODS_ACTION_SECTIONS = (
    ("state", "Install", (
        ("install_page", "install", "Install all mods on the current page"),
        ("uninstall_page", "uninstall", "Uninstall all mods on the current page"),
    )),
    ("label", "Label", (
        ("add_label", "add", "Add label to selected mods"),
        ("remove_label", "remove", "Remove label from selected mods"),
        ("favorite_selected", "favorite", "Add or remove selected mods from favorites"),
    )),
    ("preview", "Preview", (
        ("set_image", "image", "Set preview image for selected mods from the clipboard or a file; confirm when applying to multiple mods"),
    )),
    ("page", "Page", ()),
)

PRESETS_TOOLBAR_SECTIONS = (
    ("preset", "Presets", (
        ("save", "save", "Save the installed mods as a preset"),
        ("toggle", "toggle", "Toggle selected presets"),
        ("delete", "delete", "Delete selected presets"),
    )),
    ("page", "Page", ()),
)

BROKEN_TOOLBAR_SECTIONS = (
    ("cleanup", "Broken links", (
        ("remove_selected", "remove", "Remove selected broken links"),
        ("remove_all", "delete", "Remove all broken links"),
    )),
)

GAMES_TOOLBAR_SECTIONS = (
    ("choose", "Game", (
        ("select", "submit", "Select the highlighted game"),
    )),
    ("profiles", "Profiles", (
        ("edit", "edit", "Edit the highlighted game profile"),
        ("delete", "delete", "Delete the highlighted game profile"),
    )),
)

SETTINGS_TOOLBAR_SECTIONS = (
    ("settings", "Settings", (
        ("save_settings", "save", "Save settings"),
    )),
)

SELECTION_ACTIONS = ("toggle_selected", "add_label", "remove_label", "favorite_selected", "set_image")


def section_keys(specs) -> tuple[str, ...]:
    return tuple(key for key, _title, _actions in specs)


def button_keys(specs) -> tuple[str, ...]:
    return tuple(key for _section, _title, actions in specs for key, _icon, _tooltip in actions)
