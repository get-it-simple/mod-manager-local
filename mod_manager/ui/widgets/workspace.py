from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from app_paths import APP_NAME, APP_VERSION
from .. import icons
from ..theme import tokens
from .buttons import text_button
from .section import muted_label, page_title_label
from .select import select_box
from .style_utils import apply_margins, set_variant, repolish

NAVIGATION = (
    ("library", "Library", "list"),
    ("presets", "Presets", "presets"),
    ("games", "Game profiles", "game"),
    ("cleanup", "Cleanup", "broken"),
    ("settings", "Settings", "settings"),
)
PROFILE_PAGES = ("library", "presets", "cleanup")


class WorkspacePage(QtWidgets.QWidget):
    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        self.outer = apply_margins(QtWidgets.QVBoxLayout(self), tokens.PAGE_MARGIN, tokens.SPACE_2XL)
        self.header = apply_margins(QtWidgets.QHBoxLayout())
        headings = apply_margins(QtWidgets.QVBoxLayout(), spacing=tokens.SPACE_SM)
        self.title = page_title_label(title)
        self.subtitle = muted_label(subtitle)
        self.subtitle.setWordWrap(True)
        self.subtitle.setVisible(bool(subtitle))
        headings.addWidget(self.title)
        headings.addWidget(self.subtitle)
        self.header.addLayout(headings, 1)
        self.outer.addLayout(self.header)
        self.body = apply_margins(QtWidgets.QVBoxLayout(), spacing=tokens.SPACE_2XL)
        self.outer.addLayout(self.body, 1)

    def set_subtitle(self, text: str) -> None:
        self.subtitle.setText(text)
        self.subtitle.setVisible(bool(text))


class EmptyState(QtWidgets.QWidget):
    def __init__(self, title: str, description: str, parent=None):
        super().__init__(parent)
        layout = apply_margins(QtWidgets.QVBoxLayout(self), tokens.DETAIL_MARGIN)
        layout.addStretch()
        for text, heading in ((title, True), (description, False)):
            label = QtWidgets.QLabel(text)
            label.setWordWrap(True)
            label.setAlignment(QtCore.Qt.AlignCenter)
            set_variant(label, "heading" if heading else "muted")
            layout.addWidget(label)
        layout.addStretch()
        self.setMinimumHeight(tokens.EMPTY_STATE_MIN_HEIGHT)


class Workspace(QtWidgets.QWidget):
    pageRequested = QtCore.Signal(str)
    profileRequested = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        set_variant(self, "workspace")
        self.pages: dict[str, WorkspacePage] = {}
        self.sidebar = set_variant(QtWidgets.QFrame(), "sidebar")
        self.sidebar_layout = apply_margins(QtWidgets.QVBoxLayout(self.sidebar), tokens.SPACE_LG, tokens.SPACE_LG)
        self.brand = QtWidgets.QLabel(APP_NAME)
        set_variant(self.brand, "heading")
        self.sidebar_layout.addWidget(self.brand)
        self.game_label = muted_label("Game")
        self.sidebar_layout.addWidget(self.game_label)
        self.profile_box = select_box()
        self.profile_box.setAccessibleName("Active game profile")
        self.profile_box.setToolTip("Switch the active game profile")
        self.profile_box.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.profile_box.setMinimumContentsLength(0)
        self.profile_box.activated.connect(self._select_profile)
        self.sidebar_layout.addWidget(self.profile_box)
        self.game_button = text_button("Game", "Manage and switch game profiles", lambda: self.pageRequested.emit("games"), icon_name="game")
        self.sidebar_layout.addWidget(self.game_button)
        self.navigation: dict[str, QtWidgets.QPushButton] = {}
        for key, title, icon in NAVIGATION:
            if key == "settings":
                self.sidebar_layout.addStretch()
            button = text_button(title, title, lambda page=key: self.pageRequested.emit(page), icon_name=icon)
            button.setCheckable(True)
            button.setMinimumHeight(tokens.NAVIGATION_HEIGHT)
            button.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            set_variant(button, "navigation")
            self.navigation[key] = button
            self.sidebar_layout.addWidget(button)
        self.version = muted_label(f"v{APP_VERSION}")
        self.sidebar_layout.addWidget(self.version)
        self.stack = QtWidgets.QStackedWidget()
        self.stack.setMinimumWidth(0)
        layout = apply_margins(QtWidgets.QHBoxLayout(self), spacing=0)
        layout.addWidget(self.sidebar)
        layout.addWidget(self.stack, 1)
        self.compact = None
        self._update_compact()

    def add_page(self, key: str, page: WorkspacePage) -> None:
        self.pages[key] = page
        self.stack.addWidget(page)

    def show_page(self, key: str) -> None:
        self.stack.setCurrentWidget(self.pages[key])
        for name, button in self.navigation.items():
            button.setChecked(name == key)

    @property
    def current_page(self) -> str:
        return next((key for key, page in self.pages.items() if page is self.stack.currentWidget()), "")

    def set_profiles(self, profiles: list[dict], active_id: str, busy: bool) -> None:
        with QtCore.QSignalBlocker(self.profile_box):
            self.profile_box.clear()
            for profile in profiles:
                self.profile_box.addItem(profile.get("name", "Game"), profile.get("id", ""))
            self.profile_box.setCurrentIndex(self.profile_box.findData(active_id))
        self.profile_box.setToolTip(self.profile_box.currentText() or "Choose a game profile")
        self.profile_box.setEnabled(bool(profiles) and not busy)
        self.game_button.setEnabled(not busy)
        for key, button in self.navigation.items():
            button.setEnabled(not busy and (bool(active_id) or key not in PROFILE_PAGES))

    def refresh_icons(self) -> None:
        for button in (*self.navigation.values(), self.game_button):
            button.setIcon(icons.standard_icon(button.property("iconName")))

    def _select_profile(self, index: int) -> None:
        profile_id = self.profile_box.itemData(index)
        if profile_id:
            self.profileRequested.emit(profile_id)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_compact()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.FontChange and hasattr(self, "navigation"):
            self._update_compact()

    def _update_compact(self) -> None:
        label_width = max(self.fontMetrics().horizontalAdvance(title) for _key, title, _icon in NAVIGATION)
        required_width = label_width + tokens.ICON_SIZE + tokens.BUTTON_PADDING[1] * 2 + tokens.SPACE_LG * 2
        compact = self.width() < tokens.SIDEBAR_BREAKPOINT or required_width > tokens.SIDEBAR_WIDTH
        if compact == self.compact:
            return
        self.compact = compact
        self.sidebar.setFixedWidth(tokens.SIDEBAR_COMPACT_WIDTH if compact else tokens.SIDEBAR_WIDTH)
        for widget in (self.brand, self.game_label, self.profile_box, self.version):
            widget.setVisible(not compact)
        self.game_button.setVisible(compact)
        self.game_button.setText("")
        for key, title, _icon in NAVIGATION:
            self.navigation[key].setText("" if compact else title)
            self.navigation[key].setProperty("compact", compact)
            repolish(self.navigation[key])
