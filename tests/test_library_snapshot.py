from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app_paths import DEFAULT_CONFIG
from mod_manager import storage
from mod_manager.labels import LabelDefinition, LabelState
from mod_manager.library_snapshot import load_library_snapshot
from mod_manager.mods import mods_view
from mod_manager.storage_policy import storage_policy


class LibrarySnapshotTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for field, filename in (("CONFIG_PATH", "config.json"), ("PRESETS_PATH", "presets.json"),
                                ("LABELS_PATH", "labels.json"), ("PROFILE_DATA_DIR", "profiles")):
            patcher = patch.object(storage, field, self.root / filename)
            patcher.start()
            self.addCleanup(patcher.stop)
        source, target = self.root / "mods", self.root / "game"
        source.mkdir()
        target.mkdir()
        (source / "combat.pak").write_bytes(b"combat")
        (source / "ui.pak").write_bytes(b"ui")
        self.cfg = storage.normalize_game_profiles({**deepcopy(DEFAULT_CONFIG), "mods_source_dir": str(source),
                                                    "game_mods_dir": str(target), "page_size": 1})
        storage.save_config(self.cfg)
        storage.save_label_state(LabelState({"Combat": LabelDefinition()}, {"combat.pak": ["Combat"]}))
        storage.save_presets({"core": ["combat.pak"]})

    def contents(self):
        return {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}

    def test_snapshot_and_projection_never_write_and_match_shared_view(self):
        before = self.contents()
        snapshot = load_library_snapshot(self.cfg)
        self.assertEqual(self.contents(), before)
        for search, labels, order, favorite, state in (((), (), "d", False, "all"),
                                                      (("ui",), (), "name", False, "all"),
                                                      ((), ("Combat",), "-name", False, "not_installed"),
                                                      ((), (), "created_date", False, "all")):
            with self.subTest(search=search, labels=labels, order=order):
                with storage_policy(strict=True, migrate=False, config=self.cfg):
                    expected = mods_view(self.cfg, 1, labels, search, order, favorite, state_filter=state)
                with patch("mod_manager.mods.discover_mods", side_effect=AssertionError("projection scanned disk")):
                    actual = mods_view(self.cfg, 1, labels, search, order, favorite, state_filter=state, snapshot=snapshot)
                self.assertEqual([[mod.name for mod in values] for values in actual[:2]],
                                 [[mod.name for mod in values] for values in expected[:2]])
                self.assertEqual(actual[2:4], expected[2:4])
        self.assertEqual(self.contents(), before)

    def test_metadata_stays_bound_to_requested_profile_after_saved_profile_changes(self):
        first_cfg = deepcopy(self.cfg)
        storage.create_game_profile("Another", {"mods_source_dir": str(self.root / "mods"),
                                               "game_mods_dir": str(self.root / "game")}, self.cfg)
        storage.save_config(self.cfg)
        storage.save_presets({"other": ["ui.pak"]})
        snapshot = load_library_snapshot(first_cfg)
        self.assertEqual(snapshot.profile_id, first_cfg["active_game_profile_id"])
        self.assertEqual(snapshot.presets, {"core": ["combat.pak"]})
        self.assertEqual(snapshot.labels["combat.pak"], "Combat")
