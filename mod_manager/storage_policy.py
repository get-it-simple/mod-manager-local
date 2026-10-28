from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from copy import deepcopy


@dataclass(frozen=True)
class StoragePolicy:
    strict: bool = False
    migrate: bool = True


_policy = ContextVar("storage_policy", default=StoragePolicy())
_profile_config = ContextVar("storage_profile_config", default=None)


def profile_config() -> dict | None:
    return _profile_config.get()


def current_policy() -> StoragePolicy:
    return _policy.get()


@contextmanager
def storage_policy(*, strict: bool = True, migrate: bool = False, config: dict | None = None):
    token = _policy.set(StoragePolicy(strict, migrate))
    config_token = _profile_config.set(deepcopy(config) if config is not None else _profile_config.get())
    try:
        yield
    finally:
        _profile_config.reset(config_token)
        _policy.reset(token)


class StorageError(ValueError):
    pass
