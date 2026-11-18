from __future__ import annotations

from datetime import datetime

from PySide6 import QtCore, QtGui, QtWidgets

from ...i18n import t
from ...models import ModItem
from ...settings_schema import spec_for
from ...trash import preview_path
from ..image_cache import ImageCache
from ..theme.colors import build_palette
from ..theme import tokens
from .item_feedback import ItemFeedback, AnimatedItemDelegate
from .segmented_control import SegmentedControl
from .trash_cards import TRASH_DAYS_ROLE, TRASH_ENTRY_ROLE, TrashTileDelegate, days_text
from .style_utils import apply_margins
from .toolbar import IconToolbar


class TrashView(QtWidgets.QWidget):
    restoreRequested = QtCore.Signal()
    deleteRequested = QtCore.Signal()
    refreshRequested = QtCore.Signal()
    modeChanged = QtCore.Signal(str)

    def __init__(self, parent=None, cfg=None, runner=None):
        super().__init__(parent)
        self.entries = []
        self.cfg = cfg if cfg is not None else {}
        self.mode = self.cfg.get("trash_view_mode", "list")
        self.images = ImageCache(runner, lambda cfg, _name: cfg.get("trash_preview"), self) if runner else None
        self.model = QtGui.QStandardItemModel(self)
        self.model.operation_frames = {}
        self.model.operation_states = {}
        self.table = QtWidgets.QTableView(self)
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(tokens.TABLE_ROW_HEIGHT)
        self.table.setShowGrid(False)
        self.table.setItemDelegate(AnimatedItemDelegate(self.table))
        self.tiles = QtWidgets.QListView(self)
        self.tiles.setModel(self.model)
        self.tiles.setSelectionModel(self.table.selectionModel())
        self.tiles.setViewMode(QtWidgets.QListView.IconMode)
        self.tiles.setResizeMode(QtWidgets.QListView.Adjust)
        self.tiles.setMovement(QtWidgets.QListView.Static)
        self.tiles.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.tiles.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.tiles.setUniformItemSizes(True)
        self.tiles.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.tile_delegate = TrashTileDelegate(self.cfg, self.images, build_palette("light"), self)
        self.tiles.setItemDelegate(self.tile_delegate)
        ItemFeedback(self.table)
        ItemFeedback(self.tiles)
        self.stack = QtWidgets.QStackedWidget(self)
        self.stack.addWidget(self.table)
        self.stack.addWidget(self.tiles)
        spec = spec_for("trash_view_mode")
        self.mode_control = SegmentedControl((
            ("list", t("trash_list"), "list", spec.tooltip),
            ("tiles", t("trash_tiles"), "tiles", spec.tooltip),
        ), self)
        self.mode_control.setToolTip(spec.tooltip)
        self.mode_control.valueChanged.connect(self.set_mode)
        if self.images:
            self.images.ready.connect(lambda _name: self.tiles.viewport().update())
        self.status = QtWidgets.QLabel(t("trash_empty"), self)
        self.status.setWordWrap(True)
        self.toolbar = IconToolbar(self)
        section = self.toolbar.add_section("trash", t("trash"))
        section.add_text_action("restore", t("trash_restore"), "reset", t("trash_restore_help"), self.restoreRequested.emit)
        section.add_text_action("delete", t("trash_delete"), "delete", t("trash_delete_help"), self.deleteRequested.emit)
        section.add_text_action("refresh", t("refresh"), "refresh", t("refresh"), self.refreshRequested.emit)
        self.toolbar.add_stretch()
        layout = apply_margins(QtWidgets.QVBoxLayout(self), spacing=tokens.SPACE_LG)
        layout.addWidget(self.mode_control)
        layout.addWidget(self.status)
        layout.addWidget(self.stack, 1)
        layout.addWidget(self.toolbar)
        self.table.selectionModel().selectionChanged.connect(self.update_actions)
        self.pending = set()
        self.badge_timer = QtCore.QTimer(self)
        self.badge_timer.setInterval(tokens.TRASH_BADGE_REFRESH_MS)
        self.badge_timer.timeout.connect(self.refresh_days)
        self.badge_timer.start()
        self.update_actions()
        self.set_mode(self.mode, persist=False)

    def set_mode(self, mode, *, persist=True):
        self.mode = mode if mode in ("list", "tiles") else "list"
        self.mode_control.set_value(self.mode)
        self.stack.setCurrentWidget(self.tiles if self.mode == "tiles" else self.table)
        if persist:
            self.modeChanged.emit(self.mode)

    def refresh_days(self):
        for row, entry in enumerate(self.entries):
            item = self.model.item(row)
            text = days_text(entry)
            if item.data(TRASH_DAYS_ROLE) != text:
                item.setData(text, TRASH_DAYS_ROLE)

    def selected_entries(self):
        rows = {index.row() for index in self.table.selectionModel().selectedIndexes()}
        return [self.entries[row] for row in sorted(rows) if row < len(self.entries)]

    def update_actions(self, *_args) -> None:
        selected = self.selected_entries()
        available = bool(selected) and not any(entry.identifier in self.pending for entry in selected)
        self.toolbar.set_enabled("restore", available and all(not entry.missing for entry in selected))
        self.toolbar.set_enabled("delete", available)

    def set_entries(self, entries) -> None:
        entries = list(entries)
        if entries == self.entries:
            self.refresh_days()
            return
        selected = {entry.identifier for entry in self.selected_entries()}
        self.entries = list(entries)
        self.model.clear()
        self.model.setHorizontalHeaderLabels([t("mod"), t("game"), t("trash_deleted_at"), t("trash_expires_at"), t("state")])
        for entry in entries:
            state = t("trash_incomplete") if entry.missing else t("trash_ready")
            deleted = datetime.fromisoformat(entry.data["deleted_at"]).astimezone().strftime("%Y-%m-%d %H:%M")
            expires = datetime.fromisoformat(entry.data["expires_at"]).astimezone().strftime("%Y-%m-%d %H:%M")
            values = (entry.name, entry.data["profile_name"], deleted, expires, state)
            items = [QtGui.QStandardItem(value) for value in values]
            for item in items:
                item.setToolTip(str(entry.root) + "\n" + state)
            for item in items:
                item.setEditable(False)
                item.setToolTip(item.toolTip() + chr(10) + expires)
            items[0].setData(entry, TRASH_ENTRY_ROLE)
            items[0].setData(ModItem(entry.name, entry.path, preview_path(entry), False, False), QtCore.Qt.UserRole)
            self.model.appendRow(items)
            if entry.identifier in selected:
                index = self.model.index(self.model.rowCount() - 1, 0)
                self.table.selectionModel().select(index, QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Rows)
        self.status.setText(t("trash_help") if entries else t("trash_empty"))
        self.status.setVisible(not entries)
        self.update_actions()
        self.refresh_days()

    def shutdown(self):
        self.badge_timer.stop()
        if self.images:
            self.images.shutdown()
