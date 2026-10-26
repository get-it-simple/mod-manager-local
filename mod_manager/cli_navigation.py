from __future__ import annotations

import shlex

from .cli_commands import NAVIGATION_HELP


class MenuNavigation(Exception):
    def __init__(self, target: str):
        self.target = target
        super().__init__(target)


def check_navigation(value: str) -> str:
    command = value.strip().lower()
    if command in {"/back", "/home", "/exit"}:
        raise MenuNavigation(command[1:])
    return value


def split_command(value: str) -> tuple[str, list[str]]:
    value = check_navigation(value).strip()
    if value == "/":
        return "help", []
    if value.startswith("/"):
        value = value[1:]
    parts = shlex.split(value)
    if not parts:
        return "", []
    command, *arguments = parts
    original_command = command
    command = command.lower()
    if command.startswith("l:"):
        return "l", [original_command[2:], *arguments]
    if command.startswith("s:"):
        return "save", [original_command[2:], *arguments]
    if command.startswith("p") and command[1:].isascii() and command[1:].isdecimal():
        return "page", [command[1:]]
    aliases = {"f": "search", "find": "search", "o": "order", "i": "install", "a": "uninstall", "s": "save", "d": "delete", "del": "delete", "clear": "clear"}
    if command[0].isdecimal():
        return "toggle", [command, *arguments]
    return aliases.get(command, command), arguments


def navigation_commands(*, paged: bool = False, mods: bool = False) -> list[str]:
    commands = ["/help", "/back", "/home", "/exit"]
    if paged:
        commands.extend(["/next", "/prev", "/page", "/refresh"])
    if mods:
        commands.append("/clear")
    return commands


def print_navigation(*, paged: bool = False, mods: bool = False) -> None:
    for command in navigation_commands(paged=paged, mods=mods):
        print(f"{command:<14} {NAVIGATION_HELP[command]}")


def navigate_page(command: str, args: list[str], page: int, pages: int) -> int:
    if command == "next":
        requested = page + 1
    elif command == "prev":
        requested = page - 1
    elif command == "refresh":
        requested = page
    else:
        if len(args) != 1 or not args[0].isascii() or not args[0].isdecimal() or int(args[0]) < 1:
            raise ValueError("Use /page N with a positive page number.")
        requested = int(args[0])
    if not 1 <= requested <= pages:
        print(f"Page unchanged: available pages are 1 to {pages}.")
        return page
    return requested
