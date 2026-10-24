from __future__ import annotations

import ast
import re
import unittest
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = PROJECT_ROOT / "mod_manager"
UI_ROOT = PACKAGE_ROOT / "ui"
THEME_ROOT = UI_ROOT / "theme"

QT_FREE_MODULES = (
    UI_ROOT / "theme" / "colors.py",
    UI_ROOT / "theme" / "tokens.py",
    UI_ROOT / "theme" / "stylesheet.py",
    UI_ROOT / "view_modes.py",
    UI_ROOT / "localization.py",
    PACKAGE_ROOT / "settings_schema.py",
)

HEX_COLOR = re.compile(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?\b")
RGB_CALL = re.compile(r"\brgba?\(")

QT_MIGRATION_PENDING: set[str] = set()

COLOR_LITERAL_PENDING: set[str] = set()

MAX_UI_MODULE_LINES = 400


def package_files() -> list[Path]:
    return sorted(PACKAGE_ROOT.rglob("*.py"))


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


class LayeringTest(unittest.TestCase):
    def test_gui_and_domain_do_not_import_cli_modules(self):
        offenders = []
        cli_modules = {path.stem for path in package_files() if path.stem.startswith("cli") or path.stem == "menus"}
        for path in package_files():
            if path.stem in cli_modules:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[-1] in cli_modules:
                    offenders.append(str(path.relative_to(PROJECT_ROOT)))
        self.assertEqual(offenders, [])

    def test_interfaces_import_independently_in_fresh_processes(self):
        probe = PROJECT_ROOT / "tests" / "fixtures" / "import_probe.py"
        for mode in ("gui", "cli"):
            with self.subTest(mode=mode):
                result = subprocess.run([sys.executable, str(probe), mode], cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("GUI imports without CLI" if mode == "gui" else "mods toggle", result.stdout)

    def test_only_ui_modules_import_qt(self):
        offenders = {
            path.relative_to(PROJECT_ROOT).as_posix()
            for path in package_files()
            if UI_ROOT not in path.parents and "PySide6" in imported_modules(path)
        }
        self.assertEqual(offenders, QT_MIGRATION_PENDING, "domain modules must stay importable without Qt")

    def test_token_modules_are_qt_free(self):
        for path in QT_FREE_MODULES:
            self.assertTrue(path.exists(), path)
            self.assertNotIn("PySide6", imported_modules(path), path.name)

    def test_tkinter_is_gone(self):
        offenders = [
            path.relative_to(PROJECT_ROOT).as_posix()
            for path in package_files()
            if {"tkinter", "Tkinter"} & imported_modules(path)
        ]
        self.assertEqual(offenders, [])


class DesignTokenTest(unittest.TestCase):
    def test_color_literals_live_only_in_the_colors_module(self):
        offenders = set()
        for path in package_files():
            if path == THEME_ROOT / "colors.py":
                continue
            text = path.read_text(encoding="utf-8")
            if HEX_COLOR.search(text) or RGB_CALL.search(text):
                offenders.add(path.relative_to(PROJECT_ROOT).as_posix())
        self.assertEqual(offenders, COLOR_LITERAL_PENDING)

    def test_colors_module_defines_the_light_and_dark_themes(self):
        text = (THEME_ROOT / "colors.py").read_text(encoding="utf-8")
        self.assertIn("LIGHT_BASE", text)
        self.assertIn("DARK_BASE", text)
        self.assertGreater(len(HEX_COLOR.findall(text)), 20)

    def test_gui_module_is_only_a_shim(self):
        text = (PACKAGE_ROOT / "gui.py").read_text(encoding="utf-8")
        self.assertLess(len(text.splitlines()), 20)
        self.assertNotIn("class ", text)
        self.assertNotIn("PySide6", imported_modules(PACKAGE_ROOT / "gui.py"))

    def test_ui_modules_stay_small(self):
        oversized = {
            path.relative_to(PROJECT_ROOT).as_posix(): len(path.read_text(encoding="utf-8").splitlines())
            for path in UI_ROOT.rglob("*.py")
            if path.name != "app.py" and len(path.read_text(encoding="utf-8").splitlines()) > MAX_UI_MODULE_LINES
        }
        self.assertEqual(oversized, {})

    def test_stylesheet_reads_sizes_from_tokens(self):
        text = (THEME_ROOT / "stylesheet.py").read_text(encoding="utf-8")
        self.assertNotIn("PySide6", text)
        self.assertGreater(text.count("tokens."), 10)
        self.assertEqual(re.findall(r"(?<![\w.}])\d+px", text), [])


if __name__ == "__main__":
    unittest.main()
