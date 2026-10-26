from __future__ import annotations


COMMAND_HELP = {
    "mods": "Browse mods and manage installation, labels and favorites for the active game.",
    "presets": "Save and manage named sets of installed mods for the active game.",
    "settings": "Show settings or change application preferences. Edit game paths through games.",
    "games": "Add, edit, select and prepare game profiles shared with the GUI.",
    "open": "Open an existing source or game mods folder without creating it.",
    "broken": "Find and remove broken links in the game mods folder; preserve regular files.",
    "gui": "Launch the graphical interface. Requires PySide6.",
    "doctor": "Check configuration, folders, metadata and optional components without changing files.",
    "help": "Show help for a command and optional subcommand.",
}

ACTION_HELP = {
    "list": "List items for the active game. Indexes start at 1 on each page.",
    "search": "List mods whose names contain the supplied text.",
    "label": "List mods with the supplied label.",
    "page": "Show a page. Use the same filters and order when acting on its indexes.",
    "order": "List mods in the supplied order; prefix a mode with '-' for descending order.",
    "install": "Install every inactive mod on the selected page, respecting filters.",
    "uninstall": "Uninstall every active mod on the selected page, preserving source mods.",
    "toggle": "Install inactive selections and uninstall active selections. Indexes refer to the selected page.",
    "label-add": "Assign a label to selected mods on the current filtered page.",
    "label-remove": "Remove a matching label from selected mods on the current filtered page.",
    "favorite-add": "Mark selected mods as favorites for the active game.",
    "favorite-remove": "Remove selected mods from the active game's favorites.",
    "save": "Save the currently installed mods as a named preset. An existing name is updated.",
    "delete": "Delete selected presets or a game profile; source mod files are preserved.",
    "show": "Display application settings and the active game's values without saving.",
    "set": "Validate and save the supplied application settings. Omitted values are preserved.",
    "select": "Make a game profile active for future CLI and GUI operations.",
    "add": "Create and select a game profile. This does not create folders or import files.",
    "edit": "Update the supplied fields of an existing game profile.",
    "prepare": "Inspect the active game's folders. Create missing folders only with --create-dirs.",
    "remove": "Remove selected broken links, or all with --all. Regular files are preserved.",
}

NAVIGATION_HELP = {
    "/help": "Show commands and examples for this section",
    "/back": "Return to the previous menu (also 0)",
    "/home": "Return to the main menu",
    "/exit": "Exit without saving an unfinished edit",
    "/next": "Show the next page",
    "/prev": "Show the previous page",
    "/page": "Go to page N, for example /page 2",
    "/refresh": "Reload this list",
    "/clear": "Clear search, label and favorite filters",
}


def command_description(command: str) -> str:
    if command in NAVIGATION_HELP:
        return NAVIGATION_HELP[command]
    key = command.lstrip("/").split(" ", 1)[0]
    if key == "favorite":
        return "Toggle the favorites-only filter."
    aliases = {"l": "label", "l+": "label-add", "l-": "label-remove"}
    description = ACTION_HELP.get(aliases.get(key, key), "")
    if key == "search":
        description += " With no text, clear the search."
    return description
