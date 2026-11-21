"""Tenant business rules.

The service owns the transaction. It decides *what* is allowed; the repository
decides *how* it is fetched. Nothing in here imports FastAPI, so the same rules
could be driven by a CLI, a background job or a test without a web server.
"""

from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.core.pagination import ListQuery
from app.models.enums import TenantStatus
from app.models.tenant import Tenant
from app.repositories.tenant_repository import TenantRepository


class TenantService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = TenantRepository(session)

    # --- Queries -----------------------------------------------------------

    def list_tenants(self, query: ListQuery) -> tuple[list[Tenant], int]:
        return self.repo.list(query)

    def get_tenant(self, tenant_id: int) -> Tenant:
        tenant = self.repo.get(tenant_id)
        if tenant is None:
            raise NotFoundError(f"Tenant {tenant_id} was not found.", {"tenant_id": tenant_id})
        return tenant

    def get_stats(self) -> tuple[int, int, int]:
        return self.repo.stats()

    # --- Commands ----------------------------------------------------------

    def create_tenant(self, name: str) -> Tenant:
        """Create a tenant (Story 1.2).

        Uniqueness is checked here for a friendly 409, and enforced again by the
        ``uq_tenants_name_lower`` index. The index is the real guarantee; this
        check only exists to produce a better error message than a constraint
        violation would.
        """
        existing = self.repo.find_by_name_ci(name)
        if existing is not None:
            raise ConflictError(
                f"A tenant named '{existing.name}' already exists.",
                {"field": "name", "existing_tenant_id": existing.id},
            )

        tenant = Tenant(name=name, status=TenantStatus.ACTIVE.value)
        self.repo.add(tenant)
        self.session.commit()
        self.session.refresh(tenant)
        return tenant
