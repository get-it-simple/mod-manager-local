from __future__ import annotations

import importlib
import importlib.abc
import sys
from pathlib import Path


class BlockImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if sys.argv[1] == "gui" and fullname.startswith("mod_manager.cli"):
            raise ModuleNotFoundError(f"Blocked import: {fullname}")
        blocked = ("mod_manager.cli", "mod_manager.cli_utils", "mod_manager.cli_parser", "mod_manager.cli_commands", "mod_manager.menus") if sys.argv[1] == "gui" else ("PySide6", "prompt_toolkit")
        if any(fullname == name or fullname.startswith(name + ".") for name in blocked):
            raise ModuleNotFoundError(f"Blocked import: {fullname}")
        return None


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.meta_path.insert(0, BlockImports())
if sys.argv[1] == "gui":
    importlib.import_module("mod_manager.ui.app")
    print("GUI imports without CLI")
else:
    from mod_manager.cli import run_cli

    raise SystemExit(run_cli(["help", "mods", "toggle"]))
