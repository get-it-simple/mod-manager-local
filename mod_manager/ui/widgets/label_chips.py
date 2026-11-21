from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets
from shiboken6 import isValid

from ...i18n import t
from ..label_artwork import custom_label_icon
from ..theme import tokens
from ..theme.colors import LABEL_CHIP_SHADE


def chip_content(name, definition, metrics):
    icon = custom_label_icon(definition)
    text = "" if not icon.isNull() and definition.icon_only else name
    extra = tokens.ICON_SIZE + (tokens.SPACE_SM if text else 0) if not icon.isNull() else 0
    return text, icon, extra


def chip_height(metrics):
    return max(tokens.TILE_BADGE_HEIGHT, metrics.height() + tokens.SPACE_SM * 2)


def layout_chips(names, definitions, rect, metrics):
    if not names or rect.width() <= 0:
        return []
    remaining_width = rect.width()
    entries = []
    for index, name in enumerate(names):
        text, _icon, extra = chip_content(name, definitions.get(name), metrics)
        natural = metrics.horizontalAdvance(text) + extra + tokens.TILE_LABEL_BADGE_PADDING
        hidden = len(names) - index - 1
        reserve = metrics.horizontalAdvance(f"+{hidden}") + tokens.TILE_LABEL_BADGE_PADDING + tokens.SPACE_SM if hidden else 0
        cap = rect.width() if len(names) == 1 else tokens.LABEL_CHIP_MAX_WIDTH
        width = min(natural, cap, remaining_width - reserve)
        minimum = extra + metrics.horizontalAdvance("…") + tokens.TILE_LABEL_BADGE_PADDING if text else natural
        if width < minimum:
            text = f"+{len(names) - index}"
            width = min(remaining_width, metrics.horizontalAdvance(text) + tokens.TILE_LABEL_BADGE_PADDING)
            entries.append((max(1, width), text, None))
            break
        text = metrics.elidedText(text, QtCore.Qt.ElideRight, max(0, width - extra - tokens.TILE_LABEL_BADGE_PADDING))
        entries.append((width, text, name))
        remaining_width -= width + tokens.SPACE_SM
    result = []
    x = rect.left()
    height = chip_height(metrics)
    for width, text, name in entries:
        result.append((QtCore.QRect(x, rect.center().y() - height // 2, width, height), text, name))
        x += width + tokens.SPACE_SM
    return result


def paint_chips(painter, option, index, badges, definitions):
    view = option.widget
    hovered = getattr(view, "_label_chip_hover", None)
    active = getattr(index.model(), "active_labels", set())
    painter.save()
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    painter.setFont(option.font)
    for rect, text, name in badges:
        key = (QtCore.QPersistentModelIndex(index), name)
        is_hovered = key == hovered
        is_active = name in active
        if is_active:
            darkening = tokens.LABEL_CHIP_ACTIVE_HOVER_DARKENING if is_hovered else tokens.LABEL_CHIP_ACTIVE_DARKENING
        else:
            darkening = tokens.LABEL_CHIP_HOVER_DARKENING if is_hovered else 0
        icon = QtGui.QIcon()
        extra = 0
        if name is not None:
            _full, icon, extra = chip_content(name, definitions.get(name), option.fontMetrics)
        base = option.palette.highlight().color()
        icon_only = not text and not icon.isNull()
        painter.setPen(QtCore.Qt.NoPen)
        if not icon_only:
            base = QtGui.QColor.fromRgbF(base.redF() * (1 - darkening), base.greenF() * (1 - darkening),
                                        base.blueF() * (1 - darkening), base.alphaF())
            painter.setBrush(base)
            painter.drawRoundedRect(rect, tokens.TILE_BADGE_RADIUS, tokens.TILE_BADGE_RADIUS)
        content = rect.adjusted(tokens.TILE_LABEL_TEXT_INSET, 0, -tokens.TILE_LABEL_TEXT_INSET, 0)
        if name is not None:
            if not icon.isNull():
                icon_rect = QtCore.QRect(content.left(), content.center().y() - tokens.ICON_SIZE // 2,
                                         tokens.ICON_SIZE, tokens.ICON_SIZE)
                if not text:
                    icon_rect.moveCenter(content.center())
                if icon_only and darkening:
                    pixmap = icon.pixmap(icon_rect.size(), painter.device().devicePixelRatioF())
                    shaded = pixmap.copy()
                    shade = QtGui.QPainter(shaded)
                    shade.setCompositionMode(QtGui.QPainter.CompositionMode_SourceAtop)
                    color = QtGui.QColor(LABEL_CHIP_SHADE)
                    color.setAlphaF(darkening)
                    shade.fillRect(shaded.rect(), color)
                    shade.end()
                    painter.drawPixmap(icon_rect, shaded)
                else:
                    icon.paint(painter, icon_rect, QtCore.Qt.AlignCenter)
                content.adjust(extra, 0, 0, 0)
        painter.setPen(option.palette.highlightedText().color())
        painter.drawText(content, QtCore.Qt.AlignCenter, text)
    painter.restore()


def chip_tooltip(name, names):
    return t("label_chip_help", name=name) if name is not None else "\n".join(names)


class LabelChipInteraction(QtCore.QObject):
    activated = QtCore.Signal(str, bool)
    choicesRequested = QtCore.Signal(object, object)

    def __init__(self, view, delegate, available):
        super().__init__(view)
        self.view = view
        self.viewport = view.viewport()
        self.delegate = delegate
        self.available = available
        self.pressed = None
        view.setMouseTracking(True)
        view.viewport().installEventFilter(self)
        view.installEventFilter(self)
        view.model().modelAboutToBeReset.connect(self.clear)
        view.verticalScrollBar().valueChanged.connect(self.clear)
        view.horizontalScrollBar().valueChanged.connect(self.clear)

    def clear(self, *_args):
        self.pressed = None
        self.view._label_chip_hover = None
        self.view._label_chip_pressed = None
        if isValid(self.viewport):
            self.viewport.update()

    def shutdown(self):
        self.view.removeEventFilter(self)
        self.viewport.removeEventFilter(self)
        self.clear()

    def at(self, pos):
        index = self.view.indexAt(pos)
        if not index.isValid():
            return None
        option = QtWidgets.QStyleOptionViewItem()
        option.initFrom(self.view)
        option.font = self.view.font()
        option.fontMetrics = self.view.fontMetrics()
        option.rect = self.view.visualRect(index)
        for rect, _text, name in self.delegate._label_badges(option, index):
            if rect.contains(pos):
                return QtCore.QPersistentModelIndex(index), name
        return None

    def eventFilter(self, obj, event):
        kind = event.type()
        if kind in (QtCore.QEvent.Hide, QtCore.QEvent.Leave):
            self.clear()
        elif kind == QtCore.QEvent.MouseMove and obj is self.viewport:
            hit = self.at(event.position().toPoint()) if self.available() else None
            if hit != getattr(self.view, "_label_chip_hover", None):
                self.view._label_chip_hover = hit
                self.view.viewport().update()
            if hit:
                obj.setCursor(QtCore.Qt.PointingHandCursor)
        elif kind in (
                QtCore.QEvent.MouseButtonPress, QtCore.QEvent.MouseButtonRelease, QtCore.QEvent.MouseButtonDblClick) and obj is self.viewport:
            if event.button() != QtCore.Qt.LeftButton:
                return False
            hit = self.at(event.position().toPoint())
            if hit is not None:
                if kind in (QtCore.QEvent.MouseButtonPress, QtCore.QEvent.MouseButtonDblClick):
                    self.pressed = hit if self.available() else None
                    self.view._label_chip_pressed = self.pressed
                    self.view.viewport().update()
                elif kind == QtCore.QEvent.MouseButtonRelease:
                    pressed = self.pressed
                    self.pressed = None
                    self.view._label_chip_pressed = None
                    self.view.viewport().update()
                    if pressed == hit and self.available():
                        index, name = hit
                        if name is None:
                            self.choicesRequested.emit(self.delegate._labels(index), event.globalPosition().toPoint())
                        else:
                            self.activated.emit(name, bool(event.modifiers() & QtCore.Qt.ShiftModifier))
                            self.view._label_chip_hover = self.at(event.position().toPoint()) if self.available() else None
                            self.viewport.update()
                return True
            if kind == QtCore.QEvent.MouseButtonRelease:
                self.pressed = None
                self.view._label_chip_pressed = None
                self.view.viewport().update()
        elif obj is self.view and kind == QtCore.QEvent.KeyPress and event.key() in (
                QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter, QtCore.Qt.Key_Space):
            index = self.view.currentIndex()
            if index.isValid() and index.column() == tokens.MOD_LABEL_COLUMN and self.available():
                names = self.delegate._labels(index)
                if names:
                    self.choicesRequested.emit(names, self.view.viewport().mapToGlobal(self.view.visualRect(index).bottomLeft()))
                    return True
        return False
