from __future__ import annotations

import sys
from typing import Callable, List
from collections.abc import Mapping

from .collection_utils import filter_items_by_query, page_slice, paginate, sort_items
from .folder_actions import ensure_paths, open_folder, select_in_explorer
from .storage import load_label_state
from .cli_commands import command_description

_PT_AVAILABLE = False

def prompt(msg: str) -> str:
    return input(msg)

def pause(msg: str = "Press Enter to continue...") -> None:
    prompt(f"{msg}")

def truncate_text(text: str, max_len: int, suffix: str = "...") -> str:
    if max_len <= 0:
        return ""
    if text is None:
        return ""
    s = str(text)
    if len(s) <= max_len:
        return s
    if max_len <= len(suffix):
        return s[:max_len]
    return s[: max_len - len(suffix)] + suffix

def format_order_short(order_mode: str) -> str:
    reverse = (order_mode or "").startswith("-")
    mode = (order_mode or "default")[1:] if reverse else (order_mode or "default")
    aliases = {"d": "default", "cd": "created_date", "created date": "created_date"}
    mode = aliases.get(mode, mode)
    suffix = " desc" if reverse else " asc"
    return f"{mode}{suffix}"

def parse_multi_choice(choice: str) -> List[int]:
    if not choice.strip():
        return []
    parts = [part.strip() for part in choice.split(",")]
    if any(not part.isascii() or not part.isdecimal() or int(part) < 1 for part in parts):
        raise ValueError("Use positive indexes separated by commas, for example 1,3,5.")
    return list(dict.fromkeys(int(part) for part in parts))


def parse_page_choice(choice: str) -> int | None:
    c = choice.strip().lower()
    if c.startswith("p") and c[1:].isdigit():
        return int(c[1:])
    return None

def print_pager(pages: int, current: int):
    if pages <= 1:
        return
    labels = []
    for i in range(1, pages + 1):
        labels.append(f"[p{i}]" if i != current else f"(p{i})")
    print("Pages:")
    for i in range(0, len(labels), 10):
        print(" ".join(labels[i:i+10]))

def _normalize_label(s: str) -> str:
    s = (s or "").strip().lower().replace("_", " ")
    s = " ".join(s.split())
    return s

def _labels_for_completion() -> List[str]:
    try:
        values = list(load_label_state().definitions)
    except Exception:
        values = []
    seen = set()
    out: List[str] = []
    for v in values:
        if not v:
            continue
        disp = " ".join(str(v).replace("_", " ").split())
        key = _normalize_label(disp)
        if key and key not in seen:
            seen.add(key)
            out.append(disp)
    return out

def _try_prompt_toolkit():
    global _PT_AVAILABLE
    try:
        from prompt_toolkit import prompt as pt_prompt
        from prompt_toolkit.formatted_text import FormattedText
        _PT_AVAILABLE = True
        return pt_prompt, FormattedText
    except Exception:
        _PT_AVAILABLE = False
        return None, None

class _CmdCompleter:
    def __init__(self, get_cmds: Callable[[], list[str] | Mapping[str, str]]):
        self.get_cmds = get_cmds

    def get_completions(self, document, complete_event):
        text = document.text or ""
        from prompt_toolkit.completion import Completion

        base = text.lower()
        cmds = self.get_cmds() or []

        for c in cmds:
            if c.lower().startswith(base):
                description = cmds[c] if isinstance(cmds, Mapping) else command_description(c)
                yield Completion(c, start_position=-len(text), display=c, display_meta=description)

        prefix = ""
        if base.startswith("/l+ "):
            prefix = "/l+ "
        elif base.startswith("/l- "):
            prefix = "/l- "
        elif base.startswith("/l "):
            prefix = "/l "

        if prefix:
            rest = text[len(prefix):]
            frag = rest.strip()
            if frag.startswith('"') or frag.startswith("'"):
                frag = frag[1:]
            nf = _normalize_label(frag)
            for lbl in _labels_for_completion():
                if not nf or _normalize_label(lbl).startswith(nf):
                    yield Completion(f'"{lbl}" ', start_position=-len(rest), display=lbl)

        yield Completion("", start_position=0, display="(keep typing)")

    async def get_completions_async(self, document, complete_event):
        for c in self.get_completions(document, complete_event):
            yield c

def smart_prompt(
    msg: str,
    get_commands: Callable[[], list[str] | Mapping[str, str]] | None = None,
    placeholder: str = "Choose an action number; type ? for help",
) -> str:
    pt_prompt, FormattedText = _try_prompt_toolkit() if sys.stdin.isatty() else (None, None)

    if not pt_prompt or not get_commands:
        text = prompt(msg)
        return text

    completer = _CmdCompleter(get_commands)

    def bottom_toolbar():
        try:
            from prompt_toolkit.application.current import get_app
            buf = get_app().current_buffer
            return FormattedText([("", placeholder)]) if not (buf.text or "") else ""
        except Exception:
            return ""

    return pt_prompt(
        msg,
        completer=completer,
        complete_while_typing=True,
        bottom_toolbar=bottom_toolbar,
    )
