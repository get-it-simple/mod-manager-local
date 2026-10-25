from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mod_manager.models import ModItem
from mod_manager.mods import (
    discover_mods,
    import_mod_image,
    is_mod_file,
    mod_image_path,
    mods_view,
    parse_extensions,
    parse_group_extensions,
)


class ParseExtensionsTests(unittest.TestCase):
    def test_empty_extensions_show_everything_including_folders(self):
        self.assertEqual(parse_extensions({"mod_extensions": ""}), (True, [], True))

    def test_multiple_extensions_are_normalized(self):
        self.assertEqual(
            parse_extensions({"mod_extensions": ".pak, utoc, .UCAS"}),
            (False, [".pak", ".utoc", ".ucas"], False),
        )

    def test_folders_token_enables_folder_mods_alongside_extensions(self):
        self.assertEqual(
            parse_extensions({"mod_extensions": ".pak,.utoc,folders"}),
            (False, [".pak", ".utoc"], True),
        )

    def test_folders_only_excludes_all_files(self):
        self.assertEqual(parse_extensions({"mod_extensions": "folders"}), (False, [], True))

    def test_grouped_extensions_are_normalized_in_their_configured_order(self):
        self.assertEqual(
            parse_group_extensions({"mod_group_extensions": ".PAK, utoc ,.ucas,.pak"}),
            [".pak", ".utoc", ".ucas"],
        )

    def test_grouped_extensions_always_count_as_mod_files(self):
        cfg = {"mod_extensions": ".pak", "mod_group_extensions": ".utoc,.ucas"}
        self.assertEqual(parse_extensions(cfg), (False, [".pak", ".utoc", ".ucas"], False))


class DiscoverModsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.src = Path(self.tmp.name) / "source"
        self.dst = Path(self.tmp.name) / "game"
        self.src.mkdir()
        self.dst.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _cfg(self, **overrides) -> dict:
        cfg = {
            "mods_source_dir": str(self.src),
            "game_mods_dir": str(self.dst),
            "mod_extensions": "",
            "mod_group_extensions": "",
            "mod_recursive_scan": False,
            "link_prefix": "",
            "install_mode": "link",
        }
        cfg.update(overrides)
        return cfg

    def test_default_config_includes_top_level_files_and_folders(self):
        (self.src / "weapon.pak").touch()
        (self.src / "FolderMod").mkdir()
        (self.src / "images").mkdir()

        items = discover_mods(self._cfg())

        names = {item.name for item in items}
        self.assertEqual(names, {"weapon.pak", "FolderMod"})
        folder_item = next(item for item in items if item.name == "FolderMod")
        self.assertTrue(folder_item.is_dir)

    def test_extensions_without_folders_token_excludes_directories(self):
        (self.src / "weapon.pak").touch()
        (self.src / "readme.txt").touch()
        (self.src / "FolderMod").mkdir()

        items = discover_mods(self._cfg(mod_extensions=".pak,.utoc"))

        self.assertEqual({item.name for item in items}, {"weapon.pak"})

    def test_folders_token_combined_with_extensions(self):
        (self.src / "weapon.pak").touch()
        (self.src / "readme.txt").touch()
        (self.src / "FolderMod").mkdir()

        items = discover_mods(self._cfg(mod_extensions=".pak,folders"))

        self.assertEqual({item.name for item in items}, {"weapon.pak", "FolderMod"})

    def test_recursive_scan_finds_nested_files_when_folders_excluded(self):
        nested = self.src / "Category" / "Sub"
        nested.mkdir(parents=True)
        (nested / "weapon.pak").touch()
        (self.src / "top.pak").touch()

        non_recursive = discover_mods(self._cfg(mod_extensions=".pak", mod_recursive_scan=False))
        self.assertEqual({item.name for item in non_recursive}, {"top.pak"})

        recursive = discover_mods(self._cfg(mod_extensions=".pak", mod_recursive_scan=True))
        self.assertEqual({item.name for item in recursive}, {"top.pak", "weapon.pak"})

    def test_recursive_scan_does_not_recurse_into_folder_mods(self):
        folder_mod = self.src / "FolderMod"
        folder_mod.mkdir()
        (folder_mod / "inner.pak").touch()

        items = discover_mods(self._cfg(mod_extensions=".pak,folders", mod_recursive_scan=True))

        self.assertEqual({item.name for item in items}, {"FolderMod"})

    def test_same_image_imported_for_different_mods_is_stored_per_mod_name(self):
        drop = Path(self.tmp.name) / "drop"
        drop.mkdir()
        image = drop / "preview.png"
        image.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
            b"\x00\x00\x00\x03\x00\x01\x9a`\x1d\x15\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        cfg = self._cfg()

        ok_first, first_name = import_mod_image(cfg, "weapon.pak", image)
        ok_second, second_name = import_mod_image(cfg, "FolderMod", image)

        self.assertTrue(ok_first)
        self.assertTrue(ok_second)
        self.assertTrue(first_name.startswith("weapon.pak"))
        self.assertTrue(second_name.startswith("FolderMod"))
        first_path = mod_image_path(cfg, "weapon.pak")
        second_path = mod_image_path(cfg, "FolderMod")
        self.assertIsNotNone(first_path)
        self.assertIsNotNone(second_path)
        self.assertNotEqual(first_path, second_path)
        self.assertNotIn("preview", {p.name for p in (self.src / "images").iterdir()})

    def test_is_mod_file_respects_folder_inclusion(self):
        folder = self.src / "FolderMod"
        folder.mkdir()
        pak = self.src / "weapon.pak"
        pak.touch()

        cfg_no_folders = self._cfg(mod_extensions=".pak")
        self.assertFalse(is_mod_file(folder, cfg_no_folders))
        self.assertTrue(is_mod_file(pak, cfg_no_folders))

        cfg_with_folders = self._cfg(mod_extensions=".pak,folders")
        self.assertTrue(is_mod_file(folder, cfg_with_folders))


