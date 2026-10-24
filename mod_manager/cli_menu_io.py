from __future__ import annotations

import argparse
import sys
from functools import wraps

from app_paths import APP_NAME, APP_VERSION

from .cli import run_cli, selected_items
from .cli_menu_actions import completions, parse_action, print_actions
from .cli_navigation import MenuNavigation, check_navigation
from .cli_utils import parse_multi_choice, prompt as terminal_prompt, smart_prompt
from .link_recovery import (
    COPY_RECOVERY_QUESTION, copy_retry_mods, retry_copy_installations, save_copy_profile,
)
from .models import OperationResult
from .mods import existing_targets, overwrite_message
from .storage import active_game_profile
from .storage_policy import storage_policy


def prompt(message: str) -> str:
    return check_navigation(terminal_prompt(message))


def interactive(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            with storage_policy():
                return function(*args, **kwargs)
        except MenuNavigation as navigation:
            if navigation.target != "back":
                raise
        except KeyboardInterrupt:
            print("\nCancelled.", file=sys.stderr)
        except (OSError, ValueError, argparse.ArgumentTypeError) as error:
            print(f"Error: {error}", file=sys.stderr)
    return wrapped


def header(section: str, cfg: dict) -> None:
    active = active_game_profile(cfg)
    game = active["name"] if active else "not selected; open Games to add a profile"
    print(f"\n{APP_NAME} v{APP_VERSION}")
    print("Main" if section == "Menu" else f"Main > {section}")
    print(f"Active game: {game}")


def read_action(section: str) -> tuple[str, list[str]]:
    while True:
        value = smart_prompt("Choose an action: ", lambda: completions(section))
        try:
            action, arguments = parse_action(section, value)
        except ValueError as error:
            print(f"Error: {error}", file=sys.stderr)
            continue
        if action == "help":
            print_actions(section, help_text=True)
            continue
        if action:
            return action, arguments


def execute(arguments: list[str]) -> int:
    try:
        return run_cli(arguments, recover_links=recover_links)
    except SystemExit as error:
        return int(error.code or 0)


def recover_links(cfg: dict, result: OperationResult, preset_names: tuple[str, ...]) -> OperationResult:
    from copy import deepcopy
    from .storage import load_config

    for item in result.items:
        if not item.success:
            print(f"{item.name}: {item.message}", file=sys.stderr)
    if not ask_yes_no(COPY_RECOVERY_QUESTION):
        return result
    current = load_config()
    overwrite = confirm_overwrite(copy_retry_mods(result))
    if overwrite is None:
        return result
    original = deepcopy(cfg)
    save_copy_profile(current, original)
    cfg.clear()
    cfg.update(current)
    return retry_copy_installations(cfg, result, overwrite, preset_names)


def read_indexes(items: list, noun: str, *, single: bool = False) -> list[int] | None:
    if not items:
        print(f"No {noun} available on this page. Nothing changed.")
        return None
    example = "1" if single or len(items) == 1 else "1,2"
    subject, separator, verb = noun.partition(" to ")
    label = f"{subject} number{'s' if not single else ''}" + (f" to {verb}" if separator else "")
    while True:
        value = prompt(f"Enter {label} (1–{len(items)}, for example {example}), or 0 to cancel: ").strip()
        if value == "0":
            print("Cancelled.")
            return None
        if value in {"?", "/help"}:
            print("Use the displayed item or page numbers from the range above. Enter 0 or /back to cancel.")
            continue
        try:
            indexes = parse_multi_choice(value)
            selected_items(items, indexes)
            if single and len(indexes) != 1:
                raise ValueError("Choose exactly one item number.")
            return indexes
        except (ValueError, argparse.ArgumentTypeError) as error:
            print(f"Error: {error}", file=sys.stderr)


def ask_yes_no(question: str, current: bool = False) -> bool:
    while True:
        answer = prompt(f"{question} (y/n) [{'y' if current else 'n'}]: ").strip().lower()
        if not answer:
            return current
        if answer in {"y", "yes", "n", "no"}:
            return answer in {"y", "yes"}
        print("Answer y or n. Use /back to cancel.", file=sys.stderr)


def confirm_overwrite(mods: list) -> bool | None:
    names = existing_targets(mods)
    if not names:
        return False
    print(overwrite_message(names))
    return True if ask_yes_no("Replace them?") else None


def read_text(label: str, *, current: str = "", description: str = "") -> str:
    while True:
        value = prompt(f"{label} [{current}; Enter keeps current; /back cancels]: ").strip()
        if value in {"?", "/help"}:
            print(description or f"Enter {label.lower()}. Use /back to cancel.")
            continue
        return value or current
