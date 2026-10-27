from __future__ import annotations

from ...i18n import t

from copy import deepcopy

from PySide6 import QtCore, QtGui

from ...labels import AUTOMATIC, MANUAL, LabelDefinition, LabelState, merge_label_states
from ...storage import load_label_state, save_label_state
from ..dialogs import prompts
from ..widgets.label_editor import LabelEditor
from ..widgets.label_fragments import FragmentDraft
from ..widgets.label_lists import update_label_item
from ..widgets.workspace import WorkspacePage
from .widget_registry import ACTIONS
from ..theme import tokens


class LabelsController(QtCore.QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.page = WorkspacePage(t('labels'), t('labels_autosave_help'))
        self.editor = LabelEditor()
        self.page.body.addWidget(self.editor)
        self.drafts: dict[str, LabelState] = {}
        self.saved: dict[str, LabelState] = {}
        self.renames: dict[str, dict[str, str]] = {}
        self.fragments: dict[str, dict[str, FragmentDraft]] = {}
        self.name_inputs: dict[str, dict[str, str]] = {}
        self.profile_id = ""
        self.selected = ""
        self._loading = False
        self._rebuilding = False
        self._save_failed = False
        self.save_timer = QtCore.QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(tokens.LABEL_SAVE_DELAY_MS)
        self.save_timer.timeout.connect(self.save)
        editor = self.editor
        editor.list_view.selectionModel().currentChanged.connect(self._select)
        editor.name_edit.textEdited.connect(self._rename)
        editor.mode_box.currentIndexChanged.connect(self._edit)
        editor.terms_edit.changed.connect(self._edit)
        editor.terms_edit.validationFailed.connect(editor.status.setText)
        editor.manual_model.checkedChanged.connect(self._check)
        editor.toolbar.connect({"add": self.add, "delete": self.delete})
        editor.retry.clicked.connect(self.save)
        editor.reload.clicked.connect(self.reload_saved)
        window.registry.extend(ACTIONS, editor.toolbar.buttons.values())

    @property
    def state(self) -> LabelState:
        return self.drafts[self.profile_id]

    def activate(self) -> bool:
        self.save_timer.stop()
        self.profile_id = str(self.window.cfg.get("active_game_profile_id") or "")
        try:
            current = load_label_state()
        except (OSError, ValueError) as error:
            prompts.show_error(self.window, t('labels'), str(error))
            return False
        unfinished = any(draft.unfinished for draft in self.fragments.get(self.profile_id, {}).values())
        unfinished = unfinished or bool(self.name_inputs.get(self.profile_id))
        if self.profile_id not in self.drafts or (self.drafts[self.profile_id] == self.saved.get(self.profile_id) and not unfinished):
            self.drafts[self.profile_id] = deepcopy(current)
            self.saved[self.profile_id] = deepcopy(current)
            self.renames[self.profile_id] = {name: name for name in current.definitions}
            self.fragments[self.profile_id] = {}
            self.name_inputs[self.profile_id] = {}
        self._rebuild(self.selected)
        return True

    def _rebuild(self, selected: str = "") -> None:
        self._rebuilding = True
        self._loading = True
        self.editor.list_model.clear()
        names = sorted(self.state.definitions, key=str.casefold)
        counts = self._counts()
        for name in names:
            definition = self.state.definitions[name]
            count = counts[name]
            item = QtGui.QStandardItem()
            item.setEditable(False)
            update_label_item(item, name, definition.mode, count)
            self.editor.list_model.appendRow(item)
        self._loading = False
        if names:
            row = names.index(selected) if selected in names else 0
            index = self.editor.list_model.index(row, 0)
            self.editor.list_view.setCurrentIndex(index)
        else:
            self.selected = ""
            self._loading = True
            self.editor.name_edit.clear()
            self.editor.terms_edit.bind(FragmentDraft())
            self.editor.manual_model.set_choices([], set())
            self.editor.details.setEnabled(False)
            self.editor.matches_model.set_matches([], [])
            self.editor.matches_heading.setText(t('matching_mods_0'))
            self._loading = False
        self.editor.toolbar.set_enabled("delete", bool(names))
        self._rebuilding = False
        self._update_status()

    def _counts(self) -> dict[str, int]:
        counts = dict.fromkeys(self.state.definitions, 0)
        for mod in self.window.current_mod_names:
            for name in self.state.members(mod):
                counts[name] += 1
        return counts

    def _refresh_items(self) -> None:
        if self.selected not in self.state.definitions:
            self._rebuild()
            return
        model = self.editor.list_model
        counts = self._counts()
        with QtCore.QSignalBlocker(self.editor.list_view.selectionModel()):
            for row in reversed(range(model.rowCount())):
                if model.item(row).data(QtCore.Qt.UserRole) not in self.state.definitions:
                    model.removeRow(row)
            items = {model.item(row).data(QtCore.Qt.UserRole): model.item(row) for row in range(model.rowCount())}
            for name, definition in self.state.definitions.items():
                item = items.get(name)
                if item is None:
                    item = QtGui.QStandardItem()
                    item.setEditable(False)
                    model.appendRow(item)
                update_label_item(item, name, definition.mode, counts[name])
            model.sort(0)

    def _select(self, index, _previous) -> None:
        if self._loading or not index.isValid():
            return
        selected = index.data(QtCore.Qt.UserRole)
        if not self._rebuilding and self.selected and self.selected in self.state.definitions:
            self.save()
        if selected not in self.state.definitions:
            self._rebuild()
            return
        self.selected = selected
        definition = self.state.definitions[self.selected]
        self._loading = True
        editor = self.editor
        editor.details.setEnabled(True)
        editor.name_edit.setText(self.name_inputs[self.profile_id].get(self.selected, self.selected))
        editor.mode_box.setCurrentIndex(1 if definition.mode == AUTOMATIC else 0)
        draft = self.fragments[self.profile_id].setdefault(
            self.selected, FragmentDraft(list(definition.terms), exclusions=list(definition.exclusions)))
        editor.terms_edit.bind(draft)
        editor.manual_model.set_choices(
            self.window.current_mod_names,
            {mod for mod, labels in self.state.assignments.items() if self.selected in labels},
        )
        editor.set_automatic(definition.mode == AUTOMATIC)
        self._loading = False
        self._preview()

    def _rename(self, name: str) -> None:
        if self._loading or not self.selected:
            return
        self.save_timer.stop()
        self.name_inputs[self.profile_id][self.selected] = name
        try:
            old = self.selected
            self.state.rename(old, name)
        except ValueError as error:
            self.editor.status.setText(str(error))
            self.window.workspace.set_dirty("labels", True)
            return
        self.selected = name.strip()
        self.name_inputs[self.profile_id].pop(old, None)
        draft = self.fragments[self.profile_id].pop(old, None)
        if draft is not None:
            self.fragments[self.profile_id][self.selected] = draft
        self.renames[self.profile_id] = {original: self.selected if value == old else value for original, value in self.renames[self.profile_id].items()}
        item = self.editor.list_model.itemFromIndex(self.editor.list_view.currentIndex())
        item.setData(self.selected, QtCore.Qt.UserRole)
        self._preview()

    def _edit(self, *_args) -> None:
        if self._loading or not self.selected:
            return
        definition = self.state.definitions[self.selected]
        definition.mode = AUTOMATIC if self.editor.mode_box.currentIndex() else MANUAL
        definition.terms = self.editor.terms_edit.draft.preview_terms()
        definition.exclusions = self.editor.terms_edit.draft.preview_exclusions()
        self.editor.set_automatic(definition.mode == AUTOMATIC)
        self._preview()

    def _check(self, mod: str, checked: bool) -> None:
        self.state.assign(self.selected, [mod], checked)
        self._preview()

    def _preview(self) -> None:
        names = [mod for mod in self.window.current_mod_names if self.selected in self.state.members(mod)]
        definition = self.state.definitions[self.selected]
        self.editor.matches_model.set_matches(names, definition.terms if definition.mode == AUTOMATIC else [])
        self.editor.matches_heading.setText(t('matching_mods_value0', value0=f'{len(names)}'))
        item = self.editor.list_model.itemFromIndex(self.editor.list_view.currentIndex())
        update_label_item(item, self.selected, definition.mode, len(names))
        self._update_status()
        if not self._loading:
            self.save_timer.start()

    def _update_status(self) -> None:
        changed = self.state != self.saved[self.profile_id] or bool(self.name_inputs[self.profile_id])
        self.editor.status.setText(t('unsaved_changes') if changed else t('all_saved'))
        dirty = any(state != self.saved.get(profile) or bool(self.name_inputs.get(profile))
                    for profile, state in self.drafts.items())
        dirty = dirty or bool(self.selected and self.editor.name_edit.text().strip() != self.selected)
        self.window.workspace.set_dirty("labels", dirty)

    def add(self) -> None:
        index = 1
        name = t('new_label')
        while any(value.casefold() == name.casefold() for value in self.state.definitions):
            index += 1
            name = t('new_label_value0', value0=f'{index}')
        self.state.definitions[name] = LabelDefinition()
        self._rebuild(name)
        self.editor.name_edit.setFocus()
        self.editor.name_edit.selectAll()
        self.save_timer.start()

    def delete(self) -> None:
        if self.selected:
            self.renames[self.profile_id] = {original: "" if value == self.selected else value for original, value in self.renames[self.profile_id].items()}
            self.state.delete(self.selected)
            self.fragments[self.profile_id].pop(self.selected, None)
            self.name_inputs[self.profile_id].pop(self.selected, None)
            self.selected = ""
            self._rebuild()
            self.editor.status.setText(t('unsaved_changes'))
            self.save_timer.start()

    def save(self) -> None:
        self.save_timer.stop()
        if self.profile_id not in self.drafts or self.profile_id != str(self.window.cfg.get("active_game_profile_id") or ""):
            return
        if self.window.busy:
            self.save_timer.start()
            return
        was_failed = self._save_failed
        self._save_failed = False
        if self.name_inputs[self.profile_id]:
            self.editor.status.setText(t('enter_a_unique_nonempty_label_name_before_saving'))
            return
        candidate = deepcopy(self.state)
        for name, draft in self.fragments[self.profile_id].items():
            try:
                candidate.definitions[name].terms = draft.committed_terms()
                candidate.definitions[name].exclusions = draft.committed_exclusions()
            except ValueError as error:
                self.editor.status.setText(str(error))
                return
        try:
            candidate.validate()
        except ValueError as error:
            self.editor.status.setText(str(error))
            return
        try:
            latest = load_label_state()
            merged = merge_label_states(self.saved[self.profile_id], candidate, latest, self.renames[self.profile_id])
            if merged != latest:
                save_label_state(merged)
        except (OSError, ValueError) as error:
            self._save_failed = True
            self.editor.status.setText(str(error))
            self.window._set_status(t("operation_failed", label=t("labels"), error=str(error)))
            self.editor.retry.show()
            self.editor.reload.show()
            return
        for name, draft in tuple(self.fragments[self.profile_id].items()):
            if name not in merged.definitions:
                del self.fragments[self.profile_id][name]
            elif (merged.definitions[name].terms != candidate.definitions[name].terms
                  or merged.definitions[name].exclusions != candidate.definitions[name].exclusions):
                draft.terms = list(merged.definitions[name].terms)
                draft.exclusions = list(merged.definitions[name].exclusions)
                draft.pending = draft.edited = ""
                draft.editing = None
                if name == self.selected:
                    self.editor.terms_edit.bind(draft)
        self.drafts[self.profile_id] = merged
        self.saved[self.profile_id] = deepcopy(merged)
        self.window.filters.reconcile_labels(self.state.definitions, self.renames[self.profile_id])
        self.renames[self.profile_id] = {name: name for name in self.state.definitions}
        self.editor.retry.hide()
        self.editor.reload.hide()
        self._refresh_items()
        if self.selected in merged.definitions:
            automatic = merged.definitions[self.selected].mode == AUTOMATIC
            with QtCore.QSignalBlocker(self.editor.mode_box):
                self.editor.mode_box.setCurrentIndex(1 if automatic else 0)
            self.editor.set_automatic(automatic)
        if merged != latest:
            self.window.refresh_mods(self.window._selected_mod_names())
        self._update_status()
        if was_failed:
            self.window._set_status(t("all_saved"))

    def reload_saved(self) -> None:
        if prompts.ask_yes_no(self.window, t("labels"), t("discard_label_draft"), default_no=True):
            self.reset()

    def flush(self) -> bool:
        self.save()
        return not self._save_failed

    def shutdown(self) -> bool:
        saved = self.flush()
        self.save_timer.stop()
        return saved

    def reset(self) -> None:
        self.save_timer.stop()
        self._save_failed = False
        try:
            self.saved[self.profile_id] = load_label_state()
        except (OSError, ValueError) as error:
            prompts.show_error(self.window, t('labels'), str(error))
            return
        self.drafts[self.profile_id] = deepcopy(self.saved[self.profile_id])
        self.fragments[self.profile_id] = {}
        self.name_inputs[self.profile_id] = {}
        self.renames[self.profile_id] = {name: name for name in self.state.definitions}
        self._rebuild(self.selected)
        self.editor.status.setText(t('all_saved'))
        self.editor.retry.hide()
        self.editor.reload.hide()
