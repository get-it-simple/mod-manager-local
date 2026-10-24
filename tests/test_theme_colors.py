from __future__ import annotations

import unittest

from mod_manager.ui.theme import colors, tokens
from mod_manager.ui.theme.stylesheet import build_stylesheet

def contrast(first: str, second: str) -> float:
    def relative(value):
        channels = [part / 255 for part in colors.hex_to_rgb(value)]
        linear = [part / 12.92 if part <= 0.04045 else ((part + 0.055) / 1.055) ** 2.4 for part in channels]
        return sum(channel * weight for channel, weight in zip(linear, (0.2126, 0.7152, 0.0722)))
    one, two = sorted((relative(first), relative(second)))
    return (two + 0.05) / (one + 0.05)


class PaletteDesignTest(unittest.TestCase):
    def test_default_text_and_metadata_are_readable_on_each_surface(self):
        for mode in ("light", "dark"):
            palette = colors.build_palette(mode)
            for surface in (palette.bg, palette.panel, palette.alt_panel):
                with self.subTest(mode=mode, surface=surface):
                    self.assertGreaterEqual(contrast(palette.fg, surface), 7)
                    self.assertGreaterEqual(contrast(palette.muted, surface), 4.5)

    def test_light_and_dark_have_distinct_surfaces(self):
        light, dark = (colors.build_palette(mode) for mode in ("light", "dark"))
        self.assertFalse(colors.is_dark_color(light.bg))
        self.assertTrue(colors.is_dark_color(dark.bg))
        for palette in (light, dark):
            self.assertNotEqual(palette.bg, palette.panel)
            self.assertNotEqual(palette.border, palette.panel)

    def test_cards_and_placeholders_are_opaque_matte_surfaces(self):
        for mode in ("light", "dark"):
            palette = colors.build_palette(mode)
            self.assertEqual(palette.tile_base.alpha, 255)
            self.assertEqual(palette.tile_base_selected.alpha, 255)
            self.assertEqual(palette.placeholder_bg.alpha, 255)

    def test_accent_colors_are_derived_from_the_accent(self):
        palette = colors.build_palette("dark", "#2563eb")
        self.assertEqual(palette.accent, "#2563eb")
        self.assertEqual(palette.accent_text, "#ffffff")
        self.assertEqual(palette.accent_fill, "rgba(37, 99, 235, 30)")
        self.assertEqual(palette.accent_border, "rgba(37, 99, 235, 170)")

    def test_a_bright_accent_gets_dark_readable_text(self):
        palette = colors.build_palette("light", "#fefefe")
        self.assertEqual(palette.accent_text, "#000000")

    def test_an_invalid_accent_falls_back(self):
        for value in ("", None, "not-a-color", "#12345"):
            self.assertEqual(colors.build_palette("dark", value).accent, colors.FALLBACK_ACCENT)

    def test_light_and_dark_define_exactly_the_same_keys(self):
        self.assertEqual(set(colors.LIGHT_BASE), set(colors.DARK_BASE))
        self.assertEqual(set(colors.LIGHT_TRANSLUCENT), set(colors.DARK_TRANSLUCENT))

    def test_unknown_mode_resolves_to_light(self):
        self.assertEqual(colors.build_palette("system").mode, "light")
        self.assertFalse(colors.build_palette("system").is_dark)
        self.assertTrue(colors.build_palette("dark").is_dark)

    def test_table_selection_uses_a_soft_accent_and_retains_readable_text(self):
        palette = colors.build_palette("dark", "#2563eb")
        stylesheet = build_stylesheet(palette)
        self.assertIn(f"background-color: {palette.accent_fill}; color: {palette.fg};", stylesheet)
        self.assertIn("QTableView::item:focus", stylesheet)
        self.assertIn(f"border-color: {palette.accent}", stylesheet)


class TextOverrideTest(unittest.TestCase):
    def test_custom_text_color_replaces_every_text_role(self):
        palette = colors.build_palette("dark", colors.FALLBACK_ACCENT, "#ff0000")
        for name in colors.TEXT_OVERRIDE_FIELDS:
            self.assertEqual(getattr(palette, name), "#ff0000", name)

    def test_custom_text_color_leaves_surfaces_untouched(self):
        palette = colors.build_palette("dark", colors.FALLBACK_ACCENT, "#ff0000")
        self.assertEqual(palette.bg, colors.build_palette("dark").bg)
        self.assertEqual(palette.panel, colors.build_palette("dark").panel)

    def test_invalid_text_override_is_ignored(self):
        palette = colors.build_palette("dark", colors.FALLBACK_ACCENT, "nonsense")
        self.assertEqual(palette.fg, colors.build_palette("dark").fg)


