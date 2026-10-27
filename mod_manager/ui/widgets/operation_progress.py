from __future__ import annotations

from PySide6 import QtWidgets

from ...i18n import t
from ..theme import tokens
from .style_utils import apply_margins
from ..motion import motion_for


class OperationProgress(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.label = QtWidgets.QLabel(self)
        self.label.setWordWrap(True)
        self.bar = QtWidgets.QProgressBar(self)
        self.bar.setMaximumWidth(tokens.FORM_MEDIUM_FIELD_WIDTH)
        layout = apply_margins(QtWidgets.QHBoxLayout(self), margins=None, spacing=tokens.SPACE_LG)
        layout.addWidget(self.label, 1)
        layout.addWidget(self.bar)
        self.hide()

    def set_busy(self, busy: bool) -> None:
        if busy:
            self.show()
            self.label.setText(t("preparing_operation"))
            self.bar.setRange(0, 0)
        else:
            self.hide()
        self.bar.setVisible(busy)
        if busy:
            self._animate_appearance()

    def update_progress(self, progress) -> None:
        self.show()
        self.bar.setRange(0, progress.total)
        self.bar.setValue(progress.completed)
        self.label.setText(t("operation_progress", stage=t(progress.stage), name=progress.name,
                             done=progress.completed, total=progress.total) if progress.total else t(progress.stage))

    def summarize(self, success: int, skipped: int, failed: int) -> None:
        self.show()
        self.bar.hide()
        self.label.setText(t("operation_summary", success=success, skipped=skipped, failed=failed))
        self._animate_appearance()

    def _animate_appearance(self) -> None:
        motion = motion_for(self)
        if motion:
            motion.fade_in(self)
