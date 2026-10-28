from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
from unittest.mock import patch

from PySide6 import QtCore, QtGui, QtWidgets

from mod_manager.models import OperationResult
from mod_manager.mods import apply_mods_batch_result, deactivate_mod_result
from mod_manager.progress import Progress, reporting
from mod_manager.ui.models.mod_model import BUSY_ROLE
from mod_manager.ui.task_runner import TaskRunner
from mod_manager.ui.theme import tokens
from mod_manager.ui.widgets.buttons import text_button
from tests.test_motion_and_loading import DeferredRunner, advance_motion
from tests.window_fixture import WindowTestCase

BACKGROUND_ACTION = TaskRunner.background


class ControlledPool:
    def __init__(self):
        self.jobs = {}
        self.results = []
        self.counter = 0

    def submit(self, file_key, worker, callback):
        self.counter += 1
        self.jobs[self.counter] = (worker, callback)
        return self.counter

    def complete(self, task_id):
        worker, _callback = self.jobs[task_id]
        try:
            result, error = worker(), None
        except Exception as failure:
            result, error = None, failure
        self.results.append((task_id, result, error))

    def poll(self):
        results, self.results = self.results, []
        return results

    def fire_callbacks(self, results):
        for task_id, result, error in results:
            _worker, callback = self.jobs.pop(task_id)
            callback(result, error)

    def has_work(self):
        return bool(self.jobs)

    def shutdown(self):
        self.jobs.clear()


