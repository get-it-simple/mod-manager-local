from __future__ import annotations

from copy import deepcopy

from PySide6 import QtCore

from ...i18n import t
from ...renames import rename_mod
from ..dialogs import prompts


class RenameController(QtCore.QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window

    def open(self):
        window = self.window
        names = window._selected_mod_names()
        if len(names) != 1 or not window._mods_available(names):
            return
        mod = next((mod for mod in window.current_mods_shown if mod.name == names[0]), None)
        if mod is None:
            return
        name, accepted = prompts.choose_mod_name(window, mod)
        if not accepted or name == mod.name:
            return
        cfg = deepcopy(window.cfg)
        window.labels_controller.flush()

        def completed(result):
            window.labels_controller.remap_mods(result.renamed)
            for _profile, old, new in result.renamed:
                window._invalidate_mod_image(old)
                window._invalidate_mod_image(new)
            window._set_status(result.summary())
            window.refresh_mods([result.new_name])
            window.refresh_presets()
            window.refresh_broken()

        window._run_action(t("rename_mod"), lambda: rename_mod(cfg, mod, name), completed,
                           mod_names=(mod.name, name), barrier=True, config=cfg)
