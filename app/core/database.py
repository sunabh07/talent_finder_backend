"""SQLAlchemy engine, session factory and the FastAPI session dependency."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

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
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
