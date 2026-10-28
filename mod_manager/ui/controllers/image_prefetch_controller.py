from __future__ import annotations

from math import ceil, floor

from PySide6 import QtCore

from ..theme import tokens


class ImagePrefetchController(QtCore.QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.view = window.tiles_view
        self._closed = False
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.refresh)
        self.view.viewport().installEventFilter(self)
        self.view.verticalScrollBar().valueChanged.connect(self.schedule)
        self.view.model().modelReset.connect(self.schedule)
        self.view.model().layoutChanged.connect(self.schedule)

    def schedule(self, *_args):
        if not self._closed and not self._timer.isActive():
            self._timer.start(tokens.IMMEDIATE_MS)

    def eventFilter(self, obj, event):
        if event.type() in (QtCore.QEvent.Type.Resize, QtCore.QEvent.Type.Show, QtCore.QEvent.Type.Hide):
            self.schedule()
        return False

    def requests(self):
        view = self.view
        model = view.model()
        count = model.rowCount()
        if not view.isVisible() or not count:
            return []
        first = view.visualRect(model.index(0, 0))
        if first.isEmpty():
            return []
        low, high = 1, count
        while low < high:
            middle = (low + high) // 2
            if view.visualRect(model.index(middle, 0)).top() == first.top():
                low = middle + 1
            else:
                high = middle
        columns = low
        stride = (view.visualRect(model.index(columns, 0)).top() - first.top()
                  if columns < count else first.height() + view.spacing() * 2)
        if stride <= 0:
            return []
        first_row = max(0, ceil(-first.bottom() / stride))
        last_row = min((count - 1) // columns, floor((view.viewport().height() - 1 - first.top()) / stride))
        rows = list(range(first_row, last_row + 1))
        for distance in range(1, tokens.IMAGE_PREFETCH_ROWS + 1):
            rows.extend((first_row - distance, last_row + distance))
        size = self.window.tile_delegate.preview_size(first)
        return [(model.mods[index].name, size) for row in rows if 0 <= row <= (count - 1) // columns
                for index in range(row * columns, min(count, (row + 1) * columns))]

    def refresh(self):
        if not self._closed:
            self.window.images.set_tile_window(self.window.cfg, self.requests())

    def shutdown(self):
        self._closed = True
        self._timer.stop()
        self.view.viewport().removeEventFilter(self)
        self.view.verticalScrollBar().valueChanged.disconnect(self.schedule)
        self.view.model().modelReset.disconnect(self.schedule)
        self.view.model().layoutChanged.disconnect(self.schedule)
        self.window.images.set_tile_window(self.window.cfg, [])
