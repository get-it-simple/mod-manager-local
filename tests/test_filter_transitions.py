from __future__ import annotations

from unittest.mock import patch

from PySide6 import QtCore, QtTest, QtWidgets

from tests.test_motion_and_loading import advance_motion
from tests.window_fixture import WindowTestCase


class FilterTransitionTests(WindowTestCase):
    def setUp(self):
        super().setUp()
        self.window.resize(1200, 750)
        self.window.show()
        self.window.activateWindow()
        self.qt_app.processEvents()
        self.window.motion.finish_all()

    def test_buttons_open_one_shared_editor_with_intermediate_frames_and_stable_geometry(self):
        control = self.window.filter_input
        self.assertTrue(control.search_button.isVisible())
        self.assertTrue(control.label_button.isVisible())
        self.assertFalse(self.window.search_box.isVisible())
        self.assertFalse(self.window.label_filter_box.isVisible())
        geometry = (control.geometry(), self.window.mods_toolbar.geometry(), self.window.tile_splitter.geometry())
        before = control.grab().toImage()
        control.search_button.click()
        advance_motion(self.window, 0.4)
        circle = control.grab().toImage()
        advance_motion(self.window, 0.7)
        expanded = control.grab().toImage()
        advance_motion(self.window)
        self.assertNotEqual(before, circle)
        self.assertNotEqual(circle, expanded)
        self.assertNotEqual(expanded, control.grab().toImage())
        self.assertTrue(self.window.search_box.isVisible())
        self.assertFalse(self.window.label_filter_box.isVisible())
        self.assertFalse(control.search_button.isVisible())
        self.assertTrue(self.window.search_box.hasFocus() or self.window.search_box.lineEdit().hasFocus())
        self.assertEqual(geometry, (control.geometry(), self.window.mods_toolbar.geometry(), self.window.tile_splitter.geometry()))

    def test_close_and_escape_keep_applied_chips_and_separate_drafts(self):
        self.window.motion.set_enabled(False)
        control = self.window.filter_input
        control.search_button.click()
        self.window.search_box.setCurrentText("combat")
        QtTest.QTest.keyClick(self.window.search_box.lineEdit(), QtCore.Qt.Key_Return)
        self.assertEqual(self.window.filters.queries, ("combat",))
        self.window.search_box.setCurrentText("unfinished search")
        control.close_button.click()
        self.assertTrue(control.search_button.isVisible())
        self.assertEqual(self.window.filters.queries, ("combat",))
        control.label_button.click()
        self.window.label_filter_box.setCurrentText("combat")
        QtTest.QTest.keyClick(self.window.label_filter_box.lineEdit(), QtCore.Qt.Key_Return)
        self.assertEqual(self.window.filters.labels, ("combat",))
        self.window.label_filter_box.setCurrentText("label draft")
        QtTest.QTest.keyClick(self.window.label_filter_box.lineEdit(), QtCore.Qt.Key_Escape)
        self.assertTrue(control.label_button.isVisible())
        control.search_button.click()
        self.assertEqual(self.window.search_box.currentText(), "unfinished search")
        control.close_button.click()
        control.label_button.click()
        self.assertEqual(self.window.label_filter_box.currentText(), "label draft")

    def test_search_shortcut_switches_from_label_and_selects_the_search_draft(self):
        self.window.motion.set_enabled(False)
        self.window.search_box.setCurrentText("draft")
        self.window.filter_input.open("label")
        with patch.object(QtWidgets.QApplication, "activeWindow", return_value=self.window):
            self.window.keyboard.activate("search")
        self.assertTrue(self.window.search_box.isVisible())
        self.assertFalse(self.window.label_filter_box.isVisible())
        self.assertEqual(self.window.search_box.lineEdit().selectedText(), "draft")
        self.assertIn(self.window.keyboard.text("search"), self.window.filter_input.search_button.toolTip())

    def test_suggestion_and_tab_apply_the_selected_filter_and_escape_closes_popup_first(self):
        self.window.motion.set_enabled(False)
        control = self.window.filter_input
        control.open("search")
        box = self.window.search_box
        box.setCurrentText("comb")
        QtTest.QTest.keyClick(box.lineEdit(), QtCore.Qt.Key_Tab)
        self.assertEqual(self.window.filters.queries, ("combat.pak",))
        control.collapse()
        control.open("label")
        box = self.window.label_filter_box
        box.completer().activated[str].emit("combat")
        self.assertEqual(self.window.filters.labels, ("combat",))
        box.lineEdit().setText("co")
        box.completer().setCompletionPrefix("co")
        box.completer().complete()
        self.qt_app.processEvents()
        popup = box.completer().popup()
        self.assertTrue(popup.isVisible())
        QtTest.QTest.keyClick(popup, QtCore.Qt.Key_Escape)
        self.assertFalse(popup.isVisible())
        self.assertTrue(box.isVisible())
        QtTest.QTest.keyClick(box.lineEdit(), QtCore.Qt.Key_Escape)
        self.assertTrue(control.search_button.isVisible())

    def test_reversal_and_disabling_motion_settle_to_the_requested_state(self):
        control = self.window.filter_input
        control.open("search")
        advance_motion(self.window, 0.4)
        control.collapse()
        advance_motion(self.window)
        self.assertTrue(control.search_button.isVisible())
        control.open("label")
        advance_motion(self.window, 0.4)
        self.window.motion.set_enabled(False)
        self.assertTrue(self.window.label_filter_box.isVisible())
        self.assertTrue(control.cover.isHidden())
        control.collapse()
        self.assertTrue(control.label_button.isVisible())
        self.window.close()
        self.assertFalse(self.window.motion._transitions)

    def test_paging_runs_immediately_and_only_clicked_arrow_pulses_without_geometry_changes(self):
        for page, toolbar, method in (("library", self.window.mods_actions, "_change_mod_page"),
                                      ("presets", self.window.presets_toolbar, "_change_preset_page")):
            with self.subTest(page=page):
                self.window._navigate(page)
                self.qt_app.processEvents()
                self.window.motion.finish_all()
                button = toolbar.button("next_page")
                other = toolbar.button("prev_page")
                geometry = button.geometry()
                before = button.grab().toImage()
                other_before = other.grab().toImage()
                with patch.object(self.window, method, wraps=getattr(self.window, method)) as change:
                    button.click()
                    change.assert_called_once_with(1)
                advance_motion(self.window, 0.5)
                self.assertNotEqual(before, button.grab().toImage())
                self.assertEqual(other_before, other.grab().toImage())
                self.assertEqual(geometry, button.geometry())
                advance_motion(self.window)
                self.assertEqual(before, button.grab().toImage())
