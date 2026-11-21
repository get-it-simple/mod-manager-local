from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
import os
from pathlib import Path
from uuid import uuid4

from . import storage
from .i18n import t
from .import_registry import _registry_path, _source_key
from .links import mklink, unlink_path
from .models import ModItem
from .mod_modes import RESERVED_MOD_DIRECTORIES
from .mods import IMAGE_EXTENSIONS, _mod_file, discover_mods
from .platform_utils import is_junction
from .storage_policy import storage_policy


@dataclass(frozen=True)
class RenameResult:
    old_name: str
    new_name: str
    profiles: tuple[str, ...]
    renamed: tuple[tuple[str, str, str], ...] = ()

    def summary(self) -> str:
        return t("rename_complete", old=self.old_name, new=self.new_name)


def validate_name(mod: ModItem, name: str) -> str:
    name = name.strip()
    devices = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    forbidden = {chr(value) for value in range(32)} | set('<>:"/|?*') | {chr(92)}
    if (not name or name in (".", "..") or name[-1] in ". " or any(char in forbidden for char in name)
            or name.split(".")[0].upper() in devices or name.casefold() in RESERVED_MOD_DIRECTORIES
            or name.startswith(".mod-import-") or name.startswith(".mod-rename-")
            or not mod.is_dir and Path(name).suffix != mod.src.suffix):
        raise ValueError(t("rename_invalid"))
    return name


def _key(path: Path) -> str:
    return os.path.normcase(str(path.absolute()))


def _exists(path: Path) -> bool:
    return os.path.lexists(path) or is_junction(path)


def _identity(path: Path):
    stat = path.lstat()
    return [stat.st_dev, stat.st_ino]


def _owned(path: Path, identity) -> bool:
    return _exists(path) and _identity(path) == identity


def _profiles(cfg: dict, root: Path):
    profiles = cfg.get("game_profiles", [])
    if not profiles:
        yield deepcopy(cfg)
    for profile in profiles:
        if profile.get("mods_source_dir") and Path(profile["mods_source_dir"]).expanduser().resolve() == root:
            pinned = deepcopy(cfg)
            storage.set_active_game_profile(pinned, profile["id"])
            yield pinned


def _renamed_source(path: Path, moves):
    for old, new in moves:
        if _key(path) == _key(old):
            return new
        if old.is_dir() and path.is_relative_to(old):
            return new / path.relative_to(old)
    return path


def _rename_records(data: dict, names: dict[str, str]):
    result = deepcopy(data)
    for old, new in names.items():
        if old != new and old in result:
            if new in result:
                raise FileExistsError(t("rename_conflict", path=new))
            result[new] = result.pop(old)
    return result


def _rename_presets(data: dict, names: dict[str, str]):
    result = deepcopy(data)
    for value in result.values():
        members = value.get("mods", []) if isinstance(value, dict) else value
        renamed = list(dict.fromkeys(names.get(name, name) for name in members))
        if isinstance(value, dict):
            value["mods"] = renamed
        else:
            members[:] = renamed
    return result


def _metadata_changes(affected):
    changes = {}
    favorites = storage.load_json(storage.LABELS_PATH, {})
    for cfg, pairs in affected:
        names = {old.name: new.name for old, new in pairs if old.name != new.name}
        with storage_policy(config=cfg):
            for base, transform in ((storage.LABELS_PATH, _rename_records), (storage.PRESETS_PATH, _rename_presets)):
                path, profile, _raw = storage._active_profile_context(base)
                data = changes.get(path, storage._load_profile_json(base, {}))
                changes[path] = transform(data, names)
                if storage._is_first_profile(profile, cfg) and base.exists():
                    legacy = changes.get(base, storage.load_json(base, {}))
                    changes[base] = transform(legacy, names)
            scope = storage._favorite_scope(cfg)
            favorite_map = favorites.get(storage.FAVORITES_KEY, {})
            if scope in favorite_map:
                favorite_map[scope] = list(dict.fromkeys(names.get(name, name) for name in favorite_map[scope]))
            registry = _registry_path(cfg)
            if registry.exists():
                data = changes.get(registry, storage.load_json(registry, {}))
                source = data.get("sources", {}).get(_source_key(cfg), [])
                folded = {old.casefold(): new for old, new in names.items()}
                data.get("sources", {})[_source_key(cfg)] = [folded.get(name.casefold(), name) for name in source]
                changes[registry] = data
    if storage.FAVORITES_KEY in favorites:
        data = changes.get(storage.LABELS_PATH, favorites)
        data[storage.FAVORITES_KEY] = favorites[storage.FAVORITES_KEY]
        changes[storage.LABELS_PATH] = data
    return changes


