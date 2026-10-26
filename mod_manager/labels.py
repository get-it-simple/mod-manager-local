from __future__ import annotations

from .i18n import t

from dataclasses import dataclass, field
from copy import deepcopy
from typing import Iterable


MANUAL = "manual"
AUTOMATIC = "automatic"


def matching_fragment_ids(mod_name: str, terms: Iterable[str]) -> tuple[int, ...]:
    folded = mod_name.casefold()
    return tuple(index for index, term in enumerate(terms, 1) if term.strip() and term.strip().casefold() in folded)


def unique_names(values: Iterable[str]) -> list[str]:
    result = {}
    for value in values:
        value = value.strip()
        if value:
            result.setdefault(value.casefold(), value)
    return list(result.values())


@dataclass
class LabelDefinition:
    mode: str = MANUAL
    terms: list[str] = field(default_factory=list)


@dataclass
class LabelState:
    definitions: dict[str, LabelDefinition] = field(default_factory=dict)
    assignments: dict[str, list[str]] = field(default_factory=dict)

    def canonical_name(self, name: str) -> str:
        return next((value for value in self.definitions if value.casefold() == name.strip().casefold()), name.strip())

    def members(self, mod_name: str) -> tuple[str, ...]:
        manual = {name.casefold() for name in self.assignments.get(mod_name, ())}
        return tuple(sorted((
            name for name, definition in self.definitions.items()
            if (definition.mode == MANUAL and name.casefold() in manual)
            or (definition.mode == AUTOMATIC and matching_fragment_ids(mod_name, definition.terms))
        ), key=str.casefold))

    def rename(self, old: str, new: str) -> None:
        new = new.strip()
        if not new or any(name != old and name.casefold() == new.casefold() for name in self.definitions):
            raise ValueError(t('enter_a_unique_nonempty_label_name'))
        self.definitions = {new if name == old else name: value for name, value in self.definitions.items()}
        for mod, names in self.assignments.items():
            self.assignments[mod] = [new if name == old else name for name in names]

    def delete(self, name: str) -> None:
        self.definitions.pop(name, None)
        self.assignments = {mod: [value for value in names if value != name] for mod, names in self.assignments.items() if any(value != name for value in names)}

    def assign(self, name: str, mods: Iterable[str], assigned: bool = True) -> list[str]:
        name = self.canonical_name(name)
        if not name:
            raise ValueError(t('enter_a_label_name'))
        definition = self.definitions.setdefault(name, LabelDefinition())
        if definition.mode == AUTOMATIC:
            raise ValueError(t('automatic_labels_are_managed_by_their_name_fragments_open_labels_to_edit'))
        changed = []
        for mod in mods:
            names = self.assignments.setdefault(mod, [])
            if assigned and name not in names:
                names.append(name)
                changed.append(mod)
            elif not assigned and name in names:
                names.remove(name)
                if not names:
                    self.assignments.pop(mod)
                changed.append(mod)
        return changed

    def validate(self) -> None:
        folded = [name.strip().casefold() for name in self.definitions]
        if any(not name for name in folded) or len(set(folded)) != len(folded):
            raise ValueError(t('enter_unique_nonempty_label_names'))
        for name, definition in self.definitions.items():
            if definition.mode not in (MANUAL, AUTOMATIC):
                raise ValueError(t('unknown_mode_for_label_value0', value0=f'{name}'))
            definition.terms = unique_names(definition.terms)
            if definition.mode == AUTOMATIC and not definition.terms:
                raise ValueError(t('enter_at_least_one_name_fragment_for_automatic_label_value0', value0=f'{name}'))


def _merge_label_value(before, desired, actual):
    if desired == before:
        return deepcopy(actual)
    if actual != before and actual != desired:
        raise ValueError(t("label_save_conflict"))
    return deepcopy(desired)


def merge_label_states(saved: LabelState, edited: LabelState, current: LabelState,
                       renames: dict[str, str]) -> LabelState:
    baseline, latest = deepcopy(saved), deepcopy(current)
    moving = {old: new for old, new in renames.items() if new and new != old}
    for old, new in moving.items():
        if old not in latest.definitions or (new in latest.definitions and new not in moving):
            raise ValueError(t("label_save_conflict"))
    for state in (baseline, latest):
        state.definitions = {moving.get(name, name): value for name, value in state.definitions.items()}
        state.assignments = {mod: [moving.get(name, name) for name in names] for mod, names in state.assignments.items()}

    result = LabelState()
    for name in sorted(baseline.definitions.keys() | edited.definitions.keys() | latest.definitions.keys(), key=str.casefold):
        before, desired, actual = (state.definitions.get(name) for state in (baseline, edited, latest))
        if before is not None and desired is not None and actual is not None:
            result.definitions[name] = LabelDefinition(_merge_label_value(before.mode, desired.mode, actual.mode),
                                                       _merge_label_value(before.terms, desired.terms, actual.terms))
        else:
            definition = _merge_label_value(before, desired, actual)
            if definition is not None:
                result.definitions[name] = definition
    result.validate()
    for mod in baseline.assignments.keys() | edited.assignments.keys() | latest.assignments.keys():
        before, desired, actual = (set(state.assignments.get(mod, ())) for state in (baseline, edited, latest))
        names = (actual - (before - desired)) | (desired - before)
        ordered = unique_names([*latest.assignments.get(mod, ()), *edited.assignments.get(mod, ())])
        values = [name for name in ordered if name in names and name in result.definitions]
        if values:
            result.assignments[mod] = values
    return result


class ResolvedLabels(dict[str, str]):
    def __init__(self, state: LabelState, names: Iterable[str]):
        self.state = state
        self.memberships = {name: state.members(name) for name in names}
        super().__init__((name, ", ".join(values)) for name, values in self.memberships.items() if values)


def label_names(labels: dict, mod_name: str) -> tuple[str, ...]:
    if isinstance(labels, ResolvedLabels):
        return labels.memberships.get(mod_name, ())
    value = labels.get(mod_name, "")
    return (value,) if value else ()


def state_from_records(records: dict, definitions: dict[str, LabelDefinition], legacy: dict | None = None) -> LabelState:
    state = LabelState(dict(definitions))
    for mod_name, record in records.items():
        values = record.get("labels")
        if values is None:
            values = [record.get("label", "")]
        names = unique_names(values)
        if names:
            state.assignments[mod_name] = names
    for mod_name, name in (legacy or {}).items():
        if name and mod_name not in records:
            state.assignments.setdefault(mod_name, [name])
    for names in state.assignments.values():
        for name in names:
            canonical = state.canonical_name(name)
            state.definitions.setdefault(canonical, LabelDefinition())
    state.assignments = {mod: [state.canonical_name(name) for name in names] for mod, names in state.assignments.items()}
    return state
