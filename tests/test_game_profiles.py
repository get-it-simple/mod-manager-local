from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mod_manager import storage
from mod_manager.cli import run_cli
from mod_manager.settings_schema import coerce_game_profile


class GameProfileStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.config_path = self.root / "config.json"
        self.presets_path = self.root / "presets.json"
        self.labels_path = self.root / "labels.json"
        self.profile_dir = self.root / "profiles"
        self.patches = [
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

    def test_legacy_game_settings_become_default_profile(self):
        storage.save_json(
            self.config_path,
            {
                "game_name": "Cyber Game",
                "mods_source_dir": "D:/mods/source",
                "game_mods_dir": "D:/game/mods",
                "mod_extensions": ".pak",
            },
        )

        cfg = storage.load_config()

        self.assertEqual(len(cfg["game_profiles"]), 1)
        profile = cfg["game_profiles"][0]
        self.assertEqual(profile["name"], "Cyber Game")
        self.assertEqual(profile["mods_source_dir"], "D:/mods/source")
        self.assertEqual(profile["game_mods_dir"], "D:/game/mods")
        self.assertEqual(profile["mod_extensions"], ".pak")
        self.assertEqual(profile["mod_mode"], "standard")
        self.assertEqual(profile["mod_icon_path"], "")
        self.assertEqual(cfg["active_game_profile_id"], profile["id"])
        self.assertEqual(cfg["mods_source_dir"], "D:/mods/source")

    def test_mod_recursive_scan_persists_per_profile(self):
        cfg = storage.load_config()
        first = storage.create_game_profile(
            "First Game",
            {"mods_source_dir": "A", "game_mods_dir": "B", "mod_recursive_scan": True},
            cfg,
        )
        second = storage.create_game_profile(
            "Second Game",
            {"mods_source_dir": "C", "game_mods_dir": "D"},
            cfg,
        )

        self.assertEqual(first["mod_recursive_scan"], True)
        self.assertFalse(second.get("mod_recursive_scan"))

        storage.set_active_game_profile(cfg, first["id"])
        self.assertEqual(cfg["mod_recursive_scan"], True)

        storage.set_active_game_profile(cfg, second["id"])
        self.assertFalse(cfg["mod_recursive_scan"])

    def test_directory_mode_and_icon_path_persist_only_in_their_profile(self):
        cfg = storage.load_config()
        first = storage.create_game_profile("Directories", {
            "mods_source_dir": "synthetic/source", "game_mods_dir": "synthetic/game",
            **coerce_game_profile({"mod_mode": "directories", "mod_icon_path": "assets/icon.png"}),
        }, cfg)
        second = storage.create_game_profile("Standard", {
            "mods_source_dir": "synthetic/other-source", "game_mods_dir": "synthetic/other-game",
        }, cfg)
        storage.save_config(cfg)
        cfg = storage.load_config()
        self.assertEqual(cfg["mod_mode"], "standard")
        self.assertEqual(cfg["mod_icon_path"], "")
        storage.set_active_game_profile(cfg, first["id"])
        storage.save_config(cfg)
        cfg = storage.load_config()
        self.assertEqual(cfg["mod_mode"], "directories")
        self.assertEqual(cfg["mod_icon_path"], "assets/icon.png")
        self.assertEqual(second["mod_icon_path"], "")

    def test_cli_add_and_edit_round_trip_directory_settings(self):
        self.assertEqual(run_cli(["games", "add", "Synthetic", "--mods-source-dir", "synthetic/source",
                                  "--game-mods-dir", "synthetic/game", "--mod-mode", "directories",
                                  "--mod-icon-path", "assets/icon.png"]), 0)
        cfg = storage.load_config()
        identifier = cfg["active_game_profile_id"]
        self.assertEqual(cfg["mod_mode"], "directories")
        self.assertEqual(cfg["mod_icon_path"], "assets/icon.png")
        self.assertEqual(run_cli(["games", "edit", identifier, "--mod-icon-path", "icon.png"]), 0)
        self.assertEqual(storage.load_config()["mod_icon_path"], "icon.png")
        self.assertEqual(run_cli(["games", "edit", identifier, "--mod-icon-path", "../outside.png"]), 1)
        self.assertEqual(storage.load_config()["mod_icon_path"], "icon.png")

    def test_legacy_presets_are_migrated_into_default_profile(self):
        storage.save_json(
            self.config_path,
            {
                "game_name": "Cyber Game",
                "mods_source_dir": "D:/mods/source",
                "game_mods_dir": "D:/game/mods",
            },
        )
        storage.save_json(self.presets_path, {"legacy": ["old.pak"]})

        cfg = storage.load_config()
        profile_id = cfg["active_game_profile_id"]

        self.assertEqual(storage.load_presets(), {"legacy": ["old.pak"]})
        self.assertTrue((self.profile_dir / f"{profile_id}-presets.json").exists())

    def test_new_profile_does_not_inherit_legacy_presets_and_labels(self):
        storage.save_json(
            self.config_path,
            {
                "game_name": "Cyber Game",
                "mods_source_dir": "D:/mods/source",
                "game_mods_dir": "D:/game/mods",
            },
        )
        storage.save_json(self.presets_path, {"legacy": ["old.pak"]})
        storage.save_json(self.labels_path, {"old.pak": {"label": "legacy", "last_managed": None, "state": "undefined"}})

        cfg = storage.load_config()
        first = cfg["game_profiles"][0]

        # First (legacy-migrated) profile keeps the legacy presets/labels.
        self.assertEqual(storage.load_presets(), {"legacy": ["old.pak"]})
        self.assertEqual(storage.load_labels(), {"old.pak": "legacy"})

        second = storage.create_game_profile("Second Game", {"mods_source_dir": "C", "game_mods_dir": "D"}, cfg)
        storage.set_active_game_profile(cfg, second["id"])
        storage.save_config(cfg)

        # New profile starts empty, not a copy of the legacy/first profile's data.
        self.assertEqual(storage.load_presets(), {})
        self.assertEqual(storage.load_labels(), {})

        storage.set_active_game_profile(cfg, first["id"])
        storage.save_config(cfg)
        self.assertEqual(storage.load_presets(), {"legacy": ["old.pak"]})
        self.assertEqual(storage.load_labels(), {"old.pak": "legacy"})

    def test_legacy_labels_merge_when_profile_file_was_created_empty_first(self):
        storage.save_json(
            self.config_path,
            {
                "game_name": "Cyber Game",
                "mods_source_dir": "D:/mods/source",
                "game_mods_dir": "D:/game/mods",
            },
        )
        cfg = storage.load_config()
        profile_id = cfg["active_game_profile_id"]
        storage.save_json(self.labels_path, {"combat.pak": {"label": "combat", "last_managed": None, "state": "undefined"}})
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        storage.save_json(self.profile_dir / f"{profile_id}-labels.json", {"combat.pak": {"label": "", "last_managed": None, "state": "undefined"}})

        self.assertEqual(storage.load_labels(), {"combat.pak": "combat"})

    def test_profile_labels_and_presets_are_separated_by_active_game(self):
        cfg = storage.load_config()
        first = storage.create_game_profile("First Game", {"mods_source_dir": "A", "game_mods_dir": "B"}, cfg)
        second = storage.create_game_profile("Second Game", {"mods_source_dir": "C", "game_mods_dir": "D"}, cfg)
        storage.set_active_game_profile(cfg, first["id"])
        storage.save_config(cfg)
        storage.save_labels({"a.pak": "combat"})
        storage.save_presets({"core": ["a.pak"]})

        storage.set_active_game_profile(cfg, second["id"])
        storage.save_config(cfg)
        storage.save_labels({"b.pak": "ui"})
        storage.save_presets({"ui": ["b.pak"]})

        storage.set_active_game_profile(cfg, first["id"])
        storage.save_config(cfg)
        self.assertEqual(storage.load_labels(), {"a.pak": "combat"})
        self.assertEqual(storage.load_presets(), {"core": ["a.pak"]})

        storage.set_active_game_profile(cfg, second["id"])
        storage.save_config(cfg)
        self.assertEqual(storage.load_labels(), {"b.pak": "ui"})
        self.assertEqual(storage.load_presets(), {"ui": ["b.pak"]})

    def test_favorites_are_scoped_by_profile_and_preserved_with_labels(self):
        cfg = storage.load_config()
        first = storage.create_game_profile("First Game", {"mods_source_dir": "A", "game_mods_dir": "B"}, cfg)
        second = storage.create_game_profile("Second Game", {"mods_source_dir": "C", "game_mods_dir": "D"}, cfg)

        storage.set_active_game_profile(cfg, first["id"])
        storage.save_config(cfg)
        storage.update_favorites(cfg, ["same.pak"], True)
        storage.save_labels({"same.pak": "combat"})

        storage.set_active_game_profile(cfg, second["id"])
        storage.save_config(cfg)
        self.assertEqual(storage.load_favorites(cfg), set())
        storage.update_favorites(cfg, ["other.pak"], True)

        storage.set_active_game_profile(cfg, first["id"])
        storage.save_config(cfg)
        self.assertEqual(storage.load_favorites(cfg), {"same.pak"})
        self.assertEqual(storage.load_labels(), {"same.pak": "combat"})
        raw = storage.load_json(self.labels_path, {})
        self.assertEqual(raw[storage.FAVORITES_KEY][first["id"]], ["same.pak"])
        self.assertEqual(raw[storage.FAVORITES_KEY][second["id"]], ["other.pak"])

    def test_reserved_favorites_record_is_not_loaded_as_a_mod(self):
        storage.save_json(
            self.labels_path,
            {
                "legacy.pak": {"label": "legacy", "last_managed": None, "state": "undefined"},
                storage.FAVORITES_KEY: {storage.DEFAULT_FAVORITE_SCOPE: ["legacy.pak"]},
            },
        )

        self.assertEqual(storage.load_labels(), {"legacy.pak": "legacy"})
        self.assertNotIn(storage.FAVORITES_KEY, storage.load_mod_records())
        self.assertEqual(storage.load_favorites({}), {"legacy.pak"})

    def test_saving_the_config_never_writes_top_level_keys_into_a_profile(self):
        cfg = storage.load_config()
        first = storage.create_game_profile("First Game", {"mods_source_dir": "A", "game_mods_dir": "B"}, cfg)
        second = storage.create_game_profile("Second Game", {"mods_source_dir": "C", "game_mods_dir": "D"}, cfg)
        cfg["mods_source_dir"] = "tampered"
        cfg["mod_extensions"] = ".tampered"
        cfg["page_size"] = 25

        storage.save_config(cfg)
        reloaded = storage.load_config()

        profiles = {profile["id"]: profile for profile in reloaded["game_profiles"]}
        self.assertEqual(profiles[first["id"]]["mods_source_dir"], "A")
        self.assertEqual(profiles[second["id"]]["mods_source_dir"], "C")
        self.assertEqual(profiles[second["id"]]["mod_extensions"], "")
        self.assertEqual(reloaded["mods_source_dir"], "C")
        self.assertEqual(reloaded["page_size"], 25)

class GameProfileCliTests(unittest.TestCase):
    def test_games_add_select_and_list_use_profile_contract(self):
        cfg = {"game_profiles": [], "active_game_profile_id": ""}
        saved = []

        with patch("mod_manager.cli.load_config", return_value=cfg), patch("mod_manager.cli.save_config", side_effect=lambda c: saved.append(dict(c))):
            self.assertEqual(run_cli(["games", "add", "Stalker Two", "--mods-source-dir", "src", "--game-mods-dir", "dst"]), 0)

        profile = cfg["game_profiles"][0]
        self.assertEqual(profile["name"], "Stalker Two")
        self.assertEqual(profile["mods_source_dir"], "src")
        self.assertEqual(profile["game_mods_dir"], "dst")
        self.assertEqual(cfg["active_game_profile_id"], profile["id"])
        self.assertTrue(saved)

    def test_games_add_stores_the_install_method_and_grouped_extensions(self):
        cfg = {"game_profiles": [], "active_game_profile_id": ""}

        with patch("mod_manager.cli.load_config", return_value=cfg), patch("mod_manager.cli.save_config"):
            code = run_cli([
                "games", "add", "Stalker Two",
                "--install-mode", "copy",
                "--mod-group-extensions", ".pak,.utoc,.ucas",
            ])

        self.assertEqual(code, 0)
        profile = cfg["game_profiles"][0]
        self.assertEqual(profile["install_mode"], "copy")
        self.assertEqual(profile["mod_group_extensions"], ".pak,.utoc,.ucas")

    def test_games_edit_changes_only_the_flags_that_were_passed(self):
        cfg = {"game_profiles": [], "active_game_profile_id": ""}

        with patch("mod_manager.cli.load_config", return_value=cfg), patch("mod_manager.cli.save_config"):
            run_cli(["games", "add", "Stalker Two", "--install-mode", "copy", "--link-prefix", "_P"])
            profile_id = cfg["game_profiles"][0]["id"]
            code = run_cli(["games", "edit", profile_id, "--mod-group-extensions", ".pak,.utoc"])

        self.assertEqual(code, 0)
        profile = cfg["game_profiles"][0]
        self.assertEqual(profile["mod_group_extensions"], ".pak,.utoc")
        self.assertEqual(profile["install_mode"], "copy")
        self.assertEqual(profile["link_prefix"], "_P")


if __name__ == "__main__":
    unittest.main()
