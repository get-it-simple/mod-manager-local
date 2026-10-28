from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


def filter_values(values: str | Iterable[str]) -> tuple[str, ...]:
    values = (values,) if isinstance(values, str) else values
    unique = {}
    for value in values:
        value = value.strip()
        if value:
            unique.setdefault(value.casefold(), value)
    return tuple(unique.values())


@dataclass
class LibraryFilters:
    chips: list[tuple[str, str]] = field(default_factory=list)
    mode: str = "all"

    @property
    def labels(self) -> tuple[str, ...]:
        return tuple(value for kind, value in self.chips if kind == "label")

    @property
    def queries(self) -> tuple[str, ...]:
        return tuple(value for kind, value in self.chips if kind == "search")

    @property
    def active(self) -> bool:
        return bool(self.chips) or self.mode != "all"

    @property
    def state(self) -> str:
        return "all" if self.mode == "favorite" else self.mode

    def add(self, kind: str, value: str) -> bool:
        value = value.strip()
        if not value or any(k == kind and v.casefold() == value.casefold() for k, v in self.chips):
            return False
        self.chips.append((kind, value))
        return True

    def remove(self, kind: str, value: str) -> None:
        self.chips = [(k, v) for k, v in self.chips if k != kind or v.casefold() != value.casefold()]

    def toggle_label(self, name: str) -> None:
        if not self.add("label", name):
            self.remove("label", name)

    def reconcile_labels(self, names: Iterable[str], renames: dict[str, str] | None = None) -> None:
        canonical = {name.casefold(): name for name in names}
        renamed = {old.casefold(): new for old, new in (renames or {}).items()}
        chips = self.chips
        self.chips = []
        for kind, value in chips:
            if kind == "label":
                value = canonical.get(renamed.get(value.casefold(), value).casefold(), "")
            self.add(kind, value)

    def clear(self) -> None:
        self.chips.clear()
        self.mode = "all"
