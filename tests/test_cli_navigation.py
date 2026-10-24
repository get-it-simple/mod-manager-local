from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch

from mod_manager import links, menus, settings_schema, storage
from mod_manager.cli_menu_actions import completions, parse_action
from mod_manager.cli_navigation import split_command
from mod_manager.cli_utils import _CmdCompleter
from tests.cli_support import CliEnvironment


class NavigationTests(CliEnvironment, unittest.TestCase):
    def interact(self, commands):
        output, errors = io.StringIO(), io.StringIO()
        answers = iter(commands)
        def answer(message):
            print(message, end="")
            value = next(answers)
            if isinstance(value, type) and issubclass(value, BaseException):
                raise value
            return value
        with patch("builtins.input", side_effect=answer) as reader, patch("sys.stdin.isatty", return_value=False), patch("sys.stdout", output), patch("sys.stderr", errors):
            code = menus.main_menu()
        self.assertEqual(reader.call_count, len(commands), "The script left unused answers.")
        return code, output.getvalue(), errors.getvalue()

    def profile_answers(self, name):
        return [name, *([""] * len(settings_schema.MODS_FIELDS))]

    def test_global_navigation_works_in_every_section(self):
        self.add_mods("a.pak")
        for choice, section in (("1", "Games"), ("2", "Settings"), ("3", "Mods"), ("4", "Presets"), ("7", "Broken links")):
            for navigation in ("/back", "/home", "/exit"):
                with self.subTest(choice=choice, navigation=navigation):
                    commands = [choice, navigation] + ([] if navigation == "/exit" else ["0"])
                    code, output, error = self.interact(commands)
                    self.assertEqual(code, 0, error)
                    self.assertIn("Main > " + section, output)

    def test_back_at_main_menu_does_not_exit(self):
        code, output, error = self.interact(["/back", "0"])
        self.assertEqual(code, 0, error)
        self.assertIn("Already at the main menu", output)
        self.assertIn("Goodbye", output)

    def test_eof_exits_from_main_and_nested_input_without_writes(self):
        before = self.snapshot()
        for commands in ([EOFError], ["3", EOFError], ["1", "1", "Unfinished", EOFError], ["2", "1", "1", EOFError]):
            with self.subTest(commands=commands):
                self.assertEqual(self.interact(commands)[0], 0)
                self.assertEqual(self.snapshot(), before)

    def test_keyboard_interrupt_cancels_edit_without_saving(self):
        before = self.config.read_bytes()
        code, _output, error = self.interact(["2", "1", "1", "20", KeyboardInterrupt, "0"])
        self.assertEqual(code, 0)
        self.assertIn("Cancelled", error)
        self.assertEqual(self.config.read_bytes(), before)
        self.assertEqual(self.interact([KeyboardInterrupt])[0], 130)

    def test_home_during_a_profile_edit_discards_the_edit(self):
        before = self.config.read_bytes()
        code, _output, error = self.interact(["1", "1", "New game", "/home", "0"])
        self.assertEqual(code, 0, error)
        self.assertEqual(self.config.read_bytes(), before)

    def test_settings_display_schema_and_use_shared_validation(self):
        code, output, error = self.interact(["2", "1", "1", "0", "25", "2", "0", "0"])
        self.assertEqual(code, 0)
        self.assertIn("Mods per page", output)
        self.assertIn("between 1 and 1000", error)
        self.assertEqual(storage.load_config()["page_size"], 25)

    def test_settings_offer_save_discard_or_return_before_leaving(self):
        for decision in ("1", "2", "0"):
            with self.subTest(decision=decision):
                self.write_config()
                tail = ["3", "0", "0"] if decision == "0" else ["0"]
                code, output, error = self.interact(["2", "1", "1", "25", "0", decision, *tail])
                self.assertEqual(code, 0, error)
                self.assertIn("unsaved settings", output)
                self.assertEqual(storage.load_config()["page_size"], 25 if decision == "1" else 2)

    def test_settings_home_requires_a_decision_when_changes_are_pending(self):
        code, output, error = self.interact(["2", "1", "1", "25", "/home", "2", "0"])
        self.assertEqual(code, 0, error)
        self.assertIn("Changes discarded", output)
        self.assertEqual(storage.load_config()["page_size"], 2)

    def test_numeric_games_edit_prompts_for_profile_and_saves(self):
        code, output, error = self.interact(["1", "2", "1", *self.profile_answers("Renamed Game"), "0", "0"])
        self.assertEqual(code, 0, error)
        self.assertIn("Enter game number to edit", output)
        self.assertIn("Editing: Test Game (#1)", output)
        self.assertEqual(storage.load_config()["game_profiles"][0]["name"], "Renamed Game")

    def test_game_edit_shortcuts_have_the_same_result(self):
        for shortcut in ("e1", "e 1", "edit 1", "/edit 1"):
            with self.subTest(shortcut=shortcut):
                self.write_config()
                code, output, error = self.interact(["1", shortcut, *self.profile_answers("Renamed"), "0", "0"])
                self.assertEqual(code, 0, error)
                self.assertIn("Editing: Test Game", output)
                self.assertEqual(storage.load_config()["game_profiles"][0]["name"], "Renamed")

    def test_literal_placeholder_input_is_explained_without_changes(self):
        before = self.snapshot()
        code, output, error = self.interact(["1", "eN 1", "0", "0"])
        self.assertEqual(code, 0)
        self.assertIn("choose 2) Edit a game, then enter 1", error)
        self.assertIn("Shortcut: edit 1", error)
        self.assertNotIn("a Add |", output)
        self.assertEqual(self.snapshot(), before)

    def test_invalid_game_numbers_can_be_corrected_or_cancelled(self):
        before = self.snapshot()
        code, _output, error = self.interact(["1", "2", "99", "bad", "0", "edit 99", "0", "0"])
        self.assertEqual(code, 0)
        self.assertIn("Invalid index", error)
        self.assertIn("positive indexes", error)
        self.assertEqual(self.snapshot(), before)

    def test_text_zero_is_a_profile_name_not_navigation(self):
        code, _output, error = self.interact(["1", "2", "1", *self.profile_answers("0"), "0", "0"])
        self.assertEqual(code, 0, error)
        self.assertEqual(storage.load_config()["game_profiles"][0]["name"], "0")

    def test_back_during_profile_fields_cancels_only_the_edit(self):
        before = self.snapshot()
        code, output, error = self.interact(["1", "2", "1", "/back", "?", "0", "0"])
        self.assertEqual(code, 0, error)
        self.assertIn("2) Edit a game", output)
        self.assertEqual(self.snapshot(), before)

    def test_numeric_game_add_select_and_delete_workflows(self):
        code, output, error = self.interact(["1", "1", *self.profile_answers("Other Game"), "4", "1", "3", "2", "0", "0"])
        self.assertEqual(code, 0, error)
        cfg = storage.load_config()
        self.assertEqual([profile["name"] for profile in cfg["game_profiles"]], ["Test Game"])
        self.assertEqual(cfg["active_game_profile_id"], "test-game")
        self.assertIn("Enter game number to select", output)
        self.assertIn("Enter game number to delete", output)

    def test_game_delete_and_select_shortcuts_are_preserved(self):
        self.request(["games", "add", "Other Game"])
        code, _output, error = self.interact(["1", "select 1", "d 2", "0", "0"])
        self.assertEqual(code, 0, error)
        self.assertEqual(len(storage.load_config()["game_profiles"]), 1)
        self.assertEqual(storage.load_config()["active_game_profile_id"], "test-game")

    def test_game_edit_back_returns_to_games_instead_of_main(self):
        code, output, error = self.interact(["1", "2", "/back", "?", "0", "0"])
        self.assertEqual(code, 0, error)
        self.assertIn("Choose a game number, then edit its fields", output)
        self.assertEqual(storage.load_config()["game_profiles"][0]["name"], "Test Game")

    def test_paging_legacy_filters_and_bad_quoting_remain_usable(self):
        self.add_mods("a.pak", "b.pak", "c.pak")
        code, output, error = self.interact(["3", "l:Combat", "/clear", '/search "unfinished', "/next", "/next", "/prev", "p2", "/toggle 1", "/back", "0"])
        self.assertEqual(code, 0)
        self.assertIn("Label: Combat", output)
        self.assertIn("No closing quotation", error)
        self.assertIn("Page unchanged", output)
        self.assertTrue((self.game / "c.pak").exists())
        self.assertFalse((self.game / "a.pak").exists())

    def test_numbered_pages_submenu_and_sort(self):
        self.add_mods("a.pak", "b.pak", "c.pak")
        code, output, error = self.interact(["3", "8", "3", "2", "1", "1", "7", "3", "y", "0", "0"])
        self.assertEqual(code, 0, error)
        self.assertIn("Order: -name", output)
        self.assertTrue((self.game / "c.pak").exists())
        self.assertFalse((self.game / "a.pak").exists())

    def test_invalid_page_shortcuts_do_not_leave_the_section(self):
        for menu, section in (("3", "Mods"), ("4", "Presets"), ("7", "Broken links")):
            with self.subTest(section=section):
                code, output, error = self.interact([menu, "/page 0", "?", "0", "0"])
                self.assertEqual(code, 0)
                self.assertIn("positive page number", error)
                self.assertIn("Main > " + section, output)

    def test_invalid_selection_does_not_toggle_valid_items(self):
        self.add_mods("a.pak", "b.pak")
        code, _output, error = self.interact(["3", "/toggle 1,99", "/toggle 1,bad", "/back", "0"])
        self.assertEqual(code, 0)
        self.assertIn("Invalid index", error)
        self.assertIn("positive indexes", error)
        self.assertEqual(list(self.game.iterdir()), [])

    def test_bare_number_is_an_action_not_a_mod_selection(self):
        self.add_mods("a.pak", "b.pak")
        code, output, error = self.interact(["3", "1", "0", "0", "0"])
        self.assertEqual(code, 0, error)
        self.assertIn("Enter mod numbers", output)
        self.assertEqual(list(self.game.iterdir()), [])

    def test_menu_label_and_favorite_shortcuts_use_cli_handlers(self):
        self.add_mods("a.pak", "b.pak")
        code, output, error = self.interact(["3", '/l+ "Combat mods" 2', "/l Combat mods", "/favorite-add 1", "/favorite", "/toggle 1", "/back", "0"])
        self.assertEqual(code, 0, error)
        self.assertEqual(storage.load_labels(), {"b.pak": "Combat mods"})
        self.assertEqual(storage.load_favorites(storage.load_config()), {"b.pak"})
        self.assertTrue((self.game / "b.pak").exists())
        self.assertIn("Favorites: True", output)

    def test_numbered_label_and_favorite_workflows(self):
        self.add_mods("a.pak", "b.pak")
        code, _output, error = self.interact(["3", "5", "2", "2", "Combat mods", "5", "1", "Combat mods", "6", "2", "1", "6", "1", "1", "1", "0", "0"])
        self.assertEqual(code, 0, error)
        self.assertEqual(storage.load_labels(), {"b.pak": "Combat mods"})
        self.assertEqual(storage.load_favorites(storage.load_config()), {"b.pak"})
        self.assertTrue((self.game / "b.pak").exists())
        self.assertFalse((self.game / "a.pak").exists())

    def test_remove_label_and_favorite_submenus(self):
        self.add_mods("a.pak")
        self.request(["mods", "label-add", "combat", "1"])
        self.request(["mods", "favorite-add", "1"])
        code, _output, error = self.interact(["3", "5", "3", "1", "combat", "6", "3", "1", "0", "0"])
        self.assertEqual(code, 0, error)
        self.assertEqual(storage.load_labels(), {})
        self.assertEqual(storage.load_favorites(storage.load_config()), set())

    def test_nested_back_cancels_only_the_current_step(self):
        self.add_mods("a.pak")
        before = self.snapshot()
        code, output, error = self.interact(["3", "5", "2", "/back", "0", "6", "0", "0", "0"])
        self.assertEqual(code, 0, error)
        self.assertIn("Remove selected mods from favorites", output)
        self.assertEqual(self.snapshot(), before)

    def test_zero_cancels_selection_and_stays_in_the_parent_submenu(self):
        self.add_mods("a.pak")
        before = self.snapshot()
        for submenu, step, title in (("5", "2", "Mods > Labels"), ("6", "2", "Mods > Favorites"), ("8", "3", "Pages: current")):
            with self.subTest(submenu=submenu):
                code, output, error = self.interact(["3", submenu, step, "0", "0", "0", "0"])
                self.assertEqual(code, 0, error)
                self.assertGreaterEqual(output.count(title), 2)
                self.assertEqual(self.snapshot(), before)

    def test_numbered_install_uninstall_and_search(self):
        self.add_mods("a.pak", "b.pak")
        code, _output, error = self.interact(["3", "4", "b", "2", "3", "0", "0"])
        self.assertEqual(code, 0, error)
        self.assertEqual(list(self.game.iterdir()), [])
        self.assertEqual((self.source / "b.pak").read_text(), "b.pak")

    def test_explicit_install_page_confirms_actual_target_page(self):
        self.add_mods("a.pak", "b.pak", "c.pak", "c.utoc")
        self.cfg["game_profiles"][0]["mod_group_extensions"] = ".pak,.utoc"
        self.write_config()
        (self.game / "c.pak").write_text("old", encoding="utf-8")
        code, output, error = self.interact(["3", "/install 2", "n", "/install 2", "y", "/back", "0"])
        self.assertEqual(code, 0, error)
        self.assertIn("c.pak", output)
        self.assertIn("Cancelled", output)
        self.assertEqual((self.game / "c.pak").read_text(), "c.pak")
        self.assertFalse((self.game / "a.pak").exists())

    def test_prepare_requires_confirmation_in_menu(self):
        self.source.rmdir()
        self.game.rmdir()
        self.assertEqual(self.interact(["1", "5", "n", "0", "0"])[0], 0)
        self.assertFalse(self.source.exists())
        self.assertFalse(self.game.exists())
        self.assertEqual(self.interact(["1", "prepare", "y", "/back", "0"])[0], 0)
        self.assertTrue(self.source.is_dir())
        self.assertTrue(self.game.is_dir())

    def test_presets_can_be_browsed_and_deleted_without_mod_folders(self):
        self.source.rmdir()
        self.game.rmdir()
        self.presets.write_text(json.dumps({"one": ["missing.pak"]}), encoding="utf-8")
        code, output, error = self.interact(["4", "/help", "3", "1", "/back", "0"])
        self.assertEqual(code, 0, error)
        self.assertIn("[?]", output)
        self.assertEqual(storage.load_presets(), {})

    def test_presets_numbered_save_and_toggle(self):
        self.add_mods("a.pak")
        self.request(["mods", "install"])
        code, _output, error = self.interact(["4", "1", "My Loadout", "2", "1", "2", "1", "3", "1", "0", "0"])
        self.assertEqual(code, 0, error)
        self.assertTrue((self.game / "a.pak").exists())
        self.assertEqual(storage.load_presets(), {})

    def test_presets_slash_and_legacy_save_and_toggle(self):
        self.add_mods("a.pak")
        self.request(["mods", "install"])
        code, _output, error = self.interact(["4", 's:"My Loadout"', "/toggle 1", "/toggle 1", "/delete 1", "/back", "0"])
        self.assertEqual(code, 0, error)
        self.assertTrue((self.game / "a.pak").exists())
        self.assertEqual(storage.load_presets(), {})

    def test_numbered_broken_link_removal_respects_current_page(self):
        for name in ("a", "b", "c"):
            target = self.source / name
            target.mkdir()
            self.assertTrue(links.mklink(target, self.game / name)[0])
            target.rmdir()
        (self.game / "regular.pak").write_text("keep")
        code, _output, error = self.interact(["7", "3", "2", "1", "1", "2", "0", "0"])
        self.assertEqual(code, 0, error)
        self.assertEqual([path.name for path in self.game.iterdir()], ["regular.pak"])
        self.assertEqual((self.game / "regular.pak").read_text(), "keep")
        self.assertTrue(self.source.is_dir())

    def test_empty_lists_explain_unavailable_actions(self):
        code, output, error = self.interact(["3", "1", "2", "0", "4", "2", "3", "0", "7", "1", "2", "0", "0"])
        self.assertEqual(code, 0, error)
        self.assertIn("No mod available", output)
        self.assertIn("No preset available", output)
        self.assertIn("No broken link available", output)
        self.assertFalse(self.profiles.exists())

    def test_empty_environment_remains_navigable(self):
        self.config.unlink()
        code, output, error = self.interact(["/help", "1", "2", "0", "3", "4", "/back", "8", "0"])
        self.assertEqual(code, 0)
        self.assertIn("not configured", error)
        self.assertIn("No active game", output)
        self.assertIn("Choose 1) Add a game first", output)
        self.assertFalse(self.config.exists())

    def test_colon_shortcuts_preserve_case(self):
        self.assertEqual(split_command("l:Combat"), ("l", ["Combat"]))
        self.assertEqual(split_command('s:"My Loadout"'), ("save", ["My Loadout"]))

    def test_context_help_explains_menu_instead_of_cli_profile_ids(self):
        code, output, error = self.interact(["1", "?", "/help", "0", "0"])
        self.assertEqual(code, 0, error)
        self.assertIn("2) Edit a game", output)
        self.assertIn("Choose a game number", output)
        self.assertIn("edit 1", output)
        self.assertNotIn("profile_id", output)
        self.assertNotIn("usage:", output)

    def test_slash_help_without_completion_has_no_extra_pause(self):
        self.add_mods("a.pak")
        code, output, error = self.interact(["3", "/", "/back", "0"])
        self.assertEqual(code, 0, error)
        self.assertIn("Enter an action number first", output)
        self.assertIn("Clear search", output)

    def test_unknown_commands_report_help_and_leave_menu_usable(self):
        code, _output, error = self.interact(["unknown", "1", "unknown", "/back", "0"])
        self.assertEqual(code, 0)
        self.assertIn("Unknown selection", error)

    def test_action_completions_describe_the_same_numbered_choices(self):
        from prompt_toolkit.document import Document

        choices = completions("Games")
        matches = list(_CmdCompleter(lambda: choices).get_completions(Document("2"), None))
        match = next(item for item in matches if item.text == "2")
        self.assertEqual(match.display_meta_text, "Edit a game")
        self.assertEqual(parse_action("Games", match.text), ("edit", []))
        self.assertEqual(parse_action("Games", "e 1"), ("edit", ["1"]))

    def test_plain_input_fallback_when_completion_is_unavailable(self):
        output = io.StringIO()
        with patch("builtins.input", side_effect=["1", "?", "0", "0"]), patch("sys.stdin.isatty", return_value=True), patch("mod_manager.cli_utils._try_prompt_toolkit", return_value=(None, None)), patch("sys.stdout", output):
            self.assertEqual(menus.main_menu(), 0)
        self.assertIn("2) Edit a game", output.getvalue())
