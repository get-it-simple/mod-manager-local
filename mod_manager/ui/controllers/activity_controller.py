from __future__ import annotations

from PySide6 import QtCore

from ..theme import tokens
from ..widgets.activity_indicator import ActivityIndicator
from ..widgets.operation_feedback import OperationVisual


class ActivityController(QtCore.QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self._closed = False
        self._last_tick = 0
        self._painted_names = set()
        self.indicator = ActivityIndicator(window.statusBar())
        self.animation = QtCore.QVariantAnimation(self)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setDuration(tokens.ACTIVITY_DURATION_MS)
        self.animation.setLoopCount(-1)
        self.animation.setEasingCurve(QtCore.QEasingCurve.Type.Linear)
        self.animation.valueChanged.connect(self._paint_frame)
        self.animation.currentLoopChanged.connect(self._loop_changed)
        window.runner.activityChanged.connect(self.sync)
        window.runner.busyChanged.connect(self._busy_changed)
        window.runner.progressChanged.connect(self.update_progress)
        window.library.changed.connect(self.sync)
        window.motion.enabledChanged.connect(self.sync)
        window.installEventFilter(self)

    def _busy_changed(self, busy: bool) -> None:
        model = self.window.mods_model
        if busy:
            model.operation_frames.clear()
        else:
            for name in model.active_mods:
                frame = model.operation_frames.get(name)
                if frame is not None and frame.finished_at is None:
                    frame.finished_at = frame.elapsed
            model.set_active_mods(set())
        self._update_views()
        self.sync()

    def update_progress(self, progress) -> None:
        if self._closed or not progress.mod_names:
            return
        model = self.window.mods_model
        names = set(model.active_mods)
        if progress.mod_state == "started":
            names.update(progress.mod_names)
            visible = {mod.name for mod in model.mods}
            for name in progress.mod_names:
                if name in visible:
                    frame = OperationVisual()
                    if not self.window.motion.enabled:
                        frame.elapsed = tokens.OPERATION_FADE_MS
                    model.operation_frames[name] = frame
        elif progress.mod_state == "finished":
            names.difference_update(progress.mod_names)
            results = {item.name: item.success for item in progress.mod_results}
            for name in progress.mod_names:
                frame = model.operation_frames.get(name)
                if frame is not None:
                    frame.finished_at = frame.elapsed
                    frame.success = results.get(name, False)
                    if not self.window.motion.enabled:
                        model.operation_frames.pop(name, None)
        else:
            return
        model.set_active_mods(names)
        self._update_views()
        self.sync()

    def sync(self, *_args) -> None:
        if self._closed:
            return
        window = self.window
        model = window.mods_model
        active = window.runner.busy or window.runner.active or window.library.loading
        self.indicator.setVisible(active)
        self.indicator.reposition()
        self.indicator.raise_()
        if not window.motion.enabled:
            model.operation_frames = {name: frame for name, frame in model.operation_frames.items()
                                      if frame.finished_at is None}
            for frame in model.operation_frames.values():
                frame.elapsed = tokens.OPERATION_FADE_MS
        animate = (active or bool(model.operation_frames)) and window.isVisible() and window.motion.enabled
        if animate:
            if self.animation.state() != QtCore.QAbstractAnimation.State.Running:
                self._last_tick = 0
                self.animation.start()
        else:
            self.animation.stop()
            self._last_tick = 0
            self.indicator.set_phase(0.5)
            self._update_views()

    def _paint_frame(self, phase: float) -> None:
        self.indicator.set_phase(phase)
        model = self.window.mods_model
        model.activity_phase = phase
        now = self.animation.currentTime()
        delta = max(0, now - self._last_tick)
        self._last_tick = now
        finished = []
        for name, frame in model.operation_frames.items():
            frame.elapsed += delta
            if frame.done:
                finished.append(name)
        for name in finished:
            model.operation_frames.pop(name, None)
        self._update_views()
        if finished:
            self.sync()

    def _loop_changed(self, _loop: int) -> None:
        self._paint_frame(self.animation.currentValue())

    def _update_views(self) -> None:
        model = self.window.mods_model
        names = self._painted_names | model.operation_frames.keys()
        self._painted_names = set(model.operation_frames)
        if not names:
            return
        for view in (self.window.mods_table, self.window.tiles_view):
            if view.isVisible():
                viewport = view.viewport()
                for row, mod in enumerate(model.mods):
                    if mod.name in names:
                        rect = view.visualRect(model.index(row, 0))
                        if view is self.window.mods_table:
                            rect.setLeft(0)
                            rect.setWidth(viewport.width())
                        if rect.intersects(viewport.rect()):
                            viewport.update(rect)

    def eventFilter(self, obj, event):
        if event.type() in (QtCore.QEvent.Type.Show, QtCore.QEvent.Type.Hide):
            self.sync()
        return False

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.animation.stop()
        self.window.mods_model.set_active_mods(set())
        self.window.mods_model.operation_frames.clear()
        self.window.removeEventFilter(self)
        self.window.runner.activityChanged.disconnect(self.sync)
        self.window.runner.busyChanged.disconnect(self._busy_changed)
        self.window.runner.progressChanged.disconnect(self.update_progress)
        self.window.library.changed.disconnect(self.sync)
        self.window.motion.enabledChanged.disconnect(self.sync)
        self.indicator.shutdown()
