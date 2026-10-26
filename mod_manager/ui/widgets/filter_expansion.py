from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ..theme import tokens


class FilterExpansion(QtCore.QObject):
    def __init__(self, toolbar, section, boxes):
        super().__init__(toolbar)
        self.toolbar = toolbar
        self.section = section
        self.boxes = tuple(boxes)
        self.baselines = {box: box.minimumWidth() for box in boxes}
        self.active = None
        self._closed = False
        self.animations = {}
        self.timer = QtCore.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._check_focus)
        for box in boxes:
            animation = QtCore.QPropertyAnimation(box, b"minimumWidth", self)
            animation.setDuration(tokens.FILTER_ANIMATION_MS)
            animation.setEasingCurve(QtCore.QEasingCurve.InOutCubic)
            self.animations[box] = animation
            animation.valueChanged.connect(self._resize_section)
            box.lineEdit().textEdited.connect(lambda _text, target=box: self.expand(target))
            box.lineEdit().installEventFilter(self)
            box.view().installEventFilter(self)
            box.completer().popup().installEventFilter(self)
        toolbar.installEventFilter(self)
        QtWidgets.QApplication.instance().focusChanged.connect(self._focus_changed)

    def _focus_changed(self, _previous, current) -> None:
        if self.active is None:
            return
        box = self.active
        popups = (box.view(), box.completer().popup())
        popup_focus = any(popup.isVisible() and (popup.window() is current or popup.window().isAncestorOf(current)) for popup in popups) if current is not None else False
        if current is not None and current not in (box, box.lineEdit()) and not popup_focus:
            self.active = None
            self._animate(box, self.baselines[box])
        else:
            self.timer.start(tokens.IMMEDIATE_MS)

    def expand(self, box) -> None:
        if self.active is not None and self.active is not box:
            self._animate(self.active, self.baselines[self.active])
        self.active = box
        baseline = self.baselines[box]
        row = [widget for widget in self.toolbar.sections.values() if widget.geometry().top() == self.section.geometry().top()]
        end = max((widget.geometry().right() for widget in row), default=self.section.geometry().right())
        spare = max(0, self.toolbar.contentsRect().right() - end)
        allocated = sum(max(0, item.minimumWidth() - self.baselines[item]) for item in self.boxes)
        target = baseline + min(baseline * (tokens.FILTER_EXPAND_FACTOR - 1), spare + allocated)
        self._animate(box, target)

    def _resize_section(self, *_args) -> None:
        extra = sum(max(0, box.minimumWidth() - baseline) for box, baseline in self.baselines.items())
        self.section.setProperty("expandedWidth", extra)
        self.section.updateGeometry()

    def _animate(self, box, target) -> None:
        animation = self.animations[box]
        if animation.state() == QtCore.QAbstractAnimation.Running and animation.endValue() == target:
            return
        animation.stop()
        animation.setStartValue(box.minimumWidth())
        animation.setEndValue(target)
        animation.start()

    def _check_focus(self) -> None:
        if self.active is None:
            return
        box = self.active
        popup_open = box.view().isVisible() or box.completer().popup().isVisible()
        if not popup_open and not box.hasFocus() and not box.lineEdit().hasFocus():
            self.active = None
            self._animate(box, self.baselines[box])

    def eventFilter(self, obj, event):
        kind = event.type()
        if kind in (QtCore.QEvent.FocusOut, QtCore.QEvent.Hide):
            self.timer.start(tokens.IMMEDIATE_MS)
        elif obj is self.toolbar and kind in (QtCore.QEvent.Resize, QtCore.QEvent.FontChange):
            if self.active is not None:
                self.expand(self.active)
        return super().eventFilter(obj, event)

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.timer.stop()
        QtWidgets.QApplication.instance().focusChanged.disconnect(self._focus_changed)
        self.toolbar.removeEventFilter(self)
        for box in self.boxes:
            self.animations[box].stop()
            box.lineEdit().removeEventFilter(self)
            box.view().removeEventFilter(self)
            box.completer().popup().removeEventFilter(self)
