from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass

from PySide6 import QtCore, QtGui

from .theme import tokens


@dataclass(frozen=True)
class ImageKey:
    generation: int
    revision: int
    profile: str
    source: str
    name: str
    width: int
    height: int
    cover: bool


def decode_image(cfg, key: ImageKey, path_for) -> QtGui.QImage:
    path = path_for(cfg, key.name)
    if path is None:
        return QtGui.QImage()
    reader = QtGui.QImageReader(str(path))
    reader.setAutoTransform(True)
    target = QtCore.QSize(key.width, key.height)
    source = reader.size()
    aspect = QtCore.Qt.KeepAspectRatioByExpanding if key.cover else QtCore.Qt.KeepAspectRatio
    if source.isValid():
        reader.setScaledSize(source.scaled(target, aspect))
    image = reader.read()
    if image.isNull():
        return image
    image = image.scaled(target, aspect, QtCore.Qt.SmoothTransformation)
    if key.cover:
        image = image.copy((image.width() - target.width()) // 2,
                           (image.height() - target.height()) // 2, target.width(), target.height())
    return image


class ImageCache(QtCore.QObject):
    ready = QtCore.Signal(str)

    def __init__(self, runner, path_for, parent=None):
        super().__init__(parent)
        self.runner = runner
        self.path_for = path_for
        self._cache = OrderedDict()
        self._pending = OrderedDict()
        self._priority = set()
        self._active = {}
        self._tiles = OrderedDict()
        self._tile_done = set()
        self._generation = 0
        self._revisions = {}
        self._bytes = 0
        self._closed = False

    @property
    def byte_count(self) -> int:
        return self._bytes

    def _key(self, cfg, name, size, cover):
        return ImageKey(self._generation, self._revisions.get(name, 0),
                        str(cfg.get("active_game_profile_id") or ""), str(cfg.get("mods_source_dir") or ""),
                        name, max(1, size.width()), max(1, size.height()), cover)

    def set_tile_window(self, cfg, requests):
        snapshot = deepcopy(cfg)
        self._tiles = OrderedDict((self._key(cfg, name, size, True), snapshot) for name, size in requests)
        self._tile_done.intersection_update(self._tiles)
        for key in list(self._pending):
            if key.cover and key not in self._priority:
                self._pending.pop(key)
        self._dispatch()

    def _fill_tiles(self):
        for key, cfg in self._tiles.items():
            if len(self._pending) >= tokens.IMAGE_PENDING_LIMIT:
                break
            if key not in self._cache and key not in self._active and key not in self._tile_done:
                self._pending.setdefault(key, cfg)

    def request(self, cfg, name: str, size: QtCore.QSize, *, cover=False, priority=False):
        key = self._key(cfg, name, size, cover)
        if key in self._cache:
            pixmap, _cost = self._cache[key]
            self._cache.move_to_end(key)
            return pixmap
        if self._closed:
            return None
        if key not in self._active:
            self._pending[key] = deepcopy(cfg)
            if priority:
                self._priority.add(key)
                self._pending.move_to_end(key, last=False)
            elif key not in self._priority:
                self._pending.move_to_end(key)
            while len(self._pending) > tokens.IMAGE_PENDING_LIMIT:
                discarded = next((candidate for candidate in self._pending if candidate not in self._priority),
                                 next(reversed(self._pending)))
                self._pending.pop(discarded)
                self._priority.discard(discarded)
            self._dispatch()
        return self._cache.get(key, (None, 0))[0]

    def _dispatch(self) -> None:
        self._fill_tiles()
        while self._pending and len(self._active) < tokens.IMAGE_WORKERS and not self._closed:
            key, cfg = self._pending.popitem(last=False)
            self._priority.discard(key)
            slot = next(slot for slot in range(tokens.IMAGE_WORKERS) if slot not in self._active.values())
            self._active[key] = slot
            self.runner.background(lambda cfg=cfg, key=key: decode_image(cfg, key, self.path_for),
                                   lambda image, error, key=key: self._completed(key, image, error),
                                   file_key=f"image-{slot}")

    def _completed(self, key, image, error) -> None:
        self._active.pop(key, None)
        if self._closed:
            return
        if key.generation == self._generation and key.revision == self._revisions.get(key.name, 0):
            if key in self._tiles:
                self._tile_done.add(key)
            pixmap = QtGui.QPixmap.fromImage(image) if error is None else QtGui.QPixmap()
            cost = max(1, pixmap.width() * pixmap.height() * max(1, pixmap.depth() // 8))
            if cost <= tokens.IMAGE_CACHE_BYTES:
                self._cache[key] = (pixmap, cost)
                self._bytes += cost
                while self._bytes > tokens.IMAGE_CACHE_BYTES or len(self._cache) > tokens.IMAGE_CACHE_ENTRIES:
                    _old, (_pixmap, old_cost) = self._cache.popitem(last=False)
                    self._bytes -= old_cost
            self.ready.emit(key.name)
        self._dispatch()

    def invalidate(self, name: str) -> None:
        self._revisions[name] = self._revisions.get(name, 0) + 1
        for key in list(self._cache):
            if key.name == name:
                _pixmap, cost = self._cache.pop(key)
                self._bytes -= cost
        for key in list(self._pending):
            if key.name == name:
                self._pending.pop(key)
                self._priority.discard(key)
        self._tiles = OrderedDict((self._key_for_revision(key), cfg) for key, cfg in self._tiles.items())
        self._tile_done = {key for key in self._tile_done if key.name != name}

    def _key_for_revision(self, key):
        return ImageKey(key.generation, self._revisions.get(key.name, 0), key.profile, key.source,
                        key.name, key.width, key.height, key.cover)

    def reset(self) -> None:
        self._generation += 1
        self._cache.clear()
        self._pending.clear()
        self._priority.clear()
        self._tiles.clear()
        self._tile_done.clear()
        self._revisions.clear()
        self._bytes = 0

    def shutdown(self) -> None:
        self._closed = True
        self.reset()
