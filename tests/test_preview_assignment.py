from __future__ import annotations

import shutil
import tempfile
from functools import partial
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6 import QtCore, QtGui, QtTest

from mod_manager.dragdrop import TransferredPaths
from mod_manager.mods import mod_image_path
from mod_manager.ui.image_clipboard import read_clipboard_image
from tests.window_fixture import WindowTestCase


class PreviewAssignmentTests(WindowTestCase):
    def setUp(self):
        super().setUp()
        self.use_inline_runner()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "mods"
        self.source.mkdir()
        self.window.cfg["mods_source_dir"] = str(self.source)
        self.clipboard_paths = []
        self.clipboard_image = None
        for module in ("mod_manager.ui.app", "mod_manager.ui.controllers.preview_controller"):
            self.start_patch(f"{module}.read_clipboard_paths", side_effect=lambda: self.clipboard_paths)
            self.start_patch(f"{module}.read_clipboard_image", side_effect=lambda: self.clipboard_image)
        self.confirm = self.start_patch("mod_manager.ui.dialogs.prompts.choose_preview_image", return_value="apply")
        self.chooser = self.start_patch("mod_manager.ui.dialogs.prompts.choose_open_file", return_value="")
        self.picker = self.start_patch("mod_manager.ui.dialogs.prompts.choose_item", return_value=("ui.pak", True))
        self.start_patch("mod_manager.ui.app.mod_image_path", side_effect=mod_image_path)
        self.image = self.make_image("art.png", "red")

    def start_patch(self, target, **kwargs):
        patcher = patch(target, **kwargs)
        result = patcher.start()
        self.addCleanup(patcher.stop)
        return result

    def make_image(self, name, color):
        image = QtGui.QImage(48, 24, QtGui.QImage.Format_RGB32)
        image.fill(QtGui.QColor(color))
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        self.assertTrue(image.save(str(path)))
        return path

    def use_qt_clipboard(self, color="red"):
        image = QtGui.QImage(48, 24, QtGui.QImage.Format_ARGB32)
        image.fill(QtGui.QColor(color))
        clipboard = Mock()
        clipboard.image.return_value = image
        mime = QtCore.QMimeData()
        mime.setImageData(image)
        clipboard.mimeData.return_value = mime
        self.start_patch("mod_manager.ui.image_clipboard.QtWidgets.QApplication.clipboard", return_value=clipboard)
        self.start_patch("mod_manager.ui.image_clipboard.read_native_clipboard_image", return_value=None)
        self.start_patch("mod_manager.ui.image_clipboard.tempfile.NamedTemporaryFile", side_effect=partial(tempfile.NamedTemporaryFile, dir=self.root))
        for module in ("mod_manager.ui.app", "mod_manager.ui.controllers.preview_controller"):
            self.start_patch(f"{module}.read_clipboard_image", side_effect=read_clipboard_image)
        return clipboard

    def test_qt_clipboard_bitmap_sets_preview_in_list_and_tiles(self):
        self.use_qt_clipboard()
        for mode in ("list", "tiles"):
            with self.subTest(mode=mode):
                self.window._set_view_mode(mode)
                self.select_mod_rows(1)
                self.window._handle_paste()
                self.assert_preview("ui.pak")
                self.assertEqual(self.window._selected_mod_names(), ["ui.pak"])
                self.assertEqual(list(self.root.glob("mods_clip_*.png")), [])
        self.confirm.assert_not_called()
        self.picker.assert_not_called()

    def test_qt_clipboard_offer_confirms_batch_and_cleans_up(self):
        self.use_qt_clipboard()
        self.select_mod_rows(0, 1)
        self.window._set_mod_image()
        self.confirm.assert_called_once()
        self.assertEqual(self.confirm.call_args.args[2], 2)
        self.assertTrue(self.confirm.call_args.kwargs["clipboard"])
        self.assertFalse(self.confirm.call_args.args[1].exists())
        self.chooser.assert_not_called()
        self.assert_preview("combat.pak")
        self.assert_preview("ui.pak")
        self.assertEqual(set(self.window._selected_mod_names()), {"combat.pak", "ui.pak"})

    def test_qt_bitmap_preserves_transparency_in_stored_preview(self):
        color = QtGui.QColor(32, 64, 128, 96)
        self.use_qt_clipboard(color)
        self.select_mod_rows(1)
        self.window._handle_paste()
        self.assert_preview("ui.pak", color)
        self.assertEqual(list(self.root.glob("mods_clip_*.png")), [])

    def test_cancel_qt_clipboard_offer_preserves_existing_preview(self):
        self.use_qt_clipboard()
        self.select_mod_rows(0)
        self.make_image("mods/images/combat.pak.png", "blue")
        self.confirm.return_value = "cancel"
        self.window._set_mod_image()
        self.assert_preview("combat.pak", "blue")
        self.assertFalse(self.confirm.call_args.args[1].exists())
        self.chooser.assert_not_called()

    def test_qt_bitmap_paste_from_search_confirms_only_once(self):
        self.use_qt_clipboard()
        self.select_mod_rows(0, 1)
        self.window.show()
        search = self.window.search_box.lineEdit()
        search.setFocus()
        self.qt_app.processEvents()
        with patch("mod_manager.ui.app.clipboard_has_files", return_value=False):
            QtTest.QTest.keyClick(search, QtCore.Qt.Key_V, QtCore.Qt.ControlModifier)
        self.assert_preview("combat.pak")
        self.assert_preview("ui.pak")
        self.confirm.assert_called_once()
        self.assertEqual(search.text(), "")

    def test_image_paste_respects_disabled_and_remapped_shortcuts(self):
        self.use_qt_clipboard()
        self.select_mod_rows(0)
        search = self.window.search_box.lineEdit()
        for binding in ({"combo": "ctrl+v", "enabled": False}, {"combo": "ctrl+g", "enabled": True}):
            with self.subTest(binding=binding):
                self.window.keyboard.bindings["paste"] = binding
                for kind in (QtCore.QEvent.ShortcutOverride, QtCore.QEvent.KeyPress):
                    event = QtGui.QKeyEvent(kind, QtCore.Qt.Key_V, QtCore.Qt.ControlModifier)
                    with patch("mod_manager.ui.app.clipboard_has_files", return_value=False):
                        self.assertFalse(self.window.eventFilter(search, event))
                self.assert_no_previews()

    def test_qt_bitmap_is_not_imported_while_busy_or_on_settings_page(self):
        self.use_qt_clipboard()
        self.select_mod_rows(0)
        self.window._set_busy(True)
        self.window._handle_paste()
        self.window._set_busy(False)
        self.window._open_settings_page()
        self.window._handle_paste()
        self.assert_no_previews()
        self.assertEqual(list(self.root.glob("mods_clip_*.png")), [])

    def test_recording_ctrl_v_does_not_import_qt_bitmap(self):
        self.use_qt_clipboard()
        self.window._open_settings_page()
        self.window.show()
        shortcuts = self.window.settings.fields["keyboard_shortcuts"]
        shortcuts.toggle.setChecked(True)
        editor = shortcuts.rows["refresh"][0]
        editor.capture.setFocus()
        self.qt_app.processEvents()
        QtTest.QTest.keyClick(editor.capture, QtCore.Qt.Key_V, QtCore.Qt.ControlModifier)
        self.assertEqual(editor.combo(), "ctrl+v")
        self.assert_no_previews()

    def test_qt_bitmap_write_errors_are_visible_and_preserve_preview(self):
        self.use_qt_clipboard()
        self.select_mod_rows(0)
        self.make_image("mods/images/combat.pak.png", "blue")
        for action in (self.window._handle_paste, self.window._set_mod_image):
            with self.subTest(action=action.__name__), patch.object(QtGui.QImage, "save", return_value=False), patch(
                "mod_manager.ui.dialogs.prompts.show_error"
            ) as error:
                action()
                error.assert_called_once()
                self.assertIn("Cannot prepare", error.call_args.args[2])
            self.assert_preview("combat.pak", "blue")
            self.assertEqual(list(self.root.glob("mods_clip_*.png")), [])

    def assert_preview(self, name, color="red"):
        path = mod_image_path(self.window.cfg, name)
        self.assertIsNotNone(path)
        image = QtGui.QImage(str(path))
        self.assertFalse(image.isNull())
        self.assertEqual(image.size(), QtCore.QSize(48, 24))
        self.assertEqual(image.pixelColor(20, 10), QtGui.QColor(color))

    def assert_no_previews(self):
        self.assertFalse((self.source / "images").exists())

    def test_paste_image_file_with_single_selected_mod_targets_it_without_picker(self):
        original = self.image.read_bytes()
        for mode in ("list", "tiles"):
            with self.subTest(mode=mode):
                self.window._set_view_mode(mode)
                self.select_mod_rows(1)
                self.clipboard_paths = [self.image]
                self.window._handle_paste()
                self.assert_preview("ui.pak")
                self.assertIsNone(mod_image_path(self.window.cfg, "combat.pak"))
                self.assertEqual(self.window._selected_mod_names(), ["ui.pak"])
        self.confirm.assert_not_called()
        self.picker.assert_not_called()
        self.assertEqual(self.image.read_bytes(), original)

    def test_paste_image_with_single_selected_mod_skips_picker_and_releases_temp(self):
        self.select_mod_rows(0)
        self.clipboard_image = self.image
        self.window._handle_paste()
        self.assert_preview("combat.pak")
        self.assertFalse(self.image.exists())
        self.picker.assert_not_called()
        self.confirm.assert_not_called()

    def test_paste_image_without_selection_still_opens_picker(self):
        self.select_mod_rows()
        self.clipboard_paths = [self.image]
        self.window._handle_paste()
        self.picker.assert_called_once()
        self.assert_preview("ui.pak")
        self.assertIsNone(mod_image_path(self.window.cfg, "combat.pak"))

    def test_cancel_mod_picker_releases_raw_image_without_writing(self):
        self.select_mod_rows()
        self.clipboard_image = self.image
        self.picker.return_value = ("", False)
        self.window._handle_paste()
        self.assert_no_previews()
        self.assertFalse(self.image.exists())

    def test_paste_one_file_applies_to_all_selected_mods_after_confirmation(self):
        for mode in ("list", "tiles"):
            with self.subTest(mode=mode):
                self.window._set_view_mode(mode)
                self.select_mod_rows(0, 1)
                self.clipboard_paths = [self.image]
                self.window._handle_paste()
                self.assert_preview("combat.pak")
                self.assert_preview("ui.pak")
                self.assertEqual(set(self.window._selected_mod_names()), {"combat.pak", "ui.pak"})
        self.assertEqual(self.confirm.call_count, 2)
        self.assertEqual(self.confirm.call_args.args[1:], (self.image, 2))
        self.assertTrue(self.image.exists())
        self.picker.assert_not_called()

    def test_paste_raw_image_applies_to_all_selected_mods_and_releases_temp(self):
        self.select_mod_rows(0, 1)
        self.clipboard_image = self.image
        self.window._handle_paste()
        self.assert_preview("combat.pak")
        self.assert_preview("ui.pak")
        self.confirm.assert_called_once()
        self.assertFalse(self.image.exists())

    def test_cancel_batch_preserves_existing_previews_and_source(self):
        old = self.make_image("mods/images/combat.pak.png", "blue")
        original = old.read_bytes()
        self.select_mod_rows(0, 1)
        self.clipboard_paths = [self.image]
        self.confirm.return_value = "cancel"
        self.window._handle_paste()
        self.assertEqual(old.read_bytes(), original)
        self.assertIsNone(mod_image_path(self.window.cfg, "ui.pak"))
        self.assertTrue(self.image.exists())

    def test_cancel_batch_releases_raw_clipboard_image(self):
        self.select_mod_rows(0, 1)
        self.clipboard_image = self.image
        self.confirm.return_value = "cancel"
        self.window._handle_paste()
        self.assertFalse(self.image.exists())
        self.assert_no_previews()

    def test_multiple_image_files_are_rejected_without_changes(self):
        self.select_mod_rows(0, 1)
        second = self.make_image("other.jpg", "blue")
        self.clipboard_paths = [self.image, second]
        with patch("mod_manager.ui.dialogs.prompts.show_warning") as warning:
            self.window._handle_paste()
        warning.assert_called_once()
        self.assert_no_previews()
        self.confirm.assert_not_called()

    def test_invalid_image_preserves_existing_preview(self):
        self.select_mod_rows(0)
        self.make_image("mods/images/combat.pak.png", "blue")
        self.image.write_bytes(b"not an image")
        self.clipboard_paths = [self.image]
        with patch("mod_manager.ui.dialogs.prompts.show_error") as error:
            self.window._handle_paste()
        error.assert_called_once()
        self.assert_preview("combat.pak", "blue")

    def test_set_preview_offers_clipboard_file_and_applies_without_file_chooser(self):
        self.select_mod_rows(1)
        self.clipboard_paths = [self.image]
        self.window._set_mod_image()
        self.confirm.assert_called_once_with(self.window, self.image, 1, clipboard=True)
        self.chooser.assert_not_called()
        self.assert_preview("ui.pak")
        self.assertTrue(self.image.exists())

    def test_set_preview_clipboard_offer_also_confirms_batch(self):
        self.select_mod_rows(0, 1)
        self.clipboard_image = self.image
        self.window._set_mod_image()
        self.confirm.assert_called_once_with(self.window, self.image, 2, clipboard=True)
        self.chooser.assert_not_called()
        self.assert_preview("combat.pak")
        self.assert_preview("ui.pak")
        self.assertFalse(self.image.exists())

    def test_declining_clipboard_offer_opens_chooser_and_confirms_chosen_batch_image(self):
        self.select_mod_rows(0, 1)
        other = self.make_image("chosen.jpg", "blue")
        self.clipboard_image = self.image
        self.confirm.side_effect = ["file", "apply"]
        self.chooser.return_value = str(other)
        self.window._set_mod_image()
        self.chooser.assert_called_once()
        self.assertEqual(self.confirm.call_count, 2)
        self.assertEqual(self.confirm.call_args.args[1:], (other, 2))
        decoded_color = QtGui.QImage(str(other)).pixelColor(20, 10)
        self.assert_preview("combat.pak", decoded_color)
        self.assert_preview("ui.pak", decoded_color)
        self.assertFalse(self.image.exists())
        self.assertTrue(other.exists())

    def test_declining_clipboard_offer_for_single_mod_uses_chosen_file_directly(self):
        self.select_mod_rows(1)
        self.clipboard_paths = [self.image]
        other = self.make_image("chosen.png", "blue")
        self.confirm.return_value = "file"
        self.chooser.return_value = str(other)
        self.window._set_mod_image()
        self.confirm.assert_called_once()
        self.assert_preview("ui.pak", "blue")
        self.assertTrue(self.image.exists())

    def test_cancel_clipboard_offer_releases_temp_without_opening_chooser(self):
        self.select_mod_rows(0)
        self.clipboard_image = self.image
        self.confirm.return_value = "cancel"
        self.window._set_mod_image()
        self.chooser.assert_not_called()
        self.assert_no_previews()
        self.assertFalse(self.image.exists())

    def test_absent_invalid_and_multiple_clipboard_images_open_file_chooser(self):
        self.select_mod_rows(0)
        invalid = self.root / "broken.png"
        invalid.write_bytes(b"broken")
        for paths in ([], [invalid], [self.image, invalid]):
            with self.subTest(paths=paths):
                self.clipboard_paths = paths
                self.chooser.reset_mock()
                self.window._set_mod_image()
                self.chooser.assert_called_once()
                self.assert_no_previews()
        self.confirm.assert_not_called()

    def test_manual_file_choice_requires_batch_confirmation(self):
        self.select_mod_rows(0, 1)
        self.chooser.return_value = str(self.image)
        self.window._set_mod_image()
        self.confirm.assert_called_once_with(self.window, self.image, 2)
        self.assert_preview("combat.pak")
        self.assert_preview("ui.pak")

    def test_cancel_manual_batch_confirmation_leaves_previews_unchanged(self):
        self.select_mod_rows(0, 1)
        self.chooser.return_value = str(self.image)
        self.confirm.return_value = "cancel"
        self.window._set_mod_image()
        self.assert_no_previews()

    def test_set_preview_without_selection_does_not_read_clipboard(self):
        self.select_mod_rows()
        with patch("mod_manager.ui.controllers.preview_controller.read_clipboard_paths") as read:
            self.window._set_mod_image()
        read.assert_not_called()
        self.chooser.assert_not_called()

    def test_file_paste_with_search_focus_sets_preview_once(self):
        self.select_mod_rows(1)
        self.clipboard_paths = [self.image]
        search = self.window.search_box.lineEdit()
        for event_type in (QtCore.QEvent.ShortcutOverride, QtCore.QEvent.KeyPress):
            event = QtGui.QKeyEvent(event_type, QtCore.Qt.Key_V, QtCore.Qt.ControlModifier)
            with patch("mod_manager.ui.app.clipboard_has_files", return_value=True):
                self.assertTrue(self.window.eventFilter(search, event))
            if event_type == QtCore.QEvent.ShortcutOverride:
                self.assert_no_previews()
        self.assert_preview("ui.pak")
        self.assertNotIn("art.png", search.text())

    def test_virtual_image_is_released_after_confirmation_or_cancel(self):
        self.select_mod_rows(0, 1)
        for choice in ("apply", "cancel"):
            with self.subTest(choice=choice):
                owner = tempfile.TemporaryDirectory(dir=self.root)
                virtual = Path(owner.name) / "virtual.png"
                shutil.copyfile(self.image, virtual)
                self.clipboard_paths = TransferredPaths([virtual], owner)
                self.confirm.return_value = choice
                self.window._handle_paste()
                self.assertFalse(virtual.parent.exists())

    def test_failed_target_does_not_stop_other_mods_and_reports_error(self):
        self.select_mod_rows(0, 1)
        self.clipboard_paths = [self.image]
        self.make_image("mods/images/combat.pak.png", "blue")
        replace = Path.replace

        def replace_with_locked_target(source, destination):
            if Path(destination).name == "combat.pak.png":
                raise PermissionError("preview is locked")
            return replace(source, destination)

        with patch.object(Path, "replace", replace_with_locked_target), patch(
            "mod_manager.ui.dialogs.prompts.show_warning"
        ) as warning:
            self.window._handle_paste()
        self.assert_preview("ui.pak")
        self.assert_preview("combat.pak", "blue")
        self.assertFalse(list((self.source / "images").glob(".mod-preview-*")))
        self.assertIn("combat.pak", warning.call_args.args[2])
        self.assertIn("updated: 1. Failed: 1", self.window.context.status_text)

    def test_image_remains_available_until_background_work_finishes(self):
        self.select_mod_rows(0)
        self.clipboard_image = self.image
        pending = []
        self.window._run_action = lambda label, worker, done: pending.append((worker, done))
        self.window._handle_paste()
        self.assertTrue(self.image.exists())
        self.assert_no_previews()
        worker, done = pending.pop()
        done(worker())
        self.assert_preview("combat.pak")
        self.assertFalse(self.image.exists())

    def test_worker_failure_still_releases_temporary_image(self):
        self.select_mod_rows(0)
        self.clipboard_image = self.image
        with patch("mod_manager.ui.controllers.preview_controller.import_mod_images", side_effect=RuntimeError("failed")):
            with self.assertRaisesRegex(RuntimeError, "failed"):
                self.window._handle_paste()
        self.assertFalse(self.image.exists())

    def test_replacing_preview_invalidates_rendered_tile_image(self):
        self.select_mod_rows(0)
        self.make_image("mods/images/combat.pak.png", "blue")
        delegate = self.window.tile_delegate
        old = delegate._pixmap_for(self.mods[0], QtCore.QSize(48, 24))
        self.assertEqual(old.toImage().pixelColor(20, 10), QtGui.QColor("blue"))
        self.clipboard_paths = [self.image]
        self.window._handle_paste()
        new = delegate._pixmap_for(self.mods[0], QtCore.QSize(48, 24))
        self.assertEqual(new.toImage().pixelColor(20, 10), QtGui.QColor("red"))
