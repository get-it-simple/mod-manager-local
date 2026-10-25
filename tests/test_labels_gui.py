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
        self.patches = [
            patch("mod_manager.ui.controllers.labels_controller.load_label_state", side_effect=lambda: deepcopy(self.persisted)),
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

    def _save(self, state):
        state.validate()
        self.persisted = deepcopy(state)

    def _view(self, _cfg, page, label_filter, search, _order, *_args):
        labels = ResolvedLabels(self.persisted, [mod.name for mod in self.mods])
        items = [mod for mod in self.mods if search.casefold() in mod.name.casefold() and (not label_filter or label_filter in self.persisted.members(mod.name))]
        return items, items[:1], 1, max(1, len(items)), labels

    def open_label(self, name):
        self.window._navigate("labels")
        self.controller._rebuild(name)

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
        self.assertEqual(self.editor.matches_model.stringList(), ["combat.pak"])
        self.editor.mode_box.setCurrentIndex(1)
        self.editor.terms_edit.setPlainText("ui\nUI\n")
        self.assertEqual(self.editor.matches_model.stringList(), ["ui.pak"])
        self.assertEqual(self.persisted.definitions["Combat"].mode, MANUAL)
        self.window._navigate("library")
        self.open_label("Combat")
        self.assertEqual(self.editor.mode_box.currentIndex(), 1)
        self.editor.mode_box.setCurrentIndex(0)
        self.assertEqual(self.editor.matches_model.stringList(), ["combat.pak"])
        self.assertEqual(self.controller.state.definitions["Combat"].terms, ["ui"])
        self.editor.toolbar.button("reset").click()
        self.assertEqual(self.controller.state, self.persisted)

    def test_manual_choices_include_mods_outside_the_current_library_page(self):
        self.open_label("Combat")
        model = self.editor.manual_model
        self.assertEqual(model.names, ["combat.pak", "ui.pak"])
        self.editor.search_edit.setText("UI")
        self.assertEqual(self.editor.manual_proxy.rowCount(), 1)
        index = self.editor.manual_proxy.index(0, 0)
        self.editor.manual_proxy.setData(index, QtCore.Qt.Checked, QtCore.Qt.CheckStateRole)
        self.assertEqual(self.editor.matches_model.stringList(), ["combat.pak", "ui.pak"])
        self.editor.toolbar.button("save").click()
        self.assertEqual(self.persisted.members("ui.pak"), ("Combat", "Looks"))
        self.assertEqual(self.window.current_mod_labels["ui.pak"], "Combat, Looks")

    def test_create_rename_delete_save_and_empty_automatic_validation(self):
        self.open_label("Combat")
        self.controller.add()
        self.editor.name_edit.setText("Fresh")
        self.editor.name_edit.textEdited.emit("Fresh")
        self.editor.mode_box.setCurrentIndex(1)
        with patch("mod_manager.ui.controllers.labels_controller.prompts.show_error") as error:
            self.controller.save()
        self.assertIn("at least one", error.call_args.args[2])
        self.assertNotIn("Fresh", self.persisted.definitions)
        self.editor.terms_edit.setPlainText("pak")
        self.controller.save()
        self.assertIn("Fresh", self.persisted.definitions)
        self.assertEqual(len(self.editor.matches_model.stringList()), 2)
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
        self.editor.terms_edit.setPlainText("ui")
        with patch("mod_manager.ui.controllers.labels_controller.save_label_state", side_effect=PermissionError("locked")), patch("mod_manager.ui.controllers.labels_controller.prompts.show_error") as error:
            self.controller.save()
        self.assertIn("locked", error.call_args.args[2])
        self.assertEqual(self.controller.state.members("ui.pak"), ("Combat", "Looks"))
        self.assertEqual(self.persisted.members("ui.pak"), ("Looks",))

    def test_profile_drafts_are_separate_and_navigation_does_not_save(self):
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

    def test_concurrent_saved_changes_are_reported_instead_of_overwritten(self):
        self.open_label("Combat")
        self.editor.terms_edit.setPlainText("new")
        self.persisted.assignments["ui.pak"] = ["Combat"]
        with patch("mod_manager.ui.controllers.labels_controller.prompts.show_error") as error:
            self.controller.save()
        self.assertIn("changed while", error.call_args.args[2])
        self.assertEqual(self.persisted.assignments["ui.pak"], ["Combat"])

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
    def test_typing_animates_width_and_focus_loss_restores_it(self):
        self.window.resize(tokens.DEFAULT_WIDTH * 2, tokens.DEFAULT_HEIGHT)
        self.window.show()
        self.window.activateWindow()
        self.qt_app.processEvents()
        box = self.window.search_box
        baseline = box.minimumWidth()
        box.lineEdit().setFocus()
        QtTest.QTest.keyClicks(box.lineEdit(), "zz")
        QtTest.QTest.qWait(tokens.FILTER_ANIMATION_MS // 2)
        self.assertGreater(box.minimumWidth(), baseline)
        self.assertLess(box.minimumWidth(), baseline * tokens.FILTER_EXPAND_FACTOR)
        QtTest.QTest.qWait(tokens.FILTER_ANIMATION_MS)
        self.assertLessEqual(box.minimumWidth(), baseline * tokens.FILTER_EXPAND_FACTOR)
        box.completer().popup().hide()
        self.window.order_box.setFocus()
        QtTest.QTest.qWait(tokens.FILTER_ANIMATION_MS * 2)
        self.assertEqual(box.minimumWidth(), baseline)

    def test_expansion_does_not_wrap_other_sections_and_popup_retains_expansion(self):
        self.window.resize(tokens.MIN_WIDTH, tokens.MIN_HEIGHT)
        self.window.show()
        self.qt_app.processEvents()
        section = self.window.mods_toolbar.sections["filter"]
        before = {name: widget.y() for name, widget in self.window.mods_toolbar.sections.items()}
        box = self.window.search_box
        box.lineEdit().setFocus()
        box.lineEdit().textEdited.emit("a")
        QtTest.QTest.qWait(tokens.FILTER_ANIMATION_MS * 2)
        after = {name: widget.y() for name, widget in self.window.mods_toolbar.sections.items()}
        self.assertEqual(after, before)
        popup = box.completer().popup()
        popup.show()
        self.window.filter_expansion._check_focus()
        self.assertIs(self.window.filter_expansion.active, box)
        popup.hide()

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
