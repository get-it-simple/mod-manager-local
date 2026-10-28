from __future__ import annotations

from dataclasses import dataclass, field

from app_paths import DEFAULT_CONFIG
from .i18n import available_languages, t
from .keyboard import validate_bindings

from .ui.theme.colors import normalize_hex

INT = "int"
TEXT = "text"
PATH = "path"
CHOICE = "choice"
FLAG = "flag"
COLOR = "color"
FONT = "font"
SHORTCUTS = "shortcuts"

INTERNAL_KEYS = frozenset({
    "active_game_profile_id",
    "game_profiles",
    "window_width",
    "window_height",
    "order_var",
    "mod_sort_key",
    "mod_sort_reverse",
    "preset_sort_key",
    "preset_sort_reverse",
})


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    tooltip: str
    kind: str
    choices: tuple = ()
    minimum: int | None = None
    maximum: int | None = None
    depends_on: tuple | None = None
    browse: bool = False

    @property
    def range_text(self) -> str:
        return f"between {self.minimum} and {self.maximum}"


GAME_NAME_FIELD = FieldSpec(
    key="name",
    label=t('game_name'),
    tooltip=t('name_shown_in_the_game_switcher_the_two_letter_abbreviation_on_the_game_'),
    kind=TEXT,
)

LABEL_NAME_FIELD = FieldSpec("label_name", t('label_name'), t('unique_name_shown_in_the_library_and_label_filters'), TEXT)
LABEL_MODE_FIELD = FieldSpec(
    "label_mode", t('mode'), t('manual_uses_selected_mods_automatic_matches_any_name_fragment_ignoring_l'),
    CHOICE, choices=(t('manual'), t('automatic')),
)
LABEL_TERMS_FIELD = FieldSpec(
    "label_terms", t('name_fragments'), t('enter_a_fragment_and_press_enter_to_add_another_edit_or_delete_existing_'), TEXT,
)
LABEL_MEMBERS_FIELD = FieldSpec(
    "label_members", t('manual_mods'), t('check_mods_to_assign_this_label_manually_these_choices_are_retained_when'), TEXT,
)

MODS_FIELDS = (
    FieldSpec(
        key="mods_source_dir",
        label=t('mods_source_folder'),
        tooltip=t('folder_that_holds_your_downloaded_mod_files_and_folders_imported_mods_ar'),
        kind=PATH,
        browse=True,
    ),
    FieldSpec(
        key="game_mods_dir",
        label=t('game_mods_folder'),
        tooltip=t('folder_inside_the_game_where_install_links_are_created_uninstalling_remo'),
        kind=PATH,
        browse=True,
    ),
    FieldSpec(
        key="mod_extensions",
        label=t('mod_file_extensions'),
        tooltip=t('comma_separated_file_extensions_treated_as_mods_for_example_pak_utoc_lea'),
        kind=TEXT,
    ),
    FieldSpec(
        key="mod_group_extensions",
        label=t('grouped_extensions'),
        tooltip=t('comma_separated_extensions_joined_into_a_single_mod_when_the_files_share'),
        kind=TEXT,
    ),
    FieldSpec(
        key="mod_recursive_scan",
        label=t('scan_subfolders'),
        tooltip=t('also_look_inside_subfolders_of_the_mods_source_folder_when_listing_avail'),
        kind=FLAG,
    ),
    FieldSpec(
        key="link_prefix",
        label=t('link_name_prefix'),
        tooltip=t('text_added_to_the_start_of_created_link_names_in_the_game_mods_folder_ap'),
        kind=TEXT,
    ),
    FieldSpec(
        key="install_mode",
        label=t('install_method'),
        tooltip=t('link_creates_a_symlink_or_junction_in_the_game_mods_folder_copy_physical'),
        kind=CHOICE,
        choices=("link", "copy"),
    ),
)

