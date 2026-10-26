from __future__ import annotations

from unittest.mock import patch

from PySide6 import QtCore, QtTest, QtWidgets

from mod_manager.models import ModFile
from mod_manager.preset_plan import PresetChange, PresetPlan, plan_presets
from mod_manager.ui.widgets.plan_review import PlanTree
from mod_manager.ui.widgets.preset_review import PresetReview
from tests.qt_support import dispose
from tests.window_fixture import WindowTestCase, mod_item


class InterfaceUpdatesTests(WindowTestCase):
    def test_preset_review_has_action_tables_without_preset_names_and_one_scroll(self):
        first = mod_item("Combat.pak", installed=True)
        second = mod_item("Textures.pak")
        second.files = (ModFile(second.src, second.dest, False),
                        ModFile(second.src.with_suffix(".utoc"), second.dest.with_suffix(".utoc"), False))
        folder = mod_item("Folder.with.dots", is_dir=True)
        changes = (PresetChange("Private preset A", first.name, "uninstall", first),
                   PresetChange("Private preset B", second.name, "install", second),
                   PresetChange("Private preset B", folder.name, "install", folder),
                   PresetChange("Private preset B", "Missing.pak", "missing"))
        dialog = PresetReview(self.window, PresetPlan((), (), changes))
        try:
            dialog.show()
            self.qt_app.processEvents()
            model = dialog.table.model()
            self.assertEqual(model.headings, [0, 3, 7])
            self.assertEqual(model.rows[1], ("Status", "Name", "Extension"))
            self.assertEqual(model.rows[2], ("Installed", "Combat", ".pak"))
            self.assertEqual(model.rows[5], ("Not installed", "Textures", ".pak, .utoc"))
            self.assertEqual(model.rows[6], ("Not installed", "Folder.with.dots", "Folder"))
            self.assertEqual(model.rows[9], ("Missing from library", "Missing", ".pak"))
            self.assertFalse(any("Private preset" in value for row in model.rows for value in row))
            self.assertEqual(dialog.findChildren(QtWidgets.QTableView), [dialog.table])
            self.assertEqual(dialog.findChildren(QtWidgets.QScrollArea), [])
            for heading in model.headings:
                self.assertEqual(dialog.table.columnSpan(heading, 0), 3)
        finally:
            dispose(dialog)

    def test_large_preset_review_scrolls_to_the_next_operation(self):
        changes = tuple(PresetChange("Hidden", f"Mod_{index}.pak", "install", mod_item(f"Mod_{index}.pak"))
                        for index in range(1000))
        changes += (PresetChange("Another", "Last.pak", "uninstall", mod_item("Last.pak", installed=True)),)
        dialog = PresetReview(self.window, PresetPlan((), (), changes))
        try:
            dialog.show()
            self.qt_app.processEvents()
            view, model = dialog.table, dialog.table.model()
            self.assertGreater(view.verticalScrollBar().maximum(), 0)
            last = model.index(model.rowCount() - 1, 1)
            view.scrollTo(last)
            self.qt_app.processEvents()
            self.assertTrue(view.viewport().rect().intersects(view.visualRect(last)))
            self.assertEqual(last.data(), "Last")
            self.assertEqual(model.rows[model.headings[-1]][0], "Uninstall")
        finally:
            dispose(dialog)

    def test_preset_status_is_the_state_before_each_reviewed_operation(self):
        with patch("mod_manager.preset_plan.load_presets", return_value={"A": ["ui.pak"], "B": ["ui.pak"]}):
            plan = plan_presets(self.window.cfg, ["A", "B"])
        self.assertEqual([(change.action, change.mod.installed) for change in plan.changes],
                         [("install", False), ("unchanged", True)])

    def test_archive_tree_is_fully_expanded_after_each_update(self):
        tree = PlanTree()
        try:
            tree.set_rows([("Archive", "Mod", "nested", "file.pak")])
            index = tree.model().index(0, 0)
            for _ in range(3):
                self.assertTrue(tree.isExpanded(index))
                index = tree.model().index(0, 0, index)
            tree.show()
            tree.setCurrentIndex(tree.model().index(0, 0))
            QtTest.QTest.keyClick(tree, QtCore.Qt.Key_Left)
            self.assertTrue(tree.isExpanded(tree.currentIndex()))
            tree.set_rows([("Library", "Other", "file.utoc")])
            self.assertTrue(tree.isExpanded(tree.model().index(0, 0)))
            self.assertTrue(tree.isExpanded(tree.model().index(0, 0, tree.model().index(0, 0))))
        finally:
            dispose(tree)

    def test_footer_stays_in_place_when_library_content_scrolls(self):
        self.window.resize(880, 560)
        self.window.show()
        self.qt_app.processEvents()
        footer = self.window.mods_actions
        position = footer.mapTo(self.window.mods_tab, QtCore.QPoint())
        self.window.library_scroll.verticalScrollBar().setValue(self.window.library_scroll.verticalScrollBar().maximum())
        self.qt_app.processEvents()
        self.assertEqual(footer.mapTo(self.window.mods_tab, QtCore.QPoint()), position)
        self.assertFalse(self.window.library_scroll.isAncestorOf(footer))
        self.assertLessEqual(position.y() + footer.height(), self.window.mods_tab.height())
