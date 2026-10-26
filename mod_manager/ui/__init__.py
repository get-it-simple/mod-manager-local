from __future__ import annotations

from ..i18n import t

import importlib.util
import os


def qt_available() -> bool:
    return importlib.util.find_spec("PySide6") is not None


def apply_ui_scale(cfg: dict) -> None:
    try:
        scale = int(cfg.get("ui_scale_percent") or 100)
    except (TypeError, ValueError):
        scale = 100
    if scale != 100:
        os.environ.setdefault("QT_SCALE_FACTOR", str(scale / 100))


def run_gui() -> int:
    if not qt_available():
        print(t('pyside6_is_required_for_the_gui_install_dependencies_with_pip_install_r_'))
        return 2

    from ..storage import load_config

    cfg = load_config()
    from ..i18n import setup
    setup(cfg.get("gui_language", "en"))
    apply_ui_scale(cfg)

    from .app import start

    return start()


__all__ = ["apply_ui_scale", "qt_available", "run_gui"]
