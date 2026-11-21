"""Shared FastAPI dependencies - most importantly, the tenant scope.

**The single chokepoint for multi-tenancy.**

Every tenant-owned endpoint (candidates, job orders, submissions) declares
``scope: TenantScopeDep``. That one declaration resolves and validates the
``X-Tenant-ID`` header *before* the handler body runs, and hands down a value
object that repositories require as an argument. The consequence is that an
unscoped query is not something a developer can forget to write - it is
something they would have to deliberately remove a required parameter to
achieve.

Honest limitation, to be raised in the interview: the assignment specifies no
authentication, so the client chooses its own ``X-Tenant-ID``. This enforces
*logical* isolation (no endpoint can leak another tenant's rows, and no
mutation can cross tenants), but it is **not** protection against a caller who
simply sends a different tenant id. Production would derive this value from an
authenticated session, never from a client-supplied header. Nothing else in the
architecture would have to change: only this function.
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import MissingTenantError, NotFoundError
from app.models.tenant import Tenant

TENANT_HEADER = "X-Tenant-ID"

DbSession = Annotated[Session, Depends(get_db)]


@dataclass(frozen=True, slots=True)
class TenantScope:
    """The validated, existing tenant a request is acting within."""

    id: int
    name: str


def get_tenant_scope(
    db: DbSession,
    x_tenant_id: Annotated[
        str | None,
        Header(
            alias=TENANT_HEADER,
            description="Id of the tenant whose data this request operates on.",
        ),
    ] = None,
) -> TenantScope:
    if x_tenant_id is None or not x_tenant_id.strip():
        raise MissingTenantError(
            f"The {TENANT_HEADER} header is required for this endpoint.",
            {"header": TENANT_HEADER},
        )

    raw = x_tenant_id.strip()
    try:
        tenant_id = int(raw)
    except ValueError:
        raise MissingTenantError(
            f"{TENANT_HEADER} must be an integer tenant id.",
            {"header": TENANT_HEADER, "received": raw},
        ) from None

    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        # 404 rather than 403: without authentication we must not confirm
        # whether a tenant id that the caller is not using actually exists.
        raise NotFoundError(f"Tenant {tenant_id} was not found.", {"tenant_id": tenant_id})

    return TenantScope(id=tenant.id, name=tenant.name)


TenantScopeDep = Annotated[TenantScope, Depends(get_tenant_scope)]
