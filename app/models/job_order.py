"""Job order and the job-order <-> required-skill link table."""

from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import JobOrderStatus, values
from app.models.skill import Skill

job_order_skills = Table(
    "job_order_skills",
    Base.metadata,
    Column(
        "job_order_id",
        ForeignKey("job_orders.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "skill_id",
        ForeignKey("skills.id", ondelete="RESTRICT"),
        primary_key=True,
    ),
    Index("ix_job_order_skills_skill_id", "skill_id"),
)

_JOB_STATUS_VALUES = ", ".join(f"'{value}'" for value in values(JobOrderStatus))


class JobOrder(Base, TimestampMixin):
    __tablename__ = "job_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    job_title: Mapped[str] = mapped_column(String(150), nullable=False)
    location: Mapped[str] = mapped_column(String(150), nullable=False)
    min_experience_years: Mapped[Decimal] = mapped_column(Numeric(4, 1), nullable=False)
    number_of_openings: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    client_name: Mapped[str | None] = mapped_column(String(150))
    job_description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text(f"'{JobOrderStatus.OPEN.value}'"),
    )

    required_skills: Mapped[list[Skill]] = relationship(
        secondary=job_order_skills,
        lazy="selectin",
        order_by=Skill.name,
    )

    __table_args__ = (
        CheckConstraint("length(btrim(job_title)) > 0", name="job_title_not_blank"),
        CheckConstraint("length(btrim(location)) > 0", name="location_not_blank"),
        CheckConstraint(
            "min_experience_years >= 0 AND min_experience_years <= 60",
            name="min_experience_in_range",
        ),
        CheckConstraint("number_of_openings >= 1", name="openings_at_least_one"),
        CheckConstraint(f"status IN ({_JOB_STATUS_VALUES})", name="status_valid"),
        UniqueConstraint("tenant_id", "id", name="uq_job_orders_tenant_id_id"),
        Index("ix_job_orders_tenant_title", "tenant_id", "job_title"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<JobOrder id={self.id} tenant_id={self.tenant_id} title={self.job_title!r}>"
