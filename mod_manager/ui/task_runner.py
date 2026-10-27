from __future__ import annotations

from typing import Callable
from queue import Empty, Queue

from PySide6 import QtCore

from ..workers import WorkerPool
from ..progress import reporting
from .theme import tokens

GLOBAL_KEY = "global"


class TaskRunner(QtCore.QObject):
    busyChanged = QtCore.Signal(bool)
    statusChanged = QtCore.Signal(str)
    failed = QtCore.Signal(str)
    progressChanged = QtCore.Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.busy = False
        self.status_text = ""
        self._pool = WorkerPool()
        self._progress = Queue()
        self._generation = 0
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self.poll)

    def set_status(self, text: str) -> None:
        self.status_text = text
        self.statusChanged.emit(text)

    def set_busy(self, busy: bool, text: str = "") -> None:
        self.busy = busy
        self.busyChanged.emit(busy)
        if text:
            self.set_status(text)

    def run(self, label: str, worker: Callable, done: Callable | None = None, file_key: str = GLOBAL_KEY) -> None:
        self._generation += 1
        generation = self._generation
        self.set_busy(True, label)

        def work():
            with reporting(lambda progress: self._progress.put((generation, progress))):
                return worker()

        def callback(result, error):
            self._drain_progress()
            self.set_busy(False)
            if error:
                self.failed.emit(str(error))
                return
            if done:
                done(result)

        self._pool.submit(file_key, work, callback=callback)
        self._timer.start(tokens.WORKER_POLL_MS)

    def poll(self) -> None:
        self._drain_progress()
        polled = self._pool.poll()
        self._pool.fire_callbacks(polled)
        if not self._pool.has_work():
            self._timer.stop()

    def background(self, worker: Callable, callback: Callable, file_key: str = GLOBAL_KEY) -> None:
        self._pool.submit(file_key, worker, callback=callback)
        self._timer.start(tokens.WORKER_POLL_MS)

    def _drain_progress(self) -> None:
        while True:
            try:
                generation, progress = self._progress.get_nowait()
            except Empty:
                break
            if generation == self._generation:
                self.progressChanged.emit(progress)

    def shutdown(self) -> None:
        self._generation += 1
        self._timer.stop()
        self._pool.shutdown()
