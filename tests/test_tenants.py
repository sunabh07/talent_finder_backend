"""Story 1.1 and 1.2 - Tenant List and Create Tenant."""

from fastapi.testclient import TestClient

BASE = "/api/v1/tenants"


def test_health_reports_database_connected(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["database"] == "connected"


# --- Story 1.2: Create Tenant ---------------------------------------------


def test_create_tenant_returns_201_with_active_status(client: TestClient) -> None:
    response = client.post(BASE, json={"name": "LinkedIn"})
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "LinkedIn"
    assert body["status"] == "Active"
    assert isinstance(body["id"], int)


def test_created_tenant_appears_in_the_list(client: TestClient, make_tenant) -> None:
    created = make_tenant("Naukri")
    listing = client.get(BASE).json()
    assert created["id"] in [row["id"] for row in listing["items"]]


def test_tenant_name_is_trimmed(client: TestClient) -> None:
    response = client.post(BASE, json={"name": "  Monster  "})
    assert response.status_code == 201
    assert response.json()["name"] == "Monster"


def test_blank_tenant_name_is_rejected(client: TestClient) -> None:
    response = client.post(BASE, json={"name": "   "})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_missing_tenant_name_is_rejected(client: TestClient) -> None:
    assert client.post(BASE, json={}).status_code == 422


def test_duplicate_tenant_name_is_rejected_case_insensitively(
    client: TestClient, make_tenant
) -> None:
    make_tenant("LinkedIn")
    response = client.post(BASE, json={"name": "linkedin"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"


# --- Story 1.1: Tenant List ------------------------------------------------


def test_list_returns_the_required_columns(client: TestClient, make_tenant) -> None:
    make_tenant("LinkedIn")
    row = client.get(BASE).json()["items"][0]
    # Tenant Name, Tenant ID, Status - the three columns the assignment names.
    assert {"id", "name", "status"} <= set(row)


def test_list_is_paginated(client: TestClient, make_tenant) -> None:
    for index in range(7):
        make_tenant(f"Channel {index:02d}")

    first = client.get(BASE, params={"page": 1, "page_size": 3}).json()
    assert first["total"] == 7
    assert first["page_size"] == 3
    assert first["total_pages"] == 3
    assert len(first["items"]) == 3

    last = client.get(BASE, params={"page": 3, "page_size": 3}).json()
    assert len(last["items"]) == 1

    # No row may appear on two pages.
    page_two = client.get(BASE, params={"page": 2, "page_size": 3}).json()
    ids = [r["id"] for r in first["items"] + page_two["items"] + last["items"]]
    assert len(ids) == len(set(ids)) == 7


def test_search_matches_tenant_name(client: TestClient, make_tenant) -> None:
    make_tenant("LinkedIn")
    make_tenant("Naukri")
    found = client.get(BASE, params={"q": "link"}).json()
    assert found["total"] == 1
    assert found["items"][0]["name"] == "LinkedIn"


def test_search_matches_tenant_id(client: TestClient, make_tenant) -> None:
    make_tenant("LinkedIn")
    target = make_tenant("Naukri")
    found = client.get(BASE, params={"q": str(target["id"])}).json()
    assert [row["id"] for row in found["items"]] == [target["id"]]


def test_sorting_by_name_descending(client: TestClient, make_tenant) -> None:
    for name in ("Alpha", "Bravo", "Charlie"):
        make_tenant(name)
    names = [
        row["name"]
        for row in client.get(BASE, params={"sort_by": "name", "sort_dir": "desc"}).json()["items"]
    ]
    assert names == sorted(names, reverse=True)


def test_unknown_sort_key_is_rejected(client: TestClient) -> None:
    response = client.get(BASE, params={"sort_by": "name; DROP TABLE tenants"})
    assert response.status_code == 422
    assert "allowed_sort_by" in response.json()["error"]["details"]


def test_page_size_above_the_maximum_is_rejected(client: TestClient) -> None:
    response = client.get(BASE, params={"page_size": 5000})
    assert response.status_code == 422
    assert response.json()["error"]["details"]["max_page_size"] == 100


def test_empty_list_is_a_valid_response(client: TestClient) -> None:
    body = client.get(BASE).json()
    assert body["total"] == 0
    assert body["items"] == []
    assert body["total_pages"] == 0


# --- Detail and stats ------------------------------------------------------


def test_get_single_tenant(client: TestClient, make_tenant) -> None:
    created = make_tenant("LinkedIn")
    fetched = client.get(f"{BASE}/{created['id']}").json()
    assert fetched["id"] == created["id"]


def test_get_unknown_tenant_returns_404(client: TestClient) -> None:
    response = client.get(f"{BASE}/999999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_stats_back_the_summary_cards(client: TestClient, make_tenant) -> None:
    make_tenant("LinkedIn")
    make_tenant("Naukri")
    stats = client.get(f"{BASE}/stats").json()
    assert stats["total"] == 2
    assert stats["active"] == 2
    assert stats["added_this_week"] == 2