def _journal_directory():
    return storage.PROFILE_DATA_DIR / "renames"


def pending_renames() -> bool:
    directory = _journal_directory()
    return directory.exists() and any(directory.glob("*.json"))


def _write_journal(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    storage.save_json(path, data)


def _assert_destination(path, source, cfg, records, name):
    if not _exists(path):
        return
    if cfg.get("install_mode") == "copy":
        if records.get(name, {}).get("state") != "installed":
            raise FileExistsError(t("rename_conflict", path=str(path)))
    elif not (path.is_symlink() or is_junction(path)) or not path.samefile(source):
        raise FileExistsError(t("rename_conflict", path=str(path)))


def _prepare(cfg, mod, name, identifier):
    root = Path(cfg["mods_source_dir"]).expanduser().resolve()
    moves = []
    for member in mod.install_files:
        old = member.src.absolute()
        if not old.resolve().is_relative_to(root) or old.is_symlink() or is_junction(old):
            raise ValueError(t("rename_invalid"))
        new = old.with_name(name if len(mod.install_files) == 1 else Path(name).stem + old.suffix)
        if _exists(new) and _key(old) != _key(new):
            raise FileExistsError(t("rename_conflict", path=str(new)))
        moves.append((old, new))
    affected = []
    destinations = {}
    for pinned in _profiles(cfg, root):
        with storage_policy(config=pinned):
            records = storage.load_mod_records()
            pairs = []
            for old_mod in discover_mods(pinned):
                members = []
                for member in old_mod.install_files:
                    source = _renamed_source(member.src.absolute(), moves)
                    members.append(_mod_file(source, member.is_dir, Path(pinned.get("game_mods_dir") or ""), pinned.get("link_prefix") or ""))
                if all(str(old.src.absolute()) == str(new.src) for old, new in zip(old_mod.install_files, members)):
                    continue
                new_mod = replace(old_mod, name=members[0].src.name, src=members[0].src, dest=members[0].dest,
                                  files=tuple(members) if old_mod.files else ())
                pairs.append((old_mod, new_mod))
                for old, new in zip(old_mod.install_files, members):
                    if not pinned.get("game_mods_dir") or not _exists(old.dest):
                        continue
                    game = Path(pinned["game_mods_dir"]).expanduser().resolve()
                    if game == root or game.is_relative_to(root) or root.is_relative_to(game):
                        raise ValueError(t("rename_invalid"))
                    _assert_destination(old.dest, old.src, pinned, records, old_mod.name)
                    if _exists(new.dest) and _key(old.dest) != _key(new.dest):
                        raise FileExistsError(t("rename_conflict", path=str(new.dest)))
                    key = _key(old.dest)
                    value = {"old": str(old.dest.absolute()), "new": str(new.dest.absolute()), "source": str(new.src),
                             "copy": old_mod.copy_install, "identity": _identity(old.dest)}
                    if key in destinations and destinations[key] != value:
                        raise FileExistsError(t("rename_conflict", path=str(old.dest)))
                    destinations[key] = value
            affected.append((pinned, pairs))
    targets = [_key(Path(value["new"])) for value in destinations.values()]
    if len(targets) != len(set(targets)):
        raise ValueError(t("rename_invalid"))
    changes = _metadata_changes(affected)
    artwork = {}
    for _pinned, pairs in affected:
        for old_mod, new_mod in pairs:
            for extension in IMAGE_EXTENSIONS:
                old = root / "images" / (old_mod.name + extension)
                new = old.with_name(new_mod.name + extension)
                if old_mod.name == new_mod.name or not _exists(old):
                    continue
                if old.is_symlink() or not old.resolve().is_relative_to(root):
                    raise ValueError(t("rename_invalid"))
                if _exists(new) and _key(old) != _key(new):
                    raise FileExistsError(t("rename_conflict", path=str(new)))
                if _key(old) in artwork and artwork[_key(old)][1] != new:
                    raise ValueError(t("rename_invalid"))
                artwork[_key(old)] = (old, new)
    moves.extend(artwork.values())
    sources = [{"old": str(old), "new": str(new), "stage": str(old.with_name(f".mod-rename-{identifier}-{index}")),
                "identity": _identity(old)} for index, (old, new) in enumerate(moves)]
    for index, destination in enumerate(destinations.values()):
        destination["backup"] = str(Path(destination["old"]).with_name(f".mod-rename-{identifier}-backup-{index}"))
    data = {"version": 1, "state": "preparing", "root": str(root), "sources": sources,
            "destinations": list(destinations.values()),
            "metadata": [{"path": str(path.absolute()), "before": path.read_bytes().hex() if path.exists() else None,
                          "after": value} for path, value in changes.items()]}
    renamed = tuple((str(pinned.get("active_game_profile_id") or ""), old.name, new.name)
                    for pinned, pairs in affected for old, new in pairs)
    return data, renamed


def _restore_metadata(data):
    from .rename_journal import restore_metadata
    restore_metadata(data["metadata"])


def _cleanup(data):
    for value in data["destinations"]:
        backup = Path(value["backup"])
        if _exists(backup):
            if value["copy"] or not _owned(backup, value["identity"]):
                raise FileExistsError(str(backup))
            ok, message = unlink_path(backup)
            if not ok:
                raise OSError(message)


def _rollback(data):
    for value in reversed(data["destinations"]):
        old, new, backup = (Path(value[key]) for key in ("old", "new", "backup"))
        if value["copy"]:
            owner = next((path for path in (backup, new, old) if _owned(path, value["identity"])), None)
            if owner is None:
                raise FileNotFoundError(str(backup))
            if str(owner) != str(old):
                if _exists(old) and _key(owner) != _key(old):
                    raise FileExistsError(str(old))
                if _key(owner) == _key(old):
                    owner.rename(backup)
                    owner = backup
                owner.rename(old)
        elif _exists(backup):
            if not _owned(backup, value["identity"]):
                raise FileExistsError(str(backup))
            if _exists(new):
                if not (new.is_symlink() or is_junction(new)) or os.path.normcase(os.path.realpath(new)) != _key(Path(value["source"]).resolve()):
                    raise FileExistsError(str(new))
                ok, message = unlink_path(new)
                if not ok:
                    raise OSError(message)
            if _exists(old):
                raise FileExistsError(str(old))
            backup.rename(old)
    for value in reversed(data["sources"]):
        old, new, stage = (Path(value[key]) for key in ("old", "new", "stage"))
        owner = next((path for path in (stage, new, old) if _owned(path, value["identity"])), None)
        if owner is None:
            raise FileNotFoundError(str(old))
        if str(owner) != str(old):
            if _exists(old) and _key(owner) != _key(old):
                raise FileExistsError(str(old))
            if _key(owner) == _key(old):
                owner.rename(stage)
                owner = stage
            owner.rename(old)
    _restore_metadata(data)


def rename_mod(cfg: dict, mod: ModItem, new_name: str) -> RenameResult:
    name = validate_name(mod, new_name)
    recover_renames(cfg)
    if name == mod.name:
        return RenameResult(mod.name, name, ())
    identifier = str(uuid4())
    with storage_policy(config=cfg):
        data, renamed = _prepare(cfg, mod, name, identifier)
        journal = _journal_directory() / f"{identifier}.json"
        _write_journal(journal, data)
        try:
            for value in data["destinations"]:
                Path(value["old"]).rename(value["backup"])
            for value in data["sources"]:
                Path(value["old"]).rename(value["stage"])
            for value in data["sources"]:
                Path(value["stage"]).rename(value["new"])
            for value in data["destinations"]:
                new = Path(value["new"])
                if _exists(new):
                    raise FileExistsError(t("rename_conflict", path=str(new)))
                if value["copy"]:
                    Path(value["backup"]).rename(new)
                else:
                    ok, message = mklink(Path(value["source"]), new)
                    if not ok:
                        raise OSError(message)
            for value in data["metadata"]:
                path = Path(value["path"])
                path.parent.mkdir(parents=True, exist_ok=True)
                storage.save_json(path, value["after"])
            data["state"] = "committed"
            _write_journal(journal, data)
        except Exception as error:
            try:
                _rollback(data)
                journal.unlink()
            except (OSError, ValueError) as recovery:
                raise OSError(t("rename_recovery", path=str(journal), error=str(recovery))) from error
            raise
        _cleanup(data)
        journal.unlink()
    return RenameResult(mod.name, name, tuple(dict.fromkeys(profile for profile, _old, _new in renamed)), renamed)


def recover_renames(cfg: dict) -> None:
    from .rename_journal import validate_journal
    directory = _journal_directory()
    if not directory.exists():
        return
    for journal in sorted(directory.glob("*.json")):
        with storage_policy(config=cfg):
            data = storage.load_json(journal, {})
            validate_journal(cfg, journal, data)
            try:
                if data["state"] == "committed":
                    _cleanup(data)
                else:
                    _rollback(data)
                journal.unlink()
            except (OSError, ValueError) as error:
                raise OSError(t("rename_recovery", path=str(journal), error=str(error))) from error
