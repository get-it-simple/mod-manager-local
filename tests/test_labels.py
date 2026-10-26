from __future__ import annotations

import unittest
from unittest.mock import patch
from copy import deepcopy

from mod_manager import storage
from mod_manager.labels import AUTOMATIC, MANUAL, LabelDefinition, LabelState, label_names, matching_fragment_ids, merge_label_states
from mod_manager.mods import add_label_to_mods, remove_label_from_mods, mods_view
from mod_manager.storage_policy import StorageError, storage_policy
from tests.cli_support import CliEnvironment


class LabelRulesTests(unittest.TestCase):
    def test_autosave_merge_keeps_external_assignments_when_renaming(self):
        saved = LabelState({"A": LabelDefinition()}, {"one.pak": ["A"]})
        edited, current = deepcopy(saved), deepcopy(saved)
        edited.rename("A", "Renamed")
        current.assign("A", ["two.pak"])
        result = merge_label_states(saved, edited, current, {"A": "Renamed"})
        self.assertEqual(result.members("one.pak"), ("Renamed",))
        self.assertEqual(result.members("two.pak"), ("Renamed",))
        self.assertEqual(saved.members("two.pak"), ())
        self.assertEqual(current.members("two.pak"), ("A",))

    def test_autosave_merge_combines_independent_definition_fields(self):
        saved = LabelState({"A": LabelDefinition(MANUAL, ["one"])})
        edited, current = deepcopy(saved), deepcopy(saved)
        edited.definitions["A"].mode = AUTOMATIC
        current.definitions["A"].terms = ["two"]
        result = merge_label_states(saved, edited, current, {})
        self.assertEqual(result.members("two.pak"), ("A",))
        self.assertEqual(result.members("one.pak"), ())

    def test_autosave_merge_rejects_conflicting_fragments_and_duplicate_names(self):
        saved = LabelState({"A": LabelDefinition(MANUAL, ["one"])})
        edited, current = deepcopy(saved), deepcopy(saved)
        edited.definitions["A"].terms = ["two"]
        current.definitions["A"].terms = ["three"]
        with self.assertRaises(ValueError):
            merge_label_states(saved, edited, current, {})
        edited = deepcopy(saved)
        edited.rename("A", "Renamed")
        current.definitions["Renamed"] = LabelDefinition()
        with self.assertRaises(ValueError):
            merge_label_states(saved, edited, current, {"A": "Renamed"})

    def test_matching_fragment_ids_preserve_positions_and_report_every_match(self):
        terms = [" Skin ", "", "синій", "pak", "missing"]
        self.assertEqual(matching_fragment_ids("СИНІЙ_SKIN.pak", terms), (1, 3, 4))
        self.assertEqual(matching_fragment_ids("other.txt", terms), ())
        state = LabelState({"Looks": LabelDefinition(AUTOMATIC, terms)})
        self.assertEqual(state.members("СИНІЙ_SKIN.pak"), ("Looks",))

    def test_any_fragment_matches_unicode_and_substrings_ignoring_case(self):
        state = LabelState({"Texture": LabelDefinition(AUTOMATIC, ["SKIN", "синій"])})
        self.assertEqual(state.members("NewSkin_P.pak"), ("Texture",))
        self.assertEqual(state.members("СИНІЙ_костюм.pak"), ("Texture",))
        self.assertEqual(state.members("other.pak"), ())

    def test_modes_preserve_inactive_settings_and_allow_overlapping_labels(self):
        state = LabelState(
            {"A": LabelDefinition(MANUAL, ["weapon"]), "B": LabelDefinition(AUTOMATIC, ["weapon"])},
            {"other.pak": ["A"], "weapon.pak": ["A"]},
        )
        self.assertEqual(state.members("weapon.pak"), ("A", "B"))
        state.definitions["A"].mode = AUTOMATIC
        self.assertEqual(state.members("other.pak"), ())
        state.definitions["A"].mode = MANUAL
        self.assertEqual(state.members("other.pak"), ("A",))
        self.assertEqual(state.definitions["A"].terms, ["weapon"])

    def test_validation_deduplicates_terms_and_rejects_empty_automatic_rules(self):
        state = LabelState({"A": LabelDefinition(AUTOMATIC, [" skin ", "SKIN", ""])})
        state.validate()
        self.assertEqual(state.definitions["A"].terms, ["skin"])
        state.definitions["A"].terms = [""]
        with self.assertRaisesRegex(ValueError, "at least one"):
            state.validate()
        self.assertEqual(state.members("anything.pak"), ())


