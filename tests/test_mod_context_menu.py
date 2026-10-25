from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from PySide6 import QtCore, QtGui, QtTest, QtWidgets

from mod_manager import storage
from mod_manager.models import ModItem
from mod_manager.mods import mod_image_path
from mod_manager.ui.theme import tokens
from tests.window_fixture import WindowTestCase


class ModContextMenuCase(WindowTestCase):
    def setUp(self):
        super().setUp()
        self.use_inline_runner()
        self.window.show()
        self.qt_app.processEvents()

    def open_menu(self, row):
        view = self.window._current_mod_view()
        index = self.window.mods_model.index(row, 0)
        view.scrollTo(index)
        self.qt_app.processEvents()
        pos = view.visualRect(index).center()
        QtTest.QTest.mouseClick(view.viewport(), QtCore.Qt.RightButton, pos=pos)
        event = QtGui.QContextMenuEvent(QtGui.QContextMenuEvent.Mouse, pos, view.viewport().mapToGlobal(pos))
        self.qt_app.sendEvent(view.viewport(), event)
        self.qt_app.processEvents()
        self.assertIsNotNone(self.window.mod_menu.menu)
        self.assertTrue(self.window.mod_menu.menu.isVisible())
        return self.window.mod_menu.menu

    def actions(self, menu):
        return {action.data(): action for action in menu.actions() if not action.isSeparator()}

    def trigger(self, row, key):
        self.actions(self.open_menu(row))[key].trigger()
        self.qt_app.processEvents()


