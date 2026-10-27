from __future__ import annotations

import ast
import json
import importlib.util
import tempfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6 import QtCore, QtTest, QtWidgets

from mod_manager import i18n, mods
from mod_manager.import_preview import destination_rows, preview_plans
from mod_manager.imports import ImportUnit, PreparedArchive, execute_plans
from mod_manager.keyboard import default_bindings, normalize_combo, validate_bindings
from mod_manager.library_state import folder_issues
from mod_manager.models import ModItem
from mod_manager.preset_plan import execute_preset_plan, plan_presets
from mod_manager.progress import report, reporting
from tests.window_fixture import WindowTestCase, mod_item


@pytest.mark.parametrize("value, expected", [(" Shift + Ctrl + F ", "ctrl+shift+f"), ("f5", "f5"), ("ctrl+plus", "ctrl+plus"), ("", "")])
def test_shortcuts_normalize_without_translated_display_values(value, expected):
    assert normalize_combo(value) == expected


@pytest.mark.parametrize("value", ["ctrl", "ctrl+f+g", "ctrl+ctrl+f", "ctrl+unknown", 1])
def test_invalid_shortcut_combinations_are_rejected(value):
    with pytest.raises(ValueError):
        normalize_combo(value)


def test_shortcut_conflicts_respect_command_context_and_disabled_bindings():
    bindings = default_bindings()
    bindings["search"]["combo"] = "ctrl+s"
    assert validate_bindings(bindings)["search"]["combo"] == "ctrl+s"
    bindings["refresh"]["combo"] = "ctrl+s"
    with pytest.raises(ValueError, match="Refresh current page"):
        validate_bindings(bindings)
    bindings["refresh"]["enabled"] = False
    assert validate_bindings(bindings)["refresh"]["enabled"] is False


def test_translation_discovery_partial_catalog_and_unknown_language(tmp_path):
    english = dict(i18n._english)
    for language, catalog in (("en", english), ("test", {"install_action": "Test install"})):
        folder = tmp_path / language
        folder.mkdir()
        (folder / "strings.json").write_text(json.dumps(catalog), encoding="utf-8")
    (tmp_path / "ignored").mkdir()
    with patch.object(i18n.resources, "files", return_value=tmp_path):
        try:
            assert i18n.available_languages() == ("en", "test")
            i18n.setup("test")
            assert i18n.t("install_action") == "Test install"
            assert i18n.t("install_selected", count=3) == "Install selected (3)"
            i18n.setup("unknown")
            assert i18n.get_current_language() == "en"
            assert i18n.t("install_action") == "Install"
        finally:
            i18n.setup("en")


def test_every_literal_translation_key_exists_in_english():
    root = Path(__file__).resolve().parents[1] / "mod_manager"
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "t":
                if node.args and isinstance(node.args[0], ast.Constant):
                    assert node.args[0].value in i18n._english, (path, node.args[0].value)


def test_translation_cannot_change_native_field_names_or_legacy_sort_values(monkeypatch):
    overrides = {key: "Translated value" for key in (
        "window", "windowtext", "text", "data1", "version", "pixelformat", "created_date")}
    monkeypatch.setattr(i18n, "_strings", {**i18n._english, **overrides})
    root = Path(__file__).resolve().parents[1] / "mod_manager"

    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    image = load("mod_manager._localized_image_test", root / "image.py")
    assert [name for name, _type in image._CLSID._fields_] == ["Data1", "Data2", "Data3", "Data4"]
    assert image._StartupInput().Version == 0
    assert "PixelFormat" in dict(image._BitmapData._fields_)
    theme = load("mod_manager.ui.theme._localized_manager_test", root / "ui/theme/manager.py")
    assert theme.PALETTE_ROLES[0][0] == "Window"
    assert theme.TEXT_ROLES[0] == "WindowText"
    order = load("mod_manager.ui._localized_order_test", root / "ui/view_modes.py")
    assert order.normalize_sort_key("Created date") == "created_date"
    assert order.normalize_sort_key("Translated value") == "created_date"


def test_installation_filter_combines_before_pagination():
    items = [mod_item("a.pak", True), mod_item("b.pak", False), mod_item("c.pak", False)]
    with patch.object(mods, "discover_mods", return_value=items), patch.object(mods, "ensure_mod_records"), patch.object(
        mods, "load_labels", return_value={}
    ), patch.object(mods, "load_mod_records", return_value={}), patch.object(mods, "load_label_definitions", return_value={}), patch.object(
        mods, "load_favorites", return_value={"b.pak", "c.pak"}
    ):
        filtered, shown, page, pages, labels = mods.mods_view({"page_size": 1}, 2, "", "pak", "name", True, state_filter="not_installed")
    assert [mod.name for mod in filtered] == ["b.pak", "c.pak"]
    assert [mod.name for mod in shown] == ["c.pak"]
    assert (page, pages, labels.catalog_count) == (2, 2, 3)


