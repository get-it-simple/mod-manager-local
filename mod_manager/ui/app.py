from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable, List

from PySide6 import QtCore, QtGui, QtWidgets

from app_paths import APP_NAME, APP_VERSION

from ..folder_actions import ensure_paths, select_in_explorer
from ..dragdrop import clipboard_has_files, read_clipboard_image, read_clipboard_paths
from ..imports import ignored_file, regular_import_tasks
from ..models import ModItem, OperationResult
from ..labels import AUTOMATIC, ResolvedLabels, label_names
from ..link_recovery import preset_install_names
from ..mods import (
    add_favorites_to_mods,
    add_label_to_mods,
    change_mods,
    change_mods_page,
    deactivate_mod_result,
    existing_targets,
    is_copy_install,
    is_image_file,
    is_mod_file,
    list_broken_links,
    list_installed_mods,
    mod_image_path,
    mods_by_indexes,
    mods_records,
    overwrite_message,
    mods_view,
    remove_label_from_mods,
    remove_favorites_from_mods,
)
from ..presets import (
    delete_presets_by_names,
    preset_mods_to_install,
    presets_records,
    presets_view,
    save_preset_from_installed,
    toggle_presets_result,
)
from ..storage import (
    active_game_profile,
    load_config,
    load_favorites,
    normalize_game_profiles,
    save_config,
)
from . import icons
from .pages.library import build_mods, build_mods_toolbar, build_mods_actions
from .pages.collections import build_presets, build_broken
from .widgets.workspace import Workspace, WorkspacePage, PROFILE_PAGES
from .context import AppContext
from .controllers import ACTIONS, SELECTION, WidgetRegistry
from .controllers.settings_controller import SAVED_MESSAGE as SETTINGS_SAVED
from .controllers.games_controller import GamesController
from .controllers.labels_controller import LabelsController
from .controllers.settings_controller import SettingsController
from .controllers.archive_import_controller import ArchiveImportController
from .controllers.preview_controller import PreviewController
from .controllers.error_history_controller import ErrorHistoryController
from .dialogs import prompts
from .dialogs.game_profile import GameProfileDialog
from .dialogs.prompts import show_error
from .localization import system_action_text as _sys_str
from .theme import colors, tokens
from .task_runner import TaskRunner
from .theme.manager import ThemeManager
from .widgets import (
    DetailImageLabel,
    QtWindowsDropTarget,
    apply_margins,
    clear_layout,
    complete,
    configure_completer,
    configure_filter_box,
    detail_name_label,
    fixed_size_policy,
    icon_button,
    owns_event_source,
    path_button,
    refresh_page_title,
    select_box,
    text_button,
)
from .view_modes import (
    MOD_ORDER_OPTIONS,
    normalize_sort_key,
    normalize_view_mode,
    order_label_for_key,
    order_label_from_config,
    order_mode,
    sort_key_for_column,
)
from ..workers import _run_import_batch

OVERWRITE_TITLE = "Overwrite files"
OVERWRITE_QUESTION = "{message}\n\nReplace them?"


class _Var:
    def __init__(self, value=None, on_change: Callable | None = None):
        self._value = value
        self._on_change = on_change

    def get(self):
        return self._value

    def set(self, value) -> None:
        self._value = value
        if self._on_change:
            self._on_change()



_sort_direction_icon = icons.sort_direction_icon


