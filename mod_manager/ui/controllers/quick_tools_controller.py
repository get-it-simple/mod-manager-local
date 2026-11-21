from __future__ import annotations

import os

from PySide6 import QtCore

from ...i18n import t
from ...platform_utils import is_windows
from ...quick_tools import executable_path
from ..dialogs import prompts


def launch_quick_tool(parent, label: str, path: str) -> None:
    try:
        target = executable_path(path)
        if is_windows() and target.suffix.lower() == ".lnk":
            os.startfile(str(target))
        else:
            started, _pid = QtCore.QProcess.startDetached(str(target), [], str(target.parent))
            if not started:
                raise OSError(t("quick_tool_process_failed"))
    except (OSError, ValueError) as error:
        prompts.show_error(parent, t("quick_tools"), t("quick_tool_launch_error", label=label, path=path, error=str(error)))
