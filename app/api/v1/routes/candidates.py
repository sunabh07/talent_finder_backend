"""Candidate HTTP routes (Story 2.1, 2.2, 2.3).

Every route in this module declares ``scope: TenantScopeDep``. That single
declaration is what makes the endpoint tenant-scoped - the dependency resolves
and validates ``X-Tenant-ID`` before the handler body runs, and the resolved
tenant is then a required argument all the way down to the repository.
"""

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Path, Response, UploadFile, status

from app.controllers.candidate_controller import CandidateController
from app.core.deps import DbSession, TenantScopeDep
from app.core.pagination import ListQuery, list_query_params
from app.schemas.candidate import (
    CandidateCreate,
    CandidateDetail,
    CandidateListItem,
    CandidateStats,
    CandidateUpdate,
    CvUploadResult,
)
from app.schemas.common import ErrorResponse, Page

router = APIRouter(prefix="/candidates", tags=["Candidates"])

ListQueryDep = Annotated[ListQuery, Depends(list_query_params)]
CandidateId = Annotated[int, Path(ge=1)]

TENANT_ERRORS: dict[int | str, dict] = {
    400: {"model": ErrorResponse, "description": "X-Tenant-ID missing or malformed"},
    404: {"model": ErrorResponse, "description": "Tenant or candidate not found in this tenant"},
}


@router.get(
    "",
    response_model=Page[CandidateListItem],
    summary="List candidates in the selected tenant",
    description=(
        "Search matches name, location, current role, email and skill name. "
        "Sortable by: full_name, location, total_experience_years, current_role, "
        "created_at, id. CV bytes are never included."
    ),
    responses=TENANT_ERRORS,
)
def list_candidates(
    db: DbSession, scope: TenantScopeDep, query: ListQueryDep
) -> Page[CandidateListItem]:
    return CandidateController(db).list_candidates(scope, query)


@router.get(
    "/stats",
    response_model=CandidateStats,
    summary="Candidate summary counts",
    responses=TENANT_ERRORS,
)
def candidate_stats(db: DbSession, scope: TenantScopeDep) -> CandidateStats:
    return CandidateController(db).get_stats(scope)


@router.get(
    "/{candidate_id}",
    response_model=CandidateDetail,
    summary="Candidate details",
    description=(
        "Includes skills, CV metadata and the job orders this candidate is shortlisted for."
    ),
    responses=TENANT_ERRORS,
)
def get_candidate(
    db: DbSession, scope: TenantScopeDep, candidate_id: CandidateId
) -> CandidateDetail:
    return CandidateController(db).get_candidate(scope, candidate_id)


@router.post(
    "",
    response_model=CandidateDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create a candidate",
    description=(
        "Creates a candidate in the selected tenant. Requires full name, location, "
        "total experience and at least one skill. Skills are resolved against the "
        "shared vocabulary, including aliases, and created on demand. "
        "Attach a CV afterwards with POST /candidates/{id}/cv."
    ),
    responses={**TENANT_ERRORS, 422: {"model": ErrorResponse, "description": "Invalid payload"}},
)
def create_candidate(
    db: DbSession, scope: TenantScopeDep, payload: CandidateCreate
) -> CandidateDetail:
    return CandidateController(db).create_candidate(scope, payload)


@router.patch(
    "/{candidate_id}",
    response_model=CandidateDetail,
    summary="Update a candidate",
    description="Partial update. Supplying `skills` replaces the whole set.",
    responses=TENANT_ERRORS,
)
def update_candidate(
    db: DbSession,
    scope: TenantScopeDep,
    candidate_id: CandidateId,
    payload: CandidateUpdate,
) -> CandidateDetail:
    return CandidateController(db).update_candidate(scope, candidate_id, payload)


@router.delete(
    "/{candidate_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a candidate",
    description="Also removes the candidate's skill links and submissions.",
    responses=TENANT_ERRORS,
)
def delete_candidate(db: DbSession, scope: TenantScopeDep, candidate_id: CandidateId) -> Response:
    CandidateController(db).delete_candidate(scope, candidate_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- CV ---------------------------------------------------------------------


@router.post(
    "/{candidate_id}/cv",
    response_model=CvUploadResult,
    summary="Attach or replace a CV",
    description=(
        "Accepts .pdf or .docx. The file is validated by extension, magic bytes and "
        "size, and the stored MIME type is derived from the signature rather than "
        "from the client's Content-Type."
    ),
    responses={**TENANT_ERRORS, 422: {"model": ErrorResponse, "description": "Rejected file"}},
)
async def upload_cv(
    db: DbSession,
    scope: TenantScopeDep,
    candidate_id: CandidateId,
    file: Annotated[UploadFile, File(description="CV file (.pdf or .docx)")],
) -> CvUploadResult:
    content = await file.read()
    return CandidateController(db).attach_cv(scope, candidate_id, file.filename, content)


@router.get(
    "/{candidate_id}/cv",
    summary="Download a CV",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}, "description": "The stored CV file"},
        **TENANT_ERRORS,
    },
)
def download_cv(db: DbSession, scope: TenantScopeDep, candidate_id: CandidateId) -> Response:
    filename, mime_type, content = CandidateController(db).get_cv(scope, candidate_id)
    # RFC 5987 encoding so that non-ASCII filenames survive the header.
    disposition = f"attachment; filename*=UTF-8''{quote(filename)}"
    return Response(
        content=content,
        media_type=mime_type,
        headers={"Content-Disposition": disposition},
    )


@router.delete(
    "/{candidate_id}/cv",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a CV",
    responses=TENANT_ERRORS,
)
def delete_cv(db: DbSession, scope: TenantScopeDep, candidate_id: CandidateId) -> Response:
    CandidateController(db).delete_cv(scope, candidate_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
