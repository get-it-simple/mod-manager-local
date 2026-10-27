from __future__ import annotations

from copy import deepcopy

from PySide6 import QtCore

from ...i18n import t
from ...library_snapshot import load_library_snapshot


class LibraryController(QtCore.QObject):
    changed = QtCore.Signal()

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.snapshot = None
        self.loading = False
        self.error = ""
        self._generation = 0
        self._running = False
        self._pending = None
        self._closed = False
        self._identity = None
        self.selected_names = None

    @property
    def ready(self) -> bool:
        return self.snapshot is not None and not self.loading and not self.error

    def refresh(self, selected_names=None) -> None:
        if self._closed:
            return
        self._generation += 1
        cfg = deepcopy(self.window.cfg)
        identity = tuple(str(cfg.get(key, "")) for key in ("active_game_profile_id", "mods_source_dir", "game_mods_dir",
                                                          "mod_extensions", "mod_group_extensions", "mod_recursive_scan", "install_mode", "link_prefix"))
        if self._identity is not None and self._identity != identity:
            self.snapshot = None
            self.window.images.reset()
            self.window._clear_library_models()
        self._identity = identity
        self.selected_names = selected_names if selected_names is not None else self.window._selected_mod_names()
        self.loading = True
        self.error = ""
        self._pending = (self._generation, cfg)
        self.changed.emit()
        self._dispatch()

    def invalidate(self) -> None:
        self._generation += 1
        self._pending = None
        self.loading = True
        self.changed.emit()

    def _dispatch(self) -> None:
        if self._running or self._pending is None or self._closed:
            return
        generation, cfg = self._pending
        self._pending = None
        self._running = True

        def completed(snapshot, error):
            self._running = False
            if self._closed:
                return
            if generation == self._generation:
                self.loading = False
                if error is not None:
                    self.error = t("library_refresh_failed", error=str(error))
                else:
                    self.snapshot = snapshot
                    self.window._apply_library_snapshot(self.selected_names)
                self.changed.emit()
            self._dispatch()

        self.window.runner.background(lambda: load_library_snapshot(cfg), completed)

    def shutdown(self) -> None:
        self._closed = True
        self._generation += 1
        self._pending = None
