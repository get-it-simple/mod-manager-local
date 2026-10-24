from __future__ import annotations

import argparse
from typing import List

from app_paths import APP_NAME, APP_VERSION

from . import settings_schema
from .cli_commands import ACTION_HELP, COMMAND_HELP
from .cli_utils import parse_multi_choice


OPTION_HELP = {
    "page": "Page number, starting at 1. Indexes refer to this page.",
    "label": "Filter by label; for label actions, the label to assign or remove.",
    "filter_label": "Filter the visible page by this label before selecting indexes.",
    "search": "Filter mod names by this text.",
    "order": "Sort: default, created_date, name, label, installed, last_managed; '-' means descending.",
    "favorite": "Show or act on favorites only.",
    "indexes": "Comma-separated positive indexes on the selected page, for example 1,3,5.",
    "number": "Page number, starting at 1.",
    "mode": "Sort mode; prefix with '-' for descending order.",
    "text": "Search text or label; quote text containing spaces.",
    "name": "Name; quote names containing spaces.",
    "profile_id": "Game profile ID shown by games list.",
    "target": "source opens downloaded mods; game opens installed mod destinations.",
}


class CommandSubparsers(argparse._SubParsersAction):
    def add_parser(self, name, **kwargs):
        description = COMMAND_HELP.get(name, ACTION_HELP.get(name, ""))
        kwargs.setdefault("help", description)
        kwargs.setdefault("description", description)
        return super().add_parser(name, **kwargs)


class CommandParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("allow_abbrev", False)
        kwargs.setdefault("formatter_class", argparse.ArgumentDefaultsHelpFormatter)
        kwargs.setdefault("description", "Manage mods for the active game. Run without arguments for menus.")
        super().__init__(*args, **kwargs)
        self.register("action", "parsers", CommandSubparsers)
        self.set_defaults(_help_parser=self)
        self.epilog = "Examples: python mod-manager.py help mods toggle; python mod-manager.py doctor"

    def _add_action(self, action):
        if action.help is None:
            action.help = OPTION_HELP.get(action.dest)
        return super()._add_action(action)

    def _parse_optional(self, arg_string):
        if arg_string in {"-default", "-created_date", "-name", "-label", "-installed", "-last_managed"}:
            return None
        return super()._parse_optional(arg_string)


