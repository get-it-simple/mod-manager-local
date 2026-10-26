from __future__ import annotations

from ...i18n import t

from PySide6 import QtCore, QtGui, QtWidgets

from .. import icons
from ..theme import tokens


class FavoriteDelegate(QtWidgets.QStyledItemDelegate):
    favoriteToggled = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.favorites: set[str] = set()

    def set_favorites(self, favorites: set[str]) -> None:
        self.favorites = set(favorites)

    def star_rect(self, rect: QtCore.QRect) -> QtCore.QRect:
        size = min(tokens.FAVORITE_HIT_SIZE, rect.height())
        return QtCore.QRect(
            rect.right() - size - tokens.FAVORITE_MARGIN,
            rect.center().y() - size // 2,
            size,
            size,
        )

    def paint(self, painter, option, index) -> None:
        super().paint(painter, option, index)
        mod = index.data(QtCore.Qt.UserRole)
        if mod is None:
            return
        favorite = mod.name in self.favorites
        hovered = bool(option.state & QtWidgets.QStyle.State_MouseOver)
        if not favorite and not hovered:
            return
        color = option.palette.color(QtGui.QPalette.Highlight if favorite else QtGui.QPalette.Text)
        icon = icons.glyph_icon("favorite_filled" if favorite else "favorite", color)
        icon.paint(painter, self.star_rect(option.rect), QtCore.Qt.AlignCenter)

    def editorEvent(self, event, model, option, index) -> bool:
        if event.type() in {QtCore.QEvent.MouseButtonPress, QtCore.QEvent.MouseButtonRelease} and event.button() == QtCore.Qt.LeftButton:
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            if self.star_rect(option.rect).contains(pos):
                if event.type() == QtCore.QEvent.MouseButtonPress:
                    return True
                mod = index.data(QtCore.Qt.UserRole)
                if mod is not None:
                    self.favoriteToggled.emit(mod.name)
                    return True
        return super().editorEvent(event, model, option, index)

    def helpEvent(self, event, view, option, index) -> bool:
        mod = index.data(QtCore.Qt.UserRole)
        if mod is not None and self.star_rect(option.rect).contains(event.pos()):
            action = t('remove_from_favorites') if mod.name in self.favorites else t('add_to_favorites')
            QtWidgets.QToolTip.showText(event.globalPos(), action, view)
            return True
        return super().helpEvent(event, view, option, index)
