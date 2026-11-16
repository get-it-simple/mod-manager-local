from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from mod_manager import storage
from mod_manager.import_preview import destination_rows, preview_plans
from mod_manager.imports import create_plans, execute_plans, prepare_archive, regular_import_tasks, resolve_plans
from mod_manager.mod_modes import normalize_icon_path
from mod_manager.links import mklink, unlink_path
from mod_manager.mods import (
    apply_mod, change_mods, deactivate_mod, discover_mods, import_mod_file, is_mod_file, mod_image_path,
)
from mod_manager.presets import apply_preset, save_preset_from_installed
from mod_manager.settings_schema import coerce_game_profile


class DirectoryModsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        self.game = self.root / "game"
        self.source.mkdir()
        self.game.mkdir()
        for key, name in (
            ("CONFIG_PATH", "config.json"), ("PRESETS_PATH", "presets.json"),
            ("LABELS_PATH", "labels.json"), ("PROFILE_DATA_DIR", "profiles"),
        ):
            patcher = patch.object(storage, key, self.root / name)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.cfg = storage.load_config()
        storage.create_game_profile("Synthetic Game", {
            "mods_source_dir": str(self.source), "game_mods_dir": str(self.game),
            "mod_mode": "directories", "mod_extensions": ".pak",
            "mod_group_extensions": ".pak,.ucas", "mod_recursive_scan": True,
            "mod_icon_path": "assets/icon.png", "link_prefix": "_prefix",
        }, self.cfg)
        storage.save_config(self.cfg)

    def folder(self, name="Mod"):
        folder = self.source / name
        (folder / "assets").mkdir(parents=True)
        (folder / "assets" / "icon.png").write_bytes(b"synthetic artwork")
        (folder / "content.bin").write_bytes(b"synthetic content")
        return folder

    def test_only_top_level_directories_are_mods_regardless_of_file_filters(self):
        self.folder()
        self.folder("Another")
        (self.source / "loose.pak").touch()
        (self.source / "images").mkdir()
        (self.source / ".mod-import-pending").mkdir()
        mods = discover_mods(self.cfg)
        self.assertEqual([mod.name for mod in mods], ["Another", "Mod"])
        self.assertTrue(all(mod.is_dir for mod in mods))
        self.assertEqual({mod.dest.name for mod in mods}, {"Another", "Mod"})
        self.assertFalse(is_mod_file(self.source / "loose.pak", self.cfg))
        self.assertTrue(is_mod_file(self.source / "Mod", self.cfg))
        self.assertFalse(is_mod_file(self.source / "images", self.cfg))

    def test_install_uninstall_and_presets_preserve_complete_source_in_link_and_copy_modes(self):
        folder = self.folder()
        expected = {path.relative_to(folder): path.read_bytes() for path in folder.rglob("*") if path.is_file()}
        for mode in ("link", "copy"):
            with self.subTest(mode=mode):
                cfg = {**self.cfg, "install_mode": mode}
                mod = discover_mods(cfg)[0]
                self.assertEqual(change_mods([mod], "install").errors, 0)
                self.assertTrue(discover_mods(cfg)[0].installed)
                for relative, data in expected.items():
                    self.assertEqual((self.game / "Mod" / relative).read_bytes(), data)
                self.assertTrue(save_preset_from_installed(cfg, "Synthetic preset")[0])
                self.assertEqual(storage.load_presets()["Synthetic preset"], ["Mod"])
                self.assertTrue(deactivate_mod(discover_mods(cfg)[0])[0])
                self.assertFalse((self.game / "Mod").exists())
                self.assertEqual(apply_preset(cfg, "Synthetic preset")[:2], (1, 0))
                self.assertTrue(deactivate_mod(discover_mods(cfg)[0])[0])
                self.assertEqual({path.relative_to(folder): path.read_bytes()
                                  for path in folder.rglob("*") if path.is_file()}, expected)

    def test_copy_replacement_requires_overwrite_and_never_replaces_source(self):
        folder = self.folder()
        target = self.game / "Mod"
        target.mkdir()
        (target / "old.bin").write_bytes(b"old")
        mod = discover_mods({**self.cfg, "install_mode": "copy"})[0]
        self.assertFalse(apply_mod(mod)[0])
        self.assertEqual((target / "old.bin").read_bytes(), b"old")
        self.assertTrue(apply_mod(mod, overwrite=True)[0])
        self.assertEqual((folder / "content.bin").read_bytes(), b"synthetic content")

    def test_internal_icon_and_manual_override_are_profile_scoped(self):
        folder = self.folder()
        internal = folder / "assets" / "icon.png"
        self.assertEqual(mod_image_path(self.cfg, "Mod"), internal)
        self.assertIsNone(mod_image_path({**self.cfg, "mod_icon_path": ""}, "Mod"))
        self.assertIsNone(mod_image_path({**self.cfg, "mod_icon_path": "missing.png"}, "Mod"))
        self.assertEqual(mod_image_path({**self.cfg, "mod_mode": "standard"}, "Mod"), internal)
        images = self.source / "images"
        images.mkdir()
        override = images / "Mod.png"
        override.write_bytes(b"manual")
        self.assertEqual(mod_image_path(self.cfg, "Mod"), override)
        self.assertEqual(internal.read_bytes(), b"synthetic artwork")

    def test_icon_path_validation_rejects_absolute_and_escaping_paths(self):
        self.folder()
        for value in ("/outside.png", "C:/outside.png", "C:outside.png", "../outside.png",
                      "assets/../../outside.png", "//host/share/icon.png", "."):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    coerce_game_profile({"mod_icon_path": value})
                self.assertIsNone(mod_image_path({**self.cfg, "mod_icon_path": value}, "Mod"))
        self.assertEqual(normalize_icon_path(" assets/icon.png "), "assets/icon.png")
        self.assertEqual(normalize_icon_path(r"assets\icon.png"), "assets/icon.png")
        with self.assertRaises(ValueError):
            normalize_icon_path(r"assets\..\outside.png")
        with self.assertRaises(ValueError):
            normalize_icon_path("bad" + chr(0) + ".png")

    def test_folder_import_preserves_icon_and_rejects_individual_files_without_writing(self):
        incoming = self.root / "Incoming"
        (incoming / "assets").mkdir(parents=True)
        icon = incoming / "assets" / "icon.png"
        icon.write_bytes(b"icon")
        payload = incoming / "payload.bin"
        payload.write_bytes(b"payload")
        self.assertTrue(import_mod_file(self.cfg, incoming)[0])
        self.assertEqual(mod_image_path(self.cfg, "Incoming").read_bytes(), b"icon")
        self.assertEqual(icon.read_bytes(), b"icon")
        self.assertFalse(import_mod_file(self.cfg, payload)[0])
        self.assertFalse((self.source / "payload.bin").exists())
        with self.assertRaisesRegex(ValueError, "Directories mode"):
            regular_import_tasks(self.cfg, [payload], set(), lambda _name: "skip")

    def test_internal_icon_cannot_follow_a_child_junction_outside_the_mod(self):
        folder = self.folder()
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "icon.png").write_bytes(b"external")
        junction = folder / "redirect"
        self.assertTrue(mklink(outside, junction)[0])
        try:
            self.assertIsNone(mod_image_path({**self.cfg, "mod_icon_path": "redirect/icon.png"}, "Mod"))
        finally:
            self.assertTrue(unlink_path(junction)[0])
        self.assertEqual((outside / "icon.png").read_bytes(), b"external")

    def test_archive_modes_always_create_folders_and_retain_artwork(self):
        archive_path = self.root / "bundle.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr("mod.pak", b"pak")
            archive.writestr("mod.ucas", b"ucas")
            archive.writestr("assets/icon.png", b"icon")
            archive.writestr("readme.txt", b"readme")
        for mode in ("together", "separate"):
            for preserve in (False, True):
                with self.subTest(mode=mode, preserve=preserve):
                    destination = self.root / f"{mode}-{preserve}"
                    destination.mkdir()
                    cfg = {**self.cfg, "mods_source_dir": str(destination), "archive_import_mode": mode,
                           "archive_preserve_structure": preserve,
                           "mod_icon_path": "assets/icon.png" if preserve else "icon.png"}
                    prepared = prepare_archive(archive_path, cfg)
                    try:
                        self.assertEqual(len(prepared.units), 2)
                        prepared.selected = {0}
                        plans = create_plans([prepared], lambda _name: "keep_both")
                        self.assertTrue(all(plan.is_directory for plan in plans))
                        self.assertEqual(preview_plans([prepared]), plans)
                        rows = destination_rows(str(destination), plans)
                        self.assertTrue(any(row[-1] == "icon.png" for row in rows))
                        self.assertEqual(execute_plans(cfg, plans)[1], [])
                        name = "bundle" if mode == "together" else "mod"
                        self.assertEqual([mod.name for mod in discover_mods(cfg)], [name])
                        self.assertEqual(mod_image_path(cfg, name).read_bytes(), b"icon")
                        self.assertEqual((destination / name / "mod.pak").read_bytes(), b"pak")
                        self.assertEqual((destination / name / "mod.ucas").read_bytes(), b"ucas")
                        self.assertEqual((destination / name / "readme.txt").exists(), mode == "together")
                    finally:
                        prepared.close()

    def test_separate_archive_selection_scopes_artwork_and_resolves_folder_conflicts(self):
        archive_path = self.root / "bundle.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            for name in ("A", "B"):
                archive.writestr(f"{name}/mod.pak", name.encode())
                archive.writestr(f"{name}/icon.png", name.encode())
        cfg = {**self.cfg, "archive_import_mode": "separate", "mod_icon_path": "icon.png"}
        prepared = prepare_archive(archive_path, cfg)
        try:
            prepared.selected = {1}
            plans = resolve_plans(cfg, create_plans([prepared], lambda _name: "keep_both"), lambda _name: "keep_both")
            self.assertEqual(execute_plans(cfg, plans)[1], [])
            self.assertEqual((self.source / "mod" / "icon.png").read_bytes(), b"B")
            self.assertEqual((self.source / "mod" / "mod.pak").read_bytes(), b"B")
            plans = resolve_plans(cfg, create_plans([prepared], lambda _name: "keep_both"), lambda _name: "keep_both")
            self.assertEqual(plans[0].name, "mod (1)")
            self.assertEqual(execute_plans(cfg, plans)[1], [])
            self.assertEqual((self.source / "mod (1)" / "icon.png").read_bytes(), b"B")
        finally:
            prepared.close()
