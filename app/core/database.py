"""SQLAlchemy engine, session factory and the FastAPI session dependency."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import get_logger

logger = get_logger(__name__)

engine = create_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,  # transparently recycle connections dropped by the server
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,  # keep ORM objects usable after commit, for response mapping
    future=True,
)


def get_db() -> Generator[Session, None, None]:
    """Request-scoped database session.

    The session is the unit of work for a single HTTP request. Services own the
    transaction boundary (they call ``commit``); this dependency only guarantees
    that the connection is returned to the pool and that an unexpected error
    leaves nothing half-written.
    """
    db = SessionLocal()
    try:
        yield db
    except AppError:
        # An expected, client-visible error - a 404, a validation failure, a
        # missing tenant header. Still roll back, but say nothing: the error
        # handler already logs it, and a warning here would imply something
        # went wrong when the API merely said "no".
        db.rollback()
        raise
    except Exception:
        # Anything else is unexpected. Roll back so a failed request cannot
        # leave a half-written transaction behind, and re-raise — swallowing
        # it here would turn a real failure into a silent success.
        db.rollback()
        logger.warning("Rolled back the session after an unexpected error")
        raise
    finally:
        db.close()
