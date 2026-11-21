"""Story 2 - candidate CRUD, tenant isolation, search, sort, pagination."""

from fastapi.testclient import TestClient

BASE = "/api/v1/candidates"


def _payload(**overrides) -> dict:
    base = {
        "full_name": "Asha Rao",
        "location": "Bengaluru",
        "total_experience_years": "6.5",
        "skills": ["Python", "FastAPI"],
    }
    base.update(overrides)
    return base


# --- Tenant isolation: the headline requirement ---------------------------


def test_candidate_created_in_tenant_a_is_invisible_to_tenant_b(
    client: TestClient, two_tenants
) -> None:
    a, b = two_tenants
    created = client.post(BASE, json=_payload(), headers=a).json()

    in_a = client.get(BASE, headers=a).json()
    in_b = client.get(BASE, headers=b).json()

    assert [row["id"] for row in in_a["items"]] == [created["id"]]
    assert in_b["total"] == 0
    assert in_b["items"] == []


def test_reading_another_tenants_candidate_returns_404(client: TestClient, two_tenants) -> None:
    """Isolation is enforced in the query, not hidden in the UI."""
    a, b = two_tenants
    created = client.post(BASE, json=_payload(), headers=a).json()
    assert client.get(f"{BASE}/{created['id']}", headers=b).status_code == 404


def test_updating_another_tenants_candidate_returns_404(client: TestClient, two_tenants) -> None:
    a, b = two_tenants
    created = client.post(BASE, json=_payload(), headers=a).json()
    response = client.patch(f"{BASE}/{created['id']}", json={"location": "Hijacked"}, headers=b)
    assert response.status_code == 404
    # And the record is genuinely untouched.
    assert client.get(f"{BASE}/{created['id']}", headers=a).json()["location"] == "Bengaluru"


def test_deleting_another_tenants_candidate_returns_404(client: TestClient, two_tenants) -> None:
    a, b = two_tenants
    created = client.post(BASE, json=_payload(), headers=a).json()
    assert client.delete(f"{BASE}/{created['id']}", headers=b).status_code == 404
    assert client.get(f"{BASE}/{created['id']}", headers=a).status_code == 200


def test_candidate_endpoints_require_the_tenant_header(client: TestClient) -> None:
    response = client.get(BASE)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "MISSING_TENANT"


# --- Create ----------------------------------------------------------------


def test_create_returns_201_with_skills(client: TestClient, tenant_a) -> None:
    response = client.post(BASE, json=_payload(), headers=tenant_a)
    assert response.status_code == 201
    body = response.json()
    assert body["full_name"] == "Asha Rao"
    assert sorted(s["name"] for s in body["skills"]) == ["FastAPI", "Python"]
    assert body["has_cv"] is False
    assert body["submissions"] == []


def test_create_requires_at_least_one_skill(client: TestClient, tenant_a) -> None:
    response = client.post(BASE, json=_payload(skills=[]), headers=tenant_a)
    assert response.status_code == 422


def test_create_rejects_blank_name(client: TestClient, tenant_a) -> None:
    assert client.post(BASE, json=_payload(full_name="  "), headers=tenant_a).status_code == 422


def test_create_rejects_negative_experience(client: TestClient, tenant_a) -> None:
    response = client.post(BASE, json=_payload(total_experience_years="-2"), headers=tenant_a)
    assert response.status_code == 422


def test_create_rejects_absurd_experience(client: TestClient, tenant_a) -> None:
    response = client.post(BASE, json=_payload(total_experience_years="120"), headers=tenant_a)
    assert response.status_code == 422


def test_blank_optional_fields_become_null(client: TestClient, tenant_a) -> None:
    body = client.post(
        BASE, json=_payload(email="  ", phone="", current_role="  "), headers=tenant_a
    ).json()
    assert body["email"] is None and body["phone"] is None and body["current_role"] is None


# --- Skill resolution ------------------------------------------------------


def test_skill_aliases_resolve_to_the_canonical_skill(
    client: TestClient, tenant_a, seeded_skills
) -> None:
    """`reactjs` and `js` are aliases seeded in Story 1."""
    body = client.post(BASE, json=_payload(skills=["reactjs", "js"]), headers=tenant_a).json()
    assert sorted(s["name"] for s in body["skills"]) == ["JavaScript", "React"]


def test_an_alias_and_its_canonical_name_collapse_to_one_skill(
    client: TestClient, tenant_a, seeded_skills
) -> None:
    body = client.post(
        BASE, json=_payload(skills=["React", "reactjs", "  REACT  "]), headers=tenant_a
    ).json()
    assert [s["name"] for s in body["skills"]] == ["React"]


def test_unknown_skills_are_created(client: TestClient, tenant_a) -> None:
    body = client.post(BASE, json=_payload(skills=["Quantum Widgetry"]), headers=tenant_a).json()
    assert [s["name"] for s in body["skills"]] == ["Quantum Widgetry"]
    found = client.get("/api/v1/skills", params={"q": "quantum"}).json()
    assert found["total"] == 1


def test_skills_are_shared_across_tenants_but_candidates_are_not(
    client: TestClient, two_tenants
) -> None:
    a, b = two_tenants
    client.post(BASE, json=_payload(skills=["Rust"]), headers=a)
    client.post(BASE, json=_payload(full_name="Other", skills=["Rust"]), headers=b)
    # One shared vocabulary row...
    assert client.get("/api/v1/skills", params={"q": "Rust"}).json()["total"] == 1
    # ...but no shared candidates.
    assert client.get(BASE, headers=a).json()["total"] == 1
    assert client.get(BASE, headers=b).json()["total"] == 1


