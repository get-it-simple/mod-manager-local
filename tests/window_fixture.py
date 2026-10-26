from __future__ import annotations

import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from tests.qt_support import dispose, qt_app, qt_available

from app_paths import DEFAULT_CONFIG
from mod_manager.models import ModItem
from mod_manager.labels import LabelDefinition, LabelState

if qt_available():
    from PySide6 import QtCore

FAKE_SRC = Path(tempfile.gettempdir()) / "mm_fixture_source"
FAKE_DEST = Path(tempfile.gettempdir()) / "mm_fixture_game"


def mod_item(name: str, installed: bool = False, is_dir: bool = False) -> ModItem:
    return ModItem(name=name, src=FAKE_SRC / name, dest=FAKE_DEST / name, is_dir=is_dir, installed=installed)


def base_config(**overrides) -> dict:
    cfg = deepcopy(DEFAULT_CONFIG)
    cfg.update({
        "mods_source_dir": str(FAKE_SRC),
        "game_mods_dir": str(FAKE_DEST),
        "mod_extensions": ".pak,.utoc",
        "window_width": 900,
        "window_height": 600,
    })
    cfg.update(overrides)
    return cfg


class WindowTestCase(unittest.TestCase):
    """Builds a real ModManagerGui with the storage and mod layers stubbed out."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.qt_app = qt_app()

    def setUp(self) -> None:
        self.cfg = base_config(**getattr(self, "config_overrides", {}))
        self.mods = [mod_item("combat.pak", installed=True), mod_item("ui.pak", installed=False)]
        self.presets = {"core": ["combat.pak"], "ui": ["ui.pak"]}
        self.broken = [mod_item("missing.pak", installed=True)]
        self.patchers = [
            # storage.save_config is imported lazily inside workers, so it must be patched at
            # its source or a test would overwrite the real config.json next to the app.
            patch("mod_manager.storage.save_config"),
            patch("mod_manager.ui.dialogs.prompts.review_plan", return_value=True),
            patch("mod_manager.preset_plan.load_presets", side_effect=lambda: self.presets),
            patch("mod_manager.preset_plan.discover_mods", side_effect=lambda _cfg: self.mods),
            patch("mod_manager.preset_plan.mark_preset_managed"),
            patch("mod_manager.ui.app.load_config", return_value=self.cfg),
            patch("mod_manager.ui.app.save_config"),
            patch("mod_manager.ui.app.ensure_paths", return_value=True),
            patch("mod_manager.ui.app.mod_image_path", return_value=None),
            patch("mod_manager.ui.app.mods_view", return_value=(self.mods, self.mods, 1, 1, {"combat.pak": "combat"})),
            patch("mod_manager.ui.app.mods_records", return_value={"combat.pak": {"last_managed": "2026-01-01 10:00:00"}}),
            patch("mod_manager.ui.app.load_favorites", return_value=set()),
            patch("mod_manager.ui.controllers.labels_controller.load_label_state", side_effect=lambda: LabelState({"combat": LabelDefinition()}, {"combat.pak": ["combat"]})),
            patch("mod_manager.ui.app.presets_view", return_value=(self.presets, list(self.presets), ["core", "ui"], 1, 1)),
            patch("mod_manager.ui.app.presets_records", return_value={"core": {"last_managed": "2026-01-02 10:00:00"}}),
            patch("mod_manager.ui.app.list_installed_mods", return_value=[self.mods[0]]),
            patch("mod_manager.ui.app.list_broken_links", return_value=self.broken),
        ]
        for patcher in self.patchers:
            patcher.start()
        from mod_manager.ui.app import ModManagerGui

        self.window = ModManagerGui()
        self.window.hide()
        self.qt_app.processEvents()

    def tearDown(self) -> None:
        dispose(self.window)
        for patcher in reversed(self.patchers):
            patcher.stop()

    def run_action_inline(self, label, worker, done=None, file_key="global") -> None:
        result = worker()
        if done:
            done(result)

    def use_inline_runner(self) -> None:
        self.window._run_action = self.run_action_inline

    def select_mod_rows(self, *rows: int) -> None:
        view = self.window._current_mod_view()
        selection_model = view.selectionModel()
        selection_model.clearSelection()
        for row in rows:
            left = self.window.mods_model.index(row, 0)
            right = self.window.mods_model.index(row, self.window.mods_model.columnCount() - 1)
            selection_model.select(QtCore.QItemSelection(left, right), QtCore.QItemSelectionModel.Select)
        self.qt_app.processEvents()
