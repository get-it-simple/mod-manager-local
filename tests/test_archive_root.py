from __future__ import annotations

from pathlib import Path
import unittest
from zipfile import ZipFile

from tests.cli_support import CliEnvironment
from mod_manager import storage
from mod_manager.import_preview import destination_rows, preview_plans
from mod_manager.imports import create_plans, execute_plans, prepare_archive, set_archive_root


class ArchiveRootTests(CliEnvironment, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.cfg = storage.load_config()
        self.cfg.update(archive_import_mode="together", archive_preserve_structure=True)
        self.archive = self.root / "Pack.zip"
        with ZipFile(self.archive, "w") as archive:
            archive.writestr("wrapper/data/sub/mod.pak", b"chosen")
            archive.writestr("wrapper/data/other.pak", b"chosen-too")
            archive.writestr("wrapper/outside.pak", b"outside")
        self.prepared = prepare_archive(self.archive, self.cfg)
        self.addCleanup(self.prepared.close)

    def test_chosen_subtree_is_rebased_in_preview_and_published_payload(self):
        before = self.archive.read_bytes()
        set_archive_root(self.prepared, Path("wrapper/data"))
        plans = preview_plans([self.prepared])
        self.assertEqual(destination_rows(str(self.source), plans), [
            (str(self.source), "Pack", "other.pak"), (str(self.source), "Pack", "sub", "mod.pak")])
        imported, errors = execute_plans(self.cfg, plans)
        self.assertEqual(imported, ["Pack"])
        self.assertEqual(errors, [])
        self.assertEqual((self.source / "Pack/sub/mod.pak").read_bytes(), b"chosen")
        self.assertEqual((self.source / "Pack/other.pak").read_bytes(), b"chosen-too")
        self.assertFalse((self.source / "Pack/wrapper").exists())
        self.assertEqual(self.archive.read_bytes(), before)

    def test_reset_and_other_modes_preserve_their_original_behavior(self):
        set_archive_root(self.prepared, Path("wrapper/data"))
        self.prepared.preserve_structure = False
        flat, = create_plans([self.prepared], lambda _name: "keep_both")
        self.assertEqual(self.prepared.import_root, Path("wrapper/data"))
        self.assertEqual({relative.as_posix() for _source, relative in flat.files},
                         {"mod.pak", "other.pak", "outside.pak"})
        self.prepared.preserve_structure = True
        self.prepared.mode = "separate"
        plans = create_plans([self.prepared], lambda _name: "keep_both")
        self.assertEqual(len(plans), 3)
        self.prepared.mode = "together"
        set_archive_root(self.prepared, Path("."))
        root, = preview_plans([self.prepared])
        self.assertIn(Path("wrapper/outside.pak"), [relative for _source, relative in root.files])

    def test_root_must_be_an_existing_archive_directory(self):
        for relative in (Path(".."), Path("missing"), Path("wrapper/data/other.pak"), self.root):
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                set_archive_root(self.prepared, relative)
