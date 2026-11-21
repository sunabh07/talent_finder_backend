"""Tenant controller.

The controller is the seam between HTTP-shaped data and domain-shaped data. It
unpacks validated request models, calls the service, and maps ORM entities onto
response schemas. Routes stay free of mapping logic; services stay free of
response schemas.
"""

from sqlalchemy.orm import Session

from app.core.pagination import ListQuery
from app.schemas.common import Page
from app.schemas.tenant import TenantCreate, TenantRead, TenantStats
from app.services.tenant_service import TenantService


class TenantController:
    def __init__(self, session: Session) -> None:
        self.service = TenantService(session)

    def list_tenants(self, query: ListQuery) -> Page[TenantRead]:
        tenants, total = self.service.list_tenants(query)
        return Page.build(
            items=[TenantRead.model_validate(tenant) for tenant in tenants],
            total=total,
            page=query.page,
            page_size=query.page_size,
        )

    def get_tenant(self, tenant_id: int) -> TenantRead:
        return TenantRead.model_validate(self.service.get_tenant(tenant_id))

    def create_tenant(self, payload: TenantCreate) -> TenantRead:
        return TenantRead.model_validate(self.service.create_tenant(payload.name))

    def get_stats(self) -> TenantStats:
        total, active, added_this_week = self.service.get_stats()
        return TenantStats(total=total, active=active, added_this_week=added_this_week)
