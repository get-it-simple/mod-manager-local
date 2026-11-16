from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from uuid import UUID, uuid4

from . import storage
from .archive_backend import safe_relative_path
from .i18n import t
from .import_registry import directory_mods, register_directory_mod, unregister_directory_mod
from .imports import _remove_import_path
from .labels import LabelDefinition
from .models import ModItem, OperationItem, OperationResult
from .mod_modes import TRASH_DIRECTORY
from .mods import IMAGE_EXTENSIONS, deactivate_mod_result
from .progress import mod_activity
from .platform_utils import hide_directory
from .storage_policy import storage_policy

RETENTION_DAYS = 14


@dataclass(frozen=True)
class TrashEntry:
    root: Path
    identifier: str
    data: dict
    missing: tuple[str, ...] = ()

    @property
    def name(self) -> str:
        return self.data["name"]

    @property
    def path(self) -> Path:
        return self.root / TRASH_DIRECTORY / self.identifier


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _exists(path: Path) -> bool:
    return path.exists() or path.is_symlink() or path.is_junction()


def _registry() -> Path:
    return storage.PROFILE_DATA_DIR / "trash-roots.json"


def trash_roots(cfg: dict) -> list[Path]:
    saved = storage.load_json(_registry(), {"roots": []})
    roots = saved.get("roots", []) if isinstance(saved, dict) else []
    roots = [value for value in roots if isinstance(value, str) and Path(value).is_absolute()]
    for profile in [cfg, *cfg.get("game_profiles", [])]:
        value = profile.get("mods_source_dir")
        if value and Path(value).expanduser().is_absolute():
            roots.append(str(Path(value).expanduser().absolute()))
    return list(dict.fromkeys(Path(value) for value in roots))


def _register_root(root: Path, cfg: dict) -> None:
    roots = trash_roots(cfg)
    if root not in roots:
        roots.append(root)
    _registry().parent.mkdir(parents=True, exist_ok=True)
    storage.save_json(_registry(), {"version": 1, "roots": [str(path) for path in roots]})


def _entry_path(root: Path, identifier: str) -> Path:
    if str(UUID(identifier)) != identifier:
        raise ValueError(t("trash_invalid_entry"))
    directory = root / TRASH_DIRECTORY
    if directory.is_symlink() or directory.is_junction():
        raise ValueError(t("trash_invalid_entry"))
    entry = directory / identifier
    if entry.is_symlink() or entry.is_junction():
        raise ValueError(t("trash_invalid_entry"))
    return entry


def _original(root: Path, relative: str) -> Path:
    relative = safe_relative_path(relative)
    path = root / relative
    if (relative.parts[0].casefold() == TRASH_DIRECTORY
            or not path.parent.resolve().is_relative_to(root.resolve())):
        raise ValueError(t("trash_invalid_entry"))
    return path


def _stored(entry: Path, relative: str) -> Path:
    relative = safe_relative_path(relative)
    if relative.parts[0] != "payload":
        raise ValueError(t("trash_invalid_entry"))
    path = entry / relative
    if not path.parent.resolve().is_relative_to(entry.resolve()):
        raise ValueError(t("trash_invalid_entry"))
    return path


def _manifest(entry: Path, data: dict) -> None:
    storage.save_json(entry / "entry.json", data)


def _validate(data: dict) -> None:
    if (not isinstance(data, dict) or data.get("version") != 1
            or not isinstance(data.get("name"), str) or not data["name"]
            or not isinstance(data.get("files"), list) or not data["files"]):
        raise ValueError(t("trash_invalid_entry"))
    safe_relative_path(data["name"])
    for member in data["files"]:
        if not isinstance(member, dict) or not all(isinstance(member.get(key), str) for key in ("original", "stored")):
            raise ValueError(t("trash_invalid_entry"))
    for key in ("deleted_at", "expires_at"):
        value = datetime.fromisoformat(data[key])
        if value.tzinfo is None:
            raise ValueError(t("trash_invalid_entry"))


def list_entries(cfg: dict) -> list[TrashEntry]:
    entries = []
    for root in trash_roots(cfg):
        directory = root / TRASH_DIRECTORY
        if not directory.exists():
            continue
        if directory.is_symlink() or directory.is_junction():
            raise ValueError(t("trash_invalid_entry"))
        for path in sorted(directory.iterdir()):
            if not path.is_dir():
                continue
            path = _entry_path(root, path.name)
            data = storage.load_json(path / "entry.json", {})
            _validate(data)
            members = [(_original(root, member["original"]), _stored(path, member["stored"]))
                       for member in data["files"]]
            if data.get("state") == "preparing":
                _recover_preparing(cfg, root, path, data)
                continue
            if data.get("state") == "restored":
                _remove_import_path(path)
                continue
            if data.get("state") == "restoring":
                _rollback_restore(path, data)
            missing = tuple(member["original"] for member in data["files"]
                            if not _exists(_stored(path, member["stored"])))
            if len(missing) == len(data["files"]) and data.get("state") == "trashed":
                _remove_import_path(path)
                continue
            entries.append(TrashEntry(root, path.name, data, missing))
    return sorted(entries, key=lambda entry: entry.data["deleted_at"], reverse=True)


