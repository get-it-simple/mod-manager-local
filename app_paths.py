#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
import os
import sys
from mod_manager.keyboard import default_bindings
from pathlib import Path

APP_NAME = "Mod Manager"
APP_VERSION = "1.2.45"
INSTALL_MARKER = "mod-manager.machine"


def machine_data_directory(local_data: Path) -> Path:
    directory = local_data / "GetItSimple" / APP_NAME
    legacy = local_data / APP_NAME
    if directory.is_dir() or not legacy.is_dir():
        return directory
    if any((legacy / "profiles" / "renames").glob("*.json")):
        return legacy
    try:
        directory.parent.mkdir(parents=True, exist_ok=True)
        legacy.rename(directory)
    except OSError:
        return directory if directory.is_dir() else legacy
    return directory


def data_directory(app_dir: Path, *, frozen: bool) -> Path:
    if os.name == "nt" and frozen and (app_dir / INSTALL_MARKER).is_file():
        local_data = os.environ.get("LOCALAPPDATA")
        return machine_data_directory(Path(local_data) if local_data else Path.home() / "AppData" / "Local")
    return app_dir


if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
elif Path(sys.argv[0]).suffix.lower() == ".pyz":
    APP_DIR = Path(sys.argv[0]).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parent
DATA_DIR = data_directory(APP_DIR, frozen=getattr(sys, "frozen", False))
CONFIG_PATH = DATA_DIR / "config.json"
PRESETS_PATH = DATA_DIR / "presets.json"
LABELS_PATH = DATA_DIR / "labels.json"
PROFILE_DATA_DIR = DATA_DIR / "profiles"

PAGE_SIZE = 10

PRINT_SIZE = 48

DEFAULT_CONFIG = {
    "active_game_profile_id": "",
    "game_profiles": [],
    "mods_source_dir": "",
    "game_mods_dir": "",
    "mod_extensions": "",
    "mod_mode": "standard",
    "mod_icon_path": "",
    "mod_group_extensions": "",
    "mod_recursive_scan": False,
    "link_prefix": "",
    "install_mode": "link",
    "quick_tools": [],
    "archive_import_mode": "together",
    "archive_preserve_structure": False,
    "import_ignore_extensions": "",
    "page_size": 10,
    "max_mod_name_len": 28,
    "max_preset_name_len": 28,
    "max_label_name_len": 12,
    "gui_theme": "system",
    "gui_language": "en",
    "gui_animations_enabled": True,
    "keyboard_shortcuts": default_bindings(),
    "gui_accent_color_mode": "system",
    "gui_accent_color": "#2563eb",
    "gui_text_color_mode": "system",
    "gui_text_color": "#111827",
    "gui_font_family": "",
    "gui_font_size": 10,
    "ui_scale_percent": 100,
    "placeholder_image_col_width": 32,
    "mod_view_mode": "list",
    "trash_view_mode": "list",
    "mod_details_visible": True,
    "tile_size": 140,
    "window_width": 1200,
    "window_height": 750,
    "order_var": "Default",
    "mod_sort_key": "d",
    "mod_sort_reverse": False,
    "preset_sort_key": "name",
    "preset_sort_reverse": False,
}
