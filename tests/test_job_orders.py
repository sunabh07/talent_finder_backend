"""Story 3.1 and 3.2 - Job Order List and Create Job Order."""

from fastapi.testclient import TestClient

BASE = "/api/v1/job-orders"


def _payload(**overrides) -> dict:
    base = {
        "job_title": "Senior Backend Engineer",
        "location": "Bengaluru",
        "min_experience_years": "5",
        "number_of_openings": 2,
        "required_skills": ["Python", "FastAPI"],
    }
    base.update(overrides)
    return base


# --- Create ----------------------------------------------------------------


def test_create_defaults_to_open(client: TestClient, tenant_a) -> None:
    response = client.post(BASE, json=_payload(), headers=tenant_a)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "Open"
    assert body["client_name"] is None
    assert sorted(s["name"] for s in body["required_skills"]) == ["FastAPI", "Python"]


def test_openings_must_be_at_least_one(client: TestClient, tenant_a) -> None:
    assert (
        client.post(BASE, json=_payload(number_of_openings=0), headers=tenant_a).status_code == 422
    )
    assert (
        client.post(BASE, json=_payload(number_of_openings=-3), headers=tenant_a).status_code == 422
    )


def test_at_least_one_required_skill(client: TestClient, tenant_a) -> None:
    assert client.post(BASE, json=_payload(required_skills=[]), headers=tenant_a).status_code == 422


def test_required_fields_are_enforced(client: TestClient, tenant_a) -> None:
    for field in ("job_title", "location", "min_experience_years", "number_of_openings"):
        payload = _payload()
        payload.pop(field)
        assert client.post(BASE, json=payload, headers=tenant_a).status_code == 422, field


def test_blank_job_title_is_rejected(client: TestClient, tenant_a) -> None:
    assert client.post(BASE, json=_payload(job_title="   "), headers=tenant_a).status_code == 422


def test_client_name_is_optional(client: TestClient, tenant_a) -> None:
    body = client.post(BASE, json=_payload(client_name="Acme Ltd"), headers=tenant_a).json()
    assert body["client_name"] == "Acme Ltd"


# --- List ------------------------------------------------------------------


def test_list_returns_the_required_columns(client: TestClient, tenant_a) -> None:
    client.post(BASE, json=_payload(client_name="Acme"), headers=tenant_a)
    row = client.get(BASE, headers=tenant_a).json()["items"][0]
    assert {
        "job_title",
        "client_name",
        "location",
        "min_experience_years",
        "number_of_openings",
        "required_skills",
        "status",
    } <= set(row)


def test_list_is_tenant_scoped(client: TestClient, two_tenants) -> None:
    a, b = two_tenants
    client.post(BASE, json=_payload(), headers=a)
    assert client.get(BASE, headers=a).json()["total"] == 1
    assert client.get(BASE, headers=b).json()["total"] == 0


def test_search_matches_title_client_and_skill(client: TestClient, tenant_a) -> None:
    client.post(BASE, json=_payload(client_name="Northwind"), headers=tenant_a)
    client.post(
        BASE,
        json=_payload(job_title="Frontend Engineer", required_skills=["Angular"]),
        headers=tenant_a,
    )
    assert client.get(BASE, params={"q": "northwind"}, headers=tenant_a).json()["total"] == 1
    assert client.get(BASE, params={"q": "frontend"}, headers=tenant_a).json()["total"] == 1
    assert client.get(BASE, params={"q": "angular"}, headers=tenant_a).json()["total"] == 1


def test_search_by_skill_does_not_duplicate_rows(client: TestClient, tenant_a) -> None:
    client.post(BASE, json=_payload(required_skills=["Python", "FastAPI"]), headers=tenant_a)
    body = client.get(BASE, params={"q": "Python"}, headers=tenant_a).json()
    assert body["total"] == 1 and len(body["items"]) == 1


