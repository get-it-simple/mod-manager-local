from __future__ import annotations

import unittest
from copy import deepcopy
from unittest.mock import patch

from tests.qt_support import dispose, qt_available
from tests.window_fixture import WindowTestCase, mod_item

if qt_available():
    from PySide6 import QtCore, QtGui, QtTest, QtWidgets

    from mod_manager.ui.app import ModManagerGui
    from mod_manager.ui.theme import tokens


@unittest.skipUnless(qt_available(), "PySide6 is not installed")
class WorkspaceGuiTests(WindowTestCase):
    def test_navigation_keeps_library_selection_and_filters(self):
        self.select_mod_rows(1)
        self.window.search_box.setCurrentText("draft search")
        for key in ("settings", "presets", "cleanup", "games", "library"):
            self.window.workspace.navigation[key].click()
            self.assertEqual(self.window.workspace.current_page, key)
        self.assertEqual(self.window._selected_indexes(), [2])
        self.assertEqual(self.window.search_box.currentText(), "draft search")

    def test_settings_draft_is_retained_without_writing_and_reset_uses_saved_values(self):
        self.window._navigate("settings")
        with patch("mod_manager.storage.save_config") as save:
            self.window.setting_widgets["page_size"].setText("27")
            self.window._navigate("library")
            self.window._navigate("settings")
            self.assertEqual(self.window.setting_widgets["page_size"].text(), "27")
            self.assertEqual(self.window.cfg["page_size"], self.cfg["page_size"])
            save.assert_not_called()
            self.window.settings.toolbar.button("reset_settings").click()
            self.assertEqual(self.window.setting_widgets["page_size"].text(), str(self.window.cfg["page_size"]))
            save.assert_not_called()

    def test_closing_never_writes_unsaved_settings(self):
        previous = self.window.cfg["page_size"]
        self.window.setting_widgets["page_size"].setText("29")
        with patch("mod_manager.ui.app.save_config") as save:
            self.window.close()
        self.assertEqual(save.call_args.args[0]["page_size"], previous)

    def test_details_visibility_and_width_survive_new_window_and_view_changes(self):
        self.window.show()
        self.qt_app.processEvents()
        self.window.tile_splitter.setSizes([400, 300])
        self.window.details_button.click()
        self.assertFalse(self.window.cfg["mod_details_visible"])
        width = self.window.cfg["_tile_detail_width"]
        self.window._set_view_mode("tiles")
        self.assertTrue(self.window.detail_scroll.isHidden())
        self.window._save_tile_splitter_sizes()
        self.assertEqual(self.window.cfg["_tile_detail_width"], width)
        saved = deepcopy(self.window.cfg)
        with patch("mod_manager.ui.app.load_config", return_value=saved):
            other = ModManagerGui()
        try:
            other.show()
            self.qt_app.processEvents()
            self.assertFalse(other.details_button.isChecked())
            self.assertTrue(other.detail_scroll.isHidden())
            other.details_button.click()
            self.qt_app.processEvents()
            self.assertFalse(other.detail_scroll.isHidden())
            self.assertGreater(other.tile_splitter.sizes()[1], 0)
            self.assertEqual(other.setting_widgets["mod_details_visible"].isChecked(), True)
        finally:
            dispose(other)

    def test_list_and_tiles_share_selection_and_details(self):
        self.select_mod_rows(1)
        for mode in ("tiles", "list", "tiles"):
            self.window._set_view_mode(mode)
            self.assertEqual(self.window._selected_indexes(), [2])
            text = [label.text() for label in self.window.detail_frame.findChildren(QtWidgets.QLabel)]
            self.assertIn("ui.pak", text)

    def test_navigation_and_profile_changes_are_blocked_while_busy(self):
        self.window._set_busy(True)
        try:
            for key, button in self.window.workspace.navigation.items():
                button.click()
                self.assertFalse(button.isEnabled(), key)
                self.assertEqual(self.window.workspace.current_page, "library")
            self.assertFalse(self.window.workspace.profile_box.isEnabled())
            self.assertFalse(self.window.details_button.isEnabled())
            self.assertFalse(self.window.detail_frame.isEnabled())
            self.window._navigate("settings")
            self.assertEqual(self.window.workspace.current_page, "library")
        finally:
            self.window._set_busy(False)
        self.window.workspace.navigation["settings"].click()
        self.assertEqual(self.window.workspace.current_page, "settings")

    def test_paste_and_library_shortcuts_do_not_operate_from_settings(self):
        self.window._navigate("settings")
        with patch.object(self.window, "_handle_clipboard_paths") as paths, patch.object(self.window, "_change_mod_page") as page, patch("mod_manager.ui.app.read_clipboard_paths", return_value=[self.mods[0].src]):
            self.window._handle_paste()
            self.window._nav_back()
            self.window._nav_forward()
        paths.assert_not_called()
        page.assert_not_called()

    def test_paste_into_an_edit_keeps_normal_text_behavior(self):
        self.window.show()
        self.window._navigate("settings")
        edit = self.window.setting_widgets["page_size"]
        edit.setFocus()
        edit.selectAll()
        self.qt_app.clipboard().setText("23")
        self.qt_app.processEvents()
        with patch.object(self.window, "_handle_paste") as import_paste:
            QtTest.QTest.keyClick(edit, QtCore.Qt.Key_V, QtCore.Qt.ControlModifier)
        self.assertEqual(edit.text(), "23")
        import_paste.assert_not_called()

    def test_sidebar_and_toolbars_fit_at_minimum_and_default_sizes(self):
        self.window.show()
        for width, height in ((tokens.MIN_WIDTH, tokens.MIN_HEIGHT), (tokens.DEFAULT_WIDTH, tokens.DEFAULT_HEIGHT)):
            self.window.resize(width, height)
            self.qt_app.processEvents()
            self.assertEqual(self.window.width(), width)
            if width < tokens.SIDEBAR_BREAKPOINT:
                self.assertTrue(self.window.workspace.compact)
            for button in self.window.workspace.navigation.values():
                if self.window.workspace.compact:
                    self.assertEqual(button.text(), "")
                    self.assertTrue(button.accessibleName())
                    self.assertTrue(button.toolTip())
                else:
                    self.assertGreater(button.width(), button.fontMetrics().horizontalAdvance(button.text()) + tokens.ICON_SIZE)
            for toolbar in (self.window.mods_toolbar, self.window.mods_actions):
                for section in toolbar.sections.values():
                    self.assertTrue(toolbar.rect().contains(section.geometry()), (width, section.key, section.geometry(), toolbar.rect()))
            self.assertGreater(self.window.mods_stack.width(), 0)
            self.assertGreater(self.window.mods_stack.height(), 0)

    def test_large_collection_keeps_model_view_and_empty_state_recovers(self):
        mods = [mod_item(f"Mod-{index:04}.pak") for index in range(2000)]
        with patch("mod_manager.ui.app.mods_view", return_value=(mods, mods, 1, 1, {})):
            self.window.refresh_mods()
        self.assertEqual(self.window.mods_model.rowCount(), 2000)
        self.assertIs(self.window.mods_table.model(), self.window.tiles_view.model())
        self.assertLess(len(self.window.tiles_view.findChildren(QtWidgets.QPushButton)), 10)
        with patch("mod_manager.ui.app.mods_view", return_value=([], [], 1, 1, {})):
            self.window.refresh_mods()
        self.assertIs(self.window.mods_stack.currentWidget(), self.window.library_empty)
        self.window.refresh_mods()
        self.assertIs(self.window.mods_stack.currentWidget(), self.window.mods_table)

    def test_detail_controls_keep_their_height_in_a_small_window(self):
        self.window.resize(tokens.MIN_WIDTH, tokens.MIN_HEIGHT)
        self.window.show()
        self.select_mod_rows(0)
        self.qt_app.processEvents()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        buttons = self.window.detail_frame.findChildren(QtWidgets.QPushButton)
        rectangles = []
        for button in buttons:
            self.assertGreaterEqual(button.height(), button.minimumSizeHint().height())
            origin = button.mapTo(self.window.detail_frame, QtCore.QPoint())
            rectangle = QtCore.QRect(origin, button.size())
            self.assertTrue(self.window.detail_frame.rect().contains(rectangle))
            for previous in rectangles:
                self.assertFalse(rectangle.intersects(previous))
            rectangles.append(rectangle)
        self.assertGreaterEqual(self.window.detail_frame.height(), self.window.detail_layout.minimumSize().height())

    def test_library_file_paste_keeps_working_with_search_focused(self):
        self.window.show()
        search = self.window.search_box.lineEdit()
        search.setFocus()
        self.qt_app.processEvents()
        with patch("mod_manager.ui.app.clipboard_has_files", return_value=True), patch.object(self.window, "_handle_paste") as paste:
            key = QtCore.QEvent.Type.KeyPress
            event = QtGui.QKeyEvent(key, QtCore.Qt.Key_V, QtCore.Qt.ControlModifier)
            self.assertTrue(self.window.eventFilter(search, event))
        paste.assert_called_once()

    def test_settings_save_stays_on_page_and_applies_details_setting(self):
        self.use_inline_runner()
        self.window._navigate("settings")
        self.window.setting_widgets["mod_details_visible"].setChecked(False)
        self.window.setting_widgets["page_size"].setText("26")
        self.window.settings.toolbar.button("save_settings").click()
        self.assertEqual(self.window.workspace.current_page, "settings")
        self.assertEqual(self.window.cfg["page_size"], 26)
        self.assertFalse(self.window.cfg["mod_details_visible"])
        self.window._navigate("library")
        self.assertTrue(self.window.detail_scroll.isHidden())

    def test_large_font_wraps_toolbars_and_preserves_control_geometry(self):
        self.window.cfg["gui_font_size"] = 20
        self.window._refresh_theme()
        self.window.resize(tokens.MIN_WIDTH, tokens.MIN_HEIGHT)
        self.window.show()
        self.qt_app.processEvents()
        self.assertTrue(self.window.workspace.compact)
        for toolbar in (self.window.mods_toolbar, self.window.mods_actions):
            for section in toolbar.sections.values():
                self.assertTrue(toolbar.rect().contains(section.geometry()), (section.key, section.geometry(), toolbar.rect()))
        self.assertGreater(self.window.mods_stack.height(), 0)

    def test_collection_pages_explain_empty_results(self):
        with patch("mod_manager.ui.app.presets_view", return_value=({}, [], [], 1, 1)):
            self.window._navigate("presets")
        self.assertIs(self.window.presets_stack.currentWidget(), self.window.presets_empty)
        self.assertTrue(self.window.presets_toolbar.button("save").isEnabled())
        with patch("mod_manager.ui.app.list_broken_links", return_value=[]):
            self.window._navigate("cleanup")
        self.assertIs(self.window.broken_stack.currentWidget(), self.window.broken_empty)


@unittest.skipUnless(qt_available(), "PySide6 is not installed")
class EmptyWorkspaceTests(WindowTestCase):
    config_overrides = {"mods_source_dir": "", "game_mods_dir": "", "mod_extensions": "", "game_profiles": [], "active_game_profile_id": ""}

    def test_no_profile_starts_at_games_and_only_enables_global_pages(self):
        self.assertEqual(self.window.workspace.current_page, "games")
        for key in ("library", "presets", "cleanup"):
            self.assertFalse(self.window.workspace.navigation[key].isEnabled())
            self.window._navigate(key)
            self.assertEqual(self.window.workspace.current_page, "games")
        self.window.workspace.navigation["settings"].click()
        self.assertEqual(self.window.workspace.current_page, "settings")
