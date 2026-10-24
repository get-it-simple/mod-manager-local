from __future__ import annotations

import unittest
from pathlib import Path

from tests.qt_support import dispose, qt_app, qt_available

if qt_available():
    from PySide6 import QtCore, QtWidgets

    from mod_manager.ui.widgets.detail_view import display_path, path_button


@unittest.skipUnless(qt_available(), "PySide6 is not installed")
class PathDisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def test_deep_path_keeps_two_closest_directories(self):
        self.assertEqual(display_path(r"C:\Library\Games\Game\Mods\Weapon.pak"),
                         "…\\Game\\Mods\\Weapon.pak")

    def test_short_path_is_unchanged(self):
        for path in (r"C:\Mods\Weapon.pak", "Weapon.pak", "Mods/Weapon.pak"):
            with self.subTest(path=path):
                self.assertEqual(display_path(path), path)

    def test_unc_and_unicode_paths(self):
        self.assertEqual(display_path(r"\\server\share\Games\Гра\Моди\Зброя.pak"),
                         "…\\Гра\\Моди\\Зброя.pak")
        self.assertEqual(display_path("/library/games/game/mods/weapon.pak"),
                         "…/game/mods/weapon.pak")

    def test_character_limit_elides_the_middle_of_the_whole_string(self):
        for length in (99, 100, 101, 300):
            with self.subTest(length=length):
                path = "начало" + "x" * (length - len("начало.pak")) + ".pak"
                expected = path if length <= 100 else path[:50] + "…" + path[-49:]
                self.assertEqual(display_path(path), expected)
                self.assertLessEqual(len(display_path(path)), 100)

    def test_long_directories_and_filename_share_the_character_limit(self):
        compact = "…\\" + "a" * 60 + "\\" + "b" * 60 + "\\" + "c" * 60 + ".pak"
        path = "C:\\root\\" + compact[2:]
        self.assertEqual(display_path(path), compact[:50] + "…" + compact[-49:])

    def test_button_tooltip_and_click_use_the_full_path(self):
        path = Path("C:/Library/Games/Game/Mods") / ("x" * 150 + ".pak")
        selected = []
        button = path_button(path, selected.append)
        self.addCleanup(dispose, button)
        self.assertEqual(button.toolTip(), str(path))
        self.assertEqual(button.accessibleName(), str(path))
        self.assertLessEqual(len(button.text()), 100)
        button.click()
        self.assertEqual(selected, [path])

    def test_narrow_button_elides_and_expanding_restores_the_display(self):
        button = path_button(Path("C:/Library/Games/Game/Mods") / ("Weapon" * 10 + ".pak"), lambda path: None)
        self.addCleanup(dispose, button)
        button.resize(180, button.sizeHint().height())
        button.show()
        self.app.processEvents()
        self.assertIn("…", button.text())
        option = QtWidgets.QStyleOptionButton()
        button.initStyleOption(option)
        content = button.style().subElementRect(QtWidgets.QStyle.SE_PushButtonContents, option, button)
        self.assertLessEqual(button.fontMetrics().horizontalAdvance(button.text()), content.width())
        button.resize(1600, button.height())
        self.app.processEvents()
        self.assertEqual(button.text(), display_path(button.toolTip()))
        self.assertEqual(button.sizePolicy().horizontalPolicy(), QtWidgets.QSizePolicy.Ignored)
