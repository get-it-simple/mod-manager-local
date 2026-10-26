from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class Progress:
    stage: str
    name: str = ""
    completed: int = 0
    total: int = 0


_reporter = ContextVar("operation_reporter", default=None)


def report(stage: str, name: str = "", completed: int = 0, total: int = 0) -> None:
    callback = _reporter.get()
    if callback is not None:
        callback(Progress(stage, name, completed, total))


@contextmanager
def reporting(callback):
    token = _reporter.set(callback)
    try:
        yield
    finally:
        _reporter.reset(token)
