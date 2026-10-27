from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy

from .labels import ResolvedLabels
from .library_state import folder_issues
from .models import ModItem
from .storage_policy import storage_policy


@dataclass(frozen=True)
class LibrarySnapshot:
    profile_id: str
    items: tuple[ModItem, ...]
    labels: ResolvedLabels
    records: dict
    favorites: frozenset[str]
    created: dict[str, float]
    issues: tuple[str, ...]
    presets: dict
    preset_records: dict
    installed: frozenset[str]
    broken: tuple[ModItem, ...]


def load_library_snapshot(cfg: dict) -> LibrarySnapshot:
    from . import mods, storage

    cfg = deepcopy(cfg)
    with storage_policy(strict=True, migrate=False, config=cfg):
        items, _shown, _page, _pages, labels = mods.mods_view(cfg, 1, (), (), "d")
        created = {}
        for mod in items:
            try:
                created[mod.name] = mod.src.stat().st_ctime
            except OSError:
                created[mod.name] = 0
        return LibrarySnapshot(
            str(cfg.get("active_game_profile_id") or ""), tuple(items), labels,
            mods.mods_records(), frozenset(storage.load_favorites(cfg)), created,
            folder_issues(cfg), storage.load_presets(), storage.load_preset_records(),
            frozenset(mod.name for mod in mods.list_installed_mods(cfg)),
            tuple(mods.list_broken_links(cfg)),
        )