def _capture(cfg: dict, mod: ModItem, now: datetime) -> dict:
    state = storage.load_label_state()
    records = storage.load_mod_records()
    assignments = state.assignments.get(mod.name, [])
    return {
        "version": 1, "name": mod.name, "profile_id": str(cfg.get("active_game_profile_id") or ""),
        "profile_name": (storage.active_game_profile(cfg) or {}).get("name", t("default")),
        "deleted_at": now.isoformat(), "expires_at": (now + timedelta(days=RETENTION_DAYS)).isoformat(),
        "state": "preparing", "record": records.get(mod.name),
        "definitions": {name: {"mode": definition.mode, "terms": list(definition.terms),
                               "exclusions": list(definition.exclusions)}
                        for name, definition in state.definitions.items() if name in assignments},
        "favorite": mod.name in storage.load_favorites(cfg),
        "presets": [name for name, members in storage.load_presets().items() if mod.name in members],
        "registered": mod.name.casefold() in directory_mods(cfg),
        "files": [],
    }


def _remove_metadata(cfg: dict, data: dict) -> None:
    name = data["name"]
    records = storage.load_mod_records()
    records.pop(name, None)
    storage.save_mod_records(records)
    storage.update_favorites(cfg, [name], False)
    presets = storage.load_presets()
    for members in presets.values():
        members[:] = [member for member in members if member != name]
    storage.save_presets(presets)
    unregister_directory_mod(cfg, name)


def _return_payload(root: Path, entry: Path, data: dict) -> None:
    for member in reversed(data["files"]):
        original = _original(root, member["original"])
        stored = _stored(entry, member["stored"])
        if _exists(stored):
            if _exists(original):
                raise FileExistsError(t("trash_recovery_retained", path=str(entry)))
            original.parent.mkdir(parents=True, exist_ok=True)
            stored.rename(original)


def _recover_preparing(cfg: dict, root: Path, path: Path, data: dict) -> None:
    _return_payload(root, path, data)
    entry = TrashEntry(root, path.name, data)
    pinned = _profile_config(cfg, entry)
    with storage_policy(config=pinned):
        _restore_metadata(pinned, data, data["name"])
    _remove_import_path(path)


def _restore_metadata(cfg: dict, data: dict, name: str) -> None:
    if data.get("record") is not None:
        records = storage.load_mod_records()
        records[name] = {**data["record"], "state": "uninstalled"}
        storage.save_mod_records(records)
    state = storage.load_label_state()
    for label, definition in data.get("definitions", {}).items():
        if state.canonical_name(label) not in state.definitions:
            state.definitions[label] = LabelDefinition(definition["mode"], definition["terms"], definition["exclusions"])
    storage.save_label_state(state)
    if data.get("favorite"):
        storage.update_favorites(cfg, [name], True)
    presets = storage.load_presets()
    for preset in data.get("presets", []):
        if preset in presets and name not in presets[preset]:
            presets[preset].append(name)
    storage.save_presets(presets)
    if data.get("registered"):
        register_directory_mod(cfg, name)


def trash_mod(cfg: dict, mod: ModItem, now: datetime | None = None) -> None:
    root = Path(cfg["mods_source_dir"]).expanduser().absolute()
    now = now or utc_now()
    destinations = mod.install_files if str(cfg.get("game_mods_dir") or "").strip() else ()
    if destinations:
        game = Path(cfg["game_mods_dir"]).expanduser().absolute().resolve()
        for member in destinations:
            parent = member.dest.absolute().parent.resolve()
            if (not parent.is_relative_to(game) or parent.is_relative_to(root.resolve())
                    or parent / member.dest.name == root.resolve()):
                raise ValueError(t("trash_destination_invalid"))
    with storage_policy(config=cfg):
        data = _capture(cfg, mod, now)
        paths = list(dict.fromkeys(member.src.absolute() for member in mod.install_files))
        paths.extend(root / "images" / (mod.name + extension) for extension in IMAGE_EXTENSIONS
                     if _exists(root / "images" / (mod.name + extension)))
        for index, path in enumerate(paths):
            relative = path.relative_to(root).as_posix()
            _original(root, relative)
            if not _exists(path):
                raise FileNotFoundError(str(path))
            data["files"].append({"original": relative, "stored": f"payload/{index}"})
        _register_root(root, cfg)
        entry = _entry_path(root, str(uuid4()))
        (entry / "payload").mkdir(parents=True)
        try:
            hide_directory(entry.parent)
            _manifest(entry, data)
        except Exception:
            _remove_import_path(entry)
            raise
        try:
            if any(_exists(member.dest) for member in destinations):
                result = deactivate_mod_result(mod)
                if not result.success:
                    raise OSError(result.message)
            for member in data["files"]:
                original = _original(root, member["original"])
                target = _stored(entry, member["stored"])
                original.rename(target)
            _remove_metadata(cfg, data)
            data["state"] = "trashed"
            _manifest(entry, data)
        except Exception:
            _return_payload(root, entry, data)
            _restore_metadata(cfg, data, mod.name)
            _remove_import_path(entry)
            raise


