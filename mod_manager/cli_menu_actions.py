from __future__ import annotations

import shlex
from dataclasses import dataclass

from .cli_commands import command_description
from .cli_navigation import check_navigation, split_command


@dataclass(frozen=True)
class MenuAction:
    key: str
    title: str
    description: str
    aliases: tuple[str, ...] = ()


MENUS = {
    "Main": (
        MenuAction("games", "Games", "Add, edit or select a game profile."),
        MenuAction("settings", "Settings", "Edit application preferences."),
        MenuAction("mods", "Mods", "Browse and manage mods for the active game."),
        MenuAction("presets", "Presets", "Save and manage sets of mods."),
        MenuAction("open-source", "Open mods source folder", "Open the folder containing downloaded mods."),
        MenuAction("open-game", "Open game mods folder", "Open the folder containing installed mods."),
        MenuAction("broken", "Broken links", "Find links whose sources no longer exist."),
        MenuAction("doctor", "Check configuration", "Check paths and metadata without changing files."),
    ),
    "Games": (
        MenuAction("add", "Add a game", "Enter a name and game-specific paths.", ("a",)),
        MenuAction("edit", "Edit a game", "Choose a game number, then edit its fields.", ("e",)),
        MenuAction("delete", "Delete a game", "Choose a profile to delete; source mod files are preserved.", ("d",)),
        MenuAction("select", "Select the active game", "Choose the game used for subsequent operations.", ("s",)),
        MenuAction("prepare", "Prepare folders", "Inspect active game folders; confirm before creating missing folders."),
    ),
    "Mods": (
        MenuAction("toggle", "Toggle selected mods", "Choose mod numbers on this page to install or uninstall."),
        MenuAction("install", "Install current page", "Install every inactive mod on this filtered page.", ("i",)),
        MenuAction("uninstall", "Uninstall current page", "Uninstall every active mod on this filtered page.", ("a",)),
        MenuAction("search", "Search mods", "Enter search text; empty text clears the search.", ("f", "find")),
        MenuAction("labels", "Labels", "Filter, assign or remove labels."),
        MenuAction("favorites", "Favorites", "Filter, add or remove favorites."),
        MenuAction("order", "Sort mods", "Choose a sort field and direction.", ("o",)),
        MenuAction("pages", "Pages", "Change page or reload the list."),
    ),
    "Presets": (
        MenuAction("save", "Save installed mods as a preset", "Enter a preset name; an existing name is updated.", ("s",)),
        MenuAction("toggle", "Toggle selected presets", "Choose preset numbers to apply or deactivate."),
        MenuAction("delete", "Delete selected presets", "Choose preset numbers; installed mod files are preserved.", ("d", "del")),
        MenuAction("pages", "Pages", "Change page or reload the list."),
    ),
    "Broken links": (
        MenuAction("remove", "Remove selected broken links", "Choose link numbers on this page."),
        MenuAction("all", "Remove all broken links on this page", "Remove only the broken links displayed on this page.", ("a",)),
        MenuAction("pages", "Pages", "Change page or reload the list."),
    ),
    "Settings": (
        MenuAction("edit", "Edit a setting", "Choose a setting number, then enter its value."),
        MenuAction("save", "Save changes", "Save staged changes and stay in Settings.", ("s",)),
        MenuAction("discard", "Discard changes", "Restore the last saved settings."),
    ),
    "Labels": (
        MenuAction("filter", "Filter by label", "Enter a label to show matching mods."),
        MenuAction("add", "Assign a label", "Choose mod numbers on the current page, then enter a label."),
        MenuAction("remove", "Remove a label", "Choose mod numbers, then enter the matching label to remove."),
        MenuAction("clear", "Clear the label filter", "Show mods with any label."),
    ),
    "Favorites": (
        MenuAction("filter", "Toggle favorites filter", "Switch between all mods and favorites only."),
        MenuAction("add", "Add selected mods to favorites", "Choose mod numbers on this page."),
        MenuAction("remove", "Remove selected mods from favorites", "Choose mod numbers on this page."),
    ),
    "Pages": (
        MenuAction("prev", "Previous page", "Stay on the current page if already at the start."),
        MenuAction("next", "Next page", "Stay on the current page if already at the end."),
        MenuAction("page", "Go to a page", "Enter a page number from the available range."),
        MenuAction("refresh", "Refresh the list", "Reload the current page."),
    ),
    "Unsaved changes": (
        MenuAction("save", "Save changes and leave", "Save staged settings before leaving."),
        MenuAction("discard", "Discard changes and leave", "Leave without saving staged settings."),
    ),
}

