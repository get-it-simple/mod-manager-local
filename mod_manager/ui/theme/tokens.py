from __future__ import annotations

SPACE_XS = 2
SPACE_SM = 4
SPACE_MD = 6
SPACE_LG = 8
SPACE_XL = 10
SPACE_2XL = 12
SPACE_3XL = 18

PAGE_MARGIN = 16
DETAIL_MARGIN = 12
TOOLBAR_SECTION_MARGIN = 6
FORM_LABEL_MIN_WIDTH = 170
FORM_SHORT_FIELD_WIDTH = 96
FORM_MEDIUM_FIELD_WIDTH = 240
FORM_PAIR_SPACING = 24
PAGE_INPUT_WIDTH = 44

RADIUS_SM = 4
RADIUS_MD = 6
RADIUS_LG = 6
RADIUS_IMAGE = 5

BORDER_WIDTH = 1
ICON_SIZE = 18
PREVIEW_ICON_SIZE = 22
FONT_PREVIEW_MIN_HEIGHT = 48
LABEL_LIST_MIN_WIDTH = 180
LABEL_LIST_DEFAULT_WIDTH = 240
LABEL_EDITOR_LIST_HEIGHT = 150
LABEL_FRAGMENTS_COLUMN_WIDTH = 96
LABEL_FRAGMENT_ID_WIDTH = 40
LABEL_FRAGMENT_SAVE_WIDTH = 72
LABEL_FRAGMENT_LIST_HEIGHT = 112
FILTER_ANIMATION_MS = 160
FILTER_EXPAND_FACTOR = 2
ICON_BUTTON_SIZE = 32
GAME_BUTTON_MIN_WIDTH = 48
TEXT_BUTTON_MIN_WIDTH = 96
LABEL_EDIT_MAX_WIDTH = 160
PROFILE_FIELD_MIN_WIDTH = 420
DETAIL_LABEL_MIN_WIDTH = 110
DETAIL_PANEL_MIN_WIDTH = 280
DETAIL_DATES_SPACING = 28
DETAIL_IMAGE_INSET = 2
PATH_MAX_CHARS = 100
PATH_VISIBLE_DIRECTORIES = 2

MIN_WIDTH = 880
MIN_HEIGHT = 560
DEFAULT_WIDTH = 1200
DEFAULT_HEIGHT = 750
DIALOG_SIZE = (760, 520)
LARGE_DIALOG_SIZE = (820, 560)
ARCHIVE_DIALOG_SIZE = (960, 680)
ARCHIVE_SWITCHER_MIN_WIDTH = 160
ARCHIVE_NAME_MAX_CHARS = 32
WHEEL_ANGLE_STEP = 120
ARCHIVE_WHEEL_PIXEL_STEP = 40
ARCHIVE_PREVIEW_SIZE = 180
PREVIEW_CONFIRM_WIDTH = 480
PREVIEW_CONFIRM_IMAGE_SIZE = 240
ARCHIVE_CHECK_COLUMN_WIDTH = 36
ARCHIVE_NAME_COLUMN_WIDTH = 230
TILE_LIST_STRETCH = 3
TILE_DETAIL_STRETCH = 2

TITLE_FONT_STEP = 6
TITLE_FONT_MIN = 16

SIDEBAR_WIDTH = 176
SIDEBAR_COMPACT_WIDTH = 56
SIDEBAR_BREAKPOINT = 1100
NAVIGATION_HEIGHT = 36
TABLE_ROW_HEIGHT = 34
TABLE_HEADER_HEIGHT = 32
SCROLLBAR_WIDTH = 10
SPLITTER_WIDTH = 4
SEARCH_MIN_WIDTH = 130
LABEL_FILTER_MIN_WIDTH = 92
ORDER_MIN_WIDTH = 115
DETAIL_TITLE_FONT_STEP = 2
EMPTY_STATE_MIN_HEIGHT = 100

CHECK_PEN_MIN = 2.0
CHECK_PEN_RATIO = 0.14
CHECK_PATH = ((0.22, 0.50), (0.43, 0.72), (0.78, 0.28))

SORT_ARROW_PEN = 2.2
SORT_ARROW_MARGIN = 4
SORT_ARROW_HEAD = 5
SORT_ARROW_HEAD_Y = 10

STATE_ICON_SIZE = 18
STATE_ICON_PEN = 2.6
STATE_CHECK_PATH = ((4, 9), (8, 13), (14, 5))
STATE_CROSS_PATH = (((5, 5), (13, 13)), ((13, 5), (5, 13)))

