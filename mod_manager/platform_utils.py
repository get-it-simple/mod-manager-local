from __future__ import annotations

import platform
import stat
from pathlib import Path

FILE_SUPPORTS_REPARSE_POINTS = 0x00000080

def is_windows() -> bool:
    return platform.system().lower().startswith("win")


def supports_links(directory: Path) -> bool | None:
    if not is_windows():
        return None
    import ctypes
    from ctypes import wintypes

    try:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        volume_path = kernel.GetVolumePathNameW
        volume_path.argtypes = (wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD)
        volume_path.restype = wintypes.BOOL
        volume_info = kernel.GetVolumeInformationW
        volume_info.argtypes = (
            wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR, wintypes.DWORD,
        )
        volume_info.restype = wintypes.BOOL
        root = ctypes.create_unicode_buffer(32768)
        if not volume_path(str(directory.resolve()), root, len(root)):
            return None
        flags = wintypes.DWORD()
        if not volume_info(root.value, None, 0, None, None, ctypes.byref(flags), None, 0):
            return None
        return bool(flags.value & FILE_SUPPORTS_REPARSE_POINTS)
    except (OSError, ValueError, AttributeError):
        return None


def is_junction(path: Path) -> bool:
    check = getattr(path, "is_junction", None)
    if check is not None:
        return check()
    if not is_windows():
        return False
    try:
        return path.lstat().st_reparse_tag == stat.IO_REPARSE_TAG_MOUNT_POINT
    except (OSError, AttributeError):
        return False
