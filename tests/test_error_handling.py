"""Error handling and request correlation.

The catch-all exception handler is the point of these tests. Before it
existed, an unexpected failure returned FastAPI's default 500 — a different
shape from every other error the API emits, and with internals in the body.
"""

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.core.errors import NotFoundError
from app.core.middleware import REQUEST_ID_HEADER


def _boom_route(app: FastAPI, exc: Exception):
    @app.get("/api/v1/_boom")
    def boom() -> dict:
        raise exc

    # raise_server_exceptions=False makes TestClient return the handler's
    # response instead of re-raising, which is what a real client would see.
    return TestClient(app, raise_server_exceptions=False)


# --- The catch-all ---------------------------------------------------------


def test_unexpected_exception_returns_the_standard_envelope(app: FastAPI) -> None:
    client = _boom_route(app, RuntimeError("something nobody predicted"))
    response = client.get("/api/v1/_boom")

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    # Same shape as every other error the API can return.
    assert set(body["error"]) == {"code", "message", "details"}


def test_unexpected_exception_does_not_leak_internals(app: FastAPI) -> None:
    """The message and the type must not reach the caller."""
    client = _boom_route(app, RuntimeError("secret connection string in here"))
    text = client.get("/api/v1/_boom").text

    assert "secret connection string" not in text
    assert "RuntimeError" not in text
    assert "Traceback" not in text


def test_unexpected_exception_is_logged_with_a_traceback(
    app: FastAPI, caplog: pytest.LogCaptureFixture
) -> None:
    """Hidden from the caller, but never lost."""
    client = _boom_route(app, RuntimeError("diagnostic detail"))
    with caplog.at_level(logging.ERROR, logger="app.core.errors"):
        client.get("/api/v1/_boom")

    records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert records, "the failure must be logged"
    assert records[0].exc_info is not None, "a traceback must be attached"
    assert "diagnostic detail" in caplog.text


def test_database_errors_become_503_not_500(app: FastAPI) -> None:
    client = _boom_route(app, OperationalError("SELECT 1", {}, Exception("conn refused")))
    response = client.get("/api/v1/_boom")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"


def test_expected_errors_still_win_over_the_catch_all(app: FastAPI) -> None:
    """The catch-all must not swallow the specific handlers."""
    client = _boom_route(app, NotFoundError("Candidate 1 was not found."))
    response = client.get("/api/v1/_boom")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


# --- Request correlation ---------------------------------------------------


def test_every_response_carries_a_request_id(client: TestClient) -> None:
    response = client.get("/api/v1/tenants")
    assert response.headers.get(REQUEST_ID_HEADER)


def test_an_upstream_request_id_is_preserved(client: TestClient) -> None:
    """So a trace survives across a proxy or another service."""
    response = client.get("/api/v1/tenants", headers={REQUEST_ID_HEADER: "trace-abc-123"})
    assert response.headers[REQUEST_ID_HEADER] == "trace-abc-123"


def test_request_ids_differ_between_requests(client: TestClient) -> None:
    first = client.get("/api/v1/tenants").headers[REQUEST_ID_HEADER]
    second = client.get("/api/v1/tenants").headers[REQUEST_ID_HEADER]
    assert first != second


def test_log_lines_carry_the_request_id(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """The whole point of the ContextVar: correlation without plumbing."""
    with caplog.at_level(logging.INFO, logger="app.request"):
        response = client.get("/api/v1/tenants")

    request_id = response.headers[REQUEST_ID_HEADER]
    assert any(getattr(r, "request_id", None) == request_id for r in caplog.records)


# --- Business event logging ------------------------------------------------


def test_creating_a_tenant_is_logged(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="app.services.tenant_service"):
        client.post("/api/v1/tenants", json={"name": "LinkedIn"})
    assert "Tenant created" in caplog.text


def test_idempotent_shortlist_is_distinguishable_in_the_log(
    client: TestClient, tenant_a, caplog: pytest.LogCaptureFixture
) -> None:
    """A burst of no-ops means the UI is double-firing — make it visible."""
    job = client.post(
        "/api/v1/job-orders",
        json={
            "job_title": "Backend Engineer",
            "location": "Pune",
            "min_experience_years": "2",
            "number_of_openings": 1,
            "required_skills": ["Python"],
        },
        headers=tenant_a,
    ).json()
    candidate = client.post(
        "/api/v1/candidates",
        json={
            "full_name": "Asha Rao",
            "location": "Pune",
            "total_experience_years": "5",
            "skills": ["Python"],
        },
        headers=tenant_a,
    ).json()

    url = f"/api/v1/job-orders/{job['id']}/shortlist"
    body = {"candidate_id": candidate["id"]}

    with caplog.at_level(logging.INFO, logger="app.services.submission_service"):
        client.post(url, json=body, headers=tenant_a)
        client.post(url, json=body, headers=tenant_a)

    assert "Shortlist created" in caplog.text
    assert "already shortlisted" in caplog.text
