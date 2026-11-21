"""Repository layer foundations.

Rules for everything in ``app/repositories``:

* This is the **only** package allowed to build SQLAlchemy queries. Services
  express intent; repositories express SQL.
* Repositories never commit. The transaction boundary belongs to the service,
  so that one business operation spanning several repositories stays atomic.
* Every tenant-owned repository takes ``tenant_id`` as a required argument
  rather than reading it from global state, which makes an unscoped query a
  visible mistake at the call site instead of a silent one.
"""

from typing import Any, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.pagination import ListQuery

T = TypeVar("T")


class BaseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session


def count_rows(session: Session, stmt: Select[Any]) -> int:
    """Total rows a filtered statement would return, ignoring limit/offset.

    Wrapping the statement in a subquery (rather than re-deriving the filters)
    guarantees the count can never drift out of sync with the page query.
    """
    subquery = stmt.order_by(None).subquery()
    return session.scalar(select(func.count()).select_from(subquery)) or 0


def apply_window(stmt: Select[Any], query: ListQuery) -> Select[Any]:
    """Apply LIMIT/OFFSET derived from the validated list query."""
    return stmt.limit(query.page_size).offset(query.offset)
