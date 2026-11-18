from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ..motion import motion_for
from ..theme import tokens


class OverlayScrollBar(QtWidgets.QScrollBar):
    def __init__(self, source, parent):
        super().__init__(source.orientation(), parent)
        self.source = source
        self.expansion = 0.0
        self.hovered = False
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setCursor(QtCore.Qt.ArrowCursor)
        self.setAttribute(QtCore.Qt.WA_OpaquePaintEvent, False)
        self.setAutoFillBackground(False)
        self.valueChanged.connect(source.setValue)
        source.valueChanged.connect(self.setValue)
        self.sliderPressed.connect(self._expand)
        self.sliderReleased.connect(self._expand)
        self.hide()

    def sync(self):
        self.setRange(self.source.minimum(), self.source.maximum())
        self.setPageStep(self.source.pageStep())
        self.setSingleStep(self.source.singleStep())
        self.setValue(self.source.value())
        self.setEnabled(self.source.isEnabled())

    def _expand(self):
        target = float(self.hovered or self.isSliderDown())
        motion = motion_for(self)
        def apply(value):
            self.expansion = value
            self.update()
        if motion:
            motion.animate(self, "scrollbar", self.expansion, target, apply, tokens.MOTION_HOVER_MS)
        else:
            apply(target)

    def enterEvent(self, event):
        self.hovered = True
        self._expand()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hovered = False
        self._expand()
        super().leaveEvent(event)

    def paintEvent(self, event):
        option = QtWidgets.QStyleOptionSlider()
        self.initStyleOption(option)
        rect = self.style().subControlRect(QtWidgets.QStyle.CC_ScrollBar, option,
                                          QtWidgets.QStyle.SC_ScrollBarSlider, self)
        width = tokens.SCROLLBAR_IDLE_WIDTH + (tokens.SCROLLBAR_WIDTH - tokens.SCROLLBAR_IDLE_WIDTH) * self.expansion
        rect = QtCore.QRectF(rect)
        if self.orientation() == QtCore.Qt.Vertical:
            rect.setLeft(rect.right() - width)
        else:
            rect.setTop(rect.bottom() - width)
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(QtCore.Qt.NoPen)
        motion = motion_for(self)
        if motion:
            palette = motion.window.theme.palette
            color = QtGui.QColor(palette.muted if self.hovered or self.isSliderDown() else palette.field_border)
        else:
            color = self.palette().color(QtGui.QPalette.Mid)
        painter.setBrush(color)
        painter.drawRoundedRect(rect, width / 2, width / 2)
        painter.end()


class OverlayScrollArea(QtCore.QObject):
    def __init__(self, area):
        super().__init__(area)
        self.area = area
        self.vertical_allowed = area.verticalScrollBarPolicy() != QtCore.Qt.ScrollBarAlwaysOff
        self.horizontal_allowed = area.horizontalScrollBarPolicy() != QtCore.Qt.ScrollBarAlwaysOff
        self.vertical = OverlayScrollBar(area.verticalScrollBar(), area.viewport())
        self.horizontal = OverlayScrollBar(area.horizontalScrollBar(), area.viewport())
        self.timer = QtCore.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.sync)
        area.installEventFilter(self)
        area.viewport().installEventFilter(self)
        for source in (area.verticalScrollBar(), area.horizontalScrollBar()):
            source.rangeChanged.connect(self.schedule)
            source.valueChanged.connect(self.schedule)
        self.sync()

    def schedule(self, *_args):
        if not self.timer.isActive():
            self.timer.start(tokens.IMMEDIATE_MS)

    def sync(self):
        area = self.area
        if area.verticalScrollBarPolicy() != QtCore.Qt.ScrollBarAlwaysOff:
            self.vertical_allowed = True
            area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        if area.horizontalScrollBarPolicy() != QtCore.Qt.ScrollBarAlwaysOff:
            self.horizontal_allowed = True
            area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.vertical.sync()
        self.horizontal.sync()
        vertical = self.vertical_allowed and self.vertical.maximum() > self.vertical.minimum()
        horizontal = self.horizontal_allowed and self.horizontal.maximum() > self.horizontal.minimum()
        rect = area.viewport().rect()
        width = tokens.SCROLLBAR_WIDTH
        self.vertical.setGeometry(rect.right() - width + 1, 0, width, max(0, rect.height() - width * horizontal))
        self.horizontal.setGeometry(0, rect.bottom() - width + 1, max(0, rect.width() - width * vertical), width)
        self.vertical.setVisible(vertical)
        self.horizontal.setVisible(horizontal)
        self.vertical.raise_()
        self.horizontal.raise_()

    def eventFilter(self, obj, event):
        if event.type() in (QtCore.QEvent.Resize, QtCore.QEvent.Show, QtCore.QEvent.LayoutRequest,
                            QtCore.QEvent.StyleChange, QtCore.QEvent.Wheel):
            self.schedule()
        return False

    def shutdown(self):
        self.timer.stop()
        self.area.removeEventFilter(self)
        self.area.viewport().removeEventFilter(self)
        for source in (self.area.verticalScrollBar(), self.area.horizontalScrollBar()):
            source.rangeChanged.disconnect(self.schedule)
            source.valueChanged.disconnect(self.schedule)
        self.vertical.hide()
        self.horizontal.hide()
