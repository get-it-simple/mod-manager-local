from __future__ import annotations

from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from typing import Callable
from queue import Empty, Queue

from PySide6 import QtCore

from ..workers import WorkerPool
from ..progress import reporting
from ..storage_policy import storage_policy
from .theme import tokens

GLOBAL_KEY = "global"


@dataclass
class QueuedAction:
    identifier: int
    label: str
    worker: Callable
    done: Callable | None
    config: dict | None
    mod_names: tuple[str, ...]
    preset_names: tuple[str, ...]
    blocking: bool
    barrier: bool
    prepare: Callable | None


class TaskRunner(QtCore.QObject):
    busyChanged = QtCore.Signal(bool)
    statusChanged = QtCore.Signal(str)
    failed = QtCore.Signal(str)
    progressChanged = QtCore.Signal(object)
    activityChanged = QtCore.Signal(bool)
    actionFinished = QtCore.Signal()
    queueChanged = QtCore.Signal()
    commandStarted = QtCore.Signal(object)
    commandFinished = QtCore.Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.busy = False
        self.status_text = ""
        self.active = False
        self._pool = WorkerPool()
        self._progress = Queue()
        self._generation = 0
        self._queue = deque()
        self._current = None
        self._closed = False
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self.poll)

    @property
    def commands(self) -> tuple[QueuedAction, ...]:
        return ((self._current,) if self._current is not None else ()) + tuple(self._queue)

    @property
    def pending_mods(self) -> set[str]:
        return {name for command in self.commands for name in command.mod_names}

    @property
    def pending_presets(self) -> set[str]:
        return {name for command in self.commands for name in command.preset_names}

    @property
    def barrier_pending(self) -> bool:
        return any(command.barrier for command in self.commands)

    def set_status(self, text: str) -> None:
        self.status_text = text
        self.statusChanged.emit(text)

    def pin_current_config(self, config: dict) -> None:
        if self._current is not None:
            self._current.config = deepcopy(config)

    def set_busy(self, busy: bool, text: str = "") -> None:
        self.busy = busy
        self.busyChanged.emit(busy)
        if text:
            self.set_status(text)

    def run(self, label: str, worker: Callable, done: Callable | None = None, file_key: str = GLOBAL_KEY,
            *, config: dict | None = None, mod_names=(), preset_names=(), blocking: bool = True,
            barrier: bool = False, prepare: Callable | None = None, front: bool = False) -> None:
        if self._closed:
            return
        self._generation += 1
        command = QueuedAction(self._generation, label, worker, done, deepcopy(config),
                               tuple(mod_names), tuple(preset_names), blocking, barrier, prepare)
        if front:
            self._queue.appendleft(command)
        else:
            self._queue.append(command)
        self.queueChanged.emit()
        self._update_activity()
        self._dispatch()

    def _dispatch(self) -> None:
        if self._current is not None or not self._queue or self._closed:
            return
        command = self._current = self._queue.popleft()
        self.queueChanged.emit()
        self.set_status(command.label)
        if command.blocking:
            self.set_busy(True)
        try:
            accepted = command.prepare is None or command.prepare() is not False
        except Exception as error:
            self.failed.emit(str(error))
            accepted = False
        if not accepted:
            self._finish(command)
            return
        self.commandStarted.emit(command)

        def work():
            with storage_policy(strict=True, migrate=False, config=command.config):
                with reporting(lambda progress: self._progress.put((command.identifier, progress))):
                    return command.worker()

        def callback(result, error):
            if self._closed:
                return
            self._drain_progress()
            try:
                if error is not None:
                    self.failed.emit(str(error))
                elif command.done:
                    command.done(result)
            finally:
                self._finish(command)

        self.background(work, callback, "operations")

    def _finish(self, command) -> None:
        self.commandFinished.emit(command)
        if command.blocking:
            self.set_busy(False)
        self._current = None
        self.queueChanged.emit()
        self._update_activity()
        self.actionFinished.emit()
        self._dispatch()

    def poll(self) -> None:
        self._drain_progress()
        polled = self._pool.poll()
        self._pool.fire_callbacks(polled)
        self._update_activity()
        if not self._pool.has_work():
            self._timer.stop()

    def background(self, worker: Callable, callback: Callable, file_key: str = GLOBAL_KEY) -> None:
        if self._closed:
            return
        self._pool.submit(file_key, worker, callback=callback)
        self._update_activity()
        self._timer.start(tokens.WORKER_POLL_MS)

    def _update_activity(self) -> None:
        active = bool(self.commands) or self._pool.has_work()
        if active != self.active:
            self.active = active
            self.activityChanged.emit(active)

    def _drain_progress(self) -> None:
        while True:
            try:
                generation, progress = self._progress.get_nowait()
            except Empty:
                break
            if self._current is not None and generation == self._current.identifier:
                self.progressChanged.emit(progress)

    def shutdown(self) -> None:
        self._closed = True
        self._queue.clear()
        self._current = None
        self._timer.stop()
        self._pool.shutdown()
        self._update_activity()
