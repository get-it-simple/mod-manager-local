from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

from .platform_utils import is_windows


def ensure_paths(cfg: dict) -> bool:
    paths = [cfg.get("game_mods_dir"), cfg.get("mods_source_dir")]
    if not all(paths):
        print("Please configure paths first.")
        return False
    try:
        for path in paths:
            Path(path).mkdir(parents=True, exist_ok=True)
        return True
    except (OSError, ValueError, TypeError):
        return False


def _windows_explorer_select_arg(target: Path) -> str:
    return f'/select,"{target}"'


def _windows_shell_select_path(target: Path) -> bool:
    import ctypes
    import ctypes.wintypes

    pidl = ctypes.c_void_p()
    initialized = False
    try:
        ole32 = ctypes.windll.ole32
        shell32 = ctypes.windll.shell32
        ole32.CoInitialize.argtypes = [ctypes.c_void_p]
        ole32.CoInitialize.restype = ctypes.c_long
        ole32.CoUninitialize.argtypes = []
        ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        shell32.SHParseDisplayName.argtypes = [ctypes.wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.c_ulong, ctypes.c_void_p]
        shell32.SHParseDisplayName.restype = ctypes.c_long
        shell32.SHOpenFolderAndSelectItems.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_ulong]
        shell32.SHOpenFolderAndSelectItems.restype = ctypes.c_long
        initialized = ole32.CoInitialize(None) in (0, 1)
        if shell32.SHParseDisplayName(str(target), None, ctypes.byref(pidl), 0, None) != 0 or not pidl.value:
            return False
        return shell32.SHOpenFolderAndSelectItems(pidl, 0, None, 0) == 0
    except (AttributeError, OSError):
        return False
    finally:
        if pidl.value:
            ole32.CoTaskMemFree(pidl)
        if initialized:
            ole32.CoUninitialize()


def select_in_explorer(path: Path) -> None:
    target = Path(path).expanduser()
    try:
        if is_windows():
            target = target.absolute()
            if target.exists() or target.is_symlink():
                if not _windows_shell_select_path(target):
                    subprocess.Popen(["explorer", _windows_explorer_select_arg(target)], creationflags=0x08000000)
            elif target.parent.exists():
                subprocess.Popen(["explorer", str(target.parent)], creationflags=0x08000000)
        elif platform.system() == "Darwin":
            if target.exists():
                subprocess.Popen(["open", "-R", str(target)])
            elif target.parent.exists():
                subprocess.Popen(["open", str(target.parent)])
    except (OSError, ValueError):
        pass


def open_folder(path_str: str, *, create: bool = True) -> tuple[bool, str]:
    try:
        if not path_str:
            return False, "Path is empty"
        path = Path(path_str).expanduser()
        if create:
            path.mkdir(parents=True, exist_ok=True)
        if not path.is_dir():
            return False, "Folder does not exist. Use games prepare --create-dirs first."
        if is_windows():
            os.startfile(str(path))
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
        return True, "Opened"
    except (OSError, ValueError, TypeError) as error:
        return False, str(error)