def positive_number(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("Enter a positive whole number.") from None
    if number < 1:
        raise argparse.ArgumentTypeError("Enter a positive whole number.")
    return number


def _indexes(value: str) -> List[int]:
    try:
        indexes = parse_multi_choice(value or "")
        if not indexes:
            raise ValueError("Select at least one index, for example 1,3,5.")
        return indexes
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error

def _order(value: str) -> str:
    v = (value or "d").strip().lower()
    aliases = {
        "d": "default",
        "default": "default",
        "default desc": "-default",
        "cd": "created_date",
        "created date": "created_date",
        "created_date": "created_date",
        "created date desc": "-created_date",
        "created_date desc": "-created_date",
        "name": "name",
        "name desc": "-name",
        "label": "label",
        "label desc": "-label",
        "installed": "installed",
        "installed desc": "-installed",
        "last managed": "last_managed",
        "last_managed": "last_managed",
        "last managed desc": "-last_managed",
        "last_managed desc": "-last_managed",
    }
    if v.startswith("-"):
        key = v[1:]
        if key in {"default", "created_date", "created date", "name", "label", "installed", "last_managed", "last managed"}:
            return "-" + aliases.get(key, key.replace(" ", "_"))
    if v in aliases:
        return aliases[v]
    raise argparse.ArgumentTypeError("order must be one of: default, created_date, name, label, installed, last_managed, with optional '-' prefix or ' desc'")

OVERWRITE_HELP = "Replace files that already exist in the game mods folder when the profile installs by copy."

def _add_overwrite_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--overwrite", action="store_true", help=OVERWRITE_HELP)

def _add_profile_args(parser: argparse.ArgumentParser, use_defaults: bool) -> None:
    """Build the per game profile flags from the shared schema so the lists cannot drift."""
    for spec in settings_schema.MODS_FIELDS:
        flag = "--" + spec.key.replace("_", "-")
        if spec.kind == settings_schema.FLAG:
            default = False if use_defaults else None
            parser.add_argument(flag, action=argparse.BooleanOptionalAction, default=default, help=spec.tooltip)
        elif spec.kind == settings_schema.CHOICE:
            default = spec.choices[0] if use_defaults else None
            parser.add_argument(flag, choices=list(spec.choices), default=default, help=spec.tooltip)
        else:
            parser.add_argument(flag, default="" if use_defaults else None, help=spec.tooltip)

def _add_view_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--page", type=positive_number, default=1)
    parser.add_argument("--label", default="")
    parser.add_argument("--search", default="")
    parser.add_argument("--order", type=_order, default="d")
    parser.add_argument("--favorite", action="store_true")

def build_parser() -> argparse.ArgumentParser:
    parser = CommandParser(prog="mod-manager.py")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} v{APP_VERSION}")
    sub = parser.add_subparsers(dest="cmd")

    mods = sub.add_parser("mods")
    mods_sub = mods.add_subparsers(dest="mods_cmd", required=False)
    for name in ["list", "install", "uninstall", "toggle"]:
        p = mods_sub.add_parser(name)
        _add_view_args(p)
        if name in {"install", "toggle"}:
            _add_overwrite_arg(p)
    p = mods_sub.add_parser("search")
    p.add_argument("text")
    p.add_argument("--page", type=positive_number, default=1)
    p.add_argument("--label", default="")
    p.add_argument("--order", type=_order, default="d")
    p.add_argument("--favorite", action="store_true")
    p = mods_sub.add_parser("label")
    p.add_argument("text")
    p.add_argument("--page", type=positive_number, default=1)
    p.add_argument("--search", default="")
    p.add_argument("--order", type=_order, default="d")
    p.add_argument("--favorite", action="store_true")
    p = mods_sub.add_parser("page")
    p.add_argument("number", type=positive_number)
    p.add_argument("--label", default="")
    p.add_argument("--search", default="")
    p.add_argument("--order", type=_order, default="d")
    p.add_argument("--favorite", action="store_true")
    p = mods_sub.add_parser("order")
    p.add_argument("mode", type=_order)
    p.add_argument("--page", type=positive_number, default=1)
    p.add_argument("--label", default="")
    p.add_argument("--search", default="")
    p.add_argument("--favorite", action="store_true")
    mods_sub.choices["toggle"].add_argument("indexes", type=_indexes)
    for name in ["label-add", "label-remove"]:
        p = mods_sub.add_parser(name)
        p.add_argument("label")
        p.add_argument("indexes", type=_indexes)
        p.add_argument("--page", type=positive_number, default=1)
        p.add_argument("--filter-label", default="")
        p.add_argument("--search", default="")
        p.add_argument("--order", type=_order, default="d")
        p.add_argument("--favorite", action="store_true")
    for name in ["favorite-add", "favorite-remove"]:
        p = mods_sub.add_parser(name)
        p.add_argument("indexes", type=_indexes)
        p.add_argument("--page", type=positive_number, default=1)
        p.add_argument("--filter-label", default="")
        p.add_argument("--search", default="")
        p.add_argument("--order", type=_order, default="d")
        p.add_argument("--favorite", action="store_true")

    presets = sub.add_parser("presets")
    presets_sub = presets.add_subparsers(dest="presets_cmd", required=False)
    presets_sub.add_parser("list").add_argument("--page", type=positive_number, default=1)
    presets_sub.add_parser("page").add_argument("number", type=positive_number)
    presets_sub.add_parser("save").add_argument("name")
    for name in ["delete", "toggle"]:
        p = presets_sub.add_parser(name)
        p.add_argument("indexes", type=_indexes)
        p.add_argument("--page", type=positive_number, default=1)
        if name == "toggle":
            _add_overwrite_arg(p)

    settings = sub.add_parser("settings")
    settings_sub = settings.add_subparsers(dest="settings_cmd", required=False)
    settings_sub.add_parser("show")
    settings_set = settings_sub.add_parser("set")
    for spec in settings_schema.all_specs():
        flag = "--" + spec.key.replace("_", "-")
        if spec.kind == settings_schema.FLAG:
            settings_set.add_argument(flag, action=argparse.BooleanOptionalAction, default=None, help=spec.tooltip)
        elif spec.kind == settings_schema.CHOICE:
            settings_set.add_argument(flag, choices=list(spec.choices), help=spec.tooltip)
        elif spec.kind == settings_schema.INT:
            settings_set.add_argument(flag, type=positive_number, help=spec.tooltip)
        else:
            settings_set.add_argument(flag, help=spec.tooltip)

    games = sub.add_parser("games")
    games_sub = games.add_subparsers(dest="games_cmd", required=False)
    games_sub.add_parser("list")
    games_sub.add_parser("prepare").add_argument("--create-dirs", action="store_true", help="Confirm creation of the listed missing folders. No files are imported.")
    games_select = games_sub.add_parser("select")
    games_select.add_argument("profile_id")
    games_delete = games_sub.add_parser("delete")
    games_delete.add_argument("profile_id")
    games_add = games_sub.add_parser("add")
    games_add.add_argument("name")
    _add_profile_args(games_add, use_defaults=True)
    games_edit = games_sub.add_parser("edit")
    games_edit.add_argument("profile_id")
    games_edit.add_argument("--name")
    _add_profile_args(games_edit, use_defaults=False)

    open_parser = sub.add_parser("open")
    open_parser.add_argument("target", choices=["source", "game"])

    broken = sub.add_parser("broken")
    broken_sub = broken.add_subparsers(dest="broken_cmd", required=False)
    broken_sub.add_parser("list")
    broken_remove = broken_sub.add_parser("remove")
    broken_remove.add_argument("indexes", nargs="?", type=_indexes, default=[])
    broken_remove.add_argument("--all", action="store_true", help="Remove every broken link listed by broken list.")

    sub.add_parser("gui")
    sub.add_parser("doctor")

    help_p = sub.add_parser("help", help="Show help for a command")
    help_p.add_argument("topic", nargs="*", metavar="command", help="Command and optional subcommand (e.g. mods toggle)")

    return parser
