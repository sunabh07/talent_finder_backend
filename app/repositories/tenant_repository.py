"""Data access for tenants."""

# Repository classes define a ``list`` method, which shadows the builtin inside
# the class body. Deferring annotation evaluation keeps ``list[...]`` hints working.
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select

from app.core.pagination import ListQuery
from app.models.enums import TenantStatus
from app.models.tenant import Tenant
from app.repositories.base import BaseRepository, apply_window, count_rows

# Columns a client is allowed to sort the tenant list by. Anything outside this
# map is rejected before it reaches SQL.
SORTABLE: dict[str, object] = {
    "name": Tenant.name,
    "id": Tenant.id,
    "status": Tenant.status,
    "created_at": Tenant.created_at,
}
DEFAULT_SORT = "name"


class TenantRepository(BaseRepository):
    def get(self, tenant_id: int) -> Tenant | None:
        return self.session.get(Tenant, tenant_id)

    def find_by_name_ci(self, name: str) -> Tenant | None:
        """Case-insensitive lookup, mirroring the uq_tenants_name_lower index."""
        stmt = select(Tenant).where(func.lower(Tenant.name) == name.casefold())
        return self.session.scalars(stmt).first()

    def list(self, query: ListQuery) -> tuple[list[Tenant], int]:
        stmt = select(Tenant)

        if query.q:
            term = f"%{query.q}%"
            conditions = [Tenant.name.ilike(term)]
            # Recruiters read the Tenant ID straight off the table, so let the
            # search box accept it as well as the name.
            if query.q.isdigit():
                conditions.append(Tenant.id == int(query.q))
            stmt = stmt.where(or_(*conditions))

        column, descending = query.validated_sort(SORTABLE, DEFAULT_SORT)
        order = column.desc() if descending else column.asc()  # type: ignore[union-attr]
        # Tie-break on id so that pagination is stable when the sort column has
        # duplicate values; without it, rows can repeat or vanish across pages.
        stmt = stmt.order_by(order, Tenant.id.asc())

        total = count_rows(self.session, stmt)
        rows = list(self.session.scalars(apply_window(stmt, query)).all())
        return rows, total

    def add(self, tenant: Tenant) -> Tenant:
        self.session.add(tenant)
        self.session.flush()  # assign the PK without ending the transaction
        return tenant

    def stats(self) -> tuple[int, int, int]:
        """Return ``(total, active, added_in_last_7_days)`` for the summary cards."""
        since = datetime.now(UTC) - timedelta(days=7)
        row = self.session.execute(
            select(
                func.count(Tenant.id),
                func.count(Tenant.id).filter(Tenant.status == TenantStatus.ACTIVE.value),
                func.count(Tenant.id).filter(Tenant.created_at >= since),
            )
        ).one()
        return int(row[0]), int(row[1]), int(row[2])
