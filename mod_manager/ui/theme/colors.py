from __future__ import annotations

from dataclasses import dataclass

THEME_MODES = ("system", "light", "dark")
COLOR_MODES = ("system", "custom")

FALLBACK_ACCENT = "#2563eb"
FALLBACK_TEXT = "#111827"
STATE_OK = "#16a34a"
STATE_BAD = "#dc2626"

DARK_THRESHOLD = 0.45
READABLE_THRESHOLD = 0.58

LIGHT_BASE = {
    "bg": "#f5f6f8",
    "fg": "#202735",
    "control_fg": "#202735",
    "panel": "#ffffff",
    "alt_panel": "#edf0f4",
    "button": "#ffffff",
    "tooltip_bg": "#ffffff",
    "tooltip_fg": "#202735",
    "field": "#ffffff",
    "field_border": "#dce1e8",
    "field_focus": "#5f6b7d",
    "field_fg": "#202735",
    "combo": "#ffffff",
    "combo_hover": "#e8edf3",
    "combo_focus": "#edf0f4",
    "combo_list": "#ffffff",
    "combo_list_border": "#dce1e8",
    "menu": "#ffffff",
    "menu_border": "#dce1e8",
    "menu_selected": "#e8edf3",
    "border": "#dce1e8",
    "muted": "#5f6b7d",
    "placeholder_fg": "#5f6b7d",
}

DARK_BASE = {
    "bg": "#181b20",
    "fg": "#e8edf4",
    "control_fg": "#e8edf4",
    "panel": "#20242b",
    "alt_panel": "#1d2127",
    "button": "#20242b",
    "tooltip_bg": "#20242b",
    "tooltip_fg": "#e8edf4",
    "field": "#20242b",
    "field_border": "#353c47",
    "field_focus": "#a1adbd",
    "field_fg": "#e8edf4",
    "combo": "#20242b",
    "combo_hover": "#2c333d",
    "combo_focus": "#1d2127",
    "combo_list": "#20242b",
    "combo_list_border": "#353c47",
    "menu": "#20242b",
    "menu_border": "#353c47",
    "menu_selected": "#2c333d",
    "border": "#353c47",
    "muted": "#a1adbd",
    "placeholder_fg": "#a1adbd",
}

LIGHT_TRANSLUCENT = {
    "placeholder_bg": ("#edf0f4", 255),
    "tile_base": ("#ffffff", 255),
    "tile_base_selected": ("#edf0f4", 255),
    "tile_border": ("#dce1e8", 255),
    "tile_border_selected": ("#667287", 255),
    "tile_shine": ("#ffffff", 0),
    "tile_end": ("#ffffff", 0),
    "tile_shadow": ("#f5f6f8", 0),
    "tile_inner": ("#ffffff", 0),
}

DARK_TRANSLUCENT = {
    "placeholder_bg": ("#1d2127", 255),
    "tile_base": ("#20242b", 255),
    "tile_base_selected": ("#1d2127", 255),
    "tile_border": ("#353c47", 255),
    "tile_border_selected": ("#a1adbd", 255),
    "tile_shine": ("#20242b", 0),
    "tile_end": ("#20242b", 0),
    "tile_shadow": ("#181b20", 0),
    "tile_inner": ("#20242b", 0),
}

BUTTON_OVERLAY = {
    "light": ("#000000", {
        "normal": 0,
        "hover": 12,
        "pressed": 20,
        "disabled": 5,
    }),
    "dark": ("#ffffff", {
        "normal": 0,
        "hover": 14,
        "pressed": 22,
        "disabled": 6,
    }),
}

ACCENT_FILL_ALPHA = 30
ACCENT_BORDER_ALPHA = 170

TEXT_OVERRIDE_FIELDS = ("fg", "control_fg", "field_fg", "tooltip_fg")


def normalize_hex(value) -> str | None:
    text = str(value or "").strip()
    if not text.startswith("#"):
        return None
    digits = text[1:]
    if len(digits) == 3:
        digits = "".join(char * 2 for char in digits)
    if len(digits) != 6:
        return None
    try:
        int(digits, 16)
    except ValueError:
        return None
    return "#" + digits.lower()


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    digits = (normalize_hex(value) or FALLBACK_ACCENT)[1:]
    return int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16)


def rgb_to_hex(red: int, green: int, blue: int) -> str:
    clamped = tuple(max(0, min(255, int(round(part)))) for part in (red, green, blue))
    return "#%02x%02x%02x" % clamped


def rgba_css(value: str, alpha: int) -> str:
    red, green, blue = hex_to_rgb(value)
    return f"rgba({red}, {green}, {blue}, {int(alpha)})"


