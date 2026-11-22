"""Candidate controller: entity <-> schema mapping."""

from sqlalchemy.orm import Session

from app.core.deps import TenantScope
from app.core.pagination import ListQuery
from app.models.candidate import Candidate
from app.schemas.candidate import (
    CandidateCreate,
    CandidateDetail,
    CandidateListItem,
    CandidateStats,
    CandidateSubmissionLink,
    CandidateUpdate,
    CvUploadResult,
)
from app.schemas.common import Page
from app.services.candidate_service import CandidateService


class CandidateController:
    def __init__(self, session: Session) -> None:
        self.service = CandidateService(session)

    def list_candidates(self, scope: TenantScope, query: ListQuery) -> Page[CandidateListItem]:
        candidates, total = self.service.list_candidates(scope, query)
        return Page.build(
            items=[CandidateListItem.model_validate(c) for c in candidates],
            total=total,
            page=query.page,
            page_size=query.page_size,
        )

    def get_candidate(self, scope: TenantScope, candidate_id: int) -> CandidateDetail:
        candidate = self.service.get_candidate(scope, candidate_id)
        return self._to_detail(scope, candidate)

    def create_candidate(self, scope: TenantScope, payload: CandidateCreate) -> CandidateDetail:
        candidate = self.service.create_candidate(scope, payload)
        return self._to_detail(scope, candidate)

    def update_candidate(
        self, scope: TenantScope, candidate_id: int, payload: CandidateUpdate
    ) -> CandidateDetail:
        candidate = self.service.update_candidate(scope, candidate_id, payload)
        return self._to_detail(scope, candidate)

    def delete_candidate(self, scope: TenantScope, candidate_id: int) -> None:
        self.service.delete_candidate(scope, candidate_id)

    def get_stats(self, scope: TenantScope) -> CandidateStats:
        total, added_this_week, with_cv = self.service.get_stats(scope)
        return CandidateStats(total=total, added_this_week=added_this_week, with_cv=with_cv)

    def attach_cv(
        self,
        scope: TenantScope,
        candidate_id: int,
        filename: str | None,
        content: bytes,
        evidence: list[str] | None = None,
    ) -> CvUploadResult:
        candidate = self.service.attach_cv(scope, candidate_id, filename, content, evidence)
        return CvUploadResult(
            candidate_id=candidate.id,
            cv_filename=candidate.cv_filename or "",
            cv_mime_type=candidate.cv_mime_type or "",
            cv_size_bytes=candidate.cv_size_bytes or 0,
        )

    def get_cv(self, scope: TenantScope, candidate_id: int) -> tuple[str, str, bytes]:
        return self.service.get_cv(scope, candidate_id)

    def delete_cv(self, scope: TenantScope, candidate_id: int) -> None:
        self.service.delete_cv(scope, candidate_id)

    # --- Mapping -----------------------------------------------------------

    def _to_detail(self, scope: TenantScope, candidate: Candidate) -> CandidateDetail:
        detail = CandidateDetail.model_validate(candidate)
        detail.submissions = [
            CandidateSubmissionLink(
                submission_id=row[0],
                job_order_id=row[1],
                job_title=row[2],
                client_name=row[3],
                status=row[4],
                created_at=row[5],
            )
            for row in self.service.get_submissions(scope, candidate.id)
        ]
        return detail
