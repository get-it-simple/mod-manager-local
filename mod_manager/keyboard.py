from __future__ import annotations

from dataclasses import dataclass

from .i18n import t


@dataclass(frozen=True)
class CommandSpec:
    id: str
    label: str
    default: str = ""
    context: str = "window"
    aliases: tuple[str, ...] = ()


COMMANDS = (
    CommandSpec("search", "search_command", "ctrl+f", "library"),
    CommandSpec("refresh", "refresh_command", "f5"),
    CommandSpec("save", "save_command", "ctrl+s", "editor"),
    CommandSpec("help", "help_command", "f1"),
    CommandSpec("back", "back_command", "backspace", aliases=("back",)),
    CommandSpec("forward", "forward_command", "alt+right", aliases=("forward",)),
    CommandSpec("zoom_in", "zoom_in_command", "ctrl+plus", "library", ("ctrl+equal",)),
    CommandSpec("zoom_out", "zoom_out_command", "ctrl+minus", "library"),
    CommandSpec("paste", "paste_command", "ctrl+v", "library"),
    CommandSpec("install", "install_command", "", "library"),
    CommandSpec("uninstall", "uninstall_command", "", "library"),
    CommandSpec("import_files", "import_files", "", "library"),
    CommandSpec("import_folder", "import_folder", "", "library"),
    CommandSpec("details", "details_command", "", "library"),
    CommandSpec("view", "view_command", "", "library"),
)
MODIFIERS = ("ctrl", "alt", "shift", "win")
KEYS = tuple("abcdefghijklmnopqrstuvwxyz0123456789") + tuple(f"f{i}" for i in range(1, 25)) + (
    "plus", "minus", "equal", "back", "forward", "space", "enter", "tab", "escape", "backspace", "delete", "insert",
    "home", "end", "pageup", "pagedown", "left", "right", "up", "down",
)


def normalize_combo(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Shortcut must be text")
    parts = [part.strip().lower() for part in value.split("+") if part.strip()]
    if not parts:
        return ""
    keys = [part for part in parts if part not in MODIFIERS]
    if len(keys) != 1 or keys[0] not in KEYS or len(parts) != len(set(parts)):
        raise ValueError(value)
    return "+".join([modifier for modifier in MODIFIERS if modifier in parts] + keys)


def effective_combos(command: CommandSpec, combo: str) -> tuple[str, ...]:
    return (combo, *command.aliases) if combo == command.default else (combo,)


def default_bindings() -> dict:
    return {command.id: {"combo": command.default, "enabled": True} for command in COMMANDS}


def validate_bindings(value: dict) -> dict:
    if not isinstance(value, dict):
        raise ValueError(t("shortcuts_help"))
    result = default_bindings()
    used = []
    for command in COMMANDS:
        binding = value.get(command.id, result[command.id])
        try:
            if not isinstance(binding, dict) or not isinstance(binding.get("enabled", True), bool):
                raise ValueError(command.id)
            combo = normalize_combo(binding.get("combo", ""))
        except ValueError as error:
            raise ValueError(t("invalid_shortcut", action=t(command.label), combo=str(binding))) from error
        result[command.id] = {"combo": combo, "enabled": binding.get("enabled", True)}
        if not combo or not result[command.id]["enabled"]:
            continue
        for other, other_combo in used:
            overlap = command.context == other.context or "window" in (command.context, other.context)
            if set(effective_combos(command, combo)) & set(effective_combos(other, other_combo)) and overlap:
                raise ValueError(t("shortcut_conflict", combo=combo, first=t(other.label), second=t(command.label)))
        used.append((command, combo))
    return result
