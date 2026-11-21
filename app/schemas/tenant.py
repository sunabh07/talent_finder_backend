"""Tenant request and response schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.normalization import normalize_display_name
from app.models.enums import TenantStatus


class TenantCreate(BaseModel):
    """Payload for Story 1.2 - Create Tenant.

    The assignment requires exactly one field: a non-blank Tenant Name.
    """

    name: str = Field(
        min_length=1,
        max_length=120,
        description="Display name of the sourcing channel, e.g. 'LinkedIn'",
        examples=["LinkedIn"],
    )

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        cleaned = normalize_display_name(value)
        if not cleaned:
            raise ValueError("Tenant name cannot be blank.")
        return cleaned


class TenantRead(BaseModel):
    """Row shape for the Tenant List table: Tenant Name, Tenant ID, Status."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    status: TenantStatus
    created_at: datetime
    updated_at: datetime


class TenantStats(BaseModel):
    """Backs the summary cards above the Tenant List table."""

    total: int
    active: int
    added_this_week: int
