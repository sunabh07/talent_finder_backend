"""Tenant - the isolation boundary for every other record.

In this assignment a tenant is a *sourcing channel* (LinkedIn, Naukri,
Monster): the recruitment agency segregates its candidate and job-order data by
the channel it came through.
"""

from sqlalchemy import CheckConstraint, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import TenantStatus, values


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text(f"'{TenantStatus.ACTIVE.value}'"),
    )

    __table_args__ = (
        CheckConstraint("length(btrim(name)) > 0", name="name_not_blank"),
        CheckConstraint(
            "status IN ({})".format(", ".join(f"'{v}'" for v in values(TenantStatus))),
            name="status_valid",
        ),
        # Case-insensitive uniqueness: "LinkedIn" and "linkedin" are one tenant.
        Index("uq_tenants_name_lower", text("lower(name)"), unique=True),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Tenant id={self.id} name={self.name!r}>"
