from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mod_manager import storage
from tests.gui_background import DeferredRunner, inline_background
from tests.qt_support import dispose
from mod_manager.labels import LabelDefinition, LabelState

try:
    from PySide6 import QtCore, QtWidgets
except ModuleNotFoundError:
    QtWidgets = None


@unittest.skipIf(QtWidgets is None, "PySide6 is not installed")
class GameProfileSwitchGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.config_path = root / "config.json"
        self.presets_path = root / "presets.json"
        self.labels_path = root / "labels.json"
        self.profile_dir = root / "profiles"
        self.src_a = root / "src_a"
        self.dst_a = root / "dst_a"
        self.src_b = root / "src_b"
        self.dst_b = root / "dst_b"
        for d in (self.src_a, self.dst_a, self.src_b, self.dst_b):
            d.mkdir()
        (self.src_a / "a.pak").touch()
        (self.src_b / "b.pak").touch()

        self.patches = [
            patch("mod_manager.ui.task_runner.TaskRunner.background", new=inline_background),
            patch("mod_manager.storage.CONFIG_PATH", self.config_path),
            patch("mod_manager.storage.PRESETS_PATH", self.presets_path),
            patch("mod_manager.storage.LABELS_PATH", self.labels_path),
            patch("mod_manager.storage.PROFILE_DATA_DIR", self.profile_dir),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def label_profiles(self):
        (self.src_a / "shared.pak").touch()
        cfg = storage.load_config()
        first = storage.create_game_profile(
            "First Game", {"mods_source_dir": str(self.src_a), "game_mods_dir": str(self.dst_a)}, cfg)
        second = storage.create_game_profile(
            "Second Game", {"mods_source_dir": str(self.src_b), "game_mods_dir": str(self.dst_b)}, cfg)
        for profile, definitions, assignments in (
            (first, {"Common": LabelDefinition(), "Only first": LabelDefinition()},
             {"a.pak": ["Common", "Only first"], "shared.pak": ["Common"]}),
            (second, {"Common": LabelDefinition(), "Only second": LabelDefinition()},
             {"b.pak": ["Common", "Only second"]}),
        ):
            storage.set_active_game_profile(cfg, profile["id"])
            storage.save_config(cfg)
            storage.save_label_state(LabelState(definitions, assignments))
        storage.set_active_game_profile(cfg, first["id"])
        storage.save_config(cfg)
        return cfg, first, second

    def sidebar_entries(self, win):
        model = win.workspace.labels_list.model()
        return [model.index(row, 0).data(QtCore.Qt.UserRole)[:3] for row in range(model.rowCount())]

    def test_labels_and_counts_follow_profile_switch_in_both_directions(self):
        _cfg, first, second = self.label_profiles()
        from mod_manager.ui.app import ModManagerGui

        win = ModManagerGui()
        try:
            self.assertEqual(win.cfg["mods_source_dir"], str(self.src_a))
            self.assertEqual({mod.name for mod in win.library.snapshot.items}, {"a.pak", "shared.pak"})
            self.assertEqual(self.sidebar_entries(win), [("Common", "manual", 2), ("Only first", "manual", 1)])
            win.filters.add("label", "Common")
            win.filters.add("label", "Only first")
            win.filters.add("search", ".pak")
            win.filters.mode = "favorite"
            win._select_game_profile(second["id"])
            self.assertEqual(self.sidebar_entries(win), [("Common", "manual", 1), ("Only second", "manual", 1)])
            self.assertEqual(win.label_filter_box.model().stringList(), ["Common", "Only second"])
            self.assertEqual(win.filters.labels, ("Common",))
            self.assertEqual(win.filters.queries, (".pak",))
            self.assertEqual(win.filters.mode, "favorite")
            win._select_game_profile(first["id"])
            self.assertEqual(self.sidebar_entries(win), [("Common", "manual", 2), ("Only first", "manual", 1)])
            self.assertEqual(win.label_filter_box.model().stringList(), ["Common", "Only first"])
        finally:
            dispose(win)

    def test_profile_load_clears_labels_and_ignores_old_completion_before_retry(self):
        _cfg, _first, second = self.label_profiles()
        from mod_manager.ui.app import ModManagerGui

        win = ModManagerGui()
        deferred = DeferredRunner()
        try:
            win.runner.background = deferred.background
            win.refresh_mods()
            win._select_game_profile(second["id"])
            self.assertNotEqual(win.cfg["active_game_profile_id"], second["id"])
            self.assertTrue(win.runner.barrier_pending)
            deferred.complete(1)
            win._sync_workspace()
            self.assertEqual(self.sidebar_entries(win), [])
            self.assertEqual(win.label_filter_box.model().stringList(), [])
            self.assertFalse(win.workspace.labels_list.isEnabled())
            self.assertFalse(win.label_filter_box.isEnabled())
            win._sidebar_label_requested("Only first")
            self.assertEqual(win.filters.labels, ())
            deferred.complete()
            self.assertEqual(self.sidebar_entries(win), [])
            deferred.complete(error=PermissionError("synthetic profile read failure"))
            self.assertEqual(self.sidebar_entries(win), [])
            self.assertEqual(win.label_filter_box.model().stringList(), [])
            self.assertFalse(win.workspace.labels_list.isEnabled())
            win.library_status.retry.click()
            deferred.complete()
            self.assertEqual(self.sidebar_entries(win), [("Common", "manual", 1), ("Only second", "manual", 1)])
            self.assertTrue(win.workspace.labels_list.isEnabled())
            self.assertTrue(win.label_filter_box.isEnabled())
        finally:
            dispose(win)

    def test_switch_to_empty_profile_clears_both_label_lists(self):
        cfg, _first, _second = self.label_profiles()
        empty = storage.create_game_profile(
            "Empty Game", {"mods_source_dir": str(self.src_b), "game_mods_dir": str(self.dst_b)}, cfg)
        storage.set_active_game_profile(cfg, cfg["game_profiles"][0]["id"])
        storage.save_config(cfg)
        from mod_manager.ui.app import ModManagerGui

        win = ModManagerGui()
        try:
            win._select_game_profile(empty["id"])
            self.assertEqual(self.sidebar_entries(win), [])
            self.assertEqual(win.label_filter_box.model().stringList(), [])
        finally:
            dispose(win)

    def test_switching_active_profile_refreshes_presets_in_gui(self):
        cfg = storage.load_config()
        first = storage.create_game_profile(
            "First Game", {"mods_source_dir": str(self.src_a), "game_mods_dir": str(self.dst_a)}, cfg
        )
        second = storage.create_game_profile(
            "Second Game", {"mods_source_dir": str(self.src_b), "game_mods_dir": str(self.dst_b)}, cfg
        )
        storage.set_active_game_profile(cfg, first["id"])
        storage.save_config(cfg)
        storage.save_presets({"first_preset": ["a.pak"]})

        storage.set_active_game_profile(cfg, second["id"])
        storage.save_config(cfg)
        storage.save_presets({"second_preset": ["b.pak"]})

        storage.set_active_game_profile(cfg, first["id"])
        storage.save_config(cfg)

        from mod_manager.ui.app import ModManagerGui

        win = ModManagerGui()
        try:
            win.refresh_presets()
            self.assertEqual(win.presets_model.keys, ["first_preset"])

            win._select_game_profile(second["id"])
            self.assertEqual(win.cfg.get("active_game_profile_id"), second["id"])
            self.assertEqual(win.presets_model.keys, ["second_preset"])

            win._select_game_profile(first["id"])
            self.assertEqual(win.cfg.get("active_game_profile_id"), first["id"])
            self.assertEqual(win.presets_model.keys, ["first_preset"])
        finally:
            win.close()
            win.deleteLater()


if __name__ == "__main__":
    unittest.main()
