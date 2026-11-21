from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ..motion import motion_for
from ..theme import colors, tokens
from .operation_feedback import paint_operation


def blend_color(first, second, progress):
    return QtGui.QColor(*(round(a + (b - a) * progress) for a, b in zip(first.getRgb(), second.getRgb())))


class ItemFeedback(QtCore.QObject):
    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.hovered = QtCore.QPersistentModelIndex()
        self.values = {}
        self.targets = {}
        view.setMouseTracking(True)
        view.viewport().installEventFilter(self)
        view.entered.connect(self._entered)
        view.selectionModel().selectionChanged.connect(self._selected)
        view.model().modelAboutToBeReset.connect(self.clear)
        view._item_feedback = self

    def value(self, index, kind, default):
        return self.values.get((QtCore.QPersistentModelIndex(index.siblingAtColumn(0)), kind), float(default))

    def pulse_favorite(self, index):
        self._animate({(QtCore.QPersistentModelIndex(index.siblingAtColumn(0)), "favorite"): (0.0, 1.0)})

    def _entered(self, index):
        index = QtCore.QPersistentModelIndex(index.siblingAtColumn(0))
        if index != self.hovered:
            changes = {(self.hovered, "hover"): (1.0, 0.0), (index, "hover"): (0.0, 1.0)}
            self.hovered = index
            self._animate(changes)

    def _selected(self, selected, deselected):
        changes = {}
        for selection, start, end in ((selected, 0.0, 1.0), (deselected, 1.0, 0.0)):
            for index in selection.indexes():
                index = index.siblingAtColumn(0)
                if self.view.visualRect(index).intersects(self.view.viewport().rect()):
                    changes[(QtCore.QPersistentModelIndex(index), "selection")] = (start, end)
        self._animate(changes)

    def _animate(self, changes):
        motion = motion_for(self.view)
        if motion is None:
            return
        for key, (start, end) in changes.items():
            if key[0].isValid():
                self.targets[key] = end
                self.values.setdefault(key, start)
        starts, targets = dict(self.values), dict(self.targets)

        def apply(progress):
            region = QtGui.QRegion()
            for key, end in targets.items():
                self.values[key] = starts[key] + (end - starts[key]) * progress
                if key[0].isValid():
                    rect = self.view.visualRect(QtCore.QModelIndex(key[0]))
                    rect.setLeft(0)
                    rect.setWidth(self.view.viewport().width())
                    region += rect
            self.view.viewport().update(region)

        motion.animate(self.view, "items", 0.0, 1.0, apply, tokens.MOTION_HOVER_MS, self._finished)

    def _finished(self):
        self.values.clear()
        self.targets.clear()

    def clear(self):
        motion = motion_for(self.view)
        if motion:
            motion.stop(self.view, "items")
        self._finished()
        self.hovered = QtCore.QPersistentModelIndex()

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.Leave:
            self._entered(QtCore.QModelIndex())
        elif event.type() == QtCore.QEvent.Hide:
            self.clear()
        return False


class AnimatedItemDelegate(QtWidgets.QStyledItemDelegate):
    def paint(self, painter, option, index):
        from ..models.mod_model import OPERATION_ROLE
        frame = index.data(OPERATION_ROLE)
        painter.save()
        if frame is not None:
            painter.setOpacity(frame.content_opacity)
        self._paint_content(painter, option, index)
        painter.restore()
        if frame is not None and index.column() == getattr(index.model(), "operation_column", 1):
            paint_operation(painter, option.rect, frame, option.palette, index.model().activity_color)

    def _paint_content(self, painter, option, index):
        feedback = getattr(option.widget, "_item_feedback", None)
        if feedback is None:
            super().paint(painter, option, index)
            return
        option = QtWidgets.QStyleOptionViewItem(option)
        selected = bool(option.state & QtWidgets.QStyle.State_Selected)
        hovered = bool(option.state & QtWidgets.QStyle.State_MouseOver)
        selection = feedback.value(index, "selection", selected)
        hover = feedback.value(index, "hover", hovered)
        if selection > 0 or hover > 0:
            option.state &= ~(QtWidgets.QStyle.State_Selected | QtWidgets.QStyle.State_MouseOver)
            background = blend_color(option.palette.base().color(), option.palette.highlight().color(), selection)
            background = blend_color(background, option.palette.alternateBase().color(), hover * (1 - selection))
            painter.fillRect(option.rect, background)
            option.backgroundBrush = QtGui.QBrush(QtCore.Qt.NoBrush)
        super().paint(painter, option, index)