def blend(first: str, second: str, ratio: float) -> str:
    ratio = max(0.0, min(1.0, float(ratio)))
    one = hex_to_rgb(first)
    two = hex_to_rgb(second)
    return rgb_to_hex(*(one[i] * ratio + two[i] * (1.0 - ratio) for i in range(3)))


def luminance(value: str) -> float:
    red, green, blue = (part / 255.0 for part in hex_to_rgb(value))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def is_dark_color(value: str) -> bool:
    return luminance(value) < DARK_THRESHOLD


def readable_on(value: str) -> str:
    return "#000000" if luminance(value) > READABLE_THRESHOLD else "#ffffff"


def button_ripple_color(palette, surface: tuple[int, int, int, int]) -> str:
    red, green, blue, alpha = surface
    background = blend(rgb_to_hex(red, green, blue), palette.panel, alpha / 255.0)
    return readable_on(background)


def color_channels(value: str) -> tuple[int, int, int, int]:
    if value == "transparent":
        return (0, 0, 0, 0)
    if value.startswith("rgba"):
        return tuple(int(part.strip()) for part in value[value.index("(") + 1:value.index(")")].split(","))
    return (*hex_to_rgb(value), 255)


def button_surface(palette, variant, enabled, checked, hovered, pressed, focused):
    background, border, foreground = palette.panel, palette.border, palette.control_fg
    if variant in ("navigation", "segment", "link"):
        background = border = "transparent"
    if checked:
        background, border = palette.accent_fill, palette.accent_border
    if hovered:
        background = palette.button_hover if variant in ("navigation", "segment", "link") else palette.combo_hover
    if pressed:
        background = palette.combo_focus
    if variant == "primary":
        background = palette.accent_border if hovered else palette.accent
        border, foreground = palette.accent, palette.accent_text
    if focused:
        border = palette.accent
    if not enabled:
        background, border, foreground = palette.button_disabled, palette.border, palette.muted
    return tuple(color_channels(value) for value in (background, border, foreground))


def normalize_mode(value) -> str:
    mode = str(value or "system").strip().lower()
    return mode if mode in THEME_MODES else "system"


def normalize_color_mode(value) -> str:
    mode = str(value or "system").strip().lower()
    return mode if mode in COLOR_MODES else "system"


@dataclass(frozen=True)
class Rgba:
    color: str
    alpha: int

    @property
    def css(self) -> str:
        return rgba_css(self.color, self.alpha)


@dataclass(frozen=True)
class Palette:
    mode: str
    bg: str
    fg: str
    control_fg: str
    panel: str
    alt_panel: str
    button: str
    tooltip_bg: str
    tooltip_fg: str
    field: str
    field_border: str
    field_focus: str
    field_fg: str
    combo: str
    combo_hover: str
    combo_focus: str
    combo_list: str
    combo_list_border: str
    menu: str
    menu_border: str
    menu_selected: str
    border: str
    muted: str
    placeholder_fg: str
    accent: str
    accent_text: str
    accent_fill: str
    accent_border: str
    button_normal: str
    button_hover: str
    button_pressed: str
    button_disabled: str
    state_ok: str
    state_bad: str
    placeholder_bg: Rgba
    tile_base: Rgba
    tile_base_selected: Rgba
    tile_border: Rgba
    tile_border_selected: Rgba
    tile_shine: Rgba
    tile_end: Rgba
    tile_shadow: Rgba
    tile_inner: Rgba

    @property
    def is_dark(self) -> bool:
        return self.mode == "dark"


def build_palette(mode: str, accent: str | None = None, text: str | None = None) -> Palette:
    resolved_mode = "dark" if str(mode).lower() == "dark" else "light"
    base = dict(DARK_BASE if resolved_mode == "dark" else LIGHT_BASE)
    translucent = DARK_TRANSLUCENT if resolved_mode == "dark" else LIGHT_TRANSLUCENT

    text_override = normalize_hex(text)
    if text_override:
        for field in TEXT_OVERRIDE_FIELDS:
            base[field] = text_override

    accent_color = normalize_hex(accent) or FALLBACK_ACCENT
    overlay_color, alphas = BUTTON_OVERLAY[resolved_mode]

    return Palette(
        mode=resolved_mode,
        accent=accent_color,
        accent_text=readable_on(accent_color),
        accent_fill=rgba_css(accent_color, ACCENT_FILL_ALPHA),
        accent_border=rgba_css(accent_color, ACCENT_BORDER_ALPHA),
        button_normal=rgba_css(overlay_color, alphas["normal"]),
        button_hover=rgba_css(overlay_color, alphas["hover"]),
        button_pressed=rgba_css(overlay_color, alphas["pressed"]),
        button_disabled=rgba_css(overlay_color, alphas["disabled"]),
        state_ok=STATE_OK,
        state_bad=STATE_BAD,
        **base,
        **{key: Rgba(*value) for key, value in translucent.items()},
    )
