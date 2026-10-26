from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import cli_menu_io as console
from . import settings_schema
from .cli import selected_items
from .cli_collection_menus import menu_fix_broken, menu_mods_toggle, menu_presets
from .cli_environment import prepare_paths
from .cli_menu_actions import action_label, print_actions
from .cli_navigation import MenuNavigation
from .cli_utils import parse_multi_choice
from .storage import load_config, save_config
from .storage_policy import storage_policy

_ask_yes_no = console.ask_yes_no
_confirm_overwrite = console.confirm_overwrite


def _prompt_game_profile(existing: dict | None = None) -> dict | None:
    existing = existing or {}
    name = console.read_text("Game name", current=existing.get("name", ""), description=settings_schema.GAME_NAME_FIELD.tooltip)
    if not name:
        print("Cancelled: empty game name.")
        return None
    values = {"name": name}
    for spec in settings_schema.MODS_FIELDS:
        print(spec.tooltip)
        if spec.kind == settings_schema.FLAG:
            values[spec.key] = console.ask_yes_no(spec.label, bool(existing.get(spec.key)))
            continue
        current = str(existing.get(spec.key, ""))
        hint = f" ({'/'.join(spec.choices)})" if spec.kind == settings_schema.CHOICE else ""
        value = console.read_text(spec.label + hint, current=current, description=spec.tooltip).strip('"')
        if spec.kind == settings_schema.PATH and value:
            value = str(Path(value).expanduser())
        if spec.kind == settings_schema.CHOICE and value and value not in spec.choices:
            raise ValueError(f"{spec.label}: choose {' or '.join(spec.choices)}.")
        values[spec.key] = value
    return settings_schema.coerce_game_profile(values)


def _profile_arguments(values: dict) -> list[str]:
    arguments = []
    for spec in settings_schema.MODS_FIELDS:
        value = values[spec.key]
        flag = "--" + spec.key.replace("_", "-")
        if spec.kind == settings_schema.FLAG:
            arguments.append(flag if value else "--no-" + spec.key.replace("_", "-"))
        else:
            arguments.extend([flag, value])
    return arguments


@console.interactive
def _game_action(command: str, args: list[str], cfg: dict) -> None:
    if command == "prepare":
        print("\n".join(prepare_paths(cfg)))
        if console.ask_yes_no("Create the missing folders?"):
            console.execute(["games", "prepare", "--create-dirs"])
        return
    if command == "add":
        values = _prompt_game_profile()
        if values:
            console.execute(["games", "add", values["name"], *_profile_arguments(values)])
        return
    profiles = cfg.get("game_profiles", [])
    if not profiles:
        print(f"No games available. Choose {action_label('Games', 'add')} first.")
        return
    indexes = parse_multi_choice(" ".join(args)) if args else console.read_indexes(profiles, "game to " + command, single=True)
    if indexes is None:
        return
    if len(indexes) != 1:
        raise ValueError("Choose exactly one game number; for example edit 1.")
    profile = selected_items(profiles, indexes)[0]
    title = {"edit": "Editing", "delete": "Deleting", "select": "Selecting"}[command]
    print(f"{title}: {profile['name']} (#{indexes[0]})")
    if command == "edit":
        values = _prompt_game_profile(profile)
        if values:
            console.execute(["games", "edit", profile["id"], "--name", values["name"], *_profile_arguments(values)])
    else:
        console.execute(["games", command, profile["id"]])


@console.interactive
def menu_games(cfg: dict) -> None:
    while True:
        cfg = load_config()
        console.header("Games", cfg)
        print("\nItems")
        for index, profile in enumerate(cfg.get("game_profiles", []), 1):
            mark = "*" if profile["id"] == cfg.get("active_game_profile_id") else " "
            print(f"  #{index} [{mark}] {profile['name']}")
        if not cfg.get("game_profiles"):
            print(f"No game profiles. Choose {action_label('Games', 'add')}.")
        print_actions("Games")
        command, args = console.read_action("Games")
        if command == "back":
            return
        _game_action(command, args, cfg)


