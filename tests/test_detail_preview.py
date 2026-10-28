from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6 import QtCore, QtGui, QtWidgets

from mod_manager.ui.theme import tokens
from mod_manager.ui.theme.colors import build_palette
from mod_manager.ui.theme.stylesheet import build_stylesheet
from mod_manager.ui.widgets.detail_view import DetailImageLabel, DetailPanel
from tests.qt_support import dispose, qt_app
from tests.window_fixture import WindowTestCase


def artwork(width: int, height: int) -> QtGui.QPixmap:
    image = QtGui.QPixmap(width, height)
    image.fill(QtGui.QColor("red"))
    painter = QtGui.QPainter(image)
    painter.fillRect(width // 2, 0, width - width // 2, height, QtGui.QColor("blue"))
    painter.end()
    return image


def settle(app) -> None:
    for _ in range(12):
        app.processEvents()


class DetailPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def panel(self, source_size=(80, 160), panel_size=(420, 800)):
        panel = DetailPanel()
        self.addCleanup(dispose, panel)
        panel.resize(*panel_size)
        panel.add_heading("Preview mod", lambda: None)
        panel.add_text_row("Status", "Not installed")
        image = DetailImageLabel(artwork(*source_size))
        panel.add_widget(image)
        panel.add_stretch()
        panel.show()
        settle(self.app)
        return panel, image

    def assert_fits(self, panel, image, source_size):
        pixmap = image.pixmap()
        self.assertFalse(pixmap.isNull())
        size = pixmap.deviceIndependentSize()
        self.assertLessEqual(size.width(), panel.available_width())
        bottom = image.mapTo(panel.viewport(), QtCore.QPoint(0, image.height())).y()
        self.assertLessEqual(bottom, panel.viewport().height() - tokens.DETAIL_MARGIN)
        if source_size[0] >= source_size[1]:
            self.assertAlmostEqual(size.height(), size.width() * source_size[1] / source_size[0], delta=1)
        else:
            self.assertAlmostEqual(size.width(), size.height() * source_size[0] / source_size[1], delta=1)
        self.assertEqual(image.alignment(), QtCore.Qt.AlignHCenter | QtCore.Qt.AlignTop)
        pixels = pixmap.toImage()
        self.assertEqual(pixels.pixelColor(0, 0), QtGui.QColor("red"))
        self.assertEqual(pixels.pixelColor(pixels.width() - 1, pixels.height() - 1), QtGui.QColor("blue"))

    def test_small_images_enlarge_beyond_old_height_limit_without_cropping(self):
        for size in ((80, 160), (160, 80), (80, 80)):
            with self.subTest(size=size):
                panel, image = self.panel(size)
                self.assertGreater(image.pixmap().height(), 180)
                self.assertGreater(image.pixmap().width(), size[0])
                self.assert_fits(panel, image, size)
                panel.hide()

    def test_portrait_uses_remaining_height_and_landscape_uses_available_width(self):
        portrait, portrait_image = self.panel((400, 1600), (420, 650))
        self.assert_fits(portrait, portrait_image, (400, 1600))
        bottom = portrait_image.mapTo(portrait.viewport(), QtCore.QPoint(0, portrait_image.height())).y()
        self.assertAlmostEqual(bottom, portrait.viewport().height() - tokens.DETAIL_MARGIN, delta=1)
        landscape, landscape_image = self.panel((1600, 400))
        self.assert_fits(landscape, landscape_image, (1600, 400))
        self.assertAlmostEqual(landscape_image.pixmap().width(), landscape.available_width() - tokens.DETAIL_IMAGE_INSET, delta=1)

    def test_resize_shrinks_and_restores_preview_without_layout_oscillation(self):
        panel, image = self.panel((400, 1600), (420, 800))
        original = image.pixmap().size()
        original_pixels = image.pixmap().toImage()
        for _ in range(3):
            panel.resize(300, 400)
            settle(self.app)
            self.assertLess(image.pixmap().height(), original.height())
            self.assert_fits(panel, image, (400, 1600))
            panel.resize(420, 800)
            settle(self.app)
            self.assertEqual(image.pixmap().size(), original)
            self.assertEqual(image.pixmap().toImage(), original_pixels)
            self.assert_fits(panel, image, (400, 1600))
        geometry = (image.geometry(), panel.viewport().size(), panel.verticalScrollBar().maximum())
        settle(self.app)
        self.assertEqual((image.geometry(), panel.viewport().size(), panel.verticalScrollBar().maximum()), geometry)
        self.assertEqual(panel.verticalScrollBar().maximum(), 0)

    def test_width_changes_resize_landscape_preview(self):
        panel, image = self.panel((1600, 400), (420, 800))
        original = image.pixmap().size()
        panel.resize(300, 800)
        settle(self.app)
        self.assertLess(image.pixmap().width(), original.width())
        self.assert_fits(panel, image, (1600, 400))
        panel.resize(420, 800)
        settle(self.app)
        self.assertEqual(image.pixmap().size(), original)

    def test_wrapped_metadata_and_font_changes_reduce_available_image_height(self):
        self.addCleanup(self.app.setStyleSheet, self.app.styleSheet())
        self.addCleanup(self.app.setFont, self.app.font())
        for theme in (None, "light", "dark"):
            with self.subTest(theme=theme):
                stylesheet = build_stylesheet(build_palette(theme)) if theme else ""
                font = self.app.font()
                font.setPointSize(10)
                self.app.setFont(font)
                self.app.setStyleSheet(stylesheet)
                panel, image = self.panel((400, 1600), (420, 900))
                original = image.height()
                panel.layout.insertWidget(2, QtWidgets.QLabel("A long mod description " * 12))
                description = panel.layout.itemAt(2).widget()
                description.setWordWrap(True)
                settle(self.app)
                self.assertEqual(description.font().pointSize(), 10)
                self.assertLess(image.height(), original)
                before_font = image.height()
                font.setPointSize(16)
                self.app.setFont(font)
                self.app.setStyleSheet(stylesheet)
                settle(self.app)
                self.assertEqual(description.font().pointSize(), 16)
                self.assertLess(image.height(), before_font)
                self.assert_fits(panel, image, (400, 1600))
                self.assertGreaterEqual(description.height(), description.heightForWidth(description.width()))
                panel.hide()

    def test_long_heading_wraps_without_overlapping_preview(self):
        panel, image = self.panel((400, 1600), (300, 800))
        original = image.height()
        heading = panel.layout.itemAt(0).layout().itemAt(0).widget()
        heading.setText("Long mod name with several words " * 5)
        settle(self.app)
        self.assertLess(image.height(), original)
        self.assertGreaterEqual(heading.height(), heading.heightForWidth(heading.width()))
        self.assert_fits(panel, image, (400, 1600))

    def test_metadata_overflow_still_scrolls_and_scrolling_does_not_rescale(self):
        panel, image = self.panel((400, 1600), (300, 120))
        for index in range(12):
            panel.layout.insertWidget(index, QtWidgets.QPushButton(f"Action {index}"))
        settle(self.app)
        self.assertGreater(panel.verticalScrollBar().maximum(), 0)
        self.assertEqual(panel.image_target_size(image).height(), 1)
        size = image.pixmap().size()
        self.assertFalse(image.pixmap().isNull())
        panel.verticalScrollBar().setValue(panel.verticalScrollBar().maximum())
        settle(self.app)
        self.assertEqual(image.pixmap().size(), size)
        for button in panel.frame.findChildren(QtWidgets.QPushButton):
            self.assertGreaterEqual(button.height(), button.minimumSizeHint().height())
        panel.resize(420, 1000)
        settle(self.app)
        self.assertGreater(image.height(), 180)
        self.assert_fits(panel, image, (400, 1600))

    def test_one_pixel_target_does_not_fall_back_to_source_height(self):
        image = DetailImageLabel(artwork(80, 160))
        self.addCleanup(dispose, image)
        image.update_scaled_pixmap(QtCore.QSize(300, 1))
        self.assertLessEqual(image.pixmap().height(), 1)
        self.assertFalse(image.pixmap().isNull())

    def test_high_dpi_pixmap_fits_logical_area(self):
        panel, image = self.panel()
        source = artwork(160, 320)
        source.setDevicePixelRatio(2)
        panel.clear()
        image = DetailImageLabel(source)
        panel.add_widget(image)
        settle(self.app)
        self.assertEqual(image.height(), round(image.pixmap().deviceIndependentSize().height()))
        self.assert_fits(panel, image, (160, 320))


class DetailPreviewWindowTests(WindowTestCase):
    def test_preview_fits_after_view_switch_hiding_and_reopening(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preview.png"
            self.assertTrue(artwork(80, 160).save(str(path)))
            with patch("mod_manager.ui.app.mod_image_path", return_value=path):
                self.window.images.invalidate("combat.pak")
                self.window.resize(1200, 1100)
                self.window.show()
                self.select_mod_rows(0)
                settle(self.qt_app)
                image = self.window.detail_frame.findChild(DetailImageLabel)
                self.assertIsNotNone(image)
                self.assertGreater(image.height(), 180)
                for mode in ("tiles", "list"):
                    self.window._set_view_mode(mode)
                    self.window.details_button.click()
                    self.window.resize(1000, 950)
                    self.window.details_button.click()
                    settle(self.qt_app)
                    image = self.window.detail_frame.findChild(DetailImageLabel)
                    self.assertFalse(image.pixmap().isNull())
                    panel = self.window.detail_scroll
                    bottom = image.mapTo(panel.viewport(), QtCore.QPoint(0, image.height())).y()
                    self.assertLessEqual(bottom, panel.viewport().height() - tokens.DETAIL_MARGIN)
                    self.assertEqual(panel.verticalScrollBar().maximum(), 0)