TILE_CARD_INSET = 6
TILE_CONTENT_PAD = 8
TILE_IMAGE_MIN_HEIGHT = 48
TILE_IMAGE_HEIGHT_TRIM = 18
TILE_BADGE_MARGIN = 12
TILE_BADGE_HEIGHT = 24
TILE_CHECK_BADGE_WIDTH = 28
TILE_BADGE_RADIUS = 4
TILE_BADGE_CHECK_PEN = 2.8
TILE_BADGE_CHECK_PATH = ((7, 12), (12, 17), (21, 7))
TILE_LABEL_BADGE_MAX_CHARS = 8
TILE_LABEL_BADGE_MIN_WIDTH = 34
TILE_LABEL_BADGE_PADDING = 14
TILE_LABEL_TEXT_INSET = 7
TILE_NAME_TEXT_INSET = 8
FAVORITE_HIT_SIZE = 24
FAVORITE_MARGIN = 4
TILE_CARD_RADIUS = 8
TILE_CARD_INNER_RADIUS = 7
TILE_SHADOW_OFFSET = 2
TILE_GRADIENT_MID = 0.45
TILE_SIZE_MIN = 96
TILE_SIZE_MAX = 280
TILE_SIZE_STEP = 12
TILE_EXTRA_WIDTH = 28
TILE_EXTRA_HEIGHT = 58

COMBO_PAD_V = 5
COMBO_PAD_RIGHT = 20
COMBO_PAD_LEFT = 9
COMBO_ARROW_WIDTH = 18
COMBO_CHEVRON_PEN = 1.8
COMBO_CHEVRON_HALF_WIDTH = 4
COMBO_CHEVRON_HALF_HEIGHT = 2
COMBO_CHEVRON_RIGHT_INSET = 9

GLYPH_PEN = 1.8
ICON_SCALE_FACTORS = (1, 2, 3)
GLYPH_PATHS = {
    "add": (((4, 9), (14, 9)), ((9, 4), (9, 14))),
    "remove": (((4, 4), (14, 14)), ((14, 4), (4, 14))),
    "clear": (((4, 4), (14, 14)), ((14, 4), (4, 14))),
    "back": (((11, 4), (6, 9), (11, 14)),),
    "forward": (((7, 4), (12, 9), (7, 14)),),
    "folder": (((2, 14), (2, 4), (7, 4), (9, 6), (16, 6), (16, 14), (2, 14)),),
    "open": (((2, 14), (2, 4), (7, 4), (9, 6), (16, 6), (16, 14), (2, 14)),),
    "image": (((2, 2), (16, 2), (16, 16), (2, 16), (2, 2)), ((3, 13), (7, 8), (10, 11), (13, 7), (16, 11))),
    "tiles": (((2, 2), (7, 2), (7, 7), (2, 7), (2, 2)), ((11, 2), (16, 2), (16, 7), (11, 7), (11, 2)), ((2, 11), (7, 11), (7, 16), (2, 16), (2, 11)), ((11, 11), (16, 11), (16, 16), (11, 16), (11, 11))),
    "list": (((3, 4), (4, 4)), ((7, 4), (15, 4)), ((3, 9), (4, 9)), ((7, 9), (15, 9)), ((3, 14), (4, 14)), ((7, 14), (15, 14))),
    "import": (((9, 2), (9, 11)), ((5, 7), (9, 11), (13, 7)), ((3, 11), (3, 16), (15, 16), (15, 11))),
    "install": (((9, 2), (9, 11)), ((5, 7), (9, 11), (13, 7)), ((3, 13), (3, 16), (15, 16), (15, 13))),
    "uninstall": (((4, 9), (14, 9)),),
    "toggle": (((3, 6), (14, 6), (11, 3)), ((15, 12), (4, 12), (7, 15))),
    "save": (((3, 2), (13, 2), (16, 5), (16, 16), (2, 16), (2, 2), (3, 2)), ((5, 2), (5, 7), (12, 7), (12, 2)), ((5, 16), (5, 11), (13, 11), (13, 16))),
    "presets": (((2, 6), (9, 2), (16, 6), (9, 10), (2, 6)), ((2, 10), (9, 14), (16, 10)), ((2, 14), (9, 18), (16, 14))),
    "game": (((3, 5), (15, 5), (17, 14), (13, 14), (11, 11), (7, 11), (5, 14), (1, 14), (3, 5)), ((4, 8), (8, 8)), ((6, 6), (6, 10)), ((12, 8), (13, 8)), ((14, 10), (15, 10))),
    "menu": (((3, 4), (15, 4)), ((3, 9), (15, 9)), ((3, 14), (15, 14))),
    "details": (((2, 2), (16, 2), (16, 16), (2, 16), (2, 2)), ((11, 2), (11, 16))),
    "details_show": (((2, 2), (16, 2), (16, 16), (2, 16), (2, 2)), ((11, 2), (11, 16)), ((5, 6), (8, 9), (5, 12))),
    "details_hide": (((2, 2), (16, 2), (16, 16), (2, 16), (2, 2)), ((11, 2), (11, 16)), ((8, 6), (5, 9), (8, 12))),
    "folder_forward": (((2, 14), (2, 4), (7, 4), (9, 6), (16, 6), (16, 9)), ((10, 13), (17, 13)), ((14, 10), (17, 13), (14, 16))),
    "label_add": (((9, 2), (2, 2), (2, 9), (7, 14), (14, 7), (9, 2)), ((5, 5), (6, 5)), ((11, 14), (17, 14)), ((14, 11), (14, 17))),
    "label_remove": (((9, 2), (2, 2), (2, 9), (7, 14), (14, 7), (9, 2)), ((5, 5), (6, 5)), ((11, 14), (17, 14))),
    "search": (((11, 11), (16, 16)),),
    "reset": (((3, 7), (5, 4), (10, 3), (14, 6), (15, 10), (12, 14), (7, 15), (4, 12)), ((3, 2), (3, 7), (8, 7))),
}
GLYPH_CIRCLES = {"search": (3, 3, 10, 10)}
GLYPH_MARGIN = 3
GLYPH_INNER_MARGIN = 6
GLYPH_CENTER = 9
GLYPH_SMALL_RADIUS = 3
GLYPH_LARGE_RADIUS = 6
STAR_OUTER_RADIUS = 7
STAR_INNER_RADIUS = 3
STAR_POINTS = 5
STAR_START_DEGREES = -90
STAR_STEP_DEGREES = 36
TRASH_TOP = 5
TRASH_BOTTOM = 15
TRASH_LEFT = 5
TRASH_RIGHT = 13
FILTER_PATH = ((3, 4), (15, 4), (10, 9), (10, 15), (8, 14), (8, 9), (3, 4))
CHECK_SMALL_PATH = ((10, 12), (12, 14), (16, 10))
CROSS_SMALL_PATH = (((11, 11), (15, 15)), ((15, 11), (11, 15)))
EDIT_PATH = ((4, 14), (5, 10), (12, 3), (15, 6), (8, 13), (4, 14))
SUBMIT_PATH = ((3, 9), (13, 9), (10, 6), (13, 9), (10, 12))
BROKEN_LEFT_PATH = ((3, 11), (2, 9), (3, 7), (6, 4), (8, 4), (9, 5))
BROKEN_RIGHT_PATH = ((9, 13), (11, 14), (13, 13), (16, 10), (16, 8), (15, 7))
BROKEN_SLASH_PATH = ((5, 14), (13, 3))
MENU_ITEM_PADDING = (6, 24, 6, 12)
MENUBAR_ITEM_PADDING = (4, 8)
BUTTON_PADDING = (6, 10)
FIELD_PADDING = (4, 8)