SHORTCUTS = {
    "Games": {"e1": "Edit game #1; e 1 and edit 1 also work.", "d1": "Delete game #1; d 1 and delete 1 also work.", "select 1": "Select game #1."},
    "Mods": {command: command_description(command) for command in ("/toggle", "/install", "/uninstall", "/search", "/l", "/l+", "/l-", "/label", "/favorite", "/favorite-add", "/favorite-remove", "/clear", "/order")},
    "Presets": {command: command_description(command) for command in ("/save", "/toggle", "/delete")},
    "Broken links": {"/remove": "Remove specified link numbers on this page.", "/all": "Remove all broken links on this page."},
}

PAGED_MENUS = {"Mods", "Presets", "Broken links"}
PAGE_COMMANDS = ("next", "prev", "page", "refresh")


def action_label(section: str, key: str) -> str:
    for number, action in enumerate(MENUS[section], 1):
        if action.key == key:
            return f"{number}) {action.title}"
    raise KeyError(key)


def print_actions(section: str, *, help_text: bool = False) -> None:
    print("\nActions")
    for number, action in enumerate(MENUS[section], 1):
        print(f"  {number}) {action.title}")
        if help_text:
            print(f"     {action.description}")
    print("  0) " + ("Exit" if section == "Main" else "Back"))
    print("  ?) Help")
    if help_text:
        print("Enter an action number first. Item numbers are requested in the next step.")
        print("/back returns one level; /home opens Main; /exit exits without saving an unfinished edit.")
        if section in SHORTCUTS:
            print("Shortcuts")
            for command, description in SHORTCUTS[section].items():
                print(f"  {command:<18} {description}")
        if section in PAGED_MENUS:
            print("  /next, /prev, /page 2, p2, /refresh also navigate the list.")


def parse_action(section: str, value: str) -> tuple[str, list[str]]:
    value = check_navigation(value).strip()
    if not value:
        return "", []
    if value == "0":
        return "back", []
    if value in {"?", "/", "/help", "help"}:
        return "help", []
    if value.isascii() and value.isdecimal():
        number = int(value)
        if 1 <= number <= len(MENUS[section]):
            return MENUS[section][number - 1].key, []
        destination = "Exit" if section == "Main" else "Back"
        raise ValueError(f"Choose an action from 1 to {len(MENUS[section])}, or 0 for {destination}.")
    parts = shlex.split(value.lstrip("/"))
    if not parts:
        return "help", []
    command, *arguments = parts
    command = command.lower()
    if section == "Games" and command[:1] in {"e", "d"} and command[1:].isascii() and command[1:].isdecimal():
        return ("edit" if command[0] == "e" else "delete"), [command[1:], *arguments]
    for action in MENUS[section]:
        if command in (action.key, *action.aliases):
            return action.key, arguments
    if section in PAGED_MENUS:
        command, arguments = split_command(value)
        allowed = set(PAGE_COMMANDS) | {name.lstrip("/") for name in SHORTCUTS.get(section, {})}
        if value.startswith("/") or not value[:1].isdecimal():
            if command in allowed:
                return command, arguments
    if section == "Games":
        raise ValueError(f"Unknown selection. To edit game #1, choose {action_label('Games', 'edit')}, then enter 1. Shortcut: edit 1 (also e1 or e 1).")
    raise ValueError(f"Unknown selection. Choose an action number in {section}; type ? for help.")


def completions(section: str) -> dict[str, str]:
    choices = {}
    for number, action in enumerate(MENUS[section], 1):
        choices[str(number)] = action.title
        choices[action.key] = action.description
    choices.update(SHORTCUTS.get(section, {}))
    choices.update({"0": "Exit" if section == "Main" else "Back", "?": "Help", "/help": "Explain this menu", "/back": "Return one level", "/home": "Open Main", "/exit": "Exit"})
    if section in PAGED_MENUS:
        choices.update({"/" + command: command_description("/" + command) for command in PAGE_COMMANDS})
    return choices