class LabelStorageTests(CliEnvironment, unittest.TestCase):
    def test_legacy_records_migrate_without_losing_history_or_favorites(self):
        storage.save_json(self.labels, {
            "old.pak": "Legacy",
            "history.pak": {"label": "History", "last_managed": "2026-01-01", "state": "installed"},
            storage.FAVORITES_KEY: {"test-game": ["old.pak"]},
        })
        state = storage.load_label_state()
        self.assertEqual(state.members("old.pak"), ("Legacy",))
        state.assignments["old.pak"].append("History")
        storage.save_label_state(state)
        self.assertEqual(storage.load_label_state().members("old.pak"), ("History", "Legacy"))
        self.assertEqual(storage.load_mod_records()["history.pak"]["last_managed"], "2026-01-01")
        self.assertEqual(storage.load_favorites(storage.load_config()), {"old.pak"})
        storage.mark_mods_managed(["old.pak"], "installed")
        self.assertEqual(storage.load_label_state().members("old.pak"), ("History", "Legacy"))
        self.assertNotIn(storage.LABEL_DEFINITIONS_KEY, storage.load_mod_records())

    def test_add_and_remove_only_the_requested_manual_label(self):
        add_label_to_mods("One", ["a.pak"])
        add_label_to_mods("Two", ["a.pak", "b.pak"])
        add_label_to_mods("one", ["a.pak"])
        self.assertEqual(storage.load_label_state().members("a.pak"), ("One", "Two"))
        remove_label_from_mods("ONE", ["a.pak"])
        self.assertEqual(storage.load_label_state().members("a.pak"), ("Two",))
        self.assertEqual(storage.load_label_state().members("b.pak"), ("Two",))

    def test_rename_and_delete_never_resurrect_legacy_labels(self):
        storage.save_json(self.labels, {"old.pak": "Old"})
        state = storage.load_label_state()
        state.rename("Old", "New")
        storage.save_label_state(state)
        self.assertEqual(storage.load_label_state().members("old.pak"), ("New",))
        state.delete("New")
        storage.save_label_state(state)
        storage.ensure_mod_records(["new.pak"])
        self.assertEqual(storage.load_label_state().definitions, {})
        self.assertEqual(storage.load_labels(), {})

    def test_automatic_labels_are_dynamic_and_cannot_be_manually_changed(self):
        self.add_mods("Skin.pak", "other.pak")
        cfg = storage.load_config()
        storage.save_label_state(LabelState({"Looks": LabelDefinition(AUTOMATIC, ["skin"])}, {"other.pak": ["Looks"]}))
        items, _shown, *_rest, labels = mods_view(cfg, 1, "looks", "", "name")
        self.assertEqual([mod.name for mod in items], ["Skin.pak"])
        self.assertEqual(label_names(labels, "Skin.pak"), ("Looks",))
        self.add_mods("NEWskin.pak")
        items = mods_view(cfg, 1, "Looks", "", "name")[0]
        self.assertEqual({mod.name for mod in items}, {"Skin.pak", "NEWskin.pak"})
        before = self.snapshot()
        for operation in (add_label_to_mods, remove_label_from_mods):
            with self.assertRaisesRegex(ValueError, "Automatic labels"):
                operation("Looks", ["other.pak"])
        self.assertEqual(self.snapshot(), before)

    def test_resolved_catalog_is_independent_of_filters_and_pagination(self):
        self.add_mods("SkinA.pak", "SkinB.pak", "Other.pak")
        state = LabelState({"Skin": LabelDefinition(AUTOMATIC, ["skin"]), "Empty": LabelDefinition()})
        storage.save_label_state(state)
        cfg = storage.load_config()
        cfg["page_size"] = 1
        _items, shown, page, pages, labels = mods_view(cfg, 2, "Skin", "", "name")
        self.assertEqual((len(shown), page, pages), (1, 2, 2))
        self.assertEqual(set(labels.memberships), {"SkinA.pak", "SkinB.pak", "Other.pak"})
        self.assertIn("Empty", labels.state.definitions)
        labels = mods_view(cfg, 1, "Skin", "no-result", "name", True)[4]
        self.assertEqual(len(labels.memberships), 3)

    def test_label_definitions_and_assignments_are_isolated_per_profile(self):
        cfg = storage.load_config()
        storage.save_label_state(LabelState({"A": LabelDefinition(AUTOMATIC, ["a"])}, {"a.pak": ["A"]}))
        storage.create_game_profile("Other", {"mods_source_dir": str(self.source), "game_mods_dir": str(self.game)}, cfg)
        other = cfg["game_profiles"][-1]["id"]
        storage.set_active_game_profile(cfg, other)
        storage.save_config(cfg)
        self.assertEqual(storage.load_label_state(), LabelState())
        storage.save_label_state(LabelState({"B": LabelDefinition()}, {"b.pak": ["B"]}))
        storage.set_active_game_profile(cfg, "test-game")
        storage.save_config(cfg)
        self.assertEqual(set(storage.load_label_state().definitions), {"A"})

    def test_failed_atomic_save_preserves_existing_data(self):
        storage.save_label_state(LabelState({"A": LabelDefinition()}, {"a.pak": ["A"]}))
        before = self.snapshot()
        state = storage.load_label_state()
        state.rename("A", "B")
        with patch("mod_manager.storage.os.replace", side_effect=PermissionError("locked")):
            with self.assertRaises(PermissionError):
                storage.save_label_state(state)
        self.assertEqual(self.snapshot(), before)

    def test_cli_read_only_loads_rules_and_multi_labels_without_writing(self):
        self.add_mods("Skin.pak", "Other.pak")
        storage.save_label_state(LabelState(
            {"Auto": LabelDefinition(AUTOMATIC, ["skin"]), "Manual": LabelDefinition()}, {"Skin.pak": ["Manual"]},
        ))
        before = self.snapshot()
        code, output, errors = self.request(["mods", "list", "--label", "Auto"])
        self.assertEqual((code, errors), (0, ""))
        self.assertIn("Skin.pak", output)
        self.assertNotIn("Other.pak", output)
        self.assertIn("Auto, Manual", output)
        self.assertEqual(self.snapshot(), before)

    def test_strict_loading_rejects_malformed_new_metadata(self):
        path = storage._active_profile_data_path(storage.LABELS_PATH)
        storage.save_json(path, {"a.pak": {"label": "A", "labels": "A"}})
        with storage_policy():
            with self.assertRaises(StorageError):
                storage.load_label_state()
        storage.save_json(path, {storage.LABEL_DEFINITIONS_KEY: {"A": {"mode": "automatic", "terms": "bad"}}})
        with storage_policy():
            with self.assertRaises(StorageError):
                storage.load_label_state()

    def test_empty_mod_records_do_not_change_label_drafts(self):
        storage.save_label_state(LabelState({"A": LabelDefinition()}, {"a.pak": ["A"]}))
        before = storage.load_label_state()
        storage.ensure_mod_records(["new.pak"])
        self.assertEqual(storage.load_label_state(), before)