def _setting_value(spec, value: str):
    if spec.kind == settings_schema.FLAG:
        if value.lower() not in {"y", "yes", "true", "n", "no", "false"}:
            raise ValueError("Enter y or n.")
        return value.lower() in {"y", "yes", "true"}
    if spec.kind == settings_schema.CHOICE and value not in spec.choices:
        raise ValueError(f"Choose one of: {', '.join(spec.choices)}.")
    if spec.kind == settings_schema.COLOR and not settings_schema.normalize_hex(value):
        raise ValueError("Enter a hexadecimal color.")
    return settings_schema.coerce_value(spec, value)


def _print_settings(pending: dict) -> None:
    print("\nItems")
    offset = 0
    for caption, fields in settings_schema.SETTINGS_SECTIONS:
        print(caption)
        for spec in fields:
            offset += 1
            print(f"  #{offset} {spec.label}: {pending.get(spec.key, '')}")


@console.interactive
def _edit_setting(pending: dict) -> None:
    specs = list(settings_schema.all_specs())
    indexes = console.read_indexes(specs, "setting to edit", single=True)
    if indexes is None:
        return
    spec = specs[indexes[0] - 1]
    print(f"Editing: {spec.label}")
    print(spec.tooltip)
    if spec.choices:
        print("Choices: " + ", ".join(spec.choices))
    while True:
        value = console.read_text(spec.label, current=str(pending.get(spec.key, "")), description=spec.tooltip)
        try:
            pending[spec.key] = _setting_value(spec, value)
            return
        except ValueError as error:
            print(f"Error: {error}", file=sys.stderr)


@console.interactive
def _leave_settings(pending: dict, saved: dict) -> bool:
    if pending == saved:
        return True
    print("There are unsaved settings changes.")
    print_actions("Unsaved changes")
    command, _args = console.read_action("Unsaved changes")
    if command == "back":
        return False
    if command == "save":
        save_config(pending)
        print("Saved.")
    else:
        print("Changes discarded.")
    return True


@console.interactive
def menu_settings(cfg: dict) -> None:
    saved = dict(cfg)
    pending = dict(cfg)
    while True:
        console.header("Settings", cfg)
        _print_settings(pending)
        print_actions("Settings")
        try:
            command, _args = console.read_action("Settings")
            if command == "back":
                if _leave_settings(pending, saved):
                    return
            elif command == "edit":
                _edit_setting(pending)
            elif command == "save":
                save_config(pending)
                saved = dict(pending)
                cfg.update(saved)
                print("Saved.")
            elif command == "discard":
                pending = dict(saved)
                print("Changes discarded.")
        except MenuNavigation as navigation:
            if _leave_settings(pending, saved):
                raise navigation
        except (OSError, ValueError) as error:
            print(f"Error: {error}", file=sys.stderr)


def main_menu() -> int:
    try:
        with storage_policy():
            while True:
                try:
                    cfg = load_config()
                    console.header("Menu", cfg)
                    print_actions("Main")
                    command, _args = console.read_action("Main")
                    sections = {"games": menu_games, "settings": menu_settings, "mods": menu_mods_toggle, "presets": menu_presets, "broken": menu_fix_broken}
                    if command in sections:
                        sections[command](cfg)
                    elif command == "back":
                        print("Goodbye!")
                        return 0
                    elif command in {"open-source", "open-game"}:
                        console.execute(["open", "source" if command == "open-source" else "game"])
                    elif command == "doctor":
                        console.execute(["doctor"])
                except MenuNavigation as navigation:
                    if navigation.target == "exit":
                        return 0
                    if navigation.target == "back":
                        print("Already at the main menu.")
    except EOFError:
        print("\nEnd of input.")
        return 0
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