def test_folder_diagnostics_do_not_create_missing_directories(tmp_path):
    source, game = tmp_path / "source", tmp_path / "game"
    assert folder_issues({"mods_source_dir": str(source), "game_mods_dir": str(game)})
    assert not source.exists() and not game.exists()
    source.mkdir()
    assert any("contain" in issue for issue in folder_issues({"mods_source_dir": str(source), "game_mods_dir": str(source / "nested")}))


def test_preset_preview_order_matches_actual_payload_changes(tmp_path):
    source, game = tmp_path / "source", tmp_path / "game"
    source.mkdir()
    game.mkdir()
    items = []
    for name, installed in (("a.pak", True), ("b.pak", False)):
        path = source / name
        path.write_bytes(name.encode())
        if installed:
            (game / name).write_bytes(path.read_bytes())
        items.append(ModItem(name, path, game / name, False, installed, copy_install=True))
    cfg = {"mods_source_dir": str(source), "game_mods_dir": str(game), "install_mode": "copy"}
    definitions = {"first": ["a.pak", "b.pak"], "second": ["a.pak"], "missing": ["absent.pak"]}
    with patch("mod_manager.preset_plan.load_presets", return_value=definitions), patch(
        "mod_manager.preset_plan.discover_mods", return_value=items
    ), patch("mod_manager.preset_plan.mark_preset_managed"), patch("mod_manager.mods.mark_mods_managed"):
        plan = plan_presets(cfg, list(definitions))
        assert [(row.name, row.action) for row in plan.changes] == [
            ("a.pak", "unchanged"), ("b.pak", "install"), ("a.pak", "uninstall"), ("absent.pak", "missing")]
        assert not (game / "b.pak").exists()
        result = execute_preset_plan(plan, True)
    assert not (game / "a.pak").exists()
    assert (game / "b.pak").read_bytes() == b"b.pak"
    assert result.errors == 1
    assert all(item.src.read_bytes() == item.name.encode() for item in items)


@pytest.mark.parametrize("together,preserve", [(True, False), (True, True), (False, False), (False, True)])
def test_import_preview_matches_published_paths(tmp_path, together, preserve):
    root = tmp_path / "archive"
    root.mkdir()
    relative = Path("nested") / "A.pak"
    (root / relative).parent.mkdir()
    (root / relative).write_bytes(b"original")
    archive = PreparedArchive("pack", root, [ImportUnit("A.pak", (relative,))], mode="together" if together else "separate",
                              preserve_structure=preserve, selected={0})
    destination = tmp_path / "library"
    destination.mkdir()
    plans = preview_plans([archive])
    expected = {Path(*row) for row in destination_rows(str(destination), plans)}
    assert list(destination.iterdir()) == []
    with patch("mod_manager.imports.ensure_mod_records"), patch("mod_manager.imports.register_directory_mod"):
        imported, failed = execute_plans({"mods_source_dir": str(destination)}, plans)
    assert len(imported) == 1 and failed == []
    assert {path for path in destination.rglob("*") if path.is_file()} == expected
    assert all(path.read_bytes() == b"original" for path in expected)


def test_progress_reporter_is_scoped_and_restored_after_failure():
    events = []
    with pytest.raises(ValueError):
        with reporting(events.append):
            report("Importing", "a.pak", 1, 3)
            raise ValueError("failure")
    report("Outside reporter")
    assert len(events) == 1
    assert (events[0].name, events[0].completed, events[0].total) == ("a.pak", 1, 3)


