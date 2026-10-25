from __future__ import annotations

from copy import deepcopy

from PySide6 import QtCore, QtGui

from ...labels import AUTOMATIC, MANUAL, LabelDefinition, LabelState, unique_names
from ...storage import load_label_state, save_label_state
from ..dialogs import prompts
from ..widgets.label_editor import LabelEditor
from ..widgets.workspace import WorkspacePage
from .widget_registry import ACTIONS


class LabelsController(QtCore.QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.page = WorkspacePage("Labels", "Manage manual labels and automatic name matches. Save to apply your changes.")
        self.editor = LabelEditor()
        self.page.body.addWidget(self.editor)
        self.drafts: dict[str, LabelState] = {}
        self.saved: dict[str, LabelState] = {}
        self.renames: dict[str, dict[str, str]] = {}
        self.profile_id = ""
        self.selected = ""
        self._loading = False
        editor = self.editor
        editor.list_view.selectionModel().currentChanged.connect(self._select)
        editor.name_edit.textEdited.connect(self._rename)
        editor.mode_box.currentIndexChanged.connect(self._edit)
        editor.terms_edit.textChanged.connect(self._edit)
        editor.manual_model.checkedChanged.connect(self._check)
        editor.toolbar.connect({"add": self.add, "delete": self.delete, "save": self.save, "reset": self.reset})
        window.registry.extend(ACTIONS, editor.toolbar.buttons.values())

    @property
    def state(self) -> LabelState:
        return self.drafts[self.profile_id]

    def activate(self) -> bool:
        self.profile_id = str(self.window.cfg.get("active_game_profile_id") or "")
        try:
            current = load_label_state()
        except (OSError, ValueError) as error:
            prompts.show_error(self.window, "Labels", str(error))
            return False
        if self.profile_id not in self.drafts or self.drafts[self.profile_id] == self.saved.get(self.profile_id):
            self.drafts[self.profile_id] = deepcopy(current)
            self.saved[self.profile_id] = deepcopy(current)
            self.renames[self.profile_id] = {name: name for name in current.definitions}
        self._rebuild(self.selected)
        return True

    def _rebuild(self, selected: str = "") -> None:
        self._loading = True
        self.editor.list_model.clear()
        names = sorted(self.state.definitions, key=str.casefold)
        counts = dict.fromkeys(names, 0)
        for mod in self.window.current_mod_names:
            for name in self.state.members(mod):
                counts[name] += 1
        for name in names:
            definition = self.state.definitions[name]
            count = counts[name]
            item = QtGui.QStandardItem(f"{name} · {definition.mode.capitalize()} · {count}")
            item.setEditable(False)
            item.setToolTip(name)
            item.setData(name, QtCore.Qt.UserRole)
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
            self.editor.terms_edit.clear()
            self.editor.manual_model.set_choices([], set())
            self.editor.details.setEnabled(False)
            self.editor.matches_model.setStringList([])
            self.editor.matches_heading.setText("Matching mods (0)")
            self._loading = False
        self.editor.toolbar.set_enabled("delete", bool(names))
        self.editor.status.setText("Unsaved changes" if self.state != self.saved[self.profile_id] else "All changes saved")

    def _select(self, index, _previous) -> None:
        if self._loading or not index.isValid():
            return
        self.selected = index.data(QtCore.Qt.UserRole)
        definition = self.state.definitions[self.selected]
        self._loading = True
        editor = self.editor
        editor.details.setEnabled(True)
        editor.name_edit.setText(self.selected)
        editor.mode_box.setCurrentIndex(1 if definition.mode == AUTOMATIC else 0)
        editor.terms_edit.setPlainText("\n".join(definition.terms))
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
        try:
            old = self.selected
            self.state.rename(old, name)
        except ValueError as error:
            self.editor.status.setText(str(error))
            return
        self.selected = name.strip()
        self.renames[self.profile_id] = {original: self.selected if value == old else value for original, value in self.renames[self.profile_id].items()}
        item = self.editor.list_model.itemFromIndex(self.editor.list_view.currentIndex())
        item.setData(self.selected, QtCore.Qt.UserRole)
        self._preview()

    def _edit(self, *_args) -> None:
        if self._loading or not self.selected:
            return
        definition = self.state.definitions[self.selected]
        definition.mode = AUTOMATIC if self.editor.mode_box.currentIndex() else MANUAL
        definition.terms = unique_names(self.editor.terms_edit.toPlainText().splitlines())
        self.editor.set_automatic(definition.mode == AUTOMATIC)
        self._preview()

    def _check(self, mod: str, checked: bool) -> None:
        self.state.assign(self.selected, [mod], checked)
        self._preview()

    def _preview(self) -> None:
        names = [mod for mod in self.window.current_mod_names if self.selected in self.state.members(mod)]
        self.editor.matches_model.setStringList(names)
        self.editor.matches_heading.setText(f"Matching mods ({len(names)})")
        definition = self.state.definitions[self.selected]
        item = self.editor.list_model.itemFromIndex(self.editor.list_view.currentIndex())
        item.setText(f"{self.selected} · {definition.mode.capitalize()} · {len(names)}")
        item.setToolTip(self.selected)
        self.editor.status.setText("Unsaved changes" if self.state != self.saved[self.profile_id] else "All changes saved")

    def add(self) -> None:
        index = 1
        name = "New label"
        while any(value.casefold() == name.casefold() for value in self.state.definitions):
            index += 1
            name = f"New label {index}"
        self.state.definitions[name] = LabelDefinition()
        self._rebuild(name)
        self.editor.name_edit.setFocus()
        self.editor.name_edit.selectAll()

    def delete(self) -> None:
        if self.selected:
            self.renames[self.profile_id] = {original: "" if value == self.selected else value for original, value in self.renames[self.profile_id].items()}
            self.state.delete(self.selected)
            self._rebuild()
            self.editor.status.setText("Unsaved changes")

    def save(self) -> None:
        if self.selected and self.editor.name_edit.text().strip() != self.selected:
            self.editor.status.setText("Enter a unique, nonempty label name before saving.")
            return
        try:
            if load_label_state() != self.saved[self.profile_id]:
                raise ValueError("Saved labels changed while this draft was open. Reset changes to load the current labels.")
            save_label_state(self.state)
        except (OSError, ValueError) as error:
            prompts.show_error(self.window, "Labels", str(error))
            return
        self.saved[self.profile_id] = deepcopy(self.state)
        active = self.window.label_filter_var.get()
        renamed = next((value for original, value in self.renames[self.profile_id].items() if original.casefold() == active.casefold()), active)
        self.window.label_filter_var.set(renamed if renamed in self.state.definitions else "")
        self.renames[self.profile_id] = {name: name for name in self.state.definitions}
        self.window.refresh_mods()
        self._rebuild(self.selected)
        self.editor.status.setText("All changes saved")

    def reset(self) -> None:
        try:
            self.saved[self.profile_id] = load_label_state()
        except (OSError, ValueError) as error:
            prompts.show_error(self.window, "Labels", str(error))
            return
        self.drafts[self.profile_id] = deepcopy(self.saved[self.profile_id])
        self.renames[self.profile_id] = {name: name for name in self.state.definitions}
        self._rebuild(self.selected)
        self.editor.status.setText("All changes saved")