class ColorMathTest(unittest.TestCase):
    def test_normalize_hex_accepts_short_and_long_forms(self):
        self.assertEqual(colors.normalize_hex("#ABC"), "#aabbcc")
        self.assertEqual(colors.normalize_hex("  #A1B2C3 "), "#a1b2c3")
        self.assertIsNone(colors.normalize_hex("a1b2c3"))
        self.assertIsNone(colors.normalize_hex("#zzzzzz"))

    def test_hex_and_rgb_round_trip(self):
        self.assertEqual(colors.hex_to_rgb("#1e293b"), (30, 41, 59))
        self.assertEqual(colors.rgb_to_hex(30, 41, 59), "#1e293b")

    def test_rgb_to_hex_clamps_out_of_range_values(self):
        self.assertEqual(colors.rgb_to_hex(-5, 300, 128), "#00ff80")

    def test_blend_interpolates_between_two_colors(self):
        self.assertEqual(colors.blend("#000000", "#ffffff", 0.0), "#ffffff")
        self.assertEqual(colors.blend("#000000", "#ffffff", 1.0), "#000000")
        self.assertEqual(colors.blend("#000000", "#ffffff", 0.5), "#808080")

    def test_readable_on_picks_a_contrasting_text_color(self):
        self.assertEqual(colors.readable_on("#ffffff"), "#000000")
        self.assertEqual(colors.readable_on("#000000"), "#ffffff")

    def test_is_dark_color_matches_the_luminance_threshold(self):
        self.assertTrue(colors.is_dark_color("#202124"))
        self.assertFalse(colors.is_dark_color("#f8fafc"))

    def test_mode_normalizers_reject_unknown_values(self):
        self.assertEqual(colors.normalize_mode("DARK"), "dark")
        self.assertEqual(colors.normalize_mode("nope"), "system")
        self.assertEqual(colors.normalize_color_mode("Custom"), "custom")
        self.assertEqual(colors.normalize_color_mode(None), "system")


class TokenTest(unittest.TestCase):
    def test_column_specs_are_well_formed(self):
        specs = (tokens.MOD_COLUMNS, tokens.PRESET_COLUMNS, tokens.BROKEN_COLUMNS)
        resize_modes = {tokens.RESIZE_FIXED, tokens.RESIZE_STRETCH, tokens.RESIZE_CONTENTS}
        alignments = {tokens.ALIGN_LEFT, tokens.ALIGN_CENTER, tokens.ALIGN_RIGHT}
        for columns in specs:
            self.assertTrue(columns)
            for key, title, resize, align in columns:
                self.assertTrue(key)
                self.assertIsInstance(title, str)
                self.assertIn(resize, resize_modes)
                self.assertIn(align, alignments)

    def test_clamp_tile_size_stays_within_bounds(self):
        self.assertEqual(tokens.clamp_tile_size(10), tokens.TILE_SIZE_MIN)
        self.assertEqual(tokens.clamp_tile_size(9999), tokens.TILE_SIZE_MAX)
        self.assertEqual(tokens.clamp_tile_size(140), 140)
        self.assertEqual(tokens.clamp_tile_size(None), tokens.TILE_SIZE_MIN)
        self.assertEqual(tokens.clamp_tile_size("junk"), tokens.TILE_SIZE_MIN)

    def test_tile_item_size_adds_the_card_padding(self):
        self.assertEqual(tokens.tile_item_size(140), (140 + tokens.TILE_EXTRA_WIDTH, 140 + tokens.TILE_EXTRA_HEIGHT))

    def test_scaled_clamps_the_percentage(self):
        self.assertEqual(tokens.scaled(100, 100), 100)
        self.assertEqual(tokens.scaled(100, 200), 200)
        self.assertEqual(tokens.scaled(100, 10), tokens.SCALE_MIN)
        self.assertEqual(tokens.scaled(100, "junk"), 100)


if __name__ == "__main__":
    unittest.main()
