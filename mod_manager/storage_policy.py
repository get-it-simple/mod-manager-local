from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class StoragePolicy:
    strict: bool = False
    migrate: bool = True


_policy = ContextVar("storage_policy", default=StoragePolicy())


def current_policy() -> StoragePolicy:
    return _policy.get()


@contextmanager
def storage_policy(*, strict: bool = True, migrate: bool = False):
    token = _policy.set(StoragePolicy(strict, migrate))
    try:
        yield
    finally:
        _policy.reset(token)


class StorageError(ValueError):
    pass
