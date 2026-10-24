from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mod_manager.models import ModFile, ModItem
from mod_manager.mods import apply_mods_batch, apply_mods_batch_result, change_mods, deactivate_mod_result
from mod_manager.presets import apply_preset, toggle_presets_by_names, toggle_presets_result


class OperationErrorTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        self.destination = self.root / "game"
        self.source.mkdir()
        self.destination.mkdir()
        self.members = tuple(
            ModFile(self.source / f"Weapon{suffix}", self.destination / f"Weapon{suffix}", False)
            for suffix in (".pak", ".utoc", ".ucas")
        )
        for member in self.members:
            member.src.write_text("source payload", encoding="utf-8")
        self.mod = ModItem("Weapon.pak", self.members[0].src, self.members[0].dest,
                           False, False, self.members)

    def test_link_failures_keep_every_member_path_and_original_message(self):
        def link(source, destination):
            if source.suffix == ".pak":
                destination.write_text("installed payload", encoding="utf-8")
                return True, "OK"
            return False, f"Access denied: {source.name}"

        with patch("mod_manager.mods.is_windows", return_value=False), patch(
            "mod_manager.mods.mklink", side_effect=link
        ), patch("mod_manager.mods.mark_mods_managed") as managed:
            result = change_mods([self.mod], action="install")

        self.assertEqual(result.errors, 1)
        self.assertEqual([(error.src, error.dest) for error in result.items[0].failures],
                         [(member.src, member.dest) for member in self.members[1:]])
        self.assertEqual([error.message for error in result.items[0].failures],
                         ["Access denied: Weapon.utoc", "Access denied: Weapon.ucas"])
        managed.assert_not_called()
        self.assertTrue(self.members[0].dest.exists())
        self.assertFalse(self.members[1].dest.exists())
        for member in self.members:
            self.assertEqual(member.src.read_text(encoding="utf-8"), "source payload")

    def test_copy_failure_reports_the_actual_file(self):
        self.mod.copy_install = True
        with patch("mod_manager.links.shutil.copy2", side_effect=PermissionError("File locked")):
            result = apply_mods_batch_result([self.mod])
        self.assertEqual(len(result.items[0].failures), 3)
        self.assertEqual(result.items[0].failures[2].dest, self.members[2].dest)
        self.assertEqual(result.items[0].failures[2].message, "File locked")
        self.assertTrue(all(member.src.exists() for member in self.members))

    def test_uninstall_keeps_every_failed_member_and_source(self):
        self.mod.copy_install = True
        for member in self.members:
            member.dest.write_text("installed", encoding="utf-8")
        with patch("mod_manager.links.Path.unlink", side_effect=PermissionError("File in use")):
            result = deactivate_mod_result(self.mod)
        self.assertFalse(result.success)
        self.assertEqual([error.dest for error in result.failures], [member.dest for member in self.members])
        self.assertTrue(all(member.dest.exists() and member.src.exists() for member in self.members))

    def test_legacy_batch_result_still_returns_the_first_failure(self):
        with patch("mod_manager.mods._link_files", return_value=[
            (True, "OK"), (False, "First error"), (False, "Second error"),
        ]):
            self.assertEqual(apply_mods_batch([self.mod]), [(False, "First error")])

    def test_preset_results_keep_file_failures_and_missing_mods(self):
        with patch("mod_manager.presets.load_presets", return_value={"core": [self.mod.name, "missing.pak"]}), patch(
            "mod_manager.presets.discover_mods", return_value=[self.mod]
        ), patch("mod_manager.mods._link_files", return_value=[(False, "Denied")] * 3), patch(
            "mod_manager.presets.mark_preset_managed"
        ) as managed:
            summary, result = toggle_presets_result({}, ["core"], set())
        self.assertEqual(summary, "Installed: 0, Errors: 2")
        self.assertEqual(result.errors, 2)
        self.assertEqual(result.items[0].name, "missing.pak")
        self.assertEqual(result.items[1].failures[1].src, self.members[1].src)
        managed.assert_not_called()

    def test_successful_preset_keeps_legacy_return_types_and_metadata(self):
        self.mod.copy_install = True
        with patch("mod_manager.presets.load_presets", return_value={"core": [self.mod.name]}), patch(
            "mod_manager.presets.discover_mods", return_value=[self.mod]
        ), patch("mod_manager.presets.mark_preset_managed") as managed:
            result = apply_preset({}, "core")
        self.assertEqual(result, (1, 0, ["Weapon.pak: OK (OK)"]))
        managed.assert_called_once_with("core", "applied")
        self.assertTrue(all(member.dest.exists() and member.src.exists() for member in self.members))

    def test_missing_preset_legacy_result_remains_compatible(self):
        with patch("mod_manager.presets.load_presets", return_value={}):
            self.assertEqual(toggle_presets_by_names({}, ["missing"], set()),
                             ("", ["Skipped: missing (preset not found)"], True))

    def test_empty_preset_legacy_toggle_keeps_the_explanation(self):
        with patch("mod_manager.presets.load_presets", return_value={"empty": []}), patch(
            "mod_manager.presets.discover_mods", return_value=[]
        ), patch("mod_manager.presets.mark_preset_managed"):
            self.assertEqual(toggle_presets_by_names({}, ["empty"], set()),
                             ("Installed: 0, Errors: 0", ["Nothing to install (all present or missing)."], False))
