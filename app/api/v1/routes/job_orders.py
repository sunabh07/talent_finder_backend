"""Job order, matching and shortlist routes (Stories 3.1-3.4)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response, status

from app.controllers.job_order_controller import JobOrderController, SubmissionController
from app.core.deps import DbSession, TenantScopeDep
from app.core.pagination import ListQuery, list_query_params
from app.schemas.common import ErrorResponse, Page
from app.schemas.job_order import (
    JobOrderCreate,
    JobOrderDetail,
    JobOrderListItem,
    JobOrderStats,
    JobOrderUpdate,
    MatchPage,
    ShortlistRequest,
    ShortlistResult,
)

router = APIRouter(prefix="/job-orders", tags=["Job Orders"])

ListQueryDep = Annotated[ListQuery, Depends(list_query_params)]
JobOrderId = Annotated[int, Path(ge=1)]

TENANT_ERRORS: dict[int | str, dict] = {
    400: {"model": ErrorResponse, "description": "X-Tenant-ID missing or malformed"},
    404: {"model": ErrorResponse, "description": "Tenant or job order not found in this tenant"},
}


@router.get(
    "",
    response_model=Page[JobOrderListItem],
    summary="List job orders in the selected tenant",
    description=(
        "Search matches job title, client name, location, status and required skill "
        "name. Sortable by: job_title, client_name, location, min_experience_years, "
        "number_of_openings, status, created_at (default), id."
    ),
    responses=TENANT_ERRORS,
)
def list_job_orders(
    db: DbSession, scope: TenantScopeDep, query: ListQueryDep
) -> Page[JobOrderListItem]:
    return JobOrderController(db).list_job_orders(scope, query)


@router.get(
    "/stats",
    response_model=JobOrderStats,
    summary="Job order summary counts",
    responses=TENANT_ERRORS,
)
def job_order_stats(db: DbSession, scope: TenantScopeDep) -> JobOrderStats:
    return JobOrderController(db).get_stats(scope)


@router.get(
    "/{job_order_id}",
    response_model=JobOrderDetail,
    summary="Job order details",
    description="Includes required skills and the Shortlisted Candidates section.",
    responses=TENANT_ERRORS,
)
def get_job_order(db: DbSession, scope: TenantScopeDep, job_order_id: JobOrderId) -> JobOrderDetail:
    return JobOrderController(db).get_job_order(scope, job_order_id)


@router.post(
    "",
    response_model=JobOrderDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create a job order",
    description=(
        "Requires job title, location, minimum experience, at least one opening and at "
        "least one required skill. Client name is optional; status defaults to Open. "
        "There is no file upload on this resource."
    ),
    responses={**TENANT_ERRORS, 422: {"model": ErrorResponse, "description": "Invalid payload"}},
)
def create_job_order(
    db: DbSession, scope: TenantScopeDep, payload: JobOrderCreate
) -> JobOrderDetail:
    return JobOrderController(db).create_job_order(scope, payload)


@router.patch(
    "/{job_order_id}",
    response_model=JobOrderDetail,
    summary="Update a job order",
    description="Partial update. Supplying `required_skills` replaces the whole set.",
    responses=TENANT_ERRORS,
)
def update_job_order(
    db: DbSession,
    scope: TenantScopeDep,
    job_order_id: JobOrderId,
    payload: JobOrderUpdate,
) -> JobOrderDetail:
    return JobOrderController(db).update_job_order(scope, job_order_id, payload)


@router.delete(
    "/{job_order_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a job order",
    description="Also removes its required-skill links and submissions.",
    responses=TENANT_ERRORS,
)
def delete_job_order(db: DbSession, scope: TenantScopeDep, job_order_id: JobOrderId) -> Response:
    JobOrderController(db).delete_job_order(scope, job_order_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Matching and shortlisting ------------------------------------------------


@router.get(
    "/{job_order_id}/matches",
    response_model=MatchPage,
    summary="Candidates ranked by matched required skills",
    description=(
        "Same-tenant candidates only. Candidates with zero matching required skills "
        "are excluded. Ordered by matched skill count descending, with name and id as "
        "deterministic tie-breakers.\n\n"
        "**There is no `sort_by` parameter.** The ranking is specified by the "
        "assignment and is not a client choice. `meets_min_experience` is returned "
        "for display only and never affects inclusion or order."
    ),
    responses=TENANT_ERRORS,
)
def match_candidates(
    db: DbSession, scope: TenantScopeDep, job_order_id: JobOrderId, query: ListQueryDep
) -> MatchPage:
    return JobOrderController(db).match_candidates(scope, job_order_id, query)


@router.post(
    "/{job_order_id}/shortlist",
    response_model=ShortlistResult,
    summary="Shortlist a candidate against this job order",
    description=(
        "Creates one submission with status `Shortlisted`. Idempotent: clicking twice "
        "returns the existing submission with `already_shortlisted: true` and creates "
        "nothing new. The candidate and job order must both belong to the selected "
        "tenant."
    ),
    responses=TENANT_ERRORS,
)
def shortlist_candidate(
    db: DbSession,
    scope: TenantScopeDep,
    job_order_id: JobOrderId,
    payload: ShortlistRequest,
) -> ShortlistResult:
    return SubmissionController(db).shortlist(scope, job_order_id, payload.candidate_id)
