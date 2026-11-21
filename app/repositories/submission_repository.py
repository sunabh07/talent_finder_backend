"""Data access for submissions (Story 4)."""

# Repository classes define a ``list`` method, which shadows the builtin inside
# the class body. Deferring annotation evaluation keeps ``list[...]`` hints working.
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import Row, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.pagination import ListQuery
from app.models.candidate import Candidate
from app.models.enums import SubmissionStatus
from app.models.job_order import JobOrder
from app.models.submission import Submission
from app.repositories.base import BaseRepository, apply_window, count_rows

SORTABLE: dict[str, object] = {
    "job_title": JobOrder.job_title,
    "candidate_name": Candidate.full_name,
    "status": Submission.status,
    "created_at": Submission.created_at,
    "id": Submission.id,
}
DEFAULT_SORT = "created_at"


class SubmissionRepository(BaseRepository):
    def _base_select(self, tenant_id: int):
        """Submissions joined to the two names the list screen shows."""
        return (
            select(
                Submission.id,
                Submission.job_order_id,
                JobOrder.job_title,
                JobOrder.client_name,
                Submission.candidate_id,
                Candidate.full_name,
                Submission.status,
                Submission.created_at,
            )
            .join(JobOrder, JobOrder.id == Submission.job_order_id)
            .join(Candidate, Candidate.id == Submission.candidate_id)
            .where(Submission.tenant_id == tenant_id)
        )

    def list(self, tenant_id: int, query: ListQuery) -> tuple[list[Row], int]:
        stmt = self._base_select(tenant_id)

        if query.q:
            pattern = f"%{query.q}%"
            stmt = stmt.where(
                or_(
                    JobOrder.job_title.ilike(pattern),
                    JobOrder.client_name.ilike(pattern),
                    Candidate.full_name.ilike(pattern),
                    Submission.status.ilike(pattern),
                )
            )

        column, descending = query.validated_sort(SORTABLE, DEFAULT_SORT)
        order = column.desc() if descending else column.asc()  # type: ignore[union-attr]
        stmt = stmt.order_by(order, Submission.id.desc())

        total = count_rows(self.session, stmt)
        return list(self.session.execute(apply_window(stmt, query)).all()), total

    def get(self, tenant_id: int, submission_id: int) -> Submission | None:
        stmt = select(Submission).where(
            Submission.id == submission_id,
            Submission.tenant_id == tenant_id,
        )
        return self.session.scalars(stmt).first()

    def find_pair(self, candidate_id: int, job_order_id: int) -> Submission | None:
        stmt = select(Submission).where(
            Submission.candidate_id == candidate_id,
            Submission.job_order_id == job_order_id,
        )
        return self.session.scalars(stmt).first()

    def shortlist(
        self, tenant_id: int, candidate_id: int, job_order_id: int
    ) -> tuple[Submission, bool]:
        """Insert a submission, absorbing a repeat click.

        ``ON CONFLICT DO NOTHING`` against ``uq_submissions_candidate_job``
        makes this idempotent **in a single statement**. A read-then-write
        ("does it exist? no, insert it") would lose a race between two rapid
        clicks and raise an IntegrityError on the second; here the database
        resolves it.

        Returns ``(submission, already_existed)``.
        """
        stmt = (
            pg_insert(Submission)
            .values(
                tenant_id=tenant_id,
                candidate_id=candidate_id,
                job_order_id=job_order_id,
                status=SubmissionStatus.SHORTLISTED.value,
            )
            .on_conflict_do_nothing(constraint="uq_submissions_candidate_job")
            .returning(Submission.id)
        )
        inserted_id = self.session.scalar(stmt)

        if inserted_id is None:
            # Nothing inserted: the pair already existed. Fetch and report it.
            existing = self.find_pair(candidate_id, job_order_id)
            assert existing is not None  # the conflict proves it is there
            return existing, True

        self.session.flush()
        created = self.session.get(Submission, inserted_id)
        assert created is not None
        return created, False

    def stats(self, tenant_id: int) -> tuple[int, int, int]:
        """``(total, added_in_last_7_days, distinct_job_orders)``."""
        since = datetime.now(UTC) - timedelta(days=7)
        row = self.session.execute(
            select(
                func.count(Submission.id),
                func.count(Submission.id).filter(Submission.created_at >= since),
                func.count(func.distinct(Submission.job_order_id)),
            ).where(Submission.tenant_id == tenant_id)
        ).one()
        return int(row[0]), int(row[1]), int(row[2])
