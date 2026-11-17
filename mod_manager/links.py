from __future__ import annotations

from .i18n import t

import os
import shutil
from pathlib import Path
from typing import List, Tuple

from .platform_utils import is_junction, is_windows, supports_links
from .windows_links import create_junction

TARGET_EXISTS = t('target_already_exists')
SOURCE_MISSING = t('source_not_found')
UNSUPPORTED_LINKS = "unsupported_links"
UNSUPPORTED_LINK_MESSAGE = (
    t('the_destination_file_system_does_not_support_links_select_copy_as_the_ga')
)

def _link_path(
    src: Path, dest: Path, is_dir: bool | None, support: dict[Path, bool | None],
) -> Tuple[bool, str]:
    try:
        if os.path.lexists(dest):
            return False, TARGET_EXISTS.format(dest)
        if not src.exists():
            return False, SOURCE_MISSING.format(src)
        if dest.parent not in support:
            support[dest.parent] = supports_links(dest.parent)
        if support[dest.parent] is False:
            return False, UNSUPPORTED_LINK_MESSAGE
        if is_dir is None:
            is_dir = src.is_dir()
        if is_windows() and is_dir:
            create_junction(src, dest)
        else:
            os.symlink(os.path.abspath(src), dest, target_is_directory=is_dir)
        return True, "OK"
    except Exception as error:
        return False, str(error)


def mklink(src: Path, dest: Path) -> Tuple[bool, str]:
    return _link_path(src, dest, None, {})


def mklink_batch(items: List[Tuple[Path, Path, bool]]) -> List[Tuple[bool, str]]:
    support: dict[Path, bool | None] = {}
    return [_link_path(src, dest, is_dir, support) for src, dest, is_dir in items]


def unlink_path(path: Path) -> Tuple[bool, str]:
    try:
        junction = is_junction(path)
        if not path.exists() and not path.is_symlink() and not junction:
            return False, t('already_removed')
        if junction:
            os.rmdir(path)
        elif path.is_dir() and not path.is_symlink():
            try:
                os.rmdir(path)
            except OSError:
                return False, t('not_a_link_or_not_empty')
        else:
            path.unlink()
        return True, "OK"
    except Exception as e:
        return False, str(e)

def unlink_broken_link(path: Path) -> Tuple[bool, str]:
    try:
        if not (path.is_symlink() or is_junction(path)) or path.exists():
            return False, t('not_a_broken_link_left_unchanged')
        return unlink_path(path)
    except OSError as error:
        return False, str(error)


def copy_path(src: Path, dest: Path, overwrite: bool = False) -> Tuple[bool, str]:
    try:
        if not src.exists():
            return False, SOURCE_MISSING.format(src)
        if dest.exists() or dest.is_symlink():
            if not overwrite:
                return False, TARGET_EXISTS.format(dest)
            ok, msg = remove_path(dest)
            if not ok:
                return False, msg
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dest)
        else:
            shutil.copy2(src, dest)
        return True, "OK"
    except Exception as e:
        return False, str(e)

def copy_batch(items: List[Tuple[Path, Path, bool]], overwrite: bool = False) -> List[Tuple[bool, str]]:
    return [copy_path(src, dest, overwrite) for src, dest, _is_dir in items]

def remove_path(path: Path) -> Tuple[bool, str]:
    """Remove a link or a copy installed in the game mods folder."""
    try:
        if path.is_symlink() or is_junction(path):
            return unlink_path(path)
        if not path.exists():
            return False, t('already_removed')
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
        return True, "OK"
    except Exception as e:
        return False, str(e)
