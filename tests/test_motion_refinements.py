from __future__ import annotations

from dataclasses import replace
from itertools import product
from pathlib import Path
import tempfile
from unittest.mock import patch

from PySide6 import QtCore, QtGui, QtTest, QtWidgets

from mod_manager.models import OperationItem
from mod_manager.preset_plan import PresetChange, PresetPlan, execute_preset_plan
from mod_manager.progress import Progress, reporting
from mod_manager.ui.image_cache import ImageCache
from mod_manager.ui.theme import colors, tokens
from tests.test_motion_and_loading import DeferredRunner
from tests.window_fixture import WindowTestCase, mod_item


class MotionRefinementTests(WindowTestCase):
    def setUp(self):
        super().setUp()
        self.window.resize(1200, 750)
        self.window.show()
        self.qt_app.processEvents()
        self.window.motion.finish_all()

    def advance(self, milliseconds):
        animation = self.window.activity.animation
        animation.setCurrentTime(animation.currentTime() + milliseconds)

    def progress(self, state, names=("ui.pak",), success=True):
        results = tuple(OperationItem(name, "installed", success, "Result") for name in names)
        self.window.runner.progressChanged.emit(Progress("progress_installing", mod_names=names,
                                                       mod_state=state, mod_results=results if state == "finished" else ()))

    def button(self, command=None):
        button = QtWidgets.QPushButton("Action", self.window)
        if command is not None:
            button.clicked.connect(command)
        button.setGeometry(0, 0, 240, 40)
        button.setFocusPolicy(QtCore.Qt.NoFocus)
        button.show()
        self.qt_app.processEvents()
        self.window.motion.finish_all()
        return button

    def test_hover_reversal_continues_from_current_pixels(self):
        button = self.button()
        self.qt_app.sendEvent(button, QtCore.QEvent(QtCore.QEvent.Leave))
        self.window.motion.finish_all()
        before = button.grab().toImage()
        self.qt_app.sendEvent(button, QtCore.QEvent(QtCore.QEvent.Enter))
        transition = self.window.motion._transitions[(id(button), "feedback")][0]
        self.assertEqual(transition.duration(), 220)
        transition.setCurrentTime(110)
        middle = button.grab().toImage()
        self.assertNotEqual(before, middle)
        self.qt_app.sendEvent(button, QtCore.QEvent(QtCore.QEvent.Leave))
        self.assertEqual(middle, button.grab().toImage())
        self.window.motion.finish_all()
        self.assertEqual(before, button.grab().toImage())

    def test_ripple_expands_from_mouse_and_stays_inside_button(self):
        button = self.button()
        clicked = []
        button.clicked.connect(lambda: clicked.append(True))
        geometry = button.geometry()
        point = QtCore.QPoint(12, 18)
        QtTest.QTest.mousePress(button, QtCore.Qt.LeftButton, pos=point)
        self.assertNotIn((id(button), "button-ripple"), self.window.motion._transitions)
        self.assertFalse(clicked)
        QtTest.QTest.mouseRelease(button, QtCore.Qt.LeftButton, pos=point)
        feedback = button._motion_feedback
        self.assertEqual(feedback.click_origin, QtCore.QPointF(point))
        self.assertEqual(clicked, [True])
        self.window.motion.stop(button, "feedback")
        feedback.surface = feedback.target()
        animation = self.window.motion._transitions[(id(button), "button-ripple")][0]
        self.assertEqual(animation.duration(), 600)
        animation.setCurrentTime(0)
        before = button.grab().toImage()
        animation.setCurrentTime(60)
        middle = button.grab().toImage()
        self.assertNotEqual(before.pixelColor(25, 8), middle.pixelColor(25, 8))
        self.assertEqual(before.pixelColor(220, 8), middle.pixelColor(220, 8))
        self.assertEqual(before.pixelColor(0, 0), middle.pixelColor(0, 0))
        animation.setCurrentTime(180)
        expanded = button.grab().toImage()
        self.assertNotEqual(before.pixelColor(120, 8), expanded.pixelColor(120, 8))
        self.assertEqual(before.pixelColor(220, 8), expanded.pixelColor(220, 8))
        animation.setCurrentTime(300)
        covered = button.grab().toImage()
        self.assertNotEqual(before.pixelColor(220, 8), covered.pixelColor(220, 8))
        animation.setCurrentTime(600)
        self.assertEqual(before, button.grab().toImage())
        self.assertEqual(button.geometry(), geometry)
        self.window.motion.finish_all()
        self.assertEqual(feedback.click_progress, 1.0)

    def test_cancelled_press_neither_starts_nor_repositions_ripple(self):
        button = self.button()
        clicked = []
        button.clicked.connect(lambda: clicked.append(True))
        QtTest.QTest.mousePress(button, QtCore.Qt.LeftButton, pos=QtCore.QPoint(12, 18))
        QtTest.QTest.mouseRelease(button, QtCore.Qt.LeftButton, pos=QtCore.QPoint(-5, -5))
        self.assertFalse(clicked)
        self.assertNotIn((id(button), "button-ripple"), self.window.motion._transitions)
        QtTest.QTest.mouseClick(button, QtCore.Qt.LeftButton, pos=QtCore.QPoint(12, 18))
        animation = self.window.motion._transitions[(id(button), "button-ripple")][0]
        animation.setCurrentTime(100)
        QtTest.QTest.mousePress(button, QtCore.Qt.LeftButton, pos=QtCore.QPoint(220, 18))
        self.assertEqual(button._motion_feedback.click_origin, QtCore.QPointF(12, 18))
        QtTest.QTest.mouseRelease(button, QtCore.Qt.LeftButton, pos=QtCore.QPoint(-5, -5))
        self.assertEqual(clicked, [True])
        self.assertIs(animation, self.window.motion._transitions[(id(button), "button-ripple")][0])

    def test_ripple_contrast_and_fade_adapt_to_light_dark_and_primary_buttons(self):
        button = self.button()
        self.window.cfg["gui_accent_color_mode"] = "custom"
        accents = (colors.FALLBACK_ACCENT, colors.LIGHT_BASE["panel"], colors.DARK_BASE["bg"])
        for theme, accent in product(("light", "dark"), accents):
            self.window.cfg["gui_theme"] = theme
            self.window.cfg["gui_accent_color"] = accent
            self.window._refresh_theme()
            for variant, hovered in product((None, "primary"), (False, True)):
                with self.subTest(theme=theme, accent=accent, variant=variant, hovered=hovered):
                    button.setProperty("variant", variant)
                    self.qt_app.sendEvent(button, QtCore.QEvent(QtCore.QEvent.Enter if hovered else QtCore.QEvent.Leave))
                    button._motion_feedback.refresh()
                    self.window.motion.finish_all()
                    before = button.grab().toImage().pixelColor(25, 8)
                    QtTest.QTest.mouseClick(button, QtCore.Qt.LeftButton, pos=QtCore.QPoint(12, 18))
                    self.window.motion.stop(button, "feedback")
                    button._motion_feedback.surface = button._motion_feedback.target()
                    animation = self.window.motion._transitions[(id(button), "button-ripple")][0]
                    animation.setCurrentTime(0)
                    base = button.grab().toImage().pixelColor(25, 8)
                    animation.setCurrentTime(60)
                    early = button.grab().toImage().pixelColor(25, 8)
                    animation.setCurrentTime(300)
                    middle = button.grab().toImage().pixelColor(25, 8)
                    animation.setCurrentTime(450)
                    late = button.grab().toImage().pixelColor(25, 8)
                    base_luma, early_luma, middle_luma, late_luma = (
                        255 * colors.luminance(pixel.name()) for pixel in (base, early, middle, late)
                    )
                    if base_luma > 255 * colors.READABLE_THRESHOLD:
                        self.assertLess(early_luma, base_luma)
                    else:
                        self.assertGreater(early_luma, base_luma)
                    self.assertGreater(abs(early_luma - base_luma), 60)
                    self.assertAlmostEqual(abs(middle_luma - base_luma),
                                           2 * abs(late_luma - base_luma), delta=3)
                    animation.setCurrentTime(600)
                    self.assertEqual(base, button.grab().toImage().pixelColor(25, 8))
                    self.assertEqual(before, base)

    def test_keyboard_programmatic_repeat_and_disabled_motion_ripples(self):
        button = self.button()
        button.click()
        feedback = button._motion_feedback
        self.assertEqual(feedback.click_origin, QtCore.QPointF(button.rect().center()))
        self.window.motion._transitions[(id(button), "button-ripple")][0].setCurrentTime(180)
        QtTest.QTest.mouseClick(button, QtCore.Qt.LeftButton, pos=QtCore.QPoint(220, 20))
        self.assertEqual(feedback.click_progress, 0.0)
        self.assertEqual(feedback.click_origin, QtCore.QPointF(220, 20))
        button.setFocusPolicy(QtCore.Qt.StrongFocus)
        button.setFocus()
        QtTest.QTest.keyClick(button, QtCore.Qt.Key_Space)
        self.assertEqual(feedback.click_origin, QtCore.QPointF(button.rect().center()))
        self.window.motion.set_enabled(False)
        button.click()
        self.assertEqual(feedback.click_progress, 1.0)
        self.assertFalse(self.window.motion._transitions)

    def test_action_does_not_delay_or_cut_off_ripple_when_disabling_button(self):
        snapshots = []

        def action():
            self.window._set_busy(True)
            snapshots.append(not button._motion_feedback.frozen_image.isNull())

        button = self.button(action)
        self.window.registry.add("actions", button)
        button.click()
        self.assertEqual(snapshots, [True])
        self.assertTrue(self.window.busy)
        self.assertFalse(button.isEnabled())
        self.assertTrue(button._motion_feedback.frozen_image.isNull())
        animation = self.window.motion._transitions[(id(button), "button-ripple")][0]
        animation.setCurrentTime(60)
        first = button.grab().toImage()
        animation.setCurrentTime(200)
        self.assertNotEqual(first, button.grab().toImage())
        self.window._set_busy(False)

    def test_detail_uses_same_cycle_and_refresh_does_not_restart_fade(self):
        self.select_mod_rows(1)
        self.window.motion.finish_all()
        geometry = self.window.detail_scroll.geometry()
        self.window._set_busy(True)
        self.progress("started")
        cover = self.window.activity.detail_cover
        self.assertTrue(cover.isVisible())
        self.assertTrue(all(not button.isEnabled() for button in self.window.detail_frame.findChildren(QtWidgets.QAbstractButton)))
        self.advance(tokens.OPERATION_FADE_MS // 2)
        fading = cover.grab().toImage()
        self.window._refresh_selected_detail()
        self.assertEqual(fading, cover.grab().toImage())
        self.assertNotIn((id(self.window.detail_frame), "fade"), self.window.motion._transitions)
        self.mods[1] = replace(self.mods[1], installed=True)
        self.progress("finished")
        self.window._set_busy(False)
        self.assertIs(cover.frame, self.window.mods_model.operation_frames["ui.pak"])
        self.advance(tokens.OPERATION_CYCLE_MS * 3)
        self.assertFalse(cover.isVisible())
        self.assertEqual(geometry, self.window.detail_scroll.geometry())
        self.assertFalse(self.window.mods_actions.button("install_selected").isEnabled())
        self.assertTrue(self.window.mods_actions.button("uninstall_selected").isEnabled())

    def test_multiple_details_wait_for_whole_batch_and_show_mixed_failure(self):
        self.select_mod_rows(0, 1)
        self.window.motion.finish_all()
        self.window._set_busy(True)
        self.progress("started", ("combat.pak",))
        self.progress("finished", ("combat.pak",))
        self.advance(tokens.OPERATION_CYCLE_MS * 3)
        cover = self.window.activity.detail_cover
        self.assertTrue(cover.isVisible())
        self.assertIsNone(cover.frame.finished_at)
        self.progress("started")
        self.progress("finished", success=False)
        self.window._set_busy(False)
        self.assertFalse(cover.frame.success)
        self.advance(tokens.OPERATION_RESULT_MS)
        failure = cover.grab().toImage()
        self.advance(tokens.OPERATION_HOLD_MS + tokens.OPERATION_FADE_MS * 2)
        self.assertFalse(cover.isVisible())
        self.assertNotEqual(failure, self.window.detail_scroll.viewport().grab().toImage())

    def test_all_bottom_buttons_wait_for_animation_then_scan_and_refresh_counts(self):
        self.select_mod_rows(0, 1)
        buttons = [self.window.mods_actions.button(key) for key in
                   ("install_selected", "uninstall_selected", "install_page", "uninstall_page")]
        self.assertTrue(all(button.isEnabled() for button in buttons))
        self.window._set_busy(True)
        self.progress("started")
        self.progress("finished")
        deferred = DeferredRunner()
        self.window.runner.background = deferred.background
        self.window._set_busy(False)
        self.assertTrue(self.window.library.loading)
        self.advance(tokens.OPERATION_CYCLE_MS * 3)
        self.assertFalse(self.window.activity.visual_busy)
        self.assertTrue(all(not button.isEnabled() for button in buttons))
        self.mods[1] = replace(self.mods[1], installed=True)
        deferred.complete()
        self.assertEqual([button.isEnabled() for button in buttons], [False, True, False, True])
        self.assertIn("2", buttons[1].text())
        self.assertIn("2", buttons[3].text())

    def test_fast_scan_cannot_enable_actions_or_repeat_action_during_result(self):
        self.select_mod_rows(0, 1)
        self.window._set_busy(True)
        self.progress("started")
        self.progress("finished")
        self.window._set_busy(False)
        self.assertTrue(self.window.library.ready)
        self.assertFalse(self.window.busy)
        self.assertTrue(self.window.activity.visual_busy)
        for key in ("install_selected", "uninstall_selected", "install_page", "uninstall_page"):
            self.assertFalse(self.window.mods_actions.button(key).isEnabled())
        with patch("mod_manager.ui.controllers.error_history_controller.ErrorHistoryController.run") as run:
            self.window._install_page()
            self.window._uninstall_page()
            self.window._toggle_selected_mods()
            self.window._toggle_selected_presets(["ui"])
            run.assert_not_called()
        self.advance(tokens.OPERATION_CYCLE_MS * 3)
        self.assertTrue(self.window.mods_actions.button("install_page").isEnabled())

    def test_preset_row_reuses_feedback_and_survives_refresh(self):
        self.window._navigate("presets")
        self.qt_app.processEvents()
        self.window.motion.finish_all()
        view = self.window.presets_table
        rect = view.visualRect(self.window.presets_model.index(1, 0))
        rect.setLeft(0)
        rect.setWidth(view.viewport().width())
        before = view.viewport().grab(rect).toImage()
        self.window._set_busy(True)
        self.window.runner.progressChanged.emit(Progress("toggling_presets", preset_name="ui", preset_state="started"))
        self.advance(tokens.OPERATION_FADE_MS // 2)
        self.assertNotEqual(before, view.viewport().grab(rect).toImage())
        self.window.runner.progressChanged.emit(Progress("toggling_presets", preset_name="ui", preset_state="finished",
                                                       preset_success=False))
        frame = self.window.presets_model.operation_frames["ui"]
        self.window._set_busy(False)
        self.assertIs(frame, self.window.presets_model.operation_frames["ui"])
        self.assertFalse(frame.success)
        self.assertFalse(self.window.presets_toolbar.button("toggle").isEnabled())
        self.advance(tokens.OPERATION_CYCLE_MS * 3)
        self.assertTrue(self.window.presets_toolbar.button("toggle").isEnabled())
        self.assertFalse(self.window.presets_model.operation_frames)

    def test_motion_off_and_profile_change_clear_detail_and_preset_feedback(self):
        self.select_mod_rows(1)
        self.window._set_busy(True)
        self.progress("started")
        self.window.runner.progressChanged.emit(Progress("toggling_presets", preset_name="ui", preset_state="started"))
        self.window.motion.set_enabled(False)
        self.assertEqual(self.window.activity.animation.state(), QtCore.QAbstractAnimation.Stopped)
        self.qt_app.processEvents()
        first = self.window.activity.detail_cover.grab().toImage()
        self.qt_app.processEvents()
        self.assertEqual(first, self.window.activity.detail_cover.grab().toImage())
        self.progress("finished")
        self.window.runner.progressChanged.emit(Progress("toggling_presets", preset_name="ui", preset_state="finished",
                                                       preset_success=True))
        self.window._set_busy(False)
        self.assertFalse(self.window.activity.visual_busy)
        self.assertFalse(self.window.activity.detail_cover.isVisible())
        self.window.motion.set_enabled(True)
        self.window._set_busy(True)
        self.progress("started")
        self.window.runner.progressChanged.emit(Progress("toggling_presets", preset_name="ui", preset_state="started"))
        self.window.cfg["active_game_profile_id"] = "another"
        self.window.refresh_mods()
        self.assertFalse(self.window.activity.visual_busy)
        self.window.close()
        self.assertFalse(self.window.image_prefetch._timer.isActive())

    def test_preset_progress_brackets_real_results_and_exception(self):
        with tempfile.TemporaryDirectory() as temporary, patch("mod_manager.mods.mark_mods_managed"):
            root = Path(temporary)
            source = root / "source.pak"
            source.write_bytes(b"mod")
            mod = replace(self.mods[1], src=source, dest=root / "installed.pak", copy_install=True)
            plan = PresetPlan((), (("good", (mod.name,)), ("missing", ("absent",))),
                              (PresetChange("good", mod.name, "install", mod),
                               PresetChange("missing", "absent", "missing")))
            events = []
            with reporting(events.append):
                result = execute_preset_plan(plan)
            self.assertEqual(mod.dest.read_bytes(), b"mod")
            self.assertEqual(result.errors, 1)
            preset_events = [(event.preset_name, event.preset_state, event.preset_success)
                             for event in events if event.preset_name]
            self.assertEqual(preset_events, [("good", "started", None), ("good", "finished", True),
                                             ("missing", "started", None), ("missing", "finished", False)])
            removal = PresetPlan((), (("good", (mod.name,)),),
                                 (PresetChange("good", mod.name, "uninstall", replace(mod, installed=True)),))
            with reporting(events.append):
                removed = execute_preset_plan(removal)
            self.assertEqual(removed.errors, 0)
            self.assertFalse(mod.dest.exists())
            self.assertTrue(events[-1].preset_success)
            self.assertEqual(source.read_bytes(), b"mod")
            with reporting(events.append), patch("mod_manager.preset_plan.change_mods", side_effect=OSError("Locked")):
                with self.assertRaises(OSError):
                    execute_preset_plan(plan)
            self.assertFalse(events[-1].preset_success)


class PreviewPrefetchTests(WindowTestCase):
    def setUp(self):
        super().setUp()
        self.mods[:] = [mod_item(f"mod-{index:04d}.pak") for index in range(300)]
        self.window.cfg["mod_details_visible"] = False
        self.window.cfg["tile_size"] = 160
        self.window.resize(1200, 750)
        self.window.refresh_mods()
        self.window._set_view_mode("tiles")
        self.window.show()
        self.qt_app.processEvents()

    def expected(self):
        view = self.window.tiles_view
        rows = {}
        for index, mod in enumerate(self.mods):
            rect = view.visualRect(self.window.mods_model.index(index, 0))
            rows.setdefault(rect.top(), []).append((mod.name, rect))
        ordered = sorted(rows)
        visible = [index for index, top in enumerate(ordered)
                   if any(rect.intersects(view.viewport().rect()) for _name, rect in rows[top])]
        selected = ordered[max(0, min(visible) - 3):max(visible) + 4]
        return {name for top in selected for name, _rect in rows[top]}

    def test_three_actual_rows_above_and_below_after_scroll_resize_and_zoom(self):
        view = self.window.tiles_view
        for width, tile_size, index in ((1200, 160, 0), (1200, 160, 150), (960, 220, 150), (1320, 160, 299)):
            with self.subTest(width=width, size=tile_size, index=index):
                self.window.resize(width, 750)
                self.window.cfg["tile_size"] = tile_size
                view.reset()
                self.qt_app.processEvents()
                view.scrollTo(self.window.mods_model.index(index, 0), QtWidgets.QAbstractItemView.PositionAtCenter)
                self.qt_app.processEvents()
                requested = self.window.image_prefetch.requests()
                self.assertEqual({name for name, _size in requested}, self.expected())
                for name, size in requested:
                    row = next(index for index, mod in enumerate(self.mods) if mod.name == name)
                    rect = view.visualRect(self.window.mods_model.index(row, 0))
                    self.assertEqual(size, self.window.tile_delegate.preview_size(rect))

    def test_window_beyond_pending_limit_fills_completely_and_retains_detail_priority(self):
        runner = DeferredRunner()
        cache = ImageCache(runner, lambda _cfg, _name: None)
        self.addCleanup(cache.shutdown)
        size = QtCore.QSize(20, 20)
        names = [f"tile-{index}" for index in range(tokens.IMAGE_PENDING_LIMIT + 20)]
        cache.set_tile_window(self.cfg, [(name, size) for name in names])
        cache.request(self.cfg, "selected", size, priority=True)
        order = []
        with patch("mod_manager.ui.image_cache.decode_image", side_effect=lambda cfg, key, path: (
                order.append(key.name) or QtGui.QImage(20, 20, QtGui.QImage.Format_ARGB32))):
            while runner.jobs:
                self.assertLessEqual(len(runner.jobs), tokens.IMAGE_WORKERS)
                self.assertLessEqual(len(cache._pending), tokens.IMAGE_PENDING_LIMIT)
                runner.complete()
        self.assertEqual(order[2], "selected")
        self.assertEqual(set(order), {*names, "selected"})
        for name in names:
            self.assertIsNotNone(cache.request(self.cfg, name, size, cover=True))
        self.assertFalse(runner.jobs)

    def test_rapid_scroll_retires_old_pending_images_and_hidden_view_stops_prefetch(self):
        runner = DeferredRunner()
        cache = ImageCache(runner, lambda _cfg, _name: None)
        self.addCleanup(cache.shutdown)
        size = QtCore.QSize(20, 20)
        cache.set_tile_window(self.cfg, [(f"old-{index}", size) for index in range(100)])
        cache.set_tile_window(self.cfg, [(f"new-{index}", size) for index in range(10)])
        order = []
        with patch("mod_manager.ui.image_cache.decode_image", side_effect=lambda cfg, key, path: (
                order.append(key.name) or QtGui.QImage())):
            while runner.jobs:
                runner.complete()
        self.assertEqual(set(order), {"old-0", "old-1", *(f"new-{index}" for index in range(10))})
        self.window._set_view_mode("list")
        self.qt_app.processEvents()
        self.assertFalse(self.window.image_prefetch.requests())
