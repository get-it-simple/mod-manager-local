from __future__ import annotations

from mod_manager.library_snapshot import LibrarySnapshot


def inline_background(_runner, worker, callback, file_key="global"):
    try:
        result = worker()
    except Exception as error:
        callback(None, error)
    else:
        callback(result, None)


class InlineRunner:
    background = inline_background


def synthetic_snapshot(cfg):
    from mod_manager.ui import app

    items, _shown, _page, _pages, labels = app.mods_view(cfg, 1, (), (), "d")
    presets, _keys, _page_keys, _page, _pages = app.presets_view(cfg, 1, "d")
    return LibrarySnapshot(
        str(cfg.get("active_game_profile_id") or ""), tuple(items), labels,
        app.mods_records(), frozenset(app.load_favorites(cfg)), {mod.name: 0 for mod in items},
        app.folder_issues(cfg), presets, app.presets_records(),
        frozenset(mod.name for mod in app.list_installed_mods(cfg)), tuple(app.list_broken_links(cfg)),
    )
