from __future__ import annotations

from copy import deepcopy
import unittest

from mod_manager import storage
from mod_manager.labels import AUTOMATIC, MANUAL, LabelDefinition, LabelState, merge_label_states
from mod_manager.library_filters import LibraryFilters
from mod_manager.mods import change_mods_page, mods_view
from tests.cli_support import CliEnvironment


class LibraryFilterStateTests(unittest.TestCase):
    def test_chips_preserve_order_type_phrases_and_case_insensitive_uniqueness(self):
        filters = LibraryFilters()
        self.assertTrue(filters.add("search", " first type "))
        self.assertTrue(filters.add("label", "First Type"))
        self.assertTrue(filters.add("search", "second"))
        self.assertFalse(filters.add("search", "FIRST TYPE"))
        self.assertFalse(filters.add("search", "  "))
        self.assertEqual(filters.chips, [("search", "first type"), ("label", "First Type"), ("search", "second")])
        filters.remove("search", "FIRST TYPE")
        self.assertEqual(filters.labels, ("First Type",))
        self.assertEqual(filters.queries, ("second",))

    def test_rename_delete_and_profile_reconciliation_keep_other_filters(self):
        filters = LibraryFilters([("label", "A"), ("search", "first type"), ("label", "B"), ("label", "C")], "favorite")
        filters.reconcile_labels(["Renamed", "C"], {"A": "Renamed", "B": ""})
        self.assertEqual(filters.chips, [("label", "Renamed"), ("search", "first type"), ("label", "C")])
        self.assertEqual(filters.mode, "favorite")
        filters.reconcile_labels(["c"])
        self.assertEqual(filters.labels, ("c",))
        self.assertEqual(filters.queries, ("first type",))

    def test_toggle_and_clear_reset_active_state(self):
        filters = LibraryFilters()
        self.assertFalse(filters.active)
        filters.toggle_label("A")
        self.assertTrue(filters.active)
        filters.toggle_label("a")
        self.assertFalse(filters.active)
        filters.mode = "favorite"
        self.assertEqual(filters.state, "all")
        self.assertTrue(filters.active)
        filters.clear()
        self.assertFalse(filters.active)


class LabelExclusionTests(unittest.TestCase):
    def test_exclusions_override_any_inclusion_with_unicode_and_spaces(self):
        state = LabelState({"A": LabelDefinition(AUTOMATIC, ["first type", "синій"], ["first type old", "червоний"])})
        self.assertEqual(state.members("FIRST TYPE new.pak"), ("A",))
        self.assertEqual(state.members("first_type.pak"), ())
        self.assertEqual(state.members("FIRST TYPE OLD синій.pak"), ())
        self.assertEqual(state.members("СИНІЙ ЧЕРВОНИЙ.pak"), ())
        self.assertEqual(state.members("СИНІЙ новий.pak"), ("A",))

    def test_exclusions_only_affect_their_automatic_label(self):
        state = LabelState({
            "A": LabelDefinition(AUTOMATIC, ["pak"], ["old"]),
            "B": LabelDefinition(AUTOMATIC, ["pak"]),
            "C": LabelDefinition(MANUAL, ["pak"], ["old"]),
        }, {"old.pak": ["C"]})
        self.assertEqual(state.members("old.pak"), ("B", "C"))
        state.definitions["C"].mode = AUTOMATIC
        self.assertEqual(state.members("old.pak"), ("B",))
        self.assertEqual(state.definitions["C"].exclusions, ["old"])

    def test_validation_requires_inclusion_and_deduplicates_each_rule_type(self):
        state = LabelState({"A": LabelDefinition(AUTOMATIC, [" first type ", "FIRST TYPE"], [" old type ", "OLD TYPE", ""])})
        state.validate()
        self.assertEqual(state.definitions["A"].terms, ["first type"])
        self.assertEqual(state.definitions["A"].exclusions, ["old type"])
        state.definitions["A"].terms.clear()
        with self.assertRaises(ValueError):
            state.validate()

    def test_merge_preserves_independent_fields_and_rejects_conflicting_exclusions(self):
        saved = LabelState({"A": LabelDefinition(AUTOMATIC, ["pak"], ["old"])})
        edited, current = deepcopy(saved), deepcopy(saved)
        edited.definitions["A"].exclusions = ["obsolete"]
        current.definitions["A"].terms = ["skin"]
        merged = merge_label_states(saved, edited, current, {})
        self.assertEqual(merged.definitions["A"], LabelDefinition(AUTOMATIC, ["skin"], ["obsolete"]))
        current.definitions["A"].exclusions = ["broken"]
        with self.assertRaises(ValueError):
            merge_label_states(saved, edited, current, {})


class LibraryFilterIntegrationTests(CliEnvironment, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.add_mods("first type.pak", "second.pak", "first type old.pak", "unrelated.pak")
        self.cfg = storage.load_config()
        storage.save_label_state(LabelState({
            "First": LabelDefinition(AUTOMATIC, ["first type"], ["old"]),
            "Second": LabelDefinition(AUTOMATIC, ["second"]),
            "Empty": LabelDefinition(),
        }))
        storage.update_favorites(self.cfg, ["second.pak", "unrelated.pak"], True)

    def test_or_groups_intersect_before_pagination_and_counts_use_full_catalog(self):
        items, shown, page, pages, labels = mods_view(self.cfg, 2, ("First", "Second"), ("type", "second"), "name")
        self.assertEqual([mod.name for mod in items], ["first type.pak", "second.pak"])
        self.assertEqual([mod.name for mod in shown], ["first type.pak", "second.pak"])
        self.assertEqual((page, pages), (1, 1))
        self.assertEqual(dict((name, count) for name, _mode, count in labels.catalog()), {"First": 1, "Second": 1, "Empty": 0})
        self.assertEqual(len(labels.memberships), 4)

    def test_page_install_and_uninstall_use_all_active_filters(self):
        self.cfg["page_size"] = 1
        page, installed = change_mods_page(self.cfg, 2, ("First", "Second"), ("type", "second"), "name")
        self.assertEqual(page, 2)
        self.assertEqual([item.name for item in installed.items], ["second.pak"])
        self.assertEqual((self.game / "second.pak").read_text(encoding="utf-8"), "second.pak")
        self.assertFalse((self.game / "first type.pak").exists())
        _, removed = change_mods_page(self.cfg, 1, ("First", "Second"), (), "name", True, action="uninstall", state_filter="installed")
        self.assertEqual([item.name for item in removed.items], ["second.pak"])
        self.assertFalse((self.game / "second.pak").exists())
        self.assertTrue((self.source / "second.pak").is_file())

    def test_old_string_arguments_and_cli_observe_exclusions(self):
        items = mods_view(self.cfg, 1, "First", "first type", "name")[0]
        self.assertEqual([mod.name for mod in items], ["first type.pak"])
        code, output, _ = self.request(["mods", "list", "--label", "First"])
        self.assertEqual(code, 0)
        self.assertIn("first type.pak", output)
        self.assertNotIn("first type old.pak", output)

    def test_old_definitions_load_and_exclusions_round_trip(self):
        self.assertEqual(storage.load_label_state().definitions["First"].exclusions, ["old"])
        path = storage._active_profile_data_path(storage.LABELS_PATH)
        raw = storage.load_json(path, {})
        raw[storage.LABEL_DEFINITIONS_KEY]["First"].pop("exclusions", None)
        storage.save_json(path, raw)
        self.assertEqual(storage.load_label_state().definitions["First"].exclusions, [])
