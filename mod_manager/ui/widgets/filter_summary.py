from __future__ import annotations

from PySide6 import QtWidgets

from ...i18n import t
from .buttons import text_button
from .flow_layout import FlowLayout
from .style_utils import clear_layout


class FilterSummary(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.flow = FlowLayout(self, constrain_items=True)

    def update_filters(self, count: int, total: int, filters) -> None:
        clear_layout(self.flow)
        self.flow.addWidget(QtWidgets.QLabel(t("showing_mods", count=count, total=total)))
        for text, callback in filters:
            self.flow.addWidget(text_button(text, t("remove_filter"), callback, icon_name="clear"))
        self.setMinimumHeight(self.flow.heightForWidth(self.width()))
        self.updateGeometry()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.setMinimumHeight(self.flow.heightForWidth(self.width()))
