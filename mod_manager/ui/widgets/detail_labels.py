from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ...i18n import t
from ..theme import tokens
from .buttons import icon_button, text_button
from .flow_layout import FlowLayout, WrappingWidget
from .label_chips import chip_content
from .style_utils import apply_margins


class DetailLabels(WrappingWidget):
    def __init__(self, labels, count: int, add, assign, remove, edit, filter_label, parent=None, *, can_assign=True, definitions=None):
        super().__init__(parent)
        self.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        layout = apply_margins(QtWidgets.QVBoxLayout(self), margins=None, spacing=tokens.SPACE_SM)
        header = apply_margins(QtWidgets.QHBoxLayout(), margins=None, spacing=tokens.SPACE_SM)
        header.addWidget(QtWidgets.QLabel(t("labels")))
        header.addWidget(icon_button("label_add", t("new_label"), add))
        assignment = icon_button("label", t("assign_label"), assign)
        assignment.setProperty("actionAvailable", can_assign)
        assignment.setEnabled(can_assign)
        header.addWidget(assignment)
        header.addStretch(1)
        layout.addLayout(header)
        flow = FlowLayout(constrain_items=True)
        flow.setSpacing(tokens.SPACE_SM)
        for name, matched, automatic in labels:
            host = QtWidgets.QWidget(self)
            row = apply_margins(QtWidgets.QHBoxLayout(host), margins=None, spacing=tokens.SPACE_XS)
            text, icon, _extra = chip_content(name, (definitions or {}).get(name), self.fontMetrics())
            caption = f"{name} ({matched}/{count})" if count > 1 else name
            if text:
                text = caption
            tooltip = t("filter_mods_by_value0", value0=caption)
            button = text_button(text, tooltip, lambda value=name: filter_label(value),
                                 icon_name="label" if icon.isNull() else "", accessible_name=caption)
            if not icon.isNull():
                button.setIcon(icon)
                button.setIconSize(QtCore.QSize(tokens.ICON_SIZE, tokens.ICON_SIZE))
            row.addWidget(button)
            action = edit if automatic else remove
            row.addWidget(icon_button("edit" if automatic else "label_remove", t("edit_label_rule") if automatic else t("remove_label"), lambda value=name, run=action: run(value)))
            flow.addWidget(host)
        layout.addLayout(flow)