LIST_FIELDS = (
    FieldSpec(
        key="page_size",
        label=t('mods_per_page'),
        tooltip=t('how_many_mods_are_shown_on_a_single_page_in_the_mods_list_and_in_paged_c'),
        kind=INT,
        minimum=1,
        maximum=1000,
    ),
    FieldSpec(
        key="max_mod_name_len",
        label=t('max_mod_name_length'),
        tooltip=t('longest_mod_name_shown_before_it_is_shortened_with_an_ellipsis_display_o'),
        kind=INT,
        minimum=4,
        maximum=200,
    ),
    FieldSpec(
        key="max_preset_name_len",
        label=t('max_preset_name_length'),
        tooltip=t('longest_preset_name_shown_before_it_is_shortened_in_the_presets_list'),
        kind=INT,
        minimum=4,
        maximum=200,
    ),
    FieldSpec(
        key="max_label_name_len",
        label=t('max_label_length'),
        tooltip=t('longest_label_text_shown_before_it_is_shortened_on_tiles_and_in_the_labe'),
        kind=INT,
        minimum=2,
        maximum=64,
    ),
)

APPEARANCE_FIELDS = (
    FieldSpec("gui_animations_enabled", t("interface_animations"), t("interface_animations_help"), FLAG),
    FieldSpec("gui_language", t("language_label"), t("language_help"), CHOICE, choices=available_languages()),
    FieldSpec(
        key="mod_details_visible",
        label=t('details'),
        tooltip=t('show_the_selected_mod_details_beside_the_library_in_list_and_tile_views_'),
        kind=FLAG,
    ),
    FieldSpec(
        key="gui_theme",
        label=t('theme'),
        tooltip=t('follow_the_operating_system_appearance_or_always_use_the_light_or_the_da'),
        kind=CHOICE,
        choices=("system", "light", "dark"),
    ),
    FieldSpec(
        key="gui_accent_color_mode",
        label=t('accent_colour'),
        tooltip=t('use_the_accent_colour_of_the_operating_system_or_pick_a_fixed_custom_acc'),
        kind=CHOICE,
        choices=("system", "custom"),
    ),
    FieldSpec(
        key="gui_accent_color",
        label=t('custom_accent_colour'),
        tooltip=t('colour_used_for_selection_highlights_tile_badges_and_checked_buttons_use'),
        kind=COLOR,
        depends_on=("gui_accent_color_mode", "custom"),
    ),
    FieldSpec(
        key="gui_text_color_mode",
        label=t('text_colour'),
        tooltip=t('use_the_default_text_colour_of_the_theme_or_pick_a_fixed_custom_text_col'),
        kind=CHOICE,
        choices=("system", "custom"),
    ),
    FieldSpec(
        key="gui_text_color",
        label=t('custom_text_colour'),
        tooltip=t('colour_used_for_window_button_input_and_tooltip_text_used_only_while_the'),
        kind=COLOR,
        depends_on=("gui_text_color_mode", "custom"),
    ),
    FieldSpec(
        key="gui_font_family",
        label=t('font_family'),
        tooltip=t('font_used_across_the_whole_interface_leave_empty_to_use_the_system_defau'),
        kind=FONT,
    ),
    FieldSpec(
        key="gui_font_size",
        label=t('font_size'),
        tooltip=t('point_size_of_the_interface_font_applies_immediately_after_saving'),
        kind=INT,
        minimum=6,
        maximum=40,
    ),
    FieldSpec(
        key="ui_scale_percent",
        label=t('interface_scale'),
        tooltip=t('scales_the_whole_interface_in_percent_restart_the_application_for_a_chan'),
        kind=INT,
        minimum=50,
        maximum=400,
    ),
)

MODS_VIEW_FIELDS = (
    FieldSpec(
        key="mod_view_mode",
        label=t('mods_view'),
        tooltip=t('show_mods_as_a_details_list_or_as_image_tiles_with_a_preview_panel_next_'),
        kind=CHOICE,
        choices=("list", "tiles"),
    ),
    FieldSpec(
        key="tile_size",
        label=t('tile_size'),
        tooltip=t('width_in_pixels_of_a_mod_tile_in_tile_view_ctrl_together_with_the_mouse_'),
        kind=INT,
        minimum=96,
        maximum=280,
    ),
    FieldSpec(
        key="placeholder_image_col_width",
        label=t('state_column_width'),
        tooltip=t('width_in_pixels_of_the_leading_install_state_column_in_the_mods_list'),
        kind=INT,
        minimum=16,
        maximum=400,
    ),
)

