from __future__ import annotations

from PySide6 import QtCore, QtWidgets
from weakref import WeakSet
from shiboken6 import isValid

from ..motion import motion_for
from ..theme import tokens
from ..widgets.overlay_scrollbar import OverlayScrollArea


class InteractionController(QtCore.QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.areas = WeakSet()
        self.closed = False
        QtWidgets.QApplication.instance().installEventFilter(self)

    def eventFilter(self, obj, event):
        kind = event.type()
        if kind in (QtCore.QEvent.Polish, QtCore.QEvent.Show, QtCore.QEvent.EnabledChange):
            if isinstance(obj, QtWidgets.QWidget) and motion_for(obj) is self.window.motion:
                if isinstance(obj, (QtWidgets.QAbstractButton, QtWidgets.QComboBox)):
                    obj.setCursor(QtCore.Qt.PointingHandCursor if obj.isEnabled() else QtCore.Qt.ArrowCursor)
                if (isinstance(obj, QtWidgets.QAbstractScrollArea) and not isinstance(obj, QtWidgets.QHeaderView)
                        and not hasattr(obj, "_overlay_scrollbars")):
                    obj._overlay_scrollbars = None
                    QtCore.QTimer.singleShot(tokens.IMMEDIATE_MS, obj, lambda area=obj: self._attach_area(area))
                if isinstance(obj, QtWidgets.QAbstractItemView):
                    obj.setMouseTracking(True)
                    if not obj.isEnabled():
                        obj.viewport().setCursor(QtCore.Qt.ArrowCursor)
                if isinstance(obj, QtWidgets.QAbstractScrollArea) and getattr(obj, "_overlay_scrollbars", None) is not None:
                    self.areas.add(obj)
        elif kind == QtCore.QEvent.MouseMove and isinstance(obj, QtWidgets.QWidget):
            view = obj.parentWidget()
            if isinstance(view, QtWidgets.QAbstractItemView) and obj is view.viewport() and motion_for(view) is self.window.motion:
                index = view.indexAt(event.position().toPoint())
                actionable = (view.isEnabled() and index.isValid()
                              and bool(index.flags() & QtCore.Qt.ItemIsEnabled)
                              and bool(index.flags() & (QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsUserCheckable)))
                obj.setCursor(QtCore.Qt.PointingHandCursor if actionable else QtCore.Qt.ArrowCursor)
        return False

    def _attach_area(self, area):
        if not self.closed:
            area._overlay_scrollbars = OverlayScrollArea(area)
            self.areas.add(area)

    def shutdown(self):
        self.closed = True
        QtWidgets.QApplication.instance().removeEventFilter(self)
        for area in tuple(self.areas):
            if isValid(area) and area._overlay_scrollbars is not None:
                area._overlay_scrollbars.shutdown()
