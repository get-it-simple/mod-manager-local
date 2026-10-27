from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.qt_support import qt_app, qt_available
from tests.gui_background import InlineRunner

from mod_manager.models import ModItem

if qt_available():
    from PySide6 import QtCore, QtGui, QtWidgets

    from mod_manager.ui.models import BrokenTableModel, FavoriteDelegate, ModTableModel, PresetTableModel, TileDelegate, configure_header
    from mod_manager.ui.models import columns as columns_module
    from mod_manager.ui.image_cache import ImageCache
    from mod_manager.ui.theme import colors, tokens

SRC = Path(tempfile.gettempdir()) / "mm_model_source"
DEST = Path(tempfile.gettempdir()) / "mm_model_game"


def mods() -> list[ModItem]:
    return [
        ModItem("combat.pak", SRC / "combat.pak", DEST / "combat.pak", False, True),
        ModItem("ui.pak", SRC / "ui.pak", DEST / "ui.pak", False, False),
    ]


@unittest.skipUnless(qt_available(), "PySide6 is not installed")
class ModTableModelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = qt_app()

    def setUp(self) -> None:
        self.model = ModTableModel(colors.FALLBACK_ACCENT)
        self.model.set_data(mods(), {"combat.pak": "combat"}, {"combat.pak": {"last_managed": "2026-01-02"}})

    def test_headers_come_from_the_column_tokens(self):
        self.assertEqual(ModTableModel.HEADERS, ("", "Name", "Label", "Last managed"))
        self.assertEqual(self.model.columnCount(), len(tokens.MOD_COLUMNS))

    def test_rows_expose_name_label_and_last_managed(self):
        self.assertEqual(self.model.rowCount(), 2)
        self.assertEqual(self.model.data(self.model.index(0, 1)), "combat.pak")
        self.assertEqual(self.model.data(self.model.index(0, 2)), "combat")
        self.assertEqual(self.model.data(self.model.index(0, 3)), "2026-01-02")

    def test_missing_label_and_date_render_as_a_dash(self):
        self.assertEqual(self.model.data(self.model.index(1, 2)), "-")
        self.assertEqual(self.model.data(self.model.index(1, 3)), "-")

    def test_user_role_returns_the_mod_item(self):
        self.assertEqual(self.model.data(self.model.index(1, 0), QtCore.Qt.UserRole).name, "ui.pak")

    def test_installed_state_is_shown_with_a_check_icon(self):
        installed = self.model.data(self.model.index(0, 0), QtCore.Qt.DecorationRole)
        not_installed = self.model.data(self.model.index(1, 0), QtCore.Qt.DecorationRole)
        self.assertIsNot(installed, not_installed)
        self.assertFalse(installed.isNull())

    def test_invalid_index_returns_nothing(self):
        self.assertIsNone(self.model.data(QtCore.QModelIndex()))

    def test_refresh_accent_rebuilds_the_icons(self):
        before = self.model._installed_icon
        self.model.refresh_accent("#ff0000")
        self.assertIsNot(before, self.model._installed_icon)


@unittest.skipUnless(qt_available(), "PySide6 is not installed")
class PresetTableModelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = qt_app()

    def setUp(self) -> None:
        self.model = PresetTableModel(colors.build_palette("dark"))
        self.model.set_data(
            {"core": ["combat.pak", "ui.pak"], "extra": ["missing.pak"], "empty": []},
            ["core", "extra", "empty"],
            {"core": {"last_managed": "2026-01-03"}},
            {"combat.pak", "ui.pak"},
        )

    def test_headers_come_from_the_column_tokens(self):
        self.assertEqual(PresetTableModel.HEADERS, ("Preset", "State", "Mods", "Last managed"))

    def test_a_preset_is_active_when_every_mod_is_installed(self):
        self.assertTrue(self.model.is_active("core"))
        self.assertFalse(self.model.is_active("extra"))

    def test_an_empty_preset_is_never_active(self):
        self.assertFalse(self.model.is_active("empty"))

    def test_state_column_reports_active_through_the_user_role(self):
        self.assertEqual(self.model.data(self.model.index(0, 1), QtCore.Qt.UserRole), "active")
        self.assertEqual(self.model.data(self.model.index(1, 1), QtCore.Qt.UserRole), "inactive")

    def test_mod_count_and_last_managed_are_shown(self):
        self.assertEqual(self.model.data(self.model.index(0, 0)), "core")
        self.assertEqual(self.model.data(self.model.index(0, 2)), "2")
        self.assertEqual(self.model.data(self.model.index(0, 3)), "2026-01-03")
        self.assertEqual(self.model.data(self.model.index(1, 3)), "-")

    def test_state_icons_change_with_the_palette(self):
        before = self.model._active_icon
        self.model.set_palette(colors.build_palette("light"))
        self.assertIsNot(before, self.model._active_icon)


