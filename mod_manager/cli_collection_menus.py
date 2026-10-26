from __future__ import annotations

from dataclasses import dataclass

from . import cli_menu_io as console
from .cli import _print_mods, _print_presets, selected_items
from .cli_environment import require_paths
from .cli_menu_actions import action_label, print_actions
from .cli_navigation import navigate_page
from .cli_parser import _order
from .cli_utils import parse_multi_choice
from .collection_utils import page_size, page_slice, paginate
from .mods import list_broken_links, mods_view
from .presets import preset_mods_to_install, presets_view
from .storage import load_config


@dataclass
class ModView:
    page: int = 1
    label: str = ""
    search: str = ""
    order: str = "default"
    favorite: bool = False

    def snapshot(self, cfg: dict):
        view = mods_view(cfg, self.page, self.label, self.search, self.order, self.favorite)
        self.page = view[2]
        return view

    def arguments(self, *, label_action: bool = False) -> list[str]:
        arguments = ["--page", str(self.page), "--filter-label" if label_action else "--label", self.label, "--search", self.search, "--order", self.order]
        return arguments + (["--favorite"] if self.favorite else [])


def _print_mod_items(cfg: dict, state: ModView, view) -> None:
    print("\nItems")
    print(f"Order: {state.order}; Label: {state.label or '-'}; Search: {state.search or '-'}; Favorites: {state.favorite}")
    _print_mods(cfg, state.page, state.label, state.search, state.order, state.favorite, interactive=True, view=view)


@console.interactive
def _page_change(page: int, pages: int, command: str, args: list[str]) -> int | None:
    if command == "page" and not args:
        indexes = console.read_indexes(range(pages), "page", single=True)
        if indexes is None:
            return None
        args = [str(indexes[0])]
    return navigate_page(command, args, page, pages)


@console.interactive
def _pages(page: int, pages: int, command: str = "", args: list[str] | None = None) -> int | None:
    if command:
        return _page_change(page, pages, command, args or [])
    while True:
        print(f"\nPages: current {page}, available 1–{pages}")
        print_actions("Pages")
        command, args = console.read_action("Pages")
        if command == "back":
            return None
        selected = _page_change(page, pages, command, args)
        if selected is not None:
            return selected


def _indexes(args: list[str], shown: list, noun: str) -> list[int] | None:
    indexes = parse_multi_choice(" ".join(args)) if args else console.read_indexes(shown, noun)
    if indexes is not None:
        selected_items(shown, indexes)
    return indexes


@console.interactive
def _sort_mods(state: ModView) -> None:
    modes = ("default", "created_date", "name", "label", "installed", "last_managed")
    print("\nSort fields")
    for index, mode in enumerate(modes, 1):
        print(f"  #{index} {mode.replace('_', ' ').capitalize()}")
    selected = console.read_indexes(list(modes), "sort field", single=True)
    if selected is None:
        return
    descending = console.ask_yes_no("Descending order?")
    state.order = ("-" if descending else "") + modes[selected[0] - 1]
    state.page = 1


@console.interactive
def _label_change(command: str, cfg: dict, state: ModView) -> bool:
    if command == "clear":
        state.label, state.page = "", 1
    elif command == "filter":
        state.label = console.read_text("Label filter", description="Enter a label, or leave empty to show all labels.")
        state.page = 1
    else:
        indexes = console.read_indexes(state.snapshot(cfg)[1], "mod")
        if indexes is None:
            return False
        label = console.read_text("Label", description="Enter the label to assign or remove.")
        if not label:
            print("Cancelled: empty label.")
            return False
        console.execute(["mods", "label-add" if command == "add" else "label-remove", label, ",".join(map(str, indexes)), *state.arguments(label_action=True)])
    return True


@console.interactive
def _labels(cfg: dict, state: ModView) -> None:
    while True:
        console.header("Mods > Labels", cfg)
        _print_mod_items(cfg, state, state.snapshot(cfg))
        print_actions("Labels")
        command, _args = console.read_action("Labels")
        if command == "back" or _label_change(command, cfg, state):
            return


@console.interactive
def _favorite_change(command: str, cfg: dict, state: ModView, shown: list) -> bool:
    if command == "filter":
        state.favorite, state.page = not state.favorite, 1
    else:
        indexes = console.read_indexes(shown, "mod")
        if indexes is None:
            return False
        console.execute(["mods", "favorite-add" if command == "add" else "favorite-remove", ",".join(map(str, indexes)), *state.arguments(label_action=True)])
    return True


@console.interactive
def _favorites(cfg: dict, state: ModView) -> None:
    while True:
        console.header("Mods > Favorites", cfg)
        view = state.snapshot(cfg)
        _print_mod_items(cfg, state, view)
        print_actions("Favorites")
        command, _args = console.read_action("Favorites")
        if command == "back" or _favorite_change(command, cfg, state, view[1]):
            return


