from __future__ import annotations

from weakref import WeakSet
from math import sin, pi

from PySide6 import QtCore, QtGui, QtWidgets
from shiboken6 import isValid

from .theme import colors, tokens


def motion_for(widget):
    while widget is not None:
        motion = getattr(widget, "motion", None)
        if motion is not None:
            return motion
        widget = widget.parentWidget()
    return None


class MotionController(QtCore.QObject):
    enabledChanged = QtCore.Signal(bool)

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.enabled = bool(window.cfg.get("gui_animations_enabled", True))
        self._transitions = {}
        self._buttons = WeakSet()
        self._feedback = set()
        self._closed = False
        self.operation_blocked = False
        QtWidgets.QApplication.instance().installEventFilter(self)

    def attach(self, widget) -> None:
        if isinstance(widget, (QtWidgets.QPushButton, QtWidgets.QToolButton)):
            if not hasattr(widget, "_motion_feedback"):
                widget._motion_feedback = None
                feedback = ButtonFeedback(widget, self)
                widget._motion_feedback = feedback
                self._feedback.add(feedback)
                widget.destroyed.connect(lambda _obj=None, feedback=feedback: self._feedback.discard(feedback))
                self._buttons.add(widget)

    def eventFilter(self, obj, event):
        if isinstance(obj, QtWidgets.QWidget) and event.type() in (QtCore.QEvent.Polish, QtCore.QEvent.Show):
            if motion_for(obj) is self:
                self.attach(obj)
                if event.type() == QtCore.QEvent.Show and isinstance(obj, QtWidgets.QDialog):
                    if not isinstance(obj, (QtWidgets.QMessageBox, QtWidgets.QFileDialog, QtWidgets.QInputDialog)):
                        self.animate(obj, "dialog", 0.0, 1.0, obj.setWindowOpacity, tokens.MOTION_CONTENT_MS)
        return False

    def animate(self, owner, key, start, end, apply, duration, finished=None):
        identity = (id(owner), key)
        self.stop(owner, key)
        if self._closed or not self.enabled or not owner.isVisible():
            apply(end)
            if finished:
                finished()
            return None
        animation = QtCore.QVariantAnimation(self)
        animation.setStartValue(start)
        animation.setEndValue(end)
        animation.setDuration(duration)
        animation.setEasingCurve(QtCore.QEasingCurve.OutCubic)

        def update(value):
            if isValid(owner):
                apply(value)

        def complete():
            self._transitions.pop(identity, None)
            if isValid(owner) and finished:
                finished()
            animation.deleteLater()

        animation.valueChanged.connect(update)
        animation.finished.connect(complete)
        self._transitions[identity] = (animation, owner, end, apply, finished)
        apply(start)
        animation.start()
        return animation

    def stop(self, owner, key) -> None:
        transition = self._transitions.pop((id(owner), key), None)
        if transition:
            transition[0].stop()
            transition[0].deleteLater()

    def fade_in(self, widget) -> None:
        if not widget.isVisible() or not self.enabled:
            return
        self.stop(widget, "fade")
        cover = getattr(widget, "_motion_cover", None)
        if cover is None or not isValid(cover):
            cover = FadeCover(widget, self)
            widget._motion_cover = cover
        cover.setGeometry(widget.rect())
        cover.show()
        cover.raise_()
        self.animate(widget, "fade", 0.0, 1.0, cover.reveal, tokens.MOTION_CONTENT_MS, cover.hide)

    def expand(self, widget, expanded: bool) -> None:
        self.stop(widget, "expand")
        if not self.enabled or not widget.parentWidget().isVisible():
            widget.setMaximumHeight(tokens.MAX_WIDGET_HEIGHT)
            widget.setVisible(expanded)
            return
        start = widget.height() if widget.isVisible() else 0
        widget.show()
        target = widget.sizeHint().height() if expanded else 0

        def finished():
            widget.setVisible(expanded)
            widget.setMaximumHeight(tokens.MAX_WIDGET_HEIGHT)

        self.animate(widget, "expand", start, target, widget.setMaximumHeight, tokens.MOTION_EXPAND_MS, finished)

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        self.finish_all()
        self.enabledChanged.emit(enabled)
        for button in tuple(self._buttons):
            if isValid(button):
                button._motion_feedback.refresh()

    def set_operation_blocked(self, blocked: bool) -> None:
        if blocked == self.operation_blocked:
            return
        self.operation_blocked = blocked
        for feedback in tuple(self._feedback):
            if isValid(feedback.button):
                feedback.frozen_image = feedback.button.grab() if blocked and feedback.button.isVisible() else QtGui.QPixmap()
                self.stop(feedback.button, "feedback")
                feedback.frozen_surface = feedback.surface if blocked else None
                feedback.refresh()
                feedback.button.update()

    def finish_all(self) -> None:
        transitions, self._transitions = self._transitions, {}
        for animation, owner, end, apply, finished in transitions.values():
            animation.stop()
            if isValid(owner):
                apply(end)
                if finished:
                    finished()
            animation.deleteLater()

    def shutdown(self) -> None:
        self._closed = True
        self.finish_all()
        QtWidgets.QApplication.instance().removeEventFilter(self)
        for button in tuple(self._buttons):
            if isValid(button):
                feedback = button._motion_feedback
                button.removeEventFilter(feedback)
                button.pressed.disconnect(feedback._press)
                button.released.disconnect(feedback._release)
                button.toggled.disconnect(feedback.refresh)
                button.clicked.disconnect(feedback._click)
        self._feedback.clear()


