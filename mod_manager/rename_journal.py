from __future__ import annotations

import os
from pathlib import Path
import tempfile
from uuid import UUID

from . import storage
from .i18n import t


def restore_metadata(snapshots):
    for snapshot in snapshots:
        path = Path(snapshot["path"])
        before = snapshot["before"]
        if before is None:
            path.unlink(missing_ok=True)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(bytes.fromhex(before))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)


def validate_journal(cfg, journal, data):
    identifier = journal.stem
    if str(UUID(identifier)) != identifier or journal.is_symlink() or data.get("version") != 1:
        raise ValueError(t("rename_invalid"))
    if journal.parent.is_symlink() or journal.parent.is_junction():
        raise ValueError(t("rename_invalid"))
    profiles = [cfg, *cfg.get("game_profiles", [])]
    roots = {Path(profile["mods_source_dir"]).expanduser().resolve() for profile in profiles if profile.get("mods_source_dir")}
    games = {Path(profile["game_mods_dir"]).expanduser().resolve() for profile in profiles if profile.get("game_mods_dir")}
    root = Path(data["root"]).resolve()
    if root not in roots or data.get("state") not in ("preparing", "committed"):
        raise ValueError(t("rename_invalid"))
    for index, value in enumerate(data["sources"]):
        old, new, stage = (Path(value[key]) for key in ("old", "new", "stage"))
        if (not old.is_absolute() or not old.parent.resolve().is_relative_to(root) or new.parent != old.parent
                or stage != old.with_name(f".mod-rename-{identifier}-{index}")):
            raise ValueError(t("rename_invalid"))
    for index, value in enumerate(data["destinations"]):
        old, new, backup = (Path(value[key]) for key in ("old", "new", "backup"))
        if (old.parent.resolve() not in games or new.parent != old.parent
                or backup != old.with_name(f".mod-rename-{identifier}-backup-{index}")
                or not Path(value["source"]).parent.resolve().is_relative_to(root)):
            raise ValueError(t("rename_invalid"))
    allowed = {storage.LABELS_PATH.absolute(), storage.PRESETS_PATH.absolute()}
    for profile in cfg.get("game_profiles", []):
        for suffix in (storage.LABELS_PATH.name, storage.PRESETS_PATH.name, "imports.json"):
            allowed.add((storage.PROFILE_DATA_DIR / f"{profile['id']}-{suffix}").absolute())
    allowed.add((storage.PROFILE_DATA_DIR / "default-imports.json").absolute())
    for snapshot in data["metadata"]:
        if Path(snapshot["path"]).absolute() not in allowed:
            raise ValueError(t("rename_invalid"))
        if snapshot["before"] is not None:
            bytes.fromhex(snapshot["before"])
