from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath

from .i18n import t

MOD_MODES = ("standard", "directories")
TRASH_DIRECTORY = ".mod-trash"
RESERVED_MOD_DIRECTORIES = frozenset(("images", TRASH_DIRECTORY))


def directory_mode(cfg: dict) -> bool:
    return cfg.get("mod_mode") == "directories"


def normalize_icon_path(value) -> str:
    text = str(value or "").strip().replace("\\", "/")
    if not text:
        return ""
    path = PurePosixPath(text)
    if (path.is_absolute() or PureWindowsPath(text).drive or ".." in path.parts
            or ":" in text or "\0" in text or not path.name or path == PurePosixPath(".")):
        raise ValueError(t("mod_icon_path_invalid"))
    return path.as_posix()


def internal_mod_icon(cfg: dict, mod_dir: Path) -> Path | None:
    try:
        relative = normalize_icon_path(cfg.get("mod_icon_path"))
        if not relative or not mod_dir.is_dir():
            return None
        candidate = mod_dir / relative
        if candidate.resolve().is_relative_to(mod_dir.resolve()) and candidate.is_file():
            return candidate
    except (OSError, ValueError, RuntimeError):
        return None
    return None
