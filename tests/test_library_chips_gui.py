from __future__ import annotations

from copy import deepcopy
import unittest
from unittest.mock import patch

from mod_manager.labels import AUTOMATIC, LabelDefinition, LabelState, ResolvedLabels
from mod_manager.mods import mods_view
from tests.qt_support import qt_available
from tests.window_fixture import WindowTestCase, mod_item

if qt_available():
    from PySide6 import QtCore, QtGui, QtTest, QtWidgets

    from mod_manager.ui.theme import tokens


@unittest.skipUnless(qt_available(), "PySide6 is not installed")
class LibraryChipsGuiTests(WindowTestCase):
    def setUp(self):
        super().setUp()
        self.mods += [mod_item("first type.pak", True), mod_item("first type old.pak")]
        self.state = LabelState({
            "Combat": LabelDefinition(),
            "Looks": LabelDefinition(AUTOMATIC, ["ui", "first type"], ["old"]),
            "Many": LabelDefinition(AUTOMATIC, ["pak"]),
            "Empty": LabelDefinition(),
        }, {"combat.pak": ["Combat"]})
        self.favorites = {"ui.pak", "first type.pak"}
        patches = [
            patch("mod_manager.ui.app.mods_view", side_effect=mods_view),
            patch("mod_manager.mods.discover_mods", side_effect=lambda _cfg: self.mods),
            patch("mod_manager.mods.ensure_mod_records"),
            patch("mod_manager.mods.load_labels", return_value={}),
            patch("mod_manager.mods.load_mod_records", side_effect=lambda: {
                name: {"labels": values} for name, values in self.state.assignments.items()}),
            patch("mod_manager.mods.load_label_definitions", side_effect=lambda: self.state.definitions),
            patch("mod_manager.mods.load_favorites", side_effect=lambda _cfg: self.favorites),
            patch("mod_manager.ui.app.load_favorites", side_effect=lambda _cfg: self.favorites),
            patch("mod_manager.ui.controllers.labels_controller.load_label_state", side_effect=lambda: deepcopy(self.state)),
            patch("mod_manager.ui.controllers.labels_controller.save_label_state", side_effect=self._save),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.window.refresh_mods()

    def _save(self, state):
        self.state = deepcopy(state)

    def names(self):
        return [mod.name for mod in self.window.current_mod_items]

    def enter(self, box, text):
        box.setCurrentText(text)
        box.lineEdit().returnPressed.emit()

    def show_window(self, width=tokens.DEFAULT_WIDTH):
        self.window.resize(width, tokens.DEFAULT_HEIGHT)
        self.window.show()
        self.qt_app.processEvents()

    def test_multiple_label_and_search_chips_share_order_and_remove_individually(self):
        self.enter(self.window.label_filter_box, "looks")
        self.enter(self.window.search_box, "first type")
        self.enter(self.window.label_filter_box, "Combat")
        self.enter(self.window.search_box, "combat")
        self.enter(self.window.search_box, "FIRST TYPE")
        self.assertEqual(self.window.filters.chips, [
            ("label", "Looks"), ("search", "first type"), ("label", "Combat"), ("search", "combat")])
        self.assertEqual(self.names(), ["combat.pak", "first type.pak"])
        summary = self.window.filter_summary
        self.assertEqual(summary.model.rowCount(), 4)
        self.assertEqual([summary.model.index(row, 0).data(QtCore.Qt.UserRole) for row in range(4)],
                         ["label", "search", "label", "search"])
        self.assertEqual(self.window.search_box.currentText(), "")
        self.assertEqual(self.window.label_filter_box.currentText(), "")
        summary.view.setCurrentIndex(summary.model.index(0, 0))
        QtTest.QTest.keyClick(summary.view, QtCore.Qt.Key_Delete)
        self.assertEqual(self.window.filters.labels, ("Combat",))
        self.assertEqual(self.window.filters.queries, ("first type", "combat"))
        self.assertEqual(self.names(), ["combat.pak"])
        self.assertIn("Showing 1 of 4 mods", self.window.mods_tab.subtitle.text())
        self.assertFalse(any("Showing" in label.text() for label in summary.findChildren(QtWidgets.QLabel)))

    def test_radio_modes_are_exclusive_and_clear_tracks_active_filters_and_busy(self):
        clear = self.window.filter_summary.clear_button
        self.assertFalse(clear.isEnabled())
        self.window.filter_modes.buttons["installed"].click()
        self.assertEqual(self.names(), ["combat.pak", "first type.pak"])
        self.assertTrue(clear.isEnabled())
        self.window.filter_modes.buttons["favorite"].click()
        self.assertEqual(self.names(), ["first type.pak", "ui.pak"])
        self.assertEqual(self.window.filters.state, "all")
        self.assertEqual(sum(button.isChecked() for button in self.window.filter_modes.buttons.values()), 1)
        self.window.filter_modes.buttons["favorite"].click()
        self.assertEqual(self.window.filters.mode, "favorite")
        self.window._set_busy(True)
        self.assertFalse(clear.isEnabled())
        self.window._set_busy(False)
        self.assertTrue(clear.isEnabled())
        clear.click()
        self.assertEqual(self.window.filters.mode, "all")
        self.assertEqual(len(self.names()), 4)
        self.assertFalse(clear.isEnabled())
        self.window._set_busy(True)
        self.window._set_busy(False)
        self.assertFalse(clear.isEnabled())
        self.enter(self.window.search_box, "unmatched")
        self.assertTrue(clear.isEnabled())
        self.window.search_box.setCurrentText("unfinished")
        clear.click()
        self.assertEqual(self.window.search_box.currentText(), "")
        self.assertFalse(clear.isEnabled())

    def test_sidebar_counts_sort_whole_catalog_and_toggle_across_pages(self):
        view = self.window.workspace.labels_list
        entries = [view.model().index(row, 0).data(QtCore.Qt.UserRole) for row in range(4)]
        self.assertEqual([(name, count) for name, _mode, count, _active in entries],
                         [("Many", 4), ("Looks", 2), ("Combat", 1), ("Empty", 0)])
        self.window._navigate("presets")
        view.setCurrentIndex(view.model().index(1, 0))
        QtTest.QTest.keyClick(view, QtCore.Qt.Key_Return)
        self.assertEqual(self.window.workspace.current_page, "library")
        self.assertEqual(self.window.filters.labels, ("Looks",))
        self.assertEqual(self.names(), ["first type.pak", "ui.pak"])
        self.assertTrue(view.model().index(1, 0).data(QtCore.Qt.UserRole)[3])
        self.enter(self.window.search_box, "first")
        self.assertEqual(view.model().index(1, 0).data(QtCore.Qt.UserRole)[2], 2)
        QtTest.QTest.keyClick(view, QtCore.Qt.Key_Return)
        self.assertEqual(self.window.filters.labels, ())
        self.assertFalse(view.model().index(1, 0).data(QtCore.Qt.UserRole)[3])
        self.assertEqual(view.delegate.accent, QtGui.QColor(self.window.theme.system_accent))

    def test_chip_strip_scrolls_without_wrapping_and_mouse_close_keeps_other_types(self):
        self.show_window()
        for number in range(12):
            self.window.filters.add("search", f"very long search phrase {number}")
        self.window.filters.add("label", "Looks")
        self.window.refresh_mods()
        self.qt_app.processEvents()
        summary = self.window.filter_summary
        view = summary.view
        bar = view.horizontalScrollBar()
        self.assertGreater(bar.maximum(), 0)
        self.assertTrue(bar.isVisible())
        self.assertEqual(view.verticalScrollBar().maximum(), 0)
        rects = [view.visualRect(summary.model.index(row, 0)) for row in range(summary.model.rowCount())]
        self.assertEqual(len({rect.top() for rect in rects}), 1)
        self.assertTrue(view.viewport().rect().contains(rects[-1]))
        old = bar.value()
        wheel = QtGui.QWheelEvent(QtCore.QPointF(view.viewport().rect().center()),
                                 QtCore.QPointF(view.viewport().mapToGlobal(view.viewport().rect().center())),
                                 QtCore.QPoint(), QtCore.QPoint(0, 120), QtCore.Qt.NoButton,
                                 QtCore.Qt.NoModifier, QtCore.Qt.NoScrollPhase, False)
        QtWidgets.QApplication.sendEvent(view.viewport(), wheel)
        self.assertLess(bar.value(), old)
        bar.setValue(0)
        first = summary.model.index(0, 0)
        close = view.itemDelegate().close_rect(view.visualRect(first))
        QtTest.QTest.mouseClick(view.viewport(), QtCore.Qt.LeftButton, pos=close.center())
        self.assertEqual(len(self.window.filters.queries), 11)
        self.assertEqual(self.window.filters.labels, ("Looks",))
        summary.clear_button.click()
        self.qt_app.processEvents()
        self.assertEqual(bar.maximum(), 0)
        self.assertFalse(bar.isVisible())

    def test_profile_reconciliation_removes_missing_labels_and_retains_search_and_mode(self):
        self.window.filters.add("label", "Looks")
        self.window.filters.add("label", "Combat")
        self.window.filters.add("search", "pak")
        self.window.filters.mode = "favorite"
        self.state = LabelState({"Combat": LabelDefinition()}, {"combat.pak": ["Combat"]})
        self.window.refresh_mods()
        self.assertEqual(self.window.filters.labels, ("Combat",))
        self.assertEqual(self.window.filters.queries, ("pak",))
        self.assertEqual(self.window.filters.mode, "favorite")
        self.assertEqual(self.window.workspace.labels_list.model().rowCount(), 1)

    def test_exclusion_input_preview_autosave_and_edit_cancel(self):
        self.window._navigate("labels")
        controller = self.window.labels_controller
        controller._rebuild("Looks")
        editor = controller.editor.terms_edit
        editor.mode_button.click()
        self.assertIn("Exclude", editor.mode_button.toolTip())
        editor.new_edit.setText("first type")
        self.assertEqual(controller.editor.matches_model.names, ["ui.pak"])
        controller.flush()
        self.assertEqual(self.state.definitions["Looks"].exclusions, ["old", "first type"])
        editor.add_pending()
        self.assertEqual(editor.new_edit.text(), "")
        excluded_row = len(editor.draft.terms)
        editor.start_edit(excluded_row)
        field = editor.view.indexWidget(editor.model.index(excluded_row, 1))
        field.setText("ui")
        self.assertEqual(controller.editor.matches_model.names, [])
        QtTest.QTest.keyClick(field, QtCore.Qt.Key_Escape)
        self.assertEqual(editor.draft.exclusions, ["old", "first type"])
        self.assertEqual(controller.editor.matches_model.names, ["ui.pak"])
        self.assertIn("Exclude:", editor.model.index(excluded_row, 1).data(QtCore.Qt.ToolTipRole))

    def test_rule_type_toggle_preserves_raw_edit_and_blocks_removing_last_inclusion(self):
        self.window._navigate("labels")
        controller = self.window.labels_controller
        controller._rebuild("Looks")
        editor = controller.editor.terms_edit
        editor.toggle_rule(0)
        self.assertTrue(editor.draft.edited_excluded)
        editor.confirm_edit()
        self.assertEqual(editor.draft.terms, ["first type"])
        self.assertEqual(editor.draft.exclusions, ["ui", "old"])
        editor.toggle_rule(0)
        controller.flush()
        self.assertIn("at least one", controller.editor.status.text())
        self.assertEqual(self.state.definitions["Looks"].terms, ["ui", "first type"])
        editor.cancel_edit()
        controller.flush()
        self.assertEqual(self.state.definitions["Looks"].terms, ["first type"])
