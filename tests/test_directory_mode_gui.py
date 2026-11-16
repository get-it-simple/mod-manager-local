from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from PySide6 import QtCore, QtGui, QtWidgets

from mod_manager.models import ModItem
from mod_manager.mods import mod_image_path
from mod_manager.ui.dialogs.game_profile import GameProfileDialog
from tests.qt_support import dispose
from tests.window_fixture import WindowTestCase


class DirectoryModeGuiTests(WindowTestCase):
    def test_profile_dialog_exposes_readable_mode_and_validates_relative_icon_path(self):
        dialog = GameProfileDialog(self.window, {
            "name": "Synthetic Game", "mod_mode": "directories", "mod_icon_path": "assets/icon.png",
        })
        try:
            mode = dialog.form.fields["mod_mode"]
            self.assertEqual(mode.currentText(), "Directories")
            self.assertEqual(dialog.form.values()["mod_mode"], "directories")
            self.assertTrue(mode.toolTip())
            icon = dialog.form.fields["mod_icon_path"]
            self.assertTrue(icon.toolTip())
            icon.setText("../outside.png")
            with patch("mod_manager.ui.dialogs.prompts.show_error") as error:
                dialog.accept()
            self.assertEqual(error.call_count, 1)
            self.assertNotEqual(dialog.result(), QtWidgets.QDialog.Accepted)
            icon.setText("assets/icon.png")
            dialog.accept()
            self.assertEqual(dialog.result(), QtWidgets.QDialog.Accepted)
            self.assertEqual(dialog.form.values()["mod_icon_path"], "assets/icon.png")
        finally:
            dispose(dialog)

    def test_icon_pixels_refresh_after_profile_path_change_and_manual_preview_wins(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mod = root / "Folder Mod"
            (mod / "assets").mkdir(parents=True)
            colors = [(20, 40, 60), (70, 90, 110), (120, 140, 160)]
            paths = [mod / "assets" / "first.png", mod / "assets" / "second.png", root / "images" / "Folder Mod.png"]
            for path, color in zip(paths[:2], colors[:2]):
                self.save_image(path, color)
            self.window.cfg.update(mods_source_dir=str(root), mod_mode="directories", mod_icon_path="assets/first.png")
            self.mods[:] = [ModItem("Folder Mod", mod, root / "game" / "Folder Mod", True, False)]
            with patch("mod_manager.ui.app.mod_image_path", side_effect=mod_image_path):
                self.window.refresh_mods()
                self.assert_preview_color(colors[0])
                self.window.cfg["mod_icon_path"] = "assets/second.png"
                self.window.refresh_mods()
                self.assert_preview_color(colors[1])
                self.save_image(paths[2], colors[2])
                self.window.refresh_all(reload_artwork=True)
                self.assert_preview_color(colors[2])
                paths[2].unlink()
                paths[1].write_bytes(b"synthetic invalid image")
                self.window.refresh_all(reload_artwork=True)
                preview = self.window.images.request(self.window.cfg, "Folder Mod", QtCore.QSize(24, 24))
                self.assertTrue(preview is None or preview.isNull())

    def assert_preview_color(self, color):
        pixmap = self.window.images.request(self.window.cfg, "Folder Mod", QtCore.QSize(24, 24))
        self.assertIsNotNone(pixmap)
        self.assertEqual(pixmap.toImage().pixelColor(12, 12).getRgb()[:3], color)

    def save_image(self, path, color):
        path.parent.mkdir(parents=True, exist_ok=True)
        image = QtGui.QImage(16, 16, QtGui.QImage.Format_ARGB32)
        image.fill(QtGui.QColor(*color))
        self.assertTrue(image.save(str(path)))

    def test_loose_file_drop_reports_directory_mode_and_keeps_preview_assignment_available(self):
        self.window.cfg["mod_mode"] = "directories"
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "loose.pak"
            path.touch()
            with patch.object(self.window, "_run_action") as run:
                self.window._import_regular_paths([path])
            run.assert_not_called()
            self.assertIn("Directories mode accepts mod folders", self.window.runner.status_text)