class GroupedModTests(unittest.TestCase):
    GROUP = ".pak,.utoc,.ucas"

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.src = Path(self.tmp.name) / "source"
        self.dst = Path(self.tmp.name) / "game"
        self.src.mkdir()
        self.dst.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _cfg(self, **overrides) -> dict:
        cfg = {
            "mods_source_dir": str(self.src),
            "game_mods_dir": str(self.dst),
            "mod_extensions": ".pak,.utoc,.ucas",
            "mod_group_extensions": self.GROUP,
            "mod_recursive_scan": False,
            "link_prefix": "",
            "install_mode": "link",
        }
        cfg.update(overrides)
        return cfg

    def _touch_group(self, folder: Path, stem: str, suffixes=(".pak", ".utoc", ".ucas")) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        for suffix in suffixes:
            (folder / f"{stem}{suffix}").touch()

    def test_matching_files_become_one_mod_named_after_the_first_grouped_extension(self):
        self._touch_group(self.src, "Weapon")

        items = discover_mods(self._cfg())

        self.assertEqual([item.name for item in items], ["Weapon.pak"])
        self.assertEqual(
            sorted(f.src.name for f in items[0].install_files),
            ["Weapon.pak", "Weapon.ucas", "Weapon.utoc"],
        )

    def test_the_primary_member_follows_the_configured_extension_order(self):
        self._touch_group(self.src, "Weapon")

        items = discover_mods(self._cfg(mod_group_extensions=".ucas,.utoc,.pak"))

        self.assertEqual([item.name for item in items], ["Weapon.ucas"])
        self.assertEqual(items[0].src, self.src / "Weapon.ucas")

    def test_a_group_counts_as_installed_only_when_every_member_is_present(self):
        self._touch_group(self.src, "Weapon")
        (self.dst / "Weapon.pak").touch()
        (self.dst / "Weapon.utoc").touch()

        self.assertFalse(discover_mods(self._cfg())[0].installed)

        (self.dst / "Weapon.ucas").touch()
        self.assertTrue(discover_mods(self._cfg())[0].installed)

    def test_files_outside_the_grouped_list_stay_separate_mods(self):
        self._touch_group(self.src, "Weapon")
        (self.src / "Weapon.txt").touch()

        items = discover_mods(self._cfg(mod_extensions=".pak,.utoc,.ucas,.txt"))

        self.assertEqual(sorted(item.name for item in items), ["Weapon.pak", "Weapon.txt"])

    def test_grouping_never_merges_the_same_name_from_different_subfolders(self):
        self._touch_group(self.src / "First", "Weapon")
        self._touch_group(self.src / "Second", "Weapon")

        items = discover_mods(self._cfg(mod_recursive_scan=True))

        self.assertEqual([item.name for item in items], ["Weapon.pak", "Weapon.pak"])
        self.assertEqual(
            sorted(str(item.src.parent.name) for item in items),
            ["First", "Second"],
        )

    def test_a_lone_grouped_file_is_still_a_normal_mod(self):
        (self.src / "Solo.pak").touch()

        items = discover_mods(self._cfg())

        self.assertEqual([item.name for item in items], ["Solo.pak"])
        self.assertEqual(items[0].files, ())

    def test_the_link_prefix_still_applies_to_every_member(self):
        self._touch_group(self.src, "Weapon")

        items = discover_mods(self._cfg(link_prefix="_P"))

        self.assertEqual(
            sorted(f.dest.name for f in items[0].install_files),
            ["Weapon_P.pak", "Weapon_P.ucas", "Weapon_P.utoc"],
        )

    def test_the_install_mode_of_the_profile_reaches_every_mod(self):
        (self.src / "Solo.pak").touch()

        self.assertFalse(discover_mods(self._cfg())[0].copy_install)
        self.assertTrue(discover_mods(self._cfg(install_mode="copy"))[0].copy_install)


class ModsViewFavoriteTests(unittest.TestCase):
    def test_search_label_and_favorite_filters_are_combined(self):
        root = Path(tempfile.gettempdir())
        items = [
            ModItem("combat-favorite.pak", root / "a", root / "da", False, False),
            ModItem("combat-normal.pak", root / "b", root / "db", False, False),
            ModItem("ui-favorite.pak", root / "c", root / "dc", False, False),
        ]
        cfg = {"page_size": 10, "active_game_profile_id": "game", "link_prefix": ""}
        labels = {
            "combat-favorite.pak": "combat",
            "combat-normal.pak": "combat",
            "ui-favorite.pak": "ui",
        }

        with patch("mod_manager.mods.discover_mods", return_value=items), patch(
            "mod_manager.mods.ensure_mod_records"
        ), patch("mod_manager.mods.load_labels", return_value=labels), patch(
            "mod_manager.mods.load_mod_records", return_value={}
        ), patch("mod_manager.mods.load_favorites", return_value={"combat-favorite.pak", "ui-favorite.pak"}):
            with patch("mod_manager.mods.load_label_definitions", return_value={}):
                filtered, shown, page, pages, returned_labels = mods_view(
                    cfg, 1, "combat", "pak", "name", True
                )

        self.assertEqual([mod.name for mod in filtered], ["combat-favorite.pak"])
        self.assertEqual(shown, filtered)
        self.assertEqual((page, pages), (1, 1))
        self.assertEqual(returned_labels, labels)


if __name__ == "__main__":
    unittest.main()
