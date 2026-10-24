from __future__ import annotations

import argparse
import sys
from typing import Dict, List

from . import settings_schema
from .cli_environment import configured_path, diagnose, prepare_paths, require_paths
from .cli_parser import build_parser
from .folder_actions import open_folder
from .mods import (
    add_favorites_to_mods, add_label_to_mods, change_mods, existing_targets,
    list_broken_links, mods_view, overwrite_message, remove_favorites_from_mods,
    remove_label_from_mods,
)
from .links import unlink_broken_link
from .presets import (
    delete_presets_by_indexes, preset_mods_to_install, presets_view,
    save_preset_from_installed, toggle_presets_by_indexes,
)
from .storage import (
    GAME_PROFILE_KEYS, create_game_profile, delete_game_profile, game_abbreviation,
    load_config, save_config, set_active_game_profile, update_game_profile,
)
from .storage_policy import storage_policy


def report_error(message: str) -> int:
    print(f"Error: {message}", file=sys.stderr)
    return 1


def selected_items(items: list, indexes: list[int]) -> list:
    if not indexes or any(index < 1 or index > len(items) for index in indexes):
        raise argparse.ArgumentTypeError(f"Invalid index. Select indexes from 1 to {len(items)} on this page; use list with the same filters first.")
    return [items[index - 1] for index in dict.fromkeys(indexes)]


def _filtered_mods_view(cfg: Dict, page: int, label: str, search: str, order: str, favorite_only: bool = False):
    return mods_view(cfg, page, label, search, order, favorite_only)


def _print_mods(cfg: Dict, page: int, label: str, search: str, order: str, favorite_only: bool = False, *, interactive: bool = False, view=None) -> int:
    items, shown, page, pages, labels = view if view is not None else _filtered_mods_view(cfg, page, label, search, order, favorite_only)
    print(f"Page {page}/{pages}")
    for index, mod in enumerate(shown, 1):
        mark = "X" if mod.installed else " "
        if not cfg.get("game_mods_dir"):
            mark = "?"
        print(f"{'#' if interactive else ''}{index}. [{mark}] {mod.name} [{labels.get(mod.name, '-')}]")
    if not items:
        print("No mods.")
    return 0


def _print_presets(cfg: Dict, page: int, *, interactive: bool = False) -> int:
    presets, keys, page_keys, page, pages = presets_view(cfg, page)
    known_state = False
    installed = set()
    try:
        require_paths(cfg)
        installed = {mod.name for mod in mods_view(cfg, 1, "", "", "d")[0] if mod.installed}
        known_state = True
    except (OSError, ValueError):
        pass
    print(f"Page {page}/{pages}")
    for index, name in enumerate(page_keys, 1):
        members = presets.get(name, [])
        mark = "X" if members and all(member in installed for member in members) else " "
        if not known_state:
            mark = "?"
        print(f"{'#' if interactive else ''}{index}. [{mark}] {name} [{len(members)}]")
    if not keys:
        print("No presets saved.")
    if not known_state:
        print("[?] Installation state unavailable. Run doctor to check game paths.")
    return 0


def _allow_overwrite(pending: list, overwrite: bool) -> bool:
    names = existing_targets(pending) if not overwrite else []
    if names:
        report_error(overwrite_message(names))
        print("Re-run with --overwrite to replace them.", file=sys.stderr)
        return False
    return True


def _mods_selection(args, cfg):
    label = getattr(args, "filter_label", None)
    if label is None:
        label = args.label
    return mods_view(cfg, args.page, label, args.search, args.order, args.favorite)


