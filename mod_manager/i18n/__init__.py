from __future__ import annotations

import json
from importlib import resources


def available_languages() -> tuple[str, ...]:
    return tuple(sorted(item.name for item in resources.files(__package__).iterdir()
                        if item.is_dir() and item.joinpath("strings.json").is_file()))


def _catalog(language: str) -> dict[str, str]:
    value = json.loads(resources.files(__package__).joinpath(language, "strings.json").read_text(encoding="utf-8"))
    if not isinstance(value, dict) or any(not isinstance(text, str) for text in value.values()):
        raise ValueError(f"Invalid translation catalog: {language}")
    return value


_english = _catalog("en")
_strings = dict(_english)
_language = "en"


def setup(language: str = "en") -> None:
    global _strings, _language
    _language = language if language in available_languages() else "en"
    try:
        _strings = {**_english, **_catalog(_language)}
    except (OSError, ValueError):
        _language = "en"
        _strings = dict(_english)


def get_current_language() -> str:
    return _language


def t(key: str, **values) -> str:
    text = _strings.get(key, key)
    return text.format(**values) if values else text
