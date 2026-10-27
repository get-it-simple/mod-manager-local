from __future__ import annotations

import tempfile
import unittest
from functools import partial
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6 import QtCore, QtGui

from mod_manager.ui import image_clipboard as clipboard_images
from tests.qt_support import qt_app


class ClipboardImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.clipboard = Mock()
        self.clipboard.image.return_value = QtGui.QImage()
        self.clipboard.mimeData.return_value = QtCore.QMimeData()
        clipboard_patch = patch.object(clipboard_images.QtWidgets.QApplication, "clipboard", return_value=self.clipboard)
        clipboard_patch.start()
        self.addCleanup(clipboard_patch.stop)
        native_patch = patch.object(clipboard_images, "read_native_clipboard_image", return_value=None)
        self.native = native_patch.start()
        self.addCleanup(native_patch.stop)
        files_patch = patch.object(clipboard_images.tempfile, "NamedTemporaryFile", partial(tempfile.NamedTemporaryFile, dir=self.root))
        files_patch.start()
        self.addCleanup(files_patch.stop)

    def test_qt_bitmap_without_png_or_files_preserves_pixels_and_alpha(self):
        image = QtGui.QImage(3, 2, QtGui.QImage.Format_RGBA8888)
        colors = ("red", "green", "blue", "white", "black", "yellow")
        for index, name in enumerate(colors):
            color = QtGui.QColor(name)
            color.setAlpha(40 + index * 40)
            image.setPixelColor(index % 3, index // 3, color)
        mime = self.clipboard.mimeData.return_value
        mime.setImageData(image)
        self.clipboard.image.return_value = image

        self.assertEqual(mime.formats(), ["application/x-qt-image"])
        self.assertTrue(clipboard_images.clipboard_has_image())
        path = clipboard_images.read_clipboard_image()

        self.assertEqual(path.suffix, ".png")
        decoded = QtGui.QImage(str(path))
        self.assertEqual(decoded.convertToFormat(QtGui.QImage.Format_RGBA8888), image)
        self.native.assert_not_called()

    def test_null_qt_image_uses_existing_native_fallback(self):
        path = self.root / "native.png"
        image = QtGui.QImage(2, 3, QtGui.QImage.Format_RGB32)
        image.fill(QtGui.QColor("blue"))
        self.assertTrue(image.save(str(path)))
        self.native.return_value = path

        result = clipboard_images.read_clipboard_image()

        self.assertEqual(result, path)
        self.assertEqual(QtGui.QImage(str(result)), image)
        self.native.assert_called_once()

    def test_absent_image_and_text_do_not_create_files(self):
        self.clipboard.mimeData.return_value.setText("search text")
        self.assertFalse(clipboard_images.clipboard_has_image())
        self.assertIsNone(clipboard_images.read_clipboard_image())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_missing_mime_data_is_not_an_image(self):
        self.clipboard.mimeData.return_value = None
        self.assertFalse(clipboard_images.clipboard_has_image())

    def test_invalid_image_data_does_not_create_a_png(self):
        mime = self.clipboard.mimeData.return_value
        mime.setData("image/png", b"broken image")
        self.assertIsNone(clipboard_images.read_clipboard_image())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_png_write_failure_removes_partial_file(self):
        image = QtGui.QImage(2, 2, QtGui.QImage.Format_RGB32)
        image.fill(QtGui.QColor("red"))
        self.clipboard.image.return_value = image

        def fail_save(_image, destination, _format):
            Path(destination).write_bytes(b"partial")
            return False

        with patch.object(QtGui.QImage, "save", fail_save):
            with self.assertRaisesRegex(OSError, "Cannot prepare"):
                clipboard_images.read_clipboard_image()

        self.assertEqual(list(self.root.iterdir()), [])
        self.native.assert_not_called()

    def test_temp_creation_failure_is_reported(self):
        self.clipboard.image.return_value = QtGui.QImage(2, 2, QtGui.QImage.Format_RGB32)
        with patch.object(clipboard_images.tempfile, "NamedTemporaryFile", side_effect=PermissionError("unwritable")):
            with self.assertRaisesRegex(PermissionError, "unwritable"):
                clipboard_images.read_clipboard_image()
        self.assertEqual(list(self.root.iterdir()), [])
