"""Candidate and the candidate <-> skill link table."""

from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.skill import Skill

candidate_skills = Table(
    "candidate_skills",
    Base.metadata,
    Column(
        "candidate_id",
        ForeignKey("candidates.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    # RESTRICT: the skill vocabulary is shared, so a skill must never vanish
    # from under a candidate who claims it.
    Column(
        "skill_id",
        ForeignKey("skills.id", ondelete="RESTRICT"),
        primary_key=True,
    ),
    Index("ix_candidate_skills_skill_id", "skill_id"),
)


class Candidate(Base, TimestampMixin):
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # --- Core profile (Story 2.2 required fields) --------------------------
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    location: Mapped[str] = mapped_column(String(150), nullable=False)
    total_experience_years: Mapped[Decimal] = mapped_column(Numeric(4, 1), nullable=False)

    # --- Optional profile --------------------------------------------------
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(40))
    current_role: Mapped[str | None] = mapped_column(String(150))
    professional_summary: Mapped[str | None] = mapped_column(Text)

    # --- CV stored in PostgreSQL (Story 2) ---------------------------------
    cv_filename: Mapped[str | None] = mapped_column(String(255))
    cv_mime_type: Mapped[str | None] = mapped_column(String(120))
    cv_size_bytes: Mapped[int | None] = mapped_column(Integer)
    # deferred=True keeps the bytes out of every SELECT unless a query asks for
    # them explicitly. This makes "no CV bytes in list responses" a property of
    # the mapping rather than a rule each endpoint has to remember.
    cv_data: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    cv_evidence: Mapped[list[str] | None] = mapped_column(JSONB(none_as_null=True), deferred=True)

    skills: Mapped[list[Skill]] = relationship(
        secondary=candidate_skills,
        lazy="selectin",
        order_by=Skill.name,
    )

    @property
    def has_cv(self) -> bool:
        """Whether a CV is attached, without touching the deferred bytes.

        Keyed off the filename rather than ``cv_data`` so that reading it never
        triggers a load of the blob. The service writes and clears all four CV
        columns together, and ``ck_candidates_cv_metadata_complete`` enforces
        that bytes can never exist without this metadata.
        """
        return self.cv_filename is not None

    __table_args__ = (
        CheckConstraint("length(btrim(full_name)) > 0", name="full_name_not_blank"),
        CheckConstraint("length(btrim(location)) > 0", name="location_not_blank"),
        CheckConstraint(
            "total_experience_years >= 0 AND total_experience_years <= 60",
            name="experience_in_range",
        ),
        CheckConstraint(
            "cv_data IS NULL OR (cv_filename IS NOT NULL AND cv_mime_type IS NOT NULL)",
            name="cv_metadata_complete",
        ),
        # Target of the composite foreign keys on `submissions`. Redundant with
        # the primary key on its own, but it is what lets PostgreSQL guarantee
        # that a submission's candidate belongs to the submission's tenant.
        UniqueConstraint("tenant_id", "id", name="uq_candidates_tenant_id_id"),
        Index("ix_candidates_tenant_full_name", "tenant_id", "full_name"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Candidate id={self.id} tenant_id={self.tenant_id} name={self.full_name!r}>"