class InterfaceImprovementsGuiTests(WindowTestCase):
    def setUp(self):
        super().setUp()
        self.use_inline_runner()

    def test_selection_counts_and_state_specific_availability(self):
        self.select_mod_rows(0, 1)
        for name in ("install_selected", "uninstall_selected"):
            button = self.window.mods_actions.button(name)
            self.assertTrue(button.isEnabled())
            self.assertIn("(1)", button.text())
        self.select_mod_rows(0)
        self.assertFalse(self.window.mods_actions.button("install_selected").isEnabled())
        self.assertTrue(self.window.mods_actions.button("uninstall_selected").isEnabled())

    def test_large_font_library_actions_are_readable_and_scroll_into_view(self):
        self.window.cfg["gui_font_size"] = 20
        self.window._refresh_theme()
        self.window.resize(880, 560)
        self.window.show()
        self.qt_app.processEvents()
        for name in ("install_page", "uninstall_page", "install_selected", "uninstall_selected"):
            button = self.window.mods_actions.button(name)
            self.qt_app.processEvents()
            self.assertGreaterEqual(button.width(), button.fontMetrics().horizontalAdvance(button.text()))
            position = button.mapTo(self.window.mods_tab, button.rect().center())
            self.assertTrue(self.window.mods_tab.rect().contains(position))
            self.assertFalse(self.window.library_scroll.isAncestorOf(button))

    def test_native_default_aliases_participate_in_conflict_detection(self):
        bindings = default_bindings()
        bindings["install"]["combo"] = "ctrl+equal"
        with self.assertRaises(ValueError):
            validate_bindings(bindings)

    def test_large_font_library_actions_are_readable_and_scroll_into_view(self):
        self.window.cfg["gui_font_size"] = 20
        self.window._refresh_theme()
        self.window.resize(880, 560)
        self.window.show()
        self.qt_app.processEvents()
        for name in ("install_page", "uninstall_page", "install_selected", "uninstall_selected"):
            button = self.window.mods_actions.button(name)
            self.qt_app.processEvents()
            self.assertGreaterEqual(button.width(), button.fontMetrics().horizontalAdvance(button.text()))
            position = button.mapTo(self.window.mods_tab, button.rect().center())
            self.assertTrue(self.window.mods_tab.rect().contains(position))
            self.assertFalse(self.window.library_scroll.isAncestorOf(button))

    def test_native_default_aliases_participate_in_conflict_detection(self):
        bindings = default_bindings()
        bindings["install"]["combo"] = "ctrl+equal"
        with self.assertRaises(ValueError):
            validate_bindings(bindings)

    def test_filter_chips_remove_only_the_chosen_filter(self):
        self.window.filters.add("search", "combat")
        self.window.filters.mode = "favorite"
        self.window._refresh_library_state()
        view = self.window.filter_summary.view
        view.setCurrentIndex(view.model().index(0, 0))
        QtTest.QTest.keyClick(view, QtCore.Qt.Key_Delete)
        self.assertEqual(self.window.filters.queries, ())
        self.assertEqual(self.window.filters.mode, "favorite")

    def test_empty_states_offer_contextual_actions(self):
        self.window.current_mods_shown = []
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, game = root / "source", root / "game"
            source.mkdir()
            game.mkdir()
            self.window.cfg.update(mods_source_dir=str(source), game_mods_dir=str(game))
            self.window.library.snapshot = replace(self.window.library.snapshot, issues=folder_issues(self.window.cfg))
            self.window._refresh_library_state()
            self.assertEqual(self.window.library_empty.labels[0].text(), "Your mod library is empty")
            self.window.filters.add("search", "missing")
            self.window._refresh_library_state()
            self.assertEqual(self.window.library_empty.labels[0].text(), "No matching mods")
            self.window.cfg["mods_source_dir"] = str(root / "absent")
            self.window.library.snapshot = replace(self.window.library.snapshot, issues=folder_issues(self.window.cfg))
            self.window._refresh_library_state()
            self.assertEqual(self.window.library_empty.labels[0].text(), "Check your mod folders")
            self.assertFalse((root / "absent").exists())

    def test_recording_shortcut_does_not_execute_save_and_reset_restores_saved_values(self):
        self.window._open_settings_page()
        self.window.show()
        editor = self.window.settings.fields["keyboard_shortcuts"].rows["refresh"][0]
        self.window.settings.fields["keyboard_shortcuts"].toggle.setChecked(True)
        editor.capture.setFocus()
        self.qt_app.processEvents()
        with patch.object(self.window.settings, "save") as save:
            QtTest.QTest.keyClick(editor.capture, QtCore.Qt.Key_S, QtCore.Qt.ControlModifier)
        save.assert_not_called()
        self.assertEqual(editor.combo(), "ctrl+s")
        self.assertEqual(self.window.keyboard.bindings["refresh"]["combo"], "f5")
        self.assertIn("settings", self.window.workspace.dirty_pages)
        self.window.settings.reset()
        self.assertEqual(editor.combo(), "f5")
        self.assertNotIn("settings", self.window.workspace.dirty_pages)

    def test_shortcut_conflict_blocks_save_and_preserves_live_bindings(self):
        self.window._open_settings_page()
        editor = self.window.settings.fields["keyboard_shortcuts"].rows["refresh"][0]
        editor.set_combo("ctrl+s")
        with patch("mod_manager.ui.dialogs.prompts.show_error") as error, patch("mod_manager.storage.save_config") as save:
            self.window.settings.save()
        error.assert_called_once()
        save.assert_not_called()
        self.assertEqual(self.window.keyboard.bindings["refresh"]["combo"], "f5")
        self.assertEqual(editor.combo(), "ctrl+s")

    def test_shortcuts_start_collapsed_and_clear_inside_the_capture_field(self):
        self.window._open_settings_page()
        shortcuts = self.window.settings.fields["keyboard_shortcuts"]
        self.assertTrue(shortcuts.content.isHidden())
        self.assertEqual(shortcuts.arrow.arrowType(), QtCore.Qt.DownArrow)
        shortcuts.arrow.click()
        self.assertFalse(shortcuts.content.isHidden())
        editor = shortcuts.rows["refresh"][0]
        self.assertEqual(editor.command.text(), "Refresh current page")
        self.assertEqual(editor.findChildren(QtWidgets.QComboBox), [])
        for key in (QtCore.Qt.Key_Backspace, QtCore.Qt.Key_Delete):
            editor.set_combo("ctrl+g")
            QtTest.QTest.keyClick(editor.capture, key)
            self.assertEqual(editor.combo(), "")
            self.assertEqual(editor.capture.text(), "")
        editor.set_combo("ctrl+g")
        editor.clear_button.click()
        self.assertEqual(editor.combo(), "")
        self.window.settings.save()
        self.assertEqual(self.window.keyboard.text("refresh"), "")
        self.assertEqual(self.window.cfg["keyboard_shortcuts"]["refresh"]["combo"], "")

    def test_typed_filters_wait_for_enter_and_completions_add_another_chip(self):
        box = self.window.search_box
        box.lineEdit().setText("comb")
        with patch.object(self.window, "_render_mods") as refresh:
            box.lineEdit().textEdited.emit("comb")
            self.assertEqual(self.window.filters.queries, ())
            QtTest.QTest.qWait(300)
            self.assertEqual(self.window.filters.queries, ())
            refresh.assert_not_called()
            box.lineEdit().returnPressed.emit()
            self.assertEqual(self.window.filters.queries, ("comb",))
            refresh.assert_called_once()
            refresh.reset_mock()
            box.completer().activated[str].emit("combat.pak")
            self.assertEqual(self.window.filters.queries, ("comb", "combat.pak"))
            refresh.assert_called_once()

    def test_save_applies_shortcut_and_updates_tooltips(self):
        self.window._open_settings_page()
        editor = self.window.settings.fields["keyboard_shortcuts"].rows["search"][0]
        editor.set_combo("ctrl+g")
        self.window.settings.save()
        self.assertEqual(self.window.cfg["keyboard_shortcuts"]["search"]["combo"], "ctrl+g")
        self.assertEqual(self.window.keyboard.text("search"), "Ctrl+G")
        self.assertIn("Ctrl+G", self.window.search_box.toolTip())

    def test_cancelled_preset_preview_has_no_side_effects(self):
        self.window.presets_table.selectRow(1)
        with patch("mod_manager.ui.dialogs.prompts.review_preset_plan", return_value=False) as review, patch(
            "mod_manager.ui.app.execute_preset_plan"
        ) as execute:
            self.window._toggle_selected_presets()
        self.assertEqual([(change.action, change.name) for change in review.call_args.args[1].changes], [("install", "ui.pak")])
        execute.assert_not_called()

    def test_preset_state_change_requires_an_updated_confirmation(self):
        self.window.presets_table.selectRow(0)
        def confirm(*_args):
            if self.mods[0].installed:
                self.mods[0].installed = False
            return True
        with patch("mod_manager.ui.dialogs.prompts.review_preset_plan", side_effect=confirm) as review, patch(
            "mod_manager.ui.app.execute_preset_plan", return_value=mods.OperationResult()
        ) as execute:
            self.window._toggle_selected_presets()
        self.assertEqual(review.call_count, 2)
        self.assertEqual(execute.call_args.args[0].changes[0].action, "install")

    def test_profile_context_and_operation_result_remain_visible_across_pages(self):
        self.assertIn("Links", self.window.mods_tab.subtitle.text())
        self.window._set_status("Successful: 2 · Skipped: 1 · Failed: 1")
        self.window._open_settings_page()
        self.window.show()
        self.qt_app.processEvents()
        self.assertEqual(self.window.statusBar().currentMessage(), "Successful: 2 · Skipped: 1 · Failed: 1")
        self.assertIs(self.window.centralWidget(), self.window.workspace)

    def test_completed_settings_tasks_do_not_leave_a_preparing_message(self):
        indicator = self.window.activity.indicator
        self.window._set_busy(True)
        self.assertFalse(indicator.isHidden())
        self.window._set_busy(False)
        self.assertTrue(indicator.isHidden())
        self.assertFalse(self.window.library.loading)
