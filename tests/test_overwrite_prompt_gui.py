from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.qt_support import qt_available
from tests.window_fixture import WindowTestCase

from mod_manager.models import ModFile, ModItem, OperationResult


@unittest.skipUnless(qt_available(), "PySide6 is not installed")
class GroupedModDetailTest(WindowTestCase):
    """A grouped mod must show the files it actually manages, not just its primary member."""

    def _grouped_mod(self) -> ModItem:
        root = Path(tempfile.gettempdir()) / "mm_group"
        members = tuple(
            ModFile(src=root / f"Weapon{suffix}", dest=root / "game" / f"Weapon{suffix}", is_dir=False)
            for suffix in (".pak", ".utoc", ".ucas")
        )
        return ModItem(
            name="Weapon.pak",
            src=members[0].src,
            dest=members[0].dest,
            is_dir=False,
            installed=False,
            files=members,
        )

    def _detail_texts(self) -> list[str]:
        from PySide6 import QtWidgets

        return [label.text() for label in self.window.detail_frame.findChildren(QtWidgets.QLabel)]

    def test_a_grouped_mod_lists_its_members(self):
        self.window._refresh_mod_detail(self._grouped_mod())

        texts = self._detail_texts()
        self.assertIn("Grouped files", texts)
        self.assertIn("Weapon.pak, Weapon.utoc, Weapon.ucas", texts)

    def test_a_plain_mod_has_no_grouped_files_row(self):
        self.window._refresh_mod_detail(self.mods[0])

        self.assertNotIn("Grouped files", self._detail_texts())


@unittest.skipUnless(qt_available(), "PySide6 is not installed")
class OverwritePromptTest(WindowTestCase):
    """A copy install must confirm before it replaces files already in the game folder."""

    config_overrides = {"install_mode": "copy"}

    def setUp(self) -> None:
        super().setUp()
        self.use_inline_runner()
        self.tmp = tempfile.TemporaryDirectory()
        self.game_dir = Path(self.tmp.name)
        self.taken = self.game_dir / "weapon.pak"
        self.taken.write_text("old", encoding="utf-8")
        self.window.current_mods_shown = [self._mod("weapon.pak", copy_install=True)]

    def tearDown(self) -> None:
        self.tmp.cleanup()
        super().tearDown()

    def _mod(self, name: str, copy_install: bool = False) -> ModItem:
        return ModItem(
            name=name,
            src=Path(self.tmp.name) / "source" / name,
            dest=self.game_dir / name,
            is_dir=False,
            installed=False,
            copy_install=copy_install,
        )

    def test_installing_the_page_asks_before_replacing_existing_files(self):
        with patch("mod_manager.ui.dialogs.prompts.ask_yes_no", return_value=True) as question, patch(
            "mod_manager.ui.app.change_mods_page", return_value=(1, OperationResult())
        ) as apply_mods, patch.object(self.window, "refresh_mods"), patch.object(self.window, "refresh_presets"):
            self.window._install_page()

        question.assert_called_once()
        self.assertIn("weapon.pak", question.call_args[0][2])
        self.assertIs(apply_mods.call_args[0][-1], True)

    def test_declining_the_prompt_installs_nothing(self):
        with patch("mod_manager.ui.dialogs.prompts.ask_yes_no", return_value=False) as question, patch(
            "mod_manager.ui.app.change_mods_page"
        ) as apply_mods:
            self.window._install_page()

        question.assert_called_once()
        apply_mods.assert_not_called()
        self.assertEqual(self.taken.read_text(encoding="utf-8"), "old")

    def test_toggling_selected_mods_asks_before_replacing_existing_files(self):
        with patch("mod_manager.ui.dialogs.prompts.ask_yes_no", return_value=False) as question, patch(
            "mod_manager.ui.app.change_mods"
        ) as toggle:
            self.window._toggle_selected_indexes([1])

        question.assert_called_once()
        toggle.assert_not_called()

    def test_a_free_destination_installs_without_a_prompt(self):
        self.window.current_mods_shown = [self._mod("free.pak", copy_install=True)]

        with patch("mod_manager.ui.app.change_mods_page", return_value=(1, OperationResult())) as apply_mods, patch.object(
            self.window, "refresh_mods"
        ), patch.object(self.window, "refresh_presets"):
            self.window._install_page()

        apply_mods.assert_called_once()

    def test_a_preset_toggle_asks_for_the_mods_it_would_install(self):
        pending = [self._mod("weapon.pak", copy_install=True)]

        self.window.presets_table.selectRow(1)
        with patch("mod_manager.preset_plan.load_presets", return_value={"ui": [pending[0].name]}), patch("mod_manager.preset_plan.discover_mods", return_value=pending), patch(
            "mod_manager.ui.dialogs.prompts.ask_yes_no", return_value=False
        ) as question, patch("mod_manager.ui.app.execute_preset_plan") as toggle:
            self.window._toggle_selected_presets()

        question.assert_called_once()
        toggle.assert_not_called()


@unittest.skipUnless(qt_available(), "PySide6 is not installed")
class LinkProfileNeverPromptsTest(WindowTestCase):
    """qt_support turns any unexpected modal into a failure, so a silent run is the assertion."""

    def setUp(self) -> None:
        super().setUp()
        self.use_inline_runner()
        self.tmp = tempfile.TemporaryDirectory()
        game_dir = Path(self.tmp.name)
        (game_dir / "weapon.pak").write_text("old", encoding="utf-8")
        self.window.current_mods_shown = [
            ModItem(
                name="weapon.pak",
                src=game_dir / "source" / "weapon.pak",
                dest=game_dir / "weapon.pak",
                is_dir=False,
                installed=False,
            )
        ]

    def tearDown(self) -> None:
        self.tmp.cleanup()
        super().tearDown()

    def test_installing_a_link_profile_never_opens_a_prompt(self):
        with patch("mod_manager.ui.app.change_mods_page", return_value=(1, OperationResult())) as apply_mods, patch.object(
            self.window, "refresh_mods"
        ), patch.object(self.window, "refresh_presets"):
            self.window._install_page()

        apply_mods.assert_called_once()


if __name__ == "__main__":
    unittest.main()