class ButtonItemFeedback(ItemFeedback):
    def __init__(self, view, active=None):
        self.active = active
        self.states = {}
        self.click_index = QtCore.QPersistentModelIndex()
        self.click_origin = QtCore.QPointF()
        self.click_progress = 1.0
        super().__init__(view)
        view.model().dataChanged.connect(self._changed)
        view.model().rowsInserted.connect(self._changed)
        view.model().rowsRemoved.connect(self._changed)
        self._changed()

    def _changed(self, *_args):
        if self.active is None:
            return
        changes = {}
        for row in range(self.view.model().rowCount()):
            index = QtCore.QPersistentModelIndex(self.view.model().index(row, 0))
            state = bool(self.active(index))
            previous = self.states.get(index, state)
            self.states[index] = state
            if state != previous:
                changes[(index, "active")] = (float(previous), float(state))
        self.states = {key: value for key, value in self.states.items() if key.isValid()}
        self._animate(changes)

    def eventFilter(self, obj, event):
        kind = event.type()
        if kind == QtCore.QEvent.MouseButtonPress and event.button() == QtCore.Qt.LeftButton:
            index = self.view.indexAt(event.position().toPoint())
            if index.isValid() and self.view.isEnabled():
                self.click_index = QtCore.QPersistentModelIndex(index)
                self.click_origin = event.position() - self.view.visualRect(index).topLeft()
                self._animate({(self.click_index, "press"): (0.0, 1.0)})
        elif kind == QtCore.QEvent.MouseButtonRelease and self.click_index.isValid():
            self._animate({(self.click_index, "press"): (1.0, 0.0)})
            motion = motion_for(self.view)
            if motion:
                def apply(progress):
                    self.click_progress = progress
                    if self.click_index.isValid():
                        self.view.viewport().update(self.view.visualRect(QtCore.QModelIndex(self.click_index)))
                motion.animate(self.view, "item-ripple", 0.0, 1.0, apply, tokens.BUTTON_RIPPLE_MS)
        return super().eventFilter(obj, event)

    def clear(self):
        super().clear()
        self.states.clear()
        self.click_index = QtCore.QPersistentModelIndex()
        self.click_progress = 1.0
        motion = motion_for(self.view)
        if motion:
            motion.stop(self.view, "item-ripple")


def paint_item_button(painter, option, index, active=False):
    view = option.widget
    feedback = getattr(view, "_item_feedback", None)
    motion = motion_for(view)
    if motion is None:
        return
    palette = motion.window.theme.palette
    painter.save()
    hover = bool(option.state & QtWidgets.QStyle.State_MouseOver)
    selected = feedback.value(index, "active" if feedback.active else "selection", active) if feedback else float(active)
    hovered = feedback.value(index, "hover", hover) if feedback else float(hover)
    pressed = feedback.value(index, "press", 0) if feedback else 0
    normal = colors.button_surface(palette, "segment", view.isEnabled(), False, False, False, False)
    checked = colors.button_surface(palette, "segment", view.isEnabled(), True, False, False, False)
    over = colors.button_surface(palette, "segment", view.isEnabled(), active, True, False, False)
    down = colors.button_surface(palette, "segment", view.isEnabled(), active, True, True, False)
    surface = []
    for base, target, hover_color, press_color in zip(normal, checked, over, down):
        color = blend_color(QtGui.QColor(*base), QtGui.QColor(*target), selected)
        color = blend_color(color, QtGui.QColor(*hover_color), hovered)
        surface.append(blend_color(color, QtGui.QColor(*press_color), pressed))
    rect = QtCore.QRectF(option.rect).adjusted(tokens.SPACE_XS, tokens.SPACE_XS, -tokens.SPACE_XS, -tokens.SPACE_XS)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    painter.setBrush(surface[0])
    painter.setPen(QtGui.QPen(surface[1], tokens.BORDER_WIDTH))
    painter.drawRoundedRect(rect, tokens.RADIUS_MD, tokens.RADIUS_MD)
    if feedback and feedback.click_index == index and feedback.click_progress < 1.0:
        painter.save()
        clip = QtGui.QPainterPath()
        clip.addRoundedRect(rect, tokens.RADIUS_MD, tokens.RADIUS_MD)
        painter.setClipPath(clip)
        color = QtGui.QColor(colors.button_ripple_color(palette, surface[0].getRgb()))
        color.setAlphaF(tokens.BUTTON_RIPPLE_ALPHA * (1.0 - feedback.click_progress))
        painter.setBrush(color)
        painter.setPen(QtCore.Qt.NoPen)
        radius = max(rect.width(), rect.height()) * tokens.BUTTON_RIPPLE_SCALE * feedback.click_progress / 2
        painter.drawEllipse(QtCore.QPointF(option.rect.topLeft()) + feedback.click_origin, radius, radius)
        painter.restore()
    painter.restore()
