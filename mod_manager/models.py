from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class ModFile:
    src: Path
    dest: Path
    is_dir: bool

@dataclass
class ModItem:
    name: str
    src: Path
    dest: Path
    is_dir: bool
    installed: bool
    files: tuple[ModFile, ...] = ()
    copy_install: bool = False

    @property
    def install_files(self) -> tuple[ModFile, ...]:
        """Every file the mod installs; a plain mod installs itself alone."""
        return self.files or (ModFile(self.src, self.dest, self.is_dir),)


@dataclass(frozen=True)
class OperationFailure:
    src: Path
    dest: Path
    message: str


@dataclass(frozen=True)
class OperationItem:
    name: str
    action: str
    success: bool
    message: str
    failures: tuple[OperationFailure, ...] = ()


@dataclass(frozen=True)
class OperationResult:
    items: tuple[OperationItem, ...] = ()

    @property
    def errors(self) -> int:
        return sum(not item.success for item in self.items)

    def summary(self) -> str:
        parts = []
        for action in ("installed", "uninstalled"):
            selected = [item for item in self.items if item.action == action]
            if selected:
                success = sum(item.success for item in selected)
                parts.append(f"{action.capitalize()} {success}/{len(selected)}. Errors: {len(selected) - success}.")
        return " ".join(parts) or "Nothing to change."
