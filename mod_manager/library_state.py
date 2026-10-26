from __future__ import annotations

from pathlib import Path

from .i18n import t


def folder_issues(cfg: dict) -> tuple[str, ...]:
    issues = []
    paths = []
    for key in ("mods_source_dir", "game_mods_dir"):
        value = str(cfg.get(key) or "").strip()
        if not value:
            issues.append(t("missing_folder", name=key))
            continue
        try:
            path = Path(value).expanduser().resolve()
            paths.append(path)
            if not path.is_dir():
                issues.append(t("unavailable_folder", path=path))
        except (OSError, ValueError) as error:
            issues.append(str(error))
    if len(paths) == 2 and (paths[0] == paths[1] or paths[0] in paths[1].parents or paths[1] in paths[0].parents):
        issues.append(t("overlapping_folders"))
    return tuple(issues)
