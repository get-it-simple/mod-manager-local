from __future__ import annotations

import ctypes
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mod_manager import links, windows_links
from mod_manager.platform_utils import is_junction


@unittest.skipUnless(os.name == "nt", "Windows junction API")
class WindowsJunctionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "源目录😀"
        self.source.mkdir()
        self.payload = self.source / "data.bin"
        self.payload.write_bytes(b"synthetic payload")
        self.target = self.root / "目标😀"
        self.kernel = windows_links._kernel32()

    def denied(self, *args):
        ctypes.set_last_error(5)
        return False

    def test_failed_reparse_write_closes_the_handle_and_removes_only_the_new_directory(self):
        with patch.object(self.kernel, "DeviceIoControl", side_effect=self.denied), patch.object(
            self.kernel, "CloseHandle", wraps=self.kernel.CloseHandle,
        ) as close:
            with self.assertRaises(PermissionError):
                windows_links.create_junction(self.source, self.target)
        close.assert_called_once()
        self.assertFalse(os.path.lexists(self.target))
        self.assertEqual(self.payload.read_bytes(), b"synthetic payload")

    def test_failed_open_removes_the_new_directory_without_closing_an_invalid_handle(self):
        def failed_open(*args):
            ctypes.set_last_error(5)
            return windows_links.INVALID_HANDLE_VALUE

        with patch.object(self.kernel, "CreateFileW", side_effect=failed_open), patch.object(
            self.kernel, "CloseHandle", wraps=self.kernel.CloseHandle,
        ) as close:
            with self.assertRaises(PermissionError):
                windows_links.create_junction(self.source, self.target)
        close.assert_not_called()
        self.assertFalse(os.path.lexists(self.target))
        self.assertEqual(self.payload.read_bytes(), b"synthetic payload")

    def test_existing_directory_and_junction_are_never_replaced_or_cleaned(self):
        self.target.mkdir()
        occupied = self.target / "keep.bin"
        occupied.write_bytes(b"keep")
        with self.assertRaises(FileExistsError):
            windows_links.create_junction(self.source, self.target)
        self.assertEqual(occupied.read_bytes(), b"keep")
        occupied.unlink()
        self.target.rmdir()
        windows_links.create_junction(self.source, self.target)
        with self.assertRaises(FileExistsError):
            windows_links.create_junction(self.source, self.target)
        self.assertTrue(is_junction(self.target))
        self.assertTrue(os.path.samefile(self.source, self.target))
        self.assertEqual(links.unlink_path(self.target), (True, "OK"))
        self.assertEqual(self.payload.read_bytes(), b"synthetic payload")

    def test_cleanup_failure_reports_both_errors_and_preserves_sources(self):
        with patch.object(self.kernel, "DeviceIoControl", side_effect=self.denied), patch(
            "mod_manager.windows_links.os.rmdir", side_effect=OSError("Synthetic cleanup failure"),
        ):
            ok, message = links.mklink(self.source, self.target)
        self.assertFalse(ok)
        self.assertIn("5", message)
        self.assertIn("Synthetic cleanup failure", message)
        self.assertIn(str(self.target), message)
        self.assertTrue(self.target.is_dir())
        self.assertFalse(is_junction(self.target))
        self.assertEqual(self.payload.read_bytes(), b"synthetic payload")

    def test_broken_junction_is_an_occupied_destination(self):
        windows_links.create_junction(self.source, self.target)
        self.payload.unlink()
        self.source.rmdir()
        replacement = self.root / "replacement"
        replacement.mkdir()
        ok, message = links.mklink(replacement, self.target)
        self.assertFalse(ok)
        self.assertIn("Target already exists", message)
        self.assertTrue(is_junction(self.target))
        self.assertFalse(self.target.exists())
        self.assertEqual(links.unlink_path(self.target), (True, "OK"))
        self.assertTrue(replacement.is_dir())
