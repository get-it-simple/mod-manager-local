from __future__ import annotations

from ...i18n import t

from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Callable

from PySide6 import QtCore, QtGui, QtWidgets

from ..theme import tokens
from .style_utils import LINK, apply_margins, clear_layout, fixed_size_policy, set_variant
from .buttons import icon_button
from .flow_layout import FlowLayout


class DetailImageLabel(QtWidgets.QLabel):
    def __init__(self, pixmap: QtGui.QPixmap, parent=None):
        super().__init__(parent)
        self._source_pixmap = pixmap
        self._target_size: QtCore.QSize | None = None
        self.setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignTop)
        self.setMinimumWidth(0)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.update_scaled_pixmap()

    def set_source_pixmap(self, pixmap: QtGui.QPixmap) -> None:
        self._source_pixmap = pixmap
        self._target_size = None
        self.update_scaled_pixmap()

    def update_scaled_pixmap(self, size: QtCore.QSize | None = None) -> None:
        if self._source_pixmap.isNull():
            return
        target = size or self._target_size or QtCore.QSize(self.width(), self._source_pixmap.height())
        target = QtCore.QSize(max(1, target.width()), max(1, target.height()))
        if target == self._target_size:
            return
        self._target_size = target
        ratio = self._source_pixmap.devicePixelRatio()
        pixel_size = self._source_pixmap.size().scaled(target * ratio, QtCore.Qt.KeepAspectRatio)
        pixel_size = QtCore.QSize(max(1, pixel_size.width()), max(1, pixel_size.height()))
        scaled = self._source_pixmap.scaled(
            pixel_size,
            QtCore.Qt.IgnoreAspectRatio,
            QtCore.Qt.SmoothTransformation,
        )
        self.setPixmap(scaled)
        self.setFixedHeight(max(1, round(scaled.deviceIndependentSize().height())))


def detail_name_label(text: str, parent=None) -> QtWidgets.QLabel:
    label = QtWidgets.QLabel(text, parent)
    set_variant(label, "muted")
    label.setMinimumWidth(tokens.DETAIL_LABEL_MIN_WIDTH)
    label.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)
    return label


def display_path(path: Path | str) -> str:
    full = str(path)
    windows = "\\" in full or (len(full) > 1 and full[1] == ":")
    parsed = PureWindowsPath(full) if windows else PurePosixPath(full)
    parts = parsed.parts[1:] if parsed.anchor else parsed.parts
    visible_parts = tokens.PATH_VISIBLE_DIRECTORIES + 1
    if len(parts) > visible_parts:
        separator = "\\" if windows else "/"
        full = "…" + separator + separator.join(parts[-visible_parts:])
    if len(full) > tokens.PATH_MAX_CHARS:
        first = tokens.PATH_MAX_CHARS // 2
        last = tokens.PATH_MAX_CHARS - first - 1
        full = full[:first] + "…" + full[-last:]
    return full


class PathButton(QtWidgets.QPushButton):
    def __init__(self, path: Path, on_click: Callable, parent=None):
        self._display_path = display_path(path)
        super().__init__(self._display_path, parent)
        set_variant(self, LINK)
        self.setFlat(True)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setMinimumWidth(0)
        self.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        self.setToolTip(str(path))
        self.setAccessibleName(str(path))
        self.clicked.connect(lambda _checked=False, target=Path(path): on_click(target))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_text()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() in (QtCore.QEvent.FontChange, QtCore.QEvent.StyleChange):
            self._update_text()

    def _update_text(self) -> None:
        option = QtWidgets.QStyleOptionButton()
        self.initStyleOption(option)
        content = self.style().subElementRect(QtWidgets.QStyle.SE_PushButtonContents, option, self)
        self.setText(self.fontMetrics().elidedText(self._display_path, QtCore.Qt.ElideMiddle, max(0, content.width())))


def path_button(path: Path, on_click: Callable, parent=None) -> QtWidgets.QPushButton:
    return PathButton(path, on_click, parent)


def action_button(text: str, icon: QtGui.QIcon, tooltip: str, on_click: Callable, parent=None) -> QtWidgets.QPushButton:
    button = QtWidgets.QPushButton(text, parent)
    button.setIcon(icon)
    button.setToolTip(tooltip)
    button.clicked.connect(lambda _checked=False: on_click())
    return fixed_size_policy(button)


