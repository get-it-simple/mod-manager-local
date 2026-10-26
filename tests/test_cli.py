from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from mod_manager import links, storage
from mod_manager.collection_utils import paginate
from mod_manager.platform_utils import is_junction
from pathlib import Path
from mod_manager.storage_policy import storage_policy


from tests.cli_support import CliEnvironment


class CliRequestTests(CliEnvironment, unittest.TestCase):
    def test_help_and_version_never_load_configuration(self):
        for argv in ([], ["help"], ["help", "mods", "toggle"], ["--help"], ["--version"], ["mods"], ["games"], ["presets"], ["settings"], ["broken"]):
            with self.subTest(argv=argv), patch("mod_manager.cli.load_config", side_effect=AssertionError("loaded")):
                code, output, errors = self.request(argv)
                self.assertEqual(code, 0, errors)
                self.assertTrue(output)
        self.assertIn("Install inactive selections", self.request(["help", "mods", "toggle"])[1])

    def test_help_rejects_unknown_and_extra_topics(self):
        for argv in (["help", "missing"], ["help", "mods", "missing"], ["help", "mods", "toggle", "extra"]):
            self.assertEqual(self.request(argv)[0], 1)

    def test_every_parser_has_descriptions_and_option_help(self):
        output = self.request(["help", "mods", "list"])[1]
        for text in ("Filter", "Page number", "descending", "favorites"):
            self.assertIn(text, output)
        self.assertIn("respecting filters", self.request(["help", "mods", "install"])[1])

    def test_listing_search_label_page_and_order_share_filters(self):
        self.add_mods("a.pak", "b.pak", "c.pak")
        self.assertIn("a.pak", self.request(["mods", "list"])[1])
        self.assertNotIn("c.pak", self.request(["mods", "list"])[1])
        self.assertIn("c.pak", self.request(["mods", "page", "2"])[1])
        self.assertNotIn("a.pak", self.request(["mods", "search", "b"])[1])
        self.assertEqual(self.request(["mods", "label-add", "combat", "2"])[0], 0)
        self.assertIn("b.pak", self.request(["mods", "label", "combat"])[1])
        self.assertNotIn("a.pak", self.request(["mods", "label", "combat"])[1])
        self.assertIn("1. [ ] c.pak", self.request(["mods", "order", "-name"])[1])
        self.assertEqual(self.request(["mods", "list", "--order", "-last_managed"])[0], 0)

    def test_install_and_uninstall_respect_page_search_and_source(self):
        self.add_mods("a.pak", "b.pak", "c.pak")
        original = {path.name: path.read_bytes() for path in self.source.iterdir()}
        self.assertEqual(self.request(["mods", "install", "--page", "2"])[0], 0)
        self.assertEqual([path.name for path in self.game.iterdir()], ["c.pak"])
        self.assertEqual(self.request(["mods", "uninstall", "--search", "c"])[0], 0)
        self.assertEqual(list(self.game.iterdir()), [])
        self.assertEqual({path.name: path.read_bytes() for path in self.source.iterdir()}, original)

    def test_toggle_deduplicates_indexes_and_updates_managed_state(self):
        self.add_mods("a.pak", "b.pak")
        self.assertEqual(self.request(["mods", "toggle", "1,1"])[0], 0)
        self.assertTrue((self.game / "a.pak").exists())
        self.assertFalse((self.game / "b.pak").exists())
        self.assertEqual(storage.load_mod_records()["a.pak"]["state"], "installed")
        self.assertEqual(self.request(["mods", "toggle", "1"])[0], 0)
        self.assertFalse((self.game / "a.pak").exists())
        self.assertEqual(storage.load_mod_records()["a.pak"]["state"], "uninstalled")

    def test_label_and_favorite_actions_use_the_filtered_page(self):
        self.add_mods("a.pak", "b.pak", "c.pak")
        self.assertEqual(self.request(["mods", "label-add", "combat", "1", "--page", "2"])[0], 0)
        self.assertEqual(storage.load_labels(), {"c.pak": "combat"})
        self.assertEqual(self.request(["mods", "favorite-add", "1", "--filter-label", "combat"])[0], 0)
        output = self.request(["mods", "list", "--favorite"])[1]
        self.assertIn("c.pak", output)
        self.assertNotIn("a.pak", output)
        self.assertEqual(self.request(["mods", "install", "--favorite"])[0], 0)
        self.assertEqual([path.name for path in self.game.iterdir()], ["c.pak"])
        self.assertEqual(self.request(["mods", "uninstall", "--favorite"])[0], 0)
        self.assertFalse((self.game / "c.pak").exists())
        self.assertEqual(self.request(["mods", "favorite-remove", "1", "--favorite"])[0], 0)
        self.assertEqual(storage.load_favorites(storage.load_config()), set())
        self.assertEqual(self.request(["mods", "label-remove", "combat", "1", "--filter-label", "combat"])[0], 0)
        self.assertEqual(storage.load_labels(), {})

    def test_invalid_selection_refuses_the_whole_operation(self):
        self.add_mods("a.pak", "b.pak")
        for command, operands in (("toggle", ["1,3"]), ("label-add", ["combat", "1,3"]), ("favorite-add", ["1,3"])):
            before = self.snapshot()
            self.assertEqual(self.request(["mods", command, *operands])[0], 2)
            self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.request(["mods", "toggle", "1", "--page", "99"])[0], 2)
        self.assertEqual(list(self.game.iterdir()), [])

    def test_invalid_input_is_usage_error(self):
        for argv in (["mods", "toggle", "0"], ["mods", "toggle", "1,bad"], ["mods", "toggle", "1,"], ["mods", "toggle", ""], ["mods", "list", "--page", "0"], ["mods", "page", "-1"], ["mods", "list", "--order", "newest"], ["settings", "set", "--mods-source-dir", "x"]):
            with self.subTest(argv=argv):
                code, _output, error = self.request(argv)
                self.assertEqual(code, 2, error)
                self.assertTrue(error)

    def test_copy_overwrite_requires_flag_and_preserves_source(self):
        self.add_mods("a.pak")
        (self.game / "a.pak").write_text("old", encoding="utf-8")
        self.assertEqual(self.request(["mods", "install"])[0], 0)
        self.assertEqual((self.game / "a.pak").read_text(), "old")
        self.cfg["game_profiles"][0]["mod_group_extensions"] = ".pak,.utoc"
        self.add_mods("a.utoc")
        self.write_config()
        self.assertEqual(self.request(["mods", "install"])[0], 1)
        self.assertEqual((self.game / "a.pak").read_text(), "old")
        self.assertEqual(self.request(["mods", "install", "--overwrite"])[0], 0)
        self.assertEqual((self.game / "a.pak").read_text(), "a.pak")
        self.assertEqual((self.source / "a.pak").read_text(), "a.pak")

    def test_partial_install_reports_failure_and_marks_only_success(self):
        self.add_mods("a.pak", "b.pak")
        real_copy = links.copy_path
        def copy(source, destination, overwrite=False):
            return (False, "access denied") if source.name == "b.pak" else real_copy(source, destination, overwrite)
        with patch("mod_manager.links.copy_path", side_effect=copy):
            code, output, error = self.request(["mods", "install"])
        self.assertEqual(code, 1)
        self.assertIn("Installed 1/2", output)
        self.assertIn("access denied", error)
        records = storage.load_mod_records()
        self.assertEqual(records["a.pak"]["state"], "installed")
        self.assertNotIn("b.pak", records)

    def test_uninstall_and_toggle_failures_return_nonzero(self):
        self.add_mods("a.pak")
        self.request(["mods", "install"])
        for command, operands in (("uninstall", []), ("toggle", ["1"])):
            with self.subTest(command=command), patch("mod_manager.mods.remove_path", return_value=(False, "locked")):
                code, output, errors = self.request(["mods", command, *operands])
            self.assertEqual(code, 1)
            self.assertIn("Errors: 1", output)
            self.assertIn("locked", errors)
            self.assertTrue((self.game / "a.pak").exists())

    def test_settings_updates_are_validated_together_and_preserve_game_values(self):
        before = self.config.read_bytes()
        self.assertEqual(self.request(["settings", "set", "--gui-font-size", "12", "--page-size", "0"])[0], 2)
        self.assertEqual(self.config.read_bytes(), before)
        code, _output, error = self.request(["settings", "set", "--page-size", "25", "--gui-theme", "dark", "--archive-import-mode", "separate", "--archive-preserve-structure", "--import-ignore-extensions", ".txt"])
        self.assertEqual(code, 0, error)
        cfg = storage.load_config()
        self.assertEqual(cfg["page_size"], 25)
        self.assertEqual(cfg["gui_theme"], "dark")
        self.assertEqual(cfg["mods_source_dir"], str(self.source))
        self.assertEqual(cfg["archive_import_mode"], "separate")
        self.assertIs(cfg["archive_preserve_structure"], True)
        self.assertEqual(cfg["import_ignore_extensions"], ".txt")

    def test_settings_show_and_empty_set_do_not_save(self):
        before = self.config.read_bytes()
        output = self.request(["settings", "show"])[1]
        self.assertLess(output.index("game_mods_dir:"), output.index("mods_source_dir:"))
        self.assertEqual(self.request(["settings", "set"])[0], 0)
        self.assertEqual(self.config.read_bytes(), before)

    def test_presets_save_list_toggle_delete(self):
        self.add_mods("a.pak")
        self.request(["mods", "install"])
        self.assertEqual(self.request(["presets", "save", "My loadout"])[0], 0)
        self.assertIn("My loadout", self.request(["presets", "list"])[1])
        self.assertIn("My loadout", self.request(["presets", "page", "1"])[1])
        self.assertEqual(self.request(["presets", "toggle", "1"])[0], 0)
        self.assertFalse((self.game / "a.pak").exists())
        self.assertEqual(self.request(["presets", "toggle", "1"])[0], 0)
        self.assertTrue((self.game / "a.pak").exists())
        self.assertEqual(self.request(["presets", "delete", "1"])[0], 0)
        self.assertEqual(storage.load_presets(), {})

    def test_preset_delete_rejects_mixed_invalid_selection(self):
        self.presets.write_text(json.dumps({"one": ["a.pak"]}), encoding="utf-8")
        before = self.snapshot()
        self.assertEqual(self.request(["presets", "delete", "1,2"])[0], 2)
        self.assertEqual(self.snapshot(), before)

    def test_deleted_legacy_preset_stays_deleted_after_reload(self):
        self.presets.write_text(json.dumps({"one": ["a.pak"], "two": ["b.pak"]}), encoding="utf-8")
        self.assertEqual(self.request(["presets", "delete", "1"])[0], 0)
        for _ in range(2):
            self.assertEqual(storage.load_presets(), {"two": ["b.pak"]})

    def test_removed_legacy_label_stays_removed_and_preserves_favorites(self):
        self.add_mods("a.pak")
        favorites = {"test-game": ["a.pak"]}
        self.labels.write_text(json.dumps({"a.pak": "combat", storage.FAVORITES_KEY: favorites}), encoding="utf-8")
        self.assertEqual(self.request(["mods", "label-remove", "combat", "1"])[0], 0)
        self.assertEqual(storage.load_labels(), {})
        self.assertEqual(storage.load_labels(), {})
        self.assertEqual(json.loads(self.labels.read_text())[storage.FAVORITES_KEY], favorites)

    def test_unsafe_profile_identifier_is_refused_without_writes(self):
        self.cfg["game_profiles"][0]["id"] = "../outside"
        self.write_config()
        before = self.snapshot()
        self.assertEqual(self.request(["presets", "save", "one"])[0], 1)
        self.assertEqual(self.snapshot(), before)

    def test_missing_preset_member_is_reported_as_failure(self):
        self.presets.write_text(json.dumps({"one": ["missing.pak"]}), encoding="utf-8")
        code, _output, errors = self.request(["presets", "toggle", "1"])
        self.assertEqual(code, 1)
        self.assertIn("missing.pak", errors)
        self.assertEqual(self.presets.read_text(), json.dumps({"one": ["missing.pak"]}))

    def test_preset_deactivation_failure_is_not_success(self):
        self.add_mods("a.pak")
        self.request(["mods", "install"])
        self.request(["presets", "save", "one"])
        with patch("mod_manager.mods.remove_path", return_value=(False, "locked")):
            code, _output, errors = self.request(["presets", "toggle", "1"])
        self.assertEqual(code, 1)
        self.assertIn("locked", errors)

    def test_metadata_commands_work_without_game_folders(self):
        self.source.rmdir()
        self.game.rmdir()
        self.presets.write_text(json.dumps({"one": ["a.pak"]}), encoding="utf-8")
        self.assertEqual(self.request(["presets", "list"])[0], 0)
        self.assertIn("[?]", self.request(["presets", "list"])[1])
        self.assertEqual(self.request(["presets", "delete", "1"])[0], 0)
        for argv in (["games", "list"], ["settings", "show"]):
            self.assertEqual(self.request(argv)[0], 0)
        self.assertFalse(self.source.exists())
        self.assertFalse(self.game.exists())

    def test_read_commands_do_not_create_metadata_or_migrate_legacy(self):
        self.add_mods("a.pak")
        self.labels.write_text(json.dumps({"a.pak": "combat"}), encoding="utf-8")
        self.presets.write_text(json.dumps({"one": ["a.pak"]}), encoding="utf-8")
        before = self.snapshot()
        for argv in (["mods", "list"], ["presets", "list"], ["broken", "list"], ["settings", "show"], ["games", "list"], ["doctor"]):
            with self.subTest(argv=argv):
                self.assertEqual(self.request(argv)[0], 0)
                self.assertEqual(self.snapshot(), before)
                self.assertFalse(self.profiles.exists())

    def test_empty_environment_remains_usable_without_writes(self):
        self.config.unlink()
        for argv in (["games", "list"], ["settings", "show"], ["presets", "list"]):
            self.assertEqual(self.request(argv)[0], 0)
        for argv in (["mods", "list"], ["mods", "install"], ["broken", "list"], ["doctor"]):
            code, output, errors = self.request(argv)
            self.assertEqual(code, 1)
            self.assertNotIn("Traceback", output + errors)
        self.assertFalse(self.config.exists())
        self.assertFalse(self.profiles.exists())

    def test_invalid_config_is_preserved(self):
        for value in ("{broken", "[]", "null", '{"page_size":0}', '{"page_size":"bad"}', '{"game_profiles":42}', '{"game_profiles":[1]}', '{"mods_source_dir":42}', '{"mod_recursive_scan":"yes"}'):
            with self.subTest(value=value):
                self.config.write_text(value, encoding="utf-8")
                code, output, errors = self.request(["settings", "set", "--page-size", "20"])
                self.assertEqual(code, 1)
                self.assertTrue(errors)
                self.assertNotIn("Traceback", output + errors)
                self.assertEqual(self.config.read_text(), value)

    def test_invalid_metadata_is_not_silently_replaced(self):
        for value in ("{broken", "[]", '{"one":{"mods":42}}'):
            self.presets.write_text(value, encoding="utf-8")
            self.assertEqual(self.request(["presets", "delete", "1"])[0], 1)
            self.assertEqual(self.presets.read_text(), value)

    def test_missing_directories_require_explicit_creation(self):
        self.source.rmdir()
        self.game.rmdir()
        for argv in (["mods", "list"], ["open", "source"], ["doctor"]):
            self.assertEqual(self.request(argv)[0], 1)
        code, output, error = self.request(["games", "prepare"])
        self.assertEqual(code, 0, error)
        self.assertIn("Missing:", output)
        self.assertFalse(self.source.exists())
        self.assertFalse(self.game.exists())
        self.assertEqual(self.request(["games", "prepare", "--create-dirs"])[0], 0)
        self.assertTrue(self.source.is_dir())
        self.assertTrue(self.game.is_dir())

    def test_prepare_rejects_file_path_before_creating_anything(self):
        self.source.rmdir()
        self.game.rmdir()
        self.game.write_text("valuable", encoding="utf-8")
        self.assertEqual(self.request(["games", "prepare", "--create-dirs"])[0], 1)
        self.assertFalse(self.source.exists())
        self.assertEqual(self.game.read_text(), "valuable")

    def test_overlapping_source_and_game_folders_are_refused(self):
        self.cfg["game_profiles"][0]["game_mods_dir"] = str(self.source)
        self.write_config()
        self.add_mods("a.pak")
        self.assertEqual(self.request(["mods", "install"])[0], 1)
        self.assertEqual(self.request(["games", "prepare", "--create-dirs"])[0], 1)
        self.assertEqual((self.source / "a.pak").read_text(), "a.pak")

    def test_permission_errors_are_actionable(self):
        with patch("pathlib.Path.open", side_effect=PermissionError("permission denied")):
            code, _output, error = self.request(["settings", "show"])
        self.assertEqual(code, 1)
        self.assertIn("permission denied", error)

    def test_failed_atomic_save_preserves_previous_configuration(self):
        before = self.config.read_bytes()
        with patch("mod_manager.storage.os.replace", side_effect=PermissionError("locked")):
            code, _output, error = self.request(["settings", "set", "--page-size", "20"])
        self.assertEqual(code, 1)
        self.assertIn("locked", error)
        self.assertEqual(self.config.read_bytes(), before)
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_open_never_creates_a_missing_directory(self):
        with patch("mod_manager.folder_actions.os.startfile", create=True) as startfile:
            self.assertEqual(self.request(["open", "source"])[0], 0)
            startfile.assert_called_once_with(str(self.source))
        self.source.rmdir()
        self.assertEqual(self.request(["open", "source"])[0], 1)
        self.assertFalse(self.source.exists())

    def test_game_profile_commands_share_persistent_data(self):
        self.assertEqual(self.request(["games", "add", "Other Game", "--install-mode", "copy"])[0], 0)
        cfg = storage.load_config()
        other = cfg["active_game_profile_id"]
        self.assertNotEqual(other, "test-game")
        self.assertEqual(self.request(["games", "edit", other, "--name", "Renamed"])[0], 0)
        self.assertIn("Renamed", self.request(["games", "list"])[1])
        self.assertEqual(self.request(["games", "select", "test-game"])[0], 0)
        self.assertEqual(storage.load_config()["active_game_profile_id"], "test-game")
        self.assertEqual(self.request(["games", "delete", other])[0], 0)
        self.assertEqual(len(storage.load_config()["game_profiles"]), 1)
        self.assertEqual(self.request(["games", "select", "absent"])[0], 1)

    def test_empty_names_are_refused(self):
        for argv in (["games", "add", ""], ["presets", "save", " "]):
            self.assertEqual(self.request(argv)[0], 2)

    def test_profiles_with_same_name_created_in_one_second_have_independent_ids(self):
        with patch("mod_manager.storage._now_iso", return_value="2026-10-24 12:00:00"):
            for _ in range(2):
                self.assertEqual(self.request(["games", "add", "Same Game"])[0], 0)
        profiles = storage.load_config()["game_profiles"]
        self.assertEqual(len({profile["id"] for profile in profiles}), 3)
        self.assertEqual(storage.load_config()["active_game_profile_id"], profiles[-1]["id"])

    def test_deleting_last_profile_does_not_recreate_it_from_legacy_paths(self):
        self.assertEqual(self.request(["games", "delete", "test-game"])[0], 0)
        cfg = storage.load_config()
        self.assertEqual(cfg["game_profiles"], [])
        self.assertEqual(cfg["active_game_profile_id"], "")
        self.assertEqual(cfg["mods_source_dir"], "")
        self.assertTrue(self.source.is_dir())
        self.assertTrue(self.game.is_dir())

    def test_link_install_and_uninstall_preserve_source_folder(self):
        folder = self.source / "FolderMod"
        folder.mkdir()
        (folder / "keep.pak").write_text("keep", encoding="utf-8")
        self.assertEqual(self.request(["games", "edit", "test-game", "--install-mode", "link"])[0], 0)
        code, _output, error = self.request(["mods", "install"])
        self.assertEqual(code, 0, error)
        self.assertTrue((self.game / "FolderMod" / "keep.pak").is_file())
        self.assertEqual(self.request(["mods", "uninstall"])[0], 0)
        self.assertEqual((folder / "keep.pak").read_text(), "keep")
        self.assertFalse((self.game / "FolderMod").exists())

    def test_broken_remove_requires_an_explicit_selection(self):
        self.assertEqual(self.request(["broken", "remove"])[0], 2)
        self.assertEqual(self.request(["broken", "remove", "1", "--all"])[0], 2)
        self.assertEqual(self.request(["broken", "remove", "--all"])[0], 0)

    def test_broken_junction_after_source_deletion_is_detected_and_removed(self):
        target = self.source / "folder"
        target.mkdir()
        destination = self.game / "linked"
        ok, message = links.mklink(target, destination)
        self.assertTrue(ok, message)
        target.rmdir()
        regular = self.game / "regular.pak"
        regular.write_text("keep", encoding="utf-8")
        self.assertIn("linked", self.request(["broken", "list"])[1])
        self.assertEqual(self.request(["broken", "remove", "1"])[0], 0)
        self.assertFalse(is_junction(destination))
        self.assertFalse(destination.is_symlink())
        self.assertEqual(regular.read_text(), "keep")
        self.assertTrue(self.source.exists())

    def test_broken_cleanup_refuses_regular_files_and_live_links(self):
        target = self.source / "folder"
        target.mkdir()
        destination = self.game / "linked"
        self.assertTrue(links.mklink(target, destination)[0])
        self.assertFalse(links.unlink_broken_link(destination)[0])
        regular = self.game / "regular"
        regular.write_text("keep")
        self.assertFalse(links.unlink_broken_link(regular)[0])
        self.assertEqual(regular.read_text(), "keep")
        self.assertTrue(target.is_dir())
        self.assertTrue(links.unlink_path(destination)[0])

    def test_junction_cleanup_supports_python_without_path_is_junction(self):
        target = self.source / "folder"
        target.mkdir()
        destination = self.game / "linked"
        self.assertTrue(links.mklink(target, destination)[0])
        target.rmdir()
        with patch.object(Path, "is_junction", None, create=True):
            self.assertIn("linked", self.request(["broken", "list"])[1])
            self.assertEqual(self.request(["broken", "remove", "--all"])[0], 0)
        self.assertFalse(is_junction(destination))
        self.assertFalse(destination.is_symlink())

    def test_broken_remove_failure_returns_error(self):
        with patch("mod_manager.cli.list_broken_links", return_value=[type("Broken", (), {"dest": self.game / "gone"})()]), patch("mod_manager.cli.unlink_broken_link", return_value=(False, "locked")):
            code, _output, error = self.request(["broken", "remove", "--all"])
        self.assertEqual(code, 1)
        self.assertIn("locked", error)

    def test_invalid_page_size_raises_validation_error_in_shared_helper(self):
        for size in (0, -1, "bad", None):
            with self.subTest(size=size), self.assertRaisesRegex(ValueError, "Mods per page"):
                paginate(1, 1, {"page_size": size})

    def test_storage_policy_is_restored_after_failure(self):
        with self.assertRaises(ValueError), storage_policy():
            storage.load_json(self.source, {})
        self.assertEqual(storage.load_json(self.source, {}), {})

    def test_keyboard_interrupt_returns_130(self):
        with patch("mod_manager.cli.load_config", side_effect=KeyboardInterrupt):
            self.assertEqual(self.request(["mods", "list"])[0], 130)
