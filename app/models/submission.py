"""Submission - a candidate put forward for a job order.

This table carries the strongest integrity guarantee in the schema. Instead of
three independent foreign keys plus a service-level "are these the same
tenant?" check, it uses **composite foreign keys**::

    (tenant_id, candidate_id) -> candidates (tenant_id, id)
    (tenant_id, job_order_id) -> job_orders (tenant_id, id)

Because ``tenant_id`` is a single shared column on this row, a submission can
only exist when the candidate *and* the job order both live in that one tenant.
Cross-tenant shortlisting is rejected by PostgreSQL, not by an ``if`` statement
that a future refactor might quietly delete.
"""

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.candidate import Candidate
from app.models.enums import SubmissionStatus, values
from app.models.job_order import JobOrder

_SUBMISSION_STATUS_VALUES = ", ".join(f"'{value}'" for value in values(SubmissionStatus))


class Submission(Base, TimestampMixin):
    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    candidate_id: Mapped[int] = mapped_column(nullable=False)
    job_order_id: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text(f"'{SubmissionStatus.SHORTLISTED.value}'"),
    )

    # These relationships are read-only on purpose. `tenant_id` is shared by
    # both composite foreign keys, so letting more than one relationship write
    # it would make the authoritative value ambiguous. Services assign the
    # scalar columns explicitly after validating scope; the ORM only reads.
    candidate: Mapped[Candidate] = relationship(
        viewonly=True,
        lazy="selectin",
        primaryjoin=lambda: Submission.candidate_id == Candidate.id,
        foreign_keys=lambda: [Submission.candidate_id],
    )
    job_order: Mapped[JobOrder] = relationship(
        viewonly=True,
        lazy="selectin",
        primaryjoin=lambda: Submission.job_order_id == JobOrder.id,
        foreign_keys=lambda: [Submission.job_order_id],
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "candidate_id"],
            ["candidates.tenant_id", "candidates.id"],
            name="fk_submissions_tenant_candidate",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "job_order_id"],
            ["job_orders.tenant_id", "job_orders.id"],
            name="fk_submissions_tenant_job_order",
            ondelete="CASCADE",
        ),
        # Makes "shortlist" idempotent at the database level: a repeated click
        # can be absorbed with ON CONFLICT DO NOTHING instead of a read-then-
        # write race.
        UniqueConstraint("candidate_id", "job_order_id", name="uq_submissions_candidate_job"),
        CheckConstraint(f"status IN ({_SUBMISSION_STATUS_VALUES})", name="status_valid"),
        Index("ix_submissions_tenant_job_order", "tenant_id", "job_order_id"),
        Index("ix_submissions_tenant_candidate", "tenant_id", "candidate_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Submission id={self.id} tenant_id={self.tenant_id} "
            f"candidate_id={self.candidate_id} job_order_id={self.job_order_id}>"
        )
