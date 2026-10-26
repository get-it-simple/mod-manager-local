from __future__ import annotations

from .models import ModItem
from . import settings_schema
from app_paths import DEFAULT_CONFIG


def page_size(cfg: dict) -> int:
    return settings_schema.parse_int(settings_schema.spec_for("page_size"), cfg.get("page_size", DEFAULT_CONFIG["page_size"]))


def paginate(total: int, page: int, cfg: dict) -> tuple[int, int]:
    size = page_size(cfg)
    pages = max(1, (total + size - 1) // size)
    return max(1, min(page, pages)), pages


def page_slice(items: list, page: int, cfg: dict) -> list:
    size = page_size(cfg)
    return items[(page - 1) * size:page * size]


def filter_items_by_query(items: list[ModItem], query: str) -> list[ModItem]:
    query = (query or "").lower()
    return [item for item in items if query in item.name.lower()] if query else items


def sort_items(items: list[ModItem], order_mode: str) -> list[ModItem]:
    if order_mode in {"cd", "created date"}:
        try:
            return sorted(items, key=lambda item: item.src.stat().st_ctime, reverse=True)
        except OSError:
            pass
    return sorted(items, key=lambda item: (not item.is_dir, item.name.lower()))