class OperationActivityGuiTests(WindowTestCase):
    def show_window(self):
        self.window.resize(tokens.DEFAULT_WIDTH, tokens.DEFAULT_HEIGHT)
        self.window.show()
        self.qt_app.processEvents()
        advance_motion(self.window)

    def geometry(self):
        return tuple(widget.geometry() for widget in (
            self.window.workspace, self.window.workspace.sidebar, self.window.mods_toolbar,
            self.window.filter_summary, self.window.tile_splitter, self.window.mods_actions,
            self.window.statusBar()))

    def use_controlled_pool(self):
        pool = ControlledPool()
        self.window.runner._pool = pool
        return pool

    def paint_mod(self, row, mode):
        model = self.window.mods_model
        index = model.index(row, 0 if mode == "tiles" else 1)
        option = QtWidgets.QStyleOptionViewItem()
        view = self.window.tiles_view if mode == "tiles" else self.window.mods_table
        option.initFrom(view)
        option.widget = view
        option.state &= ~(QtWidgets.QStyle.State_MouseOver | QtWidgets.QStyle.State_Selected)
        delegate = self.window.tile_delegate if mode == "tiles" else view.itemDelegateForColumn(0)
        if delegate is None:
            delegate = view.itemDelegate()
        size = delegate.sizeHint(option, index) if mode == "tiles" else QtCore.QSize(tokens.ICON_BUTTON_SIZE * 2, tokens.NAVIGATION_HEIGHT)
        option.rect = QtCore.QRect(QtCore.QPoint(), size)
        image = QtGui.QImage(size, QtGui.QImage.Format_ARGB32)
        image.fill(QtGui.QColor(self.window.theme.palette.panel))
        painter = QtGui.QPainter(image)
        delegate.paint(painter, option, index)
        painter.end()
        return image

    def test_busy_refresh_error_and_summary_do_not_shift_the_page(self):
        self.show_window()
        original = self.geometry()
        deferred = DeferredRunner()
        self.window.runner.background = deferred.background
        self.window.refresh_mods()
        self.qt_app.processEvents()
        self.assertEqual(self.geometry(), original)
        self.assertTrue(self.window.library_status.isHidden())
        self.assertTrue(self.window.activity.indicator.isVisible())
        deferred.complete(error=OSError("Synthetic refresh failure"))
        self.qt_app.processEvents()
        self.assertEqual(self.geometry(), original)
        self.assertTrue(self.window.library_status.retry.isVisible())
        self.assertTrue(self.window.activity.indicator.isHidden())
        self.window.library_status.retry.click()
        deferred.complete()
        self.qt_app.processEvents()
        self.assertEqual(self.geometry(), original)
        self.window._set_busy(True)
        self.qt_app.processEvents()
        self.assertEqual(self.geometry(), original)
        self.assertTrue(self.window.mods_table.isEnabled())
        self.assertTrue(self.window.tiles_view.isEnabled())
        self.window._set_busy(False)
        deferred.complete()
        self.window.errors.record_import(["ui.pak"], [], self.window.cfg)
        self.window._set_status("Imported 1")
        self.qt_app.processEvents()
        self.assertEqual(self.geometry(), original)
        self.assertIs(self.window.centralWidget(), self.window.workspace)
        self.assertEqual(self.window.statusBar().currentMessage(), "Imported 1")
        self.assertTrue(self.window.activity.indicator.isHidden())

    def test_only_processing_mods_change_pixels_in_list_and_tiles(self):
        self.show_window()
        for mode in ("list", "tiles"):
            with self.subTest(mode=mode):
                before = [self.paint_mod(row, mode) for row in range(2)]
                self.window._set_busy(True)
                self.window.runner.progressChanged.emit(Progress("progress_installing", mod_names=("ui.pak",), mod_state="started"))
                self.assertFalse(self.window.mods_model.index(0, 0).data(BUSY_ROLE))
                self.assertTrue(self.window.mods_model.index(1, 0).data(BUSY_ROLE))
                self.window.activity.animation.setCurrentTime(self.window.activity.animation.currentTime() + tokens.OPERATION_FADE_MS // 2)
                during = [self.paint_mod(row, mode) for row in range(2)]
                self.assertEqual(before[0], during[0])
                self.assertNotEqual(before[1], during[1])
                self.window.activity.animation.setCurrentTime(self.window.activity.animation.currentTime() + tokens.ACTIVITY_DURATION_MS // 3)
                self.assertNotEqual(during[1], self.paint_mod(1, mode))
                self.window.runner.progressChanged.emit(Progress("progress_installing", mod_names=("ui.pak",), mod_state="finished"))
                self.window.activity.animation.setCurrentTime(self.window.activity.animation.currentTime() + tokens.OPERATION_CYCLE_MS * 3)
                self.assertEqual(before, [self.paint_mod(row, mode) for row in range(2)])
                self.window._set_busy(False)

    def test_line_moves_right_stays_bounded_and_respects_motion_setting(self):
        self.show_window()
        self.window._set_busy(True)
        activity = self.window.activity
        indicator = activity.indicator
        self.assertLess(indicator.width(), self.window.width())
        self.assertLessEqual(indicator.width(), tokens.ACTIVITY_WIDTH)
        activity.animation.setCurrentTime(tokens.ACTIVITY_DURATION_MS // 4)
        first = indicator.grab().toImage()
        activity.animation.setCurrentTime(tokens.ACTIVITY_DURATION_MS // 2)
        second = indicator.grab().toImage()
        self.assertNotEqual(first, second)
        self.assertGreater(indicator.phase, 0.25)
        self.window.motion.set_enabled(False)
        self.assertTrue(indicator.isVisible())
        self.assertEqual(activity.animation.state(), QtCore.QAbstractAnimation.Stopped)
        self.assertEqual(indicator.phase, 0.5)
        self.window._set_busy(False)
        self.assertTrue(indicator.isHidden())
        self.window._set_busy(True)
        self.window.close()
        self.assertTrue(indicator.isHidden())
        self.assertEqual(activity.animation.state(), QtCore.QAbstractAnimation.Stopped)

    def test_background_work_keeps_line_visible_until_last_callback(self):
        self.show_window()
        pool = self.use_controlled_pool()
        self.window.runner.background = BACKGROUND_ACTION.__get__(self.window.runner)
        self.window.runner.background(lambda: None, lambda _result, _error: None, file_key="first")
        self.window.runner.background(lambda: None, lambda _result, _error: None, file_key="second")
        self.assertTrue(self.window.activity.indicator.isVisible())
        pool.complete(1)
        self.window.runner.poll()
        self.assertTrue(self.window.activity.indicator.isVisible())
        pool.complete(2)
        self.window.runner.poll()
        self.assertTrue(self.window.activity.indicator.isHidden())

    def test_action_refreshes_once_after_done_and_also_after_failure(self):
        pool = self.use_controlled_pool()
        with patch("mod_manager.ui.controllers.library_controller.load_library_snapshot", side_effect=lambda _cfg: self.window.library.snapshot) as scan:
            def done(_result):
                self.assertEqual(scan.call_count, 0)
                self.window.refresh_mods()

            self.window._run_action("Synthetic operation", lambda: OperationResult(), done)
            pool.complete(1)
            self.window.runner.poll()
            self.assertEqual(scan.call_count, 1)
            self.assertTrue(self.window.library.ready)
            self.assertFalse(self.window.runner.active)
            def fail():
                raise OSError("Backend unavailable")

            with patch("mod_manager.ui.app.show_error") as error:
                self.window._run_action("Synthetic failure", fail)
                self.window.runner._progress.put((self.window.runner._generation - 1,
                                                 Progress("progress_installing", mod_names=("ui.pak",), mod_state="started")))
                pool.complete(2)
                self.window.runner.poll()
            error.assert_called_once()
            self.assertEqual(scan.call_count, 2)
            self.assertEqual(self.window.mods_model.active_mods, set())
            self.assertFalse(self.window.library.loading)

    def test_artwork_survives_state_refresh_but_replacement_and_f5_reload_it(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "art.png"

        def save_art(color):
            image = QtGui.QImage(32, 32, QtGui.QImage.Format_RGB32)
            image.fill(QtGui.QColor(color))
            self.assertTrue(image.save(str(path)))

        save_art("red")
        self.window.images.path_for = lambda _cfg, _name: path
        size = QtCore.QSize(24, 24)
        original = self.window.images.request(self.window.cfg, "ui.pak", size, cover=True)
        self.assertEqual(original.toImage().pixelColor(0, 0), QtGui.QColor("red"))
        save_art("blue")
        self.window.refresh_mods()
        cached = self.window.images.request(self.window.cfg, "ui.pak", size, cover=True)
        self.assertEqual(cached.cacheKey(), original.cacheKey())
        self.assertEqual(cached.toImage().pixelColor(0, 0), QtGui.QColor("red"))
        self.window._invalidate_mod_image("ui.pak")
        updated = self.window.images.request(self.window.cfg, "ui.pak", size, cover=True)
        self.assertEqual(updated.toImage().pixelColor(0, 0), QtGui.QColor("blue"))
        save_art("green")
        self.window.keyboard.refresh_page()
        updated = self.window.images.request(self.window.cfg, "ui.pak", size, cover=True)
        self.assertEqual(updated.toImage().pixelColor(0, 0), QtGui.QColor("green"))

    def test_reselecting_active_profile_keeps_models_selection_filters_and_scroll(self):
        self.show_window()
        self.select_mod_rows(1)
        self.window.filters.add("search", "synthetic")
        selection = self.window.mods_table.selectionModel()
        current = QtCore.QPersistentModelIndex(selection.currentIndex())
        snapshot = self.window.library.snapshot
        self.window._navigate("games")
        with patch("mod_manager.ui.controllers.games_controller.save_config") as save, patch(
            "mod_manager.ui.controllers.library_controller.load_library_snapshot") as load, patch.object(
            self.window.mods_model, "beginResetModel") as reset, patch.object(self.window.images, "reset") as images:
            self.window.games.select(self.window.cfg["active_game_profile_id"])
        save.assert_not_called()
        load.assert_not_called()
        reset.assert_not_called()
        images.assert_not_called()
        self.assertEqual(self.window.workspace.current_page, "library")
        self.assertIs(self.window.library.snapshot, snapshot)
        self.assertEqual(self.window._selected_mod_names(), ["ui.pak"])
        self.assertEqual(self.window.filters.queries, ("synthetic",))
        self.assertTrue(current.isValid())

    def test_transparent_list_areas_match_their_surroundings_in_both_themes(self):
        self.show_window()
        for theme in ("light", "dark"):
            self.window.cfg["gui_theme"] = theme
            self.window._refresh_theme()
            self.qt_app.processEvents()
            image = self.window.grab().toImage()
            for view in (self.window.filter_summary.view, self.window.workspace.labels_list):
                point = view.viewport().mapTo(self.window, QtCore.QPoint(view.viewport().width() - 2,
                                                                      view.viewport().height() - 2))
                parent = view.parentWidget()
                expected = QtGui.QColor(self.window.theme.palette.alt_panel if parent is self.window.workspace.sidebar else self.window.theme.palette.bg)
                self.assertEqual(image.pixelColor(point), expected)

    def test_animated_button_labels_keep_the_native_style_padding(self):
        font_path = Path("C:/Windows/Fonts/segoeui.ttf")
        font_id = QtGui.QFontDatabase.addApplicationFont(str(font_path)) if font_path.is_file() else -1
        families = (QtGui.QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else
                    [QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.GeneralFont).family()])
        if font_id >= 0:
            self.addCleanup(QtGui.QFontDatabase.removeApplicationFont, font_id)
        self.window.cfg.update(gui_font_family=families[0], gui_font_size=10)
        self.window._refresh_theme()
        self.show_window()
        buttons = list(self.window.workspace.navigation.values())
        buttons.append(text_button("Synthetic padded action", "", parent=self.window.mods_tab))
        buttons[-1].resize(buttons[-1].sizeHint())
        buttons[-1].show()
        self.qt_app.processEvents()
        for button in buttons:
            button.setFont(QtGui.QFont(families[0], 10))
            feedback = button._motion_feedback
            self.qt_app.sendEvent(button, QtCore.QEvent(QtCore.QEvent.Leave))
            advance_motion(self.window)
            animated = button.grab().toImage()
            button.removeEventFilter(feedback)
            native = button.grab().toImage()
            button.installEventFilter(feedback)
            foreground = QtGui.QColor(*feedback.surface[2])

            def text_bounds(image):
                points = [QtCore.QPoint(x, y) for y in range(tokens.SPACE_LG, image.height() - tokens.SPACE_LG)
                          for x in range(tokens.SPACE_LG, image.width() - tokens.SPACE_LG)
                          if sum(abs(a - b) for a, b in zip(image.pixelColor(x, y).getRgb()[:3],
                                                         foreground.getRgb()[:3])) < 90]
                self.assertTrue(points, (button.text(), button.size(), foreground.name()))
                return min(point.x() for point in points), max(point.x() for point in points)

            self.assertEqual(text_bounds(animated), text_bounds(native), button.text())

    def test_action_waits_for_stale_scan_and_then_loads_one_fresh_snapshot(self):
        pool = self.use_controlled_pool()
        deferred = DeferredRunner()
        self.window.runner.background = deferred.background
        self.window.refresh_mods()
        self.window._run_action("Synthetic operation", lambda: None)
        pool.complete(1)
        self.window.runner.poll()
        self.assertEqual(len(deferred.jobs), 1)
        self.assertTrue(self.window.library.loading)
        deferred.complete()
        self.assertTrue(self.window.library.loading)
        self.assertEqual(len(deferred.jobs), 1)
        deferred.complete()
        self.assertTrue(self.window.library.ready)
        self.assertEqual(deferred.jobs, [])
        self.assertTrue(self.window.activity.indicator.isHidden())

    def test_domain_progress_brackets_real_copy_install_and_failed_removal(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        source = Path(temporary.name) / "source.pak"
        destination = Path(temporary.name) / "game.pak"
        source.write_text("payload", encoding="utf-8")
        mod = replace(self.mods[1], src=source, dest=destination, copy_install=True)
        events = []
        with reporting(events.append):
            result = apply_mods_batch_result([mod])
        self.assertTrue(result.items[0].success)
        self.assertEqual(destination.read_text(encoding="utf-8"), "payload")
        self.assertEqual([(event.mod_names, event.mod_state) for event in events],
                         [((mod.name,), "started"), ((mod.name,), "finished")])
        with reporting(events.append), patch("mod_manager.mods.remove_path", side_effect=OSError("Locked")):
            with self.assertRaises(OSError):
                deactivate_mod_result(mod)
        self.assertEqual(events[-1].mod_state, "finished")
        self.assertEqual(source.read_text(encoding="utf-8"), "payload")