class FadeCover(QtWidgets.QWidget):
    def __init__(self, parent, motion):
        super().__init__(parent)
        self.motion = motion
        self.progress = 0.0
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.setFocusPolicy(QtCore.Qt.NoFocus)

    def reveal(self, progress):
        self.progress = progress
        self.update()

    def paintEvent(self, event):
        color = QtGui.QColor(self.motion.window.theme.palette.bg)
        color.setAlphaF(max(0.0, min(1.0, 1.0 - self.progress)))
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), color)
        painter.end()


class ButtonFeedback(QtCore.QObject):
    def __init__(self, button, motion):
        self.button = button
        self.motion = motion
        self.hovered = False
        self.pressed = False
        self.focused = button.hasFocus()
        super().__init__(button)
        self.surface = self.target()
        self.frozen_surface = self.surface if motion.operation_blocked else None
        self.frozen_image = QtGui.QPixmap()
        self.click_progress = 1.0
        button.installEventFilter(self)
        button.pressed.connect(self._press)
        button.released.connect(self._release)
        button.toggled.connect(self.refresh)
        button.clicked.connect(self._click)

    def target(self):
        frozen = getattr(self, "frozen_surface", None)
        if frozen is not None:
            return frozen
        return colors.button_surface(self.motion.window.theme.palette, self.button.property("variant"),
                                     self.button.isEnabled(), self.button.isChecked(),
                                     self.hovered, self.pressed, self.focused)

    def _press(self):
        self.pressed = True
        self.refresh()

    def _release(self):
        self.pressed = False
        self.refresh()

    def _click(self, *_args):
        if not self.button.property("pagePulse"):
            return
        def apply(progress):
            self.click_progress = progress
            self.button.update()
        self.motion.animate(self.button, "page-pulse", 0.0, 1.0, apply, tokens.PAGE_PULSE_MS)

    def refresh(self, *_args):
        start, target = self.surface, self.target()
        if start == target:
            self.motion.stop(self.button, "feedback")
            return

        def apply(progress):
            self.surface = tuple(tuple(round(a + (b - a) * progress) for a, b in zip(old, new))
                                 for old, new in zip(start, target))
            self.button.update()

        self.motion.animate(self.button, "feedback", 0.0, 1.0, apply,
                            tokens.MOTION_PRESS_MS if self.pressed else tokens.MOTION_HOVER_MS)

    def eventFilter(self, obj, event):
        kind = event.type()
        if kind in (QtCore.QEvent.Enter, QtCore.QEvent.Leave):
            self.hovered = kind == QtCore.QEvent.Enter
            self.refresh()
        elif kind in (QtCore.QEvent.FocusIn, QtCore.QEvent.FocusOut):
            self.focused = kind == QtCore.QEvent.FocusIn
            self.refresh()
        elif kind == QtCore.QEvent.EnabledChange:
            self.motion.stop(obj, "feedback")
            self.surface = self.target()
            obj.update()
        elif kind in (QtCore.QEvent.PaletteChange, QtCore.QEvent.StyleChange):
            self.refresh()
        elif kind == QtCore.QEvent.Hide:
            self.hovered = self.pressed = False
            self.motion.stop(obj, "feedback")
            self.surface = self.target()
        elif kind == QtCore.QEvent.Paint:
            self.paint()
            return True
        return False

    def paint(self):
        button = self.button
        painter = QtGui.QPainter(button)
        if not self.frozen_image.isNull():
            painter.drawPixmap(button.rect(), self.frozen_image)
            painter.end()
            return
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        pulse = sin(self.click_progress * pi) if self.click_progress < 1.0 else 0.0
        scale = 1.0 - (1.0 - tokens.PAGE_PULSE_SCALE) * pulse
        center = QtCore.QRectF(button.rect()).center()
        painter.translate(center)
        painter.scale(scale, scale)
        painter.translate(-center)
        background, border, foreground = (QtGui.QColor(*value) for value in self.surface)
        background = background.lighter(round(100 * (1 + tokens.PAGE_PULSE_LIGHTEN * pulse)))
        inset = tokens.BORDER_WIDTH / 2
        rect = QtCore.QRectF(button.rect()).adjusted(inset, inset, -inset, -inset)
        painter.setBrush(background)
        painter.setPen(QtGui.QPen(border, tokens.BORDER_WIDTH))
        painter.drawRoundedRect(rect, tokens.RADIUS_MD, tokens.RADIUS_MD)
        if button.property("variant") == "navigation" and button.isChecked():
            painter.setPen(QtGui.QPen(QtGui.QColor(self.motion.window.theme.palette.accent), tokens.BORDER_WIDTH))
            painter.drawLine(rect.topLeft(), rect.bottomLeft())
        if isinstance(button, QtWidgets.QPushButton):
            option = QtWidgets.QStyleOptionButton()
            button.initStyleOption(option)
            option.rect = button.style().subElementRect(QtWidgets.QStyle.SE_PushButtonContents, option, button)
            control = QtWidgets.QStyle.CE_PushButtonLabel
        else:
            option = QtWidgets.QStyleOptionToolButton()
            button.initStyleOption(option)
            option.rect = button.style().subControlRect(QtWidgets.QStyle.CC_ToolButton, option,
                                                        QtWidgets.QStyle.SC_ToolButton, button)
            control = QtWidgets.QStyle.CE_ToolButtonLabel
        option.palette.setColor(QtGui.QPalette.ButtonText, foreground)
        if self.frozen_surface is not None:
            option.state |= QtWidgets.QStyle.State_Enabled
        button.style().drawControl(control, option, painter, button)
        painter.end()
