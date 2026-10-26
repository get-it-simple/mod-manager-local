from __future__ import annotations

import unittest
from copy import deepcopy
from unittest.mock import patch

from tests.qt_support import qt_available
from tests.window_fixture import WindowTestCase, mod_item
from mod_manager.labels import AUTOMATIC, MANUAL, LabelDefinition, LabelState, ResolvedLabels

if qt_available():
    from PySide6 import QtCore, QtGui, QtTest, QtWidgets

    from mod_manager.ui.theme import tokens


@unittest.skipUnless(qt_available(), "PySide6 is not installed")
class LabelsGuiTests(WindowTestCase):
    def setUp(self):
        super().setUp()
        self.persisted = LabelState(
            {"Combat": LabelDefinition(MANUAL, ["combat"]), "Looks": LabelDefinition(AUTOMATIC, ["ui"])},
            {"combat.pak": ["Combat"]},
        )
        self.initial = deepcopy(self.persisted)
        self.profile_states = {str(self.window.cfg.get("active_game_profile_id") or ""): self.persisted}
        self.patches = [
            patch("mod_manager.ui.controllers.labels_controller.load_label_state", side_effect=self._load),
            patch("mod_manager.ui.controllers.labels_controller.save_label_state", side_effect=self._save),
            patch("mod_manager.ui.app.mods_view", side_effect=self._view),
        ]
        for patcher in self.patches:
            patcher.start()
        self.window.refresh_mods()
        self.controller = self.window.labels_controller
        self.editor = self.controller.editor

    def tearDown(self):
        super().tearDown()
        for patcher in reversed(self.patches):
            patcher.stop()

    def _load(self):
        profile = str(self.window.cfg.get("active_game_profile_id") or "")
        self.persisted = self.profile_states.setdefault(profile, deepcopy(self.initial))
        return deepcopy(self.persisted)

    def _save(self, state):
        self.persisted = deepcopy(state)
        self.profile_states[str(self.window.cfg.get("active_game_profile_id") or "")] = self.persisted

    def _view(self, _cfg, page, label_filter, search, _order, *_args):
        labels = ResolvedLabels(self.persisted, [mod.name for mod in self.mods])
        items = [mod for mod in self.mods if search.casefold() in mod.name.casefold() and (not label_filter or label_filter in self.persisted.members(mod.name))]
        return items, items[:1], 1, max(1, len(items)), labels

    def open_label(self, name):
        self.window._navigate("labels")
        self.controller._rebuild(name)

    def set_fragments(self, *terms):
        editor = self.editor.terms_edit
        while editor.model.rowCount():
            editor.delete_fragment(0)
        for term in terms:
            editor.new_edit.setText(term)
            QtTest.QTest.keyClick(editor.new_edit, QtCore.Qt.Key_Return)

    def show_editor(self):
        self.window.show()
        self.window.activateWindow()
        self.qt_app.processEvents()

    def click_fragment_action(self, row, column):
        fragments = self.editor.terms_edit
        view = fragments.view
        index = view.model().index(row, 1)
        view.scrollTo(index)
        self.qt_app.processEvents()
        if column == 2 and fragments.draft.editing == row:
            QtTest.QTest.keyClick(view.indexWidget(index), QtCore.Qt.Key_Return)
            return
        rect = view.visualRect(index)
        point = rect.center() if column == 2 else QtCore.QPoint(rect.right() - tokens.ICON_BUTTON_SIZE // 2, rect.center().y())
        QtTest.QTest.mouseClick(view.viewport(), QtCore.Qt.LeftButton, pos=point)

    def test_fragment_enter_deduplication_and_save_include_unconfirmed_input(self):
        self.open_label("Looks")
        self.show_editor()
        fragments = self.editor.terms_edit
        for text in (" skin ", "SKIN", "   "):
            fragments.new_edit.setText(text)
            QtTest.QTest.keyClick(fragments.new_edit, QtCore.Qt.Key_Return)
            self.assertEqual(fragments.new_edit.text(), "")
            self.assertTrue(fragments.new_edit.hasFocus())
        self.assertEqual(fragments.model.rowCount(), 2)
        self.assertEqual(fragments.model.index(1, 0).data(), "2")
        fragments.new_edit.setText(" pak ")
        self.assertEqual(self.editor.matches_model.names, ["combat.pak", "ui.pak"])
        self.controller.flush()
        self.assertEqual(self.persisted.definitions["Looks"].terms, ["ui", "skin", "pak"])
        self.assertEqual(fragments.new_edit.text(), " pak ")
        self.assertEqual(fragments.model.rowCount(), 2)

    def test_fragment_row_edit_save_and_enter_return_to_new_input(self):
        self.open_label("Looks")
        self.show_editor()
        fragments = self.editor.terms_edit
        self.click_fragment_action(0, 2)
        field = fragments.view.indexWidget(fragments.model.index(0, 1))
        self.assertIsInstance(field, QtWidgets.QLineEdit)
        field.setText("combat")
        self.assertEqual(self.editor.matches_model.names, ["combat.pak"])
        self.assertEqual(fragments.model.index(0, 2).data(), "Edit fragment")
        self.click_fragment_action(0, 2)
        self.assertTrue(fragments.new_edit.hasFocus())
        self.assertEqual(fragments.model.index(0, 1).data(), "combat")
        self.click_fragment_action(0, 2)
        field = fragments.view.indexWidget(fragments.model.index(0, 1))
        field.setText(" pak ")
        QtTest.QTest.keyClick(field, QtCore.Qt.Key_Return)
        self.assertTrue(fragments.new_edit.hasFocus())
        self.assertEqual(fragments.model.index(0, 1).data(), "pak")
        self.assertEqual(self.persisted.definitions["Looks"].terms, ["ui"])

    def test_global_save_includes_open_row_editor_without_enter(self):
        self.open_label("Looks")
        fragments = self.editor.terms_edit
        fragments.start_edit(0)
        field = fragments.view.indexWidget(fragments.model.index(0, 1))
        field.setText(" combat ")
        fragments.new_edit.setText("pak")
        self.controller.flush()
        self.assertEqual(self.persisted.definitions["Looks"].terms, ["combat", "pak"])
        self.assertEqual(fragments.draft.editing, 0)
        self.assertEqual(fragments.new_edit.text(), "pak")

    def test_fragment_actions_support_keyboard_activation_and_escape_cancels_edit(self):
        self.open_label("Looks")
        self.show_editor()
        fragments = self.editor.terms_edit
        fragments.view.setCurrentIndex(fragments.model.index(0, 1))
        fragments.view.setFocus()
        QtTest.QTest.keyClick(fragments.view, QtCore.Qt.Key_Return)
        field = fragments.view.indexWidget(fragments.model.index(0, 1))
        self.assertIsInstance(field, QtWidgets.QLineEdit)
        field.setText("combat")
        QtTest.QTest.keyClick(field, QtCore.Qt.Key_Escape)
        self.assertEqual(fragments.model.index(0, 1).data(), "ui")
        self.assertEqual(self.editor.matches_model.names, ["ui.pak"])
        self.assertTrue(fragments.new_edit.hasFocus())

    def test_switching_edited_rows_after_deduplication_keeps_the_clicked_fragment(self):
        self.open_label("Looks")
        self.set_fragments("ui", "pak", "combat")
        fragments = self.editor.terms_edit
        fragments.start_edit(0)
        fragments.view.indexWidget(fragments.model.index(0, 1)).setText("pak")
        fragments.start_edit(2)
        self.assertEqual(fragments.model.rowCount(), 2)
        self.assertEqual(fragments.draft.editing, 1)
        self.assertEqual(fragments.view.indexWidget(fragments.model.index(1, 1)).text(), "combat")
        self.assertEqual(fragments.next_id.text(), "3")

    def test_deleting_a_row_before_an_open_editor_preserves_its_unconfirmed_text(self):
        self.open_label("Looks")
        self.set_fragments("ui", "pak", "combat")
        fragments = self.editor.terms_edit
        fragments.start_edit(2)
        fragments.view.indexWidget(fragments.model.index(2, 1)).setText("skin")
        fragments.delete_fragment(0)
        self.assertEqual(fragments.draft.editing, 1)
        self.assertEqual(fragments.view.indexWidget(fragments.model.index(1, 1)).text(), "skin")
        self.controller.save()
        self.assertEqual(self.persisted.definitions["Looks"].terms, ["pak", "skin"])

    def test_failed_save_preserves_open_edit_and_pending_input_for_retry(self):
        self.open_label("Looks")
        fragments = self.editor.terms_edit
        fragments.start_edit(0)
        fragments.view.indexWidget(fragments.model.index(0, 1)).setText(" combat ")
        fragments.new_edit.setText(" pak ")
        with patch("mod_manager.ui.controllers.labels_controller.save_label_state", side_effect=PermissionError("locked")), patch("mod_manager.ui.controllers.labels_controller.prompts.show_error"):
            self.controller.save()
        self.assertEqual(self.persisted.definitions["Looks"].terms, ["ui"])
        self.assertEqual(fragments.view.indexWidget(fragments.model.index(0, 1)).text(), " combat ")
        self.assertEqual(fragments.new_edit.text(), " pak ")
        self.controller.save()
        self.assertEqual(self.persisted.definitions["Looks"].terms, ["combat", "pak"])

    def test_switching_to_manual_keeps_an_invalid_open_fragment_accessible(self):
        self.open_label("Looks")
        self.show_editor()
        fragments = self.editor.terms_edit
        fragments.start_edit(0)
        fragments.view.indexWidget(fragments.model.index(0, 1)).setText("")
        self.editor.mode_box.setCurrentIndex(0)
        self.controller.save()
        self.assertEqual(self.editor.mode_box.currentIndex(), 0)
        self.assertFalse(fragments.isHidden())
        self.assertIn("nonempty fragment", self.editor.status.text())
        fragments.cancel_edit()
        self.assertTrue(fragments.isHidden())
        self.controller.save()
        self.assertEqual(self.persisted.definitions["Looks"].mode, MANUAL)
        self.assertEqual(self.persisted.definitions["Looks"].terms, ["ui"])

    def test_empty_edited_fragment_blocks_save_and_survives_navigation(self):
        self.open_label("Looks")
        self.show_editor()
        fragments = self.editor.terms_edit
        fragments.start_edit(0)
        field = fragments.view.indexWidget(fragments.model.index(0, 1))
        field.setText("   ")
        self.click_fragment_action(0, 2)
        self.assertIn("nonempty fragment", self.editor.status.text())
        self.assertEqual(fragments.draft.editing, 0)
        self.controller._rebuild("Combat")
        self.controller.flush()
        self.assertIn("nonempty fragment", self.editor.status.text())
        self.controller._rebuild("Looks")
        field = fragments.view.indexWidget(fragments.model.index(0, 1))
        self.assertEqual(field.text(), "   ")
        QtTest.QTest.mouseClick(field, QtCore.Qt.LeftButton)
        self.assertTrue(field.hasFocus())
        self.assertEqual(self.persisted.definitions["Looks"].terms, ["ui"])
        fragments.cancel_edit()
        fragments.new_edit.setText("   ")
        self.controller.save()
        self.assertEqual(self.persisted.definitions["Looks"].terms, ["ui"])

    def test_pending_and_open_edit_drafts_survive_labels_pages_and_profiles(self):
        self.open_label("Looks")
        first = self.controller.profile_id
        fragments = self.editor.terms_edit
        fragments.start_edit(0)
        fragments.view.indexWidget(fragments.model.index(0, 1)).setText("combat")
        fragments.new_edit.setText("  pak  ")
        self.controller._rebuild("Combat")
        self.window._navigate("library")
        self.window.cfg["active_game_profile_id"] = "other"
        self.open_label("Looks")
        self.assertEqual(fragments.new_edit.text(), "")
        self.assertEqual(fragments.model.index(0, 1).data(), "ui")
        self.window.cfg["active_game_profile_id"] = first
        self.open_label("Looks")
        self.assertEqual(fragments.new_edit.text(), "  pak  ")
        self.assertEqual(fragments.view.indexWidget(fragments.model.index(0, 1)).text(), "combat")
        self.controller._rebuild("Combat")
        self.controller.save()
        self.assertEqual(self.persisted.definitions["Looks"].terms, ["combat", "pak"])

    def test_unchanged_open_fragment_editor_is_retained_on_reactivation(self):
        self.open_label("Looks")
        fragments = self.editor.terms_edit
        fragments.start_edit(0)
        self.window._navigate("library")
        self.open_label("Looks")
        self.assertEqual(fragments.draft.editing, 0)
        self.assertEqual(fragments.view.indexWidget(fragments.model.index(0, 1)).text(), "ui")

    def test_delete_renumbers_all_match_ids_and_empty_automatic_cannot_save(self):
        self.open_label("Looks")
        self.show_editor()
        self.set_fragments("ui", "pak", "combat")
        model = self.editor.matches_model
        self.assertEqual(model.index(0, 1).data(), "2, 3")
        self.assertEqual(model.index(1, 1).data(), "1, 2")
        self.click_fragment_action(0, 3)
        self.assertEqual(model.index(0, 1).data(), "1, 2")
        self.assertEqual(model.index(1, 1).data(), "1")
        self.assertEqual(self.editor.terms_edit.model.index(1, 0).data(), "2")
        self.set_fragments()
        self.controller.flush()
        self.assertIn("at least one", self.editor.status.text())
        self.assertEqual(self.persisted.definitions["Looks"].terms, ["ui"])

    def test_fragment_drafts_follow_rename_and_reset_discards_input(self):
        self.open_label("Looks")
        self.editor.terms_edit.new_edit.setText("pak")
        self.editor.name_edit.setText("Visuals")
        self.editor.name_edit.textEdited.emit("Visuals")
        self.controller._rebuild("Combat")
        self.controller.save()
        self.assertEqual(self.persisted.definitions["Visuals"].terms, ["ui", "pak"])
        self.controller._rebuild("Visuals")
        self.editor.terms_edit.new_edit.setText("combat")
        self.controller.reset()
        self.assertEqual(self.editor.terms_edit.new_edit.text(), "")
        self.assertEqual(self.editor.terms_edit.model.rowCount(), 2)
        self.controller.delete()
        self.controller.save()
        self.assertNotIn("Visuals", self.persisted.definitions)

    def test_matching_columns_keep_full_tooltips_and_fixed_fragment_width(self):
        name = "UI_" + "long_mod_name_" * 12 + ".pak"
        self.mods.append(mod_item(name))
        self.window.refresh_mods()
        self.open_label("Looks")
        self.set_fragments("ui", "pak", *["long_mod_name"[:length] for length in range(1, 13)])
        self.show_editor()
        view = self.editor.matches_view
        self.editor.search_edit.setText("long_mod_name")
        self.assertEqual(self.editor.matches_proxy.rowCount(), 1)
        first = self.editor.matches_proxy.index(0, 0)
        second = self.editor.matches_proxy.index(0, 1)
        self.assertEqual(first.data(QtCore.Qt.ToolTipRole), name)
        self.assertEqual(second.data(QtCore.Qt.ToolTipRole), second.data())
        self.assertIn("1, 2, 3", second.data())
        self.assertGreater(view.fontMetrics().horizontalAdvance(second.data()), view.columnWidth(1))
        before = view.columnWidth(0)
        self.window.resize(tokens.DEFAULT_WIDTH * 2, tokens.DEFAULT_HEIGHT)
        self.qt_app.processEvents()
        self.assertEqual(view.columnWidth(1), tokens.LABEL_FRAGMENTS_COLUMN_WIDTH)
        self.assertGreater(view.columnWidth(0), before)
        self.controller._rebuild("Combat")
        self.assertTrue(view.isColumnHidden(1))

    def test_autosave_waits_for_pause_and_preserves_active_fragment_input(self):
        self.open_label("Looks")
        self.show_editor()
        fragments = self.editor.terms_edit
        fragments.new_edit.setFocus()
        fragments.new_edit.setText("skin")
        QtTest.QTest.qWait(tokens.LABEL_SAVE_DELAY_MS // 2)
        self.assertEqual(self.persisted.definitions["Looks"].terms, ["ui"])
        fragments.new_edit.setText("skin_blue")
        QtTest.QTest.qWait(tokens.LABEL_SAVE_DELAY_MS // 2)
        self.assertEqual(self.persisted.definitions["Looks"].terms, ["ui"])
        cursor = fragments.new_edit.cursorPosition()
        saved = QtTest.QSignalSpy(self.controller.save_timer.timeout)
        self.assertTrue(saved.wait(3000))
        self.assertEqual(self.persisted.definitions["Looks"].terms, ["ui", "skin_blue"])
        self.assertEqual(fragments.new_edit.text(), "skin_blue")
        self.assertEqual(fragments.new_edit.cursorPosition(), cursor)
        self.assertTrue(fragments.new_edit.hasFocus())
        self.assertEqual(self.editor.status.text(), "All changes saved")
        self.assertIsNone(self.editor.toolbar.button("save"))
        self.assertIsNone(self.editor.toolbar.button("reset"))

    def test_invalid_name_survives_label_navigation_until_corrected(self):
        self.open_label("Combat")
        self.editor.name_edit.setText("looks")
        self.editor.name_edit.textEdited.emit("looks")
        self.controller._rebuild("Looks")
        self.controller._rebuild("Combat")
        self.assertEqual(self.editor.name_edit.text(), "looks")
        self.controller.flush()
        self.assertEqual(set(self.persisted.definitions), {"Combat", "Looks"})
        self.editor.name_edit.setText("Renamed")
        self.editor.name_edit.textEdited.emit("Renamed")
        saved = QtTest.QSignalSpy(self.controller.save_timer.timeout)
        self.assertTrue(saved.wait(3000))
        self.assertEqual(self.persisted.members("combat.pak"), ("Renamed",))

    def test_new_label_waits_for_autosave_and_close_flushes_valid_edits(self):
        self.open_label("Combat")
        self.controller.add()
        self.assertEqual(set(self.persisted.definitions), {"Combat", "Looks"})
        self.editor.name_edit.setText("Fresh")
        self.editor.name_edit.textEdited.emit("Fresh")
        self.assertNotIn("Fresh", self.persisted.definitions)
        self.window.close()
        self.assertIn("Fresh", self.persisted.definitions)
        self.assertNotIn("New label", self.persisted.definitions)

    def test_failed_save_keeps_window_and_profile_open_until_retry(self):
        self.open_label("Looks")
        self.show_editor()
        self.editor.terms_edit.new_edit.setText("skin")
        with patch("mod_manager.ui.controllers.labels_controller.save_label_state", side_effect=PermissionError("locked")), patch(
            "mod_manager.ui.controllers.games_controller.set_active_game_profile") as switch:
            self.window._navigate("library")
            self.assertIn("locked", self.window.runner.status_text)
            self.assertFalse(self.window.close())
            self.assertTrue(self.window.isVisible())
            self.window.games.select("other")
            switch.assert_not_called()
        self.window._navigate("labels")
        self.editor.retry.click()
        self.assertEqual(self.persisted.definitions["Looks"].terms, ["ui", "skin"])
        self.assertTrue(self.window.close())

    def test_external_label_deletion_updates_the_editor_without_resurrecting_it(self):
        self.open_label("Looks")
        self.persisted.delete("Looks")
        self.controller.flush()
        self.assertEqual(self.controller.selected, "Combat")
        self.assertEqual(self.editor.list_model.rowCount(), 1)
        self.controller.flush()
        self.assertNotIn("Looks", self.persisted.definitions)

    def test_fragment_chips_wrap_and_all_remain_visible(self):
        self.open_label("Looks")
        self.set_fragments(*[f"fragment_{index}" for index in range(18)])
        self.window.resize(tokens.DEFAULT_WIDTH * 2, tokens.DEFAULT_HEIGHT)
        self.show_editor()
        view = self.editor.terms_edit.view
        wide = view.height()
        rects = [view.visualRect(view.model().index(row, 1)) for row in range(view.model().rowCount())]
        self.assertTrue(any(rect.top() == rects[0].top() for rect in rects[1:]))
        self.assertTrue(all(view.viewport().rect().contains(rect) for rect in rects))
        self.window.resize(tokens.MIN_WIDTH, tokens.MIN_HEIGHT)
        self.qt_app.processEvents()
        self.assertGreater(view.height(), wide)
        last = view.visualRect(view.model().index(17, 1))
        self.assertTrue(view.viewport().rect().contains(last))
        self.assertFalse(view.verticalScrollBar().isVisible())

    def test_compact_label_list_shows_mode_icon_and_count_and_restores_names(self):
        self.open_label("Looks")
        self.show_editor()
        view = self.editor.list_view
        selected = view.currentIndex().data(QtCore.Qt.UserRole)
        self.editor.splitter.setSizes([view.minimumWidth(), self.editor.splitter.width()])
        self.qt_app.processEvents()
        self.assertTrue(view.compact)
        images = []
        for row, name in enumerate(("Combat", "Looks")):
            index = self.editor.list_model.index(row, 0)
            option = QtWidgets.QStyleOptionViewItem()
            option.initFrom(view)
            view.itemDelegate().initStyleOption(option, index)
            self.assertEqual(option.text, "1")
            self.assertFalse(option.icon.isNull())
            self.assertIn(name, index.data(QtCore.Qt.ToolTipRole))
            self.assertIn("Matching mods: 1", index.data(QtCore.Qt.ToolTipRole))
            images.append(option.icon.pixmap(tokens.ICON_SIZE).toImage())
        self.assertNotEqual(images[0], images[1])
        self.editor.splitter.setSizes([tokens.LABEL_LIST_MIN_WIDTH * 2, self.editor.splitter.width()])
        self.qt_app.processEvents()
        self.assertFalse(view.compact)
        self.assertEqual(view.currentIndex().data(QtCore.Qt.UserRole), selected)
        option = QtWidgets.QStyleOptionViewItem()
        view.itemDelegate().initStyleOption(option, view.currentIndex())
        self.assertIn("Looks", option.text)
        self.assertIn("Automatic", option.text)

    def test_compact_minimum_fits_large_font_and_multi_digit_counts(self):
        self.mods.extend(mod_item(f"ui_{number}.pak") for number in range(120))
        self.window.refresh_mods()
        self.open_label("Looks")
        self.show_editor()
        view = self.editor.list_view
        for point_size in (20, 72):
            with self.subTest(point_size=point_size):
                font = view.font()
                font.setPointSize(point_size)
                view.setFont(font)
                self.editor.splitter.setSizes([view.minimumWidth(), self.editor.splitter.width()])
                self.qt_app.processEvents()
                self.assertTrue(view.compact)
                self.assertGreaterEqual(view.viewport().width(), view.fontMetrics().horizontalAdvance("121") + tokens.ICON_SIZE)
                self.assertGreater(view.width(), 0)
                self.assertEqual(view.currentIndex().data(QtCore.Qt.UserRole), "Looks")

    def test_filters_retain_the_complete_catalog_including_empty_labels(self):
        self.persisted.definitions["Empty"] = LabelDefinition()
        self.window.search_box.setCurrentText("nothing")
        self.window.label_filter_box.setCurrentText("Looks")
        self.window._mods_search()
        self.assertEqual(self.window.mods_model.rowCount(), 0)
        self.assertEqual([self.window.search_box.itemText(i) for i in range(self.window.search_box.count())], ["combat.pak", "ui.pak"])
        self.assertEqual(self.window.label_filter_box.count(), 3)
        self.window._change_mod_page(1)
        self.assertEqual(self.window.search_box.count(), 2)

    def test_filter_option_tooltips_and_completion_hover_show_full_names(self):
        name = "A very long mod name that must remain available in full.pak"
        self.mods.append(mod_item(name))
        self.window.refresh_mods()
        box = self.window.search_box
        index = box.findText(name)
        self.assertEqual(box.itemData(index, QtCore.Qt.ToolTipRole), name)
        completer = box.completer()
        completer.setCompletionPrefix("very long")
        popup = completer.popup()
        model_index = completer.completionModel().index(0, 0)
        help_event = QtGui.QHelpEvent(QtCore.QEvent.ToolTip, QtCore.QPoint(), QtCore.QPoint())
        with patch.object(QtWidgets.QToolTip, "showText") as show:
            self.assertTrue(popup.itemDelegate().helpEvent(help_event, popup, QtWidgets.QStyleOptionViewItem(), model_index))
        self.assertEqual(show.call_args.args[1], name)

    def test_draft_preview_mode_switching_and_reset_preserve_inactive_settings(self):
        self.open_label("Combat")
        self.assertEqual(self.editor.matches_model.names, ["combat.pak"])
        self.editor.mode_box.setCurrentIndex(1)
        self.set_fragments("ui", "UI", "")
        self.assertEqual(self.editor.matches_model.names, ["ui.pak"])
        self.assertEqual(self.persisted.definitions["Combat"].mode, MANUAL)
        self.window._navigate("library")
        self.open_label("Combat")
        self.assertEqual(self.editor.mode_box.currentIndex(), 1)
        self.editor.mode_box.setCurrentIndex(0)
        self.assertEqual(self.editor.matches_model.names, ["combat.pak"])
        self.assertEqual(self.controller.state.definitions["Combat"].terms, ["ui"])
        self.controller.reset()
        self.assertEqual(self.controller.state, self.persisted)

    def test_manual_choices_include_mods_outside_the_current_library_page(self):
        self.open_label("Combat")
        model = self.editor.manual_model
        self.assertEqual(model.names, ["combat.pak", "ui.pak"])
        self.editor.search_edit.setText("UI")
        self.assertEqual(self.editor.manual_proxy.rowCount(), 1)
        index = self.editor.manual_proxy.index(0, 0)
        self.editor.manual_proxy.setData(index, QtCore.Qt.Checked, QtCore.Qt.CheckStateRole)
        self.assertEqual(self.editor.matches_model.names, ["combat.pak", "ui.pak"])
        self.controller.flush()
        self.assertEqual(self.persisted.members("ui.pak"), ("Combat", "Looks"))
        self.assertEqual(self.window.current_mod_labels["ui.pak"], "Combat, Looks")

    def test_create_rename_delete_save_and_empty_automatic_validation(self):
        self.open_label("Combat")
        self.controller.add()
        self.editor.name_edit.setText("Fresh")
        self.editor.name_edit.textEdited.emit("Fresh")
        self.editor.mode_box.setCurrentIndex(1)
        self.controller.flush()
        self.assertIn("at least one", self.editor.status.text())
        self.assertNotIn("Fresh", self.persisted.definitions)
        self.editor.terms_edit.new_edit.setText("pak")
        self.controller.save()
        self.assertIn("Fresh", self.persisted.definitions)
        self.assertEqual(len(self.editor.matches_model.names), 2)
        self.controller.delete()
        self.controller.save()
        self.assertNotIn("Fresh", self.persisted.definitions)

    def test_invalid_duplicate_name_cannot_save_or_overwrite_another_label(self):
        self.open_label("Combat")
        self.editor.name_edit.setText("looks")
        self.editor.name_edit.textEdited.emit("looks")
        self.controller.save()
        self.assertIn("unique", self.editor.status.text())
        self.assertEqual(set(self.persisted.definitions), {"Combat", "Looks"})

    def test_save_failure_keeps_draft_and_library_unchanged(self):
        self.open_label("Combat")
        self.editor.mode_box.setCurrentIndex(1)
        self.set_fragments("ui")
        with patch("mod_manager.ui.controllers.labels_controller.save_label_state", side_effect=PermissionError("locked")), patch("mod_manager.ui.controllers.labels_controller.prompts.show_error") as error:
            self.controller.save()
        self.assertIn("locked", self.editor.status.text())
        self.assertFalse(self.editor.retry.isHidden())
        self.assertEqual(self.controller.state.members("ui.pak"), ("Combat", "Looks"))
        self.assertEqual(self.persisted.members("ui.pak"), ("Looks",))

    def test_profile_drafts_are_separate_when_active_profile_changes(self):
        self.open_label("Combat")
        first = self.controller.profile_id
        self.editor.mode_box.setCurrentIndex(1)
        self.window.cfg["active_game_profile_id"] = "other"
        self.controller.activate()
        self.assertNotEqual(self.controller.profile_id, first)
        self.assertEqual(self.controller.state.definitions["Combat"].mode, MANUAL)
        self.window.cfg["active_game_profile_id"] = first
        self.controller.activate()
        self.assertEqual(self.controller.state.definitions["Combat"].mode, AUTOMATIC)
        self.assertEqual(self.persisted.definitions["Combat"].mode, MANUAL)

    def test_independent_saved_membership_changes_are_merged(self):
        self.open_label("Combat")
        self.set_fragments("new")
        self.persisted.assignments["ui.pak"] = ["Combat"]
        self.controller.flush()
        self.assertEqual(self.persisted.assignments["ui.pak"], ["Combat"])
        self.assertEqual(self.persisted.definitions["Combat"].terms, ["new"])
        self.assertEqual(self.editor.status.text(), "All changes saved")

    def test_conflicting_saved_fragments_keep_draft_and_offer_reload(self):
        self.open_label("Looks")
        self.set_fragments("new")
        self.persisted.definitions["Looks"].terms = ["external"]
        self.controller.flush()
        self.assertIn("changed while", self.editor.status.text())
        self.assertEqual(self.persisted.definitions["Looks"].terms, ["external"])
        self.assertEqual(self.editor.terms_edit.draft.preview_terms(), ["new"])
        with patch("mod_manager.ui.dialogs.prompts.ask_yes_no", return_value=False):
            self.editor.reload.click()
        self.assertEqual(self.editor.terms_edit.draft.preview_terms(), ["new"])
        with patch("mod_manager.ui.dialogs.prompts.ask_yes_no", return_value=True):
            self.editor.reload.click()
        self.assertEqual(self.editor.terms_edit.draft.preview_terms(), ["external"])

    def test_saved_rename_updates_the_active_filter(self):
        self.window.label_filter_var.set("Combat")
        self.open_label("Combat")
        self.editor.name_edit.setText("Renamed")
        self.editor.name_edit.textEdited.emit("Renamed")
        self.controller.save()
        self.assertEqual(self.window.label_filter_var.get(), "Renamed")
        self.assertEqual(self.persisted.members("combat.pak"), ("Renamed",))

    def test_automatic_assignment_opens_the_label_editor(self):
        with patch.object(self.window, "_run_action") as run:
            self.window._change_label_selected("looks", remove=True)
        run.assert_not_called()
        self.assertEqual(self.window.workspace.current_page, "labels")
        self.assertEqual(self.controller.selected, "Looks")

    def test_detail_new_label_rejects_duplicates_and_existing_assignment_is_separate(self):
        self.select_mod_rows(0)
        with patch("mod_manager.ui.dialogs.prompts.choose_text", return_value=(" combat ", True)), patch(
            "mod_manager.ui.dialogs.prompts.show_error") as error, patch.object(self.window, "_change_label_selected") as change:
            self.window._add_label_selected()
        error.assert_called_once()
        change.assert_not_called()
        with patch("mod_manager.ui.dialogs.prompts.choose_item", return_value=("Combat", True)) as choose, patch.object(
            self.window, "_change_label_selected") as change:
            self.window._assign_existing_label()
        self.assertEqual(choose.call_args.args[3], ["Combat"])
        change.assert_called_once_with("Combat")

    def test_label_menu_dismissal_and_refresh_release_and_invalidate_actions(self):
        names = ("Combat", "Looks")
        self.window._show_label_choices(names, self.window.mapToGlobal(QtCore.QPoint()))
        menu = self.window._label_choices_menu
        action = menu.actions()[0]
        self.window.refresh_mods()
        action.trigger()
        self.assertEqual(self.window.label_filter_var.get(), "")
        self.qt_app.processEvents()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        self.assertIsNone(self.window._label_choices_menu)
        self.window._show_label_choices(names, self.window.mapToGlobal(QtCore.QPoint()))
        self.window._label_choices_menu.close()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        self.assertIsNone(self.window._label_choices_menu)

    def test_multi_label_details_filter_each_label_without_selecting_other_mods(self):
        self.persisted.assignments["combat.pak"].append("Looks")
        self.persisted.definitions["Looks"].terms = ["pak"]
        self.window.refresh_mods()
        self.select_mod_rows(0)
        buttons = {button.text(): button for button in self.window.detail_frame.findChildren(QtWidgets.QPushButton) if not button.isHidden()}
        self.assertIn("Combat", buttons)
        self.assertIn("Looks", buttons)
        self.window.show()
        self.qt_app.processEvents()
        for name in ("Combat", "Looks"):
            self.assertGreater(buttons[name].width(), 0)
            self.assertGreaterEqual(buttons[name].height(), buttons[name].minimumSizeHint().height())
        buttons["Looks"].click()
        self.assertEqual(self.window.label_filter_var.get(), "Looks")
        self.assertLessEqual(len(self.window._selected_mod_names()), 1)

    def test_tile_badges_offer_each_label_and_an_overflow_menu(self):
        for index in range(8):
            name = f"Long label {index}"
            self.persisted.definitions[name] = LabelDefinition()
            self.persisted.assignments["combat.pak"].append(name)
        self.window.refresh_mods()
        self.window._set_view_mode("tiles")
        index = self.window.mods_model.index(0, 0)
        option = QtWidgets.QStyleOptionViewItem()
        option.font = self.window.font()
        option.rect = QtCore.QRect(0, 0, tokens.TILE_SIZE_MAX, tokens.TILE_SIZE_MAX)
        badges = self.window.tile_delegate._label_badges(option, index)
        self.assertTrue(any(label is None for _rect, _text, label in badges))
        for rect, _text, label in badges:
            tooltip = self.window.tile_delegate._tooltip_for_pos(option, index, rect.center())
            self.assertEqual(self.window.tile_delegate._label_for_pos(option, index, rect.center()), label or "")
            if label is None:
                self.assertIn("Long label 7", tooltip)
        names = self.window.tile_delegate._labels(index)
        self.window._show_label_choices(names, self.window.mapToGlobal(QtCore.QPoint()))
        menu = self.window._label_choices_menu
        self.assertEqual([action.text() for action in menu.actions()], list(names))
        menu.actions()[-1].trigger()
        self.assertEqual(self.window.label_filter_var.get(), names[-1])


@unittest.skipUnless(qt_available(), "PySide6 is not installed")
class AdaptiveFiltersTests(WindowTestCase):
    def test_filters_use_available_width_without_focus_and_keep_it_on_focus_loss(self):
        self.window.resize(tokens.DEFAULT_WIDTH * 2, tokens.DEFAULT_HEIGHT)
        self.window.show()
        self.qt_app.processEvents()
        box = self.window.search_box
        width = box.width()
        self.assertGreater(width, box.minimumWidth())
        box.lineEdit().setFocus()
        self.window.order_box.setFocus()
        self.qt_app.processEvents()
        self.assertEqual(box.width(), width)
        self.window.resize(tokens.MIN_WIDTH, tokens.MIN_HEIGHT)
        self.qt_app.processEvents()
        self.assertLess(box.width(), width)

    def test_popup_fits_long_values_inside_the_screen_and_applies_selection(self):
        self.window.show()
        self.qt_app.processEvents()
        box = self.window.label_filter_box
        name = "Long label " * 20
        with QtCore.QSignalBlocker(box):
            box.addItem(name)
        box.showPopup()
        self.qt_app.processEvents()
        popup = box.view().window()
        self.assertGreater(popup.width(), box.width())
        self.assertTrue(box.screen().availableGeometry().contains(popup.geometry()))
        with patch.object(self.window, "refresh_mods") as refresh:
            box.setCurrentIndex(box.findText(name))
            box.activated.emit(box.currentIndex())
        self.assertEqual(self.window.label_filter_var.get(), name.strip())
        refresh.assert_called_once()
        box.hidePopup()

    def test_large_font_preview_stays_in_the_settings_field_column(self):
        self.window._navigate("settings")
        self.window.resize(tokens.DEFAULT_WIDTH * 2, tokens.DEFAULT_HEIGHT)
        self.window.show()
        self.window.settings.fields["gui_font_size"].setText("48")
        self.qt_app.processEvents()
        self.window.resize(tokens.MIN_WIDTH, tokens.MIN_HEIGHT)
        self.qt_app.processEvents()
        preview = self.window.settings.font_preview
        section = self.window.settings.form.sections["Appearance"]
        self.assertTrue(preview.wordWrap())
        self.assertTrue(preview.alignment() & QtCore.Qt.AlignLeft)
        self.assertTrue(preview.hasHeightForWidth())
        self.assertGreaterEqual(preview.height(), preview.heightForWidth(preview.width()))
        self.assertLessEqual(preview.mapTo(section, QtCore.QPoint()).x() + preview.width(), section.width())
        field = self.window.settings.fields["gui_font_family"]
        self.assertEqual(preview.mapTo(section, QtCore.QPoint()).x(), field.mapTo(section, QtCore.QPoint()).x())
        theme_row = self.window.settings.accent_badge.parentWidget()
        self.assertLess(preview.mapTo(section, QtCore.QPoint()).y() + preview.height(), theme_row.mapTo(section, QtCore.QPoint()).y())
