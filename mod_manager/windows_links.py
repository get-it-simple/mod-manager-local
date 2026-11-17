from __future__ import annotations

import ctypes
from ctypes import wintypes
import errno
from functools import lru_cache
import os
from pathlib import Path
import struct


IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003
FSCTL_SET_REPARSE_POINT = 0x000900A4
MAXIMUM_REPARSE_DATA_BUFFER_SIZE = 16384
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ_WRITE_DELETE = 0x7
OPEN_EXISTING = 3
FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


@lru_cache(maxsize=1)
def _kernel32():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateDirectoryW.argtypes = (wintypes.LPCWSTR, wintypes.LPVOID)
    kernel.CreateDirectoryW.restype = wintypes.BOOL
    kernel.CreateFileW.argtypes = (
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    )
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.DeviceIoControl.argtypes = (
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
        wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID,
    )
    kernel.DeviceIoControl.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    return kernel


def _junction_data(source: Path) -> bytes:
    target = os.path.abspath(source)
    if target.startswith("\\\\?\\"):
        target = target[4:]
    if target.startswith("\\\\"):
        target = "UNC\\" + target[2:]
    substitute = ("\\??\\" + target).encode("utf-16-le", errors="surrogatepass")
    display = os.path.abspath(source).encode("utf-16-le", errors="surrogatepass")
    paths = substitute + b"\0\0" + display + b"\0\0"
    if 16 + len(paths) > MAXIMUM_REPARSE_DATA_BUFFER_SIZE:
        raise OSError(errno.ENAMETOOLONG, os.strerror(errno.ENAMETOOLONG), str(source))
    return struct.pack(
        "<IHHHHHH", IO_REPARSE_TAG_MOUNT_POINT, 8 + len(paths), 0,
        0, len(substitute), len(substitute) + 2, len(display),
    ) + paths


def create_junction(source: Path, destination: Path) -> None:
    data = _junction_data(source)
    kernel = _kernel32()
    if not kernel.CreateDirectoryW(str(destination), None):
        raise ctypes.WinError(ctypes.get_last_error())
    handle = INVALID_HANDLE_VALUE
    try:
        try:
            handle = kernel.CreateFileW(
                str(destination), GENERIC_WRITE, FILE_SHARE_READ_WRITE_DELETE, None,
                OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS, None,
            )
            if handle == INVALID_HANDLE_VALUE:
                raise ctypes.WinError(ctypes.get_last_error())
            returned = wintypes.DWORD()
            buffer = ctypes.create_string_buffer(data)
            if not kernel.DeviceIoControl(
                handle, FSCTL_SET_REPARSE_POINT, buffer, len(data),
                None, 0, ctypes.byref(returned), None,
            ):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            if handle != INVALID_HANDLE_VALUE:
                kernel.CloseHandle(handle)
    except Exception as error:
        try:
            os.rmdir(destination)
        except OSError as cleanup_error:
            raise OSError(f"{error}; {destination}: {cleanup_error}") from error
        raise