def test_sort_and_paginate(client: TestClient, tenant_a) -> None:
    for index, openings in enumerate((5, 1, 3)):
        client.post(
            BASE,
            json=_payload(job_title=f"Role {index}", number_of_openings=openings),
            headers=tenant_a,
        )
    items = client.get(
        BASE,
        params={"sort_by": "number_of_openings", "sort_dir": "desc"},
        headers=tenant_a,
    ).json()["items"]
    assert [i["number_of_openings"] for i in items] == [5, 3, 1]

    page = client.get(BASE, params={"page": 2, "page_size": 2}, headers=tenant_a).json()
    assert page["total"] == 3 and len(page["items"]) == 1


def test_unknown_sort_key_is_rejected(client: TestClient, tenant_a) -> None:
    assert client.get(BASE, params={"sort_by": "tenant_id"}, headers=tenant_a).status_code == 422


# --- Detail, update, delete ------------------------------------------------


def test_detail_includes_skills_and_empty_shortlist(client: TestClient, tenant_a) -> None:
    created = client.post(BASE, json=_payload(), headers=tenant_a).json()
    detail = client.get(f"{BASE}/{created['id']}", headers=tenant_a).json()
    assert len(detail["required_skills"]) == 2
    assert detail["shortlisted"] == []


def test_cross_tenant_detail_update_delete_are_404(client: TestClient, two_tenants) -> None:
    a, b = two_tenants
    created = client.post(BASE, json=_payload(), headers=a).json()
    job_url = f"{BASE}/{created['id']}"
    assert client.get(job_url, headers=b).status_code == 404
    assert client.patch(job_url, json={"location": "Hijacked"}, headers=b).status_code == 404
    assert client.delete(job_url, headers=b).status_code == 404
    # Untouched.
    assert client.get(job_url, headers=a).json()["location"] == "Bengaluru"


def test_partial_update_and_skill_replacement(client: TestClient, tenant_a) -> None:
    created = client.post(BASE, json=_payload(), headers=tenant_a).json()
    updated = client.patch(
        f"{BASE}/{created['id']}",
        json={"number_of_openings": 7, "required_skills": ["Go"]},
        headers=tenant_a,
    ).json()
    assert updated["number_of_openings"] == 7
    assert updated["job_title"] == "Senior Backend Engineer"
    assert [s["name"] for s in updated["required_skills"]] == ["Go"]


def test_a_job_order_can_be_closed(client: TestClient, tenant_a) -> None:
    created = client.post(BASE, json=_payload(), headers=tenant_a).json()
    updated = client.patch(
        f"{BASE}/{created['id']}", json={"status": "Closed"}, headers=tenant_a
    ).json()
    assert updated["status"] == "Closed"


def test_invalid_status_is_rejected(client: TestClient, tenant_a) -> None:
    created = client.post(BASE, json=_payload(), headers=tenant_a).json()
    response = client.patch(f"{BASE}/{created['id']}", json={"status": "Paused"}, headers=tenant_a)
    assert response.status_code == 422


def test_delete_removes_the_job_order(client: TestClient, tenant_a) -> None:
    created = client.post(BASE, json=_payload(), headers=tenant_a).json()
    assert client.delete(f"{BASE}/{created['id']}", headers=tenant_a).status_code == 204
    assert client.get(f"{BASE}/{created['id']}", headers=tenant_a).status_code == 404


# --- Stats ------------------------------------------------------------------


def test_stats_are_tenant_scoped(client: TestClient, two_tenants) -> None:
    a, b = two_tenants
    client.post(BASE, json=_payload(number_of_openings=2), headers=a)
    created = client.post(
        BASE, json=_payload(job_title="Other", number_of_openings=3), headers=a
    ).json()
    client.post(BASE, json=_payload(), headers=b)
    client.patch(f"{BASE}/{created['id']}", json={"status": "Closed"}, headers=a)

    stats = client.get(f"{BASE}/stats", headers=a).json()
    assert stats["total"] == 2
    assert stats["open"] == 1
    assert stats["total_openings"] == 2  # only counts open jobs
    assert client.get(f"{BASE}/stats", headers=b).json()["total"] == 1
