from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ..theme import tokens
from ..widgets.item_feedback import AnimatedItemDelegate
from ..widgets.label_chips import chip_content, chip_height, chip_tooltip, layout_chips, paint_chips


class LabelChipsDelegate(AnimatedItemDelegate):
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.text = ""

    def _labels(self, index):
        if index.column() != tokens.MOD_LABEL_COLUMN:
            return ()
        mod = index.data(QtCore.Qt.UserRole)
        return index.model().label_memberships.get(mod.name, ()) if mod else ()

    def _label_badges(self, option, index):
        rect = option.rect.adjusted(tokens.SPACE_SM, 0, -tokens.SPACE_SM, 0)
        return layout_chips(self._labels(index), index.model().label_definitions, rect, option.fontMetrics)

    def sizeHint(self, option, index):
        metrics = option.fontMetrics
        names = self._labels(index)
        contents = [chip_content(name, index.model().label_definitions.get(name), metrics) for name in names]
        width = sum(metrics.horizontalAdvance(text) + extra + tokens.TILE_LABEL_BADGE_PADDING + tokens.SPACE_SM
                    for text, _icon, extra in contents)
        return QtCore.QSize(min(tokens.LABEL_COLUMN_MAX_WIDTH, max(tokens.ICON_BUTTON_SIZE, width)),
                            max(tokens.TABLE_ROW_HEIGHT, chip_height(metrics) + tokens.SPACE_SM * 2))

    def _paint_content(self, painter, option, index):
        super()._paint_content(painter, option, index)
        paint_chips(painter, option, index, self._label_badges(option, index), index.model().label_definitions)

    def helpEvent(self, event, view, option, index):
        for rect, _text, name in self._label_badges(option, index):
            if rect.contains(event.pos()):
                QtWidgets.QToolTip.showText(event.globalPos(), chip_tooltip(name, self._labels(index)), view)
                return True
        return super().helpEvent(event, view, option, index)
