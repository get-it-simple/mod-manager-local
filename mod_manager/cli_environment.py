from __future__ import annotations

import importlib.util
import os
from pathlib import Path

from app_paths import CONFIG_PATH, PROFILE_DATA_DIR

from . import settings_schema
from .storage import active_game_profile, load_mod_records, load_preset_records


PATH_KEYS = ("mods_source_dir", "game_mods_dir")
PREPARE_HINT = "Use games prepare to inspect paths, then games prepare --create-dirs to create missing folders."


def configured_path(cfg: dict, key: str) -> Path:
    value = cfg.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{settings_schema.label_for(key)} is not configured. Use games add or games edit; see help games.")
    if "\0" in value:
        raise ValueError(f"{settings_schema.label_for(key)} contains an invalid character.")
    return Path(value).expanduser()


def require_paths(cfg: dict, *, source: bool = True, game: bool = True) -> None:
    for key, required in zip(PATH_KEYS, (source, game)):
        if required:
            path = configured_path(cfg, key)
            if not path.is_dir():
                raise ValueError(f"{settings_schema.label_for(key)} is not an existing folder: {path}. {PREPARE_HINT}")
    if source and game:
        _require_separate_paths([configured_path(cfg, key) for key in PATH_KEYS])


def _require_separate_paths(paths: list[Path]) -> None:
    source, game = (path.resolve() for path in paths)
    if source == game or source in game.parents or game in source.parents:
        raise ValueError("Source and game mods folders must be separate and must not contain each other.")


def prepare_paths(cfg: dict, *, create: bool = False) -> list[str]:
    paths = [configured_path(cfg, key) for key in PATH_KEYS]
    _require_separate_paths(paths)
    for path in paths:
        parent = path
        while not parent.exists() and parent != parent.parent:
            parent = parent.parent
        if not parent.is_dir() or path.is_symlink() and not path.exists():
            raise ValueError(f"Path is not a usable folder: {path}")
    messages = []
    for path in paths:
        if path.is_dir():
            messages.append(f"Ready: {path}")
        elif create:
            try:
                path.mkdir(parents=True, exist_ok=True)
            except OSError as error:
                raise OSError(f"Cannot create {path}: {error}. Earlier folders may already have been created.") from error
            messages.append(f"Created: {path}")
        else:
            messages.append(f"Missing: {path}")
    if not create:
        messages.append("No folders created. Use games prepare --create-dirs to confirm creation.")
    return messages


def diagnose(cfg: dict) -> tuple[list[str], bool]:
    messages = [f"Configuration: {CONFIG_PATH}"]
    errors = False
    profile = active_game_profile(cfg)
    messages.append(f"Active game: {profile['name']}" if profile else "No active game. Use games add; see help games add.")
    errors = not bool(profile)
    for key in PATH_KEYS:
        try:
            require_paths(cfg, source=key == PATH_KEYS[0], game=key == PATH_KEYS[1])
            path = configured_path(cfg, key)
            with os.scandir(path):
                pass
            messages.append(f"Ready: {settings_schema.label_for(key)}")
        except (OSError, ValueError) as error:
            messages.append(str(error))
            errors = True
    try:
        if all(cfg.get(key) and Path(cfg[key]).is_dir() for key in PATH_KEYS):
            require_paths(cfg)
        load_mod_records()
        load_preset_records()
        for path in (CONFIG_PATH.parent, PROFILE_DATA_DIR if PROFILE_DATA_DIR.exists() else PROFILE_DATA_DIR.parent):
            if not os.access(path, os.W_OK):
                messages.append(f"Storage is not writable: {path}. Check folder permissions.")
                errors = True
    except (OSError, ValueError) as error:
        messages.append(str(error))
        errors = True
    for module, usage in (("PySide6", "GUI"), ("prompt_toolkit", "optional completion")):
        available = importlib.util.find_spec(module) is not None
        messages.append(f"{usage}: {'available' if available else 'unavailable; install requirements.txt if needed'}")
    return messages, errors
