"""Pytest fixtures.

Two decisions worth stating:

1. **Tests run against a real PostgreSQL database, not SQLite.** The schema
   leans on things SQLite does not implement the same way - composite foreign
   keys, ``btrim`` in CHECK constraints, a functional unique index, ``BYTEA``.
   Testing against a different engine than production would mean the
   constraints this project is built around go unverified.

2. **The schema is created by running the real Alembic migrations**, not by
   ``Base.metadata.create_all``. "Migrations run on a clean database" is a
   Story 1 acceptance criterion, so every test session proves it.

Each test runs inside a transaction that is rolled back afterwards. The session
is joined to that outer transaction with ``create_savepoint``, so application
code can call ``commit()`` normally while the test still leaves no trace.
"""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import settings
from app.core.database import get_db
from app.main import create_app

TEST_DATABASE_URL = settings.test_database_url or settings.database_url


@pytest.fixture(scope="session")
def engine() -> Generator[Engine, None, None]:
    if settings.database_url == TEST_DATABASE_URL:
        pytest.fail(
            "TEST_DATABASE_URL is not configured; refusing to run the suite "
            "against the development database."
        )

    test_engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True, future=True)

    # Start from genuinely empty, then migrate. This is what makes the run a
    # real test of the migration chain rather than of the ORM metadata.
    with test_engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))

    alembic_cfg = Config("alembic.ini")
    os.environ["ALEMBIC_DATABASE_URL"] = TEST_DATABASE_URL
    try:
        command.upgrade(alembic_cfg, "head")
    finally:
        os.environ.pop("ALEMBIC_DATABASE_URL", None)

    yield test_engine
    test_engine.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Generator[Session, None, None]:
    """A session whose work is always rolled back."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def app(db_session: Session) -> FastAPI:
    """App instance wired to the rolled-back test session."""
    application = create_app()
    application.dependency_overrides[get_db] = lambda: db_session
    return application


@pytest.fixture
def client(app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def make_tenant(client: TestClient):
    """Create a tenant through the API and return its JSON body."""

    def _make(name: str) -> dict:
        response = client.post("/api/v1/tenants", json={"name": name})
        assert response.status_code == 201, response.text
        return response.json()

    return _make


@pytest.fixture
def tenant_a(make_tenant) -> dict[str, str]:
    """Headers selecting a tenant, ready to pass as ``headers=tenant_a``."""
    return {"X-Tenant-ID": str(make_tenant("Tenant A")["id"])}


@pytest.fixture
def two_tenants(make_tenant) -> tuple[dict[str, str], dict[str, str]]:
    """Header pairs for two separate tenants, for isolation tests."""
    first = {"X-Tenant-ID": str(make_tenant("Tenant A")["id"])}
    second = {"X-Tenant-ID": str(make_tenant("Tenant B")["id"])}
    return first, second


@pytest.fixture
def seeded_skills(db_session: Session) -> None:
    """Load the canonical skill vocabulary and aliases used by the real app.

    Tests that exercise alias resolution need the same data the seed script
    installs, rather than a parallel fixture that could drift away from it.
    """
    from scripts.seed import seed_aliases, seed_skills

    skills = seed_skills(db_session)
    seed_aliases(db_session, skills)
    db_session.flush()
