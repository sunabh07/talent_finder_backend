"""Shared list-query primitives: pagination, search and whitelisted sorting."""

from dataclasses import dataclass
from typing import Literal

from fastapi import Query

from app.core.config import settings
from app.core.errors import ValidationError
from app.core.normalization import normalize_search_term

SortDirection = Literal["asc", "desc"]


@dataclass(frozen=True, slots=True)
class ListQuery:
    """Everything a list endpoint needs, validated once at the boundary."""

    q: str | None
    sort_by: str
    sort_dir: SortDirection
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    def validated_sort(self, allowed: dict[str, object], default: str) -> tuple[object, bool]:
        """Resolve ``sort_by`` against a per-resource whitelist.

        Returning the mapped column (never the raw string) is what makes the
        sort injection-proof: an unknown key is rejected outright rather than
        interpolated into SQL.
        """
        key = self.sort_by or default
        if key not in allowed:
            raise ValidationError(
                f"Cannot sort by '{key}'.",
                {"allowed_sort_by": sorted(allowed)},
            )
        return allowed[key], self.sort_dir == "desc"


def list_query_params(
    q: str | None = Query(None, max_length=200, description="Free-text search"),
    sort_by: str | None = Query(None, description="Field to sort by (resource-specific)"),
    sort_dir: SortDirection = Query("asc", description="Sort direction"),
    page: int = Query(1, ge=1, description="1-based page number"),
    page_size: int | None = Query(None, ge=1, description="Items per page"),
) -> ListQuery:
    """FastAPI dependency producing a validated :class:`ListQuery`."""
    size = page_size or settings.default_page_size
    if size > settings.max_page_size:
        raise ValidationError(
            f"page_size may not exceed {settings.max_page_size}.",
            {"max_page_size": settings.max_page_size},
        )
    return ListQuery(
        q=normalize_search_term(q),
        sort_by=sort_by or "",
        sort_dir=sort_dir,
        page=page,
        page_size=size,
    )
