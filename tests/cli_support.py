from __future__ import annotations

import io
import json
import tempfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from mod_manager.cli import run_cli


class CliEnvironment:
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        self.game = self.root / "game"
        self.source.mkdir()
        self.game.mkdir()
        self.config = self.root / "config.json"
        self.presets = self.root / "presets.json"
        self.labels = self.root / "labels.json"
        self.profiles = self.root / "profiles"
        stack = ExitStack()
        self.addCleanup(stack.close)
        for module, key, value in (
            ("mod_manager.storage", "CONFIG_PATH", self.config),
            ("mod_manager.storage", "PRESETS_PATH", self.presets),
            ("mod_manager.storage", "LABELS_PATH", self.labels),
            ("mod_manager.storage", "PROFILE_DATA_DIR", self.profiles),
            ("mod_manager.cli_environment", "CONFIG_PATH", self.config),
            ("mod_manager.cli_environment", "PROFILE_DATA_DIR", self.profiles),
        ):
            stack.enter_context(patch(f"{module}.{key}", value))
        self.cfg = {
            "game_profiles": [{"id": "test-game", "name": "Test Game", "created_at": "2026-01-01", "mods_source_dir": str(self.source), "game_mods_dir": str(self.game), "install_mode": "copy"}],
            "active_game_profile_id": "test-game",
            "page_size": 2,
        }
        self.write_config()

    def write_config(self):
        self.config.write_text(json.dumps(self.cfg), encoding="utf-8")

    def add_mods(self, *names):
        for name in names:
            (self.source / name).write_text(name, encoding="utf-8")

    def request(self, argv):
        output, errors = io.StringIO(), io.StringIO()
        with patch("sys.stdout", output), patch("sys.stderr", errors):
            try:
                code = run_cli(argv)
            except SystemExit as error:
                code = error.code
        return code, output.getvalue(), errors.getvalue()

    def snapshot(self):
        return {path.relative_to(self.root).as_posix(): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
