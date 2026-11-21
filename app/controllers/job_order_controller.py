"""Job order, matching and submission controllers."""

from sqlalchemy.orm import Session

from app.core.deps import TenantScope
from app.core.pagination import ListQuery
from app.models.job_order import JobOrder
from app.schemas.candidate import SkillRead
from app.schemas.common import Page
from app.schemas.job_order import (
    JobOrderCreate,
    JobOrderDetail,
    JobOrderListItem,
    JobOrderStats,
    JobOrderUpdate,
    MatchedCandidate,
    MatchPage,
    MatchSummary,
    ShortlistedCandidate,
    ShortlistResult,
    SubmissionListItem,
    SubmissionStats,
)
from app.services.job_order_service import JobOrderService
from app.services.submission_service import SubmissionService


class JobOrderController:
    def __init__(self, session: Session) -> None:
        self.service = JobOrderService(session)

    def list_job_orders(self, scope: TenantScope, query: ListQuery) -> Page[JobOrderListItem]:
        job_orders, total = self.service.list_job_orders(scope, query)
        return Page.build(
            items=[JobOrderListItem.model_validate(job) for job in job_orders],
            total=total,
            page=query.page,
            page_size=query.page_size,
        )

    def get_job_order(self, scope: TenantScope, job_order_id: int) -> JobOrderDetail:
        job_order = self.service.get_job_order(scope, job_order_id)
        return self._to_detail(scope, job_order)

    def create_job_order(self, scope: TenantScope, payload: JobOrderCreate) -> JobOrderDetail:
        return self._to_detail(scope, self.service.create_job_order(scope, payload))

    def update_job_order(
        self, scope: TenantScope, job_order_id: int, payload: JobOrderUpdate
    ) -> JobOrderDetail:
        job_order = self.service.update_job_order(scope, job_order_id, payload)
        return self._to_detail(scope, job_order)

    def delete_job_order(self, scope: TenantScope, job_order_id: int) -> None:
        self.service.delete_job_order(scope, job_order_id)

    def get_stats(self, scope: TenantScope) -> JobOrderStats:
        total, open_count, openings = self.service.get_stats(scope)
        return JobOrderStats(total=total, open=open_count, total_openings=openings)

    def match_candidates(
        self, scope: TenantScope, job_order_id: int, query: ListQuery
    ) -> MatchPage:
        job_order, rows, total = self.service.match_candidates(scope, job_order_id, query)
        page = Page.build(
            items=[
                MatchedCandidate(
                    candidate_id=row[0],
                    full_name=row[1],
                    current_role=row[2],
                    location=row[3],
                    total_experience_years=row[4],
                    match_count=row[5],
                    matched_skills=list(row[6] or []),
                    meets_min_experience=bool(row[7]),
                    is_shortlisted=bool(row[8]),
                )
                for row in rows
            ],
            total=total,
            page=query.page,
            page_size=query.page_size,
        )
        return MatchPage(
            items=page.items,
            total=page.total,
            page=page.page,
            page_size=page.page_size,
            total_pages=page.total_pages,
            summary=MatchSummary(
                job_order_id=job_order.id,
                required_skill_count=len(job_order.required_skills),
                required_skills=[
                    SkillRead.model_validate(skill) for skill in job_order.required_skills
                ],
            ),
        )

    # --- Mapping -------------------------------------------------------------

    def _to_detail(self, scope: TenantScope, job_order: JobOrder) -> JobOrderDetail:
        detail = JobOrderDetail.model_validate(job_order)
        detail.shortlisted = [
            ShortlistedCandidate(
                submission_id=row[0],
                candidate_id=row[1],
                full_name=row[2],
                current_role=row[3],
                location=row[4],
                total_experience_years=row[5],
                status=row[6],
                created_at=row[7],
            )
            for row in self.service.get_shortlisted(scope, job_order.id)
        ]
        return detail


class SubmissionController:
    def __init__(self, session: Session) -> None:
        self.service = SubmissionService(session)

    def list_submissions(self, scope: TenantScope, query: ListQuery) -> Page[SubmissionListItem]:
        rows, total = self.service.list_submissions(scope, query)
        return Page.build(
            items=[
                SubmissionListItem(
                    id=row[0],
                    job_order_id=row[1],
                    job_title=row[2],
                    client_name=row[3],
                    candidate_id=row[4],
                    candidate_name=row[5],
                    status=row[6],
                    created_at=row[7],
                )
                for row in rows
            ],
            total=total,
            page=query.page,
            page_size=query.page_size,
        )

    def get_stats(self, scope: TenantScope) -> SubmissionStats:
        total, added_this_week, job_orders = self.service.get_stats(scope)
        return SubmissionStats(
            total=total,
            added_this_week=added_this_week,
            job_orders_with_submissions=job_orders,
        )

    def shortlist(
        self, scope: TenantScope, job_order_id: int, candidate_id: int
    ) -> ShortlistResult:
        submission, already = self.service.shortlist(scope, job_order_id, candidate_id)
        return ShortlistResult(
            submission_id=submission.id,
            job_order_id=submission.job_order_id,
            candidate_id=submission.candidate_id,
            status=submission.status,
            created_at=submission.created_at,
            already_shortlisted=already,
        )
