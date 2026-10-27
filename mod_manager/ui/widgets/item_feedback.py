from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ..motion import motion_for
from ..theme import tokens
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
        frame = index.model().operation_frames.get(index.data(QtCore.Qt.UserRole).name)
        painter.save()
        if frame is not None:
            painter.setOpacity(frame.content_opacity)
        self._paint_content(painter, option, index)
        painter.restore()
        if frame is not None and index.column() == 1:
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
