from __future__ import annotations

from ..i18n import get_current_language, t



def system_language() -> str:
    return get_current_language()


def system_action_text(key: str) -> str:
    return t(key + "_action")