class ModContextMenuViewTests(ModContextMenuCase):
    def detail_text(self):
        return [label.text() for label in self.window.detail_frame.findChildren(QtWidgets.QLabel)]

    def test_right_click_and_dismiss_preserve_selection_and_details_in_both_views(self):
        for mode in ("list", "tiles"):
            with self.subTest(mode=mode):
                self.window._set_view_mode(mode)
                self.select_mod_rows(0)
                before = self.detail_text()
                menu = self.open_menu(1)
                self.assertEqual(self.window._selected_mod_names(), ["combat.pak"])
                self.assertEqual(self.detail_text(), before)
                QtTest.QTest.keyClick(menu, QtCore.Qt.Key_Escape)
                self.qt_app.processEvents()
                self.assertIsNone(self.window.mod_menu.menu)
                self.assertEqual(self.window._selected_mod_names(), ["combat.pak"])
                self.assertEqual(self.detail_text(), before)

    def test_show_details_is_always_available_without_hide_details(self):
        for mode in ("list", "tiles"):
            self.window._set_view_mode(mode)
            for visible in (False, True):
                self.window._set_details_visible(visible)
                for rows in ((), (0,), (1,), (0, 1)):
                    self.select_mod_rows(*rows)
                    for row in (0, 1):
                        with self.subTest(mode=mode, visible=visible, rows=rows, row=row):
                            actions = self.actions(self.open_menu(row))
                            self.assertIn("show_details", actions)
                            self.assertNotIn("hide_details", actions)
                            self.window.mod_menu.close()

    def test_show_details_selects_target_opens_panel_and_saves_visibility(self):
        self.select_mod_rows(0)
        self.window._set_details_visible(False)
        with patch("mod_manager.ui.app.save_config") as save:
            self.trigger(1, "show_details")
        self.assertEqual(self.window._selected_mod_names(), ["ui.pak"])
        self.assertIn("ui.pak", self.detail_text())
        self.assertFalse(self.window.detail_scroll.isHidden())
        self.assertTrue(self.window.details_button.isChecked())
        self.assertTrue(self.window.setting_widgets["mod_details_visible"].isChecked())
        self.assertTrue(save.call_args.args[0]["mod_details_visible"])
        self.assertGreater(self.window.tile_splitter.sizes()[1], 0)

    def test_mouse_click_on_menu_action_runs_after_popup_hides(self):
        self.select_mod_rows(0)
        menu = self.open_menu(1)
        action = self.actions(menu)["show_details"]
        QtTest.QTest.mouseClick(menu, QtCore.Qt.LeftButton, pos=menu.actionGeometry(action).center())
        self.qt_app.processEvents()
        self.assertIsNone(self.window.mod_menu.menu)
        self.assertEqual(self.window._selected_mod_names(), ["ui.pak"])
        self.assertIn("ui.pak", self.detail_text())

    def test_show_details_reopens_hidden_panel_for_single_and_multiple_selected_mods(self):
        for mode in ("list", "tiles"):
            self.window._set_view_mode(mode)
            for rows, heading in (((0,), "combat.pak"), ((0, 1), "2 mods selected")):
                with self.subTest(mode=mode, rows=rows):
                    self.select_mod_rows(*rows)
                    self.window._set_details_visible(False)
                    self.trigger(0, "show_details")
                    self.assertEqual(self.window._selected_mod_names(), [self.mods[row].name for row in rows])
                    self.assertFalse(self.window.detail_scroll.isHidden())
                    self.assertIn(heading, self.detail_text())

    def test_menu_actions_never_turn_detail_controls_into_windows(self):
        class WindowTracker(QtCore.QObject):
            def __init__(self):
                super().__init__()
                self.detached = []

            def eventFilter(self, obj, event):
                if event.type() == QtCore.QEvent.ParentChange and isinstance(obj, QtWidgets.QWidget) and obj.isWindow():
                    self.detached.append(type(obj).__name__)
                return False

        tracker = WindowTracker()
        for mode in ("list", "tiles"):
            self.window._set_view_mode(mode)
            self.select_mod_rows(0)
            for key in ("show_details", "favorite"):
                for widget in self.window.detail_frame.findChildren(QtWidgets.QWidget):
                    widget.installEventFilter(tracker)
                self.trigger(1, key)
        self.assertEqual(tracker.detached, [])

    def test_single_and_mixed_selections_offer_appropriate_state_actions(self):
        for mode in ("list", "tiles"):
            self.window._set_view_mode(mode)
            self.select_mod_rows(0, 1)
            actions = self.actions(self.open_menu(0))
            self.assertTrue({"install", "uninstall", "toggle"}.issubset(actions))
            self.assertNotIn("source", actions)
            self.window.mod_menu.close()
            self.select_mod_rows(0)
            actions = self.actions(self.open_menu(1))
            self.assertIn("install", actions)
            self.assertNotIn("uninstall", actions)
            self.assertNotIn("toggle", actions)
            self.assertIn("source", actions)
            actions = self.actions(self.open_menu(0))
            self.assertIn("uninstall", actions)
            self.assertNotIn("install", actions)

    def test_every_action_and_submenu_has_visible_painted_icons_in_both_themes(self):
        for theme in ("light", "dark"):
            self.window.cfg["gui_theme"] = theme
            self.window._refresh_theme()
            for selected in (False, True):
                self.select_mod_rows(0, 1) if selected else self.select_mod_rows(1)
                menu = self.open_menu(0)
                menus = [menu] + [action.menu() for action in menu.actions() if action.menu()]
                for current in menus:
                    for action in current.actions():
                        if action.isSeparator():
                            continue
                        with self.subTest(theme=theme, action=action.text()):
                            self.assertTrue(action.isIconVisibleInMenu())
                            self.assertFalse(action.icon().isNull())
                            for mode in (QtGui.QIcon.Normal, QtGui.QIcon.Disabled):
                                image = action.icon().pixmap(tokens.ICON_SIZE, tokens.ICON_SIZE, mode).toImage()
                                self.assertTrue(any(image.pixelColor(x, y).alpha() for x in range(image.width()) for y in range(image.height())))
                self.window.mod_menu.close()

    def test_label_submenu_is_disabled_without_labels(self):
        self.select_mod_rows(1)
        action = self.actions(self.open_menu(1))["remove_label"]
        self.assertFalse(action.isEnabled())
        self.assertFalse(action.icon().isNull())

    def test_blank_space_and_busy_state_never_open_menu(self):
        for mode in ("list", "tiles"):
            self.window._set_view_mode(mode)
            view = self.window._current_mod_view()
            self.window.mod_menu.open(view, QtCore.QPoint(-1, -1))
            self.assertIsNone(self.window.mod_menu.menu)
            self.window._set_busy(True)
            try:
                self.window.mod_menu.open(view, view.visualRect(self.window.mods_model.index(0, 0)).center())
                self.assertIsNone(self.window.mod_menu.menu)
            finally:
                self.window._set_busy(False)

    def test_refresh_busy_navigation_and_view_changes_close_and_invalidate_menu(self):
        changes = (
            self.window.refresh_mods,
            lambda: self.window._set_busy(True),
            lambda: self.window._navigate("settings"),
            lambda: self.window._set_view_mode("tiles"),
        )
        for change in changes:
            with self.subTest(change=change):
                self.window._set_busy(False)
                self.window._navigate("library")
                self.window._set_view_mode("list")
                self.select_mod_rows(0)
                menu = self.open_menu(1)
                action = self.actions(menu)["show_details"]
                change()
                self.assertIsNone(self.window.mod_menu.menu)
                self.assertFalse(menu.isVisible())
                action.trigger()
                self.assertEqual(self.window._selected_mod_names(), ["combat.pak"])
                self.qt_app.processEvents()
        self.window._set_busy(False)

    def test_keyboard_context_menu_targets_current_selection(self):
        self.select_mod_rows(0, 1)
        view = self.window._current_mod_view()
        view.selectionModel().setCurrentIndex(self.window.mods_model.index(1, 0), QtCore.QItemSelectionModel.NoUpdate)
        event = QtGui.QContextMenuEvent(QtGui.QContextMenuEvent.Keyboard, QtCore.QPoint())
        self.qt_app.sendEvent(view, event)
        self.assertIsNotNone(self.window.mod_menu.menu)
        self.assertIn("toggle", self.actions(self.window.mod_menu.menu))
        self.assertEqual(self.window._selected_mod_names(), ["combat.pak", "ui.pak"])

    def test_path_actions_use_full_target_paths(self):
        for key, path in (("source", self.mods[1].src), ("destination", self.mods[1].dest)):
            self.select_mod_rows(0)
            with patch("mod_manager.ui.controllers.mod_context_menu.select_in_explorer") as reveal:
                self.trigger(1, key)
            reveal.assert_called_once_with(path)
            self.assertEqual(self.window._selected_mod_names(), ["ui.pak"])

    def test_closed_menu_widgets_are_released(self):
        for _ in range(3):
            menu = self.open_menu(0)
            menu.close()
            self.qt_app.processEvents()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        self.assertEqual(self.window.findChildren(QtWidgets.QMenu), [])


