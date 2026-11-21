from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from mod_manager import storage
from mod_manager.import_registry import directory_mods, register_directory_mod
from mod_manager.labels import LabelDefinition, LabelState
from mod_manager.mods import change_mods, discover_mods
from mod_manager.renames import _prepare, _write_journal, recover_renames, rename_mod
from mod_manager.storage_policy import storage_policy
from tests.cli_support import CliEnvironment


class RenameTests(CliEnvironment, unittest.TestCase):

    def test_native_file_links_and_directory_junctions_keep_new_targets(self):
        storage.update_game_profile(self.cfg, "test-game", {"install_mode": "link"})
        self.add_mods("sample.pak")
        folder = self.source / "Original"
        folder.mkdir()
        (folder / "data.bin").write_bytes(b"folder-payload")
        self.seed_metadata(self.cfg, ["sample.pak", "Original"])
        with storage_policy(config=self.cfg):
            installed = change_mods(discover_mods(self.cfg), "install")
            self.assertFalse(installed.errors, installed.items)
        for old, new in (("sample.pak", "changed.pak"), ("Original", "Changed")):
            mod = next(mod for mod in discover_mods(self.cfg) if mod.name == old)
            rename_mod(self.cfg, mod, new)
            self.assertFalse((self.game / old).exists())
            self.assertTrue((self.game / new).samefile(self.source / new))
        self.assertEqual((self.game / "Changed/data.bin").read_bytes(), b"folder-payload")

    def test_failed_rollback_retains_original_payload_until_conflict_is_resolved(self):
        storage.update_game_profile(self.cfg, "test-game", {"mod_group_extensions": ".pak,.utoc"})
        self.add_mods("sample.pak", "sample.utoc")
        original_rename = Path.rename
        calls = 0

        def fail_second_stage(path, target):
            nonlocal calls
            if path.parent == self.source and Path(target).name.startswith(".mod-rename-"):
                calls += 1
                if calls == 2:
                    (self.source / "sample.pak").write_bytes(b"external-file")
                    raise PermissionError("synthetic second move failure")
            return original_rename(path, target)

        with patch.object(Path, "rename", fail_second_stage), self.assertRaises(OSError) as failure:
            rename_mod(self.cfg, discover_mods(self.cfg)[0], "changed.pak")
        self.assertIn("retained", str(failure.exception))
        self.assertEqual((self.source / "sample.pak").read_bytes(), b"external-file")
        journal, = (self.profiles / "renames").glob("*.json")
        data = storage.load_json(journal, {})
        self.assertEqual(Path(data["sources"][0]["stage"]).read_bytes(), b"sample.pak")
        (self.source / "sample.pak").unlink()
        recover_renames(self.cfg)
        self.assertEqual((self.source / "sample.pak").read_bytes(), b"sample.pak")
        self.assertFalse(journal.exists())
    def setUp(self):
        super().setUp()
        self.cfg = storage.load_config()

    def seed_metadata(self, cfg, names):
        with storage_policy(config=cfg):
            storage.save_label_state(LabelState({"Manual": LabelDefinition()}, {name: ["Manual"] for name in names}))
            storage.update_favorites(cfg, names, True)
            storage.save_presets({"Core": list(names), "Other": [names[0], "unrelated.pak"]})
            storage.mark_preset_managed("Core", "installed")

    def test_active_copy_keeps_files_artwork_labels_favorites_and_every_preset(self):
        self.add_mods("sample.pak")
        art = self.source / "images" / "sample.pak.png"
        art.parent.mkdir()
        art.write_bytes(b"synthetic-artwork")
        self.seed_metadata(self.cfg, ["sample.pak"])
        with storage_policy(config=self.cfg):
            self.assertFalse(change_mods(discover_mods(self.cfg), "install").errors)
            before = deepcopy(storage.load_preset_records())
        result = rename_mod(self.cfg, discover_mods(self.cfg)[0], "Нова назва.pak")
        self.assertEqual(result.new_name, "Нова назва.pak")
        self.assertFalse((self.source / "sample.pak").exists())
        self.assertFalse((self.game / "sample.pak").exists())
        self.assertEqual((self.source / result.new_name).read_bytes(), b"sample.pak")
        self.assertEqual((self.game / result.new_name).read_bytes(), b"sample.pak")
        self.assertEqual((art.parent / (result.new_name + ".png")).read_bytes(), b"synthetic-artwork")
        with storage_policy(config=self.cfg):
            self.assertEqual(storage.load_label_state().assignments, {result.new_name: ["Manual"]})
            self.assertEqual(storage.load_favorites(self.cfg), {result.new_name})
            after = storage.load_preset_records()
            self.assertEqual(after["Core"]["mods"], [result.new_name])
            self.assertEqual(after["Other"]["mods"], [result.new_name, "unrelated.pak"])
            self.assertEqual(after["Core"]["last_managed"], before["Core"]["last_managed"])
            self.assertEqual(after["Core"]["state"], before["Core"]["state"])
        self.assertEqual(list(self.profiles.joinpath("renames").glob("*.json")), [])

    def test_group_and_second_profile_with_individual_files_keep_their_presets(self):
        storage.update_game_profile(self.cfg, "test-game", {"mod_group_extensions": ".pak,.utoc"})
        storage.create_game_profile("Second", {"mods_source_dir": str(self.source), "game_mods_dir": str(self.root / "game2"),
                                              "install_mode": "copy"}, self.cfg)
        second_id = self.cfg["game_profiles"][1]["id"]
        (self.root / "game2").mkdir()
        storage.set_active_game_profile(self.cfg, "test-game")
        self.add_mods("sample.pak", "sample.utoc")
        second = deepcopy(self.cfg)
        storage.set_active_game_profile(second, second_id)
        self.seed_metadata(self.cfg, ["sample.pak"])
        self.seed_metadata(second, ["sample.pak", "sample.utoc"])
        for cfg in (self.cfg, second):
            with storage_policy(config=cfg):
                self.assertFalse(change_mods(discover_mods(cfg), "install").errors)
        group, = discover_mods(self.cfg)
        rename_mod(self.cfg, group, "changed.pak")
        for cfg in (self.cfg, second):
            game = Path(cfg["game_mods_dir"])
            for extension in (".pak", ".utoc"):
                self.assertEqual((game / ("changed" + extension)).read_text(), "sample" + extension)
                self.assertFalse((game / ("sample" + extension)).exists())
        with storage_policy(config=second):
            self.assertEqual(storage.load_presets()["Core"], ["changed.pak", "changed.utoc"])
            self.assertEqual(set(storage.load_mod_records()), {"changed.pak", "changed.utoc"})

    def test_folder_rename_preserves_registered_discovery_and_internal_contents(self):
        folder = self.source / "Original"
        folder.mkdir()
        (folder / "content.bin").write_bytes(b"payload")
        register_directory_mod(self.cfg, "Original")
        self.seed_metadata(self.cfg, ["Original"])
        rename_mod(self.cfg, discover_mods(self.cfg)[0], "Changed")
        self.assertEqual((self.source / "Changed/content.bin").read_bytes(), b"payload")
        self.assertEqual(directory_mods(self.cfg), {"changed"})
        with storage_policy(config=self.cfg):
            self.assertEqual(storage.load_presets()["Core"], ["Changed"])

    def test_case_only_rename_and_cli_use_the_same_storage_contract(self):
        self.add_mods("sample.pak")
        self.seed_metadata(self.cfg, ["sample.pak"])
        code, output, error = self.request(["mods", "rename", "1", "Sample.pak"])
        self.assertEqual((code, error), (0, ""))
        self.assertIn("Sample.pak", output)
        self.assertIn("Sample.pak", [path.name for path in self.source.iterdir()])
        with storage_policy(config=self.cfg):
            self.assertEqual(storage.load_presets()["Core"], ["Sample.pak"])

    def test_conflicts_invalid_names_and_unmanaged_destinations_preserve_payloads(self):
        self.add_mods("sample.pak", "occupied.pak")
        mod = next(mod for mod in discover_mods(self.cfg) if mod.name == "sample.pak")
        for name in ("occupied.pak", "../escape.pak", "CON.pak", "wrong.utoc", ".mod-trash", "trailing .pak."):
            with self.subTest(name=name), self.assertRaises((OSError, ValueError)):
                rename_mod(self.cfg, mod, name)
        (self.game / "sample.pak").write_bytes(b"unmanaged")
        with self.assertRaises(FileExistsError):
            rename_mod(self.cfg, mod, "changed.pak")
        self.assertEqual((self.source / "sample.pak").read_bytes(), b"sample.pak")
        self.assertEqual((self.game / "sample.pak").read_bytes(), b"unmanaged")

    def test_metadata_failure_rolls_back_exact_files_and_saved_bytes(self):
        self.add_mods("sample.pak")
        self.seed_metadata(self.cfg, ["sample.pak"])
        with storage_policy(config=self.cfg):
            change_mods(discover_mods(self.cfg), "install")
        before = self.snapshot()
        save = storage.save_json
        failed = False

        def fail_metadata(path, data):
            nonlocal failed
            if Path(path).name == "test-game-presets.json" and not failed:
                failed = True
                raise PermissionError("synthetic metadata lock")
            return save(path, data)

        for name in ("changed.pak", "Sample.pak"):
            failed = False
            with self.subTest(name=name), patch("mod_manager.storage.save_json", side_effect=fail_metadata), self.assertRaises(PermissionError):
                rename_mod(self.cfg, discover_mods(self.cfg)[0], name)
            self.assertTrue(failed)
            self.assertEqual(self.snapshot(), before)

    def test_interrupted_source_move_recovers_before_another_rename(self):
        self.add_mods("sample.pak")
        self.seed_metadata(self.cfg, ["sample.pak"])
        before = self.snapshot()
        identifier = str(uuid4())
        with storage_policy(config=self.cfg):
            data, _renamed = _prepare(self.cfg, discover_mods(self.cfg)[0], "changed.pak", identifier)
        journal = self.profiles / "renames" / (identifier + ".json")
        _write_journal(journal, data)
        source = data["sources"][0]
        Path(source["old"]).rename(source["stage"])
        recover_renames(self.cfg)
        self.assertEqual(self.snapshot(), before)

    def test_recovery_rejects_paths_outside_configured_libraries(self):
        self.add_mods("sample.pak")
        identifier = str(uuid4())
        with storage_policy(config=self.cfg):
            data, _renamed = _prepare(self.cfg, discover_mods(self.cfg)[0], "changed.pak", identifier)
        outside = self.root / "outside.pak"
        outside.write_bytes(b"preserve")
        data["sources"][0]["old"] = str(outside)
        _write_journal(self.profiles / "renames" / (identifier + ".json"), data)
        with self.assertRaises(ValueError):
            recover_renames(self.cfg)
        self.assertEqual(outside.read_bytes(), b"preserve")