IMPORT_FIELDS = (
    FieldSpec(
        key="archive_import_mode",
        label=t('default_archive_import_mode'),
        tooltip=t('together_creates_one_folder_named_after_the_archive_separate_imports_eac'),
        kind=CHOICE,
        choices=("together", "separate"),
    ),
    FieldSpec(
        key="archive_preserve_structure",
        label=t('preserve_archive_folder_structure'),
        tooltip=t('keep_paths_inside_the_archive_separate_mode_creates_a_folder_for_each_mo'),
        kind=FLAG,
    ),
    FieldSpec(
        key="import_ignore_extensions",
        label=t('ignored_import_extensions'),
        tooltip=t('comma_separated_extensions_to_exclude_from_new_files_folders_and_archive'),
        kind=TEXT,
    ),
)

SETTINGS_SECTIONS = (
    (t('lists'), LIST_FIELDS),
    (t('import'), IMPORT_FIELDS),
    (t('appearance'), APPEARANCE_FIELDS),
    (t('mods_view'), MODS_VIEW_FIELDS),
    (t('shortcuts_label'), (FieldSpec("keyboard_shortcuts", t("shortcuts_label"), t("shortcuts_help"), SHORTCUTS),)),
)

GAME_PROFILE_FIELDS = (GAME_NAME_FIELD, *MODS_FIELDS)

PROFILE_KEYS = tuple(spec.key for spec in MODS_FIELDS)

NON_SETTING_KEYS = INTERNAL_KEYS | frozenset(PROFILE_KEYS)


def all_specs() -> tuple[FieldSpec, ...]:
    return tuple(spec for _section, specs in SETTINGS_SECTIONS for spec in specs)


def spec_for(key: str) -> FieldSpec | None:
    for spec in all_specs():
        if spec.key == key:
            return spec
    for spec in GAME_PROFILE_FIELDS:
        if spec.key == key:
            return spec
    return None


def label_for(key: str) -> str:
    spec = spec_for(key)
    return spec.label if spec else str(key).replace("_", " ")


def parse_int(spec: FieldSpec, value) -> int:
    try:
        number = int(str(value).strip().rstrip("%"))
    except (TypeError, ValueError):
        raise ValueError(t('value0_must_be_a_whole_number', value0=f'{spec.label}')) from None
    if spec.minimum is not None and spec.maximum is not None and not spec.minimum <= number <= spec.maximum:
        raise ValueError(t('value0_must_be_value1', value0=f'{spec.label}', value1=f'{spec.range_text}'))
    return number


def normalize_choice(spec: FieldSpec, value) -> str:
    text = str(value or "").strip().lower()
    return text if text in spec.choices else spec.choices[0]


def normalize_color(spec: FieldSpec, value) -> str:
    fallback = str(DEFAULT_CONFIG.get(spec.key, "") or "")
    return normalize_hex(value) or normalize_hex(fallback) or fallback


def read_value(spec: FieldSpec, cfg: dict):
    value = cfg.get(spec.key, DEFAULT_CONFIG.get(spec.key, ""))
    if spec.kind == SHORTCUTS:
        return validate_bindings(value or {})
    if spec.kind == FLAG:
        return bool(value)
    return str(value if value is not None else "")


def read_settings(cfg: dict) -> dict:
    return {spec.key: read_value(spec, cfg) for spec in all_specs()}


def default_settings() -> dict:
    return read_settings(dict(DEFAULT_CONFIG))


def coerce_value(spec: FieldSpec, value):
    if spec.kind == SHORTCUTS:
        if isinstance(value, str):
            import json
            value = json.loads(value)
        return validate_bindings(value)
    if spec.kind == FLAG:
        return bool(value)
    if spec.kind == INT:
        return parse_int(spec, value)
    if spec.kind == CHOICE:
        return normalize_choice(spec, value)
    if spec.kind == COLOR:
        return normalize_color(spec, value)
    return str(value or "").strip()


def coerce_settings(values: dict) -> dict:
    result = {}
    for spec in all_specs():
        if spec.key in values:
            result[spec.key] = coerce_value(spec, values[spec.key])
    return result


def coerce_game_profile(values: dict) -> dict:
    result = {}
    for spec in GAME_PROFILE_FIELDS:
        if spec.key in values:
            result[spec.key] = coerce_value(spec, values[spec.key])
    return result
