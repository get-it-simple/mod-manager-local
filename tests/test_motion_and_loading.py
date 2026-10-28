from __future__ import annotations

from dataclasses import replace
import gc
from pathlib import Path
import tempfile
from unittest.mock import patch
import unittest

from PySide6 import QtCore, QtGui, QtTest, QtWidgets

from mod_manager.ui.app import ModManagerGui
from mod_manager.ui.image_cache import ImageCache
from mod_manager.ui.motion import ButtonFeedback
from mod_manager.ui.theme import tokens
from tests.qt_support import dispose, qt_app
from tests.window_fixture import WindowTestCase


class DeferredRunner:
    def __init__(self):
        self.jobs = []

    def background(self, worker, callback, file_key="global"):
        self.jobs.append((worker, callback))

    def complete(self, index=0, error=None):
        worker, callback = self.jobs.pop(index)
        callback(worker() if error is None else None, error)


def advance_motion(window, fraction=1.0):
    for animation in window.motion.findChildren(QtCore.QVariantAnimation):
        if animation.state() == QtCore.QAbstractAnimation.Running:
            animation.setCurrentTime(round(animation.duration() * fraction))


class StartupAndMotionTests(WindowTestCase):
    def test_favorite_change_has_intermediate_pixels_after_data_is_saved(self):
        self.window.show()
        self.window._set_view_mode("tiles")
        self.qt_app.processEvents()
        advance_motion(self.window)
        with patch("mod_manager.ui.app.add_favorites_to_mods", return_value="Saved"), patch(
            "mod_manager.ui.app.load_favorites", return_value={"combat.pak"}
        ):
            self.window._toggle_favorite_name("combat.pak")
        self.assertIn("combat.pak", self.window.current_mod_favorites)
        advance_motion(self.window, 0.35)
        middle = self.window.tiles_view.viewport().grab().toImage()
        advance_motion(self.window)
        after = self.window.tiles_view.viewport().grab().toImage()
        self.assertNotEqual(middle, after)

    def test_hidden_dialog_keeps_its_button_feedback_across_collection(self):
        dialog = QtWidgets.QDialog(self.window)
        layout = QtWidgets.QVBoxLayout(dialog)
        box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close, dialog)
        layout.addWidget(box)
        dialog.show()
        self.qt_app.processEvents()
        dialog.close()
        gc.collect()
        dialog.show()
        self.qt_app.processEvents()
        button = box.button(QtWidgets.QDialogButtonBox.Close)
        self.assertIs(button._motion_feedback.motion, self.window.motion)
        self.assertEqual(len(button.findChildren(ButtonFeedback)), 1)
        dialog.close()
        dispose(dialog)

    def test_buttons_created_during_palette_changes_have_one_feedback_owner(self):
        buttons = []
        for _ in range(20):
            button = QtWidgets.QPushButton("Synthetic action", self.window)
            buttons.append(button)
            button.ensurePolished()
            self.window.theme.apply()
        self.qt_app.processEvents()
        for button in buttons:
            self.assertEqual(len(button.findChildren(ButtonFeedback)), 1)

    def test_construction_never_shows_a_top_level_child(self):
        shown = []

        class Watcher(QtCore.QObject):
            def eventFilter(self, obj, event):
                if event.type() == QtCore.QEvent.Show and isinstance(obj, QtWidgets.QWidget) and obj.isWindow():
                    shown.append(type(obj).__name__)
                return False

        watcher = Watcher()
        self.qt_app.installEventFilter(watcher)
        other = None
        try:
            for cfg in (self.cfg, {**self.cfg, "active_game_profile_id": "", "game_profiles": [],
                                   "mods_source_dir": "", "game_mods_dir": ""}):
                with patch("mod_manager.ui.app.load_config", return_value=cfg):
                    other = ModManagerGui()
                self.assertFalse(other.isVisible())
                self.assertEqual(shown, [])
                dispose(other)
                other = None
        finally:
            self.qt_app.removeEventFilter(watcher)
            if other is not None:
                dispose(other)

    def test_hover_has_intermediate_pixels_and_click_runs_immediately(self):
        self.window.show()
        self.qt_app.processEvents()
        button = self.window.workspace.navigation["presets"]
        self.qt_app.sendEvent(button, QtCore.QEvent(QtCore.QEvent.Leave))
        advance_motion(self.window)
        before = button.grab().toImage()
        self.qt_app.sendEvent(button, QtCore.QEvent(QtCore.QEvent.Enter))
        advance_motion(self.window, 0.35)
        middle = button.grab().toImage()
        advance_motion(self.window)
        after = button.grab().toImage()
        self.assertNotEqual(before, middle)
        self.assertNotEqual(middle, after)
        button.click()
        self.assertEqual(self.window.workspace.current_page, "presets")
        advance_motion(self.window)
        self.assertEqual(self.window.motion._transitions, {})

    def test_disabled_motion_settles_transition_and_keyboard_still_works(self):
        self.window.show()
        self.qt_app.processEvents()
        button = self.window.workspace.navigation["settings"]
        self.qt_app.sendEvent(button, QtCore.QEvent(QtCore.QEvent.Enter))
        self.window.motion.set_enabled(False)
        self.assertEqual(self.window.motion._transitions, {})
        button.setFocus()
        QtTest.QTest.keyClick(button, QtCore.Qt.Key_Space)
        self.assertEqual(self.window.workspace.current_page, "settings")
        self.assertEqual(self.window.motion._transitions, {})

    def test_animation_setting_is_a_draft_until_saved_and_reset_restores_it(self):
        field = self.window.setting_widgets["gui_animations_enabled"]
        field.setChecked(False)
        self.assertTrue(self.window.motion.enabled)
        self.window.settings.reset()
        self.assertTrue(field.isChecked())
        self.use_inline_runner()
        field.setChecked(False)
        self.window.settings.save()
        self.assertFalse(self.window.motion.enabled)
        self.assertFalse(self.window.cfg["gui_animations_enabled"])

    def test_repeated_expansion_and_close_leave_no_active_effects(self):
        self.window.show()
        self.window._navigate("settings")
        self.qt_app.processEvents()
        shortcuts = self.window.setting_widgets["keyboard_shortcuts"]
        shortcuts.toggle.setChecked(True)
        advance_motion(self.window, 0.4)
        shortcuts.toggle.setChecked(False)
        advance_motion(self.window)
        self.assertTrue(shortcuts.content.isHidden())
        self.assertEqual(shortcuts.content.maximumHeight(), tokens.MAX_WIDGET_HEIGHT)
        self.window.close()
        self.assertEqual(self.window.motion._transitions, {})


