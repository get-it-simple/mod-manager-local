from __future__ import annotations

from dataclasses import dataclass, field

from ...i18n import t
from ...labels import unique_names


@dataclass
class FragmentDraft:
    terms: list[str] = field(default_factory=list)
    pending: str = ""
    editing: int | None = None
    edited: str = ""
    exclusions: list[str] = field(default_factory=list)
    pending_excluded: bool = False
    edited_excluded: bool = False

    @property
    def rules(self) -> list[tuple[bool, str]]:
        return [(False, term) for term in self.terms] + [(True, term) for term in self.exclusions]

    def preview_rules(self) -> list[tuple[bool, str]]:
        rules = self.rules
        if self.editing is not None:
            rules[self.editing] = (self.edited_excluded, self.edited)
        if self.pending.strip():
            rules.append((self.pending_excluded, self.pending))
        return [(excluded, text.strip()) for excluded, text in rules]

    def preview_terms(self) -> list[str]:
        return [text for excluded, text in self.preview_rules() if not excluded]

    def preview_exclusions(self) -> list[str]:
        return [text for excluded, text in self.preview_rules() if excluded]

    def committed_terms(self) -> list[str]:
        self.validate_edit()
        return unique_names(self.preview_terms())

    def committed_exclusions(self) -> list[str]:
        self.validate_edit()
        return unique_names(self.preview_exclusions())

    def set_rules(self, rules: list[tuple[bool, str]]) -> None:
        self.terms = unique_names(text for excluded, text in rules if not excluded)
        self.exclusions = unique_names(text for excluded, text in rules if excluded)

    def rule_excluded(self, row: int) -> bool:
        return self.edited_excluded if self.editing == row else self.rules[row][0]

    def rule_number(self, row: int) -> int:
        return row + 1 if row < len(self.terms) else row - len(self.terms) + 1

    def validate_edit(self) -> None:
        if self.editing is not None and not self.edited.strip():
            raise ValueError(t('enter_a_nonempty_fragment_or_delete_its_row'))

    @property
    def unfinished(self) -> bool:
        return self.editing is not None or bool(self.pending)


