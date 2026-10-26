from __future__ import annotations

from pathlib import Path

from .imports import PlannedMod, create_plans


def preview_plans(archives) -> list[PlannedMod]:
    return create_plans(archives, lambda _name: "keep_both")


def destination_rows(root: str, plans: list[PlannedMod]) -> list[tuple[str, ...]]:
    rows = []
    for plan in plans:
        for _source, relative in plan.files:
            parts = (plan.name, *relative.parts) if plan.is_directory else relative.parts
            rows.append((str(Path(root)), *parts))
        for directory in plan.directories:
            rows.append((str(Path(root)), plan.name, *directory.parts))
    return rows