def _run_mods(args: argparse.Namespace, cfg: Dict) -> int:
    require_paths(cfg, game=args.mods_cmd in {"install", "uninstall", "toggle"})
    if args.mods_cmd in {"list", "search", "label", "page", "order"}:
        return _print_mods(
            cfg,
            args.number if args.mods_cmd == "page" else args.page,
            args.text if args.mods_cmd == "label" else args.label,
            args.text if args.mods_cmd == "search" else args.search,
            args.mode if args.mods_cmd == "order" else args.order,
            args.favorite,
        )
    _items, shown, page, pages, _labels = _mods_selection(args, cfg)
    if args.page > pages:
        raise argparse.ArgumentTypeError(f"Page {args.page} does not exist. There are {pages} pages.")
    targets = selected_items(shown, args.indexes) if hasattr(args, "indexes") else shown
    if args.mods_cmd in {"install", "uninstall", "toggle"}:
        pending = [mod for mod in targets if not mod.installed]
        if args.mods_cmd != "uninstall" and not _allow_overwrite(pending, args.overwrite):
            return 1
        result = change_mods(targets, args.mods_cmd, getattr(args, "overwrite", False))
        print(f"Page {page}. {result.summary()}")
        for item in result.items:
            print(f"{item.name}: {'OK' if item.success else 'ERR'} — {item.message}", file=sys.stdout if item.success else sys.stderr)
        return int(bool(result.errors))
    names = [mod.name for mod in targets]
    if args.mods_cmd == "label-add":
        print(add_label_to_mods(args.label, names))
    elif args.mods_cmd == "label-remove":
        print(remove_label_from_mods(args.label, names))
    elif args.mods_cmd == "favorite-add":
        print(add_favorites_to_mods(cfg, names))
    elif args.mods_cmd == "favorite-remove":
        print(remove_favorites_from_mods(cfg, names))
    return 0


def _preset_selection(args, cfg):
    _presets, _keys, names, _page, pages = presets_view(cfg, args.page)
    if args.page > pages:
        raise argparse.ArgumentTypeError(f"Page {args.page} does not exist. There are {pages} pages.")
    return selected_items(names, args.indexes)


def _run_presets(args: argparse.Namespace, cfg: Dict) -> int:
    if args.presets_cmd in {"list", "page"}:
        return _print_presets(cfg, args.number if args.presets_cmd == "page" else args.page)
    if args.presets_cmd == "save":
        require_paths(cfg)
        if not args.name.strip():
            raise argparse.ArgumentTypeError("Preset name must not be empty.")
        ok, message = save_preset_from_installed(cfg, args.name.strip())
        print(message, file=sys.stdout if ok else sys.stderr)
        return int(not ok)
    names = _preset_selection(args, cfg)
    if args.presets_cmd == "delete":
        count, missing = delete_presets_by_indexes(cfg, args.page, args.indexes)
        print(f"Deleted: {count}. Missing: {', '.join(missing) if missing else 'none'}")
        return int(bool(missing))
    require_paths(cfg)
    installed = {mod.name for mod in mods_view(cfg, 1, "", "", "d")[0] if mod.installed}
    work, _missing = preset_mods_to_install(cfg, names)
    if not _allow_overwrite(work, args.overwrite):
        return 1
    message, messages, errors = toggle_presets_by_indexes(cfg, args.page, args.indexes, installed, args.overwrite)
    print(message or "No presets toggled.")
    for detail in messages:
        print(detail, file=sys.stderr if errors else sys.stdout)
    return int(errors)


def _run_settings(args: argparse.Namespace, cfg: Dict) -> int:
    if args.settings_cmd == "show":
        for key in sorted(cfg):
            print(f"{key}: {cfg[key]}")
        return 0
    changes = {}
    for spec in settings_schema.all_specs():
        value = getattr(args, spec.key, None)
        if value is not None:
            try:
                if spec.kind == settings_schema.COLOR and not settings_schema.normalize_hex(value):
                    raise ValueError(f"{spec.label} must be a hexadecimal color.")
                changes[spec.key] = settings_schema.coerce_value(spec, value)
            except ValueError as error:
                raise argparse.ArgumentTypeError(str(error)) from error
    if changes:
        candidate = {**cfg, **changes}
        save_config(candidate)
        cfg.update(changes)
        print("Saved.")
    else:
        print("Nothing changed. See help settings set for available options.")
    return 0


def _profile_values_from_args(args: argparse.Namespace) -> Dict:
    values = {}
    if getattr(args, "name", None) is not None:
        if not args.name.strip():
            raise argparse.ArgumentTypeError("Game name must not be empty.")
        values["name"] = args.name.strip()
    for key in GAME_PROFILE_KEYS:
        value = getattr(args, key, None)
        if value is not None:
            values[key] = value
    return settings_schema.coerce_game_profile(values)