WORKER_POLL_MS = 50
IMMEDIATE_MS = 0

SCALE_MIN = 50
SCALE_MAX = 400

ALIGN_LEFT = "left"
ALIGN_CENTER = "center"
ALIGN_RIGHT = "right"

RESIZE_FIXED = "fixed"
RESIZE_STRETCH = "stretch"
RESIZE_CONTENTS = "contents"

ERROR_COLUMNS = (
    ("time", "Time", RESIZE_CONTENTS, ALIGN_LEFT),
    ("profile", "Profile", RESIZE_CONTENTS, ALIGN_LEFT),
    ("action", "Action", RESIZE_CONTENTS, ALIGN_LEFT),
    ("mod", "Mod", RESIZE_STRETCH, ALIGN_LEFT),
    ("file", "File", RESIZE_STRETCH, ALIGN_LEFT),
)

ARCHIVE_COLUMNS = (
    ("selected", "Add", RESIZE_FIXED, ALIGN_CENTER),
    ("name", "Mod", RESIZE_FIXED, ALIGN_LEFT),
    ("files", "Files in archive", RESIZE_STRETCH, ALIGN_LEFT),
)

MOD_COLUMNS = (
    ("installed", "", RESIZE_FIXED, ALIGN_CENTER),
    ("name", "Name", RESIZE_STRETCH, ALIGN_LEFT),
    ("label", "Label", RESIZE_CONTENTS, ALIGN_LEFT),
    ("last_managed", "Last managed", RESIZE_CONTENTS, ALIGN_LEFT),
)

PRESET_COLUMNS = (
    ("name", "Preset", RESIZE_STRETCH, ALIGN_LEFT),
    ("state", "State", RESIZE_CONTENTS, ALIGN_CENTER),
    ("mods", "Mods", RESIZE_CONTENTS, ALIGN_LEFT),
    ("last_managed", "Last managed", RESIZE_CONTENTS, ALIGN_LEFT),
)

BROKEN_COLUMNS = (
    ("name", "Broken link", RESIZE_STRETCH, ALIGN_LEFT),
    ("dest", "Destination", RESIZE_STRETCH, ALIGN_LEFT),
)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def to_int(value, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def clamp_tile_size(value) -> int:
    return int(clamp(to_int(value, TILE_SIZE_MIN), TILE_SIZE_MIN, TILE_SIZE_MAX))


def tile_item_size(tile_size) -> tuple[int, int]:
    size = max(TILE_SIZE_MIN, to_int(tile_size, TILE_SIZE_MIN))
    return size + TILE_EXTRA_WIDTH, size + TILE_EXTRA_HEIGHT


def scaled(value: int, scale_percent) -> int:
    percent = clamp(to_int(scale_percent, 100), SCALE_MIN, SCALE_MAX)
    return max(1, int(round(value * percent / 100.0)))
