from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import TypedDict

from .i18n import t
from .platform_utils import is_windows


class QuickTool(TypedDict):
    label: str
    path: str


def _parse_tool(value: object, row: int) -> QuickTool:
    label = value.get("label") if isinstance(value, dict) else None
    path = value.get("path") if isinstance(value, dict) else None
    if not isinstance(label, str) or not label.strip():
        raise ValueError(t("quick_tool_missing_label", row=row))
    if not isinstance(path, str) or not path.strip():
        raise ValueError(t("quick_tool_missing_path", row=row))
    path = path.strip()
    if "\0" in path or not (PureWindowsPath(path).is_absolute() or PurePosixPath(path).is_absolute()):
        raise ValueError(t("quick_tool_absolute_path", row=row))
    return {"label": label.strip(), "path": path}


def parse_quick_tools(value: object, *, strict: bool = True, ignore_blank: bool = False) -> list[QuickTool]:
    if not isinstance(value, list):
        if strict:
            raise ValueError(t("quick_tools_invalid_list"))
        return []
    tools = []
    for row, entry in enumerate(value, start=1):
        if ignore_blank and entry == {"label": "", "path": ""}:
            continue
        try:
            tools.append(_parse_tool(entry, row))
        except ValueError:
            if strict:
                raise
    return tools


def executable_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(t("quick_tool_unusable_path"))
    if not path.is_file():
        raise FileNotFoundError(t("quick_tool_file_missing"))
    if is_windows() and path.suffix.lower() not in {".exe", ".lnk"}:
        raise ValueError(t("quick_tool_windows_types"))
    return path
