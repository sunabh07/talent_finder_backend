"""Submission list routes (Story 3.5 / Story 4)."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.controllers.job_order_controller import SubmissionController
from app.core.deps import DbSession, TenantScopeDep
from app.core.pagination import ListQuery, list_query_params
from app.schemas.common import ErrorResponse, Page
from app.schemas.job_order import SubmissionListItem, SubmissionStats

router = APIRouter(prefix="/submissions", tags=["Submissions"])

ListQueryDep = Annotated[ListQuery, Depends(list_query_params)]

TENANT_ERRORS: dict[int | str, dict] = {
    400: {"model": ErrorResponse, "description": "X-Tenant-ID missing or malformed"},
    404: {"model": ErrorResponse, "description": "Tenant not found"},
}


@router.get(
    "",
    response_model=Page[SubmissionListItem],
    summary="List submissions in the selected tenant",
    description=(
        "Every candidate shortlisted across this tenant's job orders. Search matches "
        "job title, client name, candidate name and status. Sortable by: job_title, "
        "candidate_name, status, created_at (default), id."
    ),
    responses=TENANT_ERRORS,
)
def list_submissions(
    db: DbSession, scope: TenantScopeDep, query: ListQueryDep
) -> Page[SubmissionListItem]:
    return SubmissionController(db).list_submissions(scope, query)


@router.get(
    "/stats",
    response_model=SubmissionStats,
    summary="Submission summary counts",
    responses=TENANT_ERRORS,
)
def submission_stats(db: DbSession, scope: TenantScopeDep) -> SubmissionStats:
    return SubmissionController(db).get_stats(scope)