class LibraryLoadingTests(WindowTestCase):
    def setUp(self):
        super().setUp()
        self.deferred = DeferredRunner()
        self.window.runner.background = self.deferred.background

    def test_refresh_coalesces_and_discards_the_first_result(self):
        library = self.window.library
        first = library.snapshot
        with patch("mod_manager.ui.controllers.library_controller.load_library_snapshot", return_value=first):
            self.window.refresh_mods()
            self.window.refresh_mods()
            self.window.refresh_mods()
            self.assertEqual(len(self.deferred.jobs), 1)
            self.assertTrue(library.loading)
            self.assertFalse(self.window.mods_actions.button("install_page").isEnabled())
            self.assertFalse(self.window.mods_toolbar.button("import_files").isEnabled())
            with patch("mod_manager.ui.dialogs.prompts.choose_files") as chooser, patch.object(
                QtWidgets.QApplication, "activeWindow", return_value=self.window
            ):
                self.window.keyboard.activate("import_files")
            chooser.assert_not_called()
            self.deferred.complete()
            self.assertTrue(library.loading)
            self.assertEqual(len(self.deferred.jobs), 1)
            self.deferred.complete()
        self.assertTrue(library.ready)
        self.assertTrue(self.window.mods_actions.button("install_page").isEnabled())

    def test_profile_switch_clears_old_data_and_ignores_old_completion(self):
        library = self.window.library
        first = library.snapshot
        with patch("mod_manager.ui.controllers.library_controller.load_library_snapshot", return_value=first):
            self.window.refresh_mods()
            self.window.cfg["active_game_profile_id"] = "another-profile"
            self.window.refresh_mods()
            self.assertIsNone(library.snapshot)
            self.assertEqual(self.window.mods_model.rowCount(), 0)
            self.deferred.complete()
            self.assertIsNone(library.snapshot)
        second = replace(first, profile_id="another-profile")
        with patch("mod_manager.ui.controllers.library_controller.load_library_snapshot", return_value=second):
            self.deferred.complete()
        self.assertIs(library.snapshot, second)

    def test_error_preserves_data_and_exposes_retry(self):
        previous = self.window.library.snapshot
        self.window.refresh_mods()
        self.deferred.complete(error=PermissionError("synthetic scan failure"))
        self.assertIs(self.window.library.snapshot, previous)
        self.assertIn("synthetic scan failure", self.window.library_status.message.text())
        self.assertFalse(self.window.library_status.retry.isHidden())
        self.assertFalse(self.window.library.ready)
        self.window.library_status.retry.click()
        self.assertTrue(self.window.library.loading)
        self.assertEqual(len(self.deferred.jobs), 1)

    def test_filters_sorting_and_pagination_do_not_submit_disk_work(self):
        self.window.search_box.setCurrentText("combat")
        self.window.search_box.lineEdit().returnPressed.emit()
        self.window._change_filter_mode("installed")
        self.window._sort_mods("name")
        self.window._change_mod_page(1)
        self.window._mods_clear()
        self.assertEqual(self.deferred.jobs, [])

    def test_late_completion_after_shutdown_is_ignored(self):
        self.window.refresh_mods()
        self.window.library.shutdown()
        with patch.object(self.window, "_apply_library_snapshot") as apply:
            self.deferred.complete(error=RuntimeError("late failure"))
        apply.assert_not_called()


class ImageCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "art.png"
        image = QtGui.QImage(80, 160, QtGui.QImage.Format_ARGB32)
        image.fill(QtGui.QColor(20, 40, 60, 128))
        self.assertTrue(image.save(str(self.path)))
        self.runner = DeferredRunner()
        self.cache = ImageCache(self.runner, lambda _cfg, _name: self.path)
        self.addCleanup(self.cache.shutdown)
        self.cfg = {"active_game_profile_id": "first", "mods_source_dir": self.temporary.name}

    def test_decode_is_deferred_preserves_alpha_and_reuses_cached_pixels(self):
        size = QtCore.QSize(40, 40)
        self.assertIsNone(self.cache.request(self.cfg, "portrait", size))
        self.runner.complete()
        pixmap = self.cache.request(self.cfg, "portrait", size)
        self.assertEqual(pixmap.size(), QtCore.QSize(20, 40))
        self.assertAlmostEqual(pixmap.toImage().pixelColor(0, 0).alpha(), 128, delta=1)
        self.assertEqual(self.runner.jobs, [])

    def test_stale_decode_cannot_replace_an_invalidated_preview(self):
        size = QtCore.QSize(40, 40)
        ready = []
        self.cache.ready.connect(ready.append)
        self.cache.request(self.cfg, "portrait", size)
        self.cache.invalidate("portrait")
        self.runner.complete()
        self.assertEqual(ready, [])
        self.assertEqual(self.cache.byte_count, 0)
        self.assertIsNone(self.cache.request(self.cfg, "portrait", size))
        self.runner.complete()
        self.assertFalse(self.cache.request(self.cfg, "portrait", size).isNull())

    def test_profile_reset_and_shutdown_discard_pending_images(self):
        self.cache.request(self.cfg, "portrait", QtCore.QSize(40, 40))
        self.cache.reset()
        self.runner.complete()
        self.assertEqual(self.cache.byte_count, 0)
        self.cache.request(self.cfg, "portrait", QtCore.QSize(40, 40))
        self.cache.shutdown()
        self.runner.complete()
        self.assertEqual(self.cache.byte_count, 0)

    def test_cover_keeps_tile_size_and_cache_budget_is_enforced(self):
        with patch.object(tokens, "IMAGE_CACHE_BYTES", 5000):
            for name in ("first", "second"):
                self.cache.request(self.cfg, name, QtCore.QSize(32, 32), cover=True)
                self.runner.complete()
            pixmap = self.cache.request(self.cfg, "second", QtCore.QSize(32, 32), cover=True)
            self.assertEqual(pixmap.size(), QtCore.QSize(32, 32))
            self.assertLessEqual(self.cache.byte_count, 5000)
            self.assertIsNone(self.cache.request(self.cfg, "first", QtCore.QSize(32, 32), cover=True))

    def test_decoders_and_pending_queue_are_bounded(self):
        for index in range(tokens.IMAGE_PENDING_LIMIT * 2):
            self.cache.request(self.cfg, str(index), QtCore.QSize(32, 32))
        self.assertEqual(len(self.runner.jobs), tokens.IMAGE_WORKERS)
        self.assertLessEqual(len(self.cache._pending), tokens.IMAGE_PENDING_LIMIT)
        self.assertIn(str(tokens.IMAGE_PENDING_LIMIT * 2 - 1), {key.name for key in self.cache._pending})

    def test_selected_preview_survives_a_full_queue_of_scrolled_tiles(self):
        size = QtCore.QSize(32, 32)
        self.cache.request(self.cfg, "running-one", size)
        self.cache.request(self.cfg, "running-two", size)
        self.cache.request(self.cfg, "selected", size, priority=True)
        for index in range(tokens.IMAGE_PENDING_LIMIT * 2):
            self.cache.request(self.cfg, str(index), size, cover=True)
        self.assertEqual(next(iter(self.cache._pending)).name, "selected")
        self.assertIn(str(tokens.IMAGE_PENDING_LIMIT * 2 - 1), {key.name for key in self.cache._pending})
        self.runner.complete()
        self.runner.complete()
        self.runner.complete()
        self.assertFalse(self.cache.request(self.cfg, "selected", size, priority=True).isNull())
