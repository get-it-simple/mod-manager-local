from __future__ import annotations

from copy import deepcopy
import unittest
from unittest.mock import patch

from tests.cli_support import CliEnvironment
from mod_manager import storage
from mod_manager.label_icons import icon_path, store_icon
from mod_manager.labels import LabelDefinition, LabelState, merge_label_states
from mod_manager.mods import discover_mods
from mod_manager.storage_policy import storage_policy
from mod_manager.trash import list_entries, preview_path, restore_entry, trash_mod


class LabelIconStorageTests(CliEnvironment, unittest.TestCase):
    def test_icon_round_trip_rename_profile_isolation_and_cli_preserve_metadata(self):
        reference = store_icon(b"synthetic icon")
        state = LabelState({"Same": LabelDefinition(icon=reference, icon_only=True)}, {"one.pak": ["Same"]})
        storage.save_label_state(state)
        self.assertEqual(storage.load_label_state(), state)
        state.rename("Same", "Renamed")
        storage.save_label_state(state)
        self.add_mods("one.pak")
        before = self.snapshot()
        code, output, errors = self.request(["mods", "list"])
        self.assertEqual((code, errors), (0, ""))
        self.assertIn("Renamed", output)
        self.assertEqual(self.snapshot(), before)
        cfg = storage.load_config()
        storage.create_game_profile("Other", {"mods_source_dir": str(self.source), "game_mods_dir": str(self.game)}, cfg)
        storage.set_active_game_profile(cfg, cfg["game_profiles"][-1]["id"])
        storage.save_config(cfg)
        storage.save_label_state(LabelState({"Renamed": LabelDefinition()}))
        self.assertEqual(storage.load_label_state().definitions["Renamed"].icon, "")
        storage.set_active_game_profile(cfg, "test-game")
        storage.save_config(cfg)
        self.assertEqual(storage.load_label_state().definitions["Renamed"].icon, reference)
        self.assertEqual(icon_path(reference).read_bytes(), b"synthetic icon")

    def test_icon_merge_preserves_independent_edits_and_reports_conflicts(self):
        saved = LabelState({"A": LabelDefinition()})
        edited, current = deepcopy(saved), deepcopy(saved)
        edited.definitions["A"].icon = store_icon(b"one")
        current.definitions["A"].icon_only = True
        merged = merge_label_states(saved, edited, current, {})
        self.assertEqual(merged.definitions["A"].icon, edited.definitions["A"].icon)
        self.assertTrue(merged.definitions["A"].icon_only)
        current.definitions["A"].icon = store_icon(b"two")
        with self.assertRaisesRegex(ValueError, "changed"):
            merge_label_states(saved, edited, current, {})

    def test_invalid_references_and_flags_are_rejected_without_changing_metadata(self):
        before = self.snapshot()
        for reference in ("../outside.png", "C:/private.png", "label-icons/../outside.png"):
            with self.subTest(reference=reference), self.assertRaises(ValueError):
                storage.save_label_state(LabelState({"A": LabelDefinition(icon=reference)}))
        with self.assertRaises(ValueError):
            LabelDefinition.from_record({"icon_only": "yes"})
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(LabelDefinition.from_record({"mode": "manual"}), LabelDefinition())

    def test_failed_icon_publication_keeps_prior_files_and_removes_temporary_file(self):
        reference = store_icon(b"original")
        before = self.snapshot()
        with patch("mod_manager.label_icons.os.replace", side_effect=PermissionError("locked")):
            with self.assertRaises(PermissionError):
                store_icon(b"replacement")
        self.assertEqual(icon_path(reference).read_bytes(), b"original")
        self.assertEqual(self.snapshot(), before)

    def test_trash_restores_deleted_label_definition_and_retains_icon(self):
        cfg = storage.load_config()
        self.add_mods("sample.pak")
        reference = store_icon(b"synthetic icon")
        definition = LabelDefinition(icon=reference, icon_only=True)
        with storage_policy(config=cfg):
            storage.save_label_state(LabelState({"A": definition}, {"sample.pak": ["A"]}))
            trash_mod(cfg, discover_mods(cfg)[0])
            entry, = list_entries(cfg)
            state = storage.load_label_state()
            state.delete("A")
            storage.save_label_state(state)
            restore_entry(cfg, entry)
            self.assertEqual(storage.load_label_state().definitions["A"], definition)
            self.assertEqual(storage.load_label_state().members("sample.pak"), ("A",))
        self.assertFalse((self.game / "sample.pak").exists())
        self.assertTrue(icon_path(reference).is_file())

    def test_state_column_migrates_old_default_and_keeps_custom_width(self):
        self.cfg["placeholder_image_col_width"] = 56
        self.write_config()
        self.assertEqual(storage.load_config()["placeholder_image_col_width"], 32)
        self.cfg["placeholder_image_col_width"] = 72
        self.write_config()
        self.assertEqual(storage.load_config()["placeholder_image_col_width"], 72)


class TrashInternalArtworkTests(CliEnvironment, unittest.TestCase):
    def test_retained_internal_preview_survives_profile_change_and_manual_preview_wins(self):
        cfg = storage.load_config()
        cfg["mod_mode"] = "directories"
        cfg["mod_icon_path"] = "assets/icon.png"
        folder = self.source / "Folder"
        (folder / "assets").mkdir(parents=True)
        (folder / "assets" / "icon.png").write_bytes(b"internal")
        (folder / "mod.pak").write_bytes(b"mod")
        trash_mod(cfg, discover_mods(cfg)[0])
        entry, = list_entries(cfg)
        retained = preview_path(entry, cfg)
        self.assertEqual(retained.read_bytes(), b"internal")
        self.assertTrue(retained.is_relative_to(entry.path))
        cfg["mod_icon_path"] = "changed.png"
        self.assertEqual(preview_path(entry, cfg), retained)
        restore_entry(cfg, entry)
        self.assertEqual((folder / "assets" / "icon.png").read_bytes(), b"internal")
        artwork = self.source / "images" / "Folder.png"
        artwork.parent.mkdir()
        artwork.write_bytes(b"manual")
        cfg["mod_icon_path"] = "assets/icon.png"
        trash_mod(cfg, discover_mods(cfg)[0])
        entry, = list_entries(cfg)
        self.assertEqual(preview_path(entry, cfg).read_bytes(), b"manual")

    def test_legacy_trash_uses_originating_profile_and_rejects_unsafe_icon_paths(self):
        cfg = storage.load_config()
        cfg["mod_mode"] = "directories"
        cfg["mod_icon_path"] = "icon.png"
        cfg["game_profiles"][0]["mod_icon_path"] = "icon.png"
        folder = self.source / "Folder"
        folder.mkdir()
        (folder / "icon.png").write_bytes(b"internal")
        trash_mod(cfg, discover_mods(cfg)[0])
        entry, = list_entries(cfg)
        del entry.data["mod_icon_path"]
        self.assertEqual(preview_path(entry, cfg).read_bytes(), b"internal")
        entry.data["mod_icon_path"] = "../outside.png"
        self.assertIsNone(preview_path(entry, cfg))
        entry.data["mod_icon_path"] = "missing.png"
        self.assertIsNone(preview_path(entry, cfg))

