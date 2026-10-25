from __future__ import annotations

import unittest

from tests.qt_support import dispose, qt_app, qt_available

if qt_available():
    from PySide6 import QtCore, QtWidgets

    from mod_manager.ui import icons
    from mod_manager.ui.theme import colors, tokens
    from mod_manager.ui.widgets import IconToolbar, PageControl, SelectBox, page_text, select_box, icon_button, text_button
    from mod_manager.ui.widgets.style_utils import ACRYLIC, TOOLBAR_SECTION, VARIANT_PROPERTY, apply_margins, clear_layout

SECTIONS = (
    ("page", "Page", (
        ("prev_page", "back", "Previous page"),
        ("next_page", "forward", "Next page"),
    )),
    ("state", "Install", (
        ("install", "install", "Install everything on this page"),
    )),
)


@unittest.skipUnless(qt_available(), "PySide6 is not installed")
class ButtonTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = qt_app()

    def test_icon_button_is_square_with_a_tooltip_and_no_text(self):
        button = icon_button("save", "Save the preset")
        self.assertEqual(button.text(), "")
        self.assertEqual(button.toolTip(), "Save the preset")
        self.assertEqual(button.accessibleName(), "Save the preset")
        self.assertEqual(button.size().width(), tokens.ICON_BUTTON_SIZE)
        self.assertEqual(button.size().height(), tokens.ICON_BUTTON_SIZE)
        self.assertEqual(button.iconSize().width(), tokens.ICON_SIZE)
        self.assertFalse(button.icon().isNull())
        self.assertEqual(button.property(VARIANT_PROPERTY), ACRYLIC)

    def test_icon_button_accessible_name_can_differ_from_the_tooltip(self):
        button = icon_button("save", "Save the preset", accessible_name="Save")
        self.assertEqual(button.accessibleName(), "Save")

    def test_icon_button_runs_its_handler_on_click(self):
        calls = []
        icon_button("save", "Save", lambda: calls.append(True)).click()
        self.assertEqual(calls, [True])

    def test_checkable_icon_button_toggles(self):
        button = icon_button("list", "List view", checkable=True)
        self.assertTrue(button.isCheckable())
        button.setChecked(True)
        self.assertTrue(button.isChecked())

    def test_text_button_keeps_its_label(self):
        button = text_button("Add game", "Add a game profile", icon_name="add")
        self.assertEqual(button.text(), "Add game")
        self.assertEqual(button.accessibleName(), "Add game")
        self.assertFalse(button.icon().isNull())

    def test_every_named_icon_resolves(self):
        for name in set(icons.STANDARD_ICONS) | icons.CUSTOM_ICONS:
            self.assertFalse(icons.standard_icon(name).isNull(), name)


@unittest.skipUnless(qt_available(), "PySide6 is not installed")
class IconToolbarTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = qt_app()

    def setUp(self) -> None:
        self.toolbar = IconToolbar()
        self.toolbar.build(SECTIONS)

    def test_sections_keep_their_declared_order_and_titles(self):
        self.assertEqual(self.toolbar.section_order(), ["page", "state"])
        self.assertEqual([section.title for section in self.toolbar.sections.values()], ["Page", "Install"])

    def test_sections_are_bordered_frames(self):
        for section in self.toolbar.sections.values():
            self.assertIsInstance(section, QtWidgets.QFrame)
            self.assertEqual(section.property(VARIANT_PROPERTY), TOOLBAR_SECTION)

    def test_buttons_are_registered_flat_by_key(self):
        self.assertEqual(set(self.toolbar.buttons), {"prev_page", "next_page", "install"})

    def test_buttons_land_in_their_own_section(self):
        page = self.toolbar.sections["page"]
        self.assertEqual(
            [widget.accessibleName() for widget in page.widgets()],
            ["Previous page", "Next page"],
        )

    def test_embedded_widgets_join_the_section(self):
        section = self.toolbar.sections["state"]
        combo = section.add_widget(QtWidgets.QComboBox())
        self.assertIn(combo, section.widgets())
        self.assertIs(combo.parent(), section)

    def test_connect_wires_handlers_by_key(self):
        calls = []
        self.toolbar.connect({"install": lambda: calls.append("install")})
        self.toolbar.button("install").click()
        self.assertEqual(calls, ["install"])

    def test_connect_ignores_unknown_keys(self):
        self.toolbar.connect({"nope": lambda: None})

    def test_apply_states_enables_and_disables_by_key(self):
        self.toolbar.apply_states({"prev_page": False, "next_page": True, "install": False})
        self.assertFalse(self.toolbar.button("prev_page").isEnabled())
        self.assertTrue(self.toolbar.button("next_page").isEnabled())
        self.assertFalse(self.toolbar.button("install").isEnabled())

    def test_disable_all_turns_every_button_off(self):
        self.toolbar.disable_all()
        self.assertTrue(all(not button.isEnabled() for button in self.toolbar.buttons.values()))

    def test_every_button_has_a_tooltip(self):
        for key, button in self.toolbar.buttons.items():
            self.assertTrue(button.toolTip(), key)


