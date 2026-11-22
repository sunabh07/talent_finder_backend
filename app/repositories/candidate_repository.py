"""Data access for candidates.

**Every method takes ``tenant_id`` as a required argument.** There is no
overload that omits it, so an unscoped candidate query cannot be written by
accident - it would be a missing-argument error at the call site.
"""

# Repository classes define a ``list`` method, which shadows the builtin inside
# the class body. Deferring annotation evaluation keeps ``list[...]`` hints working.
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, exists, func, or_, select
from sqlalchemy.orm import undefer

from app.core.pagination import ListQuery
from app.models.candidate import Candidate, candidate_skills
from app.models.job_order import JobOrder
from app.models.skill import Skill
from app.models.submission import Submission
from app.repositories.base import BaseRepository, apply_window, count_rows

SORTABLE: dict[str, object] = {
    "full_name": Candidate.full_name,
    "location": Candidate.location,
    "total_experience_years": Candidate.total_experience_years,
    "current_role": Candidate.current_role,
    "created_at": Candidate.created_at,
    "id": Candidate.id,
}
DEFAULT_SORT = "full_name"


class CandidateRepository(BaseRepository):
    def cv_evidence_for(self, tenant_id: int, candidate_ids: list[int]) -> dict[int, list[str]]:
        if not candidate_ids:
            return {}
        stmt = select(Candidate.id, Candidate.cv_evidence).where(
            Candidate.tenant_id == tenant_id,
            Candidate.id.in_(candidate_ids),
            Candidate.cv_evidence.is_not(None),
        )
        return {candidate_id: items for candidate_id, items in self.session.execute(stmt) if items}

    # --- Reads -------------------------------------------------------------

    def get(self, tenant_id: int, candidate_id: int) -> Candidate | None:
        """Fetch one candidate *within* a tenant.

        The tenant predicate is part of the lookup rather than a check applied
        afterwards, so a foreign-tenant id simply returns nothing to leak.
        """
        stmt = select(Candidate).where(
            Candidate.id == candidate_id,
            Candidate.tenant_id == tenant_id,
        )
        return self.session.scalars(stmt).first()

    def list(self, tenant_id: int, query: ListQuery) -> tuple[list[Candidate], int]:
        stmt = select(Candidate).where(Candidate.tenant_id == tenant_id)

        if query.q:
            stmt = stmt.where(self._search_filter(query.q))

        column, descending = query.validated_sort(SORTABLE, DEFAULT_SORT)
        order = column.desc() if descending else column.asc()  # type: ignore[union-attr]
        stmt = stmt.order_by(order, Candidate.id.asc())

        total = count_rows(self.session, stmt)
        return list(self.session.scalars(apply_window(stmt, query)).all()), total

    @staticmethod
    def _search_filter(term: str):
        """Match the text fields a recruiter would scan, plus skill names.

        Skills are matched with EXISTS rather than a JOIN: a join against a
        many-to-many would multiply candidate rows and silently corrupt both
        the result set and the total count.
        """
        pattern = f"%{term}%"
        skill_match = (
            select(1)
            .select_from(candidate_skills)
            .join(Skill, Skill.id == candidate_skills.c.skill_id)
            .where(
                candidate_skills.c.candidate_id == Candidate.id,
                Skill.name.ilike(pattern),
            )
        )
        return or_(
            Candidate.full_name.ilike(pattern),
            Candidate.location.ilike(pattern),
            Candidate.current_role.ilike(pattern),
            Candidate.email.ilike(pattern),
            exists(skill_match),
        )

    def load_with_cv(self, tenant_id: int, candidate_id: int) -> Candidate | None:
        """Fetch a candidate *including* the deferred CV bytes.

        The only query in the codebase that undefers ``cv_data``. Everything
        else leaves the blob in the database.
        """
        stmt = (
            select(Candidate)
            .where(Candidate.id == candidate_id, Candidate.tenant_id == tenant_id)
            .options(undefer(Candidate.cv_data))
        )
        return self.session.scalars(stmt).first()

    def submissions_for(self, tenant_id: int, candidate_id: int) -> list[tuple]:
        """Job orders this candidate has been shortlisted for, newest first."""
        stmt: Select = (
            select(
                Submission.id,
                Submission.job_order_id,
                JobOrder.job_title,
                JobOrder.client_name,
                Submission.status,
                Submission.created_at,
            )
            .join(JobOrder, JobOrder.id == Submission.job_order_id)
            .where(
                Submission.tenant_id == tenant_id,
                Submission.candidate_id == candidate_id,
            )
            .order_by(Submission.created_at.desc(), Submission.id.desc())
        )
        return list(self.session.execute(stmt).all())

    def stats(self, tenant_id: int) -> tuple[int, int, int]:
        """``(total, added_in_last_7_days, with_cv)`` for the summary cards."""
        since = datetime.now(UTC) - timedelta(days=7)
        row = self.session.execute(
            select(
                func.count(Candidate.id),
                func.count(Candidate.id).filter(Candidate.created_at >= since),
                func.count(Candidate.id).filter(Candidate.cv_filename.isnot(None)),
            ).where(Candidate.tenant_id == tenant_id)
        ).one()
        return int(row[0]), int(row[1]), int(row[2])

    # --- Writes ------------------------------------------------------------

    def add(self, candidate: Candidate) -> Candidate:
        self.session.add(candidate)
        self.session.flush()
        return candidate

    def delete(self, candidate: Candidate) -> None:
        self.session.delete(candidate)
        self.session.flush()
