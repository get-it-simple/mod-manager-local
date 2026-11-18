from __future__ import annotations

from dataclasses import replace
from unittest.mock import patch

from PySide6 import QtCore, QtGui, QtTest, QtWidgets

from mod_manager.models import OperationItem, OperationResult
from mod_manager.progress import mod_activity
from mod_manager.ui.theme import tokens
from tests.gui_background import DeferredRunner
from tests.test_motion_and_loading import advance_motion
from tests.window_fixture import WindowTestCase


class UiRefinementTests(WindowTestCase):

    def test_fragment_text_stays_visible_after_painting_its_mode_button(self):
        from mod_manager.ui.widgets.label_fragments import FragmentDraft, FragmentEditor

        self.show_window()
        editor = FragmentEditor(self.window)
        editor.resize(tokens.RENAME_DIALOG_WIDTH, editor.sizeHint().height())
        editor.bind(FragmentDraft(["Visible fragment"]))
        editor.show()
        self.qt_app.processEvents()
        index = editor.model.index(0, 1)
        delegate = editor.view.itemDelegate()
        option = QtWidgets.QStyleOptionViewItem()
        option.initFrom(editor.view)
        option.widget = editor.view
        option.rect = QtCore.QRect(QtCore.QPoint(), delegate.sizeHint(option, index))
        image = QtGui.QImage(option.rect.size(), QtGui.QImage.Format_ARGB32)
        image.fill(editor.view.palette().base().color())
        painter = QtGui.QPainter(image)
        delegate.paint(painter, option, index)
        painter.end()
        text = delegate.chip_rect(option.rect).adjusted(
            tokens.ICON_BUTTON_SIZE + tokens.SPACE_SM + delegate.number_width(0), 0,
            -tokens.ICON_BUTTON_SIZE * 2 - tokens.SPACE_SM, 0)
        foreground = option.palette.text().color()
        self.assertTrue(any(image.pixelColor(x, y) == foreground
                            for x in range(text.left(), text.right()) for y in range(text.top(), text.bottom())))

    def test_trash_table_paints_retention_metadata_without_operation_role_collisions(self):
        from datetime import datetime, timedelta, timezone
        from pathlib import Path
        from mod_manager.trash import TrashEntry

        self.show_window()
        view = self.window.trash.view
        now = datetime.now(timezone.utc)
        entry = TrashEntry(Path("synthetic"), "synthetic", {
            "name": "Synthetic.pak", "profile_name": "Synthetic", "files": [],
            "deleted_at": now.isoformat(), "expires_at": (now + timedelta(days=14)).isoformat()})
        view.set_entries([entry])
        failures = []
        with patch("sys.excepthook", side_effect=lambda kind, error, trace: failures.append(error)):
            image = view.table.grab()
        self.assertFalse(image.isNull())
        self.assertEqual(failures, [])
    def show_window(self):
        self.window.resize(tokens.DEFAULT_WIDTH, tokens.DEFAULT_HEIGHT)
        self.window.show()
        for _step in range(3):
            self.qt_app.processEvents()
        advance_motion(self.window)

    def test_quick_labels_update_only_changed_rows_and_keep_scroll_after_layout(self):
        self.show_window()
        view = self.window.workspace.labels_list
        entries = [(f"Label {number:03}", "manual", 100 - number, False) for number in range(100)]
        view.update_labels(entries, self.window.theme.system_accent)
        self.qt_app.processEvents()
        self.qt_app.processEvents()
        view.verticalScrollBar().setValue(view.verticalScrollBar().maximum() // 2)
        scroll = view.verticalScrollBar().value()
        unchanged = QtCore.QPersistentModelIndex(view.model().index(40, 0))
        resets = QtTest.QSignalSpy(view.model().modelReset)
        changes = QtTest.QSignalSpy(view.model().dataChanged)
        entries[60] = (*entries[60][:3], True)
        view.update_labels(entries, self.window.theme.system_accent)
        self.qt_app.processEvents()
        self.qt_app.processEvents()
        self.assertGreater(scroll, 0)
        self.assertEqual(view.verticalScrollBar().value(), scroll)
        self.assertEqual(resets.count(), 0)
        self.assertTrue(unchanged.isValid())
        self.assertEqual(unchanged.data(), "Label 040")
        self.assertTrue(all(changes.at(index)[0].row() == 60 for index in range(changes.count())))
        previous = changes.count()
        view.update_labels(entries, self.window.theme.system_accent)
        self.qt_app.processEvents()
        self.assertEqual(changes.count(), previous)
        entries[60] = (entries[60][0], "manual", 999, True)
        entries.insert(0, entries.pop(60))
        view.update_labels(entries, self.window.theme.system_accent)
        self.qt_app.processEvents()
        self.qt_app.processEvents()
        self.assertEqual(view.model().index(0, 0).data(), "Label 060")
        self.assertEqual(view.verticalScrollBar().value(), scroll)
        self.assertTrue(unchanged.isValid())
        entries.insert(0, ("Added label", "automatic", 1000, False))
        view.update_labels(entries, self.window.theme.system_accent)
        self.qt_app.processEvents()
        self.qt_app.processEvents()
        self.assertEqual(view.verticalScrollBar().value(), scroll)
        self.assertEqual(resets.count(), 0)

    def test_overlay_scrollbars_never_reserve_space_and_follow_native_values(self):
        self.show_window()
        area = QtWidgets.QScrollArea(self.window)
        area.resize(tokens.LABEL_LIST_DEFAULT_WIDTH, tokens.LABEL_EDITOR_LIST_HEIGHT)
        content = QtWidgets.QWidget()
        content.resize(area.width() * 3, area.height() * 4)
        area.setWidget(content)
        area.show()
        for _step in range(3):
            self.qt_app.processEvents()
        bars = area._overlay_scrollbars
        self.assertIsNotNone(bars)
        self.assertTrue(bars.vertical.isVisible())
        self.assertTrue(bars.horizontal.isVisible())
        expected = area.size() - QtCore.QSize(area.frameWidth() * 2, area.frameWidth() * 2)
        self.assertEqual(area.viewport().size(), expected)
        original = area.viewport().geometry()
        self.qt_app.sendEvent(bars.vertical, QtCore.QEvent(QtCore.QEvent.Enter))
        advance_motion(self.window)
        self.assertEqual(bars.vertical.expansion, 1.0)
        self.assertEqual(area.viewport().geometry(), original)
        bars.vertical.setValue(bars.vertical.maximum() // 2)
        self.assertEqual(area.verticalScrollBar().value(), bars.vertical.value())
        area.horizontalScrollBar().setValue(area.horizontalScrollBar().maximum() // 2)
        self.assertEqual(bars.horizontal.value(), area.horizontalScrollBar().value())
        self.window.motion.set_enabled(False)
        bars.vertical.setSliderDown(True)
        self.qt_app.sendEvent(bars.vertical, QtCore.QEvent(QtCore.QEvent.Leave))
        self.assertEqual(bars.vertical.expansion, 1.0)
        bars.vertical.setSliderDown(False)
        self.assertEqual(bars.vertical.expansion, 0.0)
        self.assertEqual(area.viewport().geometry(), original)
        area.hide()

    def test_nonblocking_multi_mod_completion_removes_detail_cover_without_reselection(self):
        self.show_window()
        self.select_mod_rows(0, 1)
        selected = self.window._selected_mod_names()
        deferred = DeferredRunner()
        self.window.runner.background = deferred.background

        def work():
            results = tuple(OperationItem(name, "installed", True, "OK") for name in selected)
            with mod_activity("progress_installing", tuple(selected)) as progress:
                self.mods[:] = [replace(mod, installed=True) for mod in self.mods]
                progress.extend(results)
            return OperationResult(results)

        self.window._run_action("Synthetic batch", work, mod_names=tuple(selected))
        self.assertFalse(self.window.runner.busy)
        deferred.complete()
        self.assertEqual(self.window._selected_mod_names(), selected)
        frame = self.window.activity._detail_frame
        self.assertIsNotNone(frame)
        self.assertIsNotNone(frame.finished_at)
        self.window.activity.animation.setCurrentTime(tokens.OPERATION_CYCLE_MS * 4)
        self.qt_app.processEvents()
        self.assertIsNone(self.window.activity._detail_frame)
        self.assertTrue(self.window.activity.detail_cover.isHidden())
        self.assertEqual(self.window._selected_mod_names(), selected)
        labels = [label.text() for label in self.window.detail_frame.findChildren(QtWidgets.QLabel)]
        self.assertIn("2", labels)

    def test_rename_toolbar_is_single_selection_and_cancel_has_no_effect(self):
        self.select_mod_rows(0, 1)
        self.assertFalse(self.window.mods_actions.button("rename_mod").isEnabled())
        self.select_mod_rows(0)
        self.assertTrue(self.window.mods_actions.button("rename_mod").isEnabled())
        with patch("mod_manager.ui.dialogs.prompts.choose_mod_name", return_value=("", False)) as choose:
            self.window.mods_actions.button("rename_mod").click()
        choose.assert_called_once()
        self.assertEqual(self.window._selected_mod_names(), ["combat.pak"])

    def test_active_buttons_and_label_rows_advertise_their_action_with_a_cursor(self):
        self.show_window()
        button = self.window.mods_toolbar.button("import_files")
        self.assertEqual(button.cursor().shape(), QtCore.Qt.PointingHandCursor)
        button.setEnabled(False)
        self.assertEqual(button.cursor().shape(), QtCore.Qt.ArrowCursor)
        view = self.window.workspace.labels_list
        index = view.model().index(0, 0)
        point = view.visualRect(index).center()
        event = QtGui.QMouseEvent(QtCore.QEvent.MouseMove, QtCore.QPointF(point), QtCore.QPointF(view.viewport().mapToGlobal(point)),
                                 QtCore.Qt.NoButton, QtCore.Qt.NoButton, QtCore.Qt.NoModifier)
        self.qt_app.sendEvent(view.viewport(), event)
        self.assertEqual(view.viewport().cursor().shape(), QtCore.Qt.PointingHandCursor)
        self.assertEqual(view.add_button.property("iconName"), "add")
        self.assertTrue(view.add_button.isVisible())
