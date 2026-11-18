from __future__ import annotations

from PySide6 import QtCore, QtGui

from ...i18n import t
from ...trash import remaining_days
from ..models.tile_delegate import TileDelegate
from ..theme import tokens

TRASH_ENTRY_ROLE = QtCore.Qt.UserRole + 10
TRASH_DAYS_ROLE = QtCore.Qt.UserRole + 11


def days_text(entry):
    days = remaining_days(entry)
    if days == 1:
        return t("trash_day_remaining")
    return t("trash_days_remaining", count=days) if days else t("trash_expired")


class TrashTileDelegate(TileDelegate):
    def __init__(self, cfg, images, palette, parent):
        super().__init__(cfg, palette, parent)
        self.image_cache = images
        self.show_favorites = False

    def _paint_labels(self, painter, option, index):
        for rect, text, _label in self._label_badges(option, index):
            self._draw_badge(painter, rect, self.accent_color)
            painter.setPen(self.badge_foreground)
            painter.drawText(rect, QtCore.Qt.AlignCenter, text)

    def _labels(self, index):
        return ()

    def _label_badges(self, option, index):
        text = days_text(index.data(TRASH_ENTRY_ROLE))
        badge = self._label_badge_rect(self._content_rect(option), QtGui.QFontMetrics(option.font), text)
        return [(badge.adjusted(-tokens.SPACE_SM, 0, 0, 0), text, None)]

    def _pixmap_for(self, mod, size):
        if self.image_cache is None:
            return QtGui.QPixmap()
        cfg = {"mods_source_dir": str(mod.src), "trash_preview": mod.dest}
        return self.image_cache.request(cfg, mod.name, size, cover=True) or QtGui.QPixmap()

    def editorEvent(self, event, model, option, index):
        return False

    def helpEvent(self, event, view, option, index):
        from PySide6 import QtWidgets
        QtWidgets.QToolTip.showText(event.globalPos(), index.data(QtCore.Qt.ToolTipRole), view)
        return True
