from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest
from unittest.mock import patch

from tests.cli_support import CliEnvironment
from mod_manager import storage
from mod_manager.import_registry import directory_mods, register_directory_mod
from mod_manager.labels import LabelDefinition, LabelState
from mod_manager.mods import discover_mods
from mod_manager.storage_policy import storage_policy
from mod_manager.trash import (
    TRASH_DIRECTORY, delete_entry, list_entries, purge_entries, restore_entry, trash_mod,
)


class TrashTests(CliEnvironment, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.cfg = storage.load_config()
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def mods(self):
        return discover_mods(self.cfg)

    def test_active_copy_round_trip_preserves_payload_artwork_and_metadata(self):
        self.add_mods("sample.pak")
        art = self.source / "images" / "sample.pak.png"
        art.parent.mkdir()
        art.write_bytes(b"synthetic-artwork")
        (self.game / "sample.pak").write_bytes(b"sample.pak")
        with storage_policy(config=self.cfg):
            storage.save_label_state(LabelState({"Test": LabelDefinition()}, {"sample.pak": ["Test"]}))
            storage.update_favorites(self.cfg, ["sample.pak"], True)
            storage.save_presets({"core": ["sample.pak"]})
            trash_mod(self.cfg, self.mods()[0], self.now)
            self.assertFalse((self.source / "sample.pak").exists())
            self.assertFalse((self.game / "sample.pak").exists())
            self.assertFalse(art.exists())
            self.assertEqual(self.mods(), [])
            self.assertNotIn("sample.pak", storage.load_mod_records())
            self.assertEqual(storage.load_presets()["core"], [])
            entry, = list_entries(self.cfg)
            self.assertEqual(entry.data["expires_at"], (self.now + timedelta(days=14)).isoformat())
            restore_entry(self.cfg, entry)
            self.assertEqual((self.source / "sample.pak").read_text(), "sample.pak")
            self.assertEqual(art.read_bytes(), b"synthetic-artwork")
            self.assertFalse((self.game / "sample.pak").exists())
            self.assertEqual(storage.load_label_state().assignments["sample.pak"], ["Test"])
            self.assertEqual(storage.load_favorites(self.cfg), {"sample.pak"})
            self.assertEqual(storage.load_presets()["core"], ["sample.pak"])
            self.assertEqual(list_entries(self.cfg), [])

    def test_group_move_failure_rolls_back_every_member(self):
        self.cfg["mod_group_extensions"] = ".pak,.utoc"
        self.add_mods("sample.pak", "sample.utoc")
        mod, = self.mods()
        rename = Path.rename

        def fail_second(source, target):
            if source == self.source / "sample.utoc":
                raise PermissionError("synthetic locked file")
            return rename(source, target)

        with patch.object(Path, "rename", fail_second):
            with self.assertRaises(PermissionError):
                trash_mod(self.cfg, mod, self.now)
        self.assertEqual((self.source / "sample.pak").read_text(), "sample.pak")
        self.assertEqual((self.source / "sample.utoc").read_text(), "sample.utoc")
        self.assertEqual(list_entries(self.cfg), [])

    def test_directory_registration_and_contents_round_trip(self):
        folder = self.source / "Folder"
        (folder / "nested").mkdir(parents=True)
        (folder / "nested" / "mod.pak").write_bytes(b"nested")
        register_directory_mod(self.cfg, "Folder")
        trash_mod(self.cfg, self.mods()[0], self.now)
        self.assertEqual(directory_mods(self.cfg), set())
        entry, = list_entries(self.cfg)
        restore_entry(self.cfg, entry)
        self.assertEqual((folder / "nested" / "mod.pak").read_bytes(), b"nested")
        self.assertEqual(directory_mods(self.cfg), {"folder"})

    def test_retention_uses_utc_boundary_and_never_deletes_active_library(self):
        self.add_mods("old.pak", "kept.pak")
        mod = next(mod for mod in self.mods() if mod.name == "old.pak")
        trash_mod(self.cfg, mod, self.now)
        self.assertFalse(purge_entries(self.cfg, expired_only=True, now=self.now + timedelta(days=14, microseconds=-1)).items)
        result = purge_entries(self.cfg, expired_only=True, now=self.now + timedelta(days=14))
        self.assertEqual([item.success for item in result.items], [True])
        self.assertEqual(list_entries(self.cfg), [])
        self.assertEqual((self.source / "kept.pak").read_text(), "kept.pak")

    def test_restore_conflict_preserves_both_copies_and_supports_new_name(self):
        self.add_mods("sample.pak")
        trash_mod(self.cfg, self.mods()[0], self.now)
        entry, = list_entries(self.cfg)
        (self.source / "sample.pak").write_bytes(b"replacement")
        with self.assertRaises(FileExistsError):
            restore_entry(self.cfg, entry)
        restore_entry(self.cfg, entry, "restored.pak")
        self.assertEqual((self.source / "sample.pak").read_bytes(), b"replacement")
        self.assertEqual((self.source / "restored.pak").read_text(), "sample.pak")

    def test_manual_partial_and_complete_removal_are_reconciled(self):
        self.cfg["mod_group_extensions"] = ".pak,.utoc"
        self.add_mods("sample.pak", "sample.utoc")
        trash_mod(self.cfg, self.mods()[0], self.now)
        entry, = list_entries(self.cfg)
        (entry.path / entry.data["files"][0]["stored"]).unlink()
        partial, = list_entries(self.cfg)
        self.assertEqual(len(partial.missing), 1)
        with self.assertRaises(FileNotFoundError):
            restore_entry(self.cfg, partial)
        (entry.path / entry.data["files"][1]["stored"]).unlink()
        self.assertEqual(list_entries(self.cfg), [])

    def test_uninstall_failure_keeps_the_source_out_of_trash(self):
        self.add_mods("sample.pak")
        (self.game / "sample.pak").write_bytes(b"installed")
        with patch("mod_manager.mods.remove_path", return_value=(False, "synthetic locked destination")):
            with self.assertRaises(OSError):
                trash_mod(self.cfg, self.mods()[0], self.now)
        self.assertTrue((self.source / "sample.pak").is_file())
        self.assertTrue((self.game / "sample.pak").is_file())
        self.assertEqual(list_entries(self.cfg), [])

    def test_restore_metadata_failure_returns_files_to_trash(self):
        self.add_mods("sample.pak")
        trash_mod(self.cfg, self.mods()[0], self.now)
        entry, = list_entries(self.cfg)
        with patch("mod_manager.trash._restore_metadata", side_effect=PermissionError("synthetic metadata lock")):
            with self.assertRaises(PermissionError):
                restore_entry(self.cfg, entry)
        self.assertFalse((self.source / "sample.pak").exists())
        recovered, = list_entries(self.cfg)
        self.assertFalse(recovered.missing)
        restore_entry(self.cfg, recovered)
        self.assertTrue((self.source / "sample.pak").is_file())

    def test_deleted_profile_keeps_trash_visible_and_blocks_restore(self):
        self.add_mods("sample.pak")
        trash_mod(self.cfg, self.mods()[0], self.now)
        cfg = {"game_profiles": [], "active_game_profile_id": ""}
        entry, = list_entries(cfg)
        with self.assertRaises(ValueError):
            restore_entry(cfg, entry)
        self.assertTrue(entry.path.is_dir())
        delete_entry(entry)
        self.assertEqual(list_entries(cfg), [])

    def test_invalid_original_path_never_restores_outside_library(self):
        self.add_mods("sample.pak")
        trash_mod(self.cfg, self.mods()[0], self.now)
        entry, = list_entries(self.cfg)
        entry.data["files"][0]["original"] = "../outside.pak"
        storage.save_json(entry.path / "entry.json", entry.data)
        with self.assertRaises(ValueError):
            list_entries(self.cfg)
        self.assertFalse((self.root / "outside.pak").exists())

    def test_cli_requires_confirmation_and_restores_without_installation(self):
        self.add_mods("sample.pak")
        self.assertEqual(self.request(["mods", "delete", "1"])[0], 1)
        self.assertTrue((self.source / "sample.pak").exists())
        self.assertEqual(self.request(["mods", "delete", "1", "--yes"])[0], 0)
        entry, = list_entries(self.cfg)
        code, listing, _errors = self.request(["trash", "list"])
        self.assertEqual(code, 0)
        self.assertIn(entry.identifier, listing)
        self.assertEqual(self.request(["trash", "delete", entry.identifier])[0], 1)
        self.assertEqual(self.request(["trash", "restore", entry.identifier])[0], 0)
        self.assertTrue((self.source / "sample.pak").exists())
        self.assertFalse((self.game / "sample.pak").exists())

    def test_failed_rollback_retains_original_payload_when_source_name_was_recreated(self):
        self.cfg["mod_group_extensions"] = ".pak,.utoc"
        self.add_mods("sample.pak", "sample.utoc")
        rename = Path.rename

        def collide_during_second_move(source, target):
            if source == self.source / "sample.utoc":
                (self.source / "sample.pak").write_bytes(b"new-user-file")
                raise PermissionError("synthetic second member lock")
            return rename(source, target)

        with patch.object(Path, "rename", collide_during_second_move):
            with self.assertRaises(FileExistsError):
                trash_mod(self.cfg, self.mods()[0], self.now)
        entry, = (self.source / TRASH_DIRECTORY).iterdir()
        data = storage.load_json(entry / "entry.json", {})
        self.assertEqual((entry / data["files"][0]["stored"]).read_bytes(), b"sample.pak")
        self.assertEqual((self.source / "sample.pak").read_bytes(), b"new-user-file")
        self.assertEqual((self.source / "sample.utoc").read_bytes(), b"sample.utoc")

    def test_preparing_journal_recovers_files_and_metadata_after_restart(self):
        self.add_mods("sample.pak")
        trash_mod(self.cfg, self.mods()[0], self.now)
        entry, = list_entries(self.cfg)
        data = {**entry.data, "state": "preparing"}
        storage.save_json(entry.path / "entry.json", data)
        self.assertEqual(list_entries(self.cfg), [])
        self.assertEqual((self.source / "sample.pak").read_bytes(), b"sample.pak")

    def test_restoring_journal_returns_interrupted_moves_to_trash(self):
        self.add_mods("sample.pak")
        trash_mod(self.cfg, self.mods()[0], self.now)
        entry, = list_entries(self.cfg)
        member = entry.data["files"][0]
        (entry.path / member["stored"]).rename(self.source / member["original"])
        data = {**entry.data, "state": "restoring", "restore_moves": [member]}
        storage.save_json(entry.path / "entry.json", data)
        recovered, = list_entries(self.cfg)
        self.assertFalse((self.source / "sample.pak").exists())
        self.assertFalse(recovered.missing)
        restore_entry(self.cfg, recovered)
        self.assertEqual((self.source / "sample.pak").read_bytes(), b"sample.pak")

    def test_import_cannot_replace_the_application_trash_directory(self):
        from mod_manager.imports import PlannedMod, publish_plan, resolve_plans

        self.add_mods("sample.pak")
        trash_mod(self.cfg, self.mods()[0], self.now)
        entry, = list_entries(self.cfg)
        payload = self.root / "incoming.pak"
        payload.write_bytes(b"incoming")
        plan = PlannedMod(TRASH_DIRECTORY, ((payload, Path("incoming.pak")),), True, replace_existing=True)
        ok, _message = publish_plan(self.cfg, plan)
        self.assertFalse(ok)
        resolved, = resolve_plans(self.cfg, [plan], lambda _name: "replace")
        self.assertNotEqual(resolved.name, TRASH_DIRECTORY)
        self.assertTrue(entry.path.exists())

    def test_folder_link_deactivation_never_deletes_its_source(self):
        from mod_manager.links import mklink

        folder = self.source / "Linked"
        folder.mkdir()
        (folder / "mod.pak").write_bytes(b"linked-payload")
        register_directory_mod(self.cfg, "Linked")
        self.cfg["install_mode"] = "link"
        ok, message = mklink(folder, self.game / "Linked")
        self.assertTrue(ok, message)
        trash_mod(self.cfg, self.mods()[0], self.now)
        self.assertFalse((self.game / "Linked").exists())
        entry, = list_entries(self.cfg)
        restore_entry(self.cfg, entry)
        self.assertEqual((folder / "mod.pak").read_bytes(), b"linked-payload")

    def test_overlapping_game_directory_cannot_remove_source_before_trashing(self):
        self.add_mods("sample.pak")
        self.cfg["game_mods_dir"] = str(self.source)
        self.cfg["install_mode"] = "copy"
        with self.assertRaises(ValueError):
            trash_mod(self.cfg, self.mods()[0], self.now)
        self.assertEqual((self.source / "sample.pak").read_bytes(), b"sample.pak")
        self.assertEqual(list_entries(self.cfg), [])

    def test_unconfigured_game_directory_skips_deactivation(self):
        self.add_mods("sample.pak")
        (self.game / "sample.pak").write_bytes(b"unrelated-file")
        mod, = self.mods()
        self.cfg["game_mods_dir"] = ""
        trash_mod(self.cfg, mod, self.now)
        self.assertEqual((self.game / "sample.pak").read_bytes(), b"unrelated-file")
        entry, = list_entries(self.cfg)
        self.assertEqual((entry.path / entry.data["files"][0]["stored"]).read_bytes(), b"sample.pak")