def trash_mods(cfg: dict, mods: list[ModItem]) -> OperationResult:
    items = []
    for mod in mods:
        with mod_activity("progress_updating", (mod.name,)) as activity:
            try:
                trash_mod(cfg, mod)
                item = OperationItem(mod.name, "trashed", True, t("trash_moved"))
            except (OSError, ValueError) as error:
                item = OperationItem(mod.name, "trashed", False, str(error))
            items.append(item)
            activity.append(item)
    return OperationResult(tuple(items))


def _profile_config(cfg: dict, entry: TrashEntry) -> dict:
    pinned = deepcopy(cfg)
    identifier = entry.data["profile_id"]
    profile = next((value for value in cfg.get("game_profiles", []) if value.get("id") == identifier), None)
    if identifier:
        if profile is None or Path(profile.get("mods_source_dir") or "").expanduser().absolute() != entry.root:
            raise ValueError(t("trash_profile_unavailable"))
        pinned.update(profile)
        pinned["active_game_profile_id"] = identifier
    elif Path(cfg.get("mods_source_dir") or "").expanduser().absolute() != entry.root:
        raise ValueError(t("trash_profile_unavailable"))
    if not entry.root.is_dir():
        raise ValueError(t("trash_profile_unavailable"))
    return pinned


def _restore_targets(entry: TrashEntry, name: str) -> list[tuple[Path, Path]]:
    safe_relative_path(name)
    if Path(name).name != name or name.casefold() in ("images", TRASH_DIRECTORY):
        raise ValueError(t("trash_invalid_entry"))
    targets = []
    for member in entry.data["files"]:
        original = Path(member["original"])
        if name != entry.name:
            if original.parent == Path("images"):
                original = original.with_name(name + original.name[len(entry.name):])
            elif len(entry.data["files"]) > 1 and original.name != entry.name:
                original = original.with_name(Path(name).stem + original.suffix)
            else:
                original = original.with_name(name)
        targets.append((_stored(entry.path, member["stored"]), _original(entry.root, original.as_posix())))
    if len({os.path.normcase(str(target)) for _source, target in targets}) != len(targets):
        raise ValueError(t("trash_invalid_entry"))
    return targets


def restore_conflicts(entry: TrashEntry, name: str | None = None) -> list[Path]:
    return [target for _source, target in _restore_targets(entry, name or entry.name) if _exists(target)]


def _rollback_restore(path: Path, data: dict) -> None:
    for move in reversed(data.get("restore_moves", [])):
        original = _original(path.parent.parent, move["original"])
        stored = _stored(path, move["stored"])
        if not _exists(stored) and _exists(original):
            original.rename(stored)
    data["state"] = "trashed"
    data.pop("restore_moves", None)
    _manifest(path, data)


def restore_entry(cfg: dict, entry: TrashEntry, name: str | None = None) -> None:
    _entry_path(entry.root, entry.identifier)
    _validate(entry.data)
    pinned = _profile_config(cfg, entry)
    name = name or entry.name
    targets = _restore_targets(entry, name)
    if entry.missing or any(not _exists(source) for source, _target in targets):
        raise FileNotFoundError(t("trash_incomplete"))
    if any(_exists(target) for _source, target in targets):
        raise FileExistsError(t("trash_restore_conflict"))
    data = deepcopy(entry.data)
    data["state"] = "restoring"
    data["restore_moves"] = [{"stored": source.relative_to(entry.path).as_posix(),
                              "original": target.relative_to(entry.root).as_posix()} for source, target in targets]
    _manifest(entry.path, data)
    with storage_policy(config=pinned):
        try:
            for source, target in targets:
                target.parent.mkdir(parents=True, exist_ok=True)
                source.rename(target)
            _restore_metadata(pinned, data, name)
        except Exception:
            try:
                _remove_metadata(pinned, {**data, "name": name})
            finally:
                _rollback_restore(entry.path, data)
            raise
    data["state"] = "restored"
    _manifest(entry.path, data)
    _remove_import_path(entry.path)


def delete_entry(entry: TrashEntry) -> None:
    path = _entry_path(entry.root, entry.identifier)
    if path.exists():
        _remove_import_path(path)


def purge_entries(cfg: dict, identifiers: set[str] | None = None, *, expired_only=False,
                  now: datetime | None = None) -> OperationResult:
    now = now or utc_now()
    results = []
    for entry in list_entries(cfg):
        if identifiers is not None and entry.identifier not in identifiers:
            continue
        if expired_only and (entry.data.get("state") != "trashed"
                             or datetime.fromisoformat(entry.data["expires_at"]) > now):
            continue
        try:
            delete_entry(entry)
            results.append(OperationItem(entry.name, "deleted", True, t("trash_deleted")))
        except OSError as error:
            results.append(OperationItem(entry.name, "deleted", False, str(error)))
    return OperationResult(tuple(results))
