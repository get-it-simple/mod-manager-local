from __future__ import annotations

import io
import os
import subprocess
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch

from mod_manager import links, platform_utils
from mod_manager.cli import run_cli
from mod_manager.cli_menu_io import recover_links
from mod_manager.link_recovery import (
    needs_copy_recovery, retry_copy_installations,
    save_copy_profile, validate_recovery_profile,
)
from mod_manager.models import OperationFailure, OperationItem, OperationResult
from mod_manager.mods import change_mods, discover_mods
from mod_manager.storage import load_config
from tests.cli_support import CliEnvironment


class LinkCapabilityTests(unittest.TestCase):
    def test_volume_capability_and_unknown_results(self):
        for flags, path_ok, info_ok, expected in (
            (0, True, True, False), (0x80, True, True, True),
            (0, False, True, None), (0, True, False, None),
        ):
            with self.subTest(flags=flags, path_ok=path_ok, info_ok=info_ok):
                kernel = Mock()

                def path_name(directory, buffer, size):
                    buffer.value = "C:\\"
                    return path_ok

                def information(root, name, size, serial, length, result, filesystem, capacity):
                    result._obj.value = flags
                    return info_ok

                kernel.GetVolumePathNameW.side_effect = path_name
                kernel.GetVolumeInformationW.side_effect = information
                with patch("mod_manager.platform_utils.is_windows", return_value=True), patch(
                    "ctypes.WinDLL", return_value=kernel, create=True,
                ):
                    self.assertIs(platform_utils.supports_links(Path.cwd()), expected)

    def test_unavailable_api_is_unknown(self):
        with patch("mod_manager.platform_utils.is_windows", return_value=True), patch(
            "ctypes.WinDLL", side_effect=OSError("unavailable"), create=True,
        ):
            self.assertIsNone(platform_utils.supports_links(Path.cwd()))


class LinkBackendTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source.pak"
        self.source.write_text("source", encoding="utf-8")
        self.target = self.root / "target.pak"

    def test_single_unsupported_link_never_starts_a_command(self):
        with patch("mod_manager.links.supports_links", return_value=False), patch(
            "mod_manager.links.subprocess.run",
        ) as command:
            result = links.mklink(self.source, self.target)
        self.assertEqual(result, (False, links.UNSUPPORTED_LINK_MESSAGE))
        command.assert_not_called()
        self.assertFalse(self.target.exists())
        self.assertEqual(self.source.read_text(encoding="utf-8"), "source")

    def test_batch_keeps_validation_errors_when_nothing_can_be_linked(self):
        existing = self.root / "existing.pak"
        existing.write_text("keep", encoding="utf-8")
        with patch("mod_manager.links.is_windows", return_value=True), patch(
            "mod_manager.links.supports_links", return_value=False,
        ), patch("mod_manager.links.subprocess.run") as command:
            results = links.mklink_batch([
                (self.source, self.target, False),
                (self.root / "missing.pak", self.root / "other.pak", False),
                (self.source, existing, False),
            ])
        self.assertEqual(results[0], (False, links.UNSUPPORTED_LINK_MESSAGE))
        self.assertIn("Source not found", results[1][1])
        self.assertIn("Target already exists", results[2][1])
        command.assert_not_called()
        self.assertEqual(existing.read_text(encoding="utf-8"), "keep")

    def test_unknown_support_attempts_link_and_preserves_native_error(self):
        with patch("mod_manager.links.is_windows", return_value=True), patch(
            "mod_manager.links.supports_links", return_value=None,
        ), patch("mod_manager.links.subprocess.run", return_value=subprocess.CompletedProcess(
            [], 1, "", "Native failure",
        )) as command:
            self.assertEqual(links.mklink(self.source, self.target), (False, "Native failure"))
        command.assert_called_once()

    @unittest.skipUnless(os.name == "nt", "Windows batch execution")
    def test_real_batch_output_contains_only_the_error_for_each_failed_item(self):
        native_run = subprocess.run
        scripts = []

        def substitute_backend(arguments, **kwargs):
            script = Path(arguments[-1])
            scripts.append(script)
            lines = []
            index = 0
            for line in script.read_text(encoding="utf-8").splitlines():
                if line.startswith("mklink "):
                    if index == 0:
                        lines.extend(["echo Created", "cmd /d /c exit 0"])
                    else:
                        lines.extend(["echo The device does not support symbolic links.", "cmd /d /c exit 1"])
                    index += 1
                else:
                    lines.append(line)
            script.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return native_run(arguments, **kwargs)

        with patch("mod_manager.links.supports_links", return_value=None), patch(
            "mod_manager.links.subprocess.run", side_effect=substitute_backend,
        ):
            result = links.mklink_batch([
                (self.source, self.target, False),
                (self.source, self.root / "second.pak", False),
            ])
        self.assertEqual(result, [(True, "OK"), (False, "The device does not support symbolic links.")])
        self.assertTrue(all(not script.exists() for script in scripts))

    def test_command_start_failure_preserves_prevalidated_results(self):
        missing = self.root / "missing.pak"
        with patch("mod_manager.links.is_windows", return_value=True), patch(
            "mod_manager.links.supports_links", return_value=None,
        ), patch("mod_manager.links.subprocess.run", side_effect=OSError("Cannot start cmd")):
            results = links.mklink_batch([
                (missing, self.target, False),
                (self.source, self.root / "second.pak", False),
            ])
        self.assertIn("Source not found", results[0][1])
        self.assertEqual(results[1], (False, "Cannot start cmd"))


