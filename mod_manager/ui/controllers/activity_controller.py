from __future__ import annotations

from PySide6 import QtCore

from ..theme import tokens
from ..widgets.activity_indicator import ActivityIndicator
from ..widgets.operation_cover import OperationCover
from ..widgets.operation_feedback import OperationVisual


class ActivityController(QtCore.QObject):
    changed = QtCore.Signal()

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self._closed = False
        self._last_tick = 0
        self._painted_names = set()
        self._painted_presets = set()
        self._visual_busy = False
        self._detail_frame = None
        self._detail_selection = ()
        self._detail_results = {}
        self._detail_touched = set()
        self.detail_cover = OperationCover(window.detail_scroll, window.theme)
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

    @property
    def visual_busy(self) -> bool:
        return bool(self._frames())

    def _frames(self):
        frames = [*self.window.mods_model.operation_frames.values(),
                  *self.window.presets_model.operation_frames.values()]
        if self._detail_frame is not None:
            frames.append(self._detail_frame)
        return {id(frame): frame for frame in frames}.values()

    def _new_frame(self):
        return OperationVisual(elapsed=0 if self.window.motion.enabled else tokens.OPERATION_FADE_MS)

    def _busy_changed(self, busy: bool) -> None:
        model = self.window.mods_model
        presets = self.window.presets_model
        if busy:
            self.window.motion.stop_fade(self.window.detail_frame)
            if self.window._detail_preview is not None:
                self.window.motion.stop_fade(self.window._detail_preview[1])
            model.operation_frames.clear()
            presets.operation_frames.clear()
            self._detail_frame = None
            self._detail_selection = tuple(self.window._selected_mod_names())
            self._detail_results.clear()
            self._detail_touched.clear()
        else:
            if self._detail_frame is not None and len(self._detail_selection) > 1:
                self._detail_frame.success = bool(self._detail_touched) and all(
                    self._detail_results.get(name, False) for name in self._detail_touched)
            for frame in self._frames():
                if frame.finished_at is None:
                    frame.finished_at = frame.elapsed
            model.set_active_mods(set())
        self._update_views()
        self.sync()

    def selection_changed(self) -> None:
        selection = tuple(self.window._selected_mod_names())
        if selection != self._detail_selection:
            self._detail_selection = selection
            self._detail_frame = None
            self._detail_results.clear()
            self._detail_touched.clear()
            if len(selection) == 1:
                self._detail_frame = self.window.mods_model.operation_frames.get(selection[0])
        self.detail_cover.refresh_content()
        self.detail_cover.set_frame(self._detail_frame)
        self.sync()

    def update_progress(self, progress) -> None:
        if self._closed:
            return
        if progress.preset_name:
            frames = self.window.presets_model.operation_frames
            if progress.preset_state == "started":
                frames[progress.preset_name] = self._new_frame()
            elif progress.preset_state == "finished":
                frame = frames.get(progress.preset_name)
                if frame is not None:
                    frame.finished_at = frame.elapsed
                    frame.success = progress.preset_success is True
        if progress.mod_names:
            self._mod_progress(progress)
        self._update_views()
        self.sync()

    def _mod_progress(self, progress) -> None:
        model = self.window.mods_model
        names = set(model.active_mods)
        relevant = set(progress.mod_names).intersection(self._detail_selection)
        if progress.mod_state == "started":
            names.update(progress.mod_names)
            visible = {mod.name for mod in model.mods}
            for name in progress.mod_names:
                if name in visible:
                    model.operation_frames[name] = self._new_frame()
            if relevant:
                self._detail_touched.update(relevant)
                if self._detail_frame is None:
                    self._detail_frame = (model.operation_frames.get(next(iter(relevant)))
                                          if len(self._detail_selection) == 1 else self._new_frame())
        elif progress.mod_state == "finished":
            names.difference_update(progress.mod_names)
            results = {item.name: item.success for item in progress.mod_results}
            self._detail_results.update({name: results.get(name, False) for name in relevant})
            for name in progress.mod_names:
                frame = model.operation_frames.get(name)
                if frame is not None:
                    frame.finished_at = frame.elapsed
                    frame.success = results.get(name, False)
        model.set_active_mods(names)

    def sync(self, *_args) -> None:
        if self._closed:
            return
        window = self.window
        active = window.runner.busy or window.runner.active or window.library.loading
        self.indicator.setVisible(active)
        self.indicator.reposition()
        self.indicator.raise_()
        if not window.motion.enabled:
            for frame in self._frames():
                frame.elapsed = tokens.OPERATION_FADE_MS
            self._discard_frames(lambda frame: frame.finished_at is not None)
        busy = self.visual_busy
        if busy != self._visual_busy:
            self._visual_busy = busy
            self.changed.emit()
        animate = (active or busy) and window.isVisible() and window.motion.enabled
        if animate:
            if self.animation.state() != QtCore.QAbstractAnimation.State.Running:
                self._last_tick = 0
                self.animation.start()
        else:
            self.animation.stop()
            self._last_tick = 0
            self.indicator.set_phase(0.5)
        self._update_views()

    def _discard_frames(self, discard):
        for model in (self.window.mods_model, self.window.presets_model):
            model.operation_frames = {name: frame for name, frame in model.operation_frames.items()
                                      if not discard(frame)}
        if self._detail_frame is not None and discard(self._detail_frame):
            self._detail_frame = None

    def _paint_frame(self, phase: float) -> None:
        self.indicator.set_phase(phase)
        self.window.mods_model.activity_phase = phase
        now = self.animation.currentTime()
        delta = max(0, now - self._last_tick)
        self._last_tick = now
        for frame in self._frames():
            frame.elapsed += delta
        self._discard_frames(lambda frame: frame.done)
        self._update_views()
        if self.visual_busy != self._visual_busy:
            self.sync()

    def _loop_changed(self, _loop: int) -> None:
        self._paint_frame(self.animation.currentValue())

    def _update_views(self) -> None:
        model = self.window.mods_model
        names = self._painted_names | model.operation_frames.keys()
        self._painted_names = set(model.operation_frames)
        for view in (self.window.mods_table, self.window.tiles_view):
            if view.isVisible() and names:
                self._update_rows(view, [mod.name for mod in model.mods], names)
        model = self.window.presets_model
        names = self._painted_presets | model.operation_frames.keys()
        self._painted_presets = set(model.operation_frames)
        if self.window.presets_table.isVisible() and names:
            self._update_rows(self.window.presets_table, model.keys, names)
        self.detail_cover.set_frame(self._detail_frame)

    def _update_rows(self, view, keys, names):
        viewport = view.viewport()
        for row, name in enumerate(keys):
            if name in names:
                rect = view.visualRect(view.model().index(row, 0))
                if view is not self.window.tiles_view:
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
        self._discard_frames(lambda _frame: True)
        self.window.mods_model.set_active_mods(set())
        self.detail_cover.shutdown()
        self.window.removeEventFilter(self)
        self.window.runner.activityChanged.disconnect(self.sync)
        self.window.runner.busyChanged.disconnect(self._busy_changed)
        self.window.runner.progressChanged.disconnect(self.update_progress)
        self.window.library.changed.disconnect(self.sync)
        self.window.motion.enabledChanged.disconnect(self.sync)
        self.indicator.shutdown()