class DetailPanel(QtWidgets.QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.frame = QtWidgets.QWidget()
        self.frame.setAutoFillBackground(True)
        set_variant(self.frame, "panel")
        self.layout = apply_margins(
            QtWidgets.QVBoxLayout(self.frame),
            margins=tokens.DETAIL_MARGIN,
            spacing=tokens.SPACE_SM,
        )
        self.layout.setAlignment(QtCore.Qt.AlignTop)
        self.layout.setSizeConstraint(QtWidgets.QLayout.SetMinimumSize)
        self.setWidgetResizable(True)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setWidget(self.frame)
        self._rescale_timer = QtCore.QTimer(self)
        self._rescale_timer.setSingleShot(True)
        self._rescale_timer.timeout.connect(self.rescale_images)
        self.frame.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self.frame and event.type() in (
            QtCore.QEvent.LayoutRequest,
            QtCore.QEvent.FontChange,
            QtCore.QEvent.StyleChange,
            QtCore.QEvent.Show,
        ):
            self._schedule_rescale()
        return super().eventFilter(obj, event)

    def viewportEvent(self, event):
        result = super().viewportEvent(event)
        if event.type() == QtCore.QEvent.Resize and hasattr(self, "_rescale_timer"):
            self._schedule_rescale()
        return result

    def _schedule_rescale(self) -> None:
        if not self._rescale_timer.isActive():
            self._rescale_timer.start(tokens.IMMEDIATE_MS)

    def clear(self) -> None:
        clear_layout(self.layout)

    def add_widget(self, widget: QtWidgets.QWidget) -> QtWidgets.QWidget:
        self.layout.addWidget(widget)
        return widget

    def add_heading(self, title: str, on_close: Callable | None = None) -> None:
        label = QtWidgets.QLabel(title)
        label.setWordWrap(True)
        label.setMinimumWidth(0)
        policy = label.sizePolicy()
        policy.setHorizontalPolicy(QtWidgets.QSizePolicy.Ignored)
        label.setSizePolicy(policy)
        set_variant(label, "heading")
        font = label.font()
        font.setPointSize(font.pointSize() + tokens.DETAIL_TITLE_FONT_STEP)
        font.setBold(True)
        label.setFont(font)
        if on_close is None:
            self.add_widget(label)
        else:
            self.add_row(label, icon_button("remove", t('hide_details'), on_close))

    def add_actions(self, buttons: list[QtWidgets.QPushButton]) -> None:
        self.add_flow_row(buttons)

    def add_flow_row(self, widgets: list[QtWidgets.QWidget]) -> QtWidgets.QWidget:
        host = QtWidgets.QWidget()
        layout = FlowLayout(host, constrain_items=True)
        layout.setSpacing(tokens.SPACE_SM)
        for widget in widgets:
            widget.setMinimumWidth(0)
            layout.addWidget(widget)
        host.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        return self.add_widget(host)

    def add_label_buttons(self, buttons: list[QtWidgets.QPushButton]) -> None:
        if not buttons:
            self.add_text_row(t('labels'), "-")
            return
        for button in buttons:
            button.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        self.add_flow_row([detail_name_label(t('labels')), *buttons])

    def add_fields(self, fields: list[tuple[str, str]]) -> None:
        widgets = []
        for title, value in fields:
            host = QtWidgets.QWidget()
            row = apply_margins(QtWidgets.QHBoxLayout(host), margins=None, spacing=tokens.SPACE_SM)
            label = detail_name_label(title)
            label.setMinimumWidth(0)
            text = QtWidgets.QLabel(value)
            text.setWordWrap(True)
            row.addWidget(label)
            row.addWidget(text, 1)
            widgets.append(host)
        self.add_flow_row(widgets)

    def add_row(self, *widgets, stretch_last: bool = False, trailing_stretch: bool = False):
        row = apply_margins(QtWidgets.QHBoxLayout(), margins=None)
        for index, widget in enumerate(widgets):
            last = index == len(widgets) - 1
            row.addWidget(widget, 1 if stretch_last and last else 0)
        if trailing_stretch:
            row.addStretch(1)
        self.layout.addLayout(row)
        return row

    def add_text_row(self, label: str, value: str) -> None:
        value_label = QtWidgets.QLabel(value)
        value_label.setWordWrap(True)
        self.add_row(detail_name_label(label), value_label, stretch_last=True)

    def add_stretch(self) -> None:
        self.layout.addStretch(1)

    def available_width(self) -> int:
        margins = self.layout.contentsMargins()
        width = self.viewport().width() or self.width()
        return max(1, width - margins.left() - margins.right())

    def image_target_size(self, image: DetailImageLabel | None = None) -> QtCore.QSize:
        width = self.available_width()
        margins = self.layout.contentsMargins()
        occupied_height = margins.top() + margins.bottom()
        content_count = 0
        for index in range(self.layout.count()):
            item = self.layout.itemAt(index)
            if item.spacerItem() is not None or item.isEmpty():
                continue
            content_count += 1
            if isinstance(item.widget(), DetailImageLabel):
                continue
            height = item.heightForWidth(width) if item.hasHeightForWidth() else item.sizeHint().height()
            occupied_height += max(item.minimumSize().height(), height)
        if image is None or self.layout.indexOf(image) < 0:
            content_count += 1
        occupied_height += max(0, content_count - 1) * self.layout.spacing()
        return QtCore.QSize(
            max(1, width - tokens.DETAIL_IMAGE_INSET),
            max(1, self.viewport().height() - occupied_height),
        )

    def rescale_images(self) -> None:
        for image in self.frame.findChildren(DetailImageLabel):
            image.update_scaled_pixmap(self.image_target_size(image))

    def dates_fit_on_one_row(self, first: str, second: str, available_width: int | None = None) -> bool:
        if available_width is None:
            available_width = self.available_width()
        metrics = self.frame.fontMetrics()
        needed = (
            tokens.DETAIL_LABEL_MIN_WIDTH * 2
            + metrics.horizontalAdvance(first)
            + metrics.horizontalAdvance(second)
            + tokens.DETAIL_DATES_SPACING
        )
        return available_width >= needed
