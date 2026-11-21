"""Response envelopes shared by every resource."""

from math import ceil
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Standard pagination envelope used by every list endpoint.

    Keeping one shape across all four modules means the frontend can implement
    pagination, result counts and empty states exactly once.
    """

    items: list[T]
    total: int = Field(description="Total rows matching the filter, ignoring pagination")
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def build(cls, items: list[T], total: int, page: int, page_size: int) -> "Page[T]":
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=ceil(total / page_size) if page_size else 0,
        )


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """Documented shape of every non-2xx response."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error": {
                    "code": "NOT_FOUND",
                    "message": "Tenant 42 was not found.",
                    "details": {},
                }
            }
        }
    )

    error: ErrorDetail
