from __future__ import annotations

from .i18n import t

from dataclasses import dataclass, replace

from .models import ModItem, OperationItem, OperationResult
from .mods import change_mods, discover_mods
from .storage import load_presets, mark_preset_managed


@dataclass(frozen=True)
class PresetChange:
    preset: str
    name: str
    action: str
    mod: ModItem | None = None


@dataclass(frozen=True)
class PresetPlan:
    profile: tuple
    definitions: tuple
    changes: tuple[PresetChange, ...]


def plan_presets(cfg: dict, names: list[str]) -> PresetPlan:
    definitions = load_presets()
    mods = {mod.name: mod for mod in discover_mods(cfg)}
    initial = {name for name, mod in mods.items() if mod.installed}
    simulated = set(initial)
    changes = []
    for preset in names:
        members = definitions.get(preset)
        if members is None:
            changes.append(PresetChange(preset, preset, "missing"))
            continue
        uninstall = bool(members) and all(name in initial for name in members)
        for name in dict.fromkeys(members):
            mod = mods.get(name)
            installed = name in simulated
            action = "unchanged"
            if mod is None:
                action = "missing"
            elif uninstall and name in simulated:
                action = "uninstall"
                simulated.remove(name)
            elif not uninstall and name not in simulated:
                action = "install"
                simulated.add(name)
            changes.append(PresetChange(preset, name, action, replace(mod, installed=installed) if mod else None))
    return PresetPlan(tuple(cfg.get(key) for key in ("active_game_profile_id", "mods_source_dir", "game_mods_dir", "install_mode")),
                      tuple((name, tuple(definitions[name]) if name in definitions else None) for name in names), tuple(changes))


def execute_preset_plan(plan: PresetPlan, overwrite: bool = False) -> OperationResult:
    results = []
    for preset, members in plan.definitions:
        changes = [change for change in plan.changes if change.preset == preset]
        items = []
        work = [change.mod for change in changes if change.mod is not None and change.action in ("install", "uninstall")]
        action = next((change.action for change in changes if change.action in ("install", "uninstall")), "install")
        for change in changes:
            if change.action == "missing":
                items.append(OperationItem(change.name, "missing", False, t('not_in_source')))
        if work:
            items.extend(change_mods(work, action=action, overwrite=overwrite).items)
        results.extend(items)
        if members is not None and not any(not item.success for item in items):
            state = "deactivated" if any(change.action == "uninstall" for change in changes) else "applied"
            mark_preset_managed(preset, state)
    return OperationResult(tuple(results))
