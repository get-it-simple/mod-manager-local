from __future__ import annotations

from .i18n import t

from typing import Dict, List, Tuple

from .models import ModItem, OperationItem, OperationResult
from .mods import discover_mods, list_installed_mods, apply_mods_batch_result, deactivate_mod_result
from .storage import load_presets, save_presets, load_preset_records, mark_preset_managed
from .collection_utils import page_slice, paginate

def save_preset_from_installed(cfg: Dict, name: str) -> Tuple[bool, str]:
    presets = load_presets()
    installed = list_installed_mods(cfg)
    if not installed:
        return False, t('no_installed_mods_to_save')
    presets[name] = [m.name for m in installed]
    save_presets(presets)
    mark_preset_managed(name, "saved")
    return True, t('preset_value0_saved_value1_mods', value0=f'{name}', value1=f'{len(installed)}')

def delete_presets_by_names(names: List[str]) -> Tuple[int, List[str]]:
    presets = load_presets()
    removed = 0
    missing = []
    for nm in names:
        if nm in presets:
            presets.pop(nm, None)
            removed += 1
        else:
            missing.append(nm)
    save_presets(presets)
    return removed, missing

def preset_mods_to_install(cfg: Dict, names: List[str]) -> Tuple[List[ModItem], List[str]]:
    """Return (mods a preset would install, member names missing from the source folder)."""
    presets = load_presets()
    all_mods = {m.name: m for m in discover_mods(cfg)}
    work: List[ModItem] = []
    missing: List[str] = []
    taken: set[str] = set()
    for name in names:
        for mod_name in presets.get(name, []):
            mod = all_mods.get(mod_name)
            if mod is None:
                missing.append(mod_name)
            elif not mod.installed and mod_name not in taken:
                taken.add(mod_name)
                work.append(mod)
    return work, missing

def toggle_presets_by_names(
    cfg: Dict,
    names: List[str],
    installed_set: set[str],
    overwrite: bool = False,
) -> Tuple[str, List[str], bool]:
    summary, result, messages = _toggle_presets_result(cfg, names, installed_set, overwrite)
    return summary, messages, bool(result.errors)


def toggle_presets_result(
    cfg: Dict, names: List[str], installed_set: set[str], overwrite: bool = False,
) -> Tuple[str, OperationResult]:
    summary, result, _messages = _toggle_presets_result(cfg, names, installed_set, overwrite)
    return summary, result


def _toggle_presets_result(
    cfg: Dict, names: List[str], installed_set: set[str], overwrite: bool,
) -> Tuple[str, OperationResult, List[str]]:
    presets = load_presets()
    last_operation = ""
    items = []
    messages = []
    for name in names:
        mods = presets.get(name, [])
        if name not in presets:
            items.append(OperationItem(name, "missing", False, t('preset_not_found')))
            messages.extend(_preset_messages(OperationResult((items[-1],))))
            continue
        all_on = bool(mods) and all(nm in installed_set for nm in mods)
        if all_on:
            result = deactivate_preset_result(cfg, name)
            label = t('deactivated')
        else:
            result = apply_preset_result(cfg, name, overwrite)
            label = t('installed_mods')
        successes = sum(item.success for item in result.items)
        last_operation = f"{label}: {successes}, Errors: {result.errors}"
        items.extend(result.items)
        messages.extend(_preset_messages(result, install=not all_on))
    return last_operation, OperationResult(tuple(items)), messages

def presets_view(cfg: Dict, page: int, order_mode: str = "d", *, snapshot=None) -> Tuple[Dict, List[str], List[str], int, int]:
    presets = load_presets() if snapshot is None else snapshot.presets
    records = load_preset_records() if snapshot is None else snapshot.preset_records
    keys = list(presets.keys())
    reverse = order_mode.startswith("-")
    mode = order_mode[1:] if reverse else order_mode
    if mode == "name":
        keys = sorted(keys, key=lambda k: k.lower(), reverse=reverse)
    elif mode == "mods":
        keys = sorted(keys, key=lambda k: (len(presets.get(k, [])), k.lower()), reverse=reverse)
    elif mode == "last_managed":
        keys = sorted(keys, key=lambda k: (records.get(k, {}).get("last_managed") or "", k.lower()), reverse=reverse)
    elif mode == "state":
        keys = sorted(keys, key=lambda k: (records.get(k, {}).get("state") or "undefined", k.lower()), reverse=reverse)
    page, pages = paginate(len(keys) if keys else 1, page, cfg)
    page_keys = page_slice(keys, page, cfg)
    return presets, keys, page_keys, page, pages

def presets_records() -> Dict[str, Dict]:
    return load_preset_records()

def delete_presets_by_indexes(cfg: Dict, page: int, indexes: List[int]) -> Tuple[int, List[str]]:
    presets, _keys, page_keys, _page, _pages = presets_view(cfg, page)
    to_delete = []
    for num in indexes:
        if 1 <= num <= len(page_keys):
            to_delete.append(page_keys[num - 1])
    return delete_presets_by_names(to_delete)

def preset_names_by_indexes(cfg: Dict, page: int, indexes: List[int]) -> List[str]:
    _presets, _keys, page_keys, _page, _pages = presets_view(cfg, page)
    return [page_keys[num - 1] for num in indexes if 1 <= num <= len(page_keys)]

def toggle_presets_by_indexes(
    cfg: Dict,
    page: int,
    indexes: List[int],
    installed_set: set[str],
    overwrite: bool = False,
) -> Tuple[str, List[str], bool]:
    names = preset_names_by_indexes(cfg, page, indexes)
    return toggle_presets_by_names(cfg, names, installed_set, overwrite)

def apply_preset(cfg: Dict, name: str, overwrite: bool = False) -> Tuple[int, int, List[str]]:
    result = apply_preset_result(cfg, name, overwrite)
    return sum(item.success for item in result.items), result.errors, _preset_messages(result, install=True)


def _preset_messages(result: OperationResult, *, install: bool = False) -> List[str]:
    messages = [
        t('skipped_value0_value1', value0=f'{item.name}', value1=f'{item.message}') if item.action == "missing"
        else f"{item.name}: {'OK' if item.success else 'ERR'} ({item.message})"
        for item in result.items
    ]
    if install and not any(item.action == "installed" for item in result.items):
        messages.append(t('nothing_to_install_all_present_or_missing'))
    return messages


def apply_preset_result(cfg: Dict, name: str, overwrite: bool = False) -> OperationResult:
    work, skipped_missing = preset_mods_to_install(cfg, [name])
    missing = tuple(OperationItem(nm, "missing", False, t('text_09edde0d290d')) for nm in skipped_missing)
    installed = apply_mods_batch_result(work, overwrite)
    result = OperationResult(missing + installed.items)
    if not result.errors:
        mark_preset_managed(name, "applied")
    return result

def deactivate_preset(cfg: Dict, name: str) -> Tuple[int, int, List[str]]:
    result = deactivate_preset_result(cfg, name)
    return sum(item.success for item in result.items), result.errors, _preset_messages(result)


def deactivate_preset_result(cfg: Dict, name: str) -> OperationResult:
    presets = load_presets()
    mods = {m.name: m for m in discover_mods(cfg)}
    names = presets.get(name, [])
    items = []
    for nm in names:
        m = mods.get(nm)
        if not m or not m.installed:
            continue
        items.append(deactivate_mod_result(m))
    result = OperationResult(tuple(items))
    if not result.errors:
        mark_preset_managed(name, "deactivated")
    return result
    