@unittest.skipUnless(qt_available(), "PySide6 is not installed")
class LayoutHelperTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = qt_app()

    def test_apply_margins_accepts_none_int_and_tuple(self):
        layout = apply_margins(QtWidgets.QHBoxLayout(), margins=None)
        self.assertEqual(layout.contentsMargins().left(), 0)
        layout = apply_margins(QtWidgets.QHBoxLayout(), margins=7)
        self.assertEqual(layout.contentsMargins().top(), 7)
        layout = apply_margins(QtWidgets.QHBoxLayout(), margins=(1, 2, 3, 4))
        self.assertEqual(layout.contentsMargins().right(), 3)

    def test_apply_margins_defaults_the_spacing_to_a_token(self):
        self.assertEqual(apply_margins(QtWidgets.QHBoxLayout()).spacing(), tokens.SPACE_MD)

    def test_clear_layout_removes_nested_widgets(self):
        host = QtWidgets.QWidget()
        self.addCleanup(dispose, host)
        layout = QtWidgets.QVBoxLayout(host)
        inner = QtWidgets.QHBoxLayout()
        widgets = [QtWidgets.QLabel("inner"), QtWidgets.QLabel("outer")]
        inner.addWidget(widgets[0])
        layout.addLayout(inner)
        layout.addWidget(widgets[1])
        host.show()
        self.app.processEvents()
        destroyed = []
        for widget in widgets:
            self.assertTrue(widget.isVisible())
            widget.destroyed.connect(lambda: destroyed.append(True))
        clear_layout(layout)
        self.assertEqual(layout.count(), 0)
        for widget in widgets:
            self.assertFalse(widget.isVisible())
            self.assertNotIn(widget, self.app.topLevelWidgets())
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        self.assertEqual(len(destroyed), len(widgets))


@unittest.skipUnless(qt_available(), "PySide6 is not installed")
class PagerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = qt_app()

    def test_page_text_is_formatted_once(self):
        self.assertEqual(page_text(2, 7), "Page 2/7")

    def test_page_control_emits_valid_page_requests(self):
        control = PageControl()
        requested = []
        control.pageRequested.connect(requested.append)
        control.set_page(2, 7)
        control.input.setText("5")
        control.input.returnPressed.emit()
        self.assertEqual(requested, [5])
        self.assertEqual(control.text(), "Page 2/7")

    def test_page_control_rejects_out_of_range_values(self):
        control = PageControl()
        control.set_page(2, 4)
        control.input.setText("9")
        control.input.returnPressed.emit()
        self.assertEqual(control.input.text(), "2")


@unittest.skipUnless(qt_available(), "PySide6 is not installed")
class SelectBoxTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = qt_app()

    def test_select_factory_returns_chevron_painted_combo(self):
        box = select_box(editable=True)
        self.assertIsInstance(box, SelectBox)
        self.assertTrue(box.isEditable())


@unittest.skipUnless(qt_available(), "PySide6 is not installed")
class PaintedIconTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = qt_app()

    def test_check_icon_is_drawn_at_the_requested_size(self):
        icon = icons.check_icon("#ff0000", size=tokens.PREVIEW_ICON_SIZE)
        self.assertFalse(icon.isNull())
        self.assertEqual(icon.availableSizes()[0].width(), tokens.PREVIEW_ICON_SIZE)

    def test_transparent_check_icon_still_reserves_space(self):
        icon = icons.check_icon("#ff0000", transparent=True)
        self.assertEqual(icon.availableSizes()[0].width(), tokens.ICON_SIZE)

    def test_sort_direction_icons_differ_by_direction(self):
        ascending = icons.sort_direction_icon(False, "#ffffff").pixmap(tokens.ICON_SIZE).toImage()
        descending = icons.sort_direction_icon(True, "#ffffff").pixmap(tokens.ICON_SIZE).toImage()
        self.assertNotEqual(ascending, descending)

    def test_semantic_action_icons_are_distinct(self):
        names = ("settings", "delete", "broken", "submit", "edit", "filter_apply", "filter_clear")
        images = [icons.standard_icon(name).pixmap(tokens.ICON_SIZE).toImage() for name in names]
        for index, image in enumerate(images):
            self.assertNotIn(image, images[:index], names[index])

    def test_state_icons_use_the_palette_state_colors(self):
        palette = colors.build_palette("dark")
        self.assertFalse(icons.state_icon(True, palette).isNull())
        self.assertNotEqual(
            icons.state_icon(True, palette).pixmap(tokens.STATE_ICON_SIZE).toImage(),
            icons.state_icon(False, palette).pixmap(tokens.STATE_ICON_SIZE).toImage(),
        )


if __name__ == "__main__":
    unittest.main()
