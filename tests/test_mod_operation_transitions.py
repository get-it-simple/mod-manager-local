from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
from unittest.mock import patch

from PySide6 import QtCore

from mod_manager.models import OperationItem
from mod_manager.mods import apply_mods_batch_result, deactivate_mod_result
from mod_manager.progress import Progress, reporting
from mod_manager.ui.theme import tokens
from tests.test_motion_and_loading import DeferredRunner
from tests.window_fixture import WindowTestCase


class ModOperationTransitionTests(WindowTestCase):
    def setUp(self):
        super().setUp()
        self.window.resize(1200, 750)
        self.window.show()
        self.qt_app.processEvents()
        self.window.motion.finish_all()

    def advance(self, milliseconds):
        animation = self.window.activity.animation
        animation.setCurrentTime(animation.currentTime() + milliseconds)

    def paint(self, row):
        view = self.window._current_mod_view()
        rect = view.visualRect(self.window.mods_model.index(row, 0))
        if view is self.window.mods_table:
            rect.setLeft(0)
            rect.setWidth(view.viewport().width())
        return view.viewport().grab(rect).toImage()

    def progress(self, state, names=("ui.pak",), results=()):
        self.window.runner.progressChanged.emit(Progress("progress_installing", mod_names=names,
                                                       mod_state=state, mod_results=results))

    def test_fast_success_finishes_the_visual_cycle_after_work_and_refresh_complete(self):
        for mode in ("list", "tiles"):
            with self.subTest(mode=mode):
                self.window._set_view_mode(mode)
                self.qt_app.processEvents()
                self.window.motion.finish_all()
                before = [self.paint(row) for row in range(2)]
                geometry = self.window.tile_splitter.geometry()
                self.window._set_busy(True)
                self.progress("started")
                self.progress("finished", results=(OperationItem("ui.pak", "installed", True, "Applied"),))
                self.window._set_busy(False)
                self.assertFalse(self.window.busy)
                self.assertTrue(self.window.library.ready)
                self.advance(tokens.OPERATION_FADE_MS // 2)
                fading = self.paint(1)
                self.assertNotEqual(fading, before[1])
                self.assertEqual(self.paint(0), before[0])
                self.advance(tokens.OPERATION_CYCLE_MS // 2)
                spinner = self.paint(1)
                self.assertNotEqual(spinner, fading)
                self.advance(tokens.OPERATION_CYCLE_MS // 2 + tokens.OPERATION_FADE_MS + tokens.OPERATION_RESULT_MS)
                result = self.paint(1)
                self.assertNotEqual(result, spinner)
                self.assertEqual(self.paint(0), before[0])
                self.advance(tokens.OPERATION_HOLD_MS + tokens.OPERATION_FADE_MS // 2)
                returning = self.paint(1)
                self.assertNotEqual(result, returning)
                self.advance(tokens.OPERATION_FADE_MS * 2)
                self.assertEqual(self.paint(1), before[1])
                self.assertEqual(self.window.tile_splitter.geometry(), geometry)
                self.assertFalse(self.window.mods_model.operation_frames)

    def test_long_operation_keeps_running_until_real_result_and_failure_differs_from_success(self):
        self.window._set_busy(True)
        self.progress("started", ("combat.pak", "ui.pak"))
        self.advance(tokens.OPERATION_CYCLE_MS * 3)
        spinning = self.paint(1)
        self.assertEqual(self.window.mods_model.active_mods, {"combat.pak", "ui.pak"})
        self.progress("finished", ("combat.pak", "ui.pak"),
                      (OperationItem("combat.pak", "installed", False, "Locked"),
                       OperationItem("ui.pak", "installed", True, "Applied")))
        self.advance(tokens.OPERATION_RESULT_MS)
        self.assertNotEqual(self.paint(1), spinning)
        self.assertFalse(self.window.mods_model.operation_frames["combat.pak"].success)
        self.assertTrue(self.window.mods_model.operation_frames["ui.pak"].success)
        self.assertNotEqual(self.paint(0), self.paint(1))
        self.window._set_busy(False)

    def test_missing_result_never_claims_success_and_new_operation_resets_old_feedback(self):
        self.window._set_busy(True)
        self.progress("started")
        self.progress("finished")
        self.advance(tokens.OPERATION_FADE_MS + tokens.OPERATION_CYCLE_MS + tokens.OPERATION_RESULT_MS)
        failed = self.paint(1)
        self.assertFalse(self.window.mods_model.operation_frames["ui.pak"].success)
        self.window._set_busy(False)
        self.window._set_busy(True)
        self.progress("started")
        self.assertNotEqual(self.paint(1), failed)
        self.assertIsNone(self.window.mods_model.operation_frames["ui.pak"].finished_at)
        self.window._set_busy(False)

    def test_filtered_mods_profile_change_and_close_discard_visual_state(self):
        self.window._set_busy(True)
        self.progress("started")
        self.window.mods_model.set_data([self.mods[0]], {}, {})
        self.assertFalse(self.window.mods_model.operation_frames)
        self.window._set_busy(False)
        self.window._set_busy(True)
        self.progress("started")
        self.window.cfg["active_game_profile_id"] = "another-profile"
        self.window.refresh_mods()
        self.assertFalse(self.window.mods_model.operation_frames)
        self.window.close()
        self.assertEqual(self.window.activity.animation.state(), QtCore.QAbstractAnimation.Stopped)

    def test_disabling_motion_settles_finished_feedback_and_keeps_static_active_indicator(self):
        self.window._set_busy(True)
        self.progress("started")
        self.advance(tokens.OPERATION_CYCLE_MS // 2)
        self.window.motion.set_enabled(False)
        self.assertEqual(self.window.activity.animation.state(), QtCore.QAbstractAnimation.Stopped)
        first = self.paint(1)
        self.qt_app.processEvents()
        self.assertEqual(first, self.paint(1))
        self.progress("finished", results=(OperationItem("ui.pak", "installed", True, "Applied"),))
        self.assertFalse(self.window.mods_model.operation_frames)
        self.window._set_busy(False)

    def test_action_buttons_keep_their_pixels_through_busy_and_followup_scan(self):
        buttons = [self.window.mods_toolbar.button("import_files"), self.window.workspace.navigation["presets"]]
        for button in buttons:
            self.qt_app.sendEvent(button, QtCore.QEvent(QtCore.QEvent.Leave))
        self.window.motion.finish_all()
        before = [button.grab().toImage() for button in buttons]
        self.window._set_busy(True)
        self.assertFalse(buttons[0].isEnabled())
        self.assertEqual(before, [button.grab().toImage() for button in buttons])
        deferred = DeferredRunner()
        self.window.runner.background = deferred.background
        self.window._set_busy(False)
        self.assertTrue(self.window.library.loading)
        self.assertFalse(buttons[0].isEnabled())
        self.assertEqual(before, [button.grab().toImage() for button in buttons])
        deferred.complete()
        self.window.motion.finish_all()
        self.assertTrue(buttons[0].isEnabled())
        self.assertEqual(before, [button.grab().toImage() for button in buttons])

    def test_progress_reports_real_per_mod_outcomes_for_mixed_copy_install_and_removal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            good = root / "good.pak"
            good.write_bytes(b"payload")
            mods = [replace(self.mods[0], src=good, dest=root / "installed.pak", installed=False, copy_install=True),
                    replace(self.mods[1], src=root / "absent.pak", dest=root / "failed.pak", copy_install=True)]
            events = []
            with reporting(events.append):
                result = apply_mods_batch_result(mods)
            self.assertEqual([item.success for item in result.items], [True, False])
            self.assertEqual(events[-1].mod_results, result.items)
            self.assertEqual(mods[0].dest.read_bytes(), b"payload")
            with reporting(events.append):
                removed = deactivate_mod_result(mods[0])
            self.assertTrue(removed.success)
            self.assertEqual(events[-1].mod_results, (removed,))
            self.assertFalse(mods[0].dest.exists())
            self.assertEqual(good.read_bytes(), b"payload")
            with reporting(events.append), patch("mod_manager.mods.remove_path", side_effect=OSError("Locked")):
                mods[0].dest.write_bytes(b"payload")
                with self.assertRaises(OSError):
                    deactivate_mod_result(mods[0])
            self.assertEqual(events[-1].mod_results, ())
