from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mod_manager.models import ModFile, ModItem
from tests.qt_support import qt_available
from tests.window_fixture import WindowTestCase

if qt_available():
    from PySide6 import QtCore, QtWidgets

    from mod_manager.ui.app import ModManagerGui


@unittest.skipUnless(qt_available(), "PySide6 is not installed")
class ErrorHistoryGuiTests(WindowTestCase):
    def setUp(self):
        super().setUp()
        self.use_inline_runner()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.source = root / "source"
        self.destination = root / "game"
        self.source.mkdir()
        self.destination.mkdir()
        source = self.source / "Weapon.pak"
        source.write_text("source payload", encoding="utf-8")
        self.mod = ModItem(source.name, source, self.destination / source.name, False, False)
        self.mods[:] = [self.mod]
        self.window.current_mods_shown = self.mods
        self.window.cfg.update(mods_source_dir=str(self.source), game_mods_dir=str(self.destination))
        for patcher in (
            patch("mod_manager.mods.is_windows", return_value=False),
            patch("mod_manager.mods.mklink", return_value=(False, "You do not have sufficient privilege")),
            patch("mod_manager.mods.mark_mods_managed"),
            patch("mod_manager.presets.mark_preset_managed"),
            patch("mod_manager.presets.load_presets", return_value={"core": [self.mod.name]}),
            patch("mod_manager.presets.discover_mods", return_value=self.mods),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def install(self):
        self.window._toggle_selected_indexes([1])

    def test_link_error_is_visible_in_clickable_status_and_full_details(self):
        self.assertEqual(self.window.errors.button.text(), "Errors: 0")
        self.assertFalse(self.window.errors.button.isEnabled())
        self.install()
        self.assertEqual(self.window.errors.button.text(), "Errors: 1")
        self.assertTrue(self.window.errors.button.isEnabled())
        self.assertEqual(self.window.context.status_text, "Installed 0/1. Errors: 1.")
        self.assertIsNone(self.window.errors.dialog)
        self.window.errors.button.click()
        dialog = self.window.errors.dialog
        self.assertTrue(dialog.isVisible())
        self.assertFalse(dialog.isModal())
        text = dialog.content.details.toPlainText()
        for value in (self.mod.name, str(self.mod.src), str(self.mod.dest), "sufficient privilege"):
            self.assertIn(value, text)
        self.assertTrue(dialog.content.details.isReadOnly())
        self.assertEqual(self.mod.src.read_text(encoding="utf-8"), "source payload")
        self.assertFalse(self.mod.dest.exists())

    def test_repeated_failures_accumulate_and_success_keeps_history(self):
        self.install()
        self.window.errors.button.click()
        dialog = self.window.errors.dialog
        self.install()
        self.assertEqual(dialog.content.table.model().rowCount(), 2)
        dialog.close()
        with patch("mod_manager.mods.mklink", return_value=(True, "OK")):
            self.install()
        self.assertEqual(self.window.errors.button.text(), "Errors: 2")
        self.window._set_status("Settings saved")
        self.assertTrue(self.window.errors.button.isVisibleTo(self.window.statusBar()))
        self.window.errors.button.click()
        self.assertIs(self.window.errors.dialog, dialog)
        self.assertEqual(dialog.content.table.model().rowCount(), 2)

    def test_every_failed_group_member_gets_its_own_row(self):
        self.mod.files = tuple(
            ModFile(self.source / f"Weapon{suffix}", self.destination / f"Weapon{suffix}", False)
            for suffix in (".pak", ".utoc", ".ucas")
        )
        with patch("mod_manager.mods.mklink", side_effect=[
            (True, "OK"), (False, "UTOC denied"), (False, "UCAS locked"),
        ]):
            self.install()
        self.assertEqual(self.window.errors.button.text(), "Errors: 2")
        self.window.errors.button.click()
        content = self.window.errors.dialog.content
        self.assertIn("Weapon.utoc", content.details.toPlainText())
        self.assertIn("UTOC denied", content.details.toPlainText())
        content.table.selectRow(1)
        self.assertIn("Weapon.ucas", content.details.toPlainText())
        self.assertIn("UCAS locked", content.details.toPlainText())

    def test_page_install_reports_errors_through_the_real_domain_operation(self):
        with patch("mod_manager.mods.mods_view", return_value=(self.mods, self.mods, 1, 1, {})):
            self.window._install_page()
        self.assertEqual(self.window.errors.button.text(), "Errors: 1")
        self.assertEqual(self.window.context.status_text, "Installed 0/1 on page 1. Errors: 1.")

    def test_preset_install_reports_file_error(self):
        self.window.presets_table.selectRow(0)
        self.window._toggle_selected_presets()
        entry = self.window.errors.model.entries[0]
        self.assertEqual(entry.failure.src, self.mod.src)
        self.assertEqual(entry.failure.dest, self.mod.dest)
        self.assertIn("sufficient privilege", entry.message)

    def test_uninstall_and_broken_cleanup_accumulate_errors(self):
        self.mod.installed = True
        self.mod.dest.write_text("installed", encoding="utf-8")
        with patch("mod_manager.mods.unlink_path", return_value=(False, "File locked")):
            self.install()
            self.window.current_broken = self.mods
            self.window._remove_all_broken()
        self.assertEqual(self.window.errors.button.text(), "Errors: 2")
        self.assertEqual([entry.action for entry in self.window.errors.model.entries], ["uninstalled"] * 2)
        self.assertTrue(self.mod.src.exists())
        self.assertTrue(self.mod.dest.exists())

    def test_preset_uninstall_and_page_uninstall_keep_details(self):
        self.mod.installed = True
        self.mod.dest.write_text("installed", encoding="utf-8")
        self.window.presets_table.selectRow(0)
        with patch("mod_manager.mods.unlink_path", return_value=(False, "Cannot remove link")), patch(
            "mod_manager.ui.app.list_installed_mods", return_value=self.mods
        ), patch("mod_manager.mods.mods_view", return_value=(self.mods, self.mods, 1, 1, {})):
            self.window._toggle_selected_presets()
            self.window._uninstall_page()
        self.assertEqual(self.window.errors.model.rowCount(), 2)
        self.assertTrue(all(entry.message == "Cannot remove link" for entry in self.window.errors.model.entries))

    def test_missing_preset_mod_and_unexpected_operation_failure_have_context(self):
        with patch("mod_manager.presets.load_presets", return_value={"core": ["missing.pak"]}):
            self.window.presets_table.selectRow(0)
            self.window._toggle_selected_presets()
        first = self.window.errors.model.entries[0]
        self.assertEqual(first.mod, "missing.pak")
        self.assertIsNone(first.failure)
        with patch("mod_manager.mods.mklink", side_effect=OSError("Backend unavailable")):
            self.install()
        second = self.window.errors.model.entries[1]
        self.assertEqual(second.message, "Backend unavailable")
        self.assertIsNone(second.failure)
        self.assertIn("Updating selected mods", second.mod)

    def test_profile_switch_keeps_history_and_original_profile_name(self):
        self.window.cfg["game_profiles"] = [
            {"id": "first", "name": "First Game"}, {"id": "second", "name": "Second Game"},
        ]
        self.window.cfg["active_game_profile_id"] = "first"
        self.install()
        with patch("mod_manager.ui.controllers.games_controller.save_config"), patch(
            "mod_manager.ui.controllers.games_controller.load_config", side_effect=lambda: self.window.cfg
        ):
            self.window._select_game_profile("second")
        self.window.current_mods_shown = self.mods
        self.install()
        self.assertEqual([entry.profile for entry in self.window.errors.model.entries],
                         ["First Game", "Second Game"])

    def test_history_is_empty_in_a_new_window(self):
        self.install()
        from tests.qt_support import dispose

        other = ModManagerGui()
        try:
            self.assertEqual(other.errors.model.rowCount(), 0)
            self.assertEqual(other.errors.button.text(), "Errors: 0")
        finally:
            dispose(other)

    def test_detail_paths_are_shortened_with_full_tooltips_at_minimum_size(self):
        name = "Weapon" * 24 + ".pak"
        self.mod.src = self.source / "Game" / "Mods" / name
        self.mod.dest = self.destination / "Game" / "Mods" / name
        self.window._set_view_mode("tiles")
        self.window.resize(self.window.minimumSize())
        self.window.show()
        self.window._refresh_mod_detail(self.mod)
        self.qt_app.processEvents()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        buttons = [button for button in self.window.detail_frame.findChildren(QtWidgets.QPushButton)
                   if button.toolTip() in (str(self.mod.src), str(self.mod.dest))]
        self.assertEqual(len(buttons), 2)
        self.assertGreaterEqual(self.window.detail_scroll.width(), 280)
        for button in buttons:
            self.assertLessEqual(len(button.text()), 100)
            self.assertIn("…", button.text())
            self.assertGreater(len(button.text()), 1)
            self.assertLessEqual(button.geometry().right(), self.window.detail_frame.width())
            right = button.mapTo(self.window.detail_scroll.viewport(), button.rect().topRight())
            self.assertLess(right.x(), self.window.detail_scroll.viewport().width())
            self.assertEqual(button.sizePolicy().horizontalPolicy(), QtWidgets.QSizePolicy.Ignored)
