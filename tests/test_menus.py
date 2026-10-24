from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mod_manager import menus, settings_schema
from mod_manager.models import ModItem

_ROOT = Path(tempfile.gettempdir())


def _mod(name: str, copy_install: bool = False, dest: Path | None = None) -> ModItem:
    return ModItem(
        name=name,
        src=_ROOT / "source" / name,
        dest=dest or _ROOT / "game" / name,
        is_dir=False,
        installed=False,
        copy_install=copy_install,
    )


class GameProfilePromptTests(unittest.TestCase):
    """The console prompt is generated from the schema, so it never drifts from the GUI."""

    def _run(self, answers: dict, existing: dict | None = None) -> dict | None:
        asked = []

        def fake_prompt(text: str) -> str:
            asked.append(text)
            for key, value in answers.items():
                if text.startswith(key):
                    return value
            return ""

        with patch("mod_manager.cli_menu_io.prompt", side_effect=fake_prompt):
            values = menus._prompt_game_profile(existing)
        self.asked = asked
        return values

    def test_the_prompt_covers_every_per_game_field(self):
        values = self._run({"Game name": "Stalker Two"})

        self.assertIsNotNone(values)
        for spec in settings_schema.MODS_FIELDS:
            self.assertIn(spec.key, values, spec.key)
            self.assertTrue(any(text.startswith(spec.label) for text in self.asked), spec.label)

    def test_the_install_method_and_grouping_answers_are_stored(self):
        values = self._run({
            "Game name": "Stalker Two",
            "Install method": "copy",
            "Grouped extensions": ".pak,.utoc,.ucas",
        })

        self.assertEqual(values["install_mode"], "copy")
        self.assertEqual(values["mod_group_extensions"], ".pak,.utoc,.ucas")

    def test_an_unknown_install_method_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Install method"):
            self._run({"Game name": "Stalker Two", "Install method": "teleport"})

    def test_empty_answers_keep_the_existing_profile_values(self):
        existing = {"name": "Old", "install_mode": "copy", "mod_group_extensions": ".pak"}

        values = self._run({}, existing)

        self.assertEqual(values["name"], "Old")
        self.assertEqual(values["install_mode"], "copy")
        self.assertEqual(values["mod_group_extensions"], ".pak")

    def test_an_empty_game_name_cancels(self):
        self.assertIsNone(self._run({}))


class ConfirmOverwriteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.taken = Path(self.tmp.name) / "weapon.pak"
        self.taken.touch()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _confirm(self, mods, answer: str):
        out = io.StringIO()
        with patch("mod_manager.cli_menu_io.prompt", return_value=answer), patch("sys.stdout", out):
            return menus._confirm_overwrite(mods), out.getvalue()

    def test_nothing_to_replace_needs_no_question(self):
        result, output = self._confirm([_mod("free.pak", copy_install=True)], "n")

        self.assertIs(result, False)
        self.assertEqual(output, "")

    def test_declining_cancels_the_operation(self):
        result, output = self._confirm([_mod("weapon.pak", copy_install=True, dest=self.taken)], "n")

        self.assertIsNone(result)
        self.assertIn("weapon.pak", output)

    def test_accepting_allows_the_replacement(self):
        result, _output = self._confirm([_mod("weapon.pak", copy_install=True, dest=self.taken)], "y")

        self.assertIs(result, True)

    def test_a_link_profile_is_never_asked(self):
        result, output = self._confirm([_mod("weapon.pak", dest=self.taken)], "n")

        self.assertIs(result, False)
        self.assertEqual(output, "")


if __name__ == "__main__":
    unittest.main()
