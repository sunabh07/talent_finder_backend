"""The X-Tenant-ID dependency - the single chokepoint for tenant isolation.

Nothing uses this dependency yet (candidates arrive in Story 2), so it is
exercised here through a probe route mounted on a throwaway app. Shipping an
untested dependency that every later endpoint will rely on would be the wrong
order to build in.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.deps import TenantScopeDep


def _with_probe_route(app: FastAPI) -> TestClient:
    @app.get("/api/v1/_probe")
    def probe(scope: TenantScopeDep) -> dict[str, object]:
        return {"tenant_id": scope.id, "tenant_name": scope.name}

    return TestClient(app)


def test_valid_header_resolves_the_tenant(app: FastAPI, client: TestClient) -> None:
    created = client.post("/api/v1/tenants", json={"name": "LinkedIn"}).json()
    probe = _with_probe_route(app)

    response = probe.get("/api/v1/_probe", headers={"X-Tenant-ID": str(created["id"])})
    assert response.status_code == 200
    assert response.json() == {"tenant_id": created["id"], "tenant_name": "LinkedIn"}


def test_missing_header_is_rejected(app: FastAPI) -> None:
    response = _with_probe_route(app).get("/api/v1/_probe")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "MISSING_TENANT"


def test_blank_header_is_rejected(app: FastAPI) -> None:
    response = _with_probe_route(app).get("/api/v1/_probe", headers={"X-Tenant-ID": "   "})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "MISSING_TENANT"


def test_non_numeric_header_is_rejected(app: FastAPI) -> None:
    response = _with_probe_route(app).get("/api/v1/_probe", headers={"X-Tenant-ID": "abc"})
    assert response.status_code == 400
    assert response.json()["error"]["details"]["received"] == "abc"


def test_unknown_tenant_is_rejected(app: FastAPI) -> None:
    response = _with_probe_route(app).get("/api/v1/_probe", headers={"X-Tenant-ID": "999999"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
