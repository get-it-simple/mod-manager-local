from __future__ import annotations

import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from mod_manager.models import ModItem
from tests.qt_support import qt_available
from tests.window_fixture import WindowTestCase


@unittest.skipUnless(qt_available(), "PySide6 is not installed")
class CopyRecoveryGuiTests(WindowTestCase):
    def setUp(self):
        super().setUp()
        self.use_inline_runner()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        self.game = self.root / "game"
        self.source.mkdir()
        self.game.mkdir()
        source = self.source / "Weapon.pak"
        source.write_text("source payload", encoding="utf-8")
        self.mod = ModItem(source.name, source, self.game / source.name, False, False)
        self.mods[:] = [self.mod]
        self.presets["core"] = [self.mod.name]
        self.window.current_mods_shown = self.mods
        profile = {
            "id": "recovery", "name": "Recovery game", "mods_source_dir": str(self.source),
            "game_mods_dir": str(self.game), "install_mode": "link",
        }
        self.window.cfg.update(profile)
        self.window.cfg.update(game_profiles=[profile], active_game_profile_id="recovery")
        for patcher in (
            patch("mod_manager.links.supports_links", return_value=False),
            patch("mod_manager.mods.mark_mods_managed"),
            patch("mod_manager.presets.mark_preset_managed"),
            patch("mod_manager.link_recovery.mark_preset_managed"),
            patch("mod_manager.presets.load_presets", return_value={"core": [self.mod.name]}),
            patch("mod_manager.link_recovery.load_presets", return_value={"core": [self.mod.name]}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def install(self):
        self.window._toggle_selected_indexes([1])

    def test_accept_saves_profile_copies_and_keeps_original_error_history(self):
        with patch("mod_manager.ui.dialogs.prompts.ask_yes_no", return_value=True) as ask, patch(
            "mod_manager.storage.save_config",
        ) as save:
            self.install()
        ask.assert_called_once()
        self.assertTrue(ask.call_args.kwargs["default_no"])
        save.assert_called_once()
        self.assertEqual(self.window.cfg["install_mode"], "copy")
        self.assertEqual(self.window.cfg["game_profiles"][0]["install_mode"], "copy")
        self.assertEqual(self.mod.dest.read_bytes(), self.mod.src.read_bytes())
        self.assertEqual(self.window.errors.model.rowCount(), 1)
        self.assertIn("Installed 1/1", self.window.context.status_text)
        self.assertFalse(self.window.errors.recovering)

    def test_decline_does_not_change_profile_or_files(self):
        original = deepcopy(self.window.cfg)
        with patch("mod_manager.ui.dialogs.prompts.ask_yes_no", return_value=False), patch(
            "mod_manager.storage.save_config",
        ) as save:
            self.install()
        self.assertEqual(self.window.cfg, original)
        save.assert_not_called()
        self.assertFalse(self.mod.dest.exists())
        self.assertEqual(self.window.errors.model.rowCount(), 1)

    def test_save_error_is_visible_and_stops_retry(self):
        original = deepcopy(self.window.cfg)
        with patch("mod_manager.ui.dialogs.prompts.ask_yes_no", return_value=True), patch(
            "mod_manager.storage.save_config", side_effect=PermissionError("Cannot save profile"),
        ), patch("mod_manager.ui.dialogs.prompts.show_error") as error:
            self.install()
        self.assertIn("Cannot save profile", error.call_args.args[-1])
        self.assertEqual(self.window.cfg, original)
        self.assertFalse(self.mod.dest.exists())
        self.assertFalse(self.window.errors.recovering)

    def test_changed_profile_is_rejected_after_confirmation(self):
        def change_profile(*args, **kwargs):
            self.window.cfg["game_mods_dir"] = str(self.root / "changed")
            return True

        with patch("mod_manager.ui.dialogs.prompts.ask_yes_no", side_effect=change_profile), patch(
            "mod_manager.ui.dialogs.prompts.show_error",
        ) as error, patch("mod_manager.storage.save_config") as save:
            self.install()
        self.assertIn("changed", error.call_args.args[-1])
        save.assert_not_called()
        self.assertFalse(self.mod.dest.exists())

    def test_conflict_requires_a_separate_confirmation(self):
        def collide(*args, **kwargs):
            self.mod.dest.write_text("external file", encoding="utf-8")
            return True

        def answer(*args, **kwargs):
            return collide() if kwargs.get("default_no") else False

        with patch("mod_manager.ui.dialogs.prompts.ask_yes_no", side_effect=answer) as ask:
            self.install()
        self.assertEqual(ask.call_count, 2)
        self.assertEqual(self.mod.dest.read_text(encoding="utf-8"), "external file")
        self.assertEqual(self.window.cfg["install_mode"], "link")

    def test_copy_failure_is_added_to_history_without_another_offer(self):
        with patch("mod_manager.ui.dialogs.prompts.ask_yes_no", return_value=True) as ask, patch(
            "mod_manager.links.shutil.copy2", side_effect=PermissionError("File locked"),
        ):
            self.install()
        ask.assert_called_once()
        self.assertEqual(self.window.errors.model.rowCount(), 2)
        self.assertEqual(self.window.cfg["install_mode"], "copy")
        self.assertFalse(self.mod.dest.exists())
        self.assertFalse(self.window.errors.recovering)

    def test_page_install_uses_copy_recovery(self):
        with patch("mod_manager.mods.mods_view", return_value=(self.mods, self.mods, 1, 1, {})), patch(
            "mod_manager.ui.dialogs.prompts.ask_yes_no", return_value=True,
        ):
            self.window._install_page()
        self.assertEqual(self.mod.dest.read_bytes(), self.mod.src.read_bytes())
        self.assertIn("Installed 1/1 on page 1", self.window.context.status_text)

    def test_preset_install_uses_copy_recovery(self):
        self.window.presets_table.selectRow(0)
        with patch("mod_manager.ui.app.list_installed_mods", return_value=[]), patch(
            "mod_manager.ui.dialogs.prompts.ask_yes_no", return_value=True,
        ), patch("mod_manager.link_recovery.mark_preset_managed") as managed:
            self.window._toggle_selected_presets()
        self.assertEqual(self.mod.dest.read_bytes(), self.mod.src.read_bytes())
        self.assertIn("Installed 1/1", self.window.context.status_text)
        managed.assert_called_once_with("core", "applied")

    def test_duplicate_action_during_confirmation_is_ignored(self):
        def answer(*args, **kwargs):
            self.install()
            return True

        with patch("mod_manager.ui.dialogs.prompts.ask_yes_no", side_effect=answer) as ask:
            self.install()
        ask.assert_called_once()
        self.assertEqual(self.window.errors.model.rowCount(), 1)
        self.assertTrue(self.mod.dest.exists())

    def test_successful_retry_does_not_duplicate_an_unrelated_uninstall_error(self):
        old = self.game / "old.pak"
        old.write_text("installed", encoding="utf-8")
        installed = ModItem("old.pak", self.source / "old.pak", old, False, True)
        self.mods.append(installed)
        with patch("mod_manager.ui.dialogs.prompts.ask_yes_no", return_value=True), patch(
            "mod_manager.mods.unlink_path", return_value=(False, "File in use"),
        ):
            self.window._toggle_selected_indexes([1, 2])
        self.assertEqual(self.window.errors.model.rowCount(), 2)
        self.assertEqual(old.read_text(encoding="utf-8"), "installed")
        self.assertTrue(self.mod.dest.exists())

    def test_ordinary_link_error_does_not_offer_to_change_the_profile(self):
        with patch("mod_manager.mods._link_files", return_value=[(False, "Access denied")]), patch(
            "mod_manager.ui.dialogs.prompts.ask_yes_no",
        ) as ask:
            self.install()
        ask.assert_not_called()
        self.assertEqual(self.window.cfg["install_mode"], "link")
