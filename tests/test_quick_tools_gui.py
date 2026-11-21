from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from mod_manager import storage
from tests.window_fixture import WindowTestCase
from tests.qt_support import qt_available

if qt_available():
    from PySide6 import QtCore, QtTest, QtWidgets

    from mod_manager.ui.dialogs.game_profile import GameProfileDialog
    from mod_manager.ui.theme import tokens


class QuickToolsGuiTests(WindowTestCase):
    def setUp(self) -> None:
        super().setUp()
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.profile_id = self.window.cfg["active_game_profile_id"]
        save = patch("mod_manager.ui.controllers.games_controller.save_config")
        self.saved = save.start()
        self.addCleanup(save.stop)
        self.use_inline_runner()

    def tool(self, label: str, filename: str) -> dict:
        return {"label": label, "path": str(self.directory / filename)}

    def show_library(self) -> None:
        self.window.show()
        self.window.activateWindow()
        self.qt_app.processEvents()
        self.qt_app.processEvents()

    def update_tools(self, tools: list[dict]) -> None:
        storage.update_game_profile(self.window.cfg, self.profile_id, {"quick_tools": tools})
        self.window._sync_workspace()
        self.qt_app.processEvents(QtCore.QEventLoop.AllEvents, 1000)

    def test_profile_editor_saves_added_tools_and_discards_cancelled_changes(self):
        original = self.tool("Original", "first.exe")
        selected = self.tool("New tool", "Another Tool.exe")
        self.update_tools([original])

        def save_dialog(dialog):
            dialog.quick_tools.rows[0].remove.click()
            dialog.quick_tools.add.click()
            dialog.quick_tools.add.click()
            row = dialog.quick_tools.rows[1]
            row.label.setText(" " + selected["label"] + " ")
            dialog.accept()
            self.assertNotEqual(dialog.result(), QtWidgets.QDialog.Accepted)
            error.assert_called_once()
            self.assertIn("Tool 2", error.call_args.args[2])
            self.assertIn("application path", error.call_args.args[2])
            row.browse.click()
            dialog.accept()
            return dialog.result()

        with patch.object(GameProfileDialog, "exec", save_dialog), \
                patch("mod_manager.ui.dialogs.prompts.choose_open_file", return_value=selected["path"]), \
                patch("mod_manager.ui.dialogs.prompts.show_error") as error:
            self.window.games.edit(self.profile_id)
        self.saved.assert_called_once()
        self.assertEqual(self.saved.call_args.args[0]["quick_tools"], [selected])
        self.assertEqual([button.accessibleName() for button in self.window.quick_tools.buttons], ["New tool"])

        def cancel_dialog(dialog):
            dialog.quick_tools.rows[0].remove.click()
            dialog.reject()
            return dialog.result()

        with patch.object(GameProfileDialog, "exec", cancel_dialog):
            self.window.games.edit(self.profile_id)
        self.saved.assert_called_once()
        self.assertEqual(self.window.cfg["quick_tools"], [selected])

    def test_profile_switch_replaces_tools_and_hides_empty_section(self):
        self.update_tools([self.tool("First", "first.exe")])
        second = storage.create_game_profile("Second", {
            "quick_tools": [self.tool("Second", "second.exe")],
        }, self.window.cfg)
        empty = storage.create_game_profile("Empty", {}, self.window.cfg)
        storage.set_active_game_profile(self.window.cfg, self.profile_id)
        self.show_library()
        self.assertEqual([button.text() for button in self.window.quick_tools.buttons], ["First"])

        self.window.games.select(second["id"])
        self.assertEqual([button.text() for button in self.window.quick_tools.buttons], ["Second"])
        self.assertTrue(self.window.quick_tools.isVisible())
        self.window.games.select(empty["id"])
        self.assertFalse(self.window.quick_tools.isVisible())
        self.assertTrue(self.window.details_button.isVisible())
        self.window.games.select(self.profile_id)
        self.assertEqual([button.text() for button in self.window.quick_tools.buttons], ["First"])

    def test_overflow_scrolls_inside_header_without_moving_library_controls(self):
        window = self.window
        bar = window.quick_tools
        tools = [self.tool(f"Mod management application {index + 1}", f"tool{index}.exe") for index in range(12)]
        self.show_library()
        controls = (window.details_button, window.library_scroll, window.mods_actions)
        scrollbar = bar.scroll.horizontalScrollBar()
        for width, font_size in ((tokens.DEFAULT_WIDTH, 10), (tokens.MIN_WIDTH, 17)):
            with self.subTest(width=width, font_size=font_size):
                window.cfg["gui_font_size"] = font_size
                window._refresh_theme()
                window.resize(width, tokens.MIN_HEIGHT)
                self.update_tools([])
                baseline = [control.geometry() for control in controls]
                self.update_tools(tools[:1])
                self.assertEqual(scrollbar.maximum(), 0)
                self.assertFalse(bar.scroll._overlay_scrollbars.horizontal.isVisible())
                self.assertEqual([control.geometry() for control in controls], baseline)
                self.update_tools(tools)
                self.assertGreater(scrollbar.maximum(), 0)
                self.assertTrue(bar.scroll._overlay_scrollbars.horizontal.isVisible())
                self.assertEqual([control.geometry() for control in controls], baseline)
                self.assertLess(bar.geometry().right(), window.details_button.geometry().left())
                last = bar.buttons[-1]
                bar.buttons[-2].setFocus()
                QtTest.QTest.keyClick(bar.buttons[-2], QtCore.Qt.Key_Tab)
                self.qt_app.processEvents()
                self.assertTrue(last.hasFocus())
                self.assertGreater(scrollbar.value(), 0)
                viewport = bar.scroll.viewport()
                self.assertTrue(viewport.rect().contains(last.mapTo(viewport, last.rect().center())))
                self.assertEqual(last.property("variant"), window.details_button.property("variant"))
                self.assertLessEqual(last.width(), viewport.width())
                self.assertIn(tools[-1]["label"], last.toolTip())

    def test_click_launches_exact_application_and_reports_missing_or_failed_targets(self):
        existing = self.tool("Mods & Tools", "Tool With Spaces.exe")
        missing = self.tool("Old tool", "Missing.exe")
        path = Path(existing["path"])
        path.touch()
        self.update_tools([existing, missing])
        self.show_library()
        self.assertEqual(self.window.quick_tools.buttons[0].text(), "Mods && Tools")
        with patch("mod_manager.ui.controllers.quick_tools_controller.QtCore.QProcess.startDetached",
                   side_effect=[(True, 123), (False, 0)]) as launch, \
                patch("mod_manager.ui.dialogs.prompts.show_error") as error:
            self.window.quick_tools.buttons[0].click()
            launch.assert_called_once_with(str(path), [], str(path.parent))
            error.assert_not_called()
            self.window.quick_tools.buttons[1].click()
            launch.assert_called_once()
            self.assertIn(missing["path"], error.call_args.args[2])
            self.assertIn("could not be found", error.call_args.args[2])
            self.window.quick_tools.buttons[0].click()
            self.assertEqual(launch.call_count, 2)
            self.assertIn(existing["label"], error.call_args.args[2])
            self.assertIn("could not start", error.call_args.args[2])

    def test_windows_shortcut_uses_the_system_handler(self):
        shortcut = self.tool("Mod Tool", "Tool Shortcut.lnk")
        Path(shortcut["path"]).touch()
        self.update_tools([shortcut])
        with patch("mod_manager.ui.controllers.quick_tools_controller.is_windows", return_value=True), \
                patch("mod_manager.ui.controllers.quick_tools_controller.os.startfile", create=True) as launch:
            self.window.quick_tools.buttons[0].click()
        launch.assert_called_once_with(shortcut["path"])
