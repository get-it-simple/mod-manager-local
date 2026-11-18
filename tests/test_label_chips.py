from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6 import QtCore, QtGui, QtTest, QtWidgets

from mod_manager import storage
from mod_manager.i18n import t
from mod_manager.labels import AUTOMATIC, LabelDefinition, LabelState, ResolvedLabels
from mod_manager.ui.dialogs.label_choice import LabelChoiceDialog
from mod_manager.ui.label_artwork import import_label_icon, label_icon
from mod_manager.ui.theme import tokens
from mod_manager.ui.widgets.label_chips import chip_content, layout_chips
from tests.qt_support import dispose, qt_app
from tests.window_fixture import WindowTestCase


class LabelArtworkGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def test_any_image_dimensions_import_as_portable_png_and_center_without_cropping(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(storage, "PROFILE_DATA_DIR", Path(directory) / "profiles"):
            for width, height in ((1, 1), (3200, 64), (64, 3200), (37, 83)):
                with self.subTest(size=(width, height)):
                    path = Path(directory) / "source.png"
                    source = QtGui.QImage(width, height, QtGui.QImage.Format_ARGB32)
                    source.fill(QtCore.Qt.red)
                    self.assertTrue(source.save(str(path)))
                    original = path.read_bytes()
                    reference = import_label_icon(str(path))
                    self.assertFalse(Path(reference).is_absolute())
                    self.assertEqual(path.read_bytes(), original)
                    path.unlink()
                    definition = LabelDefinition(icon=reference, icon_only=True)
                    icon = label_icon(definition)
                    pixmap = icon.pixmap(tokens.LABEL_ICON_PREVIEW_SIZE, tokens.LABEL_ICON_PREVIEW_SIZE)
                    self.assertFalse(pixmap.isNull())
                    rendered = pixmap.toImage()
                    points = [(x, y) for x in range(rendered.width()) for y in range(rendered.height())
                              if rendered.pixelColor(x, y).alpha() > 0 and rendered.pixelColor(x, y).red() > 0]
                    self.assertTrue(points)
                    left, right = min(x for x, _y in points), max(x for x, _y in points)
                    top, bottom = min(y for _x, y in points), max(y for _x, y in points)
                    self.assertLessEqual(abs(left + right - rendered.width() + 1), 1)
                    self.assertLessEqual(abs(top + bottom - rendered.height() + 1), 1)
                    if width > height:
                        self.assertGreater(right - left, bottom - top)
                    elif height > width:
                        self.assertGreater(bottom - top, right - left)
                    text, _icon, _extra = chip_content("Full name", definition, QtGui.QFontMetrics(QtGui.QFont()))
                    self.assertEqual(text, "")
            missing = LabelDefinition(icon="label-icons/" + "a" * 64 + ".png", icon_only=True)
            text, icon, _extra = chip_content("Fallback name", missing, QtGui.QFontMetrics(QtGui.QFont()))
            self.assertEqual(text, "Fallback name")
            self.assertTrue(icon.isNull())
            bad = Path(directory) / "bad.png"
            bad.write_bytes(b"not an image")
            with self.assertRaises(ValueError):
                import_label_icon(str(bad))

    def test_assignment_selector_has_chevron_searches_substrings_and_rejects_unknown_names(self):
        dialog = LabelChoiceDialog(None, ["Combat", "Visual overhaul", "UI"])
        self.addCleanup(dispose, dialog)
        dialog.show()
        self.app.processEvents()
        from mod_manager.ui.widgets.select import SelectBox

        self.assertIsInstance(dialog.choice, SelectBox)
        completer = dialog.choice.completer()
        completer.setCompletionPrefix("OVER")
        self.assertEqual(completer.completionCount(), 1)
        self.assertEqual(completer.currentCompletion(), "Visual overhaul")
        dialog.choice.setEditText("invented label")
        self.assertFalse(dialog.buttons.button(QtWidgets.QDialogButtonBox.Ok).isEnabled())
        dialog.accept()
        self.assertNotEqual(dialog.result(), QtWidgets.QDialog.Accepted)
        dialog.choice.setEditText("visual OVERHAUL")
        self.assertTrue(dialog.buttons.button(QtWidgets.QDialogButtonBox.Ok).isEnabled())
        self.assertEqual(dialog.selected_label, "Visual overhaul")


class LabelChipWindowTests(WindowTestCase):
    def setUp(self):
        super().setUp()
        self.state = LabelState(
            {"Alpha": LabelDefinition(), "Beta": LabelDefinition()},
            {mod.name: ["Alpha", "Beta"] for mod in self.mods})
        runner = patch("mod_manager.ui.app.mods_view", side_effect=lambda *_args, **_kwargs: (
            self.mods, self.mods, 1, 1, ResolvedLabels(self.state, [mod.name for mod in self.mods])))
        runner.start()
        self.addCleanup(runner.stop)
        self.window.refresh_mods()
        self.window._set_details_visible(False)
        self.window.resize(tokens.DEFAULT_WIDTH, tokens.DEFAULT_HEIGHT)
        self.window.show()
        self.qt_app.processEvents()

    def badges(self, view, delegate):
        index = self.window.mods_model.index(0, tokens.MOD_LABEL_COLUMN if view is self.window.mods_table else 0)
        option = QtWidgets.QStyleOptionViewItem()
        option.initFrom(view)
        option.rect = view.visualRect(index)
        option.font = view.font()
        option.fontMetrics = view.fontMetrics()
        return index, delegate._label_badges(option, index)

    def test_table_and_tiles_activate_labels_and_shift_keeps_other_filters_without_toggling_mod(self):
        for mode in ("list", "tiles"):
            with self.subTest(mode=mode):
                self.window._set_view_mode(mode)
                self.window._set_details_visible(False)
                self.qt_app.processEvents()
                view = self.window._current_mod_view()
                delegate = self.window.label_delegate if mode == "list" else self.window.tile_delegate
                self.window.filters.clear()
                self.window.filters.add("search", "retained only for shift")
                _index, badges = self.badges(view, delegate)
                self.assertTrue(badges)
                name = badges[0][2]
                with patch.object(self.window, "_toggle_selected_mods") as toggle:
                    QtTest.QTest.mouseClick(view.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, badges[0][0].center())
                    self.assertEqual(self.window.filters.labels, (name,))
                    self.assertEqual(self.window.filters.queries, ())
                    self.window.filters.add("search", "retained for shift")
                    _index, badges = self.badges(view, delegate)
                    QtTest.QTest.mouseClick(view.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.ShiftModifier, badges[1][0].center())
                    self.assertEqual(set(self.window.filters.labels), {"Alpha", "Beta"})
                    self.assertIn("retained for shift", self.window.filters.queries)
                    toggle.assert_not_called()
                self.assertTrue(self.mods[0].installed)

    def test_chip_hover_changes_rendered_surface(self):
        view = self.window.mods_table
        _index, badges = self.badges(view, self.window.label_delegate)
        rect = badges[0][0]
        before = view.viewport().grab(rect).toImage()
        pos = rect.center()
        event = QtGui.QMouseEvent(QtCore.QEvent.MouseMove, QtCore.QPointF(pos),
                                 QtCore.QPointF(view.viewport().mapToGlobal(pos)),
                                 QtCore.Qt.NoButton, QtCore.Qt.NoButton, QtCore.Qt.NoModifier)
        QtWidgets.QApplication.sendEvent(view.viewport(), event)
        self.qt_app.processEvents()
        after = view.viewport().grab(rect).toImage()
        self.assertNotEqual(before, after)

    def test_long_single_label_uses_available_width_and_multiple_labels_offer_overflow(self):
        metrics = self.window.fontMetrics()
        name = "A substantially longer label name"
        wide = layout_chips([name], {}, QtCore.QRect(0, 0, 500, 32), metrics)
        self.assertEqual(wide[0][1], name)
        narrow = layout_chips([name], {}, QtCore.QRect(0, 0, 110, 32), metrics)
        self.assertNotEqual(narrow[0][1], name)
        self.assertTrue(narrow[0][1].endswith("…"))
        many = layout_chips([name, "Other", "Third"], {}, QtCore.QRect(0, 0, 140, 32), metrics)
        self.assertTrue(any(label is None for _rect, _text, label in many))
        for rect, _text, _label in many:
            self.assertGreater(rect.width(), 0)
            self.assertLessEqual(rect.right(), 139)

    def test_assign_is_disabled_in_details_and_context_menu_without_manual_labels(self):
        self.state.definitions = {"Auto": LabelDefinition(AUTOMATIC, ["pak"])}
        self.state.assignments = {}
        self.window._set_details_visible(True)
        self.window.refresh_mods()
        self.select_mod_rows(0)
        assignments = [button for button in self.window.detail_frame.findChildren(QtWidgets.QPushButton)
                       if button.isVisible() and button.toolTip() == t("assign_label")]
        self.assertTrue(assignments)
        self.assertTrue(all(not button.isEnabled() for button in assignments))
        view = self.window.mods_table
        self.window.mod_menu.open(view, view.visualRect(self.window.mods_model.index(0, 1)).center())
        action = next(action for action in self.window.mod_menu.menu.actions() if action.data() == "add_label")
        self.assertFalse(action.isEnabled())
        with patch("mod_manager.ui.dialogs.prompts.choose_label") as choose:
            self.window._assign_existing_label()
        choose.assert_not_called()

    def test_compact_sidebar_hides_add_hit_zone_and_count_but_shift_still_works(self):
        sidebar = self.window.workspace.labels_list
        self.window.resize(tokens.MIN_WIDTH, tokens.MIN_HEIGHT)
        self.qt_app.processEvents()
        self.assertTrue(sidebar.delegate.compact)
        index = sidebar.model().index(0, 0)
        rect = sidebar.visualRect(index)
        pos = rect.center()
        event = QtGui.QMouseEvent(QtCore.QEvent.MouseMove, QtCore.QPointF(pos),
                                 QtCore.QPointF(sidebar.viewport().mapToGlobal(pos)),
                                 QtCore.Qt.NoButton, QtCore.Qt.NoButton, QtCore.Qt.NoModifier)
        QtWidgets.QApplication.sendEvent(sidebar.viewport(), event)
        self.assertFalse(sidebar.add_button.isVisible())
        self.assertIn("Matching mods: 2", index.data(QtCore.Qt.ToolTipRole))
        self.window.filters.clear()
        QtTest.QTest.mouseClick(sidebar.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier,
                               sidebar.delegate.add_rect(rect).center())
        self.assertEqual(self.window.filters.labels, (index.data(),))
        QtTest.QTest.mouseClick(sidebar.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.ShiftModifier, rect.center())
        self.assertEqual(self.window.filters.labels, ())

    def test_state_column_is_compact_and_last_managed_fits_with_and_without_focus(self):
        view = self.window.mods_table
        self.assertLessEqual(view.columnWidth(0), 32)
        index = self.window.mods_model.index(0, 3)
        self.assertEqual(index.data(QtCore.Qt.ToolTipRole), "2026-01-01 10:00:00")
        for focused in (False, True):
            view.setCurrentIndex(index)
            view.setFocus() if focused else view.clearFocus()
            self.qt_app.processEvents()
            option = QtWidgets.QStyleOptionViewItem()
            option.initFrom(view)
            view.itemDelegateForIndex(index).initStyleOption(option, index)
            option.rect = view.visualRect(index)
            if focused:
                option.state |= QtWidgets.QStyle.State_HasFocus
            text_rect = view.style().subElementRect(QtWidgets.QStyle.SE_ItemViewItemText, option, view)
            self.assertGreaterEqual(text_rect.width(), option.fontMetrics.horizontalAdvance(index.data()))
