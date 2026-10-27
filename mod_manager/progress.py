from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from collections.abc import Callable, Iterator

from .models import OperationItem


@dataclass(frozen=True)
class Progress:
    stage: str
    name: str = ""
    completed: int = 0
    total: int = 0
    mod_names: tuple[str, ...] = ()
    mod_state: str = ""
    mod_results: tuple[OperationItem, ...] = ()


_reporter: ContextVar[Callable[[Progress], None] | None] = ContextVar("operation_reporter", default=None)


def report(stage: str, name: str = "", completed: int = 0, total: int = 0, *,
           mod_names: tuple[str, ...] = (), mod_state: str = "",
           mod_results: tuple[OperationItem, ...] = ()) -> None:
    callback = _reporter.get()
    if callback is not None:
        callback(Progress(stage, name, completed, total, mod_names, mod_state, mod_results))


@contextmanager
def mod_activity(stage: str, names: tuple[str, ...]) -> Iterator[list[OperationItem]]:
    report(stage, mod_names=names, mod_state="started")
    results: list[OperationItem] = []
    try:
        yield results
    finally:
        report(stage, mod_names=names, mod_state="finished", mod_results=tuple(results))


@contextmanager
def reporting(callback):
    token = _reporter.set(callback)
    try:
        yield
    finally:
        _reporter.reset(token)