class CopyRecoveryTests(CliEnvironment, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.cfg["game_profiles"][0]["install_mode"] = "link"
        self.write_config()
        self.add_mods("a.pak", "b.pak")
        self.loaded = load_config()

    def failed_install(self):
        with patch("mod_manager.links.supports_links", return_value=False):
            return change_mods(discover_mods(self.loaded), "install")

    def test_failure_has_a_stable_reason_and_legacy_constructor_still_works(self):
        result = self.failed_install()
        self.assertTrue(needs_copy_recovery(result))
        self.assertEqual(result.items[0].failures[0].code, links.UNSUPPORTED_LINKS)
        self.assertEqual(OperationFailure(self.source, self.game, "old").code, "")
        ordinary = OperationResult((OperationItem("a", "installed", False, "Denied", (
            OperationFailure(self.source, self.game, "Denied"),
        )),))
        self.assertFalse(needs_copy_recovery(ordinary))

    def test_accept_saves_copy_and_retries_the_actual_files(self):
        initial = self.failed_install()
        with patch("mod_manager.cli_menu_io.ask_yes_no", return_value=True), patch("sys.stderr", io.StringIO()):
            result = recover_links(self.loaded, initial, ())
        self.assertEqual(result.errors, 0)
        self.assertEqual(load_config()["install_mode"], "copy")
        self.assertTrue(all((self.game / name).read_bytes() == (self.source / name).read_bytes()
                            for name in ("a.pak", "b.pak")))

    def test_decline_changes_neither_profile_nor_destinations(self):
        initial = self.failed_install()
        before = self.snapshot()
        with patch("mod_manager.cli_menu_io.ask_yes_no", return_value=False), patch("sys.stderr", io.StringIO()):
            self.assertIs(recover_links(self.loaded, initial, ()), initial)
        self.assertEqual(self.snapshot(), before)

    def test_save_failure_preserves_memory_and_stops_before_copying(self):
        initial = self.failed_install()
        before = deepcopy(self.loaded)
        with patch("mod_manager.storage.save_config", side_effect=PermissionError("Cannot save")):
            with self.assertRaisesRegex(PermissionError, "Cannot save"):
                save_copy_profile(self.loaded, before)
        self.assertEqual(self.loaded, before)
        self.assertEqual(list(self.game.iterdir()), [])
        self.assertTrue(needs_copy_recovery(initial))

    def test_changed_profile_is_rejected(self):
        for key, value in (("game_mods_dir", "changed"), ("install_mode", "copy"), ("active_game_profile_id", "other")):
            with self.subTest(key=key):
                current = deepcopy(self.loaded)
                current[key] = value
                with self.assertRaisesRegex(ValueError, "changed"):
                    validate_recovery_profile(current, self.loaded)

    def test_profile_field_changes_are_rejected_even_before_normalization(self):
        current = deepcopy(self.loaded)
        current["game_profiles"][0]["game_mods_dir"] = "changed"
        with self.assertRaisesRegex(ValueError, "changed"):
            validate_recovery_profile(current, self.loaded)

    def test_partial_group_retries_failed_member_and_keeps_successful_operations(self):
        success = self.game / "a.pak"
        success.write_text("already installed", encoding="utf-8")
        failure = OperationFailure(self.source / "b.pak", self.game / "b.pak", links.UNSUPPORTED_LINK_MESSAGE, links.UNSUPPORTED_LINKS)
        initial = OperationResult((
            OperationItem("a.pak", "installed", True, "OK"),
            OperationItem("old.pak", "uninstalled", True, "OK"),
            OperationItem("group.pak", "installed", False, failure.message, (failure,)),
        ))
        with patch("mod_manager.mods.mark_mods_managed") as managed:
            result = retry_copy_installations(self.loaded, initial)
        self.assertEqual(result.errors, 0)
        self.assertEqual(result.items[:2], initial.items[:2])
        self.assertEqual(success.read_text(encoding="utf-8"), "already installed")
        self.assertEqual((self.game / "b.pak").read_bytes(), (self.source / "b.pak").read_bytes())
        managed.assert_called_once_with(["group.pak"], "installed")

    def test_late_conflict_fails_instead_of_skipping_a_group_member(self):
        initial = self.failed_install()
        (self.game / "a.pak").write_text("external", encoding="utf-8")
        result = retry_copy_installations(self.loaded, initial)
        self.assertEqual(result.errors, 1)
        self.assertEqual((self.game / "a.pak").read_text(encoding="utf-8"), "external")
        self.assertTrue((self.game / "b.pak").exists())

    def test_overwrite_is_a_separate_confirmation(self):
        initial = self.failed_install()
        (self.game / "a.pak").write_text("external", encoding="utf-8")
        before = self.snapshot()
        with patch("mod_manager.cli_menu_io.ask_yes_no", side_effect=[True, False]) as ask, patch("sys.stderr", io.StringIO()), patch("sys.stdout", io.StringIO()):
            self.assertIs(recover_links(self.loaded, initial, ()), initial)
        self.assertEqual(ask.call_count, 2)
        self.assertEqual(self.snapshot(), before)

    def test_confirmed_overwrite_replaces_only_failed_destinations(self):
        initial = self.failed_install()
        (self.game / "a.pak").write_text("external", encoding="utf-8")
        with patch("mod_manager.cli_menu_io.ask_yes_no", return_value=True), patch("sys.stderr", io.StringIO()), patch("sys.stdout", io.StringIO()):
            result = recover_links(self.loaded, initial, ())
        self.assertEqual(result.errors, 0)
        self.assertEqual((self.game / "a.pak").read_bytes(), (self.source / "a.pak").read_bytes())

    def test_retry_failure_is_reported_without_marking_success(self):
        initial = self.failed_install()
        with patch("mod_manager.links.shutil.copy2", side_effect=PermissionError("Locked")), patch(
            "mod_manager.mods.mark_mods_managed",
        ) as managed:
            result = retry_copy_installations(self.loaded, initial)
        self.assertEqual(result.errors, 2)
        self.assertEqual(result.items[0].failures[0].message, "Locked")
        managed.assert_not_called()
        self.assertTrue(all((self.source / name).exists() for name in ("a.pak", "b.pak")))

    def test_one_shot_cli_reports_hint_without_prompting_or_saving(self):
        before = self.config.read_bytes()
        with patch("mod_manager.links.supports_links", return_value=False), patch("builtins.input", side_effect=AssertionError("unexpected prompt")):
            code, output, errors = self.request(["mods", "install"])
        self.assertEqual(code, 1)
        self.assertIn("games edit test-game --install-mode copy", errors)
        self.assertEqual(self.config.read_bytes(), before)
        self.assertEqual(list(self.game.iterdir()), [])

    def test_interactive_cli_callback_returns_success_after_copy(self):
        with patch("mod_manager.links.supports_links", return_value=False), patch(
            "mod_manager.cli_menu_io.ask_yes_no", return_value=True,
        ), patch("sys.stdout", io.StringIO()), patch("sys.stderr", io.StringIO()):
            self.assertEqual(run_cli(["mods", "install"], recover_links=recover_links), 0)
        self.assertEqual(load_config()["install_mode"], "copy")
        self.assertEqual(len(list(self.game.iterdir())), 2)

    def test_mixed_toggle_does_not_reinstall_a_successfully_removed_mod(self):
        (self.game / "a.pak").write_text("installed", encoding="utf-8")
        with patch("mod_manager.links.supports_links", return_value=False), patch(
            "mod_manager.cli_menu_io.ask_yes_no", return_value=True,
        ), patch("sys.stdout", io.StringIO()), patch("sys.stderr", io.StringIO()):
            code = run_cli(["mods", "toggle", "1,2"], recover_links=recover_links)
        self.assertEqual(code, 0)
        self.assertFalse((self.game / "a.pak").exists())
        self.assertTrue((self.game / "b.pak").exists())
        self.assertEqual((self.source / "a.pak").read_text(encoding="utf-8"), "a.pak")

    def test_folder_fallback_and_uninstall_preserve_the_source_tree(self):
        folder = self.source / "Folder"
        (folder / "inner").mkdir(parents=True)
        (folder / "inner" / "data.bin").write_text("payload", encoding="utf-8")
        initial = self.failed_install()
        with patch("mod_manager.cli_menu_io.ask_yes_no", return_value=True), patch("sys.stderr", io.StringIO()):
            result = recover_links(self.loaded, initial, ())
        self.assertEqual(result.errors, 0)
        self.assertEqual((self.game / "Folder" / "inner" / "data.bin").read_text(encoding="utf-8"), "payload")
        removed = change_mods(discover_mods(self.loaded), "uninstall")
        self.assertEqual(removed.errors, 0)
        self.assertEqual(list(self.game.iterdir()), [])
        self.assertEqual((folder / "inner" / "data.bin").read_text(encoding="utf-8"), "payload")

    def test_one_shot_empty_preset_keeps_the_original_explanation(self):
        with patch("mod_manager.presets.load_presets", return_value={"empty": []}):
            code, output, errors = self.request(["presets", "toggle", "1"])
        self.assertEqual(code, 0, errors)
        self.assertIn("Nothing to install (all present or missing).", output)

    def test_presets_retry_keeps_missing_members_and_marks_only_complete_presets(self):
        from mod_manager.presets import toggle_presets_result

        presets = {"complete": ["a.pak"], "incomplete": ["b.pak", "missing.pak"]}
        with patch("mod_manager.presets.load_presets", return_value=presets), patch(
            "mod_manager.links.supports_links", return_value=False,
        ):
            _summary, initial = toggle_presets_result(self.loaded, list(presets), set())
        with patch("mod_manager.link_recovery.load_presets", return_value=presets), patch(
            "mod_manager.link_recovery.mark_preset_managed",
        ) as managed:
            result = retry_copy_installations(self.loaded, initial, preset_names=tuple(presets))
        self.assertEqual(result.errors, 1)
        self.assertEqual(next(item for item in result.items if item.name == "missing.pak").action, "missing")
        managed.assert_called_once_with("complete", "applied")