@console.interactive
def _mod_action(command: str, args: list[str], cfg: dict, state: ModView, view) -> None:
    _items, shown, _page, pages, _label_values = view
    if command == "pages":
        state.page = _pages(state.page, pages) or state.page
    elif command in {"next", "prev", "page", "refresh"}:
        state.page = _pages(state.page, pages, command, args) or state.page
    elif command == "clear":
        state.page, state.label, state.search, state.favorite = 1, "", "", False
    elif command == "search":
        state.search = " ".join(args) if args else console.read_text("Search text", description="Enter text to search mod names. Empty text clears the search.")
        state.page = 1
    elif command == "l":
        state.label, state.page = " ".join(args), 1
    elif command == "labels":
        _labels(cfg, state)
    elif command == "favorites":
        _favorites(cfg, state)
    elif command == "favorite":
        state.favorite, state.page = not state.favorite, 1
    elif command == "order":
        if args:
            state.order, state.page = _order(" ".join(args)), 1
        else:
            _sort_mods(state)
    elif command in {"l+", "l-", "favorite-add", "favorite-remove", "label"}:
        operands = []
        if command == "label":
            if len(args) != 3 or args[0] not in {"add", "remove"}:
                raise ValueError('Use label add/remove "label" <mod number or name>.')
            operation = "label-" + args[0]
            operands = [args[1]]
            indexes = parse_multi_choice(args[2]) if args[2].isdecimal() else [index for index, mod in enumerate(shown, 1) if mod.name == args[2]]
            selected_items(shown, indexes)
            console.execute(["mods", operation, *operands, ",".join(map(str, indexes)), *state.arguments(label_action=True)])
            return
        if command in {"l+", "l-"}:
            if len(args) != 2:
                raise ValueError(f'Use /l+ "label" 1,3 or /l- "label" 1,3. For prompts choose {action_label("Mods", "labels")}.')
            operands = [args[0]]
            args = args[1:]
        indexes = _indexes(args, shown, "mod")
        if indexes is not None:
            operation = {"l+": "label-add", "l-": "label-remove"}.get(command, command)
            console.execute(["mods", operation, *operands, ",".join(map(str, indexes)), *state.arguments(label_action=True)])
    elif command in {"install", "uninstall", "toggle"}:
        target = ModView(state.page, state.label, state.search, state.order, state.favorite)
        operands = []
        if command == "toggle":
            indexes = _indexes(args, shown, "mod")
            if indexes is None:
                return
            shown = selected_items(shown, indexes)
            operands = [",".join(map(str, indexes))]
        elif args:
            target.page = navigate_page("page", args, state.page, pages)
            if int(args[0]) != target.page:
                return
            shown = target.snapshot(cfg)[1]
        if not shown:
            print("No mods available on this page. Nothing changed.")
            return
        require_paths(cfg)
        overwrite = False
        if command != "uninstall":
            overwrite = console.confirm_overwrite([mod for mod in shown if not mod.installed])
            if overwrite is None:
                print("Cancelled.")
                return
        flags = ["--overwrite"] if overwrite else []
        console.execute(["mods", command, *operands, *target.arguments(), *flags])


@console.interactive
def menu_mods_toggle(cfg: dict) -> None:
    require_paths(cfg, game=False)
    state = ModView()
    while True:
        cfg = load_config()
        require_paths(cfg, game=False)
        console.header("Mods", cfg)
        view = state.snapshot(cfg)
        _print_mod_items(cfg, state, view)
        print_actions("Mods")
        command, args = console.read_action("Mods")
        if command == "back":
            return
        _mod_action(command, args, cfg, state, view)


@console.interactive
def _preset_action(command: str, args: list[str], cfg: dict, page: int, names: list[str]) -> None:
    if command == "save":
        name = " ".join(args) if args else console.read_text("Preset name", description="Enter a name for the installed mods. An existing name is updated.")
        if name:
            console.execute(["presets", "save", name])
        else:
            print("Cancelled: empty preset name.")
        return
    indexes = _indexes(args, names, "preset")
    if indexes is None:
        return
    flags = []
    if command == "toggle":
        require_paths(cfg)
        selected = selected_items(names, indexes)
        work, _missing = preset_mods_to_install(cfg, selected)
        overwrite = console.confirm_overwrite(work)
        if overwrite is None:
            print("Cancelled.")
            return
        flags = ["--overwrite"] if overwrite else []
    console.execute(["presets", command, ",".join(map(str, indexes)), "--page", str(page), *flags])


@console.interactive
def menu_presets(cfg: dict) -> None:
    page = 1
    while True:
        cfg = load_config()
        console.header("Presets", cfg)
        _presets, _keys, names, page, pages = presets_view(cfg, page)
        print("\nItems")
        _print_presets(cfg, page, interactive=True)
        print_actions("Presets")
        command, args = console.read_action("Presets")
        if command == "back":
            return
        if command == "pages":
            page = _pages(page, pages) or page
        elif command in {"next", "prev", "page", "refresh"}:
            page = _pages(page, pages, command, args) or page
        else:
            _preset_action(command, args, cfg, page, names)


@console.interactive
def _broken_action(command: str, args: list[str], cfg: dict, page: int, shown: list) -> None:
    indexes = list(range(1, len(shown) + 1)) if command == "all" else _indexes(args, shown, "broken link")
    if not indexes:
        print("No broken links selected. Nothing changed.")
        return
    offset = (page - 1) * page_size(cfg)
    console.execute(["broken", "remove", ",".join(str(index + offset) for index in indexes)])


@console.interactive
def menu_fix_broken(cfg: dict) -> None:
    require_paths(cfg, source=False)
    page = 1
    while True:
        console.header("Broken links", cfg)
        broken = list_broken_links(cfg)
        page, pages = paginate(len(broken), page, cfg)
        shown = page_slice(broken, page, cfg)
        print(f"\nItems — Page {page}/{pages}")
        for index, mod in enumerate(shown, 1):
            print(f"  #{index} {mod.name} -> {mod.src}")
        if not broken:
            print("No broken links detected.")
        print_actions("Broken links")
        command, args = console.read_action("Broken links")
        if command == "back":
            return
        if command == "pages":
            page = _pages(page, pages) or page
        elif command in {"next", "prev", "page", "refresh"}:
            page = _pages(page, pages, command, args) or page
        else:
            _broken_action(command, args, cfg, page, shown)