# --- Update ----------------------------------------------------------------


def test_partial_update_leaves_other_fields_alone(client: TestClient, tenant_a) -> None:
    created = client.post(BASE, json=_payload(), headers=tenant_a).json()
    updated = client.patch(
        f"{BASE}/{created['id']}", json={"location": "Pune"}, headers=tenant_a
    ).json()
    assert updated["location"] == "Pune"
    assert updated["full_name"] == "Asha Rao"
    assert sorted(s["name"] for s in updated["skills"]) == ["FastAPI", "Python"]


def test_updating_skills_replaces_the_whole_set(client: TestClient, tenant_a) -> None:
    created = client.post(BASE, json=_payload(), headers=tenant_a).json()
    updated = client.patch(
        f"{BASE}/{created['id']}", json={"skills": ["Go"]}, headers=tenant_a
    ).json()
    assert [s["name"] for s in updated["skills"]] == ["Go"]


def test_update_can_clear_an_optional_field(client: TestClient, tenant_a) -> None:
    created = client.post(BASE, json=_payload(email="a@example.com"), headers=tenant_a).json()
    updated = client.patch(f"{BASE}/{created['id']}", json={"email": None}, headers=tenant_a).json()
    assert updated["email"] is None


# --- Delete ----------------------------------------------------------------


def test_delete_removes_the_candidate(client: TestClient, tenant_a) -> None:
    created = client.post(BASE, json=_payload(), headers=tenant_a).json()
    assert client.delete(f"{BASE}/{created['id']}", headers=tenant_a).status_code == 204
    assert client.get(f"{BASE}/{created['id']}", headers=tenant_a).status_code == 404


def test_delete_does_not_remove_the_shared_skill(client: TestClient, tenant_a) -> None:
    created = client.post(BASE, json=_payload(skills=["Haskell"]), headers=tenant_a).json()
    client.delete(f"{BASE}/{created['id']}", headers=tenant_a)
    assert client.get("/api/v1/skills", params={"q": "Haskell"}).json()["total"] == 1


# --- List: search, sort, pagination ---------------------------------------


def test_list_omits_cv_bytes_entirely(client: TestClient, tenant_a) -> None:
    client.post(BASE, json=_payload(), headers=tenant_a)
    row = client.get(BASE, headers=tenant_a).json()["items"][0]
    assert "cv_data" not in row
    assert row["has_cv"] is False


def test_search_matches_name_location_and_skill(client: TestClient, tenant_a) -> None:
    client.post(BASE, json=_payload(full_name="Asha Rao", skills=["Python"]), headers=tenant_a)
    client.post(
        BASE,
        json=_payload(full_name="Bimal Sen", location="Chennai", skills=["Kafka"]),
        headers=tenant_a,
    )

    assert client.get(BASE, params={"q": "asha"}, headers=tenant_a).json()["total"] == 1
    assert client.get(BASE, params={"q": "chennai"}, headers=tenant_a).json()["total"] == 1
    assert client.get(BASE, params={"q": "kafka"}, headers=tenant_a).json()["total"] == 1


def test_search_by_skill_does_not_duplicate_rows(client: TestClient, tenant_a) -> None:
    """A JOIN against the link table would multiply rows; EXISTS does not."""
    client.post(BASE, json=_payload(skills=["Python", "Python"]), headers=tenant_a)
    body = client.get(BASE, params={"q": "Python"}, headers=tenant_a).json()
    assert body["total"] == 1
    assert len(body["items"]) == 1


def test_sort_by_experience_descending(client: TestClient, tenant_a) -> None:
    for name, years in (("A", "2"), ("B", "9"), ("C", "5")):
        client.post(
            BASE, json=_payload(full_name=name, total_experience_years=years), headers=tenant_a
        )
    items = client.get(
        BASE,
        params={"sort_by": "total_experience_years", "sort_dir": "desc"},
        headers=tenant_a,
    ).json()["items"]
    assert [i["full_name"] for i in items] == ["B", "C", "A"]


def test_unknown_sort_key_is_rejected(client: TestClient, tenant_a) -> None:
    response = client.get(BASE, params={"sort_by": "cv_data"}, headers=tenant_a)
    assert response.status_code == 422
    assert "allowed_sort_by" in response.json()["error"]["details"]


def test_pagination(client: TestClient, tenant_a) -> None:
    for index in range(5):
        client.post(BASE, json=_payload(full_name=f"Person {index}"), headers=tenant_a)
    page = client.get(BASE, params={"page": 2, "page_size": 2}, headers=tenant_a).json()
    assert page["total"] == 5
    assert page["total_pages"] == 3
    assert len(page["items"]) == 2


# --- Stats -----------------------------------------------------------------


def test_stats_are_tenant_scoped(client: TestClient, two_tenants) -> None:
    a, b = two_tenants
    client.post(BASE, json=_payload(), headers=a)
    client.post(BASE, json=_payload(full_name="Other"), headers=a)
    client.post(BASE, json=_payload(full_name="Elsewhere"), headers=b)

    assert client.get(f"{BASE}/stats", headers=a).json() == {
        "total": 2,
        "added_this_week": 2,
        "with_cv": 0,
    }
    assert client.get(f"{BASE}/stats", headers=b).json()["total"] == 1