def _run_games(args: argparse.Namespace, cfg: Dict) -> int:
    if args.games_cmd == "prepare":
        print("\n".join(prepare_paths(cfg, create=args.create_dirs)))
        return 0
    if args.games_cmd == "list":
        profiles = cfg.get("game_profiles", [])
        for profile in profiles:
            mark = "*" if profile.get("id") == cfg.get("active_game_profile_id") else " "
            print(f"{mark} {profile['id']} {game_abbreviation(profile['name'])} {profile['name']}")
        if not profiles:
            print("No game profiles. Use games add; see help games add.")
        return 0
    if args.games_cmd == "add":
        values = _profile_values_from_args(args)
        create_game_profile(values.pop("name"), values, cfg)
        message = "Added."
    else:
        if args.games_cmd == "edit":
            ok = update_game_profile(cfg, args.profile_id, _profile_values_from_args(args))
        elif args.games_cmd == "select":
            ok = set_active_game_profile(cfg, args.profile_id)
        else:
            ok = delete_game_profile(cfg, args.profile_id)
        if not ok:
            return report_error("Game profile not found. Use games list to see profile IDs.")
        message = "Selected." if args.games_cmd == "select" else "Deleted." if args.games_cmd == "delete" else "Saved."
    save_config(cfg)
    print(message)
    return 0


def _run_open(args: argparse.Namespace, cfg: Dict) -> int:
    key = "mods_source_dir" if args.target == "source" else "game_mods_dir"
    configured_path(cfg, key)
    ok, message = open_folder(cfg[key], create=False)
    print(f"Open {args.target} folder: {'OK' if ok else 'ERR'} — {message}", file=sys.stdout if ok else sys.stderr)
    return int(not ok)


def _run_broken(args: argparse.Namespace, cfg: Dict) -> int:
    require_paths(cfg, source=False)
    broken = list_broken_links(cfg)
    if args.broken_cmd == "list":
        for index, mod in enumerate(broken, 1):
            print(f"{index}. [!] {mod.name} -> missing source: {mod.src}")
        if not broken:
            print("No broken links detected.")
        return 0
    if args.all and args.indexes:
        raise argparse.ArgumentTypeError("Use indexes or --all, not both.")
    if not args.all and not args.indexes:
        raise argparse.ArgumentTypeError("Specify indexes from broken list, or use --all.")
    targets = broken if args.all else selected_items(broken, args.indexes)
    errors = 0
    for mod in targets:
        ok, message = unlink_broken_link(mod.dest)
        errors += not ok
        print(f"Remove {mod.dest.name}: {'OK' if ok else 'ERR'} — {message}", file=sys.stdout if ok else sys.stderr)
    return int(bool(errors))


def _run_help(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    current = parser
    for topic in args.topic:
        choices = {}
        for action in current._actions:
            if isinstance(action, argparse._SubParsersAction):
                choices.update(action.choices)
        if topic not in choices:
            return report_error(f"Unknown help topic: {topic}. Available: {', '.join(choices) or 'none'}.")
        current = choices[topic]
    current.print_help()
    return 0


def run_cli(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "help":
        return _run_help(args, parser)
    if args.cmd is None or any(getattr(args, key, False) is None for key in ("mods_cmd", "presets_cmd", "games_cmd", "settings_cmd", "broken_cmd")):
        args._help_parser.print_help()
        return 0
    try:
        if args.cmd == "gui":
            from .ui import run_gui

            return run_gui()
        with storage_policy():
            cfg = load_config()
            if args.cmd == "doctor":
                messages, errors = diagnose(cfg)
                print("\n".join(messages))
                return int(errors)
            handlers = {"mods": _run_mods, "presets": _run_presets, "games": _run_games, "settings": _run_settings, "open": _run_open, "broken": _run_broken}
            return handlers[args.cmd](args, cfg)
    except argparse.ArgumentTypeError as error:
        report_error(str(error))
        return 2
    except (OSError, ValueError, TypeError) as error:
        return report_error(str(error))
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130