@unittest.skipUnless(qt_available(), "PySide6 is not installed")
class BrokenTableModelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = qt_app()

    def setUp(self) -> None:
        self.model = BrokenTableModel()
        self.model.set_data(mods())

    def test_headers_and_columns(self):
        self.assertEqual(BrokenTableModel.HEADERS, ("Broken link", "Destination"))
        self.assertEqual(self.model.columnCount(), 2)

    def test_rows_show_the_name_and_the_destination(self):
        self.assertEqual(self.model.data(self.model.index(0, 0)), "combat.pak")
        self.assertEqual(self.model.data(self.model.index(0, 1)), str(DEST / "combat.pak"))

    def test_user_role_returns_the_mod_item(self):
        self.assertEqual(self.model.data(self.model.index(0, 0), QtCore.Qt.UserRole).name, "combat.pak")


@unittest.skipUnless(qt_available(), "PySide6 is not installed")
class ConfigureHeaderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = qt_app()

    def test_resize_modes_follow_the_column_spec(self):
        view = QtWidgets.QTableView()
        view.setModel(ModTableModel(colors.FALLBACK_ACCENT))
        configure_header(view, tokens.MOD_COLUMNS)
        header = view.horizontalHeader()
        self.assertEqual(header.sectionResizeMode(0), QtWidgets.QHeaderView.Fixed)
        self.assertEqual(header.sectionResizeMode(1), QtWidgets.QHeaderView.Stretch)
        self.assertEqual(header.sectionResizeMode(2), QtWidgets.QHeaderView.ResizeToContents)
        self.assertFalse(header.stretchLastSection())
        self.assertFalse(view.verticalHeader().isVisible())
        self.assertFalse(view.showGrid())

    def test_fixed_widths_are_applied_by_column_key(self):
        view = QtWidgets.QTableView()
        view.setModel(ModTableModel(colors.FALLBACK_ACCENT))
        configure_header(view, tokens.MOD_COLUMNS, {"installed": 72})
        self.assertEqual(view.horizontalHeader().sectionSize(0), 72)

    def test_column_helpers_read_the_spec(self):
        self.assertEqual(columns_module.keys(tokens.BROKEN_COLUMNS), ("name", "dest"))
        self.assertEqual(columns_module.titles(tokens.BROKEN_COLUMNS), ("Broken link", "Destination"))


