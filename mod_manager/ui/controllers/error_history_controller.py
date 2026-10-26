from __future__ import annotations

from ...i18n import t

from copy import deepcopy
from typing import Callable

from PySide6 import QtCore

from ...log import logger
from ...link_recovery import (
    COPY_RECOVERY_QUESTION, COPY_RECOVERY_TITLE, copy_retry_mods, needs_copy_recovery,
    retry_copy_installations, retry_outcomes, save_copy_profile, validate_recovery_profile,
)
from ...models import OperationItem, OperationResult
from ...mods import existing_targets
from ...storage import active_game_profile
from pathlib import Path
from ...models import OperationFailure
from ..dialogs.base import show_dialog
from ..dialogs import prompts
from ..dialogs.error_history import ErrorHistoryDialog
from ..models.error_model import ErrorHistoryModel
from ..widgets.buttons import text_button
from ..widgets.style_utils import LINK, set_variant


class ErrorHistoryController(QtCore.QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.model = ErrorHistoryModel(self)
        self.dialog = None
        self.recovering = False
        self.button = text_button(t('errors_0'), t('show_errors_from_this_session'), self.open, window)
        set_variant(self.button, LINK)
        self.button.setEnabled(False)
        window.statusBar().addPermanentWidget(self.button)
        self.model.rowsInserted.connect(self._update_count)

    def _update_count(self, *args) -> None:
        self.button.setText(t('errors_value0', value0=f'{self.model.rowCount()}'))
        self.button.setEnabled(bool(self.model.rowCount()))

    def open(self) -> None:
        if self.dialog is None:
            self.dialog = ErrorHistoryDialog(self.model, self.window)
        self.dialog.setPalette(self.window.palette())
        show_dialog(self.dialog)

    def summarize(self, result: OperationResult) -> None:
        skipped = sum(item.action in ("missing", "skipped") for item in result.items)
        failed = sum(not item.success and item.action not in ("missing", "skipped") for item in result.items)
        success = sum(item.success for item in result.items)
        self.window.operation_progress.summarize(success, skipped, failed)

    def record_import(self, imported, errors, cfg, plans=()) -> None:
        profile = active_game_profile(cfg)
        failures = []
        for message in errors:
            plan = next((plan for plan in plans if str(message).startswith(plan.name)), None)
            source = plan.files[0][0] if plan and plan.files else Path(cfg.get("mods_source_dir") or ".")
            destination = Path(cfg.get("mods_source_dir") or ".") / (plan.name if plan else "")
            failure = OperationFailure(source, destination, str(message))
            failures.append(OperationItem(plan.name if plan else str(message), "imported", False, str(message), (failure,)))
        result = OperationResult(tuple(OperationItem(str(name), "imported", True, str(name)) for name in imported) + tuple(failures))
        self.model.append_result(result, profile.get("name", t('default')) if profile else t('default'))
        self.summarize(result)

    def run(
        self, label: str, worker: Callable, done: Callable, *,
        preset_names: tuple[str, ...] = (), recover_links: bool = True,
        previous_result: OperationResult | None = None,
    ) -> None:
        if self.window.context.busy or (self.recovering and recover_links):
            return
        original = deepcopy(self.window.cfg)
        profile = active_game_profile(self.window.cfg)
        profile_name = profile.get("name", t('default')) if profile else t('default')

        def work():
            try:
                return worker(), None
            except Exception as error:
                logger.exception(t('mod_operation_failed_s'), label)
                return None, str(error)

        def completed(outcome):
            value, error = outcome
            if error is not None:
                if not recover_links:
                    self.recovering = False
                result = OperationResult((OperationItem(label, "failed", False, error),))
                self.model.append_result(result, profile_name)
                self.window._set_status(t("operation_failed", label=label, error=error))
                self.window.refresh_all()
                self.summarize(result)
                return
            result = value[1] if isinstance(value, tuple) else value
            recorded = retry_outcomes(previous_result, result) if previous_result is not None else result
            self.model.append_result(recorded, profile_name)
            done(value)
            self.summarize(result)
            if recover_links and needs_copy_recovery(result):
                self._recover(result, original, value, done, preset_names)

        self.window._run_action(label, work, completed)

    def _recover(
        self, result: OperationResult, original: dict, value, done: Callable,
        preset_names: tuple[str, ...],
    ) -> None:
        if self.recovering:
            return
        self.recovering = True
        retry_ready = False
        try:
            validate_recovery_profile(self.window.cfg, original)
            if not prompts.ask_yes_no(self.window, COPY_RECOVERY_TITLE, COPY_RECOVERY_QUESTION, default_no=True):
                return
            retry_mods = copy_retry_mods(result)
            overwrite = bool(existing_targets(retry_mods))
            if not self.window._confirm_overwrite(retry_mods):
                return
            save_copy_profile(self.window.cfg, original)
            retry_ready = True
        except (OSError, ValueError) as error:
            prompts.show_error(self.window, COPY_RECOVERY_TITLE, str(error))
            self.window._set_status(t('copy_retry_cancelled_value0', value0=f'{error}'))
            return
        finally:
            if not retry_ready:
                self.recovering = False

        cfg = deepcopy(self.window.cfg)

        def work():
            return retry_copy_installations(cfg, result, overwrite, preset_names)

        def completed(recovered):
            try:
                if isinstance(value, tuple):
                    prefix = recovered.summary() if isinstance(value[0], str) else value[0]
                    done((prefix, recovered))
                else:
                    done(recovered)
            finally:
                self.recovering = False

        self.run(t('copying_failed_installations'), work, completed, recover_links=False, previous_result=result)
