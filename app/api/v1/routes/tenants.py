"""Tenant HTTP routes (Story 1.1 and 1.2).

Routes are intentionally thin: declare the contract, delegate to the
controller, return. No query building, no business rules, no mapping.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.controllers.tenant_controller import TenantController
from app.core.deps import DbSession
from app.core.pagination import ListQuery, list_query_params
from app.schemas.common import ErrorResponse, Page
from app.schemas.tenant import TenantCreate, TenantRead, TenantStats

router = APIRouter(prefix="/tenants", tags=["Tenants"])

ListQueryDep = Annotated[ListQuery, Depends(list_query_params)]


@router.get(
    "",
    response_model=Page[TenantRead],
    summary="List tenants",
    description=(
        "Paginated tenant list backing the Tenant List screen. "
        "Search matches the tenant name, and also an exact tenant id when the "
        "search term is numeric. Sortable by: name, id, status, created_at."
    ),
)
def list_tenants(db: DbSession, query: ListQueryDep) -> Page[TenantRead]:
    return TenantController(db).list_tenants(query)


@router.get(
    "/stats",
    response_model=TenantStats,
    summary="Tenant summary counts",
    description="Counts for the summary cards shown above the Tenant List table.",
)
def tenant_stats(db: DbSession) -> TenantStats:
    return TenantController(db).get_stats()


@router.get(
    "/{tenant_id}",
    response_model=TenantRead,
    summary="Get one tenant",
    responses={404: {"model": ErrorResponse, "description": "Tenant does not exist"}},
)
def get_tenant(db: DbSession, tenant_id: Annotated[int, Path(ge=1)]) -> TenantRead:
    return TenantController(db).get_tenant(tenant_id)


@router.post(
    "",
    response_model=TenantRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a tenant",
    responses={
        409: {"model": ErrorResponse, "description": "Tenant name already in use"},
        422: {"model": ErrorResponse, "description": "Invalid payload"},
    },
)
def create_tenant(db: DbSession, payload: TenantCreate) -> TenantRead:
    return TenantController(db).create_tenant(payload)
