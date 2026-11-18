from __future__ import annotations

from copy import deepcopy

from PySide6 import QtCore

from ...i18n import t
from ...models import OperationItem, OperationResult
from ...trash import list_entries, purge_entries, restore_conflicts, restore_entry, trash_mods
from ..dialogs import prompts
from ..theme import tokens
from ..widgets.trash_view import TrashView
from ..widgets.workspace import WorkspacePage


class TrashController(QtCore.QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.page = WorkspacePage(t("trash"), t("trash_help"))
        self.view = TrashView(self.page, window.cfg, window.runner)
        self.view.tile_delegate.set_palette(window.theme.palette)
        self.view.modeChanged.connect(self._set_mode)
        self.page.body.addWidget(self.view)
        self.view.restoreRequested.connect(self.restore)
        self.view.deleteRequested.connect(self.delete_selected)
        self.view.refreshRequested.connect(self.refresh)
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(tokens.TRASH_CLEANUP_MS)
        self.timer.timeout.connect(self.cleanup)
        self.timer.start()
        self._generation = 0
        self._closed = False
        self._cleaning = False
        window.runner.queueChanged.connect(self._queue_changed)

    def _queue_changed(self) -> None:
        self.view.pending = {identifier for command in self.window.runner.commands
                             for identifier in command.preset_names if identifier.startswith("trash:")}
        self.view.pending = {identifier.removeprefix("trash:") for identifier in self.view.pending}
        if "all" in self.view.pending:
            self.view.pending.update(entry.identifier for entry in self.view.entries)
        self.view.update_actions()

    def _set_mode(self, mode):
        self.window.cfg["trash_view_mode"] = mode
        self.window._queue_config_save(("trash_view_mode",))

    def refresh(self) -> None:
        if self._closed:
            return
        self._generation += 1
        generation = self._generation
        cfg = deepcopy(self.window.cfg)

        def completed(entries, error):
            if self._closed or generation != self._generation:
                return
            if error is not None:
                self.view.status.setText(str(error))
            else:
                self.view.set_entries(entries)

        self.window.runner.background(lambda: list_entries(cfg), completed, "operations")

    def remove_mods(self) -> None:
        window = self.window
        names = window._selected_mod_names()
        if not names or not window._mods_available(names):
            return
        if not prompts.ask_yes_no(window, t("trash"), t("trash_confirm", count=len(names)), default_no=True):
            return
        mods = [mod for mod in window.current_mod_items if mod.name in names]
        cfg = deepcopy(window.cfg)

        def done(result):
            for mod in mods:
                window._invalidate_mod_image(mod.name)
            window._set_status(result.summary())
            self.refresh()

        window.errors.run(t("trash_moving"), lambda: trash_mods(cfg, mods), done,
                          mod_names=tuple(names), recover_links=False)

    def _done(self, result):
        for item in result.items:
            if item.success and item.action == "restored":
                self.window._invalidate_mod_image(item.name)
        self.window._set_status(result.summary())
        self.refresh()
        self.window.refresh_all()

    def restore(self) -> None:
        entries = self.view.selected_entries()
        if not entries:
            return
        cfg = deepcopy(self.window.cfg)
        choices = []
        for entry in entries:
            name = entry.name
            if restore_conflicts(entry):
                name, accepted = prompts.choose_text(self.window, t("trash_restore"), t("trash_new_name"))
                if not accepted or not name.strip():
                    continue
                name = name.strip()
            choices.append((entry, name))
        if not choices:
            return

        def work():
            results = []
            for entry, name in choices:
                try:
                    restore_entry(cfg, entry, name)
                    results.append(OperationItem(name, "restored", True, t("trash_restored")))
                except (OSError, ValueError) as error:
                    results.append(OperationItem(name, "restored", False, str(error)))
            return OperationResult(tuple(results))

        self.window.errors.run(t("trash_restoring"), work, self._done, recover_links=False,
                               mod_names=tuple(name for _entry, name in choices),
                               preset_names=tuple("trash:" + entry.identifier for entry, _name in choices))

    def delete_selected(self) -> None:
        identifiers = {entry.identifier for entry in self.view.selected_entries()}
        if identifiers:
            self.empty(identifiers)

    def empty(self, identifiers=None) -> None:
        if not prompts.ask_yes_no(self.window, t("trash"), t("trash_confirm_permanent"), default_no=True):
            return
        cfg = deepcopy(self.window.cfg)
        self.window.errors.run(t("trash_deleting"), lambda: purge_entries(cfg, identifiers), self._done,
                               recover_links=False, reserved_presets=tuple("trash:" + value for value in identifiers or ("all",)))

    def cleanup(self) -> None:
        if self._closed or self._cleaning or self.window._closing_after_queue:
            return
        self._cleaning = True
        cfg = deepcopy(self.window.cfg)

        def completed(entries, error):
            self._cleaning = False
            if error is not None:
                self.window._set_status(str(error))
                return
            if entries:
                self.window.errors.run(t("trash_deleting"), lambda: purge_entries(cfg, expired_only=True),
                                       self._done, recover_links=False)

        self.window.runner.background(lambda: list_entries(cfg), completed, "operations")

    def shutdown(self) -> None:
        self._closed = True
        self._generation += 1
        self.timer.stop()
        self.view.shutdown()
        self.window.runner.queueChanged.disconnect(self._queue_changed)
