from __future__ import annotations

from . import tokens
from .colors import Palette


def build_stylesheet(palette: Palette) -> str:
    button_v, button_h = tokens.BUTTON_PADDING
    field_v, field_h = tokens.FIELD_PADDING
    menu_top, menu_right, menu_bottom, menu_left = tokens.MENU_ITEM_PADDING
    return f"""
        QMainWindow, QDialog, QWidget[variant="workspace"] {{ background: {palette.bg}; color: {palette.fg}; }}
        QWidget {{ selection-background-color: {palette.accent_fill}; selection-color: {palette.fg}; }}
        QLabel {{ color: {palette.fg}; background: transparent; }}
        QLabel[variant="muted"], QLabel[variant="sectionTitle"] {{ color: {palette.muted}; }}
        QLabel[variant="heading"] {{ font-weight: 600; }}
        QFrame[variant="sidebar"] {{ background: {palette.alt_panel}; border: none; border-right: {tokens.BORDER_WIDTH}px solid {palette.border}; }}
        QWidget[variant="panel"] {{ background: {palette.panel}; }}
        QPushButton, QToolButton {{
            background: {palette.panel}; color: {palette.control_fg}; border: {tokens.BORDER_WIDTH}px solid {palette.border};
            border-radius: {tokens.RADIUS_MD}px; padding: {button_v}px {button_h}px;
        }}
        QPushButton:hover, QToolButton:hover {{ background: {palette.combo_hover}; }}
        QPushButton:pressed, QToolButton:pressed {{ background: {palette.combo_focus}; }}
        QPushButton:checked, QToolButton:checked {{ background: {palette.accent_fill}; border-color: {palette.accent_border}; }}
        QPushButton:focus, QToolButton:focus {{ border-color: {palette.accent}; }}
        QPushButton:disabled, QToolButton:disabled {{ color: {palette.muted}; background: {palette.button_disabled}; }}
        QPushButton[variant="primary"] {{ background: {palette.accent}; color: {palette.accent_text}; border-color: {palette.accent}; }}
        QPushButton[variant="primary"]:hover {{ background: {palette.accent_border}; }}
        QPushButton[variant="primary"]:disabled {{ background: {palette.button_disabled}; color: {palette.muted}; border-color: {palette.border}; }}
        QPushButton[variant="navigation"] {{ text-align: left; background: transparent; border-color: transparent; }}
        QPushButton[variant="navigation"]:hover {{ background: {palette.button_hover}; }}
        QPushButton[variant="navigation"]:checked {{ background: {palette.accent_fill}; border-left-color: {palette.accent}; font-weight: 600; }}
        QPushButton[variant="navigation"]:focus {{ border-color: {palette.accent}; }}
        QPushButton[variant="navigation"][compact="true"] {{ text-align: center; padding: {tokens.SPACE_SM}px; }}
        QFrame[variant="toolbarSection"] {{ background: transparent; border: none; }}
        QFrame[variant="formSection"] {{ background: {palette.panel}; border: {tokens.BORDER_WIDTH}px solid {palette.border}; border-radius: {tokens.RADIUS_MD}px; }}
        QPushButton[variant="link"] {{ background: transparent; border-color: transparent; text-align: left; padding-left: 0; }}
        QPushButton[variant="link"]:hover {{ background: {palette.button_hover}; }}
        QPushButton[variant="link"]:focus {{ border-color: {palette.accent}; }}
        QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox {{
            background: {palette.field}; color: {palette.field_fg}; border: {tokens.BORDER_WIDTH}px solid {palette.field_border};
            border-radius: {tokens.RADIUS_SM}px; padding: {field_v}px {field_h}px;
        }}
        QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus {{ border-color: {palette.accent}; }}
        QFrame[variant="shortcutField"] {{ background: {palette.field}; border: {tokens.BORDER_WIDTH}px solid {palette.field_border}; border-radius: {tokens.RADIUS_SM}px; }}
        QFrame[variant="shortcutField"] QLineEdit {{ background: transparent; border: none; }}
        QComboBox {{
            background: {palette.combo}; color: {palette.field_fg}; border: {tokens.BORDER_WIDTH}px solid {palette.field_border};
            border-radius: {tokens.RADIUS_SM}px;
            padding: {tokens.COMBO_PAD_V}px {tokens.COMBO_PAD_RIGHT}px {tokens.COMBO_PAD_V}px {tokens.COMBO_PAD_LEFT}px;
        }}
        QComboBox:hover {{ background: {palette.combo_hover}; }}
        QComboBox:focus {{ border-color: {palette.accent}; }}
        QComboBox::drop-down {{ border: none; width: {tokens.COMBO_ARROW_WIDTH}px; }}
        QComboBox::down-arrow {{ image: none; }}
        QComboBox QAbstractItemView {{
            background: {palette.combo_list}; color: {palette.field_fg}; border: {tokens.BORDER_WIDTH}px solid {palette.combo_list_border};
            selection-background-color: {palette.accent_fill}; selection-color: {palette.fg};
        }}
        QComboBox QLineEdit {{ background: transparent; border: none; padding: 0 {tokens.SPACE_XS}px; }}
        QAbstractItemView {{ background: {palette.panel}; color: {palette.fg}; outline: 0; border: none; }}
        QTableView::item {{ padding: {tokens.SPACE_SM}px; border: none; }}
        QTableView::item:hover, QListWidget::item:hover {{ background: {palette.button_hover}; }}
        QTableView::item:selected, QListWidget::item:selected {{ background-color: {palette.accent_fill}; color: {palette.fg}; border: none; outline: none; }}
        QTableView::item:focus, QListWidget::item:focus {{ border: {tokens.BORDER_WIDTH}px solid {palette.accent_border}; }}
        QHeaderView::section {{
            background: {palette.alt_panel}; color: {palette.muted}; font-weight: 600; border: none;
            border-bottom: {tokens.BORDER_WIDTH}px solid {palette.border}; padding: {tokens.SPACE_LG}px;
        }}
        QTableCornerButton::section {{ background: {palette.alt_panel}; border: none; }}
        QListWidget::item {{ padding: {tokens.SPACE_LG}px; border: {tokens.BORDER_WIDTH}px solid transparent; }}
        QListView[variant="archiveSelector"] {{ background: {palette.bg}; }}
        QListView[variant="archiveSelector"]::item {{ background: {palette.panel}; color: {palette.control_fg}; border: {tokens.BORDER_WIDTH}px solid {palette.border}; border-radius: {tokens.RADIUS_MD}px; }}
        QListView[variant="archiveSelector"]::item:hover {{ background: {palette.combo_hover}; }}
        QListView[variant="archiveSelector"]::item:selected {{ background: {palette.accent_fill}; border-color: {palette.accent_border}; }}
        QListView[variant="archiveSelector"]::item:focus {{ border-color: {palette.accent}; }}
        QListView[variant="archiveSelector"]::item:disabled {{ background: {palette.button_disabled}; color: {palette.muted}; }}
        QScrollArea {{ border: none; background: transparent; }}
        QSplitter::handle {{ background: {palette.border}; }}
        QScrollBar:vertical {{ background: {palette.bg}; width: {tokens.SCROLLBAR_WIDTH}px; margin: 0; }}
        QScrollBar:horizontal {{ background: {palette.bg}; height: {tokens.SCROLLBAR_WIDTH}px; margin: 0; }}
        QScrollBar::handle {{ background: {palette.field_border}; border-radius: {tokens.RADIUS_SM}px; min-width: {tokens.SPACE_3XL}px; min-height: {tokens.SPACE_3XL}px; }}
        QScrollBar::handle:hover {{ background: {palette.muted}; }}
        QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
        QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
        QStatusBar {{ background: {palette.bg}; color: {palette.muted}; border-top: {tokens.BORDER_WIDTH}px solid {palette.border}; }}
        QStatusBar::item {{ border: none; }}
        QToolTip {{ background: {palette.tooltip_bg}; color: {palette.tooltip_fg}; border: {tokens.BORDER_WIDTH}px solid {palette.border}; padding: {tokens.SPACE_SM}px; }}
        QMenu, QMenuBar {{ background: {palette.menu}; color: {palette.field_fg}; }}
        QMenu {{ border: {tokens.BORDER_WIDTH}px solid {palette.menu_border}; padding: {tokens.SPACE_SM}px; }}
        QMenu::item {{ padding: {menu_top}px {menu_right}px {menu_bottom}px {menu_left}px; border-radius: {tokens.RADIUS_SM}px; }}
        QMenu::item:selected, QMenuBar::item:selected {{ background: {palette.menu_selected}; }}
    """