@unittest.skipUnless(qt_available(), "PySide6 is not installed")
class TileDelegateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = qt_app()

    def setUp(self) -> None:
        self.cfg = {"tile_size": 140}
        self.delegate = TileDelegate(self.cfg, colors.build_palette("dark"))

    def test_size_hint_uses_the_tile_tokens(self):
        size = self.delegate.sizeHint(QtWidgets.QStyleOptionViewItem(), QtCore.QModelIndex())
        self.assertEqual((size.width(), size.height()), tokens.tile_item_size(140))

    def test_size_hint_respects_the_minimum_tile_size(self):
        self.cfg["tile_size"] = 10
        size = self.delegate.sizeHint(QtWidgets.QStyleOptionViewItem(), QtCore.QModelIndex())
        self.assertEqual((size.width(), size.height()), tokens.tile_item_size(tokens.TILE_SIZE_MIN))

    def test_label_badge_text_is_truncated_and_skips_placeholders(self):
        self.assertEqual(self.delegate._label_badge_text("a-very-long-label"), "a-very-l")
        self.assertEqual(self.delegate._label_badge_text("-"), "")
        self.assertEqual(self.delegate._label_badge_text("   "), "")

    def test_palette_change_updates_the_badge_colors(self):
        self.delegate.set_palette(colors.build_palette("light", "#ff0000"))
        self.assertEqual(self.delegate.accent_color.name(), "#ff0000")
        self.assertFalse(self.delegate.dark_theme)

    def test_cache_can_be_cleared_entirely_or_per_mod(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.delegate.image_cache = ImageCache(InlineRunner(), lambda _cfg, name: root / f"{name}.png", self.delegate)
            image = QtGui.QImage(10, 10, QtGui.QImage.Format_RGB32)
            for name, color in (("a", "red"), ("b", "blue")):
                image.fill(QtGui.QColor(color))
                self.assertTrue(image.save(str(root / f"{name}.png")))
            a, b = mods()
            a.name, b.name = "a", "b"
            size = QtCore.QSize(10, 10)
            self.assertEqual(self.delegate._pixmap_for(a, size).toImage().pixelColor(0, 0), QtGui.QColor("red"))
            self.assertEqual(self.delegate._pixmap_for(b, size).toImage().pixelColor(0, 0), QtGui.QColor("blue"))
            image.fill(QtGui.QColor("green"))
            for name in ("a", "b"):
                self.assertTrue(image.save(str(root / f"{name}.png")))
            self.delegate.clear_cache("a")
            self.assertEqual(self.delegate._pixmap_for(a, size).toImage().pixelColor(0, 0), QtGui.QColor("green"))
            self.assertEqual(self.delegate._pixmap_for(b, size).toImage().pixelColor(0, 0), QtGui.QColor("blue"))
            self.delegate.clear_cache()
            self.assertEqual(self.delegate._pixmap_for(b, size).toImage().pixelColor(0, 0), QtGui.QColor("green"))
            self.delegate.image_cache.shutdown()

    def test_badges_stay_inside_the_card(self):
        option = QtWidgets.QStyleOptionViewItem()
        option.rect = QtCore.QRect(0, 0, *tokens.tile_item_size(140))
        card = self.delegate._content_rect(option)
        metrics = QtGui.QFontMetrics(QtWidgets.QApplication.instance().font())
        image = self.delegate._image_rect(card)
        self.assertTrue(card.contains(image))
        self.assertTrue(card.contains(self.delegate._label_badge_rect(card, metrics, "label")))
        self.assertTrue(card.contains(self.delegate._name_badge_rect(card, image)))

    def test_tile_favorite_star_handles_clicks(self):
        model = ModTableModel(colors.FALLBACK_ACCENT)
        model.set_data(mods(), {}, {}, {"combat.pak"})
        option = QtWidgets.QStyleOptionViewItem()
        option.rect = QtCore.QRect(0, 0, *tokens.tile_item_size(140))
        card = self.delegate._content_rect(option)
        star = self.delegate._favorite_rect(self.delegate._image_rect(card))
        event = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonRelease,
            QtCore.QPointF(star.center()),
            QtCore.Qt.LeftButton,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
        )
        toggled = []
        self.delegate.favoriteToggled.connect(toggled.append)

        self.assertTrue(self.delegate.editorEvent(event, model, option, model.index(0, 0)))
        self.assertEqual(toggled, ["combat.pak"])


@unittest.skipUnless(qt_available(), "PySide6 is not installed")
class FavoriteDelegateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = qt_app()

    def test_table_favorite_star_handles_clicks(self):
        model = ModTableModel(colors.FALLBACK_ACCENT)
        model.set_data(mods(), {}, {}, {"combat.pak"})
        delegate = FavoriteDelegate()
        delegate.set_favorites({"combat.pak"})
        option = QtWidgets.QStyleOptionViewItem()
        option.rect = QtCore.QRect(0, 0, 240, 32)
        star = delegate.star_rect(option.rect)
        event = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonRelease,
            QtCore.QPointF(star.center()),
            QtCore.Qt.LeftButton,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
        )
        toggled = []
        delegate.favoriteToggled.connect(toggled.append)

        self.assertTrue(delegate.editorEvent(event, model, option, model.index(0, 1)))
        self.assertEqual(toggled, ["combat.pak"])


if __name__ == "__main__":
    unittest.main()
