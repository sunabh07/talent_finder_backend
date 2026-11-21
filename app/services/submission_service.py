"""Shortlisting and submission rules (Story 4)."""

from sqlalchemy import Row
from sqlalchemy.orm import Session

from app.core.deps import TenantScope
from app.core.errors import NotFoundError
from app.core.pagination import ListQuery
from app.models.submission import Submission
from app.repositories.candidate_repository import CandidateRepository
from app.repositories.job_order_repository import JobOrderRepository
from app.repositories.submission_repository import SubmissionRepository


class SubmissionService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = SubmissionRepository(session)
        self.candidates = CandidateRepository(session)
        self.job_orders = JobOrderRepository(session)

    # --- Queries -------------------------------------------------------------

    def list_submissions(self, scope: TenantScope, query: ListQuery) -> tuple[list[Row], int]:
        return self.repo.list(scope.id, query)

    def get_stats(self, scope: TenantScope) -> tuple[int, int, int]:
        return self.repo.stats(scope.id)

    # --- Commands --------------------------------------------------------------

    def shortlist(
        self, scope: TenantScope, job_order_id: int, candidate_id: int
    ) -> tuple[Submission, bool]:
        """Shortlist a candidate against a job order, idempotently.

        Both records are fetched *through the tenant scope*, so a candidate or
        job order belonging to another tenant simply is not found and the
        request 404s before any write is attempted.

        That check is belt; the braces are the composite foreign keys on
        ``submissions``, which make a cross-tenant row impossible even if this
        method were bypassed entirely. The service check exists to return a
        clean 404 rather than a constraint violation - not because the
        database needs the help.
        """
        job_order = self.job_orders.get(scope.id, job_order_id)
        if job_order is None:
            raise NotFoundError(
                f"Job order {job_order_id} was not found in tenant '{scope.name}'.",
                {"job_order_id": job_order_id, "tenant_id": scope.id},
            )

        candidate = self.candidates.get(scope.id, candidate_id)
        if candidate is None:
            raise NotFoundError(
                f"Candidate {candidate_id} was not found in tenant '{scope.name}'.",
                {"candidate_id": candidate_id, "tenant_id": scope.id},
            )

        submission, already_existed = self.repo.shortlist(
            tenant_id=scope.id,
            candidate_id=candidate.id,
            job_order_id=job_order.id,
        )
        self.session.commit()
        self.session.refresh(submission)
        return submission, already_existed