class ModManagerGui(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.cfg = normalize_game_profiles(load_config())
        self._applying_theme = False
        self.runner = TaskRunner(self)
        self.runner.statusChanged.connect(self.statusBar().showMessage)
        self.runner.failed.connect(lambda message: show_error(self, "Error", message))
        self.runner.busyChanged.connect(self._on_busy_changed)
        self.archive_import = ArchiveImportController(self)
        self.previews = PreviewController(self)
        self._init_theme()
        self.context = AppContext(self.cfg, self.theme, self.runner)
        self.errors = ErrorHistoryController(self)
        self.registry = WidgetRegistry()
        self.resize(
            max(tokens.MIN_WIDTH, tokens.to_int(self.cfg.get("window_width"), tokens.DEFAULT_WIDTH)),
            max(tokens.MIN_HEIGHT, tokens.to_int(self.cfg.get("window_height"), tokens.DEFAULT_HEIGHT)),
        )
        self.setMinimumSize(tokens.MIN_WIDTH, tokens.MIN_HEIGHT)
        self.setAcceptDrops(True)

        self.mod_page = _Var(1)
        self.preset_page = _Var(1)
        self.search_var = _Var("")
        self.label_filter_var = _Var("")
        self.favorite_filter_var = _Var(False)
        self.label_edit_var = _Var("")
        self.order_var = _Var(self._mod_order_label_from_config())
        self.mod_view_mode = _Var(normalize_view_mode(self.cfg.get("mod_view_mode")))

        self.current_mod_items: list[ModItem] = []
        self.current_mod_names: list[str] = []
        self.current_mods_shown: list[ModItem] = []
        self.current_mod_labels: dict[str, str] = {}
        self.current_mod_records: dict[str, dict] = {}
        self.current_mod_favorites: set[str] = set()
        self.current_broken: list[ModItem] = []
        self.mod_sort_key = MOD_ORDER_OPTIONS.get(self.order_var.get(), normalize_sort_key(self.cfg.get("mod_sort_key")))
        self.mod_sort_reverse = bool(self.cfg.get("mod_sort_reverse", False))
        self.preset_sort_key = self.cfg.get("preset_sort_key", "name")
        self.preset_sort_reverse = bool(self.cfg.get("preset_sort_reverse", False))

        self._build()
        self._setup_com_drop_targets()
        self._bind_navigation_events()
        self.refresh_all()

    def _setup_com_drop_targets(self) -> None:
        from ..platform_utils import is_windows
        if not is_windows():
            return

        def make_callback(viewport):
            def callback(paths, x, y):
                pos = viewport.mapFromGlobal(QtCore.QPoint(x, y))
                mod_name = self._mod_name_at_view_position(viewport, pos)
                self._handle_mods_drop(paths, target_mod_name=mod_name)
            return callback

        self._table_drop_target = QtWindowsDropTarget(
            self.mods_table.viewport(), make_callback(self.mods_table.viewport())
        )
        self._tiles_drop_target = QtWindowsDropTarget(
            self.tiles_view.viewport(), make_callback(self.tiles_view.viewport())
        )

    def closeEvent(self, event) -> None:
        self.filter_expansion.shutdown()
        self._close_label_choices()
        self.mod_menu.shutdown()
        self.cfg["window_width"] = self.width()
        self.cfg["window_height"] = self.height()
        self._save_tile_splitter_sizes()
        save_config(self.cfg)
        self.archive_import.shutdown()
        if self.errors.dialog is not None:
            self.errors.dialog.close()
        self.runner.shutdown()
        for attr in ("_table_drop_target", "_tiles_drop_target"):
            target = getattr(self, attr, None)
            if target is not None:
                target.disable()
        self._release_application_hooks()
        super().closeEvent(event)

    def _release_application_hooks(self) -> None:
        if not getattr(self, "_bound", False):
            return
        self._bound = False
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
            app.paletteChanged.disconnect(self._on_system_appearance_changed)
        style_hints = QtGui.QGuiApplication.styleHints()
        if hasattr(style_hints, "colorSchemeChanged"):
            style_hints.colorSchemeChanged.disconnect(self._on_system_appearance_changed)

    def _init_theme(self) -> None:
        if not hasattr(self, "theme"):
            self.theme = ThemeManager(self.cfg, self)
        self.theme.apply()
        self.setPalette(QtWidgets.QApplication.instance().palette())

    @property
    def _theme_mode(self) -> str:
        return self.theme.mode

    @property
    def _theme_palette_colors(self) -> colors.Palette:
        return self.theme.palette

    @property
    def _theme_is_dark(self) -> bool:
        return self.theme.palette.is_dark

    @property
    def _theme_accent(self) -> QtGui.QColor:
        return QtGui.QColor(self.theme.palette.accent)

    @property
    def _theme_button_text(self) -> QtGui.QColor:
        return QtGui.QColor(self.theme.palette.fg)

    def _refresh_theme(self) -> None:
        self._applying_theme = True
        try:
            self._init_theme()
            self._apply_button_style()
            palette = self.theme.palette
            self.mods_model.refresh_accent(palette.accent)
            self.presets_model.set_palette(palette)
            self.tile_delegate.set_palette(palette)
            self.workspace.refresh_icons()
            self.favorite_delegate.set_favorites(self.current_mod_favorites)
            self.tiles_view.viewport().update()
            for button in self.action_widgets:
                if isinstance(button, QtWidgets.QAbstractButton):
                    icon_name = button.property("iconName")
                    if icon_name:
                        button.setIcon(self._icon(icon_name))
            for label in self.findChildren(QtWidgets.QLabel):
                if label.property("pageTitle"):
                    refresh_page_title(label)
            self._update_mod_order_direction_button()
            if hasattr(self, "_settings_form"):
                self._update_theme_preview()
                self.settings.update_font_preview()
            for dialog in self._dialogs():
                dialog.setPalette(self.palette())
                dialog.update()
            self._refresh_selected_detail()
            self.update()
        finally:
            self._applying_theme = False

    def _dialogs(self) -> list[QtWidgets.QDialog]:
        dialogs = []
        if hasattr(self, "errors") and self.errors.dialog is not None:
            dialogs.append(self.errors.dialog)
        return dialogs

    def _on_system_appearance_changed(self, *_args) -> None:
        if self._applying_theme or self.theme.is_applying:
            return
        self.theme.on_system_appearance_changed()
        self._refresh_theme()

    def _setup_filter_box(self, box: QtWidgets.QComboBox) -> None:
        configure_filter_box(box)

    def _setup_completer(self, completer: QtWidgets.QCompleter) -> None:
        configure_completer(completer)

    def _completion_line_edits(self) -> list[QtWidgets.QLineEdit]:
        edits = [box.lineEdit() for box in getattr(self, "filter_boxes", ())]
        label_edit = getattr(self, "label_edit", None)
        if label_edit is not None:
            edits.append(label_edit)
        return edits

    def _completion_line_edit_for_object(self, obj) -> QtWidgets.QLineEdit | None:
        for edit in self._completion_line_edits():
            if owns_event_source(edit, obj):
                return edit
        return None

    def _complete_line_edit(self, line_edit: QtWidgets.QLineEdit) -> bool:
        return complete(line_edit)

    def eventFilter(self, obj, event):
        if event.type() in (QtCore.QEvent.ShortcutOverride, QtCore.QEvent.KeyPress) and event.matches(QtGui.QKeySequence.Paste):
            archive_active = self.archive_import.dialog is not None and isinstance(obj, QtWidgets.QWidget) and obj.window() is self.archive_import.dialog
            library_active = isinstance(obj, QtWidgets.QWidget) and obj.window() is self and self._is_mods_tab_active()
            if (archive_active or library_active) and not self.busy and clipboard_has_files():
                event.accept()
                if event.type() == QtCore.QEvent.KeyPress:
                    self._handle_paste()
                return True
        if event.type() == QtCore.QEvent.KeyPress and event.key() == QtCore.Qt.Key_Tab:
            line_edit = self._completion_line_edit_for_object(obj)
            if line_edit is not None and self._complete_line_edit(line_edit):
                return True
        if self._is_mod_drop_target(obj):
            if event.type() in (QtCore.QEvent.DragEnter, QtCore.QEvent.DragMove) and event.mimeData().hasUrls():
                event.acceptProposedAction()
                return True
            if event.type() == QtCore.QEvent.Drop:
                paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
                if paths:
                    self._handle_mods_drop(paths, target_mod_name=self._mod_name_at_view_position(obj, event.position().toPoint()))
                    event.acceptProposedAction()
                    return True
        if event.type() == QtCore.QEvent.MouseButtonPress:
            tiles_view = getattr(self, "tiles_view", None)
            if tiles_view is not None and obj is tiles_view.viewport() and event.button() == QtCore.Qt.LeftButton:
                label = self._tile_label_at_position(event.position().toPoint())
                if label:
                    self._toggle_label_filter(label)
                    event.accept()
                    return True
            if isinstance(obj, QtWidgets.QWidget) and obj.window() is self and event.button() == QtCore.Qt.XButton1:
                return self._nav_back() == "break"
            if isinstance(obj, QtWidgets.QWidget) and obj.window() is self and event.button() == QtCore.Qt.XButton2:
                return self._nav_forward() == "break"
        return super().eventFilter(obj, event)

    def _bind_navigation_events(self) -> None:
        app = QtWidgets.QApplication.instance()
        app.installEventFilter(self)
        app.paletteChanged.connect(self._on_system_appearance_changed)
        style_hints = QtGui.QGuiApplication.styleHints()
        if hasattr(style_hints, "colorSchemeChanged"):
            style_hints.colorSchemeChanged.connect(self._on_system_appearance_changed)
        self._bound = True
        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Backspace), self, activated=self._nav_back)
        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Back), self, activated=self._nav_back)
        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Forward), self, activated=self._nav_forward)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl++"), self, activated=lambda: self._zoom_tiles(1))
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+="), self, activated=lambda: self._zoom_tiles(1))
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+-"), self, activated=lambda: self._zoom_tiles(-1))
        QtGui.QShortcut(QtGui.QKeySequence.Paste, self, activated=self._handle_paste)

    def _is_mods_tab_active(self) -> bool:
        return self.workspace.current_page == "library" and not self.busy

    def _editing_text(self) -> bool:
        return isinstance(QtWidgets.QApplication.focusWidget(), (QtWidgets.QLineEdit, QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit, QtWidgets.QAbstractSpinBox))

    def _is_tile_view(self) -> bool:
        return self.mod_view_mode.get() == "tiles"

    def _nav_back(self, event=None):
        if self._is_mods_tab_active() and not self._editing_text():
            self._change_mod_page(-1)
            return "break"
        return None

    def _nav_forward(self, event=None):
        if self._is_mods_tab_active() and not self._editing_text():
            self._change_mod_page(1)
            return "break"
        return None

    def _build(self) -> None:
        self.workspace = Workspace(self)
        self.setCentralWidget(self.workspace)
        self.workspace.pageRequested.connect(self._navigate)
        self.workspace.profileRequested.connect(self._select_game_profile)
        self.game_button = self.workspace.game_button
        self.games_page = WorkspacePage("Game profiles", "Choose a game or add a profile to get started.")
        self.mods_tab = WorkspacePage("Library")
        self.statusBar().showMessage("Ready")
        self.selection_status = QtWidgets.QLabel("0 selected")
        self.statusBar().addPermanentWidget(self.selection_status)
        self._apply_button_style()
        self._build_games_page()
        self._build_mods()
        self._build_presets()
        self._build_settings()
        self._build_broken()
        self.labels_controller = LabelsController(self)
        for key, page in (("library", self.mods_tab), ("labels", self.labels_controller.page), ("games", self.games_page), ("presets", self.presets_page), ("settings", self.settings.page), ("cleanup", self.broken_page)):
            self.workspace.add_page(key, page)
        self.registry.extend(ACTIONS, self.workspace.navigation.values())
        self.registry.extend(ACTIONS, (self.workspace.profile_box, self.game_button))
        self._show_start_page()

    def _apply_button_style(self) -> None:
        self._theme_stylesheet = self.theme.stylesheet
        self.setStyleSheet(self._theme_stylesheet)

    def _build_games_page(self) -> None:
        self.games = GamesController(self, self.games_page)
        self.games_list = self.games.page_list
        self.games_page_toolbar = self.games.page_toolbar

    def _open_presets_page(self) -> None:
        self._navigate("presets")

    def _open_settings_page(self) -> None:
        self._navigate("settings")

    def _open_broken_page(self) -> None:
        self._navigate("cleanup")

    def _open_games_page(self) -> None:
        self._navigate("games")

    def _navigate(self, key: str) -> None:
        if self.busy or (key in PROFILE_PAGES and not active_game_profile(self.cfg)):
            return
        self.mod_menu.close()
        self._close_label_choices()
        if key == "presets":
            self.refresh_presets()
        elif key == "labels":
            if not self.labels_controller.activate():
                return
        elif key == "cleanup":
            self.refresh_broken()
        elif key == "games":
            self._refresh_games_lists()
        self.workspace.show_page(key)

    def _sync_workspace(self) -> None:
        profile = active_game_profile(self.cfg)
        self.workspace.set_profiles(self.cfg.get("game_profiles", []), profile.get("id", "") if profile else "", self.busy)
        self.mods_tab.set_subtitle(f"{profile.get('name', 'Game')} · {len(self.current_mod_items)} mods" if profile else "")

    def _show_start_page(self) -> None:
        self._refresh_games_lists()
        if active_game_profile(self.cfg):
            self._set_main_page(self.mods_tab)
            self._update_game_button()
        else:
            self._set_main_page(self.games_page)

    def _set_main_page(self, widget: QtWidgets.QWidget) -> None:
        key = next(key for key, page in self.workspace.pages.items() if page is widget)
        self.workspace.show_page(key)

    def _update_game_button(self) -> None:
        self.games.update_game_button()

    def _refresh_games_lists(self) -> None:
        self.games.refresh_lists()

    def _select_game_profile(self, profile_id: str) -> None:
        if not self.busy:
            self.games.select(profile_id)

    def _add_game_profile(self) -> None:
        self.games.add()

    def _edit_game_profile(self, profile_id: str) -> None:
        self.games.edit(profile_id)

    def _delete_game_profile(self, profile_id: str) -> None:
        self.games.delete(profile_id)

    def _game_profile_values(self, profile: dict | None = None) -> dict | None:
        return GameProfileDialog(self, profile).values()

    def _icon(self, name: str) -> QtGui.QIcon:
        return icons.standard_icon(name, self.style())

    def _icon_button(self, text: str, command: Callable, tooltip: str, icon: str, icon_only: bool = True):
        if icon_only:
            button = icon_button(icon, tooltip or text, command, self, accessible_name=text)
        else:
            button = text_button(text, tooltip or text, command, self, icon_name=icon)
        self.registry.add(ACTIONS, button)
        return button

    def _mod_selection_button(self, text: str, command: Callable, tooltip: str = "", icon: str = "toggle"):
        button = self._icon_button(text, command, tooltip or text, icon)
        button.setEnabled(False)
        self.registry.add(SELECTION, button)
        return button

    def _set_icon_button_checked(self, button: QtWidgets.QPushButton, checked: bool) -> None:
        button.setCheckable(True)
        button.setChecked(checked)

    def _mod_order_options(self) -> dict[str, str]:
        return dict(MOD_ORDER_OPTIONS)

    def _normalize_mod_sort_key(self, key: str) -> str:
        return normalize_sort_key(key)

    def _mod_order_label_for_key(self, key: str) -> str:
        return order_label_for_key(key)

    def _mod_order_label_from_config(self) -> str:
        return order_label_from_config(self.cfg)

    def _filter_box(self, placeholder: str) -> QtWidgets.QComboBox:
        box = select_box(editable=True)
        box.lineEdit().setPlaceholderText(placeholder)
        box.lineEdit().returnPressed.connect(self._mods_search)
        return configure_filter_box(box)

    def _build_mods_toolbar(self):
        return build_mods_toolbar(self)

    def _build_mods_actions(self):
        return build_mods_actions(self)

    def _apply_state_column_width(self) -> None:
        width = tokens.to_int(self.cfg.get("placeholder_image_col_width"), 0)
        if width > 0:
            self.mods_table.horizontalHeader().resizeSection(0, width)

    def _build_mods(self):
        return build_mods(self)

    def _save_tile_splitter_sizes(self) -> None:
        if not hasattr(self, "tile_splitter"):
            return
        sizes = self.tile_splitter.sizes()
        if self.detail_scroll.isVisibleTo(self.tile_splitter) and len(sizes) >= 2 and sizes[0] > 0 and sizes[1] > 0:
            self.cfg["_tile_list_width"] = int(sizes[0])
            self.cfg["_tile_detail_width"] = int(sizes[1])

    def _restore_tile_splitter_sizes(self) -> None:
        if not hasattr(self, "tile_splitter"):
            return
        list_w = int(self.cfg.get("_tile_list_width") or 0)
        detail_w = int(self.cfg.get("_tile_detail_width") or 0)
        if list_w > 0 and detail_w > 0:
            self.tile_splitter.setSizes([list_w, detail_w])
        else:
            self.tile_splitter.setSizes([self.width(), tokens.DETAIL_PANEL_MIN_WIDTH])

    def _toggle_details(self) -> None:
        self._set_details_visible(self.details_button.isChecked())

    def _set_details_visible(self, visible: bool) -> None:
        if not visible:
            self._save_tile_splitter_sizes()
        self.cfg["mod_details_visible"] = visible
        self.setting_widgets["mod_details_visible"].setChecked(visible)
        self._apply_details_visibility()
        save_config(self.cfg)

    def _apply_details_visibility(self) -> None:
        visible = bool(self.cfg.get("mod_details_visible", True))
        self.details_button.setChecked(visible)
        self.detail_scroll.setVisible(visible)
        if visible:
            self._restore_tile_splitter_sizes()

    def _build_presets(self):
        return build_presets(self)

    def _build_settings(self) -> None:
        self.settings = SettingsController(self)
        self.settings_page = self.settings.page
        self.settings_form = self.settings.form
        self._settings_form = self.settings.form
        self.setting_widgets = self.settings.fields
        self.settings_toolbar = self.settings.toolbar
        self.accent_preview_badge = self.settings.accent_badge
        self.accent_preview_button = self.settings.accent_button
        self.text_preview_badge = self.settings.text_badge

    def _build_broken(self):
        return build_broken(self)

    @property
    def busy(self) -> bool:
        return self.runner.busy

    @property
    def action_widgets(self) -> list:
        return self.registry.widgets(ACTIONS)

    @property
    def mod_selection_widgets(self) -> list:
        return self.registry.widgets(SELECTION)

    def _set_status(self, text: str) -> None:
        self.runner.set_status(text)

    def _on_busy_changed(self, busy: bool) -> None:
        self._close_label_choices()
        self.registry.set_enabled(ACTIONS, not busy)
        self._sync_workspace()
        self.workspace.stack.setEnabled(not busy)
        self._update_mod_selection_actions()

    def _set_busy(self, busy: bool, text: str = "") -> None:
        self.runner.set_busy(busy, text)

    def _run_action(self, label: str, worker: Callable, done: Callable | None = None, file_key: str = "global") -> None:
        self.runner.run(label, worker, done, file_key)

    def _poll_workers(self) -> None:
        self.runner.poll()

    def _view_args(self):
        return self.mod_page.get(), self.label_filter_var.get(), self.search_var.get(), self._mod_order_mode()

    def _mod_order_mode(self) -> str:
        return order_mode(self.mod_sort_key, self.mod_sort_reverse)

    def _preset_order_mode(self) -> str:
        key = self.preset_sort_key or "name"
        return f"-{key}" if self.preset_sort_reverse else key

    def _set_view_mode(self, mode: str) -> None:
        self.mod_menu.close()
        mode = normalize_view_mode(mode)
        self.mod_view_mode.set(mode)
        self.cfg["mod_view_mode"] = mode
        save_config(self.cfg)
        self._show_mod_view()

    def _set_mod_order(self, text: str) -> None:
        options = self._mod_order_options()
        text = text if text in options else "Default"
        self.order_var.set(text)
        key = options[text]
        if self.mod_sort_key == key:
            self.mod_sort_reverse = not self.mod_sort_reverse
        else:
            self.mod_sort_key = key
            self.mod_sort_reverse = False
        self.cfg["order_var"] = text
        self.cfg["mod_sort_key"] = self.mod_sort_key
        self.cfg["mod_sort_reverse"] = self.mod_sort_reverse
        self.mod_page.set(1)
        save_config(self.cfg)
        self._update_mod_order_direction_button()
        self.refresh_mods()

    def _activate_mod_order(self, _index: int) -> None:
        self._set_mod_order(self.order_box.currentText())

    def _show_mod_view(self) -> None:
        is_tiles = self._is_tile_view()
        self.mods_stack.setCurrentWidget((self.tiles_view if is_tiles else self.mods_table) if self.current_mods_shown else self.library_empty)
        self.view_list_button.setChecked(not is_tiles)
        self.view_tiles_button.setChecked(is_tiles)
        self._refresh_selected_detail()
        self._apply_details_visibility()

    def _sort_mods(self, key: str) -> None:
        key = self._normalize_mod_sort_key(key)
        if self.mod_sort_key == key:
            self.mod_sort_reverse = not self.mod_sort_reverse
        else:
            self.mod_sort_key = key
            self.mod_sort_reverse = False
        self.order_var.set(self._mod_order_label_for_key(self.mod_sort_key))
        if hasattr(self, "order_box"):
            blocker = QtCore.QSignalBlocker(self.order_box)
            try:
                self.order_box.setCurrentText(self.order_var.get())
            finally:
                del blocker
        self.cfg["mod_sort_key"] = self.mod_sort_key
        self.cfg["mod_sort_reverse"] = self.mod_sort_reverse
        self.cfg["order_var"] = self.order_var.get()
        self.mod_page.set(1)
        save_config(self.cfg)
        self._update_mod_order_direction_button()
        self.refresh_mods()

    def _sort_mods_by_section(self, section: int) -> None:
        key = sort_key_for_column(section)
        if key:
            self._sort_mods(key)

    def _toggle_mod_order_direction(self) -> None:
        self.mod_sort_reverse = not self.mod_sort_reverse
        self.cfg["mod_sort_key"] = self.mod_sort_key
        self.cfg["mod_sort_reverse"] = self.mod_sort_reverse
        self.cfg["order_var"] = self._mod_order_label_for_key(self.mod_sort_key)
        save_config(self.cfg)
        self._update_mod_order_direction_button()
        self.mod_page.set(1)
        self.refresh_mods()

    def _update_mod_order_direction_button(self) -> None:
        button = getattr(self, "order_direction_button", None)
        if button is None:
            return
        button.setIcon(_sort_direction_icon(self.mod_sort_reverse, self._theme_button_text))
        button.setAccessibleName("Descending" if self.mod_sort_reverse else "Ascending")
        button.setToolTip("Sort descending" if self.mod_sort_reverse else "Sort ascending")

    def _zoom_tiles(self, direction: int):
        if not self._is_mods_tab_active() or self._editing_text():
            return
        if not self._is_tile_view():
            return None
        current = tokens.clamp_tile_size(self.cfg.get("tile_size"))
        step = tokens.TILE_SIZE_STEP if direction > 0 else -tokens.TILE_SIZE_STEP
        self.cfg["tile_size"] = tokens.clamp_tile_size(current + step)
        self.tile_delegate.clear_cache()
        self.tiles_view.reset()
        save_config(self.cfg)
        return "break"

    def _selected_rows(self, view) -> list[int]:
        if not view or not view.selectionModel():
            return []
        selection = view.selectionModel()
        rows = {idx.row() for idx in selection.selectedRows()}
        rows.update(idx.row() for idx in selection.selectedIndexes())
        return sorted(rows)

    def _selected_indexes(self, view=None) -> List[int]:
        if view is None:
            view = self.tiles_view if self._is_tile_view() else self.mods_table
        return [row + 1 for row in self._selected_rows(view)]

    def _has_mod_selection(self) -> bool:
        return bool(self._selected_rows(self.tiles_view if self._is_tile_view() else self.mods_table))

    def _update_mod_selection_actions(self) -> None:
        enabled = (not self.busy) and self._has_mod_selection()
        for widget in self.mod_selection_widgets:
            widget.setEnabled(enabled)

    def _on_mod_selection_changed(self) -> None:
        self._update_mod_selection_actions()
        self.selection_status.setText(f"{len(self._selected_rows(self._current_mod_view()))} selected")
        self._refresh_selected_detail()

    def _select_mod_names(self, selected_names: list[str] | None = None) -> None:
        names = set(selected_names or [])
        view = self.tiles_view if self._is_tile_view() else self.mods_table
        selection = view.selectionModel()
        if not selection:
            return
        selection.clearSelection()
        rows = [i for i, mod in enumerate(self.current_mods_shown) if mod.name in names]
        if not rows and self.current_mods_shown:
            rows = [0]
        for row in rows:
            idx = self.mods_model.index(row, 0)
            selection.select(idx, QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Rows)
            selection.setCurrentIndex(idx, QtCore.QItemSelectionModel.NoUpdate)
        self._update_mod_selection_actions()

    def _current_mod_view(self):
        return self.tiles_view if self._is_tile_view() else self.mods_table

    def _is_mod_drop_target(self, obj) -> bool:
        if not hasattr(self, "mods_table") or not hasattr(self, "tiles_view"):
            return False
        return obj in (self.mods_table.viewport(), self.tiles_view.viewport())

    def _mod_name_at_view_position(self, obj, pos: QtCore.QPoint) -> str:
        if not hasattr(self, "mods_model"):
            return ""
        view = self.tiles_view if obj is self.tiles_view.viewport() else self.mods_table
        index = view.indexAt(pos)
        if not index.isValid() or index.row() >= len(self.current_mods_shown):
            return ""
        return self.current_mods_shown[index.row()].name

    def _tile_label_at_position(self, pos: QtCore.QPoint) -> str:
        if not hasattr(self, "tiles_view"):
            return ""
        index = self.tiles_view.indexAt(pos)
        if not index.isValid():
            return ""
        option = QtWidgets.QStyleOptionViewItem()
        option.font = self.tiles_view.font()
        option.rect = self.tiles_view.visualRect(index)
        return self.tile_delegate._label_for_pos(option, index, pos)

    def _show_label_choices(self, names: tuple[str, ...], position: QtCore.QPoint) -> None:
        self._close_label_choices()
        menu = QtWidgets.QMenu(self)
        menu.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        for name in names:
            action = menu.addAction(self._icon("label_add"), name)
            action.setIconVisibleInMenu(True)
            action.triggered.connect(lambda _checked=False, label=name: self._apply_label_choice(menu, label))
        self._label_choices_menu = menu
        menu.destroyed.connect(lambda: self._forget_label_choices(menu))
        menu.popup(position)

    def _forget_label_choices(self, menu: QtWidgets.QMenu) -> None:
        if getattr(self, "_label_choices_menu", None) is menu:
            self._label_choices_menu = None

    def _apply_label_choice(self, menu: QtWidgets.QMenu, name: str) -> None:
        if getattr(self, "_label_choices_menu", None) is menu and not self.busy and self._is_mods_tab_active():
            self._toggle_label_filter(name)

    def _close_label_choices(self) -> None:
        menu = getattr(self, "_label_choices_menu", None)
        self._label_choices_menu = None
        if menu is not None:
            menu.close()

    def _refresh_selected_detail(self) -> None:
        rows = self._selected_rows(self._current_mod_view())
        if len(rows) == 1 and rows[0] < len(self.current_mods_shown):
            self._refresh_mod_detail(self.current_mods_shown[rows[0]])
        elif len(rows) > 1:
            self._refresh_multi_detail([self.current_mods_shown[i] for i in rows if i < len(self.current_mods_shown)])
        else:
            self._refresh_mod_detail(None)

    def _clear_detail(self) -> None:
        self._clear_layout(self.detail_layout)

    def _clear_layout(self, layout) -> None:
        clear_layout(layout)

    def _detail_row(self, label: str, value: str) -> None:
        self.detail_scroll.add_text_row(label, value)

    def _format_mod_created_date(self, mod: ModItem) -> str:
        record = self.current_mod_records.get(mod.name, {})
        for key in ("created_date", "created_at", "created"):
            value = record.get(key)
            if value:
                return str(value)
        try:
            return datetime.fromtimestamp(mod.src.stat().st_ctime).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return "-"

    def _dates_fit_on_one_row(self, last_managed: str, created: str, available_width: int | None = None) -> bool:
        return self.detail_scroll.dates_fit_on_one_row(last_managed, created, available_width)

    def _detail_dates_row(self, mod: ModItem) -> None:
        last_managed = self.current_mod_records.get(mod.name, {}).get("last_managed") or "-"
        created = self._format_mod_created_date(mod)
        self.detail_scroll.add_fields([("Last managed", last_managed), ("Created", created)])

    def _detail_path_row(self, label: str, path: Path) -> None:
        self.detail_scroll.add_row(detail_name_label(label), path_button(path, lambda target: select_in_explorer(target)), stretch_last=True)

    def _detail_label_row(self, values: tuple[str, ...]) -> None:
        buttons = []
        for value in values:
            buttons.append(text_button(value, f"Filter mods by {value}", lambda name=value: self._toggle_label_filter(name), icon_name="toggle"))
        self.detail_scroll.add_label_buttons(buttons)

    def _detail_favorite_button(self, mod: ModItem) -> QtWidgets.QPushButton:
        favorite = mod.name in self.current_mod_favorites
        text = "Remove from favorites" if favorite else "Add to favorites"
        button = text_button(
            "Favorite",
            text,
            lambda name=mod.name: self._toggle_favorite_name(name),
            icon_name="favorite_filled" if favorite else "favorite",
            accessible_name=text,
        )
        button.setCheckable(True)
        button.setChecked(favorite)
        return button

    def _detail_state_button(self, mod: ModItem) -> QtWidgets.QPushButton:
        action = "uninstall" if mod.installed else "install"
        index = self.current_mods_shown.index(mod) + 1 if mod in self.current_mods_shown else 1
        button = text_button(
            _sys_str(action),
            f"{action.capitalize()} this mod",
            lambda i=index: self._toggle_selected_indexes([i]),
            icon_name=action,
        )
        return button

    def _toggle_label_filter(self, label: str) -> None:
        if not label or label == "-":
            return
        current = self.label_filter_var.get()
        self.label_filter_var.set("" if current.lower() == label.lower() else label)
        self.label_filter_box.setCurrentText(self.label_filter_var.get())
        self.mod_page.set(1)
        self.refresh_mods()

    def _confirm_overwrite(self, mods: list) -> bool:
        """Ask before a copy install replaces files that are already in the game mods folder."""
        names = existing_targets(mods)
        if not names:
            return True
        question = OVERWRITE_QUESTION.format(message=overwrite_message(names))
        return prompts.ask_yes_no(self, OVERWRITE_TITLE, question)

    def _selected_mod_rows_for_state(self, installed: bool) -> list[int]:
        rows = self._selected_rows(self._current_mod_view())
        return [row + 1 for row in rows if row < len(self.current_mods_shown) and self.current_mods_shown[row].installed == installed]

    def _toggle_selected_indexes(self, indexes: list[int]) -> None:
        if not indexes:
            return
        selected = mods_by_indexes(self.current_mods_shown, indexes)
        if not self._confirm_overwrite([m for m in selected if not m.installed]):
            return
        names = [m.name for m in selected]

        def done(result):
            self._set_status(result.summary())
            self.refresh_mods(names)
            self.refresh_presets()

        self.errors.run(
            "Updating selected mods...",
            lambda: change_mods(selected, overwrite=True),
            done,
        )

    def _install_selected_mods(self) -> None:
        self._toggle_selected_indexes(self._selected_mod_rows_for_state(False))

    def _uninstall_selected_mods(self) -> None:
        self._toggle_selected_indexes(self._selected_mod_rows_for_state(True))

    def _refresh_multi_detail(self, mods: list) -> None:
        self._clear_detail()
        installed = sum(1 for mod in mods if mod.installed)
        not_installed = len(mods) - installed
        self.detail_scroll.add_heading(f"{len(mods)} mods selected", self.details_button.click)
        self._detail_row("Installed", str(installed))
        self._detail_row("Not installed", str(not_installed))
        install_button = QtWidgets.QPushButton(f"Install {not_installed}")
        install_button.setIcon(self._icon("install"))
        install_button.setToolTip("Install selected mods that are not installed")
        install_button.setEnabled(not_installed > 0)
        install_button.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        install_button.clicked.connect(self._install_selected_mods)
        uninstall_button = QtWidgets.QPushButton(f"Uninstall {installed}")
        uninstall_button.setIcon(self._icon("uninstall"))
        uninstall_button.setToolTip("Uninstall selected mods that are installed")
        uninstall_button.setEnabled(installed > 0)
        uninstall_button.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        uninstall_button.clicked.connect(self._uninstall_selected_mods)
        toggle_button = QtWidgets.QPushButton("Toggle selected")
        toggle_button.setIcon(self._icon("toggle"))
        toggle_button.setToolTip("Toggle all selected mods")
        toggle_button.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        toggle_button.clicked.connect(self._toggle_selected_mods)
        self.detail_scroll.add_actions([install_button, uninstall_button, toggle_button])

    def _detail_image(self, mod_name: str) -> None:
        img_path = mod_image_path(self.cfg, mod_name)
        if not img_path:
            return
        pixmap = QtGui.QPixmap(str(img_path))
        if pixmap.isNull():
            return
        image = DetailImageLabel(pixmap)
        self.detail_layout.addWidget(image)
        self.detail_scroll.rescale_images()

    def _detail_image_target_size(self, image: DetailImageLabel | None = None) -> QtCore.QSize:
        return self.detail_scroll.image_target_size(image)

    def _update_detail_image_size(self) -> None:
        if not hasattr(self, "detail_frame"):
            return
        self.detail_scroll.rescale_images()

    def _refresh_mod_detail(self, mod: ModItem | None) -> None:
        self._clear_detail()
        if mod is None:
            self.detail_scroll.add_heading("No mod selected", self.details_button.click)
            self.detail_scroll.add_text_row("Details", "Select a mod to see its information and available actions.")
            return
        self.detail_scroll.add_heading(mod.name, self.details_button.click)
        self.detail_scroll.add_flow_row([
            QtWidgets.QLabel("Installed" if mod.installed else "Not installed"),
            self._detail_favorite_button(mod), self._detail_state_button(mod),
        ])
        self._detail_label_row(label_names(self.current_mod_labels, mod.name))
        self._detail_dates_row(mod)
        if mod.files:
            self._detail_row("Grouped files", ", ".join(f.src.name for f in mod.files))
        self._detail_path_row("Source", mod.src)
        self._detail_path_row("Destination", mod.dest)
        self._detail_image(mod.name)
        self.detail_layout.addStretch(1)

    def _invalidate_mod_image(self, mod_name: str) -> None:
        self.tile_delegate.clear_cache(mod_name)
        for row, mod in enumerate(self.current_mods_shown):
            if mod.name == mod_name:
                index = self.mods_model.index(row, 0)
                self.mods_model.dataChanged.emit(index, index, [QtCore.Qt.DecorationRole, QtCore.Qt.DisplayRole])
                self.tiles_view.viewport().update(self.tiles_view.visualRect(index))
                break

    def refresh_all(self) -> None:
        self.refresh_mods()
        self.refresh_presets()
        self.refresh_broken()

    def refresh_mods(self, selected_names: List[str] | None = None) -> None:
        self._close_label_choices()
        page, label_filter, search, order = self._view_args()
        favorite_only = bool(self.favorite_filter_var.get())
        view_args = (self.cfg, page, label_filter, search, order)
        items, shown, page, pages, labels = (
            mods_view(*view_args, True) if favorite_only else mods_view(*view_args)
        )
        self.current_mod_items = items
        self.current_mod_names = sorted(labels.memberships if isinstance(labels, ResolvedLabels) else [mod.name for mod in items], key=str.casefold)
        self.current_mods_shown = shown
        self.current_mod_labels = labels
        self.current_mod_records = mods_records()
        self.current_mod_favorites = load_favorites(self.cfg)
        self.mod_page.set(page)
        list_blocker = QtCore.QSignalBlocker(self.mods_table.selectionModel())
        try:
            self.mods_model.set_data(shown, labels, self.current_mod_records, self.current_mod_favorites)
            self.favorite_delegate.set_favorites(self.current_mod_favorites)
            self.tile_delegate.set_favorites(self.current_mod_favorites)
            self.page_control.set_page(page, pages)
            label_values = sorted(labels.state.definitions if isinstance(labels, ResolvedLabels) else {v for v in labels.values() if v}, key=str.casefold)
            for box, values, text in ((self.search_box, self.current_mod_names, search), (self.label_filter_box, label_values, label_filter)):
                with QtCore.QSignalBlocker(box), QtCore.QSignalBlocker(box.lineEdit()):
                    box.clear()
                    box.addItems(values)
                    for index, value in enumerate(values):
                        box.setItemData(index, value, QtCore.Qt.ToolTipRole)
                    box.setCurrentText(text)
            manual_values = [name for name in label_values if not isinstance(labels, ResolvedLabels) or labels.state.definitions[name].mode != AUTOMATIC]
            self.label_edit_model.setStringList(manual_values)
            self.favorite_filter_button.setChecked(favorite_only)
            self._select_mod_names(selected_names)
        finally:
            del list_blocker
        self._show_mod_view()
        self._sync_workspace()
        self.selection_status.setText(f"{len(self._selected_rows(self._current_mod_view()))} selected")

    def refresh_presets(self) -> None:
        selected_names = [
            self.presets_model.keys[row]
            for row in self._selected_rows(self.presets_table)
            if row < len(self.presets_model.keys)
        ]
        presets, keys, page_keys, page, pages = presets_view(self.cfg, self.preset_page.get(), self._preset_order_mode())
        installed = {mod.name for mod in list_installed_mods(self.cfg)}
        self.preset_page.set(page)
        selection = self.presets_table.selectionModel()
        blocker = QtCore.QSignalBlocker(selection) if selection else None
        self.presets_table.setUpdatesEnabled(False)
        try:
            self.presets_model.set_data(presets, page_keys, presets_records(), installed)
            self.preset_page_control.set_page(page, pages)
            if selection:
                selection.clearSelection()
                for name in selected_names:
                    if name in page_keys:
                        row = page_keys.index(name)
                        idx = self.presets_model.index(row, 0)
                        selection.select(idx, QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Rows)
                        self.presets_table.setCurrentIndex(idx)
        finally:
            self.presets_table.setUpdatesEnabled(True)
            if blocker is not None:
                del blocker
        self.presets_stack.setCurrentWidget(self.presets_table if page_keys else self.presets_empty)

    def refresh_broken(self) -> None:
        self.current_broken = list_broken_links(self.cfg)
        self.broken_model.set_data(self.current_broken)
        self.broken_stack.setCurrentWidget(self.broken_table if self.current_broken else self.broken_empty)

    def _mods_search(self) -> None:
        self.search_var.set(self.search_box.currentText().strip())
        self.label_filter_var.set(self.label_filter_box.currentText().strip())
        self.mod_page.set(1)
        self.refresh_mods()

    def _toggle_favorite_filter(self) -> None:
        self.favorite_filter_var.set(self.favorite_filter_button.isChecked())
        self.mod_page.set(1)
        self.refresh_mods()

    def _set_favorite_names(self, names: list[str], favorite: bool) -> None:
        if not names:
            return
        message = (
            add_favorites_to_mods(self.cfg, names)
            if favorite
            else remove_favorites_from_mods(self.cfg, names)
        )
        self._set_status(message)
        self.refresh_mods(names)

    def _toggle_favorite_name(self, name: str) -> None:
        self._set_favorite_names([name], name not in self.current_mod_favorites)

    def _toggle_favorite_selected(self) -> None:
        names = self._selected_mod_names()
        favorite = not all(name in self.current_mod_favorites for name in names)
        self._set_favorite_names(names, favorite)

    def _mods_clear(self) -> None:
        self.search_var.set("")
        self.label_filter_var.set("")
        self.search_box.setCurrentText("")
        self.label_filter_box.setCurrentText("")
        self.favorite_filter_var.set(False)
        self.favorite_filter_button.setChecked(False)
        self.mod_page.set(1)
        self.refresh_mods()

    def _change_mod_page(self, delta: int) -> None:
        self.mod_page.set(max(1, int(self.mod_page.get()) + delta))
        self.refresh_mods()

    def _set_mod_page(self, page: int) -> None:
        self.mod_page.set(page)
        self.refresh_mods()

    def _change_preset_page(self, delta: int) -> None:
        self.preset_page.set(max(1, int(self.preset_page.get()) + delta))
        self.refresh_presets()

    def _set_preset_page(self, page: int) -> None:
        self.preset_page.set(page)
        self.refresh_presets()

    def _install_page(self) -> None:
        page, label_filter, search, order = self._view_args()
        if not self._confirm_overwrite([m for m in self.current_mods_shown if not m.installed]):
            return

        def done(result):
            target_page, operation = result
            total = len(operation.items)
            self._set_status(f"Installed {total - operation.errors}/{total} on page {target_page}. Errors: {operation.errors}.")
            self.refresh_mods()
            self.refresh_presets()

        favorite_only = bool(self.favorite_filter_var.get())
        view_args = (self.cfg, page, label_filter, search, order, favorite_only, True)
        self.errors.run("Installing mods...", lambda: change_mods_page(*view_args), done)

    def _uninstall_page(self) -> None:
        page, label_filter, search, order = self._view_args()

        def done(result):
            target_page, operation = result
            count = sum(item.success for item in operation.items)
            self._set_status(f"Uninstalled {count} on page {target_page}. Errors: {operation.errors}.")
            self.refresh_mods()
            self.refresh_presets()

        view_args = (self.cfg, page, label_filter, search, order)
        favorite_only = bool(self.favorite_filter_var.get())
        self.errors.run(
            "Uninstalling mods...",
            lambda: change_mods_page(*view_args, favorite_only, action="uninstall"),
            done,
        )

    def _toggle_selected_mods(self) -> None:
        self._toggle_selected_indexes(self._selected_indexes())

    def _selected_mod_names(self) -> list[str]:
        return [self.current_mods_shown[i - 1].name for i in self._selected_indexes() if 1 <= i <= len(self.current_mods_shown)]

    def _add_label_selected(self) -> None:
        label = self.label_edit.text().strip()
        self.label_edit_var.set(label)
        if not label:
            prompts.show_error(self, "Label", "Enter label.")
            return
        self._change_label_selected(label)

    def _remove_label_selected(self) -> None:
        label = self.label_edit.text().strip()
        self.label_edit_var.set(label)
        self._change_label_selected(label, remove=True)

    def _change_label_selected(self, label: str, *, remove: bool = False) -> None:
        if isinstance(self.current_mod_labels, ResolvedLabels):
            state = self.current_mod_labels.state
            canonical = state.canonical_name(label)
            if canonical in state.definitions and state.definitions[canonical].mode == AUTOMATIC:
                self._navigate("labels")
                self.labels_controller._rebuild(canonical)
                return
        targets = self._selected_mod_names()

        def done(message):
            self._set_status(message)
            self.refresh_mods(targets)

        action = remove_label_from_mods if remove else add_label_to_mods
        self._run_action("Removing label..." if remove else "Adding label...", lambda: action(label, targets), done)

    def _save_preset(self) -> None:
        name = self.preset_name.text().strip()
        if not name:
            prompts.show_error(self, "Preset", "Enter preset name.")
            return

        def done(result):
            ok, message = result
            self._set_status(message)
            if ok:
                self.refresh_presets()

        self._run_action("Saving preset...", lambda: save_preset_from_installed(self.cfg, name), done)

    def _toggle_selected_presets(self) -> None:
        names = self._selected_preset_names()
        installed = {m.name for m in list_installed_mods(self.cfg)}
        if is_copy_install(self.cfg) and not self._confirm_overwrite(preset_mods_to_install(self.cfg, names)[0]):
            return

        def done(result):
            message, _operation = result
            self._set_status(message)
            self.refresh_mods()
            self.refresh_presets()

        self.errors.run(
            "Toggling presets...",
            lambda: toggle_presets_result(self.cfg, names, installed, True),
            done,
            preset_names=preset_install_names(names, installed),
        )

    def _toggle_preset_at_index(self, index) -> None:
        if index.isValid() and self.presets_table.selectionModel():
            selection = self.presets_table.selectionModel()
            selection.clearSelection()
            selection.select(index, QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Rows)
            self.presets_table.setCurrentIndex(index)
        self._toggle_selected_presets()

    def _delete_selected_presets(self) -> None:
        names = self._selected_preset_names()

        def done(result):
            removed, missing = result
            message = f"Deleted: {removed}. Missing: {', '.join(missing) if missing else 'none'}"
            self._set_status(message)
            self.refresh_presets()

        self._run_action("Deleting presets...", lambda: delete_presets_by_names(names), done)

    def _selected_preset_names(self) -> list[str]:
        return [
            self.presets_model.keys[row]
            for row in self._selected_rows(self.presets_table)
            if row < len(self.presets_model.keys)
        ]

    def _choose_color(self, key: str) -> None:
        self.settings.choose_color(key)

    def _settings_accent_color(self) -> QtGui.QColor:
        return self.settings.color("gui_accent_color")

    def _settings_text_color(self) -> QtGui.QColor:
        return self.settings.color("gui_text_color")

    def _update_theme_preview(self) -> None:
        self.settings.update_preview()

    def _save_settings(self) -> None:
        self.settings.save()

    def apply_saved_settings(self, new_cfg: dict, theme_changed: bool) -> None:
        self.cfg = self.context.replace_config(new_cfg)
        self.tile_delegate.cfg = new_cfg
        self._apply_state_column_width()
        self.mod_view_mode.set(normalize_view_mode(self.cfg.get("mod_view_mode")))
        self._show_mod_view()
        if theme_changed:
            self._refresh_theme()
        self._set_status(SETTINGS_SAVED)
        self.refresh_all()
        self.settings.reset()

    def _remove_selected_broken(self) -> None:
        rows = self._selected_rows(self.broken_table)
        selected = [self.current_broken[i] for i in rows if i < len(self.current_broken)]

        self._remove_broken(selected)

    def _remove_all_broken(self) -> None:
        self._remove_broken(list(self.current_broken))

    def _remove_broken(self, mods: list[ModItem]) -> None:
        def done(result):
            count = sum(item.success for item in result.items)
            self._set_status(f"Removed broken links: {count}. Errors: {result.errors}.")
            self.refresh_broken()

        self.errors.run(
            "Removing broken links...",
            lambda: OperationResult(tuple(deactivate_mod_result(mod) for mod in mods)),
            done,
        )

    def dragEnterEvent(self, event) -> None:
        if self._is_mods_tab_active() and event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self._handle_mods_drop(paths)

    def _handle_mods_drop(self, paths, x: int = 0, y: int = 0, target_mod_name: str = "") -> None:
        if not self._is_mods_tab_active():
            release = getattr(paths, "close", None)
            if release:
                release()
            return
        if getattr(paths, "temporary_root", None) is None:
            paths = [Path(path) for path in paths]
        self._import_paths(paths, image_target_name=target_mod_name)

    def _handle_paste(self, event=None) -> None:
        if self.busy:
            return
        if self.archive_import.dialog is not None and self.archive_import.dialog.isVisible():
            self.archive_import.paste()
            return
        if not self._is_mods_tab_active():
            return
        paths = read_clipboard_paths()
        if paths:
            self._handle_clipboard_paths(paths)
            return
        image = read_clipboard_image()
        if image:
            self.previews.paste_image(image)

    def _handle_clipboard_paths(self, paths: List[Path]) -> None:
        if paths and all(is_image_file(path) for path in paths):
            self.previews.paste_paths(paths)
            return
        self._import_paths(paths, image_target_name=self._single_selected_mod_name())

    def _single_selected_mod_name(self) -> str:
        names = self._selected_mod_names()
        return names[0] if len(names) == 1 else ""

    def _import_paths(self, paths: List[Path], image_target_name: str = "") -> None:
        if self.archive_import.handle_paths(paths, image_target_name):
            return
        self._import_regular_paths(paths, image_target_name)

    def _import_regular_paths(self, paths: List[Path], image_target_name: str = "") -> None:
        if not ensure_paths(self.cfg):
            return
        existing = {m.name for m in self.current_mod_items}
        mod_paths = [path for path in paths if is_mod_file(path, self.cfg) and not ignored_file(path, self.cfg)]
        tasks = regular_import_tasks(self.cfg, mod_paths, existing, lambda name: prompts.choose_import_conflict(self, name))
        image_mods = []
        dropped_mods = {path.name for path in mod_paths}
        imported_names = {}
        for kind, source, name, _replace in tasks:
            if kind == "group":
                for member, _relative in source.files:
                    imported_names[member.name] = source.name
            else:
                imported_names[source.name] = name or source.name
        for path in paths:
            if is_image_file(path):
                if path.stem in dropped_mods:
                    mod_name = imported_names.get(path.stem, "")
                else:
                    mod_name = image_target_name or self._choose_mod_for_image(path.stem)
                if mod_name:
                    tasks.append(("image", path, mod_name, False))
                    image_mods.append(mod_name)
        if not tasks:
            release = getattr(paths, "close", None)
            if release:
                release()
            return

        def done(result):
            imported, skipped = result
            message = f"Imported: {len(imported)}. Skipped: {len(skipped)}."
            self._set_status(message)
            for mod_name in image_mods:
                self._invalidate_mod_image(mod_name)
            if image_mods:
                self.refresh_mods(image_mods)
            else:
                self.refresh_mods()

        cfg = dict(self.cfg)

        def worker():
            try:
                return _run_import_batch(cfg, tasks)
            finally:
                release = getattr(paths, "close", None)
                if release:
                    release()

        self._run_action("Importing...", worker, done)

    def _import_mod_files(self) -> None:
        files = prompts.choose_files(self, "Import mod files")
        self._import_paths([Path(p) for p in files])

    def _import_mod_folder(self) -> None:
        folder = prompts.choose_directory(self, "Import mod folder")
        if folder:
            self._import_paths([Path(folder)])

    def _choose_mod_for_image(self, default_name: str = "") -> str:
        names = [m.name for m in self.current_mod_items]
        if not names:
            return ""
        current = names.index(default_name) if default_name in names else 0
        name, ok = prompts.choose_item(self, "Mod image", "Mod", names, current)
        return name if ok else ""

    def _set_mod_image(self) -> None:
        self.previews.choose()


def _app_icon() -> QtGui.QIcon | None:
    icon_path = Path(__file__).resolve().parent.parent.parent / "assets" / "icon.png"
    if not icon_path.exists():
        return None
    return QtGui.QIcon(str(icon_path))


def start() -> int:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    icon = _app_icon()
    if icon is not None:
        app.setWindowIcon(icon)
    window = ModManagerGui()
    if icon is not None:
        window.setWindowIcon(icon)
    window.show()
    return app.exec()
