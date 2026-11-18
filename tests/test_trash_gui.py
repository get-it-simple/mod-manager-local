from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from PySide6 import QtCore, QtGui, QtTest, QtWidgets

from tests.cli_support import CliEnvironment
from tests.gui_background import inline_background
from tests.qt_support import dispose, qt_app
from mod_manager import storage
from mod_manager.imports import set_archive_root
from mod_manager.labels import LabelDefinition, LabelState
from mod_manager.storage_policy import storage_policy
from mod_manager.trash import list_entries


class TrashGuiTests(CliEnvironment, unittest.TestCase):
    def _trash_selected(self, names=("sample.pak",)):
        self.window.refresh_all()
        self.window._select_mod_names(list(names))
        with patch("mod_manager.ui.dialogs.prompts.ask_yes_no", return_value=True):
            self.window._delete_selected_mods()
        self.window._navigate("trash")
        self.window.resize(1200, 750)
        self.window.show()
        self.app.processEvents()
        return self.window.trash.view

    def test_table_fills_viewport_and_name_receives_extra_width(self):
        view = self._trash_selected()
        header = view.table.horizontalHeader()
        self.assertEqual(header.sectionResizeMode(0), QtWidgets.QHeaderView.Stretch)
        self.assertFalse(header.stretchLastSection())
        before = [view.table.columnWidth(column) for column in range(view.model.columnCount())]
        self.window.resize(1450, 750)
        self.app.processEvents()
        after = [view.table.columnWidth(column) for column in range(view.model.columnCount())]
        self.assertGreater(after[0], before[0])
        self.assertEqual(after[1:], before[1:])
        self.assertLessEqual(abs(sum(after) - view.table.viewport().width()), 1)

    def test_context_menu_restores_in_both_views_and_does_not_create_missing_folders(self):
        for mode in ("list", "tiles"):
            with self.subTest(mode=mode):
                view = self._trash_selected()
                view.set_mode(mode)
                self.app.processEvents()
                target = view.tiles if mode == "tiles" else view.table
                context = self.window.trash.context_menu
                context.open(target, target.visualRect(view.model.index(0, 0)).center())
                actions = {action.data(): action for action in context.menu.actions()}
                self.assertEqual(set(actions), {"restore", "delete", "folder"})
                self.assertTrue(actions["restore"].isEnabled())
                folder = view.selected_entries()[0].path / "payload"
                with patch("mod_manager.ui.controllers.trash_context_menu.open_folder", return_value=(True, "Opened")) as opened:
                    actions["folder"].trigger()
                opened.assert_called_once_with(str(folder), create=False)
                context.open(target, target.visualRect(view.model.index(0, 0)).center())
                next(action for action in context.menu.actions() if action.data() == "restore").trigger()
                self.assertEqual((self.source / "sample.pak").read_bytes(), b"sample.pak")
                self.assertFalse((self.game / "sample.pak").exists())

    def test_context_menu_preserves_multiple_selection_and_permanent_delete_confirmation(self):
        self.add_mods("other.pak")
        view = self._trash_selected(("sample.pak", "other.pak"))
        view.table.selectAll()
        identifiers = {entry.identifier for entry in view.selected_entries()}
        context = self.window.trash.context_menu
        context.open(view.table, view.table.visualRect(view.model.index(0, 0)).center())
        self.assertEqual({entry.identifier for entry in view.selected_entries()}, identifiers)
        actions = {action.data(): action for action in context.menu.actions()}
        self.assertNotIn("folder", actions)
        with patch("mod_manager.ui.dialogs.prompts.ask_yes_no", return_value=False) as asked:
            actions["delete"].trigger()
        asked.assert_called_once()
        self.assertEqual(len(list_entries(self.cfg)), 2)
        context.open(view.table, view.table.visualRect(view.model.index(0, 0)).center())
        with patch("mod_manager.ui.dialogs.prompts.ask_yes_no", return_value=True):
            next(action for action in context.menu.actions() if action.data() == "delete").trigger()
        self.assertEqual(list_entries(self.cfg), [])

    def test_context_menu_honors_pending_entries_and_refresh_invalidates_actions(self):
        view = self._trash_selected()
        context = self.window.trash.context_menu
        entry = view.entries[0]
        view.pending = {entry.identifier}
        context.open(view.table, view.table.visualRect(view.model.index(0, 0)).center())
        actions = {action.data(): action for action in context.menu.actions()}
        self.assertFalse(actions["restore"].isEnabled())
        self.assertFalse(actions["delete"].isEnabled())
        view.pending = set()
        context.open(view.table, view.table.visualRect(view.model.index(0, 0)).center())
        action = next(action for action in context.menu.actions() if action.data() == "restore")
        context.close()
        with patch.object(self.window.trash, "restore") as restore:
            action.trigger()
        restore.assert_not_called()
        self.assertFalse((self.source / "sample.pak").exists())


    def test_rename_button_updates_real_presets_and_keeps_the_new_mod_selected(self):
        with storage_policy(config=self.cfg):
            storage.save_presets({"Core": ["sample.pak"], "Other": ["sample.pak", "missing.pak"]})
        self.window.refresh_all()
        self.select_mod()
        with patch("mod_manager.ui.dialogs.prompts.choose_mod_name", return_value=("renamed.pak", True)):
            self.window.mods_actions.button("rename_mod").click()
        self.assertEqual((self.source / "renamed.pak").read_bytes(), b"sample.pak")
        self.assertFalse((self.source / "sample.pak").exists())
        self.assertEqual(self.window._selected_mod_names(), ["renamed.pak"])
        with storage_policy(config=self.cfg):
            self.assertEqual(storage.load_presets(), {"Core": ["renamed.pak"], "Other": ["renamed.pak", "missing.pak"]})
        self.assertEqual(self.window.library.snapshot.presets["Core"], ["renamed.pak"])

    def test_trash_cards_share_selection_and_show_remaining_days_over_the_preview(self):
        self.select_mod()
        with patch("mod_manager.ui.dialogs.prompts.ask_yes_no", return_value=True):
            self.window._delete_selected_mods()
        self.window._navigate("trash")
        view = self.window.trash.view
        view.table.selectRow(0)
        selected = [entry.identifier for entry in view.selected_entries()]
        view.set_mode("tiles")
        self.assertIs(view.stack.currentWidget(), view.tiles)
        self.assertEqual([entry.identifier for entry in view.selected_entries()], selected)
        option = QtWidgets.QStyleOptionViewItem()
        option.initFrom(view.tiles)
        option.rect = QtCore.QRect(QtCore.QPoint(), view.tile_delegate.sizeHint(option, view.model.index(0, 0)))
        badge, text, _action = view.tile_delegate._label_badges(option, view.model.index(0, 0))[0]
        self.assertIn("days left", text)
        image = view.tile_delegate._image_rect(view.tile_delegate._content_rect(option))
        self.assertTrue(image.intersects(badge))
        self.assertTrue(view.toolbar.button("restore").isEnabled())
        view.toolbar.button("restore").click()
        self.assertEqual((self.source / "sample.pak").read_bytes(), b"sample.pak")
        self.assertEqual(view.model.rowCount(), 0)
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def setUp(self):
        super().setUp()
        self.add_mods("sample.pak")
        self.cfg = storage.load_config()
        self.patchers = [
            patch("mod_manager.ui.task_runner.TaskRunner.background", new=inline_background),
            patch("mod_manager.ui.app.QtWindowsDropTarget"),
            patch("mod_manager.ui.controllers.archive_import_controller.QtWindowsDropTarget"),
            patch("mod_manager.ui.dialogs.prompts.review_plan", return_value=True),
        ]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        from mod_manager.ui.app import ModManagerGui
        self.window = ModManagerGui()
        self.addCleanup(dispose, self.window)

    def select_mod(self):
        self.window._select_mod_names(["sample.pak"])

    def test_delete_and_restore_buttons_preserve_real_data_and_metadata(self):
        with storage_policy(config=self.cfg):
            storage.save_label_state(LabelState({"Synthetic": LabelDefinition()}, {"sample.pak": ["Synthetic"]}))
            storage.update_favorites(self.cfg, ["sample.pak"], True)
            storage.save_presets({"Core": ["sample.pak"]})
        self.window.refresh_all()
        self.select_mod()
        with patch("mod_manager.ui.dialogs.prompts.ask_yes_no", return_value=True):
            self.window.mods_actions.button("delete_mods").click()
        self.assertFalse((self.source / "sample.pak").exists())
        self.window._navigate("trash")
        view = self.window.trash.view
        self.assertEqual(view.model.rowCount(), 1)
        self.assertFalse(view.toolbar.button("restore").isEnabled())
        view.table.selectRow(0)
        self.assertTrue(view.toolbar.button("restore").isEnabled())
        view.toolbar.button("restore").click()
        self.assertEqual((self.source / "sample.pak").read_text(), "sample.pak")
        self.assertFalse((self.game / "sample.pak").exists())
        self.assertEqual(view.model.rowCount(), 0)
        with storage_policy(config=self.cfg):
            self.assertEqual(storage.load_label_state().assignments["sample.pak"], ["Synthetic"])
            self.assertEqual(storage.load_presets()["Core"], ["sample.pak"])
            self.assertEqual(storage.load_favorites(self.cfg), {"sample.pak"})

    def test_settings_empty_action_requires_confirmation_and_clears_all_trash(self):
        self.select_mod()
        with patch("mod_manager.ui.dialogs.prompts.ask_yes_no", return_value=False):
            self.window._delete_selected_mods()
        self.assertTrue((self.source / "sample.pak").exists())
        with patch("mod_manager.ui.dialogs.prompts.ask_yes_no", return_value=True):
            self.window._delete_selected_mods()
        entry, = list_entries(self.cfg)
        empty = self.window.settings.trash_toolbar.button("empty")
        with patch("mod_manager.ui.dialogs.prompts.ask_yes_no", return_value=False):
            empty.click()
        self.assertTrue(entry.path.exists())
        with patch("mod_manager.ui.dialogs.prompts.ask_yes_no", return_value=True):
            empty.click()
        self.assertFalse(entry.path.exists())
        self.assertFalse((self.source / "sample.pak").exists())

    def test_refresh_reconciles_manually_removed_trash_payload(self):
        self.select_mod()
        with patch("mod_manager.ui.dialogs.prompts.ask_yes_no", return_value=True):
            self.window._delete_selected_mods()
        self.window._navigate("trash")
        entry, = self.window.trash.view.entries
        (entry.path / entry.data["files"][0]["stored"]).unlink()
        self.window.trash.view.toolbar.button("refresh").click()
        self.assertEqual(self.window.trash.view.entries, [])
        self.assertEqual(self.window.trash.view.model.rowCount(), 0)

    def test_single_mod_archive_with_structure_opens_root_picker_before_publication(self):
        self.window.cfg["archive_preserve_structure"] = True
        archive = self.root / "Pack.zip"
        with ZipFile(archive, "w") as stream:
            stream.writestr("wrapper/data/sub/mod.pak", b"payload")
        self.window._import_paths([archive])
        manager = self.window.archive_import.dialog
        self.assertIsNotNone(manager)
        self.assertFalse((self.source / "Pack").exists())
        browser = manager.browser
        self.assertFalse(browser.root_picker.isHidden())
        self.assertTrue(browser.table.isHidden())
        tree = browser.root_picker
        branch = tree.model.item(0).child(0).child(0)
        tree.tree.setCurrentIndex(branch.index())
        tree.apply.click()
        self.assertEqual(browser.archive.import_root, Path("wrapper/data"))
        self.window.archive_import.commit()
        self.assertEqual((self.source / "Pack/sub/mod.pak").read_bytes(), b"payload")
        self.assertFalse((self.source / "Pack/wrapper").exists())

    def test_archive_native_drop_targets_cover_both_views_and_are_released(self):
        from unittest.mock import Mock

        self.window.cfg["archive_preserve_structure"] = True
        archive = self.root / "Pack.zip"
        with ZipFile(archive, "w") as stream:
            stream.writestr("wrapper/mod.pak", b"payload")
        targets = []

        def target_for(viewport, _callback):
            target = Mock(viewport=viewport)
            targets.append(target)
            return target

        with patch("mod_manager.ui.controllers.archive_import_controller.QtWindowsDropTarget",
                   side_effect=target_for) as create:
            self.window._import_paths([archive])
            dialog = self.window.archive_import.dialog
            self.assertIs(create.call_args_list[0].args[0], dialog.browser.root_picker.tree.viewport())
            dialog.browser.together.setChecked(False)
            targets[0].disable.assert_called_once()
            self.assertIs(create.call_args_list[1].args[0], dialog.browser.table.viewport())
            dialog.browser.together.setChecked(True)
            targets[1].disable.assert_called_once()
            self.assertIs(create.call_args_list[2].args[0], dialog.browser.root_picker.tree.viewport())
            dialog.reject()
        self.assertEqual(len(targets), 3)
        for target in targets:
            target.disable.assert_called_once()
        self.assertIsNone(self.window.archive_import.drop_target)

    def test_copy_recovery_finishes_before_next_queued_install(self):
        from tests.gui_background import DeferredRunner

        self.add_mods("second.pak")
        storage.update_game_profile(self.window.cfg, self.window.cfg["active_game_profile_id"], {"install_mode": "link"})
        storage.save_config(self.window.cfg)
        self.window.refresh_all()
        deferred = DeferredRunner()
        self.window.runner.background = deferred.background
        with patch("mod_manager.links.supports_links", return_value=False), patch(
                "mod_manager.ui.dialogs.prompts.ask_yes_no", return_value=True) as confirm:
            self.window._select_mod_names(["sample.pak"])
            self.window._install_selected_mods()
            self.window._select_mod_names(["second.pak"])
            self.window._install_selected_mods()
            self.assertEqual(len(self.window.runner.commands), 2)
            deferred.complete()
            self.assertEqual(self.window.runner.commands[0].mod_names, ("sample.pak",))
            while deferred.jobs:
                deferred.complete()
        confirm.assert_called_once()
        self.assertEqual(self.window.cfg["install_mode"], "copy")
        for name in ("sample.pak", "second.pak"):
            self.assertEqual((self.game / name).read_bytes(), (self.source / name).read_bytes())
        self.assertEqual(self.window.errors.model.rowCount(), 1)

    def test_queued_install_rechecks_conflicts_after_copy_recovery(self):
        from tests.gui_background import DeferredRunner

        self.add_mods("second.pak", "second.utoc")
        storage.update_game_profile(self.window.cfg, self.window.cfg["active_game_profile_id"],
                                    {"install_mode": "link", "mod_group_extensions": ".pak,.utoc"})
        storage.save_config(self.window.cfg)
        (self.game / "second.utoc").write_bytes(b"existing-user-file")
        self.window.refresh_all()
        deferred = DeferredRunner()
        self.window.runner.background = deferred.background
        with patch("mod_manager.links.supports_links", return_value=False), patch(
                "mod_manager.ui.dialogs.prompts.ask_yes_no", side_effect=[True, False]) as confirm:
            self.window._select_mod_names(["sample.pak"])
            self.window._install_selected_mods()
            self.window._select_mod_names(["second.pak"])
            self.window._install_selected_mods()
            while deferred.jobs:
                deferred.complete()
        self.assertEqual(confirm.call_count, 2)
        self.assertEqual((self.game / "second.utoc").read_bytes(), b"existing-user-file")
        self.assertFalse((self.game / "second.pak").exists())
        self.assertEqual((self.game / "sample.pak").read_bytes(), (self.source / "sample.pak").read_bytes())
