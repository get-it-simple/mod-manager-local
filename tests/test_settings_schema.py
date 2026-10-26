from __future__ import annotations

import unittest

from app_paths import DEFAULT_CONFIG
from mod_manager import settings_schema as schema
from mod_manager import storage


class SchemaShapeTest(unittest.TestCase):
    def test_every_visible_setting_has_a_label_and_a_tooltip(self):
        for spec in schema.all_specs():
            self.assertTrue(spec.label, spec.key)
            self.assertNotEqual(spec.label, spec.key, spec.key)
            self.assertTrue(spec.label[0].isupper(), spec.key)
            self.assertTrue(spec.tooltip.endswith("."), spec.key)
            self.assertGreater(len(spec.tooltip), 40, spec.key)

    def test_no_label_is_a_raw_config_key(self):
        for spec in schema.all_specs():
            self.assertNotIn("_", spec.label, spec.key)

    def test_integer_settings_declare_a_range(self):
        for spec in schema.all_specs():
            if spec.kind == schema.INT:
                self.assertIsNotNone(spec.minimum, spec.key)
                self.assertIsNotNone(spec.maximum, spec.key)
                self.assertLess(spec.minimum, spec.maximum, spec.key)

    def test_choice_settings_declare_their_choices(self):
        for spec in schema.all_specs():
            if spec.kind == schema.CHOICE:
                self.assertGreaterEqual(len(spec.choices), 1 if spec.key == "gui_language" else 2, spec.key)

    def test_dependent_settings_point_at_a_real_choice_value(self):
        keys = {spec.key: spec for spec in schema.all_specs()}
        for spec in schema.all_specs():
            if spec.depends_on:
                other_key, required = spec.depends_on
                self.assertIn(other_key, keys, spec.key)
                self.assertIn(required, keys[other_key].choices, spec.key)

    def test_schema_covers_every_user_visible_default_config_key(self):
        visible = set(DEFAULT_CONFIG) - schema.NON_SETTING_KEYS
        self.assertEqual(visible, {spec.key for spec in schema.all_specs()})

    def test_per_game_keys_are_not_application_settings(self):
        self.assertTrue(schema.PROFILE_KEYS)
        self.assertFalse(set(schema.PROFILE_KEYS) & {spec.key for spec in schema.all_specs()})
        self.assertFalse(any(title == "Mods" for title, _specs in schema.SETTINGS_SECTIONS))

    def test_storage_reuses_the_schema_profile_keys(self):
        self.assertEqual(storage.GAME_PROFILE_KEYS, schema.PROFILE_KEYS)

    def test_setting_keys_are_unique(self):
        keys = [spec.key for spec in schema.all_specs()]
        self.assertEqual(len(keys), len(set(keys)))

    def test_game_profile_fields_reuse_the_mods_section_specs(self):
        self.assertEqual(schema.GAME_PROFILE_FIELDS[0].key, "name")
        self.assertEqual(schema.GAME_PROFILE_FIELDS[1:], schema.MODS_FIELDS)

    def test_dead_settings_are_gone(self):
        self.assertNotIn("button_size_percent", DEFAULT_CONFIG)

    def test_ui_scale_percent_has_a_default(self):
        self.assertEqual(DEFAULT_CONFIG["ui_scale_percent"], 100)

    def test_a_new_profile_links_instead_of_copying_and_groups_nothing(self):
        self.assertEqual(DEFAULT_CONFIG["install_mode"], "link")
        self.assertEqual(DEFAULT_CONFIG["mod_group_extensions"], "")
        self.assertEqual(schema.spec_for("install_mode").choices, ("link", "copy"))

    def test_the_install_method_and_grouping_are_per_game_settings(self):
        for key in ("install_mode", "mod_group_extensions"):
            self.assertIn(key, schema.PROFILE_KEYS, key)

    def test_label_for_falls_back_for_unknown_keys(self):
        self.assertEqual(schema.label_for("page_size"), "Mods per page")
        self.assertEqual(schema.label_for("mod_recursive_scan"), "Scan subfolders")
        self.assertEqual(schema.label_for("what_is_this"), "what is this")


class CoerceTest(unittest.TestCase):
    def test_read_settings_returns_a_value_for_every_spec(self):
        values = schema.read_settings(dict(DEFAULT_CONFIG))
        self.assertEqual(set(values), {spec.key for spec in schema.all_specs()})

    def test_defaults_round_trip_back_to_the_default_config(self):
        coerced = schema.coerce_settings(schema.default_settings())
        for key, value in coerced.items():
            self.assertEqual(value, DEFAULT_CONFIG[key], key)

    def test_integers_are_stored_as_numbers(self):
        result = schema.coerce_settings({"page_size": "25", "tile_size": "160"})
        self.assertEqual(result["page_size"], 25)
        self.assertEqual(result["tile_size"], 160)

    def test_a_trailing_percent_sign_is_accepted_for_scale(self):
        self.assertEqual(schema.coerce_settings({"ui_scale_percent": "150%"})["ui_scale_percent"], 150)

    def test_out_of_range_integers_are_rejected_with_a_readable_message(self):
        with self.assertRaises(ValueError) as caught:
            schema.coerce_settings({"page_size": "0"})
        self.assertEqual(str(caught.exception), "Mods per page must be between 1 and 1000.")

    def test_non_numeric_integers_are_rejected_with_a_readable_message(self):
        with self.assertRaises(ValueError) as caught:
            schema.coerce_settings({"gui_font_size": "big"})
        self.assertEqual(str(caught.exception), "Font size must be a whole number.")

    def test_unknown_choices_fall_back_to_the_first_choice(self):
        self.assertEqual(schema.coerce_settings({"gui_theme": "neon"})["gui_theme"], "system")
        self.assertEqual(schema.coerce_settings({"mod_view_mode": "TILES"})["mod_view_mode"], "tiles")

    def test_flags_are_stored_as_booleans(self):
        self.assertIs(schema.coerce_game_profile({"mod_recursive_scan": True})["mod_recursive_scan"], True)
        self.assertIs(schema.coerce_game_profile({"mod_recursive_scan": ""})["mod_recursive_scan"], False)

    def test_invalid_colors_fall_back_to_the_default_color(self):
        result = schema.coerce_settings({"gui_accent_color": "not a color"})
        self.assertEqual(result["gui_accent_color"], DEFAULT_CONFIG["gui_accent_color"])

    def test_valid_colors_are_normalized(self):
        self.assertEqual(schema.coerce_settings({"gui_accent_color": "#ABC"})["gui_accent_color"], "#aabbcc")

    def test_text_settings_are_trimmed(self):
        self.assertEqual(schema.coerce_settings({"gui_font_family": "  Arial  "})["gui_font_family"], "Arial")
        self.assertEqual(schema.coerce_game_profile({"link_prefix": "  zz_  "})["link_prefix"], "zz_")

    def test_keys_that_are_absent_are_left_alone(self):
        self.assertEqual(schema.coerce_settings({"page_size": "5"}), {"page_size": 5})

    def test_per_game_values_are_ignored_by_the_settings_coercion(self):
        self.assertEqual(schema.coerce_settings({"page_size": "5", "link_prefix": "zz_"}), {"page_size": 5})

    def test_game_profile_coercion_covers_the_profile_fields(self):
        result = schema.coerce_game_profile({"name": " Skyrim ", "mod_recursive_scan": True, "page_size": "9"})
        self.assertEqual(result, {"name": "Skyrim", "mod_recursive_scan": True})


if __name__ == "__main__":
    unittest.main()
