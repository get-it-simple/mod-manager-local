from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ...i18n import t
from .. import icons
from ..theme import tokens
from .buttons import icon_button, text_button
from .style_utils import apply_margins


class FilterInput(QtWidgets.QWidget):
    def __init__(self, search_box, label_box, window):
        super().__init__(window)
        self.owner = window
        self.boxes = {"search": search_box, "label": label_box}
        self.active_kind = ""
        self.progress = 0.0
        self._opening = False
        self._transitioning = False
        self.buttons_image = QtGui.QPixmap()
        self.editor_image = QtGui.QPixmap()
        self.leading_actions = {}
        self.setMinimumWidth(tokens.SEARCH_MIN_WIDTH)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self.stack = QtWidgets.QStackedLayout(self)
        self.stack.setContentsMargins(0, 0, 0, 0)
        self.launcher = QtWidgets.QWidget(self)
        layout = apply_margins(QtWidgets.QHBoxLayout(self.launcher), spacing=tokens.SPACE_SM)
        self.search_button = text_button(t("search"), search_box.toolTip(), lambda: self.open("search"), icon_name="search")
        self.label_button = text_button(t("label"), label_box.toolTip(), lambda: self.open("label"), icon_name="label")
        layout.addWidget(self.search_button)
        layout.addWidget(self.label_button)
        layout.addStretch()
        self.stack.addWidget(self.launcher)
        self.editor = QtWidgets.QWidget(self)
        self.editor_layout = apply_margins(QtWidgets.QHBoxLayout(self.editor), spacing=tokens.SPACE_SM)
        self.editors = QtWidgets.QStackedWidget(self.editor)
        for kind, box in self.boxes.items():
            box.setMinimumWidth(0)
            self.leading_actions[kind] = box.lineEdit().addAction(icons.standard_icon(kind), QtWidgets.QLineEdit.ActionPosition.LeadingPosition)
            self.editors.addWidget(box)
            box.installEventFilter(self)
            box.lineEdit().installEventFilter(self)
        self.editor_layout.addWidget(self.editors, 1)
        self.close_button = icon_button("remove", t("close_filter"), self.collapse, self.editor)
        self.close_button.installEventFilter(self)
        self.editor_layout.addWidget(self.close_button)
        self.stack.addWidget(self.editor)
        self.cover = FilterTransition(self)
        self.cover.hide()
        self.stack.setCurrentWidget(self.launcher)

    def open(self, kind: str) -> None:
        if self.owner.busy:
            return
        if self.active_kind == kind and not self._transitioning:
            self._focus_editor()
            return
        self.owner.motion.stop(self, "filter-input")
        self.buttons_image = self.launcher.grab()
        self.active_kind = kind
        self.editors.setCurrentWidget(self.boxes[kind])
        self.stack.setCurrentWidget(self.editor)
        self.editor_layout.activate()
        self.editor_image = self.editor.grab()
        self._animate(True)

    def collapse(self) -> None:
        if not self.active_kind:
            return
        box = self.boxes[self.active_kind]
        box.hidePopup()
        box.completer().popup().hide()
        self.owner.motion.stop(self, "filter-input")
        self.editor_image = self.editor.grab()
        self._animate(False)

    def _animate(self, opening: bool) -> None:
        start = self.progress if self._transitioning else (0.0 if opening else 1.0)
        self._opening = opening
        self._transitioning = True
        self.cover.setGeometry(self.rect())
        self.cover.show()
        self.cover.raise_()
        duration = tokens.FILTER_BUTTON_FADE_MS + tokens.FILTER_REVEAL_MS + tokens.FILTER_TEXT_FADE_MS
        animation = self.owner.motion.animate(self, "filter-input", start, 1.0 if opening else 0.0,
                                              self._set_progress, max(1, round(duration * abs((1.0 if opening else 0.0) - start))), self._settle)
        if animation is not None:
            animation.setEasingCurve(QtCore.QEasingCurve.Type.InOutCubic)

    def _set_progress(self, value: float) -> None:
        self.progress = value
        self.cover.update()

    def _settle(self) -> None:
        self._transitioning = False
        self.cover.hide()
        if self._opening:
            self._focus_editor()
        else:
            kind = self.active_kind
            self.active_kind = ""
            self.stack.setCurrentWidget(self.launcher)
            (self.search_button if kind == "search" else self.label_button).setFocus()

    def _focus_editor(self) -> None:
        edit = self.boxes[self.active_kind].lineEdit()
        edit.setFocus(QtCore.Qt.FocusReason.ShortcutFocusReason)
        edit.selectAll()

    def eventFilter(self, obj, event):
        if isinstance(event, QtGui.QKeyEvent) and event.type() in (QtCore.QEvent.Type.ShortcutOverride, QtCore.QEvent.Type.KeyPress) and event.key() == QtCore.Qt.Key.Key_Escape:
            box = self.boxes.get(self.active_kind)
            if box is not None and box.completer().popup().isVisible():
                return False
            event.accept()
            if event.type() == QtCore.QEvent.Type.KeyPress:
                self.collapse()
            return True
        return False

    def resizeEvent(self, event) -> None:
        self.cover.setGeometry(self.rect())
        super().resizeEvent(event)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.Type.PaletteChange:
            for kind, action in getattr(self, "leading_actions", {}).items():
                action.setIcon(icons.standard_icon(kind))


class FilterTransition(QtWidgets.QWidget):
    def __init__(self, parent: FilterInput):
        super().__init__(parent)
        self.control = parent
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)

    def paintEvent(self, event) -> None:
        control = self.control
        palette = control.owner.theme.palette
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QtGui.QColor(palette.bg))
        total = tokens.FILTER_BUTTON_FADE_MS + tokens.FILTER_REVEAL_MS + tokens.FILTER_TEXT_FADE_MS
        elapsed = control.progress * total
        if elapsed < tokens.FILTER_BUTTON_FADE_MS:
            painter.setOpacity(1.0 - elapsed / tokens.FILTER_BUTTON_FADE_MS)
            painter.drawPixmap(self.rect(), control.buttons_image)
        else:
            expand = tokens.clamp((elapsed - tokens.FILTER_BUTTON_FADE_MS) / tokens.FILTER_REVEAL_MS, 0.0, 1.0)
            text = tokens.clamp((elapsed - tokens.FILTER_BUTTON_FADE_MS - tokens.FILTER_REVEAL_MS) / tokens.FILTER_TEXT_FADE_MS, 0.0, 1.0)
            painter.setOpacity(1.0 - text)
            target = QtCore.QRectF(control.editors.geometry())
            height = target.height()
            width = height + (target.width() - height) * expand
            bounds = QtCore.QRectF(target.left(), target.top(), width, height)
            painter.setPen(QtGui.QPen(QtGui.QColor(palette.field_border), tokens.BORDER_WIDTH))
            painter.setBrush(QtGui.QColor(palette.field))
            painter.drawRoundedRect(bounds, height / 2, height / 2)
            size = tokens.ICON_SIZE
            icon_rect = QtCore.QRect(round(bounds.left() + (height - size) / 2), round(bounds.center().y() - size / 2), size, size)
            icons.standard_icon(control.active_kind).paint(painter, icon_rect)
            if text > 0:
                painter.setOpacity(text)
                painter.drawPixmap(self.rect(), control.editor_image)
        painter.end()
