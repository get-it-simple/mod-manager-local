from __future__ import annotations

from ...i18n import t

from PySide6 import QtCore, QtGui, QtWidgets

from ...models import ModItem
from .. import icons
from ..theme import colors, tokens
from ..widgets.item_feedback import blend_color
from ..widgets.operation_feedback import paint_operation

NO_IMAGE_TEXT = t('no_image')
EMPTY_LABEL = "-"


def qcolor(value) -> QtGui.QColor:
    if isinstance(value, colors.Rgba):
        color = QtGui.QColor(value.color)
        color.setAlpha(value.alpha)
        return color
    return QtGui.QColor(value)


class TileDelegate(QtWidgets.QStyledItemDelegate):
    favoriteToggled = QtCore.Signal(str)
    labelsRequested = QtCore.Signal(object, object)

    def __init__(self, cfg: dict, palette: colors.Palette | None = None, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.image_cache = getattr(parent, "images", None)
        self.favorites: set[str] = set()
        self.set_palette(palette or colors.build_palette("light"))

    def set_palette(self, palette: colors.Palette) -> None:
        self.palette_colors = palette
        self.accent_color = qcolor(palette.accent)
        self.badge_foreground = qcolor(palette.accent_text)
        self.dark_theme = palette.is_dark

    def tile_size(self) -> int:
        return max(tokens.TILE_SIZE_MIN, tokens.to_int(self.cfg.get("tile_size"), tokens.TILE_SIZE_MIN))

    def sizeHint(self, option, index):
        return QtCore.QSize(*tokens.tile_item_size(self.tile_size()))

    def clear_cache(self, mod_name: str | None = None) -> None:
        if self.image_cache is not None:
            if mod_name is None:
                self.image_cache.reset()
            else:
                self.image_cache.invalidate(mod_name)

    def set_favorites(self, favorites: set[str]) -> None:
        self.favorites = set(favorites)

    def paint(self, painter, option, index) -> None:
        frame = index.model().operation_frames.get(index.data(QtCore.Qt.UserRole).name)
        painter.save()
        if frame is not None:
            painter.setOpacity(frame.content_opacity)
        self._paint_content(painter, option, index)
        painter.restore()
        if frame is not None:
            paint_operation(painter, self._content_rect(option), frame, option.palette, self.accent_color)

    def _paint_content(self, painter, option, index) -> None:
        painter.save()
        mod = index.data(QtCore.Qt.UserRole)
        selected = bool(option.state & QtWidgets.QStyle.State_Selected)
        rect = self._content_rect(option)
        feedback = getattr(option.widget, "_item_feedback", None)
        selection = feedback.value(index, "selection", selected) if feedback else float(selected)
        hovered = bool(option.state & QtWidgets.QStyle.State_MouseOver)
        hover = feedback.value(index, "hover", hovered) if feedback else float(hovered)
        self._draw_card(painter, rect, selection, hover)

        image_rect = self._image_rect(rect)
        pixmap = self._pixmap_for(mod, image_rect.size())
        if pixmap.isNull():
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(qcolor(self.palette_colors.placeholder_bg))
            painter.drawRoundedRect(image_rect, tokens.RADIUS_IMAGE, tokens.RADIUS_IMAGE)
            painter.setPen(qcolor(self.palette_colors.placeholder_fg))
            painter.drawText(image_rect, QtCore.Qt.AlignCenter, NO_IMAGE_TEXT)
        else:
            painter.save()
            clip = QtGui.QPainterPath()
            clip.addRoundedRect(QtCore.QRectF(image_rect), tokens.RADIUS_IMAGE, tokens.RADIUS_IMAGE)
            painter.setClipPath(clip)
            painter.drawPixmap(image_rect, pixmap)
            painter.restore()

        accent = self.accent_color
        foreground = self.badge_foreground
        if mod.installed:
            badge = QtCore.QRect(
                rect.left() + tokens.TILE_BADGE_MARGIN,
                rect.top() + tokens.TILE_BADGE_MARGIN,
                tokens.TILE_CHECK_BADGE_WIDTH,
                tokens.TILE_BADGE_HEIGHT,
            )
            self._draw_badge(painter, badge, accent)
            self._draw_badge_check(painter, badge, foreground)

        for badge, text, _label in self._label_badges(option, index):
            self._draw_badge(painter, badge, accent)
            painter.setPen(foreground)
            inset = tokens.TILE_LABEL_TEXT_INSET
            painter.drawText(badge.adjusted(inset, 0, -inset, 0), QtCore.Qt.AlignCenter, text)

        name_badge = self._name_badge_rect(rect, image_rect)
        painter.setPen(qcolor(self.palette_colors.fg))
        inset = tokens.TILE_NAME_TEXT_INSET
        painter.drawText(
            name_badge.adjusted(inset, 0, -inset, 0),
            QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft,
            self._elided_mod_name(painter.fontMetrics(), mod.name, name_badge.width() - inset * 2),
        )
        favorite = mod.name in self.favorites
        hovered = bool(option.state & QtWidgets.QStyle.State_MouseOver)
        progress = feedback.value(index, "favorite", 1.0) if feedback else 1.0
        if favorite or hovered or progress < 1.0:
            favorite_rect = self._favorite_rect(image_rect)
            painter.setOpacity(painter.opacity() * (progress if favorite else 1.0 - progress if not hovered else 1.0))
            self._draw_badge(painter, favorite_rect, qcolor(self.palette_colors.panel))
            icon = icons.glyph_icon(
                "favorite_filled" if favorite else "favorite",
                qcolor(self.palette_colors.control_fg),
            )
            icon.paint(painter, favorite_rect, QtCore.Qt.AlignCenter)
        painter.restore()

    def editorEvent(self, event, model, option, index) -> bool:
        if event.type() in {QtCore.QEvent.MouseButtonPress, QtCore.QEvent.MouseButtonRelease} and event.button() == QtCore.Qt.LeftButton:
            mod = index.data(QtCore.Qt.UserRole)
            rect = self._content_rect(option)
            favorite_rect = self._favorite_rect(self._image_rect(rect))
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            for badge, _text, label in self._label_badges(option, index):
                if label is None and badge.contains(pos):
                    if event.type() == QtCore.QEvent.MouseButtonRelease:
                        self.labelsRequested.emit(self._labels(index), event.globalPosition().toPoint())
                    return True
            if mod is not None and favorite_rect.contains(pos):
                if event.type() == QtCore.QEvent.MouseButtonPress:
                    return True
                self.favoriteToggled.emit(mod.name)
                return True
        return super().editorEvent(event, model, option, index)

    def helpEvent(self, event, view, option, index) -> bool:
        tooltip = self._tooltip_for_pos(option, index, event.pos())
        if tooltip:
            QtWidgets.QToolTip.showText(event.globalPos(), tooltip, view)
            return True
        QtWidgets.QToolTip.hideText()
        return super().helpEvent(event, view, option, index)

    def _draw_card(self, painter, rect: QtCore.QRect, selected: float, hover: float = 0.0) -> None:
        theme = self.palette_colors
        base = blend_color(qcolor(theme.tile_base), qcolor(theme.tile_base_selected), selected)
        base = blend_color(base, qcolor(theme.combo_hover), hover * (1 - selected))
        border = blend_color(qcolor(theme.tile_border), self.accent_color, selected)
        painter.setBrush(base)
        painter.setPen(QtGui.QPen(border))
        painter.drawRoundedRect(rect, tokens.TILE_CARD_RADIUS, tokens.TILE_CARD_RADIUS)

    def _draw_badge(self, painter, rect: QtCore.QRect, color: QtGui.QColor) -> None:
        painter.setBrush(color)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRoundedRect(rect, tokens.TILE_BADGE_RADIUS, tokens.TILE_BADGE_RADIUS)

    def _draw_badge_check(self, painter, rect: QtCore.QRect, color: QtGui.QColor) -> None:
        painter.setPen(
            QtGui.QPen(color, tokens.TILE_BADGE_CHECK_PEN, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin)
        )
        points = [(rect.left() + x, rect.top() + y) for x, y in tokens.TILE_BADGE_CHECK_PATH]
        path = QtGui.QPainterPath()
        path.moveTo(*points[0])
        for point in points[1:]:
            path.lineTo(*point)
        painter.drawPath(path)

    def _label_badge_text(self, label: str) -> str:
        label = (label or "").strip()
        if not label or label == EMPTY_LABEL:
            return ""
        return label[: tokens.TILE_LABEL_BADGE_MAX_CHARS]

    def _elided_mod_name(self, metrics: QtGui.QFontMetrics, name: str, width: int) -> str:
        return metrics.elidedText(str(name or ""), QtCore.Qt.ElideRight, max(1, width))

    def _content_rect(self, option) -> QtCore.QRect:
        inset = tokens.TILE_CARD_INSET
        return option.rect.adjusted(inset, inset, -inset, -inset)

    def preview_size(self, item_rect: QtCore.QRect) -> QtCore.QSize:
        option = QtWidgets.QStyleOptionViewItem()
        option.rect = item_rect
        return self._image_rect(self._content_rect(option)).size()

    def _image_rect(self, rect: QtCore.QRect) -> QtCore.QRect:
        pad = tokens.TILE_CONTENT_PAD
        return QtCore.QRect(
            rect.left() + pad,
            rect.top() + pad,
            rect.width() - pad * 2,
            max(tokens.TILE_IMAGE_MIN_HEIGHT, rect.width() - tokens.TILE_IMAGE_HEIGHT_TRIM),
        )

    def _label_badge_rect(self, rect: QtCore.QRect, metrics: QtGui.QFontMetrics, text: str) -> QtCore.QRect:
        margin = tokens.TILE_BADGE_MARGIN
        badge_width = min(
            rect.width() - margin * 2,
            max(tokens.TILE_LABEL_BADGE_MIN_WIDTH, metrics.horizontalAdvance(text) + tokens.TILE_LABEL_BADGE_PADDING),
        )
        return QtCore.QRect(rect.right() - margin - badge_width, rect.top() + margin, badge_width, tokens.TILE_BADGE_HEIGHT)

    def _name_badge_rect(self, rect: QtCore.QRect, image_rect: QtCore.QRect) -> QtCore.QRect:
        pad = tokens.TILE_CONTENT_PAD
        return QtCore.QRect(rect.left() + pad, image_rect.bottom() + pad, rect.width() - pad * 2, tokens.TILE_BADGE_HEIGHT)

    def _favorite_rect(self, image_rect: QtCore.QRect) -> QtCore.QRect:
        size = min(tokens.FAVORITE_HIT_SIZE, image_rect.height())
        return QtCore.QRect(
            image_rect.right() - size - tokens.FAVORITE_MARGIN,
            image_rect.bottom() - size - tokens.FAVORITE_MARGIN,
            size,
            size,
        )

    def _tooltip_for_pos(self, option, index, pos: QtCore.QPoint) -> str:
        mod = index.data(QtCore.Qt.UserRole)
        if mod is None:
            return ""
        metrics = QtGui.QFontMetrics(option.font)
        rect = self._content_rect(option)
        image_rect = self._image_rect(rect)
        for badge, text, label in self._label_badges(option, index):
            if badge.contains(pos):
                return (label if label != text else "") if label else "\n".join(self._labels(index))
        name_badge = self._name_badge_rect(rect, image_rect)
        favorite_rect = self._favorite_rect(image_rect)
        if favorite_rect.contains(pos):
            return t('remove_from_favorites') if mod.name in self.favorites else t('add_to_favorites')
        if name_badge.contains(pos):
            elided = self._elided_mod_name(metrics, mod.name, name_badge.width() - tokens.TILE_NAME_TEXT_INSET * 2)
            if elided != mod.name:
                return mod.name
        return ""

    def _label_for_pos(self, option, index, pos: QtCore.QPoint) -> str:
        mod = index.data(QtCore.Qt.UserRole)
        if mod is None:
            return ""
        return next((label or "" for badge, _text, label in self._label_badges(option, index) if badge.contains(pos)), "")

    def _labels(self, index) -> tuple[str, ...]:
        mod = index.data(QtCore.Qt.UserRole)
        return index.model().label_memberships.get(mod.name, ()) if mod else ()

    def _label_badges(self, option, index):
        labels = self._labels(index)
        if not labels:
            return []
        rect = self._content_rect(option)
        metrics = QtGui.QFontMetrics(option.font)
        if len(labels) == 1:
            text = self._label_badge_text(labels[0])
            return [(self._label_badge_rect(rect, metrics, text), text, labels[0])]
        mod = index.data(QtCore.Qt.UserRole)
        available = rect.width() - tokens.TILE_BADGE_MARGIN * 2
        if mod.installed:
            available -= tokens.TILE_CHECK_BADGE_WIDTH + tokens.SPACE_SM
        entries = []
        for i, label in enumerate(labels):
            text = self._label_badge_text(label)
            width = max(tokens.TILE_LABEL_BADGE_MIN_WIDTH, metrics.horizontalAdvance(text) + tokens.TILE_LABEL_BADGE_PADDING)
            remaining = len(labels) - i - 1
            reserve = (metrics.horizontalAdvance(f"+{remaining}") + tokens.TILE_LABEL_BADGE_PADDING + tokens.SPACE_SM) if remaining else 0
            if width + reserve > available:
                text = f"+{len(labels) - i}"
                width = min(available, metrics.horizontalAdvance(text) + tokens.TILE_LABEL_BADGE_PADDING)
                entries.append((max(1, width), text, None))
                break
            entries.append((width, text, label))
            available -= width + tokens.SPACE_SM
        x = rect.right() - tokens.TILE_BADGE_MARGIN - sum(width for width, _text, _label in entries) - tokens.SPACE_SM * (len(entries) - 1)
        badges = []
        for width, text, label in entries:
            badges.append((QtCore.QRect(x, rect.top() + tokens.TILE_BADGE_MARGIN, width, tokens.TILE_BADGE_HEIGHT), text, label))
            x += width + tokens.SPACE_SM
        return badges

    def _pixmap_for(self, mod: ModItem, size: QtCore.QSize) -> QtGui.QPixmap:
        if self.image_cache is None:
            return QtGui.QPixmap()
        pixmap = self.image_cache.request(self.cfg, mod.name, size, cover=True)
        return pixmap if pixmap is not None else QtGui.QPixmap()