class ModContextMenuOperationTests(ModContextMenuCase):
    def setUp(self):
        super().setUp()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        self.game = self.root / "game"
        self.source.mkdir()
        self.game.mkdir()
        for key, value in (("CONFIG_PATH", self.root / "config.json"), ("LABELS_PATH", self.root / "labels.json"),
                           ("PRESETS_PATH", self.root / "presets.json"), ("PROFILE_DATA_DIR", self.root / "profiles")):
            self.start_patch(f"mod_manager.storage.{key}", value)
        self.start_patch("mod_manager.storage.load_config", return_value=self.window.cfg)
        self.window.cfg["mods_source_dir"] = str(self.source)
        self.window.cfg["game_mods_dir"] = str(self.game)
        for index, old in enumerate(self.mods):
            src, dest = self.source / old.name, self.game / old.name
            src.write_bytes(f"original-{index}".encode())
            if old.installed:
                dest.write_bytes(src.read_bytes())
            self.mods[index] = ModItem(old.name, src, dest, False, old.installed, copy_install=True)
        self.start_patch("mod_manager.ui.app.mods_view", side_effect=self.mods_view)
        self.start_patch("mod_manager.ui.app.load_favorites", side_effect=storage.load_favorites)
        self.window.refresh_mods()

    def start_patch(self, target, *args, **kwargs):
        patcher = patch(target, *args, **kwargs)
        result = patcher.start()
        self.addCleanup(patcher.stop)
        return result

    def mods_view(self, *args):
        for mod in self.mods:
            mod.installed = mod.dest.exists() and mod.dest.read_bytes() == mod.src.read_bytes()
        return self.mods, self.mods, 1, 1, storage.load_labels()

    def test_install_on_unselected_mod_copies_only_its_payload_and_preserves_sources(self):
        for mode in ("list", "tiles"):
            self.window._set_view_mode(mode)
            self.select_mod_rows(0)
            self.trigger(1, "install")
            self.assertEqual(self.mods[1].dest.read_bytes(), b"original-1")
            self.assertEqual(self.mods[0].dest.read_bytes(), b"original-0")
            self.assertEqual(self.window._selected_mod_names(), ["ui.pak"])
            self.trigger(1, "uninstall")
            self.assertFalse(self.mods[1].dest.exists())
        for index, mod in enumerate(self.mods):
            self.assertEqual(mod.src.read_bytes(), f"original-{index}".encode())

    def test_mixed_selection_install_uninstall_and_toggle_apply_to_correct_mods(self):
        self.select_mod_rows(0, 1)
        self.trigger(0, "install")
        self.assertTrue(all(mod.dest.exists() for mod in self.mods))
        self.select_mod_rows(0, 1)
        self.trigger(1, "uninstall")
        self.assertTrue(all(not mod.dest.exists() for mod in self.mods))
        self.select_mod_rows(0, 1)
        self.trigger(0, "toggle")
        self.assertTrue(all(mod.dest.exists() for mod in self.mods))
        self.assertTrue(all(mod.src.exists() for mod in self.mods))

    def test_declining_overwrite_preserves_existing_destination_and_accepting_replaces_it(self):
        self.mods[1].dest.write_bytes(b"keep")
        for accepted in (False, True):
            with patch("mod_manager.ui.dialogs.prompts.ask_yes_no", return_value=accepted) as ask:
                self.trigger(1, "install")
            ask.assert_called_once()
            self.assertEqual(self.mods[1].dest.read_bytes(), b"original-1" if accepted else b"keep")
            self.assertEqual(self.mods[1].src.read_bytes(), b"original-1")

    def test_failure_is_visible_in_session_error_history(self):
        with patch("mod_manager.links.shutil.copy2", side_effect=PermissionError("Test destination locked")):
            self.trigger(1, "install")
        self.assertEqual(self.window.errors.model.rowCount(), 1)
        self.assertIn("Test destination locked", self.window.errors.model.entries[0].message)
        self.assertFalse(self.mods[1].dest.exists())
        self.assertEqual(self.mods[1].src.read_bytes(), b"original-1")

    def test_favorites_menu_adds_mixed_selection_and_removes_all_favorites(self):
        storage.update_favorites(self.window.cfg, ["combat.pak"], True)
        self.window.refresh_mods()
        self.select_mod_rows(0, 1)
        action = self.actions(self.open_menu(0))["favorite"]
        self.assertEqual(action.text(), "Add to favorites")
        self.assertEqual(action.property("iconName"), "favorite")
        action.trigger()
        self.assertEqual(storage.load_favorites(self.window.cfg), {"combat.pak", "ui.pak"})
        action = self.actions(self.open_menu(1))["favorite"]
        self.assertEqual(action.text(), "Remove from favorites")
        self.assertEqual(action.property("iconName"), "favorite_filled")
        action.trigger()
        self.assertEqual(storage.load_favorites(self.window.cfg), set())

    def test_assign_label_dialog_uses_draft_text_and_writes_only_target(self):
        self.select_mod_rows(0)
        self.window.label_edit.setText("draft")
        with patch("mod_manager.ui.dialogs.prompts.choose_text", return_value=("  Custom label  ", True)) as choose:
            self.trigger(1, "add_label")
        self.assertEqual(choose.call_args.args[3], "draft")
        self.assertEqual(storage.load_labels(), {"ui.pak": "Custom label"})
        self.assertEqual(self.window._selected_mod_names(), ["ui.pak"])

    def test_cancelled_or_empty_label_input_never_writes_metadata(self):
        for text, accepted in (("cancelled", False), ("  ", True)):
            with patch("mod_manager.ui.dialogs.prompts.choose_text", return_value=(text, accepted)):
                self.trigger(1, "add_label")
            self.assertEqual(storage.load_labels(), {})

    def test_label_removal_submenu_removes_only_chosen_label_from_selection(self):
        storage.save_labels({"combat.pak": "Combat", "ui.pak": "UI"})
        self.window.refresh_mods()
        self.select_mod_rows(0, 1)
        submenu = self.actions(self.open_menu(0))["remove_label"].menu()
        self.assertEqual([action.text() for action in submenu.actions()], ["Combat", "UI"])
        submenu.actions()[0].trigger()
        self.assertEqual(storage.load_labels(), {"ui.pak": "UI"})
        self.assertEqual(self.window._selected_mod_names(), ["combat.pak", "ui.pak"])

    def test_preview_menu_uses_existing_batch_confirmation_and_preserves_original_image(self):
        image = QtGui.QImage(48, 24, QtGui.QImage.Format_RGB32)
        image.fill(QtCore.Qt.red)
        path = self.root / "preview.png"
        self.assertTrue(image.save(str(path)))
        original = path.read_bytes()
        self.select_mod_rows(0, 1)
        with patch("mod_manager.ui.controllers.preview_controller.read_clipboard_paths", return_value=[path]), patch(
            "mod_manager.ui.dialogs.prompts.choose_preview_image", return_value="apply",
        ) as confirm:
            self.trigger(0, "set_image")
        confirm.assert_called_once()
        self.assertEqual(confirm.call_args.args[2], 2)
        self.assertTrue(confirm.call_args.kwargs["clipboard"])
        for mod in self.mods:
            preview = QtGui.QImage(str(mod_image_path(self.window.cfg, mod.name)))
            self.assertEqual(preview.pixelColor(20, 10), QtGui.QColor(QtCore.Qt.red))
        self.assertEqual(path.read_bytes(), original)

    def test_preview_file_alternative_and_cancelled_batch_use_menu_targets(self):
        image = QtGui.QImage(48, 24, QtGui.QImage.Format_RGB32)
        image.fill(QtCore.Qt.blue)
        path = self.root / "preview.png"
        self.assertTrue(image.save(str(path)))
        with patch("mod_manager.ui.controllers.preview_controller.read_clipboard_paths", return_value=[]), patch(
            "mod_manager.ui.controllers.preview_controller.read_clipboard_image", return_value=None,
        ), patch("mod_manager.ui.dialogs.prompts.choose_open_file", return_value=str(path)), patch(
            "mod_manager.ui.dialogs.prompts.choose_preview_image", return_value="cancel",
        ) as confirm:
            self.select_mod_rows(0, 1)
            self.trigger(0, "set_image")
            confirm.assert_called_once()
            self.assertFalse((self.source / "images").exists())
            self.select_mod_rows(0)
            self.trigger(1, "set_image")
        self.assertIsNone(mod_image_path(self.window.cfg, "combat.pak"))
        preview = QtGui.QImage(str(mod_image_path(self.window.cfg, "ui.pak")))
        self.assertEqual(preview.pixelColor(20, 10), QtGui.QColor(QtCore.Qt.blue))
        self.assertTrue(path.exists())
