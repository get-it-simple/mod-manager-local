from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from .links import UNSUPPORTED_LINKS
from .models import ModFile, ModItem, OperationResult
from .mods import change_mods, list_installed_mods
from .storage import active_game_profile, load_presets, mark_preset_managed, update_game_profile


COPY_RECOVERY_TITLE = "Links are not supported"
COPY_RECOVERY_QUESTION = (
    "The destination file system does not support links. "
    "Change this game's Install method to Copy, save the profile, "
    "and retry the failed installations? Existing successful installations will be kept."
)
PROFILE_CHANGED = "The game profile or installation settings changed. Start the installation again."
PROFILE_KEYS = (
    "active_game_profile_id", "mods_source_dir", "game_mods_dir", "install_mode",
    "link_prefix", "mod_group_extensions", "mod_extensions", "mod_recursive_scan",
)


def needs_copy_recovery(result: OperationResult) -> bool:
    return any(
        failure.code == UNSUPPORTED_LINKS
        for item in result.items if item.action == "installed" and not item.success
        for failure in item.failures
    )


def validate_recovery_profile(cfg: dict, original: dict) -> None:
    profile = active_game_profile(cfg)
    previous = active_game_profile(original)
    if (not profile or not previous or profile["id"] != previous["id"]
            or any(cfg.get(key) != original.get(key) or profile.get(key) != previous.get(key)
                   for key in PROFILE_KEYS)):
        raise ValueError(PROFILE_CHANGED)


def save_copy_profile(cfg: dict, original: dict) -> None:
    from .storage import save_config

    validate_recovery_profile(cfg, original)
    updated = deepcopy(cfg)
    profile = active_game_profile(updated)
    update_game_profile(updated, profile["id"], {"install_mode": "copy"})
    save_config(updated)
    cfg.clear()
    cfg.update(updated)


def copy_retry_mods(result: OperationResult) -> list[ModItem]:
    members: dict[str, dict[Path, ModFile]] = {}
    for item in result.items:
        if item.action != "installed" or item.success:
            continue
        for failure in item.failures:
            members.setdefault(item.name, {})[failure.dest] = ModFile(
                failure.src, failure.dest, failure.src.is_dir(),
            )
    mods = []
    for name, files in members.items():
        group = tuple(files.values())
        first = group[0]
        mods.append(ModItem(name, first.src, first.dest, first.is_dir, False, group, True))
    return mods


def preset_install_names(names: list[str], installed: set[str]) -> tuple[str, ...]:
    presets = load_presets()
    return tuple(name for name in names if name in presets and not (
        presets[name] and all(member in installed for member in presets[name])
    ))


def retry_copy_installations(
    cfg: dict, initial: OperationResult, overwrite: bool = False,
    preset_names: tuple[str, ...] = (),
) -> OperationResult:
    retry = change_mods(copy_retry_mods(initial), "install", overwrite, pending_only=False)
    replacements = {item.name: item for item in retry.items}
    result = OperationResult(tuple(
        replacements.get(item.name, item)
        if item.action == "installed" and not item.success else item
        for item in initial.items
    ))
    if preset_names:
        installed = {mod.name for mod in list_installed_mods(cfg)}
        presets = load_presets()
        for name in preset_names:
            members = presets.get(name)
            if members and all(member in installed for member in members):
                mark_preset_managed(name, "applied")
    return result


def retry_outcomes(initial: OperationResult, recovered: OperationResult) -> OperationResult:
    previous = {id(item) for item in initial.items}
    retried = {id(item): item for item in recovered.items if id(item) not in previous}
    return OperationResult(tuple(retried.values()))
