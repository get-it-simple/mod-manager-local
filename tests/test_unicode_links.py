from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mod_manager import links
from mod_manager.mods import discover_mods
from mod_manager.platform_utils import is_junction
from mod_manager.storage import load_config
from tests.cli_support import CliEnvironment


UNICODE_NAMES = ("中文_Мод_é_e\u0301_😀", "Mod & [v1] (extra) ^ ! %MM_TEST_NAME% \u0027 +,;=")


class UnicodeLinkTests(unittest.TestCase):
    def setUp(self):
        build = Path(__file__).resolve().parents[1] / "build"
        build.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=build, prefix="unicode-links-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / ("source-" + UNICODE_NAMES[0])
        self.game = self.root / ("game-" + UNICODE_NAMES[1])
        self.source.mkdir()
        self.game.mkdir()
        self.environment = patch.dict(os.environ, {"MM_TEST_NAME": "must-not-expand"})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def create_source(self, name, directory):
        source = self.source / name
        if directory:
            source.mkdir()
            (source / UNICODE_NAMES[0]).mkdir()
            payload = source / UNICODE_NAMES[0] / (UNICODE_NAMES[1] + ".bin")
        else:
            payload = source
        payload.write_bytes(name.encode("utf-8"))
        return source, payload

    def assert_link(self, source, destination, directory):
        self.assertEqual(destination.name, source.name)
        self.assertTrue(os.path.samefile(source, destination))
        self.assertTrue(is_junction(destination) if directory and os.name == "nt" else destination.is_symlink())

    def test_single_links_preserve_names_and_source_contents_after_uninstall(self):
        for directory in (False, True):
            for stem in UNICODE_NAMES:
                name = stem + ("" if directory else ".pak")
                with self.subTest(name=name, directory=directory):
                    source, payload = self.create_source(name, directory)
                    destination = self.game / name
                    self.assertEqual(links.mklink(source, destination), (True, "OK"))
                    self.assert_link(source, destination, directory)
                    self.assertEqual(links.unlink_path(destination), (True, "OK"))
                    self.assertFalse(os.path.lexists(destination))
                    self.assertEqual(payload.read_bytes(), name.encode("utf-8"))
        self.assertEqual(list(self.game.iterdir()), [])

    def test_large_mixed_batch_preserves_every_name_target_and_result(self):
        items, payloads = [], []
        for index in range(300):
            directory = index % 2 == 0
            name = f"{index:04d}-" + UNICODE_NAMES[index % len(UNICODE_NAMES)] + ("" if directory else ".pak")
            source, payload = self.create_source(name, directory)
            items.append((source, self.game / name, directory))
            payloads.append((payload, name.encode("utf-8")))
        self.assertEqual(links.mklink_batch(items), [(True, "OK")] * len(items))
        self.assertEqual({path.name for path in self.game.iterdir()}, {source.name for source, _, _ in items})
        for source, destination, directory in items:
            self.assert_link(source, destination, directory)
            self.assertEqual(links.unlink_path(destination), (True, "OK"))
        self.assertEqual(list(self.game.iterdir()), [])
        for payload, expected in payloads:
            self.assertEqual(payload.read_bytes(), expected)

    def test_relative_sources_resolve_from_the_application_working_directory(self):
        for directory in (False, True):
            with self.subTest(directory=directory):
                source, _ = self.create_source("relative-" + str(directory), directory)
                destination = self.game / source.name
                relative = Path(os.path.relpath(source))
                self.assertEqual(links.mklink(relative, destination), (True, "OK"))
                self.assert_link(source, destination, directory)
                self.assertEqual(links.unlink_path(destination), (True, "OK"))


class UnicodeInstallTests(CliEnvironment, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.source = self.source.rename(self.root / UNICODE_NAMES[0])
        self.game = self.game.rename(self.root / UNICODE_NAMES[1])
        self.profile = self.cfg["game_profiles"][0]
        self.profile.update(mods_source_dir=str(self.source), game_mods_dir=str(self.game),
                            mod_extensions=".pak,.utoc,folders", mod_group_extensions=".pak,.utoc",
                            link_prefix="_中文!%MM_TEST_NAME%")
        self.stem = UNICODE_NAMES[0] + UNICODE_NAMES[1]
        self.folder = self.source / (self.stem + "-folder")
        self.folder.mkdir()
        (self.folder / "数据😀.bin").write_bytes(b"synthetic nested payload")
        for extension in (".pak", ".utoc"):
            (self.source / (self.stem + extension)).write_bytes(extension.encode())
        self.write_config()

    def verify_install_cycle(self, mode):
        self.profile["install_mode"] = mode
        self.write_config()
        with patch.dict(os.environ, {"MM_TEST_NAME": "must-not-expand"}):
            code, output, errors = self.request(["mods", "install"])
        self.assertEqual(code, 0, output + errors)
        mods = discover_mods(load_config())
        self.assertEqual({mod.name for mod in mods}, {self.stem + ".pak", self.folder.name})
        self.assertTrue(all(mod.installed for mod in mods))
        destinations = {self.folder.name}
        for extension in (".pak", ".utoc"):
            name = self.stem + self.profile["link_prefix"] + extension
            destinations.add(name)
            source = self.source / (self.stem + extension)
            destination = self.game / name
            self.assertEqual(destination.read_bytes(), source.read_bytes())
            self.assertEqual(os.path.samefile(source, destination), mode == "link")
        self.assertEqual({path.name for path in self.game.iterdir()}, destinations)
        self.assertEqual((self.game / self.folder.name / "数据😀.bin").read_bytes(), b"synthetic nested payload")
        code, output, errors = self.request(["mods", "uninstall"])
        self.assertEqual(code, 0, output + errors)
        self.assertEqual(list(self.game.iterdir()), [])
        self.assertTrue(all(not mod.installed for mod in discover_mods(load_config())))
        for extension in (".pak", ".utoc"):
            self.assertEqual((self.source / (self.stem + extension)).read_bytes(), extension.encode())
        self.assertEqual((self.folder / "数据😀.bin").read_bytes(), b"synthetic nested payload")

    def test_cli_copy_install_and_uninstall_preserve_group_and_folder_names(self):
        self.verify_install_cycle("copy")

    def test_cli_link_install_and_uninstall_preserve_group_and_folder_names(self):
        self.verify_install_cycle("link")
